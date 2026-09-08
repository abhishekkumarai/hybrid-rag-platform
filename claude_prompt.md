# Build Prompt — Modern 100% Open-Source Hybrid RAG Fullstack Platform (Django + Python)

> Paste this whole file into **Claude Code** (`claude`), **Gemini CLI** (`gemini`), or any agentic coding CLI as the opening instruction. It is written to be executed autonomously, milestone by milestone, with verifiable acceptance criteria at each step.

---

## 0. Role and operating rules

You are a senior ML platform and fullstack engineer. Build a **production-grade, 100% open-source, evaluation-driven hybrid RAG fullstack platform** using **Django 5.x** and Python, from scratch, in the current working directory.

Operating rules — follow these exactly:

1. **Work in milestones.** Complete Milestone N fully (code + tests passing + acceptance criteria met) before starting N+1. Print a short status line after each milestone.
2. **Never ask interactive questions mid-build.** Where a decision is ambiguous, pick the option marked *default* below, write your reasoning into `docs/DECISIONS.md`, and continue.
3. **100% Open-Source & Local-First by default.** The primary stack must run locally with zero cost and zero proprietary API lock-in (Ollama, BGE embeddings, Qdrant, Redis, FlashRank/BGE-Reranker, Docling). Cloud APIs (Claude, OpenAI, Cohere) are swap-in profile alternatives only.
4. **Target Hardware Alignment:** Optimize for the host environment (**NVIDIA RTX 3050 6GB VRAM + 16GB System RAM**). Enforce VRAM and memory budgets defined in §2.
5. **Frontend Rules Compliance:** All frontend interfaces must strictly obey the project design rules in `claude.md`: polished, intentional, restrained shadows, clean typography hierarchy, Lucide icons, responsive layout, no generic SaaS clutter, and interactive citation popovers.
6. **Every module ships with tests.** Unit tests must run offline with zero network calls and zero GPU (use fake/deterministic embedders, `fakeredis`, and a stub LLM). Integration tests are marked `@pytest.mark.integration` and skipped unless `RUN_INTEGRATION=1`.
7. **No secrets in code.** All keys and connection strings via env vars, loaded through `pydantic-settings` or `django-environ`. Ship `.env.example`.
8. **Everything is configurable from one place** — `configs/default.yaml` and profile overlays in `configs/profiles/`.
9. **Type hints everywhere.** `ruff` + `mypy --strict` on `apps/` must pass.
10. Prefer **composition over framework lock-in**: LangChain/LangGraph are used for orchestration, tracing, and eval glue — the retrieval math (BM25, RRF, fusion, reranking) is implemented in our own code so it is testable and swappable.
11. When you finish a milestone, run `make check` and fix anything red before moving on.

---

## 1. What you are building

A fullstack retrieval platform with these core capabilities:

- **Django 5.x Fullstack Architecture**: Unified application with Django ORM, Admin interface, and async views for Server-Sent Events (SSE) streaming.
- **Frontend UI (`claude.md` compliant)**:
  - **Conversational RAG Chat**: Real-time streaming answers with clickable inline `[Doc: Page: BBox]` citation badges that preview verified source text.
  - **Document Hub & Upload**: Drag-and-drop document upload with real-time route classification badges (`FAST`, `LAYOUT`, `OCR`).
  - **Queue & Recovery Dashboard**: Live Redis queue monitor, Dead-Letter Queue (DLQ) inspector, and one-click reconciliation trigger to pick up missed documents.
- **Layout-aware ingestion**: automatically *detects* whether a document needs layout-aware parsing (scanned pages, multi-column, tables, forms, figures) and routes it to the appropriate parser instead of parsing everything the expensive way.
- **Asynchronous Redis queue & missed document recovery**: decoupled ingestion queue with SHA-256 idempotency, worker heartbeats, DLQ, and an automatic reconciliation engine.
- **Dual chunking strategy**: **content-aware chunking** (structure- and meaning-preserving) as primary, with **recursive character chunking** as a guaranteed fallback and size enforcer.
- **Hybrid retrieval**: dense **HNSW** vector search + sparse **BM25** lexical search, run in parallel.
- **Fusion & Reranking**: **Reciprocal Rank Fusion (RRF)** followed by a cross-encoder reranker.
- **Evaluation**: **LangSmith** datasets, tracing, and evaluators (with Ragas), component-level metrics, and CI regression gates.

