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


def test_langchain_modern_trim_messages():
    """Verify modern LangChain trim_messages integration in build_node_prompt."""
    from backend.app.agent.graph import build_node_prompt
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    state = init_sales_state()
    # Add 20 back-and-forth turns
    for i in range(20):
        state["messages"].append(HumanMessage(content=f"Shopper message {i} inquiring about linen garments and wool suits"))
        state["messages"].append(AIMessage(content=f"Stylist guidance {i} recommend sovereign blazer"))

    prompt_messages = build_node_prompt("discovery", state)
    # 1. SystemMessage is preserved at index 0
    assert isinstance(prompt_messages[0], SystemMessage)
    # 2. Window starts on HumanMessage
    assert isinstance(prompt_messages[1], HumanMessage)
    # 3. Message count is bounded
    assert len(prompt_messages) < 25


def test_langgraph_memory_saver_persistence():
    """Verify LangGraph MemorySaver checkpointer maintains thread checkpoints."""
    from backend.app.agent.graph import sales_graph
    thread_id = "test-checkpointer-persistence-sid"
    cfg = {"configurable": {"thread_id": thread_id}}

    # Invoke graph directly through SalesGraphRunner with thread_id
    res = sales_graph.invoke({"messages": [HumanMessage(content="Hello!")]}, config=cfg)
    assert res is not None
    assert "messages" in res

    # Inspect checkpoint saved in MemorySaver
    saved_state = sales_graph.get_state(cfg)
    assert saved_state is not None
    assert len(saved_state.values.get("messages", [])) >= 2


def test_langchain_tools_and_tool_node():
    """Verify modern @tool decorators and ToolNode execution."""
    from backend.app.agent.graph import (
        search_store_catalog,
        get_product_specs,
        calculate_discount,
        sales_tool_node,
    )

    # 1. Direct tool invocations
    results = search_store_catalog.invoke({"query": "linen", "occasion": "summer"})
    assert isinstance(results, list)
    assert len(results) > 0

    specs = get_product_specs.invoke({"product_id": "shirt-01"})
    assert specs.get("id") == "shirt-01"

    discount = calculate_discount.invoke({"product_id": "shirt-01", "promo_code": "STYLIST10"})
    assert discount["discount_code"] == "STYLIST10"
    assert discount["discounted_price"] < discount["original_price"]

    # 2. ToolNode verified
    assert sales_tool_node is not None
    assert len(sales_tool_node.tools_by_name) == 3


def test_customer_profile_preservation_and_sizing():
    """Verify multi-turn customer profile accumulation without amnesia."""
    from backend.app.agent.graph import update_customer_profile

    state = init_sales_state()
    # Turn 1: occasion wedding
    p1 = update_customer_profile(state, "looking for a wedding suit")
    assert "wedding" in p1["occasion"].lower()

    # Turn 2: brief follow-up reception - must not overwrite wedding
    p2 = update_customer_profile(state, "reception")
    assert "wedding" in p2["occasion"].lower()
    assert "reception" in p2["occasion"].lower()

    # Turn 3: brief sizing answer
    p3 = update_customer_profile(state, "40R")
    assert p3["size"] == "40R"

    # Turn 4: budget constraint
    p4 = update_customer_profile(state, "budget is around 350")
    assert p4["budget"] == 350.0


def test_punchy_brevity_enforcement():
    """Verify make_punchy limits text to <=2 sentences, under 25 words, and strips pills tags."""
    from backend.app.agent.graph import make_punchy

    long_text = (
        "The Sovereign Merino Wool Blazer is an exquisite piece crafted in Italy. "
        "It drapes effortlessly with natural stretch and wrinkle resistance. "
        "You will look exceptionally sharp at any evening event you attend! "
        "<pills>['Option 1', 'Option 2']</pills>"
    )
    clean = make_punchy(long_text, max_sentences=2)
    assert "<pills>" not in clean
    assert len(clean.split()) <= 25
    sentences = [s.strip() for s in clean.split(".") if s.strip()]
    assert len(sentences) <= 2


