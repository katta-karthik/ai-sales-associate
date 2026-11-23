"""AI Sales Associate - FastAPI Application with Groq LPU & LangGraph Cloud Engine."""
import json
import logging
import os
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Configure LangSmith Tracing
LANGSMITH_ENABLED = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true" or os.getenv("LANGSMITH_TRACING", "").lower() == "true"
if LANGSMITH_ENABLED:
    os.environ.setdefault("LANGCHAIN_PROJECT", "ai-sales-associate")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sales_engine.main")

from langchain_core.messages import AIMessage, HumanMessage
from langchain_groq import ChatGroq

from backend.app.agent.graph import (
    build_node_prompt,
    classify_intent,
    extract_pills_and_clean_message,
    format_product_context,
    get_llm,
    has_word,
    product_sizes,
    invoke_groq_resilient,
    make_punchy,
    parse_price,
    sales_graph,
    sales_tools,
    sales_tool_node,
    stream_groq_resilient,
    update_customer_profile,
)
from backend.app.agent.persona import STYLIST_CORE_SYSTEM_PROMPT
from backend.app.agent.state import IntentStage, SalesState, init_sales_state
from backend.app.catalog.catalog import CATALOG_ITEMS, get_product, list_catalog, search_catalog

# In-memory session store: session_id -> SalesState
SESSIONS: Dict[str, SalesState] = {}

# Cross-session customer profile store: customer_id / shopper_uuid -> persistent customer profile
CUSTOMER_PROFILES: Dict[str, Dict[str, Any]] = {}


def save_customer_profile(state: SalesState, customer_id: Optional[str] = None, shopper_uuid: Optional[str] = None) -> None:
    """Save customer profile updates into cross-session store keyed by customer_id and shopper_uuid."""
    profile = state.get("customer_profile", {})
    cid = customer_id or state.get("customer_id") or profile.get("customer_id")
    suid = shopper_uuid or state.get("shopper_uuid") or profile.get("shopper_uuid")
    if cid:
        CUSTOMER_PROFILES.setdefault(str(cid), {}).update(profile)
    if suid:
        CUSTOMER_PROFILES.setdefault(str(suid), {}).update(profile)

app = FastAPI(
    title="AI Sales Associate Cloud Engine",
    description="Groq LPU-powered LangGraph autonomous retail stylist with sub-second streaming inference.",
    version="1.0.0",
)

# Enable CORS for storefront widgets
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the client-side Widget SDK directly for 1-line store integration
WIDGET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "widget")
if os.path.exists(WIDGET_DIR):
    app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")


# ==================== PYDANTIC SCHEMAS ====================

class ChatRequest(BaseModel):
    message: Optional[str] = Field(default=None, description="User message or prompt")
    session_id: Optional[str] = Field(default=None, description="Session ID for thread memory")
    thread_id: Optional[str] = Field(default=None, description="Alias for session_id")
    product: Optional[Dict[str, Any]] = Field(default=None, description="Currently viewed product on PDP")
    product_context: Optional[Dict[str, Any]] = Field(default=None, description="Alias for product")
    event: Optional[str] = Field(default="chat", description="Event trigger (chat, hesitation, approach)")
    catalog: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=200)
    occasion: Optional[str] = Field(default=None, description="Optional occasion filter")
    customer_id: Optional[str] = Field(default=None, description="Merchant customer ID")
    shopper_uuid: Optional[str] = Field(default=None, description="Persistent cross-session shopper UUID")
    store_name: Optional[str] = Field(default=None, description="Host store name / dynamic brand")
    store_domain: Optional[str] = Field(default=None, description="Store website domain")
    currency: Optional[str] = Field(default=None, description="Store currency symbol or code")
    brand_tone: Optional[str] = Field(default=None, description="Brand tone / persona style")
    viewed_products: Optional[List[Dict[str, Any]]] = Field(default=None, description="Client multi-page browsing history")
    hesitation_trigger: Optional[Dict[str, Any]] = Field(default=None, description="Hesitation trigger payload")
    promo_code: Optional[str] = Field(default=None, description="Merchant-authorized promotional code")
    allow_discounts: Optional[bool] = Field(default=None, description="Whether merchant permits promotional discounts")


class ChatResponse(BaseModel):
    session_id: str
    node: str
    intent_stage: str
    message: str
    quick_replies: List[str]
    recommended_products: List[Dict[str, Any]]
    action_payload: Optional[Dict[str, Any]] = None
    show_card: bool = False


class ConversionTelemetryRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Session ID for the converted journey")
    thread_id: Optional[str] = Field(default=None, description="Alias for session_id")
    customer_id: Optional[str] = Field(default=None, description="Merchant customer ID")
    shopper_uuid: Optional[str] = Field(default=None, description="Persistent cross-session shopper UUID")
    purchased_items: List[Dict[str, Any]] = Field(default_factory=list, description="List of purchased items")
    order_total: Optional[float] = Field(default=0.0, description="Order total monetary value")
    currency: Optional[str] = Field(default="$", description="Currency symbol or ISO code")
    order_id: Optional[str] = Field(default=None, description="Host store order or transaction ID")


# ==================== HELPERS ====================

def is_valid_product(prod: Optional[Dict[str, Any]]) -> bool:
    """Validate whether dict represents an actual product with name/title or id."""
    if not prod or not isinstance(prod, dict):
        return False
    return bool(prod.get("id") or prod.get("name") or prod.get("title"))


def get_or_create_session(
    session_id: Optional[str],
    viewed_product: Optional[Dict[str, Any]] = None,
    catalog: Optional[List[Dict[str, Any]]] = None,
    store_name: Optional[str] = None,
    store_domain: Optional[str] = None,
    currency: Optional[str] = None,
    brand_tone: Optional[str] = None,
    shopper_uuid: Optional[str] = None,
    customer_id: Optional[str] = None,
    client_viewed_products: Optional[List[Dict[str, Any]]] = None,
    hesitation_trigger: Optional[Dict[str, Any]] = None,
    promo_code: Optional[str] = None,
    allow_discounts: Optional[bool] = None,
) -> tuple[str, SalesState]:
    """Retrieve existing session or instantiate a fresh SalesState with MemorySaver checkpointer sync."""
    sid = session_id or str(uuid.uuid4())
    valid_prod = viewed_product if is_valid_product(viewed_product) else None

    # Identify if host environment is merchant store vs internal seed demo store
    is_merchant = (
        catalog is not None or
        (store_name and store_name.strip().lower() not in ("karthik & co.", "karthik & co", "karthik & co. modern apparel", "demo store", "our store")) or
        (store_domain and "localhost" not in store_domain and "127.0.0.1" not in store_domain)
    )

    if sid not in SESSIONS:
        # Check if checkpointer already has checkpoint for this thread_id
        try:
            checkpoint_state = sales_graph.get_state({"configurable": {"thread_id": sid}})
            if checkpoint_state and checkpoint_state.values:
                SESSIONS[sid] = dict(checkpoint_state.values)
        except Exception:
            pass

    if sid not in SESSIONS:
        if valid_prod:
            viewed_list = [valid_prod]
        elif client_viewed_products:
            viewed_list = [p for p in client_viewed_products if is_valid_product(p)]
        elif is_merchant:
            viewed_list = []
        else:
            viewed_list = [CATALOG_ITEMS[0]]

        clean_catalog = [p for p in catalog if isinstance(p.get("title") or p.get("name"), str) and p.get("in_stock") is not False] if catalog is not None else ([] if is_merchant else None)

        # Merge cross-session customer profile if returning customer
        lookup_id = customer_id or shopper_uuid
        persistent_profile = None
        if lookup_id:
            saved = CUSTOMER_PROFILES.get(str(lookup_id))
            if saved:
                persistent_profile = dict(saved)

        SESSIONS[sid] = init_sales_state(
            viewed_products=viewed_list,
            customer_profile=persistent_profile,
            store_name=store_name or "Our Store",
            store_domain=store_domain,
            currency=currency or "$",
            brand_tone=brand_tone,
            shopper_uuid=shopper_uuid,
            customer_id=customer_id,
            hesitation_trigger=hesitation_trigger,
            merchant_catalog=is_merchant,
            catalog_items=clean_catalog,
            promo_code=promo_code,
            allow_discounts=allow_discounts,
        )
    else:
        # Existing session: update store identity and shopper context if provided
        if is_merchant:
            SESSIONS[sid]["merchant_catalog"] = True
            if "catalog_items" not in SESSIONS[sid]:
                SESSIONS[sid]["catalog_items"] = []
        if promo_code is not None:
            SESSIONS[sid]["promo_code"] = promo_code
        if allow_discounts is not None:
            SESSIONS[sid]["allow_discounts"] = allow_discounts
        if store_name:
            SESSIONS[sid]["store_name"] = store_name
        if store_domain:
            SESSIONS[sid]["store_domain"] = store_domain
        if currency:
            SESSIONS[sid]["currency"] = currency
        if brand_tone:
            SESSIONS[sid]["brand_tone"] = brand_tone
        if customer_id:
            SESSIONS[sid]["customer_id"] = customer_id
            SESSIONS[sid].setdefault("customer_profile", {})["customer_id"] = customer_id
        if shopper_uuid:
            SESSIONS[sid]["shopper_uuid"] = shopper_uuid
            SESSIONS[sid].setdefault("customer_profile", {})["shopper_uuid"] = shopper_uuid
        if hesitation_trigger:
            SESSIONS[sid]["hesitation_trigger"] = hesitation_trigger
            if isinstance(hesitation_trigger, dict):
                reason = hesitation_trigger.get("type") or hesitation_trigger.get("reason") or hesitation_trigger.get("suggestedNudge")
                if reason:
                    SESSIONS[sid].setdefault("customer_profile", {})["hesitation_reason"] = reason

        # Merge viewed products
        existing = SESSIONS[sid].get("viewed_products", [])
        if valid_prod:
            prod_id = valid_prod.get("id") or valid_prod.get("title") or valid_prod.get("name")
            match_idx = -1
            for idx, p in enumerate(existing):
                p_id = p.get("id") or p.get("title") or p.get("name")
                if p_id and p_id == prod_id:
                    match_idx = idx
                    break
            if match_idx >= 0:
                existing[match_idx] = valid_prod
                if match_idx > 0:
                    existing.insert(0, existing.pop(match_idx))
            else:
                existing = [valid_prod] + existing

        if client_viewed_products:
            for cp in client_viewed_products:
                if not is_valid_product(cp):
                    continue
                cp_id = cp.get("id") or cp.get("title") or cp.get("name")
                if not any((p.get("id") or p.get("title") or p.get("name")) == cp_id for p in existing):
                    existing.append(cp)

        SESSIONS[sid]["viewed_products"] = existing[:10]

    if catalog is not None:
        SESSIONS[sid]["merchant_catalog"] = True
        SESSIONS[sid]["catalog_items"] = [p for p in catalog if isinstance(p.get("title") or p.get("name"), str) and p.get("in_stock") is not False]
        if valid_prod:
            SESSIONS[sid]["recommended_products"] = []
    return sid, SESSIONS[sid]


