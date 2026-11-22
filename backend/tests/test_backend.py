"""Comprehensive end-to-end tests for AI Sales Associate Backend."""
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.catalog.catalog import CATALOG_ITEMS, get_product, list_catalog, search_catalog
from backend.app.agent.state import init_sales_state
from backend.app.agent.graph import (
    build_sales_graph,
    classify_intent,
    sales_graph,
    invoke_groq_resilient,
)
from backend.app.main import app
from langchain_core.messages import HumanMessage


client = TestClient(app)


def test_catalog_retrieval():
    """Verify catalog has apparel items and search tools work."""
    items = list_catalog()
    assert len(items) >= 9
    categories = {i["category"] for i in items}
    assert "shirts" in categories
    assert "pants" in categories
    assert "jackets" in categories

    shirt = get_product("shirt-01")
    assert shirt is not None
    assert shirt["name"] == "The Riviera Linen Overshirt"
    assert "sizes" in shirt and len(shirt["sizes"]) > 0

    # Search by query
    linen_results = search_catalog(query="linen")
    assert len(linen_results) > 0
    assert any("linen" in p["material"].lower() or "linen" in p["name"].lower() for p in linen_results)

    # Search by category and price
    filtered = search_catalog(category="pants", max_price=100.0)
    assert len(filtered) > 0
    assert all(p["category"] == "pants" and p["price"] <= 100.0 for p in filtered)


def test_state_initialization():
    """Verify SalesState schema and default factories."""
    state = init_sales_state()
    assert state["intent_stage"] == "EXPLORER"
    assert state["current_node"] == "greeting"
    assert isinstance(state["messages"], list)
    assert isinstance(state["customer_profile"], dict)
    assert isinstance(state["cart_intent"], dict)


def test_intent_classification_routing():
    """Verify all 6 intent classifications route accurately."""
    state = init_sales_state()

    # 1. Action
    state["messages"] = [HumanMessage(content="I want to buy this right now, add to cart!")]
    assert classify_intent(state) == "action"

    # 2. Objection
    state["messages"] = [HumanMessage(content="Is this true to size or does it shrink in the wash?")]
    assert classify_intent(state) == "objection"

    # 3. Validation
    state["messages"] = [HumanMessage(content="How does this blazer look? Will it suit me?")]
    assert classify_intent(state) == "validation"

    # 4. Curation
    state["messages"] = [HumanMessage(content="Recommend me a casual outfit for evening drinks")]
    assert classify_intent(state) == "curation"

    # 5. Discovery
    state["messages"] = [HumanMessage(content="I'm heading to a summer wedding in southern Italy")]
    assert classify_intent(state) == "discovery"

    # 6. Greeting
    state["messages"] = [HumanMessage(content="Hello!")]
    assert classify_intent(state) == "greeting"


def test_sales_graph_compilation():
    """Verify LangGraph compiles without errors."""
    graph = build_sales_graph()
    assert graph is not None


def test_api_health_endpoint():
    """Verify /health endpoint."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["groq_configured"] is True
    assert data["catalog_size"] >= 9


def test_api_catalog_endpoint():
    """Verify /api/catalog and /api/catalog/{id} endpoints."""
    res = client.get("/api/catalog")
    assert res.status_code == 200
    assert len(res.json()) >= 9

    res_item = client.get("/api/catalog/shirt-01")
    assert res_item.status_code == 200
    assert res_item.json()["id"] == "shirt-01"

    res_404 = client.get("/api/catalog/non-existent-id")
    assert res_404.status_code == 404


def test_api_chat_sync():
    """Verify non-streaming POST /api/chat endpoint."""
    payload = {
        "message": "Hi, I'm looking for a stylish lightweight shirt for vacation.",
        "session_id": "test-session-sync",
    }
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "test-session-sync"
    assert len(data["message"]) > 0
    assert len(data["quick_replies"]) > 0
    assert data["node"] in ["curation", "discovery", "greeting", "validation"]


def test_api_chat_stream():
    """Verify SSE streaming endpoint /api/chat/stream yields tokens and final event."""
    payload = {
        "message": "Tell me about the Riviera linen overshirt.",
        "session_id": "test-session-stream",
    }
    with client.stream("POST", "/api/chat/stream", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in response.iter_lines()]
        event_text = "\n".join(lines)

        assert "event: start" in event_text
        assert "event: token" in event_text
        assert "event: done" in event_text


def test_api_reset_session():
    """Verify session reset."""
    res = client.post("/api/reset", json={"session_id": "test-session-sync"})
    assert res.status_code == 200
    assert res.json()["status"] == "reset"
