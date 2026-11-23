"""LangGraph State Machine for the AI Sales Associate.

Modern LangChain v0.3+ / v1.x architecture featuring:
- MemorySaver checkpointer persistence for thread memory
- trim_messages token windowing with start_on='human' and include_system=True
- LangChain Core @tool definitions and ToolNode
- Structured output support via with_structured_output
- Resilient model execution with streaming astream_events support
- Eliminates conversational amnesia on brief replies (e.g. 'reception', 'medium', '42')
"""
import logging
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from dotenv import load_dotenv

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    trim_messages,
)
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from backend.app.agent.persona import (
    ACTION_INSTRUCTIONS,
    CURATION_INSTRUCTIONS,
    DISCOVERY_INSTRUCTIONS,
    GREETING_INSTRUCTIONS,
    OBJECTION_INSTRUCTIONS,
    STYLIST_CORE_SYSTEM_PROMPT,
    VALIDATION_INSTRUCTIONS,
)
from backend.app.agent.state import IntentStage, SalesState, StylistStructuredResponse
from backend.app.catalog.catalog import CATALOG_ITEMS, get_product, list_catalog, search_catalog

load_dotenv()
logger = logging.getLogger("sales_engine.graph")

# Global in-memory checkpointer for session state persistence across threads
memory_saver = MemorySaver()


# ==================== FORMATTING & TEXT UTILS ====================

def make_punchy(text: str, max_sentences: int = 2) -> str:
    """Ensure in-store stylist never waffles; strictly 1-2 short sentences (under 25 words)."""
    if not text:
        return ""
    # Strip any pills tag (closed or unclosed/truncated) or markdown blocks before sentence splitting
    clean = re.sub(r'<pills>[\s\S]*?(?:</pills>|$)', '', text, flags=re.DOTALL).strip()
    clean = re.sub(r'```(?:json)?[\s\S]*?(?:```|$)', '', clean).strip()
    clean = re.sub(r'[\r\n]+', ' ', clean).strip()

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    if len(sentences) > max_sentences:
        clean = " ".join(sentences[:max_sentences])
    words = clean.split()
    if len(words) > 25:
        trimmed = " ".join(words[:25])
        if not trimmed.endswith((".", "!", "?")):
            trimmed += "."
        return trimmed
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


def extract_pills_and_clean_message(content: str, default_pills: List[str], fallback_text: str = "") -> tuple[str, List[str]]:
    """Extract <pills>["..."]</pills> from LLM response and return (clean_text, pills)."""
    pills = list(default_pills)
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
    if not cleaned and fallback_text:
        cleaned = make_punchy(fallback_text, max_sentences=2)
    return cleaned, pills


def product_sizes(product: Dict[str, Any]) -> List[str]:
    """Normalize available sizes list from product specification."""
    if not isinstance(product, dict):
        return []
    sizes = product.get("sizes")
    if not sizes and isinstance(product.get("variants"), dict):
        sizes = product["variants"].get("sizes")
    if isinstance(sizes, str):
        sizes = [sizes]
    if not isinstance(sizes, list):
        return []
    return [str(size).strip() for size in sizes
            if type(size) in (str, int, float) and str(size).strip()]


def format_product_context(products: List[Dict[str, Any]]) -> str:
    """Format product dicts into a concise context block for the LLM."""
    if not products:
        return "No specific products currently selected."
    lines = []
    for p in products:
        p_id = p.get('id') or p.get('sku') or 'item'
        p_name = p.get('title') or p.get('name') or 'Featured Item'
        price = parse_price(p.get('price', 100.0))
        fit = p.get('fit') or 'Not supplied'
        material = p.get('material') or (
            p.get('description', '')[:80] if p.get('description') else 'Not supplied'
        )
        hero = p.get('hero_highlight') or p.get('description') or 'Not supplied'
        reviews = p.get('reviews_summary') or (f"{p['rating']} stars" if p.get("rating") else "Not supplied")

        sizes = product_sizes(p)
        sizes_str = ", ".join(sizes) if sizes else "Not supplied"

        lines.append(
            f"- [{p_id}] {p_name} (${price:.2f}) | Fit: {fit} | Material: {material} | Sizes: {sizes_str}\n"
            f"  Hero: {hero}\n"
            f"  Reviews: {reviews}"
        )
    return "\n".join(lines)


