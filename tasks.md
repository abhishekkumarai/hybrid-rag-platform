# Tasks: UI ↔ Backend Gap Fixes

Generated from a frontend/backend audit (`ui/index.html` vs `services/gateway/api.py` + `contracts/`).
See the full audit for method/evidence: `C:\Users\abhi3\.claude\plans\check-the-application-and-greedy-peacock.md`.

## Confirmed gaps (actionable)

- [x] **Wire VRAM footprint display to real telemetry.**
  `GET /api/v1/hardware/gpu` exists and returns live VRAM data (via `ollama ps`/`nvidia-smi`), but
  `ui/index.html:2237-2296` never called it — the header pill, workspace drawer, and Models page rendered
  numbers from a hardcoded `MODEL_VRAM` lookup table instead.
  Done: `updateVramBudget()` now fetches `/api/v1/hardware/gpu` (used/total/free VRAM, active model, source)
  and paints all three displays from it, falling back to a single static estimate only if the request fails.
  Also polls every 15s (`setInterval`) so the header pill stays live.

- [x] **Add queue stats to Observability page.**
  `GET /api/v1/queue/stats` (pending/processing/DLQ counts) had no frontend caller — only the DLQ list
  and replay endpoints were used, and `processing` count wasn't shown anywhere (`pending`/`dlq` were already
  duplicated into `/api/v1/metrics`).
  Done: added a `PROCESSING` stat tile to the Observability page, fed by a new `/api/v1/queue/stats` fetch
  in `loadObservability()`.

- [x] **Stop silently faking Knowledge Graph data on failure/empty state.**
  `renderKnowledgeGraphDemo()` rendered a fictional dataset ("Acme Corp", invented entities/edges) both when
  `GET /api/v1/graph/stats` failed *and* when it succeeded with zero real entities (bypassing the existing,
  correct `kg-empty-state` "Graph Awaiting Ingestion" placeholder).
  Done: removed `renderKnowledgeGraphDemo()` entirely. Backend failure/network error now shows a
  "Graph Data Unavailable" state (`showKgUnavailableState()`); a genuinely empty graph shows the original
  "Graph Awaiting Ingestion" placeholder. No fabricated data is ever rendered.

## Secondary / documentation (lower priority)

- [x] **Update `DESIGN.md`'s mode selector docs.** Added the 4th mode (`Graph` / GraphRAG) to the header
  retrieval-mode-selector description, matching the shipped UI/backend.

- [ ] **Type-enforce agentic contracts through the chat endpoint.** `contracts/agent.py`'s
  `AgenticRetrieveResponse`, `DecompositionPlan`, `SubQuery`, `CRAGAssessment` are used internally by
  `AgenticCoordinator.run_plan` but never returned as a typed FastAPI `response_model` —
  `/api/v1/chat`'s SSE `agent_step`/`sub_queries` events are hand-flattened into dicts. Works today; no
  schema guard against future drift. **Deferred**: this needs a deliberate `/api/v1/chat` SSE-payload
  refactor (risk of behavior changes to a widely-used streaming endpoint) rather than a quick fix — left
  for a dedicated follow-up.

## Verified, not gaps (no action needed)
- Session update method: `PATCH /api/v1/sessions/{id}` matches on both backend and all 4 frontend call sites.
- `/api/v1/preview`, `/api/v1/figures/{name}`, `/api/v1/documents/{id}/raw` are used via `<img src>`, not
  `fetch()` — present, just invisible to a fetch-only grep.
- `/api/v1/graph/extract`, `/api/v1/compact` are correctly internal-only (not meant to be UI-exposed).