def test_curation_routing_with_sizing_and_fit_preferences():
    """Verify curation requests with sizing/fit filters route to curation, not objection."""
    from backend.app.agent.graph import classify_intent

    # Curation with sizing filters
    for prompt in [
        "Show me shirts in medium",
        "Find me casual jackets in size L",
        "Looking for a size 40 blazer for a wedding",
        "Recommend me shirts in large",
    ]:
        s = init_sales_state()
        s["messages"].append(HumanMessage(content=prompt))
        node = classify_intent(s)
        assert node == "curation", f"Prompt '{prompt}' classified as '{node}', expected 'curation'"

    # Fit preferences route to discovery
    for prompt in ["relaxed fit", "slim fit", "tailored fit"]:
        s = init_sales_state()
        s["messages"].append(HumanMessage(content=prompt))
        node = classify_intent(s)
        assert node == "discovery", f"Prompt '{prompt}' classified as '{node}', expected 'discovery'"

    # Actual sizing objections still route to objection
    for prompt in ["Is this true to size?", "Check my size", "40R", "medium"]:
        s = init_sales_state()
        s["messages"].append(HumanMessage(content=prompt))
        node = classify_intent(s)
        assert node == "objection", f"Prompt '{prompt}' classified as '{node}', expected 'objection'"


def test_session_reset_clears_checkpointer_storage():
    """Verify POST /api/reset completely eliminates checkpoints with zero zombie state."""
    from backend.app.main import SESSIONS
    from backend.app.agent.graph import sales_graph
    sid = "test-reset-checkpointer-clean"

    # 1. Send first message
    res1 = client.post("/api/chat", json={"message": "I want a wedding suit", "session_id": sid})
    assert res1.status_code == 200
    assert sid in SESSIONS
    assert len(SESSIONS[sid]["messages"]) == 2

    # Verify checkpoint exists
    chk1 = sales_graph.get_state({"configurable": {"thread_id": sid}})
    assert chk1 is not None and len(chk1.values.get("messages", [])) >= 2

    # 2. Reset session
    res2 = client.post("/api/reset", json={"session_id": sid})
    assert res2.status_code == 200
    assert sid not in SESSIONS

    # 3. Next message on the same session_id must start 100% fresh
    res3 = client.post("/api/chat", json={"message": "Hello", "session_id": sid})
    assert res3.status_code == 200
    assert len(SESSIONS[sid]["messages"]) == 2
    # Verify the old 'wedding suit' message is not in current session
    assert "wedding suit" not in SESSIONS[sid]["messages"][0].content.lower()


def test_tool_node_compiled_into_state_graph():
    """Verify ToolNode is an actual compiled node in sales_graph with conditional edges."""
    from backend.app.agent.graph import sales_graph
    graph = sales_graph._graph
    # Verify tools node is in compiled graph
    assert "tools" in graph.nodes, f"tools node missing from graph nodes: {list(graph.nodes.keys())}"


def test_stream_pills_prefix_buffering_no_leak():
    """Verify that streaming SSE does not leak partial <pills prefixes."""
    sid = "test-stream-pills-prefix-leak"
    payload = {
        "message": "Tell me about this shirt",
        "session_id": sid,
    }
    with client.stream("POST", "/api/chat/stream", json=payload) as response:
        assert response.status_code == 200
        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in response.iter_lines()]
        tokens = []
        for l in lines:
            if l.startswith("data: ") and '"type": "token"' in l:
                d = json.loads(l[6:])
                tokens.append(d["content"])
        full_streamed = "".join(tokens)
        assert "<pills" not in full_streamed, "Stream leaked <pills tag"
        assert "<pill" not in full_streamed, "Stream leaked <pill partial tag"
        assert "<p" not in full_streamed or "<p>" not in full_streamed
        # Verify done event contains dynamic replies
        done_lines = [l for l in lines if l.startswith("data: ") and '"type": "done"' in l]
        assert len(done_lines) > 0
        done_data = json.loads(done_lines[0][6:])
        assert len(done_data["quick_replies"]) > 0


