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
    # Strip any pills tag (closed or unclosed/truncated) before sentence splitting
    clean = re.sub(r'<pills>[\s\S]*?(?:</pills>|$)', '', text, flags=re.DOTALL).strip()
    sentences = re.split(r'(?<=[.!?])\s+', clean)
    if len(sentences) > max_sentences:
        return " ".join(sentences[:max_sentences])
    return clean


def parse_price(val: Any) -> float:
    """Parse numeric price from float, int, or formatted currency string ($349.00 -> 349.00)."""
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 100.0
    try:
        cleaned = re.sub(r"[^\d.]", "", str(val))
        return float(cleaned) if cleaned else 100.0
    except Exception:
        return 100.0


def extract_pills_and_clean_message(content: str, default_pills: List[str]) -> tuple[str, List[str]]:
    """Extract <pills>["..."]</pills> from LLM response and return (clean_text, pills)."""
    pills = default_pills
    if content:
        # Match complete or truncated <pills> block
        match = re.search(r'<pills>\s*(\[.*?\])\s*(?:</pills>|$)', content, re.DOTALL)
        if match:
            try:
                import json
                parsed = json.loads(match.group(1))
                if isinstance(parsed, list) and parsed:
                    pills = [str(p) for p in parsed]
            except Exception:
                extracted = re.findall(r'"([^"\\]+)"', match.group(1))
                if extracted:
                    pills = extracted
        elif "<pills>" in content:
            raw_pills = content[content.find("<pills>"):]
            extracted = re.findall(r'"([^"\\]+)"', raw_pills)
            if extracted:
                pills = extracted

    cleaned = make_punchy(content, max_sentences=2)
    return cleaned, pills


def get_llm(temperature: float = 0.6, model: Optional[str] = None, max_tokens: int = 700) -> ChatGroq:
    """Initialize Groq LPU LLM client with token ceiling sufficient for reasoning + punchy banter + dynamic pills."""
    api_key = os.getenv("GROQ_API_KEY")
    target_model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    return ChatGroq(
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        groq_api_key=api_key,
    )