def has_word(text: str, cues: List[str]) -> bool:
    """Check if any cue matches as a whole word or phrase in text."""
    for cue in cues:
        pattern = r"\b" + re.escape(cue) + r"\b"
        if re.search(pattern, text):
            return True
    return False


# ==================== LANGCHAIN TOOLS & TOOL NODE ====================

@tool
def search_store_catalog(query: str = "", category: Optional[str] = None, max_price: Optional[float] = None, occasion: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search Karthik & Co. Modern Apparel catalog for matching shirts, jackets, pants, or suits by query, category, price, or occasion."""
    return search_catalog(query=query, category=category, max_price=max_price, occasion=occasion, limit=3)


@tool
def get_product_specs(product_id: str) -> Dict[str, Any]:
    """Retrieve full product specs, available sizes, fabric materials, fit guide, and verified customer reviews."""
    prod = get_product(product_id)
    return prod if prod else {"error": f"Product '{product_id}' not found"}


@tool
def calculate_discount(product_id: str, promo_code: str = "STYLIST10") -> Dict[str, Any]:
    """Calculate 10% VIP stylist discount code STYLIST10 for a product."""
    prod = get_product(product_id) or {}
    price = parse_price(prod.get("price", 100.0))
    discount_rate = 0.10 if promo_code.upper() == "STYLIST10" else 0.0
    discounted = round(price * (1.0 - discount_rate), 2)
    return {
        "product_id": product_id,
        "original_price": price,
        "discount_code": promo_code.upper(),
        "discounted_price": discounted,
        "savings": round(price - discounted, 2),
    }


sales_tools = [search_store_catalog, get_product_specs, calculate_discount]
sales_tool_node = ToolNode(sales_tools)


# ==================== MODEL CLIENT & FALLBACKS ====================

def get_llm(temperature: float = 0.6, model: Optional[str] = None, max_tokens: int = 1500) -> ChatGroq:
    """Initialize Groq LPU LLM client with token ceiling sufficient for reasoning + punchy banter + dynamic pills."""
    api_key = os.getenv("GROQ_API_KEY")
    target_model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    return ChatGroq(
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        groq_api_key=api_key,
    )


def get_structured_llm(temperature: float = 0.6, model: Optional[str] = None):
    """Initialize LLM bound with Pydantic structured output schema for typed responses."""
    llm = get_llm(temperature=temperature, model=model)
    return llm.with_structured_output(StylistStructuredResponse)


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


# ==================== CUSTOMER PROFILE EXTRACTION ====================

def update_customer_profile(state: SalesState, user_text: str) -> Dict[str, Any]:
    """
    Extract occasion, sizing, fit, and budget cues from customer text and update
    state['customer_profile'] preserving multi-turn context without amnesia.
    """
    profile = state.get("customer_profile", {}).copy()
    lower = user_text.lower().strip()
    if not lower:
        return profile

    # 1. Occasions
    occasions = [
        "wedding", "marriage", "reception", "ceremony", "vacation", "date night",
        "work", "office", "cocktails", "travel", "casual", "gala", "dinner", "black tie"
    ]
    for occ in occasions:
        if occ in lower:
            norm_occ = "wedding" if occ == "marriage" else occ
            curr = profile.get("occasion")
            if curr and norm_occ not in curr.lower():
                if curr.lower() in ("wedding", "marriage") and norm_occ in ("reception", "ceremony"):
                    profile["occasion"] = f"wedding ({norm_occ})"
                elif norm_occ in ("wedding", "marriage") and curr.lower() in ("reception", "ceremony"):
                    profile["occasion"] = f"wedding ({curr})"
                elif curr.lower() in ("wedding", "marriage") and norm_occ in ("wedding", "marriage"):
                    pass  # synonyms
                else:
                    profile["occasion"] = f"{curr}, {norm_occ}"
            elif not curr:
                profile["occasion"] = norm_occ
            break

    # 2. Fit preferences
    for fit in ["slim", "relaxed", "oversized", "tailored"]:
        if fit in lower:
            profile["fit_preference"] = fit
            break

    # 3. Sizes
    sizes = [
        "36", "38", "40", "42", "44", "46", "48",
        "38r", "40r", "42r", "44r", "38s", "40s", "42s", "38l", "40l", "42l",
        "xs", "s", "m", "l", "xl", "xxl", "small", "medium", "large"
    ]
    for sz in sizes:
        if re.search(r"\b" + re.escape(sz) + r"\b", lower):
            profile["size"] = sz.upper() if len(sz) <= 3 else sz.capitalize()
            break

    # 4. Budget
    budget_match = re.search(r"(?:under|below|up to|budget(?: is)?|around)\s*\$?(\d+(?:\.\d+)?)", lower)
    if budget_match:
        try:
            profile["budget"] = float(budget_match.group(1))
        except ValueError:
            pass

    state["customer_profile"] = profile
    return profile


# ==================== INTENT ROUTER ====================

def classify_intent(state: SalesState) -> str:
    """
    Classify customer message to route to the appropriate sales stage:
    'greeting', 'discovery', 'curation', 'validation', 'objection', 'action'.
    Solves conversational amnesia on brief replies (e.g. 'reception', 'medium', '42').
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
        if isinstance(m, (AIMessage, BaseMessage)):
            prior_ai_msg = str(m.content).lower()
            break

    # Also check viewed product sizes for contextual sizing answers
    viewed = state.get("viewed_products", [])
    curated = state.get("recommended_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else {})
    target_sizes = [s.lower() for s in product_sizes(target)]

    # 1. Action / Cashier / Checkout cues
    action_cues = [
        "buy", "checkout", "order", "purchase", "add to cart", "cart",
        "take it", "i'll get", "i will get", "ill take", "ready to buy",
        "lock it in", "grab it", "payment", "ship", "discount", "discount code",
        "coupon", "apply", "promo", "stylist10", "view & buy", "view and buy",
        "let's buy", "lets buy", "complete checkout", "i love it, let's grab it!",
        "i love it let's grab it", "let's grab it", "lets grab it"
    ]
    if has_word(text, action_cues):
        return "action"

    # 2. Chit-Chat / Playful / About Julian (never reset to greeting!)
    chitchat_cues = [
        "who are you", "who r u", "what is ur name", "what's your name", "whats your name",
        "your name", "ur name", "are u biased", "are you biased", "biased",
        "are u based", "are you based", "where are you", "where are u", "who made you",
        "are you human", "are you a bot", "are you ai"
    ]
    if has_word(text, chitchat_cues):
        return "discovery"

    # 3. Explicit Curation cues (searching catalog, rack pull, browsing, alternative options)
    # Even if size/fit is mentioned as a search filter (e.g. "show me shirts in medium", "find me jackets in size L")
    curation_explicit_cues = [
        "show me", "recommend", "options", "looking for", "find me",
        "suggest", "what else", "rack", "collection", "bestsellers",
        "don't like", "dont like", "not like", "something else", "different",
        "other styles", "fresh styles", "just browsing fresh styles", "browse",
        "browsing", "alternatives"
    ]
    objection_doubt_phrases = [
        "how does it fit", "how does this fit", "does it fit", "will it fit",
        "true to size", "shrink", "return policy", "warranty", "exchange", "refund",
        "scratchy", "wrinkle", "iron", "care instructions", "expensive", "too much"
    ]
    has_curation = has_word(text, curation_explicit_cues)
    has_objection_doubt = has_word(text, objection_doubt_phrases)
    if has_curation and not has_objection_doubt:
        return "curation"

    # 4. Fit preferences (discovery - not objection!)
    fit_pref_cues = [
        "relaxed fit", "slim fit", "tailored fit", "oversized fit", "loose fit", "classic fit",
        "relaxed", "tailored", "oversized"
    ]
    if has_word(text, fit_pref_cues) and not has_objection_doubt and not has_word(text, ["how", "does", "will", "shrink"]):
        return "discovery"

    # 5. Objection / Anxiety / Doubt / Policy / Sizing cues
    text_clean = re.sub(r"\b[iI]['’]m\b", "i am", text)
    objection_cues = [
        "size", "sizing", "fit", "fits", "true to size", "shrink", "scratchy",
        "wrinkle", "iron", "care", "expensive", "pricey",
        "return", "exchange", "refund", "return policy", "warranty",
        "tight", "loose", "run small", "run large", "too much", "measure", "height", "weight",
        "between medium and large", "between small and medium", "between large and xl",
        "stretch", "fabric stretch", "does it shrink", "in stock", "stock",
        "check my size", "check sizing", "i wear", "my size"
    ]
    # Sizing terms that directly answer or inquire about sizing
    size_terms = [
        "small", "medium", "large", "xl", "xs", "xxl",
        "36", "38", "40", "42", "44", "46", "48",
        "38r", "40r", "42r", "44r", "38s", "40s", "42s", "38l", "40l", "42l"
    ]
    is_objection = has_word(text_clean, objection_cues) or (
        has_word(text_clean, size_terms) and (len(words) <= 4 or has_word(text_clean, ["wear", "size", "between", "measure", "am", "i"]))
    )
    if not is_objection and target_sizes:
        for sz in target_sizes:
            sz_l = str(sz).lower().strip()
            if not sz_l:
                continue
            if len(sz_l) == 1:
                if text_clean.strip() == sz_l or re.search(r"\b(?:size|wear|in)\s+" + re.escape(sz_l) + r"\b", text_clean):
                    is_objection = True
                    break
            elif has_word(text_clean, [sz_l]):
                is_objection = True
                break

    if is_objection:
        return "objection"

    # Contextual check: If prior AI asked about sizing/fit and user provides brief size answer
    if prior_ai_msg and any(w in prior_ai_msg for w in ["size", "height", "fit", "measure"]):
        size_answers = ["small", "medium", "large", "xl", "xs", "s", "m", "l", "inches", "cm", "lbs", "kg", "42", "40", "38"]
        if has_word(text, size_answers):
            return "objection"

    # 6. Validation / "Hero" pitch & Styling cues
    validation_cues = [
        "look like", "suit me", "pull this off", "how does it look",
        "opinion", "what do you think", "flattering", "posture",
        "match with", "pair with", "wear with", "style with", "tell me about this piece",
        "shoes", "pants", "trousers", "sneakers", "loafers", "accessories", "color", "colour",
        "will this suit", "dress this down", "dress up", "how should i style this", "what should i pair with this"
    ]
    if has_word(text, validation_cues):
        return "validation"

    # 7. Remaining Curation cues (piece types like "jackets", "shirts", "pants")
    catalog_types = ["outfit", "pieces", "jackets", "shirts", "pants", "suit", "blazer", "trouser", "trousers", "overshirt"]
    if has_word(text, catalog_types) and any(w in text for w in ["other", "show", "give", "need", "want", "more"]):
        return "curation"

    # 8. Discovery cues (answering occasion, style, preferences, wedding/reception/ceremony)
    discovery_cues = [
        "wedding", "marriage", "marraige", "ceremony", "reception", "gala",
        "date", "date night", "work", "office", "travel", "vacation", "trip", "holiday",
        "summer", "winter", "spring", "fall", "dinner", "cocktail", "party", "event",
        "casual", "smart casual", "formal", "black tie", "everyday", "daily",
        "linen", "wool", "cotton", "comfort",
        "black", "navy", "olive", "charcoal", "camel", "white", "blue", "grey", "gray",
        "both", "either", "reception only", "ceremony only", "yes", "shopping for an occasion",
        "ceremony & reception", "smart casual dinners"
    ]
    if has_word(text, discovery_cues):
        return "discovery"

    # Contextual check: If prior AI asked a question (e.g. ceremony or reception? event or everyday?)
    if prior_ai_msg and ("ceremony" in prior_ai_msg or "reception" in prior_ai_msg or "event" in prior_ai_msg or "occasion" in prior_ai_msg):
        if len(words) <= 5:
            return "discovery"

    # 9. Greetings / Initial approach ONLY if explicitly an opening greeting
    greeting_cues = ["hi", "hello", "hey", "good morning", "good evening", "good afternoon", "howdy", "greetings"]
    human_messages = [m for m in messages if isinstance(m, HumanMessage)]
    if has_word(text, greeting_cues) and len(human_messages) <= 1 and len(words) <= 4:
        return "greeting"

    # Default based on current intent stage or previous node
    stage = state.get("intent_stage", "EXPLORER")
    if stage == "READY_TO_BUY":
        return "action"
    elif stage == "EVALUATOR":
        return "validation"
    return "discovery"


# ==================== PROMPT BUILDER WITH MODERN MESSAGE TRIMMING ====================

def build_node_prompt(node: str, state: SalesState) -> List[BaseMessage]:
    """
    Construct full prompt messages for a given sales stage node.
    Applies modern LangChain trim_messages to maintain exact token budgets,
    start on a HumanMessage, preserve the SystemMessage, and prevent repetitive loops.
    """
    viewed = state.get("viewed_products", [])
    inventory = state.get("catalog_items", CATALOG_ITEMS)
    if not viewed:
        viewed = inventory[:1]

    curated = state.get("recommended_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else {})
    profile = state.get("customer_profile", {})

    target_price = parse_price(target.get("price", 100.0))
    discounted_price = round(target_price * 0.9, 2)
    sizes_avail = product_sizes(target)
    sizes_str = ", ".join(sizes_avail) if sizes_avail else "Not supplied"

    if node == "greeting":
        instruction = f"{GREETING_INSTRUCTIONS}\n\nCurrent items in view:\n{format_product_context(viewed)}"
    elif node == "discovery":
        instruction = f"{DISCOVERY_INSTRUCTIONS}\n\nCustomer Profile: {profile}\nBrowsed items:\n{format_product_context(viewed)}"
    elif node == "curation":
        items = curated if curated else (viewed if viewed else inventory[:3])
        instruction = f"{CURATION_INSTRUCTIONS}\n\nItems pulled from rack:\n{format_product_context(items)}"
    elif node == "validation":
        instruction = f"{VALIDATION_INSTRUCTIONS}\n\nFeatured Hero Piece:\n{format_product_context([target])}"
    elif node == "objection":
        instruction = (
            f"{OBJECTION_INSTRUCTIONS}\n\n"
            f"Product details & verified reviews:\n{format_product_context([target])}\n"
            f"Customer Profile Sizing/Fit: Size={profile.get('size')}, Fit={profile.get('fit_preference')}.\n"
            f"Return policy: {target.get('return_policy') or 'Not supplied'}.\n"
            f"Stylist Promo Code: 'STYLIST10' for 10% off today (Original: ${target_price:.2f} -> Discounted: ${discounted_price:.2f})."
        )
    elif node == "action":
        instruction = (
            f"{ACTION_INSTRUCTIONS}\n\n"
            f"Ready to checkout with item:\n{format_product_context([target])}\n"
            f"Customer Selected Size: {profile.get('size') or 'Not specified'}.\n"
            f"Original price: ${target_price:.2f}. Discounted price (10% off with STYLIST10): ${discounted_price:.2f}.\n"
            f"Available sizes: {sizes_str}."
        )
    else:
        instruction = GREETING_INSTRUCTIONS

    if state.get("merchant_catalog") and node in ("action", "objection"):
        instruction = (
            "Help the shopper review product options on the merchant page. "
            "Only use the supplied facts. The merchant confirms price, promotions, fit and returns. "
            "Do not promise a discount, refund or cart change.\n" + format_product_context([target])
        )
    system_content = f"{STYLIST_CORE_SYSTEM_PROMPT}\n\n{instruction}"
    prompt_messages: List[BaseMessage] = [SystemMessage(content=system_content)]

    # Modern LangChain trim_messages: keeps SystemMessage, starts on human, token-bounded
    raw_history = list(state.get("messages", []))
    if raw_history:
        try:
            trimmed = trim_messages(
                prompt_messages + raw_history,
                max_tokens=1000,
                strategy="last",
                token_counter="approximate",
                start_on="human",
                include_system=True,
                allow_partial=False,
            )
            return trimmed
        except Exception as e:
            logger.debug("trim_messages fallback: %s", e)
            prompt_messages.extend(raw_history[-8:])
            return prompt_messages

    return prompt_messages


# ==================== NODE IMPLEMENTATIONS ====================

def greeting_node(state: SalesState) -> Dict[str, Any]:
    """Stage 1: Greeting & Approach."""
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""
    profile = update_customer_profile(state, last_msg) if last_msg else state.get("customer_profile", {}).copy()

    viewed = state.get("viewed_products", [])
    inventory = state.get("catalog_items", CATALOG_ITEMS)
    if not viewed:
        viewed = inventory[:1]

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
        "customer_profile": profile,
        "current_node": "greeting",
        "intent_stage": "EXPLORER",
        "quick_replies": quick_replies,
        "viewed_products": viewed,
    }


def discovery_node(state: SalesState) -> Dict[str, Any]:
    """Stage 2: Consultative Discovery."""
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""
    profile = update_customer_profile(state, last_msg)

    prompt_messages = build_node_prompt("discovery", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.6)

    # Contextual fallback replies based on customer text
    lower = last_msg.lower()
    if any(w in lower for w in ["wedding", "marriage", "ceremony"]):
        default_replies = ["Ceremony", "Evening Reception", "Both events"]
    elif any(w in lower for w in ["reception", "dinner"]):
        default_replies = ["What shoes work best?", "Check my size", "Apply 10% discount and let's buy"]
    elif any(w in lower for w in ["name", "biased", "based", "who are you", "who r u"]):
        default_replies = ["Shopping for an occasion", "Just browsing fresh styles", "Check size & fit"]
    else:
        default_replies = [
            "Ceremony & Reception",
            "Smart Casual Dinners",
            "Check my size",
        ]

    default_fallback = "I would love to help you find the perfect piece for your upcoming event."
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies, fallback_text=default_fallback)
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
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""
    profile = update_customer_profile(state, last_msg)
    occasion = profile.get("occasion")
    budget = profile.get("budget")

    curated = search_catalog(query=last_msg, occasion=occasion, max_price=budget, limit=3)
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
    default_fallback = f"Here is the {first_name}—a versatile staple tailored for your vibe."
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies, fallback_text=default_fallback)
    response = AIMessage(content=clean_text)

    return {
        "messages": [response],
        "customer_profile": profile,
        "recommended_products": curated,
        "current_node": "curation",
        "intent_stage": "EVALUATOR",
        "quick_replies": quick_replies,
    }