def test_dynamic_store_persona():
    """Verify dynamic store identity produces customized system prompt with zero hardcoded brand."""
    from backend.app.agent.persona import get_stylist_system_prompt

    prompt = get_stylist_system_prompt(
        store_name="Chronos Haute Horlogerie",
        store_domain="chronos.ch",
        currency="CHF",
        brand_tone="ultra-luxury Swiss horology",
    )
    assert "Chronos Haute Horlogerie" in prompt
    assert "chronos.ch" in prompt
    assert "CHF" in prompt
    assert "ultra-luxury Swiss horology" in prompt
    assert "Karthik & Co." not in prompt

    # Verify via API chat request
    sid = "test-dynamic-store-session"
    res = client.post("/api/chat", json={
        "message": "Hi, tell me about your watch collection",
        "session_id": sid,
        "store_name": "Ginza Timepieces",
        "currency": "¥",
    })
    assert res.status_code == 200
    from backend.app.main import SESSIONS
    assert SESSIONS[sid]["store_name"] == "Ginza Timepieces"
    assert SESSIONS[sid]["currency"] == "¥"


def test_shopper_identity_and_hesitation_wiring():
    """Verify customer_id, shopper_uuid, viewed_products, and hesitation_trigger are wired into SalesState."""
    from backend.app.main import SESSIONS
    sid = "test-shopper-wiring-sid"

    payload = {
        "message": "I am not sure if this coat fits me",
        "session_id": sid,
        "customer_id": "cust_88291",
        "shopper_uuid": "uuid-cross-session-1234",
        "store_name": "Nordic Weave",
        "currency": "€",
        "viewed_products": [
            {"id": "coat-1", "title": "Wool Trench", "price": 280.0},
            {"id": "scarf-1", "title": "Cashmere Scarf", "price": 60.0},
        ],
        "hesitation_trigger": {"type": "pdp_dwell", "dwell_time": 25000, "reason": "size_hesitation"},
    }
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200

    state = SESSIONS[sid]
    assert state["customer_id"] == "cust_88291"
    assert state["shopper_uuid"] == "uuid-cross-session-1234"
    assert state["customer_profile"]["customer_id"] == "cust_88291"
    assert state["customer_profile"]["shopper_uuid"] == "uuid-cross-session-1234"
    assert state["customer_profile"]["hesitation_reason"] in ["pdp_dwell", "size_hesitation"]
    assert len(state["viewed_products"]) >= 2
    assert state["store_name"] == "Nordic Weave"


def test_measurement_table_in_product_context():
    """Verify precision sizing extraction formats measurement tables into LLM context."""
    from backend.app.agent.graph import format_product_context

    product = {
        "id": "pdp-coat",
        "title": "Seoul Tailored Trench",
        "price": 210.0,
        "currency": "₩",
        "sizes": ["M", "L"],
        "measurements": {
            "headers": ["Size", "Chest", "Length"],
            "rows": [{"Size": "M", "Chest": "104cm", "Length": "110cm"}],
            "summary": "Size M: Chest 104cm, Length 110cm"
        }
    }
    context = format_product_context([product], currency="₩")
    assert "Seoul Tailored Trench" in context
    assert "104cm" in context
    assert "₩" in context


def test_anti_hallucination_in_merchant_mode():
    """Verify Omotenashi anti-hallucination standard: no fabricated promo codes in merchant catalog mode."""
    from backend.app.main import resolve_node_metadata
    from backend.app.agent.state import init_sales_state

    merchant_items = [
        {"id": "lux-01", "title": "Kyoto Silk Kimono Jacket", "price": 450.0, "return_policy": "14-day unworn tag intact"}
    ]
    state = init_sales_state(viewed_products=merchant_items)
    state["merchant_catalog"] = True
    state["catalog_items"] = merchant_items

    stage, replies, recs, action, show_card = resolve_node_metadata("action", state, "I want to buy this")
    assert stage == "READY_TO_BUY"
    assert action is not None
    assert action["type"] == "view_product"
    assert "STYLIST10" not in str(action)
    assert not any("10% discount" in r for r in replies)


