# Tasks & Investigation: Resolving False Relevance Cutoff Refusal (Threshold: 0.15)

## Problem Statement
Users asking natural questions (e.g., *"tell me about the document"*, *"summarize this document"*, *"what is this file about"*) or querying session-scoped workspaces receive the default refusal error:
> *"I could not locate sufficiently relevant information in the indexed documents to answer your question with confidence (relevance cutoff threshold: 0.15)."*

---

## Detailed Findings & Root Cause Analysis

### 1. Post-Retrieval vs Pre-Retrieval Filtering Gap (Critical)
- **Mechanism**: In `services/retrieval/service.py`, `qdrant.search(query, top_k=5)` and `bm25.search(query, top_k=5)` executed global searches without document filtering.
- **Failure Mode**: The top 5 global hits matched other documents in the database. Post-retrieval filtering (`[r for r in results if r.doc_id in doc_ids]`) pruned all 5 candidates, producing empty `[]` candidates (`0 dense, 0 sparse -> 0 reranked`).
- **Impact**: Any workspace with attached documents failed retrieval 100% of the time if the target document was not in the top 5 global search results.

### 2. Cross-Encoder Under-Scoring on Exploratory/Summary Queries (Critical)
- **Mechanism**: FlashRank uses `ms-marco-TinyBERT-L-2-v2`, trained exclusively on MS-MARCO factoid QA pairs.
- **Failure Mode**:
  - On factoid queries (e.g. *"what is the account balance?"*): score = `0.9967`.
  - On exploratory queries (e.g. *"tell me about the document"*, *"summarize"*): cross-encoder logit is heavily negative, producing sigmoid scores like `0.000012` ($1.2 \times 10^{-5}$).
  - `round(score, 4)` becomes `0.0000`, which falls far below the `0.15` cutoff threshold, causing false refusal even when chunks from the correct document are retrieved.

### 3. RRF Score Normalization Scale Incompatibility (Bug)
- **Mechanism**: Reciprocal Rank Fusion computes $\sum \frac{1}{60 + \text{rank}}$.
- **Failure Mode**: Max possible score with dense + sparse at rank 1 is $\frac{1}{61} + \frac{1}{61} \approx 0.0328$. When fallback ranking or un-reranked candidates were evaluated, `top_score` was capped at $0.0328 \ll 0.15$, guaranteeing 100% refusal.

### 4. Lack of Executive Summary / Document Overview Intent Handling
- **Mechanism**: No intent detection or document overview routing existed for generic queries like *"tell me about the document"*.
- **Failure Mode**: BM25 searches for literal word *"document"* (which may not appear in a passbook, invoice, or resume), and dense search yields generic vectors that fail the strict cross-encoder threshold.

---

## Implementation Plan & Tasks

- [x] **Task 1: Pre-Filtering in Qdrant and BM25 Stores**
  - [x] Add `doc_ids: list[str] | None` filter to `QdrantStore.search()` using Qdrant's native payload filter (`FieldCondition` / `MatchAny`).
  - [x] Add `doc_ids: list[str] | None` pre-filter to `BM25Store.search()`.
  - [x] Update `RetrievalService.retrieve()` to pass `doc_ids` directly into both search engines instead of post-filtering after a small `top_k`.

- [x] **Task 2: RRF Score Normalization**
  - [x] Normalize `rrf_score` to $[0.0, 1.0]$ in `services/retrieval/rrf.py` ($RRF / \frac{2}{k+1}$).
  - [x] Ensure fallback ranking retains confidence scores proportional to retrieval ranks.

- [x] **Task 3: Exploratory/Summary Query Intent Detection & Hybrid Score Calibration**
  - [x] In `FlashRankReranker`, blend or calibrate scores when dense vector cosine similarity / semantic overlap is high or when query is exploratory/summary (`tell me about`, `summarize`, `what is this`, `overview`).
  - [x] In `RetrievalService`, if a query is exploratory and scoped to document(s), include initial document chunks (Page 1 / Executive summary chunks) to guarantee grounded answering.

- [x] **Task 4: Adaptive Refusal Guardrails in Gateway and CRAG**
  - [x] Update `CRAGEvaluator` to recognize scoped document queries and exploratory intents so it does not falsely trigger `REFUSE`.
  - [x] Ensure `api.py` respects adaptive score thresholds and returns helpful answers instead of premature refusals.

- [x] **Task 5: Verification & End-to-End Testing**
  - [x] Unit test: Verify scoped document search retrieves chunks from target doc even if other documents exist.
  - [x] Unit test: Verify *"tell me about the document"* succeeds without refusal on session-scoped documents (`test_exploratory_and_scoped_retrieval.py` passed).
  - [x] Integration test: Execute chat endpoint with test session and verify grounded stream completion with zero 0.15 refusal errors (Verified live with Ollama + `sess_758f74fb2179`).
  - [x] Linting & regression: `python -m ruff check .` and `pytest tests/unit/` (89/89 passed).

---

## Parked User Requests (Backlog)

*The following items are requested by the user and parked here until active tasks are marked complete:*

- [ ] **Task P1: Workspace-Scoped Observability Diagnostics & Live Telemetry Feed**
  - **Context**: User reported: *"check the observability section for each workspace. seems dead."*
  - **Issue Identified**: In `services/telemetry/tracker.py`, telemetry was stored purely in a transient in-memory ring buffer that was wiped on container restart, causing newly opened sessions or restarted gateways to display 0 metrics.
  - **Work Completed**: Added dual in-memory and Redis persistence (`rag:telemetry:history` and `rag:telemetry:session:{session_id}`) with fallback hydration in `get_system_metrics()`.
  - **Remaining / Parked Items**:
    - [ ] Add active SSE streaming push or 5-second polling on the Observability page (`#page-observability`) to update waterfall latency gauges in real-time as queries arrive.
    - [ ] Display an explicit "No queries executed yet for this workspace" placeholder card in `#obs-telemetry-empty` when a session has zero turns, with a quick-link button to open the workspace in Chat.
    - [ ] Pre-populate initial synthetic telemetry upon workspace creation so the waterfall and gauges never render completely blank/zeroed.

- [ ] **Task P2: Real-Time Hardware GPU Telemetry Stream**
  - **Context**: User asked: *"is the vram correctly showing the details? query the live hardware vram"*
  - **Work Completed**: Added `GET /api/v1/hardware/gpu` endpoint querying active model allocations from Ollama (`/api/ps`) with fallback to physical GPU memory via `nvidia-smi`.
  - **Remaining / Parked Items**:
    - [ ] Wire a recurring 5-second polling interval in `ui/index.html` calling `/api/v1/hardware/gpu` to dynamically reflect physical GPU memory allocations alongside the static model profile.
    - [ ] Add a visual breakdown tooltip showing OS + framework VRAM vs. active model weights.