def validation_node(state: SalesState) -> Dict[str, Any]:
    """Stage 4: Fitting Room ('Hero' Validation Compliment)."""
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""
    profile = update_customer_profile(state, last_msg)

    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])

    prompt_messages = build_node_prompt("validation", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.65)

    target_name = target.get('name', target.get('title', 'Piece')).split()[-1]
    default_replies = [
        f"How's the sizing on the {target_name}?",
        "What shoes pair best?",
        "Apply 10% discount and let's buy",
    ]
    default_fallback = f"The {target_name} flatters your build with an effortless, sharp drape."
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies, fallback_text=default_fallback)
    response = AIMessage(content=clean_text)

    return {
        "messages": [response],
        "customer_profile": profile,
        "current_node": "validation",
        "intent_stage": "EVALUATOR",
        "quick_replies": quick_replies,
    }


def objection_node(state: SalesState) -> Dict[str, Any]:
    """Stage 5: Objection Handling & Social Proof."""
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""
    profile = update_customer_profile(state, last_msg)

    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])
    sizes_avail = product_sizes(target)

    prompt_messages = build_node_prompt("objection", state)
    raw_response = invoke_groq_resilient(prompt_messages, temperature=0.5)

    if sizes_avail and len(sizes_avail) >= 2:
        default_replies = [f"I wear {s}" for s in sizes_avail[:3]]
    else:
        default_replies = [
            "I'm between Medium and Large",
            "Apply the 10% discount and let's buy",
            "What sizes are in stock?",
        ]
    default_fallback = f"The {target.get('title') or target.get('name') or 'garment'} fits true to size with premium natural stretch and easy returns."
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies, fallback_text=default_fallback)
    response = AIMessage(content=clean_text)

    return {
        "messages": [response],
        "customer_profile": profile,
        "current_node": "objection",
        "intent_stage": "READY_TO_BUY" if profile.get("size") else "EVALUATOR",
        "quick_replies": quick_replies,
    }


