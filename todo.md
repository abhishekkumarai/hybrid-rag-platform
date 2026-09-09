# Implementation Todo & Execution Roadmap (SOA + Langflow)

**Project**: Modern 100% Open-Source Hybrid RAG Platform (SOA + Langflow)  
**Target Hardware**: NVIDIA RTX 3050 6GB VRAM + 16GB System RAM  
**Reference Specs**: [architecture_plan.md](file:///C:/Users/abhi3/Documents/work/rag/architecture_plan.md) · [claude_prompt.md](file:///C:/Users/abhi3/Documents/work/rag/claude_prompt.md)

---

## Token-Aware Engineering Principles

To ensure zero token truncation and maximum reliability when executed by AI coding agents, this roadmap is governed by two strict token budgets:

### 1. Agent Execution Token Budget (Context & Output Safeguards)
- **Atomic Deliverables**: Each subtask is bounded to **1–2 files ($\le 150$ lines each)**. No massive, multi-file code dumps in a single turn.
- **Immediate Micro-Verification**: Every step is verified with an isolated unit test (`pytest tests/unit/test_XYZ.py`) before proceeding to keep context windows clean.
- **Zero Omitted Code**: Prevents agents from producing truncated placeholders (`# ... rest of logic`).

### 2. Runtime Inference Token Budget (Ollama 8K Context Window)
- **Top-6 Retrieved Context**: $6 \text{ chunks} \times 512 \text{ tokens max} = \mathbf{3,072 \text{ tokens}}$.
- **System Prompt & Citations**: $\mathbf{400 \text{ tokens}}$.
- **User Query & Chat Context**: $\mathbf{500 \text{ tokens}}$.
- **Generated Answer Budget**: $\mathbf{1,000 \text{ tokens}}$.
- **Total Prompt Envelope**: $\mathbf{\sim 4,972 \text{ tokens}}$ (Leaving $>3,200$ tokens safety headroom in Ollama to prevent VRAM spills).

---

## Phase Breakdown & Milestone Schedule

| Phase | Milestone | Focus Area | Micro-Tasks | Estimated Scope | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Phase 0** | **M0** | Scaffolding, Contracts, Logging & Infra | 0.1 – 0.5 | 5 files, ~300 lines | ✅ Completed |
| **Phase 1** | **M1** | Ingestion & Layout Probing Service | 1.1 – 1.4 | 5 files, ~350 lines | ✅ Completed |
| **Phase 2** | **M2** | Chunking & Dual Indexing Service | 2.1 – 2.4 | 4 files, ~320 lines | ✅ Completed |
| **Phase 3** | **M3** | Hybrid Retrieval & Cross-Encoder Rerank | 3.1 – 3.4 | 4 files, ~300 lines | ✅ Completed |
| **Phase 4** | **M4** | Langflow Custom Components & Flows | 4.1 – 4.4 | 5 files, ~350 lines | ✅ Completed |
| **Phase 5** | **M5** | Task Scheduling & Directory Reconciler | 5.1 – 5.3 | 3 files, ~250 lines | ✅ Completed |
| **Phase 6** | **M6** | End-to-End Verification & Benchmarks | 6.1 – 6.3 | 3 files, ~200 lines | ✅ Completed |
| **Phase 7** | **M7** | Unified SOA Gateway, Interactive UI & Eval | 7.1 – 7.4 | 4 files, ~350 lines | ✅ Completed |
| **Phase 8** | **M8** | Asynchronous Redis Worker & Fault-Tolerant DLQ | 8.1 – 8.4 | 4 files, ~350 lines | ✅ Completed |
| **Phase 9** | **M9** | Visual Provenance Highlighting & CI Regression Gate | 9.1 – 9.4 | 4 files, ~350 lines | ✅ Completed |
| **Phase 10** | **M10** | Conversational Multi-Turn Memory & Sliding Window | 10.1 – 10.4 | 4 files, ~300 lines | ✅ Completed |
| **Phase 11** | **M11** | Deep Multimodal Ingestion (Tables & Figure Crops) | 11.1 – 11.4 | 4 files, ~350 lines | ✅ Completed |
| **Phase 12** | **M12** | Agentic Multi-Hop Retrieval & Corrective RAG (CRAG) | 12.1 – 12.4 | 5 files, ~400 lines | ✅ Completed |
| **Phase 13** | **M13** | Graph-Augmented RAG (GraphRAG & Knowledge Graph) | 13.1 – 13.4 | 4 files, ~450 lines | ✅ Completed |
| **Phase 14** | **M14** | Contextual Compression & Adaptive Token Compactor | 14.1 – 14.4 | 3 files, ~350 lines | ✅ Completed |
| **Phase 15** | **M15** | Continuous Evaluation & Active Learning (RAGOps) | 15.1 – 15.4 | 3 files, ~300 lines | ✅ Completed |
| **Phase 16** | **M16** | Session-Scoped Workspaces (Files, Prompt, Parameters) | 16.1 – 16.5 | 5 files, ~400 lines | 📋 Planned |
| **Phase 17** | **M17** | Stitch UI Redesign — "Retrieval Intelligence Workbench" (Light Theme) | 17.1 – 17.8 | 8 Stitch screens | ✅ Generation Complete (8/8) — not yet wired into `ui/index.html` |

---

## Phase 0: Scaffolding, Shared Contracts, Logging & Infra (Milestone 0)
*Target: Logging engine, Pydantic contracts, dependencies, config loader, and service containers.*

- [x] **Task 0.1: Centralized Structured Logging Engine (`services/common/logger.py`)**
  - [x] Implement colorized console logging + rotating file logger (`logs/rag_system.log`).
  - [x] Support contextual metadata (`service`, `doc_id`, `duration_ms`).
  - [x] *Verification*: Run `tests/unit/test_logger.py` asserting file output and structured formatting.

- [x] **Task 0.2: Shared Pydantic Data Contracts (`contracts/`)**
  - [x] Implement `contracts/document.py` (`Block`, `DocumentProfile`, `IngestRequest`, `IngestResponse`).
  - [x] Implement `contracts/chunk.py` (`Chunk`, `IndexRequest`, `IndexResponse`).
  - [x] Implement `contracts/retrieval.py` (`SearchQuery`, `Candidate`, `RetrieveResponse`).
  - [x] *Verification*: Run `tests/unit/test_contracts.py` asserting schema serialization and validation.

- [x] **Task 0.3: Dependency Specification (`pyproject.toml`)**
  - [x] Create `pyproject.toml` with `uv` configuration pinning: `langflow>=1.0.0`, `pydantic-settings`, `qdrant-client`, `bm25s`, `flashrank`, `docling`, `pymupdf`, `redis`, `psycopg[binary]`, `pytest`, `ruff`.
  - [x] *Verification*: Run `uv pip compile pyproject.toml` or `uv sync --check` verifying resolution.

- [x] **Task 0.4: Centralized YAML Configuration Loader (`services/common/config.py`)**
  - [x] Implement Pydantic settings loading `configs/default.yaml` with profile overlays (`quality.yaml`, `fast.yaml`).
  - [x] Set `quality` as default with `llama3.1:8b` + `bge-m3`, and `fast` with `llama3.2:3b`.
  - [x] *Verification*: Run `tests/unit/test_config.py` asserting profile resolution.

- [x] **Task 0.5: Infrastructure Orchestration (`docker-compose.yml` & `Makefile`)**
  - [x] Create `docker-compose.yml` defining `qdrant` (port 6333) and `redis` (port 6379) with healthchecks.
  - [x] Create root `Makefile` with targets: `setup`, `run`, `scheduler`, `test`, `check`, `clean`.
  - [x] *Verification*: `make check` executes `ruff` and unit tests cleanly.

---

## Phase 1: Ingestion & Layout Probing Service (Milestone 1)
*Target: Intelligent document probing and multi-parser extraction with page/bbox provenance.*

- [x] **Task 1.1: 8-Page Layout Heuristic Prober (`services/ingestion/probe.py`)**
  - [x] Sample up to 8 pages using PyMuPDF (first, last, and up to 6 interior pages).
  - [x] Compute text coverage ratio ($< 0.6 \implies \text{OCR}$), column gutter histogram ($18\text{pt}$), and vector line density.
  - [x] *Verification*: Unit tests asserting sampling touches $\le 8$ pages on a 100-page document.

- [x] **Task 1.2: Specialized Parsers (`services/ingestion/parsers/`)**
  - [x] `fast_text.py`: PyMuPDF extractor with bounding box normalization.
  - [x] `layout.py`: Docling extractor for complex multi-column and tabular layouts.
  - [x] `ocr.py`: RapidOCR extractor for scanned pages.
  - [x] *Verification*: Isolated parser tests producing valid `Block` objects.

- [x] **Task 1.3: Ingestion Service API (`services/ingestion/service.py`)**
  - [x] Assemble `IngestionService.parse(request: IngestRequest) -> IngestResponse`.
  - [x] Add structured logging: `[IngestionService] Routed {doc_id} to {route} reason={reason}`.
  - [x] *Verification*: Synthetic test fixtures (single-column, 2-column table, scanned).

---

## Phase 2: Chunking & Dual Indexing Service (Milestone 2)
*Target: Content-aware hierarchy preservation, token capping, and dual storage.*

- [x] **Task 2.1: Content-Aware Chunker (`services/indexing/chunker.py`)**
  - [x] Table windowing: Serialize markdown tables intact with header replication.
  - [x] Heading hierarchy: Prepend parent section breadcrumbs (`# Section > ## Subsection`).
  - [x] Recursive token cap fallback: Split large sections at 512 tokens max.
  - [x] *Verification*: Assert no chunk exceeds 512 tokens and tables remain intact.

- [x] **Task 2.2: Qdrant Dense Store (`services/indexing/qdrant_store.py`)**
  - [x] Initialize Qdrant collection with cosine distance and HNSW index.
  - [x] Dense vector generation via Ollama `bge-m3` or local embeddings.
  - [x] *Verification*: Store and retrieve test vectors from Qdrant.

- [x] **Task 2.3: BM25s Sparse Store (`services/indexing/bm25_store.py`)**
  - [x] Index chunks using `bm25s` with BM25-Okapi scoring and disk persistence (`data/indices/bm25/`).
  - [x] *Verification*: Keyword lookup asserting exact token matching.

- [x] **Task 2.4: Indexing Service API (`services/indexing/service.py`)**
  - [x] Assemble `IndexingService.index(request: IndexRequest) -> IndexResponse`.
  - [x] *Verification*: End-to-end indexing of test blocks.

---

## Phase 3: Hybrid Retrieval & Cross-Encoder Rerank Service (Milestone 3)
*Target: Parallel dense+sparse retrieval, RRF fusion, and local cross-encoder cutoff.*

- [x] **Task 3.1: Custom Reciprocal Rank Fusion (`services/retrieval/rrf.py`)**
  - [x] Parallel query to Qdrant (top 20) and BM25s (top 20).
  - [x] Compute RRF score: $RRF(d) = \sum \frac{1}{60 + \text{rank}(d)}$.
  - [x] *Verification*: Unit test verifying candidate fusion and deterministic ordering.

- [x] **Task 3.2: FlashRank Cross-Encoder Reranker (`services/retrieval/reranker.py`)**
  - [x] Local CPU reranking via FlashRank ONNX runtime.
  - [x] Refusal cutoff: If top score $< 0.15$, trigger confident refusal.
  - [x] *Verification*: Assert irrelevant candidates score $< 0.15$ and trigger refusal flag.

- [x] **Task 3.3: Retrieval Service API (`services/retrieval/service.py`)**
  - [x] Assemble `RetrievalService.retrieve(request: SearchQuery) -> RetrieveResponse`.
  - [x] *Verification*: Full query test returning top-6 reranked passages with citation metadata.

---

## Phase 4: Langflow Custom Components & Flows (Milestone 4)
*Target: Visual composition, Chat Playground file uploads, and Ollama streaming.*

- [x] **Task 4.1: Custom Langflow Components (`components/`)**
  - [x] `components/layout_probe.py`: Wraps `IngestionService`.
  - [x] `components/chunker.py`: Wraps `IndexingService`.
  - [x] `components/hybrid_retriever.py`: Wraps `RetrievalService`.
  - [x] `components/citation_formatter.py`: Appends `[Doc: Page: BBox]` badges.
  - [x] *Verification*: Import test verifying Langflow component schema compliance.

- [x] **Task 4.2: Flow Export Template (`flows/hybrid_rag_flow.json`)**
  - [x] Create pre-configured flow connecting Chat Input (file upload enabled) $\to$ Ingestion $\to$ Chunker $\to$ Retriever $\to$ Ollama LLM $\to$ Chat Output with citations.
  - [x] *Verification*: Validate JSON structure against Langflow schema.

- [x] **Task 4.3: PostgreSQL & Langflow Launch Configuration**
  - [x] Configure `LANGFLOW_DATABASE_URL` connecting to `localhost:5432`.
  - [x] Configure `LANGFLOW_COMPONENTS_PATH=./components`.
  - [x] *Verification*: Verify `langflow run --port 7860` starts cleanly.

---

## Phase 5: Task Scheduling & Directory Reconciler Service (Milestone 5)
*Target: Automated folder watching, SHA-256 deduplication, and Webhook dispatch.*

- [x] **Task 5.1: Directory Reconciler Daemon (`services/scheduler/reconciler.py`)**
  - [x] Scan `data/documents/` on interval (60s).
  - [x] Compute SHA-256 hash and maintain seen file registry.
  - [x] *Verification*: Unit test asserting duplicate files are ignored and new files detected.

- [x] **Task 5.2: Webhook & Redis Queue Dispatcher (`services/scheduler/dispatcher.py`)**
  - [x] Dispatch unindexed documents to Langflow's Webhook endpoint (`/api/v1/webhook/{flow_id}`).
  - [x] Optional Redis queue fallback with 3-retry dead-letter queue (DLQ).
  - [x] *Verification*: Mock webhook assertion on file creation.

---

## Phase 6: End-to-End Verification & Benchmarking (Milestone 6)
*Target: Production readiness, playground verification, and ablation testing.*

- [x] **Task 6.1: End-to-End Test Suite (`tests/integration/test_pipeline.py`)**
  - [x] Ingest PDF $\to$ index $\to$ retrieve $\to$ rerank $\to$ verify citations.
- [x] **Task 6.2: Ablation Runner (`tests/eval/ablation.py`)**
  - [x] Compare Dense-only vs. Sparse-only vs. Hybrid RRF vs. Hybrid + Reranker.
- [x] **Task 6.3: Walkthrough & Operational Guide (`docs/walkthrough.md`)**
  - [x] Document running the system, importing the flow, uploading documents via Chat Playground, and monitoring logs.

---

## Phase 7: Unified SOA Microservice Gateway & Evaluation Harness (Milestone 7)
*Target: Production REST & SSE streaming gateway, live interactive UI, and evaluation harness.*

- [x] **Task 7.1: Unified SOA HTTP REST & SSE Gateway (`services/gateway/api.py`)**
  - [x] Implement FastAPI gateway exposing `/api/v1/health`, `/api/v1/ingest`, `/api/v1/index`, `/api/v1/retrieve`, `/api/v1/chat` (streaming SSE).
  - [x] Support multipart PDF upload directly from web clients with automated layout probing.
  - [x] *Verification*: Run `pytest tests/unit/test_gateway.py` asserting all endpoints respond correctly.

- [x] **Task 7.2: Offline Evaluation & Faithfulness Harness (`tests/eval/eval_harness.py`)**
  - [x] Build automated RAG evaluator measuring retrieval hit-rate, MRR, answer faithfulness, and citation provenance validity.
  - [x] Generate JSON benchmark report (`eval_report.json`).
  - [x] *Verification*: Run `python tests/eval/eval_harness.py` asserting scores against ground truth pairs.

- [x] **Task 7.3: Interactive Web Client & Citation Inspector (`ui/index.html`)**
  - [x] Modern, single-file responsive UI matching design standards: drag-and-drop file upload, real-time SSE token streaming, and clickable citation provenance badges.
  - [x] Mount statically in Gateway under `/`.
  - [x] *Verification*: Verify UI serves cleanly and connects to API endpoints.

- [x] **Task 7.4: Integration & Gateway Verification**
  - [x] Run full test suite with gateway tests (28 passed).
  - [x] Update Makefile with `make serve` and `make eval` targets.

---

## Phase 8: Asynchronous Redis Task Queue, Worker Pool & Fault-Tolerant DLQ (Milestone 8)
*Target: Decoupled asynchronous background processing, atomic task popping, heartbeats, and DLQ management.*

- [x] **Task 8.1: Redis Ingestion Task Queue (`services/scheduler/queue.py`)**
  - [x] Implement atomic enqueue and task deduplication (`rag:queue:pending`, `rag:tasks:seen:{hash}`).
  - [x] Support job payload contract (`task_id`, `file_path`, `file_hash`, `attempts`, `max_retries`).
  - [x] *Verification*: Run unit test verifying enqueue and duplicate rejection.

- [x] **Task 8.2: Resilient Asynchronous Worker Daemon (`services/scheduler/worker.py`)**
  - [x] Implement worker loop using `BLMOVE` / `BRPOPLPUSH` from `rag:queue:pending` into `rag:queue:processing`.
  - [x] Maintain worker heartbeats in Redis (`rag:workers:{worker_id}` with TTL=10s).
  - [x] Execute document probing, parsing, and dual indexing with exponential backoff on retry.
  - [x] Route failed tasks after 3 attempts to Dead-Letter Queue (`rag:queue:dlq`).
  - [x] *Verification*: Run worker unit test asserting task completion and DLQ routing on errors.

- [x] **Task 8.3: Dead-Letter Queue (DLQ) Inspector & Management (`services/scheduler/dlq_manager.py`)**
  - [x] Implement inspection, replay/retry, and purge for `rag:queue:dlq`.
  - [x] Expose DLQ stats and replay endpoints in Gateway (`/api/v1/queue/stats`, `/api/v1/queue/dlq`, `/api/v1/queue/dlq/replay`).
  - [x] *Verification*: Test replay moving item from DLQ back to pending queue.

- [x] **Task 8.4: Queue & Worker Verification & Test Suite (`tests/unit/test_queue_worker.py`)**
  - [x] End-to-end queue worker test verifying happy path and failure path (33 passed).
  - [x] Add `worker` target to `Makefile`, `run.ps1`, and `make.bat`.

---

## Phase 9: Visual PDF Provenance Highlighting & CI Regression Gate (Milestone 9)
*Target: Visual page snapshot rendering with bounding box highlight overlays and CI regression threshold gate.*

- [x] **Task 9.1: Visual Page Provenance Renderer (`services/ingestion/visualizer.py`)**
  - [x] Render PDF pages directly to PNG images with highlighted translucent bounding box overlays (`[x0, y0, x1, y1]`).
  - [x] Expose `GET /api/v1/preview` endpoint in FastAPI Gateway returning `image/png`.
  - [x] *Verification*: Unit test verifying rendered PNG binary output and coordinates.

- [x] **Task 9.2: Interactive Visual Provenance Inspector in Web Console (`ui/index.html`)**
  - [x] Add visual modal popover showing the highlighted PDF page snapshot when a citation badge is clicked.
  - [x] *Verification*: Verify UI popover links to `/api/v1/preview`.

- [x] **Task 9.3: Automated CI Regression Gate (`tests/eval/regression_gate.py`)**
  - [x] Implement hard regression gates asserting HitRate@1 $\ge 0.85$, MRR $\ge 0.90$, and Faithfulness $\ge 0.90$.
  - [x] Emit pass/fail status and exit code for CI/CD pipelines.
  - [x] *Verification*: Run regression gate script asserting 100% compliance.

- [x] **Task 9.4: Full Test Suite & Verification (`tests/unit/test_visualizer.py`)**
  - [x] Run complete test suite (37 passed) and update Makefile and task runners with `make gate`.

---

## Phase 16: Session-Scoped Workspaces, Document Isolation & Runtime Customization (Milestone 16)
*Target: Each chat opens in an isolated session with a dedicated session ID, scoped files/documents, customizable system prompt, and runtime parameters.*

- [ ] **Task 16.1: Extended Session Pydantic Contracts (`contracts/session.py`)**
  - [ ] Add `SessionParameters` model containing:
    - `model: str = "llama3.2:3b"`
    - `temperature: float = 0.7`
    - `retrieval_mode: Literal["auto", "agentic", "graph", "direct"] = "auto"`
    - `top_k: int = 6`
    - `min_score_threshold: float = 0.15`
    - `compactor_budget: int = 3072`
  - [ ] Extend `ChatSession` model to include:
    - `files: list[str] = Field(default_factory=list)` (attached document IDs / file names scoped to this session)
    - `system_prompt: str | None = None` (custom session persona / instructions overriding default system prompt)
    - `parameters: SessionParameters = Field(default_factory=SessionParameters)`
  - [ ] Implement `UpdateSessionRequest` model for updating session title, system prompt, parameters, and scoped files.
  - [ ] *Verification*: Unit tests asserting validation, default serialization, and backward compatibility.

- [ ] **Task 16.2: Session-Scoped Storage & Document Filtering (`services/session/manager.py`)**
  - [ ] Update Redis schema and in-memory fallback to persist session `files`, `system_prompt`, and `parameters`.
  - [ ] Implement session file attachment & detachment methods (`attach_files(session_id, files)`, `detach_file(session_id, file_id)`).
  - [ ] Implement `update_session(session_id, update_data)` to mutate session prompt, parameters, and metadata.
  - [ ] Expose helper to retrieve session-scoped Qdrant filter condition (`doc_id in session.files` if session has scoped files).
  - [ ] *Verification*: Run `tests/unit/test_session_manager.py` verifying file scoping and parameter persistence.

- [ ] **Task 16.3: Gateway Integration & Auto-Session Enforcement (`services/gateway/api.py`)**
  - [ ] Enforce session ID on every chat: If `/api/v1/chat` request omits `session_id` or session does not exist, automatically instantiate a new `ChatSession` with unique `session_id` and return it in headers/streaming metadata.
  - [ ] Inject session-specific `system_prompt` into Ollama generation prompt if defined (fallback to default system prompt).
  - [ ] Apply session-specific `parameters` (temperature, model, retrieval mode, compactor budget) during chat execution.
  - [ ] Add REST endpoints:
    - `PATCH /api/v1/sessions/{session_id}`: Update session title, system prompt, and parameters.
    - `POST /api/v1/sessions/{session_id}/files`: Attach uploaded/indexed documents to the session.
    - `DELETE /api/v1/sessions/{session_id}/files/{doc_id}`: Detach document from the session.
  - [ ] Pass session document filter into `RetrievalService` / `AgenticCoordinator` to constrain candidate search to session-scoped files.
  - [ ] *Verification*: Test gateway endpoints with curl / pytest asserting session parameter and document isolation.

- [ ] **Task 16.4: Interactive Session Workspace & Configuration UI (`ui/index.html`)**
  - [ ] Auto-open chat in session: Ensure client always creates or binds to a `currentSessionId` upon initial load.
  - [ ] Add Session Settings Modal / Drawer:
    - Custom System Prompt editor (textarea with prompt templates: e.g. "Financial Analyst", "Code Auditor", "General Assistant").
    - Parameter controls: Temperature slider (`0.0` – `1.0`), Model selector, Strategy mode selector, Token compactor budget.
    - Scoped Files Checklist: Toggle which indexed documents are active/attached to the current session.
  - [ ] Display active session badge and file count chips in the chat header.
  - [ ] Instant reactivity: Switching sessions automatically swaps active files, system prompt, and message history.
  - [ ] *Verification*: Verify in browser that new sessions persist distinct prompts, parameters, and file attachments.

- [ ] **Task 16.5: End-to-End Multi-Session Isolation Test Suite (`tests/unit/test_session_scoped_workspace.py`)**
  - [ ] Verify that Session A scoped to Document 1 cannot retrieve chunks from Document 2.
  - [ ] Verify that Session A with custom system prompt generates output adhering to its custom persona.
  - [ ] Verify that Session B maintains independent temperature, model, and message history without cross-session contamination.
  - [ ] Ensure 100% test pass rate across test suite.

---

## Phase 17: Stitch UI Redesign — "Retrieval Intelligence Workbench" (Milestone 17)
*Target: A second, distinct Stitch project — a light off-white "Warm Ink & Ember" theme (Material 3 + fluid
motion), replacing the earlier dark "Obsidian Zinc Craft" design referenced in `plan.md` / Phase 16 of
`wip.md`. New Stitch project id `10226929593327386385`
([https://stitch.withgoogle.com/project/10226929593327386385](https://stitch.withgoogle.com/project/10226929593327386385)),
design system asset `assets/16587086430143241056` ("Warm Ink & Ember"). 8 screens total, left nav rail +
hidden-by-default right inspector, NotebookLM-style per-session Sources panel, context-aware Library scope
switcher. See this session's conversation log for the full per-screen prompt text used.*

- [x] **Task 17.1: Stitch project + design system setup**
  - [x] `create_project` → "Retrieval Intelligence Workbench".
  - [x] `create_design_system` + `update_design_system` → "Warm Ink & Ember" (light, off-white `#FAF9F5`,
    Ember `#C2410C` / Moss `#4B6B4F` / Clay `#B08947`, Inter + JetBrains Mono, `ROUND_EIGHT`).

- [x] **Task 17.2: Workspace Gallery screen** — generated successfully.
- [x] **Task 17.3: Chat screen** — generated successfully (Sources sub-panel, citation badges, low-confidence
  refusal callout, hidden-by-default right inspector).
- [x] **Task 17.4: Library screen** — generated and content-verified (scope switcher, ingestion stepper,
  monospace document table all present in the rendered HTML).
- [x] **Task 17.5: Knowledge Graph screen** — generated and content-verified (entities/relations/traversal
  present).
- [x] **Task 17.6: Observability screen** — generated and content-verified (uptime/latency/Redis/Qdrant/Dead
  Letter panel present).
- [x] **Task 17.7: RAGOps screen** — generated and content-verified (satisfaction/hard-negative/JSONL export
  present).
- [x] **Task 17.8: Models & Tuning + Settings screens** — both generated and content-verified (VRAM/model-slot
  language present in Models & Tuning; Appearance/API/Danger Zone present in Settings).

All 8 target screens confirmed present via `list_screens` + spot-checked by downloading each screen's HTML
and grepping for screen-specific content (not just relying on the title field) — done 2026-09-09.

- [ ] **Cleanup: remove stray duplicate screens** — the unstable generation window (see blocker below)
  produced extra duplicate renders: 2× "Workspace Gallery", ~3× "Chat"/"Workspace Chat", 2× "Library" (one
  early "Workspace Gallery" duplicate has no screenshot and is the clearest one to remove; the rest are
  valid duplicate generations, keep whichever renders best). No `delete_screen` tool is available via MCP —
  do this by hand in the Stitch UI: [https://stitch.withgoogle.com/project/10226929593327386385](https://stitch.withgoogle.com/project/10226929593327386385).
- [ ] **Follow-up: wire the approved Stitch designs into `ui/index.html`** — this phase only covers design
  generation in Stitch; translating the approved screens into the actual single-file frontend (per
  `CLAUDE.md`'s "web client is a single hand-written file, no build step" constraint) is separate work, not
  started.

**Blocker hit 2026-09-09 (resolved)**: `generate_screen_from_text` became unreliable partway through this
batch — repeated client-side timeouts, one explicit `"The service is currently unavailable"` error (which
also briefly affected `list_screens`), and no new screens landing even after ~15+ cumulative minutes of
polling across multiple attempts (both serial and batched). On retry, waiting patiently after each
individual (non-batched) submission worked: all 6 remaining screens eventually landed together after one
more `list_screens` poll. Confirmed lesson for next time: a timeout from this tool means "check back later,"
not "failed" — and batching multiple `generate_screen_from_text` calls back-to-back is what produced most of
the stray duplicates above, so keep resubmissions strictly one-at-a-time.

---

## Phase 18: Wire "Retrieval Intelligence Workbench" Designs into `ui/index.html` (Milestone 18)
*Target: Replace the current dark "Obsidian Zinc Craft" single-page chat UI with the approved light "Warm Ink
& Ember" design from Stitch project `10226929593327386385`, ported into the same single hand-written file
(no build step, per `CLAUDE.md`) with real backend wiring — not static Stitch mockup content. Existing file
is ~3,300 lines; this is effectively a full frontend rewrite, done incrementally per screen so it can be
reviewed/tested in slices rather than as one giant unreviewable diff. Built 2026-09-09 on isolated branch
`worktree-workbench-frontend` (commit `5ab2d0f`) — **not yet merged into the main checkout**, see blocker
note at the end of this phase.*

- [x] **Task 18.1: Foundation — design tokens, app shell, router**
  - [x] Ported the exact "Warm Ink & Ember" Tailwind tokens Stitch itself resolved (`primary #8b4f3b`,
    `background #faf9f5`, full Material 3 tonal set, Inter/Public Sans/JetBrains Mono) as the Tailwind CDN
    config, replacing the old Zinc/Obsidian dark tokens.
  - [x] Built the persistent shell: left nav rail (icon+label, collapsible via `#collapseBtn`), top bar
    (breadcrumb + system-health pill), a `#pageHost` view-swap region, and a `#inspector` right panel
    (hidden by default, slide-in via citation click).
  - [x] Implemented a hash-based client-side router (`navigate()`) switching between 8 `<section>` page
    blocks with no full reload, in one file — no build step introduced.
  - [x] *Verification*: extracted the inline `<script>` and ran `node --check` — syntax valid. Tag-balance
    checked (`<section>`/`<aside>`/`<div>` counts match). **Not yet smoke-tested in an actual browser against
    a running gateway** — see deployment blocker below.

- [x] **Task 18.2: Workspace Gallery page** — grid of session cards (title, model badge, retrieval-mode
  badge, doc count, message count) wired to `GET /api/v1/sessions`; "New Workspace" wired to
  `POST /api/v1/sessions`; card click opens the Chat page for that `session_id`. (Preset quick-start buttons
  from the original design brief not yet added — plain title-only creation for now.)
- [x] **Task 18.3: Chat page** — Sources sub-panel (session-scoped `files`, attach via a picker, remove via
  `DELETE /api/v1/sessions/{id}/files/{doc_id}`), message thread + SSE streaming against `POST /api/v1/chat`
  (ported from the prior implementation: markdown rendering, citation badges, refusal callout, per-message
  thumbs feedback via `POST /api/v1/feedback`), citation click opens the right inspector via
  `/api/v1/preview`. (Retrieval-trace and context-budget inspector tabs from the original design brief not
  yet added — inspector currently shows the Source tab only.)
- [x] **Task 18.4: Library page** — "This workspace / All documents" scope switcher (filters against the
  open session's `files`), upload dropzone wired to `POST /api/v1/ingest` + `POST /api/v1/index`, document
  table wired to `GET /api/v1/documents` with an "Attach" action per row. (Live ingestion stepper animation
  from the original design brief not yet added — upload currently completes silently, then refreshes the
  table.)
- [ ] **Task 18.5: Knowledge Graph page** — still a styled placeholder. Needs: force-directed canvas, query
  bar, stat tiles; wire `POST /api/v1/graph/query`, `GET /api/v1/graph/stats`. (Canvas rendering: hand-rolled
  SVG/force layout, no new external library per the artifact/library constraints already in play.)
- [x] **Task 18.6: Observability page** — wired to `GET /api/v1/metrics` (avg retrieval/generation ms,
  tokens/sec, refusals, Qdrant points, BM25 chunks, queue depth, DLQ count) and `GET /api/v1/queue/dlq` with
  per-row and bulk `POST /api/v1/queue/dlq/replay`. Ported from the other session's in-progress dark-theme
  telemetry work (see Phase 18 note below). Browser-verified against live data (Qdrant points: 80, BM25
  chunks: 80, DLQ correctly empty).
- [x] **Task 18.7: RAGOps page** — wired to `GET /api/v1/feedback/summary` (total feedback, satisfaction
  rate, hard-negative count) and an export button hitting `GET /api/v1/ragops/dataset`. Browser-verified
  against live data (45 feedback records, 48.9% satisfaction, 21 hard negatives).
- [x] **Task 18.8: Models & Tuning page** — model dropdown wired to `GET /api/v1/models` + custom model tag
  input, retrieval-mode segmented control, top-k/rerank-depth sliders, SSE stream toggle — all feed shared
  state (`currentModel`/`currentRetrievalMode`/`currentTopK`/`currentTopRerank`/`streamEnabled`) that the
  Chat page's `POST /api/v1/chat` request now carries. Browser-verified: dropdown populates with the real
  active model. (VRAM budget meter and preset chips from the original design brief not yet added; range
  sliders/checkbox render with default browser styling, not Ember-accented — `accent-primary` Tailwind
  utility didn't visibly apply, needs a follow-up look.)
- [ ] **Task 18.9: Settings page** — still a styled placeholder. Needs: appearance/API/notifications/danger
  zone; appearance prefs to `localStorage` (no dedicated backend endpoint exists for this).
- [~] **Task 18.10: Cross-page QA & cleanup** — partially done: all 6 live pages were opened and exercised in
  an actual Chrome tab against a running `docker compose` stack (not just syntax-checked) — see verification
  log below. Still outstanding: responsive/mobile pass, removing the now-dead old dark-theme CSS/JS that's
  no longer reachable, updating `docs/frontend-guidelines.md` and `DESIGN.md`, fixing the slider/checkbox
  accent-color styling noted above.

**Source material**: the 8 approved Stitch screens (HTML+Tailwind, already generated and content-verified —
see Phase 17 above) were the visual reference for markup/layout per page. In practice, Tasks 18.6–18.8 ended
up sourcing their *functionality* from the other session's in-progress dark-theme rebuild instead (see below)
since it had already implemented working wiring for exactly these three pages — the Stitch HTML was still
used as the layout/styling reference, restyled into the light theme.

**Resolved: the other session's conflicting `ui/index.html` work (2026-09-09)**. The main checkout's
`ui/index.html` had 984 uncommitted lines from another active session implementing the *original* dark
"Obsidian Zinc Craft" plan (model selector dropdown, retrieval-mode segmented control, top-k/rerank tuning
popover, a tabbed Provenance/Graph/Telemetry inspector, hardware health pill) — real, working functionality,
not a stray edit. Per explicit user decision, that file was superseded rather than merged line-by-line:
1. The full dark-theme WIP file was preserved as `ui/dark_theme_wip_reference.html` before any overwrite, so
   nothing from that session's work is lost.
2. Its functional pieces (not its visual style) were re-implemented in the new light-theme Models & Tuning,
   Observability, and RAGOps pages (Tasks 18.6–18.8 above) — same endpoints, same state variables, restyled.
3. Only then was this branch's `ui/index.html` copied over the main checkout's, and the stack restarted
   (`docker-compose.yml` bind-mounts `./ui:/app/ui`, so the change is live immediately).
4. **A real bug was caught by browser-testing rather than assuming success**: the router toggled the HTML
   `hidden` *attribute*, but every non-Gallery page also shipped with Tailwind's `hidden` *class* baked into
   its initial markup — so every page except Gallery rendered permanently blank regardless of route. Fixed
   by switching the router to `classList.toggle('hidden', ...)`. Re-verified in-browser afterward: Chat now
   renders its Sources panel, real message history, and successfully sends/receives a live streamed message;
   Library, Observability, RAGOps, and Models & Tuning all render real backend data as described above.

Deployed and live at `http://localhost:8001/` as of 2026-09-09. Not yet done: Knowledge Graph (18.5) and
Settings (18.9) remain placeholders, and the polish/cleanup items under 18.10.
