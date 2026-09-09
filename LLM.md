# LLM.md - Hybrid RAG Platform

This document provides a concise, high-density architecture guide and operational manual designed for Large Language Models (LLMs) and AI agents interacting with or extending this codebase.

---

## 1. System Overview

The **Hybrid RAG Platform** is a local-first, production-grade Retrieval-Augmented Generation system engineered for speed, accuracy, and deterministic visual provenance under constrained consumer hardware (e.g., 6 GB VRAM).

### Core Capabilities
- **Adaptive Ingestion**: Probes PDF layout to route between Fast Text (PyMuPDF), Layout/Table (Docling), and OCR (RapidOCR).
- **Hybrid Search**: Dense semantic retrieval (Qdrant) + Sparse lexical retrieval (BM25s) fused via Reciprocal Rank Fusion (RRF, $k=60$).
- **GraphRAG**: Entity-relation extraction and multi-hop associative traversal for relational knowledge.
- **Reranking**: FlashRank neural cross-encoder reranking.
- **Corrective RAG (CRAG)**: Dynamic confidence evaluator (`CONFIDENT`, `AMBIGUOUS`, `REFUSE`) with automatic query reformulation and refusal guardrails.
- **Context Compaction**: Sentence-level extractive pruning against strict token budgets.
- **Deterministic Visual Citations**: Retains document ID, page number, and bounding box `[x0, y0, x1, y1]` for exact PDF highlight rendering.
- **RAGOps Active Learning**: Ingests user feedback (`thumbs up`/`thumbs down`) to mine hard negatives for contrastive fine-tuning.

---

## 2. Architecture & Data Flow

```
[ Ingestion ]
Source PDF ──> Probe (8 pages) ──> Router (FastText / Layout / OCR)
                 └──> Chunker ──> Dense Embedding (Qdrant)
                               ──> Lexical Index (BM25s)
                               ──> Knowledge Graph (NetworkX/JSON)

[ Query & Retrieval ]
User Query ──> AgenticCoordinator / Decomposer
                 ├──> Dense Vector Search (Qdrant)
                 ├──> Sparse BM25 Search (BM25s)
                 └──> Graph Associative Traversal
                          │
                          ▼
               Reciprocal Rank Fusion (RRF, k=60)
                          │
                          ▼
               FlashRank Cross-Encoder Rerank
                          │
                          ▼
               CRAG Evaluator (CONFIDENT | AMBIGUOUS | REFUSE)
                          │
                          ▼
               Context Compactor (Token Budget Packing)
                          │
                          ▼
               Ollama LLM (SSE Streaming Response) + Visual Citation Bounding Boxes
```

---

## 3. Directory Layout

| Directory / File | Description |
| :--- | :--- |
| `contracts/` | **Single Source of Truth**: Pydantic models for all data exchange between services (`chunk.py`, `document.py`, `retrieval.py`, `agent.py`, `graph.py`, `feedback.py`, `session.py`). |
| `services/gateway/api.py` | FastAPI SOA Gateway exposing REST and SSE streaming endpoints, serves `ui/index.html`. |
| `services/ingestion/` | Document ingestion (`service.py`), probe router (`probe.py`), chunker (`chunker.py`), multimodal/visualizer (`visualizer.py`). |
| `services/indexing/` | Storage coordinator (`service.py`) managing Qdrant (`qdrant_store.py`), BM25 (`bm25_store.py`), and Graph (`graph_store.py`). |
| `services/retrieval/` | Hybrid retriever (`service.py`), FlashRank (`reranker.py`), CRAG (`crag.py`), Agentic loop (`agentic.py`), and Compactor (`compactor.py`). |
| `services/scheduler/` | Background file watcher (`reconciler.py`), Redis worker (`worker.py`), DLQ (`dlq_manager.py`). |
| `services/session/` | Multi-turn conversational memory in Redis (`manager.py`). |
| `services/feedback/` | RAGOps store and active learning dataset generator (`store.py`). |
| `configs/` | Hierarchical configuration (`default.yaml`, `profiles/quality.yaml`, `profiles/fast.yaml`). |
| `ui/index.html` | Zero-build single-page frontend following Obsidian/Zinc craft design standards. |
| `docker-compose.yml` | Full containerized stack (gateway, worker, scheduler, qdrant, redis, postgres, langflow). |

---

## 4. Key Invariants & Rules for LLMs

1. **Contracts First**:
   - Never pass raw Python dictionaries across service boundaries. Always instantiate and validate with Pydantic models from `contracts/`.
2. **Bounding Box Preservation**:
   - Every `Block`, `Chunk`, `Candidate`, and `Citation` MUST preserve `doc_id`, `page` (1-indexed), and `bbox: [x0, y0, x1, y1]`. Visual PDF citation rendering (`/api/v1/preview`) fails if this is stripped.
3. **Singleton Stores**:
   - `IndexingService` creates and owns `qdrant`, `bm25`, and `graph`. `RetrievalService` and `AgenticCoordinator` reuse these instances. Never instantiate duplicate stores in-process.
4. **Execution Working Directory**:
   - Always run commands from the repository root (`.`). Relative paths like `data/graph` and `data/ragops` depend on this CWD.
5. **Token Budgets**:
   - Context generation targets ~4,972 tokens within an 8K Ollama window (top-6 chunks × 512 tokens) to strictly prevent consumer GPU VRAM paging.

---

## 5. Endpoints Quick Reference

Base Gateway URL: `http://localhost:8001` (Docker) or `http://localhost:8000` (Local `serve`)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Single-Page Web Client (`ui/index.html`) |
| `/docs` | `GET` | OpenAPI / Swagger Documentation |
| `/api/v1/health` | `GET` | Health probes for Qdrant, Redis, Ollama |
| `/api/v1/chat` | `POST` | Primary RAG endpoint (supports SSE streaming and multi-turn sessions) |
| `/api/v1/retrieve` | `POST` | Hybrid retrieval without generation (dense + sparse + rerank) |
| `/api/v1/ingest/file` | `POST` | Upload and parse document (`.pdf`, `.txt`, `.md`) |
| `/api/v1/preview` | `GET` | Renders a page image with overlaid citation bounding box |
| `/api/v1/feedback` | `POST` | Records 👍 / 👎 user feedback & mines hard negatives |
| `/api/v1/graph/query`| `POST` | GraphRAG associative multi-hop query |
| `/api/v1/queue/stats`| `GET` | Redis background queue length and DLQ metrics |

---

## 6. Execution Commands

### Docker Compose (Recommended Stack)
```bash
# Start all services (Infrastructure + Gateway + Worker + Scheduler + Langflow)
docker compose up -d

# Check status of containers
docker compose ps

# View service logs
docker compose logs -f gateway worker scheduler

# Stop all containers
docker compose down
```

### Local Development (PowerShell / Makefile)
```powershell
# Run Gateway locally with reload
.\run.ps1 serve

# Run linting and test suite
.\run.ps1 check

# Run unit tests only
.\run.ps1 test
```