### Fullstack Architecture

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                           DJANGO FULLSTACK APP                          │
  │  • Chat UI (SSE Streaming Answers + Interactive Citation Popovers)      │
  │  • Document Ingestion Hub (Upload + Layout Detection Route Badges)      │
  │  • Queue & Reconciler Monitor (Pending / Processing / DLQ Dashboard)   │
  │  • Django Admin (Documents, Chunks, Evaluations, Audit Logs)            │
  └───────────────────────────────────┬─────────────────────────────────────┘
                                      │
                                      ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    REDIS ASYNCHRONOUS TASK QUEUE                        │
  │  • Producer: Computes SHA-256 (idempotency, skips duplicate indexing)   │
  │  • Consumer / Worker: Heartbeats, atomic pop, 3 retries with backoff    │
  │  • Reconciler: Diffs disk vs registry (picks up missed / DLQ files)     │
  └───────────────────────────────────┬─────────────────────────────────────┘
                                      ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                     INGESTION & RETRIEVAL ENGINE                        │
  │  1. Probe: text coverage, columns histogram, drawing line density       │
  │  2. Route: FAST (PyMuPDF) | LAYOUT (Docling) | OCR (Paddle/RapidOCR)   │
  │  3. Chunk: Content-Aware (Headers/Tables) + Recursive fallback           │
  │  4. Index: Qdrant HNSW (Dense bge-m3) + BM25s (Sparse exact match)      │
  │  5. Fusion: Custom RRF (k=60) + Cross-Encoder Rerank (FlashRank/BGE)    │
  │  6. Generate: Ollama llama3.1:8b with strict citation grounding         │
  └───────────────────────────────────┬─────────────────────────────────────┘
                                      ▼
                         LangSmith Traces + Evaluators
