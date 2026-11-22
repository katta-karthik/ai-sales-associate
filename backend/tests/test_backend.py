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
from langchain_core.messages import AIMessage, HumanMessage


client = TestClient(app)


@pytest.fixture(autouse=True)
def local_model(monkeypatch):
    class Model:
        def invoke(self, messages):
            return AIMessage(content="Try the linen shirt.")

        async def astream(self, messages):
            yield self.invoke(messages)

    monkeypatch.setattr("backend.app.agent.graph.get_llm", lambda **kwargs: Model())


def test_product_size_quick_replies():
    from backend.app.main import resolve_node_metadata
    state = init_sales_state(viewed_products=[{"name": "Shirt", "sizes": ["S", "M", 42]}])
    replies = resolve_node_metadata("validation", state, "What shoes pair with this?")[1]
    assert "What shoes work best?" in replies
    for answer in ["I wear M", "42"]:
        assert "I wear 42" in resolve_node_metadata("objection", state, answer)[1]



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


@pytest.mark.parametrize("key", ["", "test-key"])
def test_api_health_endpoint(monkeypatch, key):
    """Verify /health endpoint."""
    monkeypatch.setenv("GROQ_API_KEY", key)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["groq_configured"] is bool(key)
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


def test_multiturn_session_persistence_and_no_amnesia():
    """Verify multi-turn session persistence eliminates conversational amnesia and greeting resets."""
    from backend.app.main import SESSIONS
    sid = "test-session-marriage-flow"

    # Turn 1: User indicates shopping for a marriage
    p1 = {
        "message": "yes for marraige",
        "thread_id": sid,
        "product_context": {
            "title": "The Sovereign Merino Wool Blazer",
            "price": "349.00",
            "material": "100% Superfine 120s Italian Merino Wool",
            "variants": {"sizes": ["S", "M", "L", "XL"]}
        }
    }
    res1 = client.post("/api/chat", json=p1)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["session_id"] == sid
    assert data1["node"] == "discovery"
    assert "<pills>" not in data1["message"]
    assert sid in SESSIONS
    assert len(SESSIONS[sid]["messages"]) == 2

    # Turn 2: User answers short follow-up "reception"
    p2 = {
        "message": "reception",
        "session_id": sid
    }
    res2 = client.post("/api/chat", json=p2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["session_id"] == sid
    # Must NOT reset to greeting!
    assert data2["node"] in ["discovery", "curation", "validation"]
    assert data2["node"] != "greeting"
    assert "welcome to karthik & co." not in data2["message"].lower()
    # Check that session retained all 4 messages
    assert len(SESSIONS[sid]["messages"]) == 4


def test_product_context_normalization_and_dynamic_discount():
    """Verify live PDP product data is normalized and discount computed dynamically."""
    sid = "test-session-live-product"
    payload = {
        "message": "Apply the 10% discount and let's buy",
        "session_id": sid,
        "product_context": {
            "title": "The Sovereign Merino Wool Blazer",
            "price": "349.00",
            "currency": "$",
            "variants": {"sizes": ["S", "M", "L", "XL"]}
        }
    }
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["node"] == "action"
    assert data["action_payload"] is not None
    action = data["action_payload"]
    assert action["original_price"] == 349.0
    assert action["discounted_price"] == 314.10
    assert action["discount_code"] == "STYLIST10"
    assert "Sovereign" in action["product_name"]


def test_chitchat_routing_no_greeting_reset():
    """Verify chit-chat like 'what is ur name' and 'are u biased' do not trigger initial greeting."""
    state = init_sales_state()

    state["messages"] = [HumanMessage(content="what is ur name")]
    node1 = classify_intent(state)
    assert node1 != "greeting"
    assert node1 == "discovery"

    state["messages"] = [HumanMessage(content="are u biased")]
    node2 = classify_intent(state)
    assert node2 != "greeting"
    assert node2 == "discovery"


def test_stream_with_thread_id_and_dynamic_pills():
    """Verify SSE streaming with thread_id extracts dynamic pills into done event."""
    payload = {
        "message": "What should I pair with this blazer for an evening dinner?",
        "thread_id": "test-stream-pills-session",
        "product_context": {
            "title": "The Sovereign Merino Wool Blazer",
            "price": 349.00
        }
    }
    with client.stream("POST", "/api/chat/stream", json=payload) as response:
        assert response.status_code == 200
        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in response.iter_lines()]
        
        # Verify done event
        done_lines = [l for l in lines if l.startswith("data: ") and '"type": "done"' in l]
        assert len(done_lines) > 0
        done_data = json.loads(done_lines[0][6:])
        assert done_data["session_id"] == "test-stream-pills-session"
        assert len(done_data["quick_replies"]) > 0
        assert "<pills>" not in done_data["message"]


def test_full_conversational_turn_sequence_without_looping_or_hallucination():
    """Verify entire sequence of dialogue from task prompt eliminates amnesia and looping pills."""
    state = init_sales_state(viewed_products=[{
        "id": "merino-blazer",
        "name": "The Sovereign Merino Wool Blazer",
        "title": "The Sovereign Merino Wool Blazer",
        "price": 349.0,
        "material": "100% Merino Wool",
        "variants": {"sizes": ["38R", "40R", "42R"]}
    }])

    test_turns = [
        ("Just browsing fresh styles", ["curation", "discovery"]),
        ("Check my size", ["objection"]),
        ("What should I pair with this?", ["validation"]),
        ("what is ur name", ["discovery"]),
        ("are u based", ["discovery"]),
        ("are u biased", ["discovery"]),
        ("i don't like this", ["curation"]),
        ("yes for marraige", ["discovery"]),
        ("reception", ["discovery", "validation"]),
        ("Apply the 10% discount and let's buy", ["action"]),
    ]

    for user_input, expected_nodes in test_turns:
        state["messages"].append(HumanMessage(content=user_input))
        node = classify_intent(state)
        assert node in expected_nodes, f"Input '{user_input}' classified as '{node}', expected one of {expected_nodes}"
        assert node != "greeting", f"Input '{user_input}' erroneously reset to 'greeting'"
        # Simulate assistant turn
        state["messages"].append(HumanMessage(content=f"Stylist response to {user_input}"))


@pytest.mark.parametrize("route", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize("budget, expected", [(150, ["linen"]), (100, [])])
def test_merchant_discovery(route, budget, expected):
    catalog = [
        {"id": "linen", "title": "Linen Shirt", "price": 100},
        {"id": "cotton", "title": "Cotton Shirt", "price": 90},
        {"id": "sold", "title": "Linen Blazer", "price": 99, "in_stock": False},
    ]
    response = client.post(route, json={"message": f"Show me linen under ${budget}", "catalog": catalog})
    assert response.status_code == 200
    if route.endswith("/stream"):
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [e["type"] for e in events] == ["start", "token", "done"]
        result = events[-1]
    else:
        result = response.json()
    assert [item["id"] for item in result["recommended_products"]] == expected
    assert result["show_card"] is bool(expected)
