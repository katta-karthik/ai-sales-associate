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
    invoke_groq_resilient,
    make_punchy,
    parse_price,
    sales_graph,
    stream_groq_resilient,
)
from backend.app.agent.persona import STYLIST_CORE_SYSTEM_PROMPT
from backend.app.agent.state import IntentStage, SalesState, init_sales_state
from backend.app.catalog.catalog import CATALOG_ITEMS, get_product, list_catalog, search_catalog

# In-memory session store: session_id -> SalesState
SESSIONS: Dict[str, SalesState] = {}

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


# ==================== PYDANTIC SCHEMAS ====================

class ChatRequest(BaseModel):
    message: Optional[str] = Field(default=None, description="User message or prompt")
    session_id: Optional[str] = Field(default=None, description="Session ID for thread memory")
    thread_id: Optional[str] = Field(default=None, description="Alias for session_id")
    product: Optional[Dict[str, Any]] = Field(default=None, description="Currently viewed product on PDP")
    product_context: Optional[Dict[str, Any]] = Field(default=None, description="Alias for product")
    event: Optional[str] = Field(default="chat", description="Event trigger (chat, hesitation, approach)")
    occasion: Optional[str] = Field(default=None, description="Optional occasion filter")


class ChatResponse(BaseModel):
    session_id: str
    node: str
    intent_stage: str
    message: str
    quick_replies: List[str]
    recommended_products: List[Dict[str, Any]]
    action_payload: Optional[Dict[str, Any]] = None
    show_card: bool = False


# ==================== HELPERS ====================

def is_valid_product(prod: Optional[Dict[str, Any]]) -> bool:
    """Validate whether dict represents an actual product with name/title or id."""
    if not prod or not isinstance(prod, dict):
        return False
    return bool(prod.get("id") or prod.get("name") or prod.get("title"))


def get_or_create_session(session_id: Optional[str], viewed_product: Optional[Dict[str, Any]] = None) -> tuple[str, SalesState]:
    """Retrieve existing session or instantiate a fresh SalesState."""
    sid = session_id or str(uuid.uuid4())
    valid_prod = viewed_product if is_valid_product(viewed_product) else None

    if sid not in SESSIONS:
        viewed_list = [valid_prod] if valid_prod else [CATALOG_ITEMS[0]]
        SESSIONS[sid] = init_sales_state(viewed_products=viewed_list)
    elif valid_prod:
        # Update currently viewed product if provided, keeping multi-turn history intact
        existing = SESSIONS[sid].get("viewed_products", [])
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
            SESSIONS[sid]["viewed_products"] = [valid_prod] + existing

    return sid, SESSIONS[sid]