```

---

## 2. Stack & Local Hardware Optimization

### Target Hardware & Local VRAM Budget (NVIDIA RTX 3050 6GB + 16GB RAM)

- **VRAM Budget (6144 MiB total)**:
  - System display / Windows apps: ~1.0 GB reserved.
  - Available for local inference: **~5.1 GB VRAM**.
  - **Dense Embeddings (`bge-m3:latest`)**: ~1.2 GB VRAM (or FastEmbed CPU ONNX).
  - **Cross-Encoder Reranker (`qllama/bge-reranker-v2-m3:latest` or `flashrank`)**: ~0.8 GB VRAM (or FlashRank sub-15ms on CPU).
  - **LLM Generation**:
    - **`quality` profile (Default — `llama3.1:8b`)**: ~4.7 GB Q4_K_M. Fits with ~28 layers offloaded to GPU, remaining in RAM. Generates at **~15–25 tokens/sec**.
    - **`fast` profile (`llama3.2:3b`)**: ~2.0 GB. Fits **100% inside VRAM** alongside embeddings. Generates at **~40–60 tokens/sec**.
- **System RAM Protection**: Django streaming views and chunk generators stream batches directly rather than accumulating unbounded memory lists.

### Tech Stack Table

| Layer | Default choice | Why | Swap-in alternatives |
|---|---|---|---|
| Python | 3.11+ | required by modern AI toolchains | — |
| Deps | `uv` | fast, lockfile-native | poetry |
| Fullstack Framework | **Django 5.x** | Batteries-included web framework, ORM, Admin, async streaming views | FastAPI, Flask |
| Frontend UI | **Django Templates + Tailwind CSS + Lucide Icons + HTMX / SSE JS** | Follows `claude.md` design rules: polished, clean typography, responsive, zero bloated SPA build step | React / Vite SPA |
| Local LLM | **Ollama** (`langchain-ollama`) running `llama3.1:8b` (quality) or `llama3.2:3b` (fast) | 100% local, open weights, zero API costs | `qwen2.5-coder:7b`, vLLM, `claude-sonnet-4-5` |
| Task Queue & State | **Redis** (`redis` / `django-redis` / atomic streams) + `fakeredis` for tests | Fast in-memory queue, atomic transitions, persistent state registry, zero cloud fees | Valkey, Celery |
| Orchestration | `langchain` 1.x + `langgraph` 1.x | pipeline as a typed graph, resumable, native LangSmith tracing | plain functions |
| Tracing / eval | `langsmith` + `ragas` | native trace spans + automated RAG Triad metrics (Faithfulness, Relevance) | `phoenix` (Arize), `langfuse` |
| Layout-aware parsing | `docling` (IBM) | strongest open-source layout + table-structure model, emits structured doc model with bbox/page | `pymupdf4llm`, `unstructured`, `marker-pdf` |
| Fast text-layer parsing | `pymupdf` | ~100× cheaper on born-digital PDFs | `pypdfium2` |
| OCR | `rapidocr-onnxruntime` (CPU) or `paddleocr` | fallback for scanned pages | Tesseract, Surya |
| Chunking (content-aware) | `docling` `HybridChunker` for parsed docs; `chonkie` (`SemanticChunker`) for plain text | structure-aware and cheap | `langchain-text-splitters` `MarkdownHeaderTextSplitter` |
| Chunking (recursive) | `langchain-text-splitters` `RecursiveCharacterTextSplitter` | proven separator cascade; used as the size enforcer | `chonkie.RecursiveChunker` |
| Embeddings | `BAAI/bge-m3` via `fastembed` / `sentence-transformers` | SOTA open-source local embeddings, 8k context, runs on CPU/GPU | `nomic-embed-text`, `bge-small-en-v1.5` |
| Vector store / HNSW | **Qdrant** (`qdrant-client`) — HNSW + native sparse vectors + payload filters | Open-source (Apache 2.0), local embedded mode or Docker, scales out | `LanceDB` (embedded), `pgvector`, raw `hnswlib` |
| BM25 | Qdrant sparse/BM25; `bm25s` for the local in-process index | `bm25s` is ~100× faster than `rank_bm25` and pickles cleanly | `rank_bm25` |
| Fusion | **our own RRF** in `apps/rag_engine/retrieval/fusion.py` | must be unit-testable and tunable | Qdrant server-side RRF |
| Reranker | `flashrank` (ONNX CPU, default) or `qllama/bge-reranker-v2-m3` (local GPU) | 100% open-source, local cross-encoder, ultra-low latency | Cohere Rerank 4, Voyage rerank-2.5 via API |
| Database (App) | SQLite (local default) / PostgreSQL | Django ORM for document metadata, query history, feedback | — |
| Config | `pydantic-settings` + YAML | centralized configuration | hydra |
| Tests | `pytest`, `pytest-django`, `pytest-asyncio`, `fakeredis` | comprehensive offline test suites | — |
| Lint / type | `ruff`, `mypy` | strict code hygiene | — |

---

## 3. Repository layout (create exactly this Django structure)

```
.
├── AGENTS.md                          # agent instructions (see §10)
├── CLAUDE.md                          # -> points to AGENTS.md + includes frontend rules
├── GEMINI.md                          # -> points to AGENTS.md
├── README.md
├── Makefile
├── pyproject.toml
├── .env.example
├── docker-compose.yml                 # qdrant + redis, with healthchecks
├── manage.py                          # Django management script
├── configs/
│   ├── default.yaml
│   └── profiles/{fast,quality,offline}.yaml
├── data/
│   ├── raw/                           # source docs (gitignored)
│   └── eval/                          # golden QA sets (committed, small)
├── config/                            # Django project configuration
│   ├── __init__.py
│   ├── asgi.py                        # ASGI for async streaming views
│   ├── wsgi.py
│   ├── urls.py                        # Root URL routing
│   └── settings/
│       ├── __init__.py
│       ├── base.py                    # Base Django settings + RAG config loader
│       ├── local.py                   # Local dev settings
│       └── test.py                    # Test settings (in-memory SQLite, fakeredis)
├── apps/
│   ├── core/                          # Base models, helpers, config wrapper
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── config.py                  # Pydantic Settings adapter
│   ├── documents/                     # Document models & Layout Ingestion
│   │   ├── __init__.py
│   │   ├── models.py                  # Document, Block, DocumentProfile models
│   │   ├── admin.py                   # Django Admin for documents and profiles
│   │   ├── probe.py                   # LAYOUT DETECTION — §4
│   │   ├── router.py                  # Parser routing logic
│   │   ├── parsers/
│   │   │   ├── base.py                # Parser protocol
│   │   │   ├── fast_text.py           # PyMuPDF text-layer path
│   │   │   ├── layout.py              # Docling layout + table path
│   │   │   └── ocr.py                 # OCR path for scanned pages
│   │   └── pipeline.py
│   ├── chunking/                      # Chunking logic
│   │   ├── __init__.py
│   │   ├── base.py                    # Chunker protocol
│   │   ├── content_aware.py           # structure + semantic — §5
│   │   ├── recursive.py               # RecursiveCharacterTextSplitter wrapper
│   │   ├── table.py                   # Whole table serialization + windowing
│   │   └── router.py
│   ├── rag_engine/                    # Dual Indexing, RRF, Reranking, Generation
│   │   ├── __init__.py
│   │   ├── models.py                  # Chunk, Candidate, RetrievalResult dataclasses
│   │   ├── index/
│   │   │   ├── base.py                # VectorStore + SparseIndex protocols
│   │   │   ├── dense_qdrant.py        # Qdrant client & HNSW setup
│   │   │   ├── dense_hnswlib.py       # Local zero-infra option
│   │   │   ├── sparse_bm25.py         # bm25s lexical index
│   │   │   └── builder.py
│   │   ├── retrieval/
│   │   │   ├── dense.py
│   │   │   ├── sparse.py
│   │   │   ├── fusion.py              # Custom RRF — §6
│   │   │   ├── rerank.py              # FlashRank / BGE Reranker — §7
│   │   │   └── pipeline.py
│   │   ├── generation/
│   │   │   ├── prompts.py             # Citation-grounded system prompts
│   │   │   └── answer.py              # Local Ollama stream generator
│   │   └── graph/
│   │       └── rag_graph.py           # LangGraph StateGraph pipeline
│   ├── queue_tasks/                   # Redis queue, Worker, & Reconciler
│   │   ├── __init__.py
│   │   ├── connection.py              # Redis connection pool
│   │   ├── producer.py                # Enqueues files with SHA-256 deduplication
│   │   ├── worker.py                  # Ingestion consumer worker
│   │   ├── registry.py                # State tracking (PENDING/PROCESSING/COMPLETED/FAILED)
│   │   ├── reconciler.py              # Directory scanner ("picks up missed ones")
│   │   └── management/commands/       # Django management commands
│   │       ├── rag_worker.py          # python manage.py rag_worker
│   │       ├── rag_ingest.py          # python manage.py rag_ingest
│   │       └── rag_recover.py         # python manage.py rag_recover
│   ├── eval_harness/                  # LangSmith & Ragas Evaluation
│   │   ├── __init__.py
│   │   ├── datasets.py                # Golden QA datasets manager
│   │   ├── evaluators.py              # Retrieval & generation evaluators — §9
│   │   ├── ablation.py                # Automated ablation matrix sweep
│   │   └── management/commands/
│   │       └── rag_eval.py            # python manage.py rag_eval
│   └── web/                           # Django Frontend Views & APIs
│       ├── __init__.py
│       ├── urls.py
│       ├── views.py                   # Chat view, Upload view, Dashboard view
│       └── api.py                     # SSE stream API (`/api/chat/stream/`), upload API
├── templates/                         # Polished UI complying with claude.md
│   ├── base.html                      # Layout, Tailwind setup, Lucide icons
│   ├── includes/
│   │   ├── header.html
│   │   └── citation_modal.html        # Verified source & bbox inspector modal
│   └── web/
│       ├── chat.html                  # Chat interface with streaming & citation popovers
│       ├── documents.html             # Document hub, upload dropzone, route badges
│       └── queue.html                 # Live queue & reconciliation dashboard
├── static/
│   ├── css/
│   │   └── styles.css                 # Clean typography, restrained shadows
│   └── js/
│       ├── sse_chat.js                # Handles SSE streaming & citation rendering
│       └── upload.js                  # Async file upload & status polling
├── tests/
│   ├── conftest.py                    # fake embedder, stub LLM, fakeredis, tiny fixtures
│   ├── fixtures/                      # 3 sample docs: born-digital, scanned, table-heavy
│   ├── unit/
│   └── integration/
└── docs/
    ├── ARCHITECTURE.md
    ├── DECISIONS.md
    └── EVALUATION.md