def action_node(state: SalesState) -> Dict[str, Any]:
    """Stage 6: Guided Checkout (The Cashier)."""
    last_msg = state.get("messages", [])[-1].content if state.get("messages") else ""
    profile = update_customer_profile(state, last_msg)

    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])

    cart_intent = state.get("cart_intent", {}).copy()
    cart_intent["items"] = [target]
    cart_intent["applied_discount"] = "STYLIST10"
    cart_intent["ready_for_checkout"] = True
    if profile.get("size"):
        cart_intent["size"] = profile["size"]

    target_price = parse_price(target.get("price", 100.0))
    discounted_price = round(target_price * 0.9, 2)
    sizes_avail = product_sizes(target)
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
    default_fallback = f"Your 10% discount with STYLIST10 is applied to the {target_name} (${discounted_price:.2f}). Tap View & Buy to secure your size."
    clean_text, quick_replies = extract_pills_and_clean_message(raw_response.content, default_replies, fallback_text=default_fallback)
    response = AIMessage(content=clean_text)

    return {
        "messages": [response],
        "customer_profile": profile,
        "current_node": "action",
        "intent_stage": "READY_TO_BUY",
        "cart_intent": cart_intent,
        "action_payload": action_payload,
        "quick_replies": quick_replies,
    }


# ==================== STATE GRAPH RUNNER WITH CHECKPOINTER ====================