def resolve_node_metadata(node: str, state: SalesState, user_text: str = "") -> tuple[str, List[str], List[Dict[str, Any]], Optional[Dict[str, Any]], bool]:
    """
    Extract quick replies, recommendations, action payload, and show_card flag.
    Returns: (stage, replies, recs, action, show_card)
    """
    curated = state.get("recommended_products", [])
    viewed = state.get("viewed_products", [])
    target = curated[0] if curated else (viewed[0] if viewed else CATALOG_ITEMS[0])
    text_lower = user_text.lower().strip()

    show_card = False
    target_price = parse_price(target.get("price", 100.0))
    discounted_price = round(target_price * 0.9, 2)
    target_name = target.get("title") or target.get("name") or "Featured Piece"
    sizes_avail = target.get("sizes") or (target.get("variants", {}).get("sizes") if isinstance(target.get("variants"), dict) else [])

    if node == "action" or any(w in text_lower for w in ["buy", "checkout", "grab it", "apply", "discount", "lock it in"]):
        stage = "READY_TO_BUY"
        show_card = True
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
            f"Complete checkout (${discounted_price:.2f})",
            "What shoes pair with this?",
            "What is your return policy?"
        ]
        recs = [target]

    elif any(w in text_lower for w in ["size", "sizing", "fit", "measure", "height", "weight"]) or (sizes_avail and any(s.lower() in text_lower for s in sizes_avail)):
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
                "Apply the 10% discount and let's buy"
            ]

    elif any(w in text_lower for w in ["pair", "match", "shoes", "pants", "look", "suit", "cocktail", "wedding", "marriage", "marraige", "reception", "dinner"]):
        stage = "EVALUATOR"
        show_card = False
        action = None
        recs = []
        if any(w in text_lower for w in ["wedding", "marriage", "marraige"]):
            replies = ["Ceremony", "Evening Reception", "Both events"]
        elif any(w in text_lower for w in ["reception", "ceremony"]):
            replies = ["What shoes work best?", "Check my size", "Apply 10% discount and let's buy"]
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
        show_card = True
        action = None
        recs = viewed[:1]
        replies = [
            "Check my size",
            "Will this suit an evening event?",
            "Are there any discounts today?"
        ]

    elif node == "curation":
        stage = "EVALUATOR"
        show_card = True
        action = None
        recs = curated if curated else (viewed[:2] if viewed else CATALOG_ITEMS[:2])
        replies = [
            "How does the sizing run?",
            "What fabric is this made of?",
            "Apply the 10% discount"
        ]

    else:
        stage = "EXPLORER"
        show_card = False
        action = None
        recs = []
        if any(w in text_lower for w in ["wedding", "marriage", "marraige"]):
            replies = ["Ceremony", "Evening Reception", "Both events"]
        elif any(w in text_lower for w in ["reception", "ceremony"]):
            replies = ["What shoes work best?", "Check my size", "Apply 10% discount and let's buy"]
        else:
            replies = [
                "Check my size",
                "How should I style this?",
                "Apply the 10% discount"
            ]

    return stage, replies, recs, action, show_card


# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "service": "AI Sales Associate Cloud Engine",
        "status": "online",
        "engine": "LangGraph + Groq LPU",
        "groq_model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
    sid, state = get_or_create_session(session_id_val, product_val)

    if req.message:
        state["messages"].append(HumanMessage(content=req.message))
    elif req.event == "approach":
        # Proactive approach trigger from hesitation detector
        state["messages"].append(HumanMessage(content="Hello! Can you help me find something or tell me about this piece?"))

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
            body = await request.json()
        except Exception:
            body = {}
        message = body.get("message")
        session_id = body.get("session_id") or body.get("thread_id")
        product = body.get("product") or body.get("product_context")
        event = body.get("event", "chat")
    else:
        params = request.query_params
        message = params.get("message")
        session_id = params.get("session_id") or params.get("thread_id")
        product_id = params.get("product_id")
        product = get_product(product_id) if product_id else None
        event = params.get("event", "chat")

    sid, state = get_or_create_session(session_id, product)

    if message:
        state["messages"].append(HumanMessage(content=message))
    elif event == "hesitation":
        state["messages"].append(HumanMessage(content="I'm browsing this item but second-guessing if it will look good on me."))
    elif event in ("approach", "open"):
        state["messages"].append(HumanMessage(content="Hey! What makes this piece special?"))

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

        # 2. Stream tokens from Groq
        full_tokens = []
        in_pills = False
        try:
            async for chunk in stream_groq_resilient(prompt_msgs):
                content = chunk.content
                if content:
                    full_tokens.append(content)
                    current_str = "".join(full_tokens)

                    # Once <pills tag starts, do not stream pill syntax into the chat bubble
                    if "<pills" in current_str:
                        in_pills = True

                    if not in_pills:
                        token_event = {"type": "token", "content": content}
                        yield f"event: token\ndata: {json.dumps(token_event)}\n\n"

                    # If </pills> tag is closed, stream is complete
                    if "</pills>" in current_str:
                        break
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
    """Reset session history."""
    sid = req.get("session_id")
    if sid and sid in SESSIONS:
        del SESSIONS[sid]
    return {"status": "reset", "session_id": sid}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