```

---

## 4. Milestone 1 — Layout-aware document detection

**This is the differentiator. Do not parse everything with the heavy parser.**

Implement `apps/documents/probe.py`:

```python
def probe(path: Path, config: ProbeConfig) -> DocumentProfile: ...
```

`DocumentProfile` fields: `route: Literal["fast","layout","ocr"]`, `page_count`, `text_layer_coverage: float`, `chars_per_page: float`, `image_area_ratio: float`, `column_count: int`, `table_likelihood: float`, `has_forms: bool`, `is_scanned: bool`, `page_routes: dict[int, str]`, `reasons: list[str]`, `confidence: float`.

Signals to compute (sample up to `probe.max_sample_pages`, default 8, spread evenly across the document — do **not** read the whole PDF):

1. **Text-layer coverage** — pages with extractable text ÷ pages sampled (PyMuPDF `page.get_text("text")`). `< 0.6` ⇒ scanned-ish.
2. **Chars per page** — `< 120` on a page with large image area ⇒ scanned.
3. **Image area ratio** — sum of image bbox area ÷ page area. `> 0.65` ⇒ OCR candidate.
4. **Column detection** — project the x-midpoints of text spans into a histogram; count dense clusters separated by a gutter wider than `min_gutter_pt` (default 18pt). `>= 2` ⇒ multi-column ⇒ layout route.
5. **Table likelihood** — combine:
   - (a) vector-drawing line density: horizontal/vertical segments from `page.get_drawings()`; grids of $\ge 3$ h-lines and $\ge 3$ v-lines score high.
   - (b) whitespace alignment: fraction of lines whose token x-positions align into $\ge 3$ columns across $\ge 4$ consecutive lines (catches *borderless* tables). `> tables.threshold` (0.35) ⇒ layout route.
6. **Form fields** — `doc.is_form_pdf` / AcroForm widget count > 0 ⇒ layout route.
7. **Reading-order risk** — rotated text present, or headers/footers repeating on $\ge 60\%$ of sampled pages.

**Routing rules** (`apps/documents/router.py`):
- `is_scanned` $\to$ `ocr` (Paddle/RapidOCR $\to$ Docling structure pass).
- `table_likelihood > θ` OR `column_count >= 2` OR `has_forms` OR file is `.pptx`/`.xlsx`/`.docx` $\to$ `layout` (Docling layout + TableFormer).
- Plain `.md`, `.txt`, `.html`, or single-column high-text PDF $\to$ `fast` (PyMuPDF).
- Any exception $\to$ `layout` (fail safe).

Every parser normalizes into the same model:
```python
Block(id, doc_id, page, bbox, type, text, html, level, order, meta)
DocumentModel(doc_id, source_path, mime, profile, blocks, toc, meta)
```

**Acceptance criteria**
- `tests/fixtures/` holds three PDFs: born-digital single-column prose, two-column paper with bordered table, and rasterized scan of page 1.
- `probe()` classifies all three correctly; asserts route **and** reason string.
- Probing a 200-page PDF touches $\le 8$ pages.
- Detected headers/footers are tagged `type="header"` and excluded from chunking.

---

## 5. Milestone 2 — Content-aware + recursive chunking

Two strategies, used together, selected per block by `apps/chunking/router.py`.

### 5a. Content-aware (primary)
1. **Structural grouping**: walk `blocks` in reading order; never cross `H1`/`H2` boundary. Prepend heading hierarchy (`"Ch 3 > 3.2 Dosing > Adults"`) to `chunk.meta.breadcrumb` and embedded text.
2. **Type-specific handling**:
   - `table` $\to$ serialize whole table as Markdown into one chunk with generated caption. If exceeding `max_tokens`, split by row windows repeating header row in every window.
   - `code` $\to$ split on top-level definitions (`ast`), never mid-function.
   - `list` $\to$ keep items together with introducing sentence.
3. **Semantic splitting in long prose**: sentence-split, compute embedding cosine distance between consecutive sentences, cut at 95th percentile topic shifts for sections over 600 tokens.

### 5b. Recursive (fallback + size enforcer)
`RecursiveCharacterTextSplitter` with separator cascade `["\n\n## ", "\n\n", "\n", ". ", " ", ""]`, `chunk_size` in tokens, `chunk_overlap` 12%.
Guarantees **hard token cap** on any chunk that came out too large.

**Acceptance criteria**
- No chunk exceeds `max_tokens` — property test over fixture corpus.
- The table fixture yields exactly one chunk containing every row (or windowed with repeated headers).
- Re-running ingestion produces identical SHA-256 chunk IDs.

---

## 6. Milestone 3 — Dual index + RRF fusion

### Dense (HNSW)
Qdrant collection with cosine distance, `m=32`, `ef_construct=256`, `ef_search=128`. Payload includes `doc_id`, `chunk_id`, `breadcrumb`, `page_span`, `bbox_union`.

### Sparse (BM25)
`bm25s` index over preprocessed tokens: lowercased, stemmed, punctuation stripped, preserving alphanumerics (e.g. `CVE-2024-1234`, `10-K`, `p53`). Config `k1=1.5`, `b=0.75`.

### Custom RRF (`apps/rag_engine/retrieval/fusion.py`)
```python
def rrf(ranked_lists: Sequence[Sequence[str]],
        weights: Sequence[float] | None = None,
        k: int = 60,
        top_n: int | None = None) -> list[tuple[str, float]]:
    """score(d) = Σ_i  w_i / (k + rank_i(d)), ranks starting at 1."""
