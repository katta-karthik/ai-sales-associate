# OpenWiki Knowledge Base - AI Sales Associate

Welcome to the autonomous documentation wiki for the **AI Sales Associate** platform. This repository implements a high-converting, sub-second latency autonomous retail sales stylist for e-commerce stores, powered by Groq LPU and LangGraph Cloud Engine.

## Navigation

- [System Architecture](architecture.md)
- [Architecture Contracts & Interfaces](contracts.md)
- [Developer & Contribution Guide](INSTRUCTIONS.md)

## Core System Overview

The system is partitioned into three isolated subsystems with zero mutual build-time coupling:

```
┌────────────────────────────────────────────────────────┐
│                   Mock Storefront                      │
│        (test-store/index.html, product.html)           │
│  - Luxury apparel storefront (Karthik & Co.)           │
│  - Native schema.org JSON-LD & OpenGraph microdata     │
│  - Zero modification required beyond 1 embed tag       │
└──────────────────────────┬─────────────────────────────┘
                           │ Embeds <script src="widget/loader.js">
                           ▼
┌────────────────────────────────────────────────────────┐
│                   Client Embed SDK                     │
│                       (widget/)                        │
│  - Closed Shadow DOM Web Component (<ai-sales-assoc>)  │
│  - Circuit Breaker Crash Shield (shield.js)            │
│  - Non-blocking Microdata Extractor (dom_extractor.js) │
│  - Passive Hesitation Matrix (hesitation_matrix.js)    │
│  - Cross-Page Session Memory (session_memory.js)       │
│  - Lightweight Async Entrypoint <15KB (loader.js)      │
└──────────────────────────┬─────────────────────────────┘
                           │ SSE Stream / REST JSON
                           ▼
┌────────────────────────────────────────────────────────┐
│            LangGraph Cloud Sales Engine                │
│                       (backend/)                       │
│  - Ultra-fast Groq LPU inference (llama-3.3 / gpt-oss) │
│  - 6-Node LangGraph State Machine (graph.py)           │
│  - Lead In-Store Stylist Persona (persona.py)          │
│  - In-Memory Multi-Facet Catalog (catalog.py)          │
│  - FastAPI SSE Streaming Server (main.py)              │
└────────────────────────────────────────────────────────┘
```

## Performance & Reliability Guarantees

1. **Zero Core Web Vitals Impact**:
   - Zero Cumulative Layout Shift (CLS): Root element uses `position: fixed`, completely detached from store flow.
   - Zero INP / FID Impact: All DOM parsing occurs during `requestIdleCallback` or background chunks.
   - Minimal Bundle Footprint: `loader.js` entrypoint is <7 KB (budget <15 KB).

2. **Zero-Crash Host Guarantee**:
   - The embed SDK runs under a circuit breaker (`shield.js`).
   - If 3 unhandled exceptions or rejected promises occur within the widget lifecycle, the widget triggers a silent, graceful unmount, completely removing itself and leaving the host store 100% operational.

3. **Sub-Second Streaming Inference**:
   - Powered by Groq LPUs with sub-100ms time-to-first-token (TTFT).