def invoke_groq_resilient(prompt_messages: List[BaseMessage], temperature: float = 0.6) -> AIMessage:
    """
    Invoke Groq LPU with primary model (openai/gpt-oss-120b) and graceful fallback.
    """
    candidates = [
        os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
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
        os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
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
        p_id = p.get('id') or p.get('sku') or 'item'
        p_name = p.get('title') or p.get('name') or 'Featured Item'
        price = parse_price(p.get('price', 100.0))
        fit = p.get('fit') or 'Tailored true to size'
        material = p.get('material') or (
            p.get('description', '')[:80] if p.get('description') else 'Premium Italian craftsmanship'
        )
        hero = p.get('hero_highlight') or p.get('description') or 'Impeccable modern silhouette'
        reviews = p.get('reviews_summary') or f"{p.get('rating', '4.9')} stars ({p.get('reviewCount', '128')} reviews)"

        sizes = p.get('sizes') or (p.get('variants', {}).get('sizes') if isinstance(p.get('variants'), dict) else [])
        sizes_str = ", ".join(sizes) if sizes else "S, M, L, XL"

        lines.append(
            f"- [{p_id}] {p_name} (${price:.2f}) | Fit: {fit} | Material: {material} | Sizes: {sizes_str}\n"
            f"  Hero: {hero}\n"
            f"  Reviews: {reviews}"
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
    words = text.split()

    # Find prior AI message if any, to give contextual continuity
    prior_ai_msg = None
    for m in reversed(messages[:-1]):
        if isinstance(m, AIMessage):
            prior_ai_msg = m.content.lower()
            break

    # 1. Action / Cashier / Checkout cues
    action_cues = [
        "buy", "checkout", "order", "purchase", "add to cart", "cart",
        "take it", "i'll get", "i will get", "ill take", "ready to buy",
        "lock it in", "grab it", "payment", "ship", "discount", "discount code",
        "coupon", "apply", "promo", "stylist10", "view & buy", "view and buy"
    ]
    if _has_word(text, action_cues):
        return "action"

    # 2. Objection / Anxiety / Doubt / Policy / Sizing cues
    objection_cues = [
        "size", "sizing", "fit", "true to size", "shrink", "scratchy",
        "wrinkle", "iron", "care", "expensive", "pricey",
        "return", "exchange", "refund", "return policy", "warranty",
        "tight", "loose", "run small", "run large", "too much", "measure", "height", "weight",
        "between medium and large", "between small and medium", "between large and xl",
        "stretch", "fabric stretch", "does it shrink"
    ]
    if _has_word(text, objection_cues):
        return "objection"

    # Contextual check: If prior AI asked about sizing/fit and user provides a size (e.g. "medium", "m", "large", "l")
    if prior_ai_msg and any(w in prior_ai_msg for w in ["size", "height", "fit", "measure"]):
        size_answers = ["small", "medium", "large", "xl", "xs", "s", "m", "l", "inches", "cm", "lbs", "kg"]
        if _has_word(text, size_answers):
            return "objection"

    # 3. Validation / "Hero" pitch cues
    validation_cues = [
        "look like", "suit me", "pull this off", "how does it look",
        "opinion", "what do you think", "flattering", "posture",
        "match with", "pair with", "wear with", "style with", "tell me about this piece",
        "shoes", "pants", "trousers", "sneakers", "loafers", "accessories", "color", "colour",
        "will this suit", "dress this down", "dress up"
    ]
    if _has_word(text, validation_cues):
        return "validation"

    # 4. Curation / "The Rack Pull" cues or disliking current piece
    curation_cues = [
        "show me", "recommend", "options", "looking for", "find me",
        "suggest", "outfit", "pieces", "jackets", "shirts", "pants",
        "what else", "rack", "collection", "bestsellers",
        "don't like", "dont like", "not like", "something else", "different", "other styles", "fresh styles"
    ]
    if _has_word(text, curation_cues):
        return "curation"

    # 5. Discovery cues (answering occasion, style, preferences, wedding/reception/ceremony)
    discovery_cues = [
        "wedding", "marriage", "marraige", "ceremony", "reception", "gala",
        "date", "date night", "work", "office", "travel", "vacation", "trip", "holiday",
        "summer", "winter", "spring", "fall", "dinner", "cocktail", "party", "event",
        "casual", "smart casual", "formal", "black tie", "everyday", "daily",
        "relax", "relaxed", "tailored", "linen", "wool", "cotton", "comfort",
        "black", "navy", "olive", "charcoal", "camel", "white", "blue", "grey", "gray",
        "both", "either", "reception only", "ceremony only", "yes", "shopping for an occasion"
    ]
    if _has_word(text, discovery_cues):
        return "discovery"

    # Contextual check: If prior AI asked a question (e.g. ceremony or reception? event or everyday?)
    if prior_ai_msg and ("ceremony" in prior_ai_msg or "reception" in prior_ai_msg or "event" in prior_ai_msg or "occasion" in prior_ai_msg):
        if len(words) <= 5:
            return "discovery"

    # 6. Chit-Chat / Playful / About Julian (never reset to greeting!)
    chitchat_cues = [
        "who are you", "who r u", "what is ur name", "what's your name", "whats your name",
        "your name", "ur name", "name", "are u biased", "are you biased", "biased",
        "are u based", "are you based", "where are you", "where are u", "who made you",
        "are you human", "are you a bot", "are you ai"
    ]
    if _has_word(text, chitchat_cues):
        return "discovery"

    # 7. Greetings / Initial approach ONLY if explicitly a greeting
    greeting_cues = ["hi", "hello", "hey", "good morning", "good evening", "good afternoon", "howdy", "greetings"]
    human_messages = [m for m in messages if isinstance(m, HumanMessage)]
    if _has_word(text, greeting_cues) and len(human_messages) <= 1 and len(words) <= 4:
        return "greeting"

    # Default based on current intent stage or previous node
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

    target_price = parse_price(target.get("price", 100.0))
    discounted_price = round(target_price * 0.9, 2)
    sizes_avail = target.get("sizes") or (target.get("variants", {}).get("sizes") if isinstance(target.get("variants"), dict) else [])
    sizes_str = ", ".join(sizes_avail) if sizes_avail else "S, M, L, XL"

    if node == "greeting":
        instruction = f"{GREETING_INSTRUCTIONS}\n\nCurrent items in view:\n{format_product_context(viewed)}"
    elif node == "discovery":
        instruction = f"{DISCOVERY_INSTRUCTIONS}\n\nCustomer Profile: {profile}\nBrowsed items:\n{format_product_context(viewed)}"
    elif node == "curation":
        items = curated if curated else (viewed if viewed else CATALOG_ITEMS[:3])
        instruction = f"{CURATION_INSTRUCTIONS}\n\nItems pulled from rack:\n{format_product_context(items)}"
    elif node == "validation":
        instruction = f"{VALIDATION_INSTRUCTIONS}\n\nFeatured Hero Piece:\n{format_product_context([target])}"
    elif node == "objection":
        instruction = (
            f"{OBJECTION_INSTRUCTIONS}\n\n"
            f"Product details & verified reviews:\n{format_product_context([target])}\n"
            f"Guarantee: Free 30-day sizing exchanges & full refunds.\n"
            f"Stylist Promo Code: 'STYLIST10' for 10% off today (Original: ${target_price:.2f} -> Discounted: ${discounted_price:.2f})."
        )
    elif node == "action":
        instruction = (
            f"{ACTION_INSTRUCTIONS}\n\n"
            f"Ready to checkout with item:\n{format_product_context([target])}\n"
            f"Original price: ${target_price:.2f}. Discounted price (10% off with STYLIST10): ${discounted_price:.2f}.\n"
            f"Available sizes: {sizes_str}."
        )
    else:
        instruction = GREETING_INSTRUCTIONS

    system_content = f"{STYLIST_CORE_SYSTEM_PROMPT}\n\n{instruction}"
    prompt_messages: List[BaseMessage] = [SystemMessage(content=system_content)]

    # Sliding window: keep the last 8-10 messages (4-5 turns) for LLM context to prevent
    # reasoning token exhaustion on long conversations, while state["messages"] preserves
    # the complete multi-turn conversation history.
    history = state.get("messages", [])
    if len(history) > 8:
        window = history[-8:]
        # Ensure window starts with a HumanMessage for clean user->assistant alternating turns
        if window and isinstance(window[0], AIMessage):
            window = history[-9:] if len(history) >= 9 and isinstance(history[-9], HumanMessage) else window[1:]
        prompt_messages.extend(window)
    else:
        prompt_messages.extend(history)

    return prompt_messages


# ==================== NODE IMPLEMENTATIONS ====================

def greeting_node(state: SalesState) -> Dict[str, Any]:
    """Stage 1: Greeting & Approach."""
    viewed = state.get("viewed_products", [])
    if not viewed and CATALOG_ITEMS:
        viewed = [CATALOG_ITEMS[0]]

    prompt_messages = build_node_prompt("greeting", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.7)

    default_replies = [
        "Shopping for an occasion",
        "Tell me about this piece",
        "Check sizing & fit",
    ]
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies)
    response = AIMessage(content=clean_text)

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
    for occ in ["wedding", "marriage", "reception", "ceremony", "vacation", "date night", "work", "cocktails", "travel", "casual"]:
        if occ in lower:
            profile["occasion"] = occ
            break
    for fit in ["slim", "relaxed", "oversized", "tailored"]:
        if fit in lower:
            profile["fit_preference"] = fit
            break

    state["customer_profile"] = profile
    prompt_messages = build_node_prompt("discovery", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.6)

    default_replies = [
        "Ceremony & Reception",
        "Smart Casual Dinners",
        "Check my size",
    ]
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies)
    response = AIMessage(content=clean_text)

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
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.6)

    first_name = curated[0].get('name', curated[0].get('title', 'Piece')).split()[-1]
    default_replies = [
        f"How does the {first_name} fit?",
        "What shoes or pants pair with this?",
        "Apply 10% discount",
    ]
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies)
    response = AIMessage(content=clean_text)

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
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.65)

    target_name = target.get('name', target.get('title', 'Piece')).split()[-1]
    default_replies = [
        f"How's the sizing on the {target_name}?",
        "What shoes pair best?",
        "Apply 10% discount and buy",
    ]
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies)
    response = AIMessage(content=clean_text)

    return {
        "messages": [response],
        "current_node": "validation",
        "intent_stage": "EVALUATOR",
        "quick_replies": quick_replies,
    }


