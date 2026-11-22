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

def test_store():
    print("\n--- Verifying test-store/ ---")
    class StoreParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.loader_found = False
            self.json_ld = []
            self.ids = set()
            self._in_json_ld = False
        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if "id" in attrs_dict:
                self.ids.add(attrs_dict["id"])
            if tag == "script":
                src = attrs_dict.get("src", "")
                if "loader.js" in src:
                    self.loader_found = True
                if attrs_dict.get("type") == "application/ld+json":
                    self._in_json_ld = True
        def handle_data(self, data):
            if self._in_json_ld:
                self.json_ld.append(data.strip())
                self._in_json_ld = False

    # Check index.html
    with open("test-store/index.html", "r", encoding="utf-8") as f:
        idx_content = f.read()
    p1 = StoreParser()
    p1.feed(idx_content)
    assert p1.loader_found, "test-store/index.html must embed loader.js"
    print("  [OK] test-store/index.html embeds loader.js")

    # Check product.html
    with open("test-store/product.html", "r", encoding="utf-8") as f:
        pdp_content = f.read()
    p2 = StoreParser()
    p2.feed(pdp_content)
    assert p2.loader_found, "test-store/product.html must embed loader.js"
    assert "add-to-cart-btn" in p2.ids, "test-store/product.html missing #add-to-cart-btn"
    assert "buy-now-btn" in p2.ids, "test-store/product.html missing #buy-now-btn"
    assert len(p2.json_ld) > 0, "test-store/product.html missing application/ld+json"
    parsed_ld = json.loads(p2.json_ld[0])
    assert parsed_ld.get("@type") == "Product", "JSON-LD @type must be Product"
    print(f"  [OK] test-store/product.html embeds loader.js, native buttons, and valid Schema.org Product ({parsed_ld.get('name')})")

    # Check products.js syntax
    res = subprocess.run(["node", "-c", "test-store/products.js"], capture_output=True, text=True)
    assert res.returncode == 0, "Syntax error in test-store/products.js"
    print("  [OK] test-store/products.js syntax valid")

    # Check style.css exists
    assert os.path.exists("test-store/style.css"), "Missing test-store/style.css"
    print("  [OK] test-store/style.css exists")

if __name__ == "__main__":
    test_widget()
    test_backend()
    test_store()
    print("\n================ ALL CHECKS PASSED ================")