def test_native_discovery_zero_hardcoded_fallback():
    """Verify curation does not fall back to hardcoded catalog when merchant catalog is empty or active."""
    from backend.app.agent.graph import curation_node
    from backend.app.agent.state import init_sales_state

    state = init_sales_state(viewed_products=[])
    state["merchant_catalog"] = True
    state["catalog_items"] = []
    state["messages"].append(HumanMessage(content="Show me diamond rings"))

    result = curation_node(state)
    assert result["recommended_products"] == []
    # Must NOT contain hardcoded linen overshirt or sovereign blazer!
    for p in result["recommended_products"]:
        assert "linen" not in p.get("name", "").lower()
        assert "blazer" not in p.get("name", "").lower()


def test_conversion_telemetry_endpoint_and_state_loop():
    """Verify POST /api/telemetry/conversion updates session, customer profile, and checkpointer."""
    from backend.app.main import SESSIONS
    sid = "test-conversion-telemetry-sid"

    # Step 1: Initialize session with chat
    init_res = client.post("/api/chat", json={
        "message": "I love this watch, taking it!",
        "session_id": sid,
        "customer_id": "cust_tokyo_101",
    })
    assert init_res.status_code == 200

    # Step 2: Post conversion telemetry
    conv_payload = {
        "session_id": sid,
        "customer_id": "cust_tokyo_101",
        "shopper_uuid": "shopper_tokyo_uuid",
        "order_id": "ORDER-9921",
        "order_total": 520.0,
        "currency": "$",
        "purchased_items": [{"id": "item-watch-01", "name": "Chrono Classic", "price": 520.0}],
    }
    telemetry_res = client.post("/api/telemetry/conversion", json=conv_payload)
    assert telemetry_res.status_code == 200
    data = telemetry_res.json()
    assert data["status"] == "recorded"
    assert data["session_id"] == sid
    assert data["recorded_items_count"] == 1

    # Step 3: Verify customer profile in session state
    state = SESSIONS[sid]
    profile = state["customer_profile"]
    assert profile["has_converted"] is True
    assert profile["last_order_total"] == 520.0
    assert profile["last_order_id"] == "ORDER-9921"
    assert profile["conversion_count"] == 1
    assert state["cart_intent"]["purchased"] is True

    # Step 4: Record a second conversion to verify counter increments
    conv_payload2 = {
        "session_id": sid,
        "customer_id": "cust_tokyo_101",
        "order_id": "ORDER-9922",
        "order_total": 150.0,
        "purchased_items": [{"id": "item-strap-02", "name": "Leather Strap", "price": 150.0}],
    }
    res2 = client.post("/api/telemetry/conversion", json=conv_payload2)
    assert res2.status_code == 200
    assert SESSIONS[sid]["customer_profile"]["conversion_count"] == 2


def test_dynamic_merchant_store_zero_hardcoded_apparel_bleed(monkeypatch):
    """Verify external merchant stores never bleed hardcoded demo apparel or seed catalog."""
    from backend.app.main import chat_sync, ChatRequest, SESSIONS
    from backend.app.agent.graph import build_node_prompt

    class MerchantModel:
        def invoke(self, messages):
            return AIMessage(content="Welcome to Seiko Japan! What watch movement are you looking for?")
        async def astream(self, messages):
            yield self.invoke(messages)
    monkeypatch.setattr("backend.app.agent.graph.get_llm", lambda **kwargs: MerchantModel())

    sid = "test-seiko-zero-bleed-sid"
    req = ChatRequest(
        message="Hi, what products do you have?",
        session_id=sid,
        store_name="Seiko Japan",
        currency="JPY",
    )
    res = chat_sync(req)
    assert res.session_id == sid
    # Response must not hallucinate linen shirts or blazers
    lowered = res.message.lower()
    assert "linen" not in lowered
    assert "blazer" not in lowered
    assert "karthik" not in lowered
    # Recommendations and action must be empty
    assert res.recommended_products == []
    assert res.action_payload is None
    # Session state must have empty viewed_products rather than seed CATALOG_ITEMS[0]
    state = SESSIONS[sid]
    assert state["viewed_products"] == []
    assert state["merchant_catalog"] is True

    # Prompt messages sent to LLM must not include seed catalog items
    prompt_msgs = build_node_prompt(res.node, state)
    prompt_text = " ".join(str(m.content) for m in prompt_msgs).lower()
    assert "the riviera linen overshirt" not in prompt_text
    assert "sovereign merino" not in prompt_text
    assert "karthik & co" not in prompt_text


