# Hybrid RAG Platform

A local-first, fully open-source **retrieval-augmented generation platform** built on service-oriented
architecture. It runs entirely on consumer hardware (developed against an RTX 3050 6 GB + 16 GB RAM) with
no proprietary cloud API dependency: local Ollama models for generation and embeddings, Qdrant for dense
vectors, BM25 for sparse retrieval, and a CPU cross-encoder for reranking.

Every answer is grounded in a citation carrying `document → page → bounding box`, so any claim can be
traced back to the exact region of the source PDF that produced it.

## What it does

Documents are routed through a layout probe that picks the cheapest parser that will actually work, chunked
with layout awareness, and indexed into both a dense and a sparse store. At query time the two result sets
are fused, reranked, checked for sufficiency, and only then passed to the LLM — with a confident refusal
when the evidence does not support an answer.

```
PDF ──► Layout probe ──► Parser (fast / layout / OCR) ──► Chunker ──┬──► Qdrant (dense, HNSW)
                                                                    └──► BM25s (sparse, on disk)

Query ──► Decompose ──► Dense + Sparse ──► RRF fusion ──► Rerank ──► CRAG gate ──┬──► Ollama ──► Answer + citations
                                                                                └──► Confident refusal
```

## Core capabilities

**Adaptive ingestion.** An 8-page heuristic probe measures text coverage, image ratio, column count and
table density, then routes each document to the cheapest parser that can handle it — PyMuPDF for clean
digital text, Docling for tables and multi-column layouts, RapidOCR for scans. Figures are extracted and
retained for multimodal queries.

**Hybrid retrieval.** Dense HNSW search and BM25 lexical search run in parallel and are merged with
Reciprocal Rank Fusion (`k=60`), then reranked by a FlashRank cross-encoder that runs on CPU and costs zero
VRAM. Results below a score cutoff are dropped rather than padded.

**Corrective RAG (CRAG).** Every retrieval round is graded by `CRAGEvaluator` into `CONFIDENT`,
`AMBIGUOUS`, or `REFUSE`. Ambiguous rounds trigger an automatic query reformulation and retry; `REFUSE`
produces an explicit refusal instead of a hallucinated answer.

**Agentic multi-hop.** `AgenticCoordinator` decomposes complex questions into sub-queries and plans
multi-hop retrieval, with each hop passing back through the CRAG gate.

**GraphRAG.** Entities and relations are extracted into a knowledge graph (NetworkX) supporting associative
multi-hop pathfinding and community detection for questions that span documents.

**Context compaction.** An extractive salience selector, cross-document deduplication, and table column
pruning pack retrieved context into a strict token budget while preserving bounding boxes — keeping
generation inside an 8K Ollama context window on a 6 GB card.

**RAGOps feedback loop.** Thumbs up/down on any answer is persisted, and thumbs-down automatically mines
hard negatives for later contrastive reranker fine-tuning.

**Fault-tolerant ingestion queue.** A folder watcher hashes files (SHA-256) for deduplication and enqueues
work to Redis, with a dead-letter queue and replay endpoint for failed tasks.

## Token budget

Generation is constrained to fit an 8,192-token Ollama window with headroom:

| Component | Tokens |
| :--- | ---: |
| System prompt and citation rules | ~400 |
| Retrieved context (top-6 x 512) | ~3,072 |
| Query and chat history | ~500 |
| Output completion | ~1,000 |
| **Total** | **~4,972** |

## Services

| Service | Path | Responsibility |
| :--- | :--- | :--- |
| Ingestion | `services/ingestion` | Layout probing, parser routing, figure extraction |
| Indexing | `services/indexing` | Content-aware chunking, Qdrant + BM25 writes |
| Retrieval | `services/retrieval` | RRF fusion, reranking, CRAG, agentic planning, compaction |
| Graph | `services/graph` | Entity extraction, graph store, multi-hop traversal |
| Scheduler | `services/scheduler` | Folder reconciler, Redis queue, worker, DLQ |
| Gateway | `services/gateway` | REST + SSE API, serves the web client |
| Feedback | `services/feedback` | RAGOps feedback store and hard-negative mining |
| Session | `services/session` | Chat sessions and per-session file scoping |

