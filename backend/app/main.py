"""AI Sales Associate - FastAPI Application with Groq LPU & LangGraph Cloud Engine."""
import json
import logging
import os
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
    format_product_context,
    get_llm,
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
    product: Optional[Dict[str, Any]] = Field(default=None, description="Currently viewed product on PDP")
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

def get_or_create_session(session_id: Optional[str], viewed_product: Optional[Dict[str, Any]] = None) -> tuple[str, SalesState]:
    """Retrieve existing session or instantiate a fresh SalesState."""
    sid = session_id or str(uuid.uuid4())
    if sid not in SESSIONS:
        viewed_list = [viewed_product] if viewed_product else [CATALOG_ITEMS[0]]
        SESSIONS[sid] = init_sales_state(viewed_products=viewed_list)
    elif viewed_product:
        # Update currently viewed product if provided
        existing = SESSIONS[sid].get("viewed_products", [])
        if not any(p.get("id") == viewed_product.get("id") for p in existing):
            SESSIONS[sid]["viewed_products"] = [viewed_product] + existing
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

    if node == "action" or any(w in text_lower for w in ["buy", "checkout", "grab it", "apply", "discount", "lock it in"]):
        stage = "READY_TO_BUY"
        show_card = True
        discounted_price = round(target.get("price", 100.0) * 0.9, 2)
        action = {
            "type": "checkout",
            "product_id": target.get("id"),
            "product_name": target.get("name"),
            "original_price": target.get("price"),
            "discounted_price": discounted_price,
            "discount_code": "STYLIST10",
            "checkout_url": f"/checkout?item={target.get('id')}&discount=STYLIST10",
            "sizes_available": target.get("sizes", []),
        }
        replies = [
            "Complete checkout with 10% off",
            "What shoes pair with this?",
            "What is your return policy?"
        ]
        recs = [target]

    elif any(w in text_lower for w in ["size", "sizing", "fit", "small", "large", "measure"]):
        stage = "EVALUATOR"
        show_card = False
        action = None
        recs = []
        replies = [
            "I'm between Medium and Large",
            "Does this fabric have stretch?",
            "Apply the 10% discount and let's buy"
        ]

    elif any(w in text_lower for w in ["pair", "match", "shoes", "pants", "look", "suit", "cocktail", "wedding", "dinner"]):
        stage = "EVALUATOR"
        show_card = False
        action = None
        recs = []
        replies = [
            "What shoes work best?",
            "Can I dress this down casually?",
            "I love it, let's grab it!"
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
        recs = curated if curated else CATALOG_ITEMS[:2]
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
    sid, state = get_or_create_session(req.session_id, req.product)

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
    from backend.app.agent.graph import invoke_groq_resilient
    ai_resp = invoke_groq_resilient(prompt_msgs)

    state["messages"].append(ai_resp)
    SESSIONS[sid] = state

    return ChatResponse(
        session_id=sid,
        node=node,
        intent_stage=stage,
        message=ai_resp.content,
        quick_replies=replies,
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
        session_id = body.get("session_id")
        product = body.get("product")
        event = body.get("event", "chat")
    else:
        params = request.query_params
        message = params.get("message")
        session_id = params.get("session_id")
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
        try:
            async for chunk in stream_groq_resilient(prompt_msgs):
                content = chunk.content
                if content:
                    full_tokens.append(content)
                    token_event = {"type": "token", "content": content}
                    yield f"event: token\ndata: {json.dumps(token_event)}\n\n"
        except Exception as e:
            logger.error("Error during streaming: %s", e)
            error_event = {"type": "error", "error": str(e)}
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
            return

        # 3. Finalize state and send 'done' event with actionable payloads
        full_text = "".join(full_tokens)
        state["messages"].append(AIMessage(content=full_text))
        SESSIONS[sid] = state

        done_event = {
            "type": "done",
            "session_id": sid,
            "node": node,
            "intent_stage": stage,
            "message": full_text,
            "quick_replies": replies,
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
