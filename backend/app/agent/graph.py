"""LangGraph State Machine for the AI Sales Associate."""
import logging
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from backend.app.agent.persona import (
    ACTION_INSTRUCTIONS,
    CURATION_INSTRUCTIONS,
    DISCOVERY_INSTRUCTIONS,
    GREETING_INSTRUCTIONS,
    OBJECTION_INSTRUCTIONS,
    STYLIST_CORE_SYSTEM_PROMPT,
    VALIDATION_INSTRUCTIONS,
)
from backend.app.agent.state import IntentStage, SalesState
from backend.app.catalog.catalog import CATALOG_ITEMS, get_product, search_catalog

load_dotenv()
logger = logging.getLogger("sales_engine.graph")


def make_punchy(text: str, max_sentences: int = 2) -> str:
    """Ensure in-store stylist never waffles; strict 2-sentence maximum."""
    if not text:
        return ""
    # Split by sentence endings (. ! ?)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) > max_sentences:
        return " ".join(sentences[:max_sentences])
    return text.strip()


def get_llm(temperature: float = 0.6, model: Optional[str] = None, max_tokens: int = 45) -> ChatGroq:
    """Initialize Groq LPU LLM client with strict token ceiling for snappy in-store banter."""
    api_key = os.getenv("GROQ_API_KEY")
    target_model = model or os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    return ChatGroq(
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        groq_api_key=api_key,
    )


def invoke_groq_resilient(prompt_messages: List[BaseMessage], temperature: float = 0.6) -> AIMessage:
    """
    Invoke Groq LPU with primary model (qwen/qwen3.8-27b) and graceful fallback.
    """
    candidates = [
        os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
    ]
    seen = set()
    models = [m for m in candidates if not (m in seen or seen.add(m))]

    last_exc = None
    for m in models:
        try:
            llm = get_llm(temperature=temperature, model=m)
            return llm.invoke(prompt_messages)
        except Exception as e:
            last_exc = e
            if "model_not_found" in str(e) or "does not exist" in str(e):
                logger.warning("Groq model %s unavailable, falling back to next candidate", m)
                continue
            raise e
    raise last_exc  # type: ignore


async def stream_groq_resilient(
    prompt_messages: List[BaseMessage], temperature: float = 0.6
) -> AsyncGenerator[Any, None]:
    """Stream Groq LPU response tokens asynchronously with resilient model fallback."""
    candidates = [
        os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
    ]
    seen = set()
    models = [m for m in candidates if not (m in seen or seen.add(m))]

    last_exc = None
    for m in models:
        try:
            llm = get_llm(temperature=temperature, model=m)
            async for chunk in llm.astream(prompt_messages):
                yield chunk
            return
        except Exception as e:
            last_exc = e
            if "model_not_found" in str(e) or "does not exist" in str(e):
                logger.warning("Groq model %s unavailable for streaming, falling back", m)
                continue
            raise e
    if last_exc:
        raise last_exc


def format_product_context(products: List[Dict[str, Any]]) -> str:
    """Format product dicts into a concise context block for the LLM."""
    if not products:
        return "No specific products currently selected."
    lines = []
    for p in products:
        lines.append(
            f"- [{p.get('id')}] {p.get('name')} (${p.get('price')}) | Fit: {p.get('fit')} | "
            f"Material: {p.get('material')}\n"
            f"  Hero: {p.get('hero_highlight')}\n"
            f"  Reviews: {p.get('reviews_summary', 'Top-rated')}"
        )
    return "\n".join(lines)


def _has_word(text: str, cues: List[str]) -> bool:
    """Check if any cue matches as a whole word or phrase in text."""
    for cue in cues:
        pattern = r"\b" + re.escape(cue) + r"\b"
        if re.search(pattern, text):
            return True
    return False