def discover_products(req: ChatRequest, sid: str, state: SalesState) -> Optional[ChatResponse]:
    """Handle explicit collection searches against the merchant's published products."""
    text = (req.message or "").lower()
    if req.catalog is None or not re.search(r"\b(show|find|browse|browsing|recommend|under|below|up to|alternatives)\b", text):
        return None

    budget = re.search(r"\b(under|below|up to)\s*\$?([\d,]+(?:\.\d+)?)", text)
    query = text[:budget.start()] + text[budget.end():] if budget else text
    stop = {"show", "find", "browse", "browsing", "recommend", "please", "some", "for", "the",
            "collection", "something", "under", "below", "alternatives", "fresh", "styles", "just", "with",
            "and", "items", "pieces", "products", "clothes", "about", "less", "want", "would", "like", "looking", "can", "you", "that", "cost", "than", "any", "options"}
    terms = {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", query) if w not in stop}
    matches = []
    for item in req.catalog:
        if not isinstance(item.get("title") or item.get("name"), str) or item.get("in_stock") is False:
            continue
        if budget:
            try:
                price = float(str(item["price"]).replace("$", "").replace(",", ""))
                maximum = float(budget[2].replace(",", ""))
            except (KeyError, ValueError):
                continue
            if price > maximum or (price == maximum and budget[1] != "up to"):
                continue
        words = {w.rstrip("s") for w in re.findall(r"[a-z]+", " ".join(
            str(item.get(field, "")) for field in ("title", "name", "description", "category", "material", "colors", "occasion")
        ).lower())}
        if terms <= words:
            matches.append(item)
    picks = matches[:3]
    message = ("Here are the pieces that match: " + ", ".join(p.get("title") or p.get("name") or str(p["id"]) for p in picks) + "."
               if picks else "I couldn’t find a piece matching that request. Try a different material or a higher budget.")
    state["current_node"] = "curation"
    state["intent_stage"] = "EVALUATOR"
    state["recommended_products"] = picks
    state["action_payload"] = None
    state["quick_replies"] = []
    state["messages"].append(AIMessage(content=message))
    return ChatResponse(session_id=sid, node="curation", intent_stage="EVALUATOR", message=message,
                        quick_replies=[], recommended_products=picks, show_card=bool(picks))


def resolve_node_metadata(node: str, state: SalesState, user_text: str = "") -> tuple[str, List[str], List[Dict[str, Any]], Optional[Dict[str, Any]], bool]:
    """
    Extract quick replies, recommendations, action payload, and show_card flag.
    Returns: (stage, replies, recs, action, show_card)
    """
    is_merchant = state.get("merchant_catalog") or not state.get("allow_discounts", True)
    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    available = curated or viewed or (state.get("catalog_items") or [] if state.get("merchant_catalog") else state.get("catalog_items", CATALOG_ITEMS))
    if available is None:
        available = []
    target = available[0] if available else {}
    text_lower = user_text.lower().strip()

    show_card = False
    target_price = parse_price(target.get("price", 100.0))
    discounted_price = round(target_price * 0.9, 2)
    target_name = target.get("title") or target.get("name") or "Featured Piece"
    sizes_avail = product_sizes(target)
    curr = target.get("currency") or state.get("currency") or "$"

    if node == "action" or any(w in text_lower for w in ["buy", "checkout", "grab it", "apply", "discount", "lock it in"]):
        if not target:
            return "EXPLORER", ["Browse products"], [], None, False
        stage = "READY_TO_BUY"
        show_card = True
        if is_merchant:
            return stage, ["Review product options", "Check sizing"], [target], {
                "type": "view_product", "product_name": target_name, "url": target.get("url"), "price": target_price, "currency": curr
            }, True
        action = {
            "type": "checkout",
            "product_id": target.get("id"),
            "product_name": target_name,
            "original_price": target_price,
            "discounted_price": discounted_price,
            "discount_code": "STYLIST10",
            "checkout_url": f"/checkout?item={target.get('id')}&discount=STYLIST10",
            "sizes_available": sizes_avail,
        }
        replies = [
            f"Complete checkout ({curr}{discounted_price:.2f})",
            "What shoes pair with this?",
            "What is your return policy?"
        ]
        recs = [target]

    elif node == "objection" or has_word(text_lower, ["size", "sizes", "sizing", "fit", "fits", "measure", "measurements", "height", "weight", "m", "l", "s", "xl", "xs"]) or (sizes_avail and has_word(text_lower, [str(size).lower() for size in sizes_avail])):
        stage = "EVALUATOR"
        show_card = False
        action = None
        recs = []
        if sizes_avail and len(sizes_avail) >= 2:
            replies = [f"I wear {s}" for s in sizes_avail[:3]]
        else:
            replies = [
                "I'm between Medium and Large",
                "Does this fabric have stretch?",
                "Review product options" if is_merchant else "Apply the 10% discount and let's buy"
            ]

    elif any(w in text_lower for w in ["pair", "match", "shoes", "pants", "look", "suit", "cocktail", "wedding", "marriage", "marraige", "ceremony", "reception", "dinner"]):
        stage = "EVALUATOR"
        show_card = False
        action = None
        recs = []
        if any(w in text_lower for w in ["wedding", "marriage", "marraige"]):
            replies = ["Ceremony", "Evening Reception", "Both events"]
        elif any(w in text_lower for w in ["reception", "ceremony"]):
            replies = ["What shoes work best?", "Check my size", "Review product options" if is_merchant else "Apply 10% discount and let's buy"]
        else:
            replies = [
                "What shoes work best?",
                "Can I dress this down casually?",
                "I love it, let's grab it!"
            ]

    elif any(w in text_lower for w in ["name", "biased", "based", "who are you", "who r u"]):
        stage = "EXPLORER"
        show_card = False
        action = None
        recs = []
        replies = [
            "Shopping for an occasion",
            "Just browsing fresh styles",
            "Check size & fit"
        ]

    elif node == "greeting":
        stage = "EXPLORER"
        show_card = bool(viewed)
        action = None
        recs = viewed[:1] if viewed else []
        replies = [
            "Check my size",
            "Will this suit an evening event?" if viewed else "Shopping for an occasion",
            "Review product options" if is_merchant else "Are there any discounts today?"
        ]

    elif node == "curation":
        stage = "EVALUATOR"
        show_card = True
        action = None
        recs = available[:2]
        replies = [
            "How does the sizing run?",
            "What fabric is this made of?",
            "Check sizing guide" if is_merchant else "Apply the 10% discount"
        ]

    else:
        stage = "EXPLORER"
        show_card = False
        action = None
        recs = []
        if any(w in text_lower for w in ["wedding", "marriage", "marraige"]):
            replies = ["Ceremony", "Evening Reception", "Both events"]
        elif any(w in text_lower for w in ["reception", "ceremony"]):
            replies = ["What shoes work best?", "Check my size", "Review product options" if is_merchant else "Apply 10% discount and let's buy"]
        else:
            replies = [
                "Check my size",
                "How should I style this?",
                "Review product options" if is_merchant else "Apply the 10% discount"
            ]

    return stage, replies, recs, action, show_card


# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "service": "AI Sales Associate Cloud Engine",
        "status": "online",
        "engine": "LangGraph + Groq LPU",
        "groq_model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "langsmith_tracing": LANGSMITH_ENABLED,
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "active_sessions": len(SESSIONS),
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "langsmith_tracing": LANGSMITH_ENABLED,
        "catalog_size": len(CATALOG_ITEMS),
    }