def objection_node(state: SalesState) -> Dict[str, Any]:
    """Stage 5: Objection Handling & Social Proof."""
    prompt_messages = build_node_prompt("objection", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.5)

    default_replies = [
        "I'm between Medium and Large",
        "Apply the 10% discount and let's buy",
        "What sizes are in stock?",
    ]
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies)
    response = AIMessage(content=clean_text)

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

    target_price = parse_price(target.get("price", 100.0))
    discounted_price = round(target_price * 0.9, 2)
    sizes_avail = target.get("sizes") or (target.get("variants", {}).get("sizes") if isinstance(target.get("variants"), dict) else [])
    target_name = target.get("title") or target.get("name") or "Featured Item"

    action_payload = {
        "type": "checkout",
        "product_id": target.get("id"),
        "product_name": target_name,
        "original_price": target_price,
        "discounted_price": discounted_price,
        "discount_code": "STYLIST10",
        "checkout_url": f"/checkout?item={target.get('id')}&discount=STYLIST10",
        "sizes_available": sizes_avail,
    }

    prompt_messages = build_node_prompt("action", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.5)

    default_replies = [
        "View & Buy",
        "What shoes pair with this?",
        "What is your return policy?",
    ]
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies)
    response = AIMessage(content=clean_text)

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
