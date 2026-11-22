# OpenWiki Developer & Maintenance Instructions

## Purpose

This directory contains living architectural documentation and verified interface contracts for the AI Sales Associate project.

## Verification Workflow

Before deploying changes or submitting PRs, run the comprehensive verification suite:

```bash
# 1. Run all end-to-end verifier checks:
python test_verification.py

# 2. Run backend test suite:
pytest backend/tests/test_backend.py -v

# 3. Check JavaScript syntax:
node -c widget/*.js test-store/*.js
```

## Maintenance Rules

1. **Zero-Crash Guardrails**: Any new feature introduced to `widget/` must be wrapped in `__AISalesAssociateShield.executeSafe` or `executeSafeAsync`.
2. **Shadow DOM Enforcement**: All widget elements must reside strictly within the closed Shadow DOM of `<ai-sales-associate>`.
3. **Core Web Vitals Guardrails**:
   - `loader.js` bundle size must stay strictly below 15 KB.
   - Do not trigger synchronous DOM recalculations or layout thrashing during page load; use `requestIdleCallback`.
4. **Resilient LLM Routing**: In `backend/app/agent/graph.py`, always ensure fallback candidate models are configured so API provider tier changes or missing model endpoints never take down the service.