def classify_intent(state: SalesState) -> str:
    """
    Classify customer message to route to the appropriate sales stage:
    'greeting', 'discovery', 'curation', 'validation', 'objection', 'action'.
    """
    messages = state.get("messages", [])
    if not messages:
        return "greeting"

    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        current_node = state.get("current_node", "greeting")
        return current_node

    text = last_msg.content.lower().strip()

    # 1. Action / Cashier / Checkout cues
    action_cues = [
        "buy", "checkout", "order", "purchase", "add to cart", "cart",
        "take it", "i'll get", "i will get", "ill take", "ready to buy",
        "lock it in", "grab it", "payment", "ship", "discount", "discount code", "coupon", "apply", "promo"
    ]
    if _has_word(text, action_cues):
        return "action"

    # 2. Objection / Anxiety / Doubt / Policy cues
    objection_cues = [
        "size", "sizing", "fit", "true to size", "shrink", "scratchy",
        "wrinkle", "iron", "care", "expensive", "pricey",
        "return", "exchange", "refund", "return policy", "warranty",
        "tight", "loose", "run small", "run large", "too much", "measure", "height", "weight"
    ]
    if _has_word(text, objection_cues):
        return "objection"

    # 3. Validation / "Hero" pitch cues
    validation_cues = [
        "look like", "suit me", "pull this off", "how does it look",
        "opinion", "what do you think", "flattering", "posture",
        "match with", "pair with", "wear with", "style with", "tell me about this piece"
    ]
    if _has_word(text, validation_cues):
        return "validation"

    # 4. Curation / "The Rack Pull" cues
    curation_cues = [
        "show me", "recommend", "options", "looking for", "find me",
        "suggest", "outfit", "pieces", "jackets", "shirts", "pants",
        "what else", "rack", "collection", "bestsellers"
    ]
    if _has_word(text, curation_cues):
        return "curation"

    # 5. Discovery cues (answering occasion, style, preferences)
    discovery_cues = [
        "wedding", "date", "work", "office", "travel", "vacation",
        "summer", "dinner", "party", "casual", "smart casual", "formal",
        "relax", "relaxed", "tailored", "linen", "cotton", "comfort", "black", "navy", "olive"
    ]
    if _has_word(text, discovery_cues):
        return "discovery"

    # 6. Greetings / Initial approach
    greeting_cues = ["hi", "hello", "hey", "good morning", "good evening", "start", "help"]
    if _has_word(text, greeting_cues) or len(messages) <= 1:
        return "greeting"

    # Default based on current intent stage
    stage = state.get("intent_stage", "EXPLORER")
    if stage == "READY_TO_BUY":
        return "action"
    elif stage == "EVALUATOR":
        return "validation"
    return "discovery"


def build_node_prompt(node: str, state: SalesState) -> List[BaseMessage]:
    """Construct full prompt messages for a given sales stage node."""
    viewed = state.get("viewed_products", [])
    if not viewed and CATALOG_ITEMS:
        viewed = [CATALOG_ITEMS[0]]

    curated = state.get("recommended_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])
    profile = state.get("customer_profile", {})

    if node == "greeting":
        instruction = f"{GREETING_INSTRUCTIONS}\n\nCurrent items in view:\n{format_product_context(viewed)}"
    elif node == "discovery":
        instruction = f"{DISCOVERY_INSTRUCTIONS}\n\nCustomer Profile: {profile}\nBrowsed items:\n{format_product_context(viewed)}"
    elif node == "curation":
        items = curated if curated else CATALOG_ITEMS[:3]
        instruction = f"{CURATION_INSTRUCTIONS}\n\nItems pulled from rack:\n{format_product_context(items)}"
    elif node == "validation":
        instruction = f"{VALIDATION_INSTRUCTIONS}\n\nFeatured Hero Piece:\n{format_product_context([target])}"
    elif node == "objection":
        instruction = (
            f"{OBJECTION_INSTRUCTIONS}\n\n"
            f"Product details & verified reviews:\n{format_product_context([target])}\n"
            f"Guarantee: Free 30-day sizing exchanges & full refunds.\n"
            f"Stylist Promo Code: 'STYLIST10' for 10% off today."
        )
    elif node == "action":
        discounted_price = round(target.get("price", 100.0) * 0.9, 2)
        instruction = (
            f"{ACTION_INSTRUCTIONS}\n\n"
            f"Ready to checkout with item:\n{format_product_context([target])}\n"
            f"Discounted price: ${discounted_price} (10% off applied code STYLIST10).\n"
            f"Available sizes: {', '.join(target.get('sizes', []))}."
        )
    else:
        instruction = GREETING_INSTRUCTIONS

    system_content = f"{STYLIST_CORE_SYSTEM_PROMPT}\n\n{instruction}"
    prompt_messages: List[BaseMessage] = [SystemMessage(content=system_content)]
    prompt_messages.extend(state.get("messages", []))
    return prompt_messages


# ==================== NODE IMPLEMENTATIONS ====================

def greeting_node(state: SalesState) -> Dict[str, Any]:
    """Stage 1: Greeting & Approach."""
    viewed = state.get("viewed_products", [])
    if not viewed and CATALOG_ITEMS:
        viewed = [CATALOG_ITEMS[0]]

    prompt_messages = build_node_prompt("greeting", state)
    response = invoke_groq_resilient(prompt_messages, temperature=0.7)

    quick_replies = [
        "Looking for an upcoming event",
        "Tell me about this piece",
        "Show me bestsellers",
    ]

    return {
        "messages": [response],
        "current_node": "greeting",
        "intent_stage": "EXPLORER",
        "quick_replies": quick_replies,
        "viewed_products": viewed,
    }


def discovery_node(state: SalesState) -> Dict[str, Any]:
    """Stage 2: Consultative Discovery."""
    profile = state.get("customer_profile", {}).copy()
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""

    lower = last_msg.lower()
    for occ in ["wedding", "vacation", "date night", "work", "cocktails", "travel", "casual"]:
        if occ in lower:
            profile["occasion"] = occ
            break
    for fit in ["slim", "relaxed", "oversized", "tailored"]:
        if fit in lower:
            profile["fit_preference"] = fit
            break

    state["customer_profile"] = profile
    prompt_messages = build_node_prompt("discovery", state)
    response = invoke_groq_resilient(prompt_messages, temperature=0.6)

    quick_replies = [
        "Summer Wedding / Event",
        "Smart Casual Work & Dinners",
        "Relaxed Vacation Drape",
    ]

    return {
        "messages": [response],
        "customer_profile": profile,
        "current_node": "discovery",
        "intent_stage": "EXPLORER",
        "quick_replies": quick_replies,
    }


def curation_node(state: SalesState) -> Dict[str, Any]:
    """Stage 3: The Rack Pull (Curated Items)."""
    profile = state.get("customer_profile", {})
    occasion = profile.get("occasion")
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""

    curated = search_catalog(query=last_msg, occasion=occasion, limit=3)
    if len(curated) < 2:
        curated = CATALOG_ITEMS[:3]

    state["recommended_products"] = curated
    prompt_messages = build_node_prompt("curation", state)
    response = invoke_groq_resilient(prompt_messages, temperature=0.6)

    quick_replies = [
        f"How does the {curated[0]['name'].split()[-1]} fit?",
        "What shoes or pants pair with this?",
        "Tell me about the fabric quality",
    ]

    return {
        "messages": [response],
        "recommended_products": curated,
        "current_node": "curation",
        "intent_stage": "EVALUATOR",
        "quick_replies": quick_replies,
    }


def validation_node(state: SalesState) -> Dict[str, Any]:
    """Stage 4: Fitting Room ('Hero' Validation Compliment)."""
    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])

    prompt_messages = build_node_prompt("validation", state)
    response = invoke_groq_resilient(prompt_messages, temperature=0.65)

    quick_replies = [
        f"How's the sizing on the {target['name'].split()[-1]}?",
        "Can I see return policy?",
        "Let's lock in my size",
    ]

    return {
        "messages": [response],
        "current_node": "validation",
        "intent_stage": "EVALUATOR",
        "quick_replies": quick_replies,
    }


