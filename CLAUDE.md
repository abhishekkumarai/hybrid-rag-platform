# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This is a Windows-primary repo. `Makefile` and `run.ps1` expose the same targets; use `run.ps1` when GNU
make is unavailable.

```bash
make check                              # ruff + full unit suite — the standard pre-commit gate
make test                               # unit tests only
make serve                              # gateway + web client on :8000
make eval                               # retrieval quality + faithfulness benchmark
make gate                               # regression gate; fails on metric regression vs baseline
make services-up / services-down        # full docker stack up/down
make scheduler / worker                 # reconciler and Redis queue daemons
```

Docker: `docker-compose.yml` defines the entire stack — `qdrant`, `redis`, `postgres`, `gateway`,
`worker`, `scheduler`, `langflow`, plus an opt-in `ollama` behind the `local-llm` profile. `gateway`,
`worker` and `scheduler` share one image built from `Dockerfile` and differ only in their `command`.
`docker compose up -d --build` runs everything; `docker compose up -d qdrant redis postgres` gives just
the infrastructure for a local `make serve`.

```powershell
.\run.ps1 serve                         # PowerShell equivalents
.\run.ps1 check
```

Single test / single file:

```bash
python -m pytest tests/unit/test_agentic.py -v
python -m pytest tests/unit/test_agentic.py::test_agentic_coordinator_multi_hop_run -v
python -m pytest tests/unit -q -k "rrf or rerank"
```

Lint: `python -m ruff check .` (line-length 100; `E501`/`E402` ignored).

`tests/unit` (77 tests) mocks Qdrant, Redis and Ollama and runs with no infrastructure. `tests/integration`
and `tests/eval` require live Qdrant + Ollama.

`run.ps1` help text still advertises "37 pytest tests" — stale, ignore it.

## Architecture

Five decoupled services behind a FastAPI gateway. **All inter-service payloads are Pydantic models in
`contracts/` — no service passes a bare dict to another.** When changing a data shape, change the contract
first; that is the interface, not the function signature.

```
ingest → probe → parser routing → chunk → Qdrant (dense) + BM25s (sparse) + graph
query  → decompose → dense+sparse → RRF(k=60) → FlashRank rerank → CRAG gate → compact → Ollama
```

**Store ownership.** `IndexingService` constructs and owns the three stores (`qdrant`, `bm25`, `graph`);
`RetrievalService` is handed those same instances, and `AgenticCoordinator` borrows the retrieval service's
`traverser` and `compactor`. The gateway wires all of this as module-level singletons in `get_services()` /
`get_agentic_coordinator()` (`services/gateway/api.py`). Never construct a second store instance — the BM25
index and graph are in-process state, and a duplicate silently reads a stale copy.

**Ingestion routing.** `services/ingestion/probe.py` samples the first 8 pages and measures text coverage,
image ratio, column count and table score, then `IngestionService.parse()` dispatches to one of three
parsers: `fast_text` (PyMuPDF), `layout` (Docling, for tables/multi-column), `ocr` (RapidOCR, for scans).
Thresholds live in `configs/default.yaml` under `ingestion:`, not in code.

**Retrieval layering.** `RetrievalService.retrieve()` is the plain hybrid path. Above it:
`AgenticCoordinator.run_plan()` decomposes into sub-queries, runs a retrieval per hop, and grades each hop
through `CRAGEvaluator` (`CONFIDENT` / `AMBIGUOUS` / `REFUSE`) — `AMBIGUOUS` triggers query reformulation
and retry, `REFUSE` returns an explicit refusal rather than an answer. `ContextCompactor` then packs results
into the token budget. The `/api/v1/chat` `mode` field selects the path: `auto`, `agentic`, `graph`, `direct`.

**Citations are the invariant.** Every `Block`, `Chunk`, `Candidate` and `Citation` carries
`doc_id`, `page`, and `bbox` `[x0, y0, x1, y1]`. Compaction, dedup and table pruning must preserve the bbox
— `/api/v1/preview` renders it onto the page image, so dropping it breaks visual provenance downstream.

**Document identity.** `doc_id` is `{filename_stem_lowercased}_{sha256(content)[:8]}` — content-addressed,
so re-ingesting an identical file is a no-op and an edited file gets a new id. The scheduler dedups on this.

**Token budget.** Generation targets ~4,972 tokens inside an 8K Ollama window (≈3,072 for context passages,
top-6 × 512). This is a hard constraint of the 6 GB VRAM target, not a soft preference — widening context
defaults will push the model into CPU swap.

## Configuration

`load_config()` merges three layers in order: `configs/default.yaml` → profile overlay
`configs/profiles/{quality,fast}.yaml` → environment variables. Profile is selected by the `RAG_PROFILE`
env var, else `hardware.profile` in the YAML. `quality` = `llama3.1:8b`, `fast` = `llama3.2:3b` (fully
VRAM-resident). Add new tunables to the YAML plus the matching Pydantic model in
`services/common/config.py` — nothing reads settings from the environment directly.

Env overrides are opt-in per key and enumerated explicitly at the bottom of `load_config()`:
`POSTGRES_{HOST,PORT,DB,USER,PASSWORD}`, `QDRANT_{HOST,PORT}`, `REDIS_{HOST,PORT}`, `OLLAMA_BASE_URL`.
**Adding a setting that must work in Docker means adding its override there too** — the YAML defaults are
all `127.0.0.1`, which is wrong inside a container, and compose supplies service names through these vars.

## Gotchas

- **CWD-dependent paths.** `services/graph/store.py`, `services/feedback/store.py` and
  `services/ingestion/multimodal.py` use relative paths (`Path("data/graph")`, `data/ragops`,
  `data/figures`), so they only resolve when run from the repo root. `bm25_store.py` resolves from
  `__file__` and works anywhere. Run everything from the repo root.
- **`data/` and `logs/` are gitignored** — they hold ingested source documents, the Qdrant volume, and
  derived indices/graph that contain extracted document text. Never commit them, and never commit an
  artifact derived from a document in `data/documents/`.
- Ollama must be reachable at `127.0.0.1:11434`; the gateway health check reports it but does not start it.
- Langflow credentials in `docker-compose.yml` are local dev defaults.

## Logging

`get_logger("<service.name>")` from `services/common/logger.py` writes to both colored console output and
`logs/<service.name>.log`. Log the decisions, not the data: routing choice, chunk counts, RRF and rerank
scores, stage latencies.

## Frontend

The web client is a single hand-written file, `ui/index.html` (no build step, no framework), served by the
gateway. Design tokens and component rules are in [`DESIGN.md`](DESIGN.md); behavioral rules and the
component reuse hierarchy are in [`docs/frontend-guidelines.md`](docs/frontend-guidelines.md); agent-facing
UI directives are in [`AGENTS.md`](AGENTS.md). Match the existing dark zinc/obsidian aesthetic — hairline
1px borders over drop shadows, monospace for all metadata and numerics.
