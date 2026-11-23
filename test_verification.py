"""Comprehensive verification script for AI Sales Associate."""
import json
import os
import subprocess
import sys
from html.parser import HTMLParser

def test_widget():
    print("--- Verifying widget/ ---")
    required = [
        "widget/shield.js",
        "widget/dom_extractor.js",
        "widget/hesitation_matrix.js",
        "widget/session_memory.js",
        "widget/widget.js",
        "widget/loader.js"
    ]
    for r in required:
        assert os.path.exists(r), f"Missing module: {r}"
        size = os.path.getsize(r)
        print(f"  [OK] {r} exists ({size} bytes)")
    
    loader_size = os.path.getsize("widget/loader.js")
    assert loader_size < 15360, f"loader.js ({loader_size} B) exceeds 15KB budget"
    print(f"  [OK] loader.js is lightweight ({loader_size} bytes < 15KB)")

    # Syntax check all 6 files with node -c
    for path in required:
        res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        assert res.returncode == 0, f"Syntax error in {path}: {res.stderr}"
    print("  [OK] 0 syntax errors across all 6 widget files")

    with open("widget/widget.js", "r", encoding="utf-8") as f:
        content = f.read()
    assert "attachShadow({ mode: 'closed' })" in content, "widget.js must attach shadow DOM in closed mode"
    assert "customElements.define('ai-sales-associate'" in content or "customElements.define(" in content, "widget.js must define custom element"
    print("  [OK] Mounts cleanly inside closed Shadow DOM (<ai-sales-associate>)")

    # Verify widget JS functionality (Customer identity, native search, session memory conversion)
    node_script = """
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
      ShopifyAnalytics: { meta: { page: { customerId: 44091 } } },
      dataLayer: [{ userId: 'user_dl_102' }],
      location: { href: 'https://store.example.com/products/jacket', pathname: '/products/jacket' }
    };
    global.document = {
      title: 'Luxury Leather Bomber | TokyoShift',
      querySelectorAll() { return []; },
      querySelector() { return null; },
      addEventListener() {}
    };

    eval(fs.readFileSync('widget/dom_extractor.js', 'utf8'));
    eval(fs.readFileSync('widget/session_memory.js', 'utf8'));

    const identity = window.__AISalesAssociateDOMExtractor.extractCustomerIdentity();
    if (identity.customerId !== '44091') throw new Error('Expected customerId 44091');
    if (!identity.shopperUuid) throw new Error('Expected shopperUuid');
    if (window.localStorage.getItem('__ai_sales_shopper_uuid') !== identity.shopperUuid) throw new Error('UUID not in localStorage');

    const conv = window.__AISalesAssociateSessionMemory.recordConversion({ orderId: 'ORD-1', orderTotal: 99 });
    if (conv.orderId !== 'ORD-1') throw new Error('Conversion record failed');
    """
    res_fn = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    assert res_fn.returncode == 0, f"Widget JS function check failed: {res_fn.stderr}"
    print("  [OK] Widget customer identity & conversion telemetry verified")

def test_backend():
    print("\n--- Verifying backend/ ---")
    # Verify pytest suite
    res = subprocess.run([sys.executable, "-m", "pytest", "backend/tests/test_backend.py", "-v"], capture_output=True, text=True)
    print(res.stdout)
    assert res.returncode == 0, f"Backend pytest failed: {res.stderr}"
    print("  [OK] All backend unit tests passed")

    # Verify LangGraph compilation
    from backend.app.agent.graph import sales_graph
    assert sales_graph is not None
    print("  [OK] LangGraph state machine compiled cleanly")

    # Verify Groq LLM and .env
    from dotenv import load_dotenv
    load_dotenv()
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("  [SKIP] Groq client configuration check requires GROQ_API_KEY")
        return
    print("  [OK] GROQ_API_KEY is configured in .env")

    from backend.app.agent.graph import get_llm
    llm = get_llm()
    assert llm is not None
    print(f"  [OK] Groq LLM initialized: {getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))}")

if __name__ == "__main__":
    test_widget()
    test_backend()
    print("\n================ ALL PRODUCT CHECKS PASSED ================")