All inter-service payloads are Pydantic models under `contracts/` — no service passes a bare dict to another.

## Requirements

- Python 3.11+
- Docker (Qdrant, Redis, optionally Langflow)
- [Ollama](https://ollama.com) with the models pulled:

  ```bash
  ollama pull llama3.1:8b     # quality profile (default)
  ollama pull llama3.2:3b     # fast profile
  ollama pull bge-m3          # embeddings
  ```

- PostgreSQL (only needed for Langflow flow and chat persistence)

## Quick start

```bash
# 1. Install dependencies
uv sync                       # or: pip install -e ".[parse,dev]"

# 2. Start infrastructure
docker compose up -d          # Qdrant :6333, Langflow :7860

# 3. Configure local credentials
cp .env.example .env          # then fill in your Postgres values

# 4. Launch the gateway and web client
make serve                    # http://localhost:8000
```

On Windows without GNU make, `run.ps1` provides the same targets:

```powershell
.\run.ps1 serve
.\run.ps1 check
```

Drop PDFs into `data/documents/` and the reconciler will pick them up, or upload directly from the web
client. Ollama must be running on `127.0.0.1:11434`.

### Task targets

| Target | Description |
| :--- | :--- |
| `serve` | REST + SSE gateway and web client on `:8000` |
| `run` | Langflow visual canvas on `:7860` |
| `test` | Unit test suite |
| `check` | Ruff lint + full test suite |
| `eval` | Offline retrieval and faithfulness benchmark |
| `gate` | CI regression quality gate |
| `scheduler` | Directory reconciler daemon |
| `worker` | Redis queue worker daemon |

## API

The gateway exposes the platform over REST with streaming chat via SSE:

| Endpoint | Purpose |
| :--- | :--- |
| `GET /api/v1/health` | Component health (Ollama, Qdrant, Redis, BM25) |
| `POST /api/v1/ingest` | Upload and parse a document |
| `POST /api/v1/index` | Chunk and index parsed blocks |
| `POST /api/v1/retrieve` | Hybrid retrieval with reranked candidates |
| `POST /api/v1/chat` | Grounded chat with SSE token streaming |
| `GET /api/v1/preview` | Rendered page image with citation bounding boxes |
| `POST /api/v1/graph/query` | GraphRAG multi-hop traversal |
| `POST /api/v1/feedback` | Record thumbs up/down |
| `GET /api/v1/ragops/dataset` | Export mined hard negatives |
| `GET /api/v1/queue/dlq` | Inspect and replay failed ingestion tasks |

Interactive docs at `http://localhost:8000/docs`.

## Configuration

`configs/default.yaml` holds all tunables — parser thresholds, chunk size, RRF `k`, rerank cutoff, model
names. Hardware profiles in `configs/profiles/` switch between `quality` (`llama3.1:8b`) and `fast`
(`llama3.2:3b`, fully resident in 6 GB VRAM). Secrets stay in `.env` and are never committed.

## Testing and evaluation

```bash
make check    # ruff + 77 unit tests
make eval     # retrieval quality and citation faithfulness benchmark
make gate     # fails the build on regression against baseline metrics
```

The evaluation harness reports hit-rate@1/@3 and MRR for each retrieval mode (dense, sparse, hybrid,
reranked) alongside citation validity and faithfulness, so the contribution of fusion and reranking is
measurable rather than assumed.

## Observability

Every service logs through `services/common/logger.py` to both colored console output and rotating
per-service files in `logs/` — routing decisions, chunk counts, RRF and rerank scores, and stage latencies.

## Notes

- `data/` and `logs/` are gitignored: they hold ingested source documents, the Qdrant volume, and derived
  indices, all of which are local runtime state.
- The Langflow credentials in `docker-compose.yml` are local development defaults. Change them before
  exposing the service on any network.

## License

MIT