def objection_node(state: SalesState) -> Dict[str, Any]:
    """Stage 5: Objection Handling & Social Proof."""
    prompt_messages = build_node_prompt("objection", state)
    response = invoke_groq_resilient(prompt_messages, temperature=0.5)

    quick_replies = [
        "Sounds great, let's grab it!",
        "Apply the 10% discount",
        "What sizes are in stock?",
    ]

    return {
        "messages": [response],
        "current_node": "objection",
        "intent_stage": "READY_TO_BUY",
        "quick_replies": quick_replies,
    }


def action_node(state: SalesState) -> Dict[str, Any]:
    """Stage 6: Guided Checkout (The Cashier)."""
    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])

    cart_intent = state.get("cart_intent", {}).copy()
    cart_intent["items"] = [target]
    cart_intent["applied_discount"] = "STYLIST10"
    cart_intent["ready_for_checkout"] = True

    discounted_price = round(target.get("price", 100.0) * 0.9, 2)
    action_payload = {
        "type": "checkout",
        "product_id": target.get("id"),
        "product_name": target.get("name"),
        "original_price": target.get("price"),
        "discounted_price": discounted_price,
        "discount_code": "STYLIST10",
        "checkout_url": f"/checkout?item={target.get('id')}&discount=STYLIST10",
        "sizes_available": target.get("sizes", []),
    }

    prompt_messages = build_node_prompt("action", state)
    response = invoke_groq_resilient(prompt_messages, temperature=0.5)

    quick_replies = [
        "Complete 1-Tap Purchase",
        "Change my size",
        "Add one more piece",
    ]

    return {
        "messages": [response],
        "current_node": "action",
        "intent_stage": "READY_TO_BUY",
        "cart_intent": cart_intent,
        "action_payload": action_payload,
        "quick_replies": quick_replies,
    }


# ==================== BUILD STATE MACHINE GRAPH ====================

def build_sales_graph():
    """Compile the LangGraph state machine with 6 sales nodes."""
    workflow = StateGraph(SalesState)

    workflow.add_node("greeting", greeting_node)
    workflow.add_node("discovery", discovery_node)
    workflow.add_node("curation", curation_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("objection", objection_node)
    workflow.add_node("action", action_node)

    workflow.add_conditional_edges(
        START,
        classify_intent,
        {
            "greeting": "greeting",
            "discovery": "discovery",
            "curation": "curation",
            "validation": "validation",
            "objection": "objection",
            "action": "action",
        },
    )

    workflow.add_edge("greeting", END)
    workflow.add_edge("discovery", END)
    workflow.add_edge("curation", END)
    workflow.add_edge("validation", END)
    workflow.add_edge("objection", END)
    workflow.add_edge("action", END)

    return workflow.compile()


sales_graph = build_sales_graph()