```
- Rank-based only; never mixes raw scores.
- Deterministic tie-breaking by `chunk_id`.
- Pulls `top_k=50` from dense and sparse; returns `top_n_fused=50`.

**Acceptance criteria**
- RRF unit tests pass for known ranking tables.
- Hybrid needle test passes: planted paraphrase chunk retrieved (dense wins) AND planted exact-identifier chunk retrieved (sparse wins).

---

## 7. Milestone 4 — Reranking

`apps/rag_engine/retrieval/rerank.py`, behind protocol `Reranker`.

- `FlashRankReranker` (*default*): local CPU ONNX cross-encoder (`ms-marco-MiniLM-L-12-v2`), sub-15ms latency.
- `CrossEncoderReranker`: local GPU `qllama/bge-reranker-v2-m3:latest` via sentence-transformers.
- Reranks top-50 fused candidates to final `top_n=6`.
- Drops candidates below `min_score=0.15` (triggers explicit refusal when no chunks survive).
- Caches `(query_hash, chunk_id) -> score` in SQLite/diskcache.

**Acceptance criteria**
- Reranking measurably improves nDCG@5 over raw RRF.
- Fully mockable for offline unit tests.

---

## 8. Milestone 5 — Redis Queue Ingestion & Missed Document Recovery

Implement `apps/queue_tasks/`:

### 8a. Producer (`queue_tasks/producer.py`)
- Computes `sha256(file_content)` before queueing.
- Queries `rag:doc_registry` in Redis: skips if already `COMPLETED` (idempotent).
- Pushes job `{job_id, filepath, sha256, retries: 0}` to Redis list `rag:queue:pending`.

### 8b. Worker (`queue_tasks/worker.py`)
- Atomic pop using `RPOPLPUSH` from `rag:queue:pending` to `rag:queue:processing`.
- Updates heartbeat timestamp in Redis.
- Runs: `probe` $\to$ `route` $\to$ `parse` $\to$ `chunk` $\to$ `index` (Qdrant + BM25).
- On error: retries with exponential backoff up to 3 times. If exhausted, moves to Dead-Letter Queue `rag:queue:dead_letter`.

### 8c. Reconciler ("Pick Up Missed Ones") (`queue_tasks/reconciler.py`)
- **Stalled Job Reclaim**: Scans `rag:queue:processing` for jobs with heartbeat > 600s; reclaims to `pending`.
- **Directory Scanner**: Diffs physical files on disk against Redis registry. Detects unindexed files or DLQ failures and re-enqueues them automatically.

### 8d. Django Management Commands
- `python manage.py rag_worker` — starts queue consumer.
- `python manage.py rag_ingest --path ./data/raw/` — enqueues documents.
- `python manage.py rag_recover --dir ./data/raw/` — reconciles directory and picks up missed ones.

**Acceptance criteria**
- Duplicate enqueues result in exactly one indexing execution.
- Simulated worker crashes are recovered by reconciler.
- 3 forced failures route to Dead-Letter Queue.

---

## 9. Milestone 6 — Evaluation with LangSmith, Ragas & Expected Accuracy

### Validation Targets
- **Retrieval**: Recall@10 $\ge$ 0.90, MRR $\ge$ 0.82 with `bge-m3` + `bm25s` + RRF.
- **Reranker**: nDCG@5 $\ge$ 0.82 with `bge-reranker-v2-m3` / `flashrank`.
- **Generation**: Faithfulness $\ge$ 0.90 with Ollama `llama3.1:8b`.
- **Citation Precision**: 100% of inline `[n]` citations resolve to verified retrieved chunks and page bounding boxes.

### Evaluator Suite (`apps/eval_harness/`)
- Tracing via `@traceable` with LangSmith.
- Deterministic retrieval metrics (`recall@k`, `nDCG@10`, `fusion_gain`).
- LLM-as-judge metrics via local Ollama / Ragas (`faithfulness`, `answer_correctness`, `citation_accuracy`).
- Automated ablation sweep (`python manage.py rag_eval --ablate`).
- CI regression gate: `make eval-ci` fails build if retrieval accuracy regresses > 2%.

---

## 10. Milestone 7 — Agent-CLI compatibility

The repository must be completely ergonomic for **Claude Code** and **Gemini CLI**.

Create `AGENTS.md` at root as the single source of truth. `CLAUDE.md` and `GEMINI.md` are one-line pointers to `AGENTS.md`. `AGENTS.md` contains:
- 5-line summary and fullstack architecture diagram.
- **Commands**: `make setup | migrate | run | worker | ingest | recover | eval | ablate | test | check`
- Map of `apps/*`.
- Offline profile instructions (`configs/profiles/offline.yaml` with `fakeredis`, in-memory SQLite, fake embedder, stub LLM).

Add:
- `.claude/commands/`: `/run`, `/worker`, `/ingest`, `/recover`, `/eval`
- `.gemini/settings.json` pointing to `AGENTS.md`
- `docker-compose.yml` for Qdrant and Redis with healthchecks.

---

## 11. Milestone 8 — Django Fullstack Web Application & UI

Build the complete fullstack interface in `apps/web/` complying with `claude.md`:

### 11a. Backend Async & SSE Views (`apps/web/views.py` & `api.py`)
- `GET /` — Main application dashboard:
  - Clean sidebar / navigation: Chat, Documents, Queue Monitor.
  - Professional sans-serif typography, high-contrast text, muted secondary accents.
- `POST /api/chat/stream/` — Async streaming view returning Server-Sent Events (`StreamingHttpResponse`):
  1. Sends metadata event with retrieved citation items (`chunk_id`, `source`, `page`, `bbox`, `score`).
  2. Streams response tokens as generated by local Ollama `llama3.1:8b`.
  3. Sends completion event with latency breakdown (`dense_ms`, `sparse_ms`, `rerank_ms`, `gen_ms`).
- `POST /api/documents/upload/` — Handles file uploads, immediately enqueues to Redis, and returns JSON `{job_id, status: "enqueued"}`.
- `GET /api/queue/status/` — JSON API returning pending count, processing count, completed count, and DLQ items.
- `POST /api/queue/recover/` — Triggers the directory reconciliation scanner.

### 11b. Frontend UI Templates & Components (Strictly following `claude.md`)
- **Visual Restraint**: Neutral backgrounds, subtle borders, no generic purple gradients or AI blobs, no glassmorphism.
- **Chat Interface (`templates/web/chat.html`)**:
  - Clean message thread with clear visual hierarchy.
  - Streaming markdown rendering with code highlighting.
  - Inline citation badges `[1]`, `[2]` formatted cleanly. Clicking a citation opens a sliding drawer or modal showing the verified source document chunk, page number, and bounding box preview.
- **Document Management (`templates/web/documents.html`)**:
  - Drag-and-drop file upload with immediate feedback.
  - Table of ingested documents showing filename, page count, route badge (`FAST`, `LAYOUT`, `OCR`), and status (`COMPLETED`, `PROCESSING`, `FAILED`).
- **Queue Monitor (`templates/web/queue.html`)**:
  - Real-time stat cards: Queue Depth, Active Workers, Failed/DLQ.
  - "Run Reconciliation Scanner" button to immediately pick up any missed files from disk.
- **Django Admin (`apps/documents/admin.py`)**:
  - Pre-registered models for `Document`, `DocumentProfile`, and `Chunk` with search, filtering by route, and raw JSON metadata inspector.

**Acceptance criteria**
- Running `python manage.py runserver` serves the full UI without errors.
- Querying from the chat UI streams tokens smoothly via SSE with inline citations.
- Uploading a PDF asynchronously enqueues the job and updates the document table.
- Clicking a citation displays the exact page number and text provenance.
- UI passes visual inspection: clean typography, responsive layout on mobile/tablet/desktop, Lucide icons.

---

## 12. Config files

### `configs/default.yaml`

```yaml
probe:
  max_sample_pages: 8
  scanned_text_coverage_threshold: 0.6
  image_area_ratio_threshold: 0.65
  table_likelihood_threshold: 0.35
  min_gutter_pt: 18

queue:
  redis_url: redis://localhost:6379/0
  max_retries: 3
  retry_backoff_base: 2.0
  heartbeat_timeout_sec: 600
  dlq_name: rag:queue:dead_letter
  registry_name: rag:doc_registry

chunking:
  strategy: content_aware
  max_tokens: 512
  min_tokens: 64
  overlap_ratio: 0.12
  semantic:
    enabled: true
    min_section_tokens: 600
    percentile_threshold: 95
  contextualize: false
  keep_headers_footers: false

embedding:
  model: BAAI/bge-m3             # Local SOTA multilingual embedding model
  batch_size: 32
  normalize: true

index:
  dense:
    backend: qdrant
    collection: rag_chunks
    distance: cosine
    hnsw: { m: 32, ef_construct: 256, ef_search: 128 }
  sparse:
    backend: bm25s
    k1: 1.5
    b: 0.75
    stemmer: english
    keep_alphanumerics: true

retrieval:
  top_k_dense: 50
  top_k_sparse: 50
  fusion:
    method: rrf
    k: 60
    dense_weight: 1.0
    sparse_weight: 1.0
    top_n_fused: 50
  rerank:
    enabled: true
    backend: flashrank
    model: ms-marco-MiniLM-L-12-v2
    top_n: 6
    min_score: 0.15
    batch_size: 16

generation:
  provider: ollama
  model: llama3.1:8b
  base_url: http://localhost:11434
  temperature: 0.1
  max_context_chunks: 6
  require_citations: true
  refuse_when_no_context: true

eval:
  langsmith_project: rag-hybrid
  regression_tolerance: 0.02
```

### Profile Overlays in `configs/profiles/`:
- `fast.yaml`: `generation.model: llama3.2:3b`, `rerank.backend: flashrank` (100% VRAM fit).
- `quality.yaml`: `generation.model: llama3.1:8b`, `rerank.model: qllama/bge-reranker-v2-m3`.
- `offline.yaml`: `dense.backend: hnswlib`, `queue.redis_url: fakeredis://`, fake embedder and stub LLM.

---

## 13. Build order and final deliverables

Execute in this order, one milestone per commit:

1. Django project scaffold + config + models + `manage.py`; `make check` green on empty project
2. **M1** layout detection + routing + parsers (§4)
3. **M2** chunking (§5)
4. **M3** dense HNSW + BM25 + RRF (§6)
5. **M4** reranking (§7)
6. **M5** Redis queue ingestion + worker + missed document reconciler + management commands (§8)
7. **M6** LangSmith eval + ablation + CI gate (§9)
8. **M7** agent-CLI ergonomics & offline profile (§10)
9. **M8** Django Fullstack Web Application (Chat UI, SSE streaming, document hub, queue dashboard) (§11)
10. Final pass: `README.md` with 5-minute quickstart, `docs/ARCHITECTURE.md`, `docs/EVALUATION.md`

**Definition of done for the whole build:**

- `make setup && make test` passes on a clean machine with **no API keys** (offline profile with `fakeredis`)
- `make up && make worker &` runs the background ingestion consumer
- Ingesting `tests/fixtures/` classifies documents into 3 distinct routes with reasons logged
- Running `python manage.py rag_recover --dir tests/fixtures/` demonstrates discovering and indexing any missed files
- Opening `http://localhost:8000/` serves a polished, responsive Django fullstack UI obeying `claude.md`
- Submitting a query streams an answer with inline citations that open the provenance modal
- Verified locally on RTX 3050: zero CUDA OOM errors on both `fast` and `quality` profiles
- `docs/EVALUATION.md` proves `rrf > best single arm` and `rrf+rerank > rrf` on nDCG@10

Start with Milestone 1 now. Print the plan, then build.