@app.get("/api/catalog")
def get_catalog_items(
    category: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    max_price: Optional[float] = Query(None),
    occasion: Optional[str] = Query(None),
):
    """Retrieve catalog products with optional filtering."""
    if any([category, query, max_price, occasion]):
        return search_catalog(query=query, category=category, max_price=max_price, occasion=occasion, limit=20)
    return list_catalog()


@app.get("/api/catalog/{product_id}")
def get_catalog_product(product_id: str):
    """Get single product details."""
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found.")
    return product


@app.post("/api/chat", response_model=ChatResponse)
def chat_sync(req: ChatRequest):
    """Non-streaming synchronous chat endpoint for full response roundtrip."""
    session_id_val = req.session_id or req.thread_id
    product_val = req.product or req.product_context
    sid, state = get_or_create_session(
        session_id=session_id_val,
        viewed_product=product_val,
        catalog=req.catalog,
        store_name=req.store_name,
        store_domain=req.store_domain,
        currency=req.currency,
        brand_tone=req.brand_tone,
        shopper_uuid=req.shopper_uuid,
        customer_id=req.customer_id,
        client_viewed_products=req.viewed_products,
        hesitation_trigger=req.hesitation_trigger,
        promo_code=req.promo_code,
        allow_discounts=req.allow_discounts,
    )

    if req.message:
        update_customer_profile(state, req.message)
        state["messages"].append(HumanMessage(content=req.message))
    elif req.event == "approach":
        # Proactive approach trigger from hesitation detector
        state["messages"].append(HumanMessage(content="Hello! Can you help me find something or tell me about this piece?"))

    result = discover_products(req, sid, state)
    if result:
        return result

    # Execute graph node
    node = classify_intent(state)
    state["current_node"] = node
    stage, replies, recs, action, show_card = resolve_node_metadata(node, state, user_text=req.message or "")
    state["intent_stage"] = stage
    state["quick_replies"] = replies
    state["recommended_products"] = recs
    state["action_payload"] = action

    # Run LangGraph step
    prompt_msgs = build_node_prompt(node, state)
    ai_resp = invoke_groq_resilient(prompt_msgs)

    # Extract dynamic pills and clean message
    clean_message, dynamic_replies = extract_pills_and_clean_message(ai_resp.content, replies)
    clean_ai_message = AIMessage(content=clean_message)
    state["messages"].append(clean_ai_message)
    state["quick_replies"] = dynamic_replies
    SESSIONS[sid] = state
    save_customer_profile(state, req.customer_id, req.shopper_uuid)

    try:
        sales_graph.update_state({"configurable": {"thread_id": sid}}, dict(state))
    except Exception as e:
        logger.debug("checkpointer update: %s", e)

    return ChatResponse(
        session_id=sid,
        node=node,
        intent_stage=stage,
        message=clean_message,
        quick_replies=dynamic_replies,
        recommended_products=recs,
        action_payload=action,
        show_card=show_card,
    )


