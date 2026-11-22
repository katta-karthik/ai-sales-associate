# System Architecture

## Architectural Principles

1. **Host Isolation**: The widget lives entirely inside a **closed mode Shadow DOM** (`attachShadow({ mode: 'closed' })`). Host store CSS cannot pollute widget styles, and widget styles cannot bleed into the store.
2. **Defensive Fault Containment**: The widget wraps all entrypoints and event listeners in a circuit breaker. Any unhandled error originating from widget scripts is prevented from bubbling up to the host window.
3. **Decoupled Contracts**: The widget interacts with the backend strictly through HTTP REST and Server-Sent Events (SSE), enabling independent deployments and serverless scaling.

## Component Breakdown

### 1. Client Embed SDK (`widget/`)
- **`loader.js`**:
  - Dynamically discovers its own host origin.
  - Sequentially boots dependencies: `shield.js` -> `dom_extractor.js` -> `session_memory.js` -> `hesitation_matrix.js` -> `widget.js`.
  - Dispatches `window.aiSalesAssociateReady`.
- **`shield.js`**:
  - Encapsulates `CircuitBreaker`.
  - Threshold: 3 failures with a 60-second sliding reset window.
  - Global error listener: hooks `window.addEventListener('error')` and `unhandledrejection`, filtering by widget filenames and invoking `event.preventDefault()`.
  - Unmount routine removes `<ai-sales-associate>` node from document body.
- **`dom_extractor.js`**:
  - Uses `requestIdleCallback` (with `setTimeout` fallback).
  - Traverses `script[type="application/ld+json"]` extracting `@type: "Product"` data (name, price, currency, availability, sku).
  - Scrapes OpenGraph tags (`og:title`, `og:price:amount`, `og:image`, `og:description`).
  - Scrapes DOM fallbacks (`h1`, `meta[name="description"]`).
- **`hesitation_matrix.js`**:
  - Tracks user micro-behaviors with passive event listeners (`{ passive: true }`):
    - *Dwell Spike*: User spends >20s on a single product without scrolling or clicking.
    - *Scroll Reversal*: Rapid alternation between page bottom and top (>2 reversals in 10s).
    - *Variant Toggling*: Rapid switching between sizes or swatches (>3 toggles in 15s).
    - *Return-to-Top*: Fast jump from purchase area back to top.
  - Dispatches proactive contextual nudge triggers through the widget event pipeline.
- **`session_memory.js`**:
  - Manages `thread_id` and persists viewed product history across multi-page navigation using `sessionStorage`.
  - Falls back gracefully to memory store if `sessionStorage` is blocked by browser policies.
- **`widget.js`**:
  - Custom Element: `<ai-sales-associate>`.
  - Closed Shadow Root with Constructable Stylesheets.
  - Floating Stylist Pill with status beacon.
  - Proactive speech bubble.
  - Chat drawer with SSE streaming typewriter effect, quick-reply pills, product card with "Hero" validation compliment, and 'View & Buy' button triggering native smooth scroll to purchase section.

### 2. LangGraph Cloud Sales Engine (`backend/`)
- **`main.py`**:
  - FastAPI server exposing:
    - `POST /api/chat/stream`: SSE token stream.
    - `POST /api/chat`: Synchronous response fallback.
    - `GET /api/catalog`: Product search and category filter.
    - `GET /health`: Healthcheck endpoint.
    - `POST /api/session/reset`: Reset customer session state.
- **`graph.py`**:
  - LangGraph State Machine containing 6 nodes:
    1. `GreetingNode`: Warm opening acknowledging user context.
    2. `DiscoveryNode`: Consultative discovery of customer taste and requirements.
    3. `CurationNode`: Matching catalog items against customer criteria.
    4. `ValidationNode`: "Hero" validation compliment reassuring customer confidence.
    5. `ObjectionNode`: Review synthesis addressing fit, fabric, or price hesitation.
    6. `ActionNode`: Gentle urgency and direct smooth-scroll/cart call-to-action.
  - Intent classification routing based on conversational state and keyword/intent extraction.
- **`persona.py`**:
  - System prompt engineering for *Julian*, Lead In-Store Stylist.
- **`catalog.py`**:
  - In-memory structured apparel catalog with multi-facet search.

### 3. Test Storefront (`test-store/`)
- **`index.html`**: Luxury apparel homepage with hero banner, category filters, product grid, and loader embed.
- **`product.html`**: High-fidelity PDP with multi-image gallery, size/color selectors, native `#add-to-cart-btn` and `#buy-now-btn`, and valid Schema.org Product JSON-LD.
- **`products.js`**: Client-side catalog hydration and mock checkout toast logic.
- **`style.css`**: Luxury typography, animations, responsive layouts.