def test_injected_state_tools_scoped_to_merchant_catalog():
    """Verify tools with InjectedState correctly inspect merchant catalog and block unauthorized discounts."""
    from backend.app.agent.graph import search_store_catalog, get_product_specs, calculate_discount
    from backend.app.agent.state import init_sales_state

    merchant_items = [
        {"id": "watch-01", "name": "Grand Seiko Automatic", "price": 4200.0, "category": "watches"},
        {"id": "strap-01", "name": "Alligator Leather Strap", "price": 180.0, "category": "accessories"}
    ]
    state = init_sales_state(
        store_name="Grand Seiko Boutique",
        catalog_items=merchant_items,
        merchant_catalog=True,
        allow_discounts=False
    )

    # 1. search_store_catalog with merchant state
    res = search_store_catalog.invoke({"query": "automatic", "state": state})
    assert len(res) == 1
    assert res[0]["id"] == "watch-01"
    # Ensure no linen shirt is returned
    for r in res:
        assert "linen" not in r["name"].lower()

    # 2. get_product_specs for merchant product
    specs = get_product_specs.invoke({"product_id": "watch-01", "state": state})
    assert specs.get("id") == "watch-01"
    assert specs.get("name") == "Grand Seiko Automatic"

    # 3. get_product_specs for non-existent product in merchant mode
    specs_missing = get_product_specs.invoke({"product_id": "shirt-01", "state": state})
    assert "error" in specs_missing

    # 4. calculate_discount in merchant mode with allow_discounts=False blocks unauthorized discount
    disc = calculate_discount.invoke({"product_id": "watch-01", "promo_code": "STYLIST10", "state": state})
    assert "error" in disc


def test_omotenashi_anti_hallucination_quick_replies_across_all_nodes():
    """Verify resolve_node_metadata never produces 'Apply 10% discount' in merchant mode across any stage."""
    from backend.app.main import resolve_node_metadata
    from backend.app.agent.state import init_sales_state

    merchant_state = init_sales_state(
        store_name="Zenith Horology",
        merchant_catalog=True,
        allow_discounts=False
    )

    for node in ["action", "objection", "curation", "greeting", "discovery"]:
        for text in ["I want to buy", "What is your size guide?", "Show me watches", "reception", "dinner"]:
            stage, replies, recs, action, show_card = resolve_node_metadata(node, merchant_state, user_text=text)
            for r in replies:
                assert "10% discount" not in r, f"Node {node} with text '{text}' leaked discount pill: {r}"
                assert "STYLIST10" not in r


def test_widget_configuration_and_dom_extractor_identity():
    """Verify widget configure sets identity properties, customer identity reads merchant config, and measurement table handles matrices."""
    import subprocess
    node_test = """
    const fs = require('fs');
    global.window = {
      localStorage: {
        _d: {},
        getItem(k) { return this._d[k] || null; },
        setItem(k, v) { this._d[k] = String(v); }
      },
      sessionStorage: {
        _d: {},
        getItem(k) { return this._d[k] || null; },
        setItem(k, v) { this._d[k] = String(v); },
        removeItem(k) { delete this._d[k]; }
      },
      __AI_SALES_CONFIG: {
        customerId: 'merchant_cust_991',
        storeName: 'Atelier Ginza',
        currency: '¥',
        brandTone: 'haute couture Japanese minimalist'
      },
      location: { href: 'https://ginza.example.com', origin: 'https://ginza.example.com' }
    };
    global.document = {
      title: 'Atelier Ginza Collection',
      querySelectorAll() { return []; },
      querySelector() { return null; },
      addEventListener() {}
    };

    eval(fs.readFileSync('widget/dom_extractor.js', 'utf8'));
    eval(fs.readFileSync('widget/session_memory.js', 'utf8'));

    // 1. Identity reads merchant config customerId
    const identity = window.__AISalesAssociateDOMExtractor.extractCustomerIdentity();
    if (identity.customerId !== 'merchant_cust_991') throw new Error('Expected customerId from __AI_SALES_CONFIG');
    if (!identity.shopperUuid) throw new Error('Missing shopperUuid');

    // 2. searchNativeStore skips trivial greetings
    window.__AISalesAssociateDOMExtractor.searchNativeStore('hello').then(res => {
      if (!Array.isArray(res) || res.length !== 0) throw new Error('Expected empty array on greeting');
    });
    """
    res = subprocess.run(["node", "-e", node_test], capture_output=True, text=True)
    assert res.returncode == 0, f"Widget Node check failed: {res.stderr}"