@app.post("/api/telemetry/conversion")
def record_conversion_telemetry(req: ConversionTelemetryRequest):
    """
    Log conversion telemetry and record customer conversion signals in customer_profile
    and state graph checkpointer memory.
    """
    sid = req.session_id or req.thread_id or str(uuid.uuid4())
    _, state = get_or_create_session(sid, customer_id=req.customer_id, shopper_uuid=req.shopper_uuid)

    profile = state.get("customer_profile", {}).copy()
    profile["has_converted"] = True
    profile["conversion_count"] = profile.get("conversion_count", 0) + 1
    profile["last_order_total"] = req.order_total
    profile["last_order_id"] = req.order_id
    profile["last_purchased_items"] = req.purchased_items
    if req.customer_id:
        profile["customer_id"] = req.customer_id
        state["customer_id"] = req.customer_id
    if req.shopper_uuid:
        profile["shopper_uuid"] = req.shopper_uuid
        state["shopper_uuid"] = req.shopper_uuid

    cart_intent = state.get("cart_intent", {}).copy()
    cart_intent["purchased"] = True
    cart_intent["order_id"] = req.order_id
    cart_intent["order_total"] = req.order_total

    state["customer_profile"] = profile
    state["cart_intent"] = cart_intent
    state["intent_stage"] = "READY_TO_BUY"
    SESSIONS[sid] = state
    save_customer_profile(state, req.customer_id, req.shopper_uuid)

    try:
        sales_graph.update_state({"configurable": {"thread_id": sid}}, dict(state))
    except Exception as e:
        logger.debug("conversion telemetry checkpointer update: %s", e)

    logger.info(
        "Conversion telemetry logged: session=%s customer=%s total=%s items_count=%d",
        sid, req.customer_id or req.shopper_uuid, req.order_total, len(req.purchased_items)
    )

    return {
        "status": "recorded",
        "session_id": sid,
        "customer_id": req.customer_id,
        "shopper_uuid": req.shopper_uuid,
        "order_total": req.order_total,
        "recorded_items_count": len(req.purchased_items),
    }


