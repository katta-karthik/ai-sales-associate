# Architecture Contracts & Interfaces

This document outlines the formal contracts and data schemas binding the Storefront, Widget SDK, and Backend Engine.

---

## 1. Storefront Microdata Contract

Storefront pages must provide product metadata via one or more of the following mechanisms (in order of extraction priority):

### Primary: Schema.org JSON-LD Microdata
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "The Sovereign Merino Wool Blazer",
  "image": ["https://images.unsplash.com/..."],
  "description": "Tailored from ultra-fine 100% Australian merino wool...",
  "sku": "BLZ-001",
  "offers": {
    "@type": "Offer",
    "priceCurrency": "USD",
    "price": "495.00",
    "availability": "https://schema.org/InStock"
  }
}
</script>
```

### Secondary: OpenGraph Tags
```html
<meta property="og:title" content="The Sovereign Merino Wool Blazer" />
<meta property="og:description" content="Tailored from ultra-fine 100% Australian merino wool..." />
<meta property="og:image" content="https://images.unsplash.com/..." />
<meta property="og:price:amount" content="495.00" />
<meta property="og:price:currency" content="USD" />
```

### Tertiary: Native Purchase Section Selectors
The storefront PDP should expose actionable elements matching standard IDs:
- `#add-to-cart-btn`: Native Add to Cart button.
- `#buy-now-btn`: Native Buy Now button.
- `#purchase-section`: Contains merchant purchase controls. The stylist can focus the native add-to-cart button.

---

## 2. Widget Behavioral Hesitation Matrix Contract

The `hesitation_matrix.js` module monitors client-side telemetry and dispatches proactive trigger events:

| Signal Name | Trigger Condition | Intended Agent Action |
|-------------|-------------------|-----------------------|
| `dwell_spike` | Dwell on product page > 20s without interaction | Proactive greeting with "Hero" validation compliment |
| `scroll_reversal` | > 2 scroll reversals between top & bottom within 10s | Offer consultative sizing or styling guidance |
| `variant_toggle` | > 3 size/color swatch toggles within 15s | Provide fit & fabric reassurance, address objection |
| `return_to_top` | Rapid scroll back to header from purchase section | Proactive review synthesis & gentle closing nudge |

---

## 3. Backend HTTP API Contracts

### `POST /api/chat/stream`
Server-Sent Events (SSE) streaming endpoint for real-time typewriter dialogue.

**Request Body (JSON):**
```json
{
  "message": "Does this blazer fit true to size?",
  "session_id": "sess-uuid-v4",
  "current_product": {
    "id": "blazer-001",
    "title": "The Sovereign Merino Wool Blazer",
    "price": 495.0,
    "category": "jackets"
  },
  "viewed_products": [
    {
      "id": "blazer-001",
      "title": "The Sovereign Merino Wool Blazer",
      "price": 495.0
    }
  ],
  "hesitation_trigger": "variant_toggle"
}
```

**SSE Event Types:**
1. `event: metadata`
   ```json
   {
     "intent_stage": "EVALUATOR",
     "quick_replies": ["How does it fit in the shoulders?", "What trousers pair well?"],
     "recommended_product": { ... },
     "action": "highlight_size_guide"
   }
   ```
2. `event: token`
   ```json
   { "text": "It " }
   ```
3. `event: done`
   ```json
   { "session_id": "sess-uuid-v4" }
   ```

### `POST /api/chat`
Synchronous chat endpoint (JSON response fallback).

**Response Body (JSON):**
```json
{
  "reply": "It fits tailored through the chest with an Italian drape...",
  "intent_stage": "EVALUATOR",
  "quick_replies": ["Sizing guide", "Fabric details"],
  "recommended_product": { ... },
  "action_payload": null,
  "session_id": "sess-uuid-v4"
}
```

### `GET /api/catalog`
Query parameters: `q` (string, optional), `category` (string, optional), `max_price` (float, optional).

---

## 4. LangGraph State Machine Contract

```
       ┌──────────────────────┐
       │     START NODE       │
       └──────────┬───────────┘
                  │ Intent Classification
       ┌──────────┴────────────────────────────────┐
       ▼                         ▼                 ▼
┌──────────────┐         ┌──────────────┐   ┌──────────────┐
│   Greeting   │         │  Discovery   │   │   Curation   │
│ (EXPLORER)   │         │ (EXPLORER)   │   │ (EVALUATOR)  │
└──────┬───────┘         └──────┬───────┘   └──────┬───────┘
       │                        │                  │
       └────────────┐           │           ┌──────┘
                    ▼           ▼           ▼
             ┌─────────────────────────────────────┐
             │             Validation              │
             │     ("Hero" compliment styling)     │
             └──────────────────┬──────────────────┘
                                │
                                ▼
             ┌─────────────────────────────────────┐
             │             Objection               │
             │   (Fit / fabric review synthesis)   │
             └──────────────────┬──────────────────┘
                                │
                                ▼
             ┌─────────────────────────────────────┐
             │               Action                │
             │ (Gentle urgency / Smooth-scroll CTA)│
             └──────────────────┬──────────────────┘
                                │
                                ▼
                       ┌────────────────┐
                       │    END NODE    │
                       └────────────────┘
```

The `SalesState` schema:
- `messages`: List of chat messages (HumanMessage, AIMessage) with `add_messages` reducer.
- `customer_profile`: Dict storing customer preferences (fit, style, budget, occasions).
- `viewed_products`: List of products viewed during current browsing session.
- `intent_stage`: `EXPLORER` | `EVALUATOR` | `READY_TO_BUY`.
- `cart_intent`: Boolean flag tracking purchase commitment.
- `recommended_products`: List of products selected for the customer.
- `quick_replies`: List of suggested 3-word follow-up queries.
- `action_payload`: Directives for widget actions (e.g., `scroll_to_purchase`, `highlight_swatch`).