class SalesGraphRunner:
    """
    Thread-safe, checkpointer-enabled runner wrapping compiled StateGraph
    with automatic thread_id lifecycle management and transparent proxying.
    """
    def __init__(self, compiled_graph: Any, checkpointer: Optional[Any] = None):
        self._graph = compiled_graph
        self.checkpointer = checkpointer

    def _ensure_config(self, config: Optional[Dict[str, Any]] = None, thread_id: Optional[str] = None) -> Dict[str, Any]:
        cfg = dict(config or {})
        configurable = dict(cfg.get("configurable", {}))
        if "thread_id" not in configurable:
            configurable["thread_id"] = thread_id or "default-sales-session"
        cfg["configurable"] = configurable
        return cfg

    def invoke(self, input_val: Any, config: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        cfg = self._ensure_config(config)
        return self._graph.invoke(input_val, config=cfg, **kwargs)

    async def ainvoke(self, input_val: Any, config: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        cfg = self._ensure_config(config)
        return await self._graph.ainvoke(input_val, config=cfg, **kwargs)

    def astream(self, input_val: Any, config: Optional[Dict[str, Any]] = None, **kwargs):
        cfg = self._ensure_config(config)
        return self._graph.astream(input_val, config=cfg, **kwargs)

    def astream_events(self, input_val: Any, config: Optional[Dict[str, Any]] = None, **kwargs):
        cfg = self._ensure_config(config)
        return self._graph.astream_events(input_val, config=cfg, **kwargs)

    def get_state(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        cfg = self._ensure_config(config)
        return self._graph.get_state(config=cfg, **kwargs)

    def update_state(self, config: Optional[Dict[str, Any]], values: Dict[str, Any], **kwargs):
        cfg = self._ensure_config(config)
        return self._graph.update_state(config=cfg, values=values, **kwargs)

    def delete_thread(self, thread_id: str) -> None:
        """Clear thread checkpoints from checkpointer memory."""
        if self.checkpointer and hasattr(self.checkpointer, "delete_thread"):
            try:
                self.checkpointer.delete_thread(thread_id)
            except Exception as e:
                logger.debug("delete_thread error: %s", e)
        elif self.checkpointer and hasattr(self.checkpointer, "storage"):
            self.checkpointer.storage.pop(thread_id, None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)


# ==================== BUILD STATE MACHINE GRAPH ====================

def build_sales_graph(checkpointer: Optional[Any] = None) -> SalesGraphRunner:
    """Compile the LangGraph state machine with 6 sales nodes, ToolNode, and checkpointer persistence."""
    workflow = StateGraph(SalesState)

    workflow.add_node("greeting", greeting_node)
    workflow.add_node("discovery", discovery_node)
    workflow.add_node("curation", curation_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("objection", objection_node)
    workflow.add_node("action", action_node)
    workflow.add_node("tools", sales_tool_node)

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

    for node_name in ["greeting", "discovery", "curation", "validation", "objection", "action"]:
        workflow.add_conditional_edges(node_name, tools_condition, {"tools": "tools", END: END})

    workflow.add_edge("tools", END)

    cp = checkpointer if checkpointer is not None else memory_saver
    compiled = workflow.compile(checkpointer=cp)
    return SalesGraphRunner(compiled, checkpointer=cp)


sales_graph = build_sales_graph(checkpointer=memory_saver)