@app.post("/api/chat/stream")
@app.get("/api/chat/stream")
async def chat_stream(request: Request):
    """
    SSE Streaming endpoint for sub-second, token-by-token Groq LPU inference.
    Supports both POST with JSON body and GET with query parameters.
    """
    # Parse parameters from either POST body or GET query
    if request.method == "POST":
        try:
            req = ChatRequest.model_validate(await request.json())
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid chat request")
        message = req.message
        session_id = req.session_id or req.thread_id
        product = req.product or req.product_context
        event = req.event
        catalog = req.catalog
        store_name = req.store_name
        store_domain = req.store_domain
        currency = req.currency
        brand_tone = req.brand_tone
        shopper_uuid = req.shopper_uuid
        customer_id = req.customer_id
        viewed_products = req.viewed_products
        hesitation_trigger = req.hesitation_trigger
        promo_code = req.promo_code
        allow_discounts = req.allow_discounts
    else:
        req = None
        params = request.query_params
        message = params.get("message")
        session_id = params.get("session_id") or params.get("thread_id")
        product_id = params.get("product_id")
        product = get_product(product_id) if product_id else None
        event = params.get("event", "chat")
        catalog = None
        store_name = params.get("store_name")
        store_domain = params.get("store_domain")
        currency = params.get("currency")
        brand_tone = params.get("brand_tone")
        shopper_uuid = params.get("shopper_uuid")
        customer_id = params.get("customer_id")
        viewed_products = None
        hesitation_trigger = None
        promo_code = params.get("promo_code")
        raw_allow = params.get("allow_discounts")
        allow_discounts = (raw_allow.lower() == "true") if raw_allow else None

    sid, state = get_or_create_session(
        session_id=session_id,
        viewed_product=product,
        catalog=catalog,
        store_name=store_name,
        store_domain=store_domain,
        currency=currency,
        brand_tone=brand_tone,
        shopper_uuid=shopper_uuid,
        customer_id=customer_id,
        client_viewed_products=viewed_products,
        hesitation_trigger=hesitation_trigger,
        promo_code=promo_code,
        allow_discounts=allow_discounts,
    )

    if message:
        update_customer_profile(state, message)
        state["messages"].append(HumanMessage(content=message))
    elif event == "hesitation":
        state["messages"].append(HumanMessage(content="I'm browsing this item but second-guessing if it will look good on me."))
    elif event in ("approach", "open"):
        state["messages"].append(HumanMessage(content="Hey! What makes this piece special?"))

    result = discover_products(req, sid, state) if request.method == "POST" else None
    if result:
        def discovery_events():
            for kind, data in (
                ("start", {"session_id": sid, "node": result.node, "intent_stage": result.intent_stage, "show_card": result.show_card}),
                ("token", {"content": result.message}),
                ("done", result.model_dump()),
            ):
                yield f"event: {kind}\ndata: {json.dumps(dict(type=kind, **data))}\n\n"
        return StreamingResponse(discovery_events(), media_type="text/event-stream")

    node = classify_intent(state)
    state["current_node"] = node
    stage, replies, recs, action, show_card = resolve_node_metadata(node, state, user_text=message or "")
    state["intent_stage"] = stage
    state["quick_replies"] = replies
    state["recommended_products"] = recs
    state["action_payload"] = action

    prompt_msgs = build_node_prompt(node, state)

    async def event_generator() -> AsyncGenerator[str, None]:
        # 1. Send initial metadata event
        meta_event = {
            "type": "start",
            "session_id": sid,
            "node": node,
            "intent_stage": stage,
            "show_card": show_card,
        }
        yield f"event: start\ndata: {json.dumps(meta_event)}\n\n"

        # 2. Stream tokens from Groq with tag-prefix buffering to prevent <pills> leaks
        full_tokens = []
        stream_buf = ""
        in_pills = False
        tag = "<pills"
        try:
            async for chunk in stream_groq_resilient(prompt_msgs):
                content = chunk.content
                if content:
                    full_tokens.append(content)
                    if in_pills:
                        stream_buf += content
                        if "</pills>" in stream_buf:
                            break
                        continue

                    stream_buf += content
                    idx = stream_buf.find(tag)
                    if idx != -1:
                        safe = stream_buf[:idx]
                        if safe:
                            token_event = {"type": "token", "content": safe}
                            yield f"event: token\ndata: {json.dumps(token_event)}\n\n"
                        in_pills = True
                        continue

                    # Check for partial prefix of tag at the end of stream_buf
                    matched_prefix_len = 0
                    for i in range(len(tag) - 1, 0, -1):
                        if stream_buf.endswith(tag[:i]):
                            matched_prefix_len = i
                            break
                    if matched_prefix_len > 0:
                        safe = stream_buf[:-matched_prefix_len]
                        if safe:
                            token_event = {"type": "token", "content": safe}
                            yield f"event: token\ndata: {json.dumps(token_event)}\n\n"
                        stream_buf = stream_buf[-matched_prefix_len:]
                    else:
                        token_event = {"type": "token", "content": stream_buf}
                        yield f"event: token\ndata: {json.dumps(token_event)}\n\n"
                        stream_buf = ""

            if not in_pills and stream_buf:
                token_event = {"type": "token", "content": stream_buf}
                yield f"event: token\ndata: {json.dumps(token_event)}\n\n"
        except Exception as e:
            logger.error("Error during streaming: %s", e)
            error_event = {"type": "error", "error": str(e)}
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
            return

        # 3. Finalize state and send 'done' event with actionable payloads & dynamic quick replies
        raw_text = "".join(full_tokens)
        clean_text, dynamic_replies = extract_pills_and_clean_message(raw_text, replies)
        clean_ai_msg = AIMessage(content=clean_text)
        state["messages"].append(clean_ai_msg)
        state["quick_replies"] = dynamic_replies
        SESSIONS[sid] = state
        save_customer_profile(state, customer_id, shopper_uuid)

        try:
            sales_graph.update_state({"configurable": {"thread_id": sid}}, dict(state))
        except Exception as e:
            logger.debug("checkpointer update: %s", e)

        done_event = {
            "type": "done",
            "session_id": sid,
            "node": node,
            "intent_stage": stage,
            "message": clean_text,
            "quick_replies": dynamic_replies,
            "recommended_products": recs,
            "action_payload": action,
            "show_card": show_card,
        }
        yield f"event: done\ndata: {json.dumps(done_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.post("/api/reset")
def reset_session(req: Dict[str, str]):
    """Reset session history completely across both SESSIONS store and checkpointer."""
    sid = req.get("session_id")
    if sid:
        if sid in SESSIONS:
            del SESSIONS[sid]
        try:
            sales_graph.delete_thread(sid)
        except Exception as e:
            logger.debug("sales_graph delete_thread: %s", e)
    return {"status": "reset", "session_id": sid}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