def test_cross_session_customer_profile_memory():
    """Verify customer profile facts persist across separate sessions when customer_id is provided."""
    from backend.app.main import SESSIONS, CUSTOMER_PROFILES
    customer_id = "vip_customer_7788"

    # Session 1: customer establishes size and converts
    sid1 = "session-visit-1"
    res1 = client.post("/api/chat", json={
        "message": "I wear size 42 and prefer slim cut",
        "session_id": sid1,
        "customer_id": customer_id,
        "store_name": "Sartoria Milano",
    })
    assert res1.status_code == 200

    # Log conversion
    conv_res = client.post("/api/telemetry/conversion", json={
        "session_id": sid1,
        "customer_id": customer_id,
        "order_id": "ORD-99001",
        "order_total": 520.0,
        "purchased_items": [{"title": "Wool Suit", "size": "42"}],
    })
    assert conv_res.status_code == 200
    assert customer_id in CUSTOMER_PROFILES
    assert CUSTOMER_PROFILES[customer_id].get("has_converted") is True

    # Session 2: days later, customer returns with a brand new session_id
    sid2 = "session-visit-2-different-day"
    res2 = client.post("/api/chat", json={
        "message": "Hello, show me new arrivals",
        "session_id": sid2,
        "customer_id": customer_id,
        "store_name": "Sartoria Milano",
    })
    assert res2.status_code == 200

    # Verify session 2 automatically inherited customer facts from session 1
    state2 = SESSIONS[sid2]
    prof2 = state2["customer_profile"]
    assert prof2.get("customer_id") == customer_id
    assert prof2.get("has_converted") is True
    assert prof2.get("last_order_total") == 520.0
    assert prof2.get("size") == "42"




@pytest.mark.parametrize("route", ["/api/chat", "/api/chat/stream"])
def test_purchase_handoff_follows_explicit_shopper_choice(route):
    catalog = [
        {"title": "Linen Shirt", "url": "/shirt", "price": 100, "sizes": ["S", "M"]},
        {"title": "Linen Jacket", "url": "/jacket", "price": 120, "sizes": ["L", "XL"]},
    ]
    session_id = None

    def turn(message):
        nonlocal session_id
        response = client.post(route, json={"message": message, "catalog": catalog, "session_id": session_id})
        assert response.status_code == 200
        if route.endswith("/stream"):
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            result = events[-1]
            assert result["type"] == "done"
        else:
            result = response.json()
        session_id = result["session_id"]
        return result

    assert turn("Show me linen")["quick_replies"] == ["Tell me about Linen Shirt", "Tell me about Linen Jacket"]
    ambiguous = turn("I want to buy it")
    assert "Which" in ambiguous["message"]
    assert ambiguous["action_payload"] is None
    assert turn("Tell me about Linen Jacket")["recommended_products"] == [catalog[1]]
    assert "I wear XL" in turn("Check sizing")["quick_replies"]
    purchase = turn("Review product options")
    assert purchase["action_payload"]["url"] == "/jacket"
    assert purchase["recommended_products"] == [catalog[1]]
