# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Issue tracking (Jira)

All work on this repo is tracked in Jira project **IRA** on `emailabhishek2.atlassian.net`
(cloudId `3452e1b8-4aa4-4627-bd49-cc769a985cef`, board
`https://emailabhishek2.atlassian.net/jira/software/projects/IRA/boards/134`). File every new bug, task
and feature there and reference its key (`IRA-NN`) in commit messages, docstrings and test names.
**Never file RAG work in project REC** — REC ("Stock Recommendations Engine") belongs to an unrelated
stock-app project.

- Issue types: Bug, Task, Story, Epic, Subtask. There is no Feature type — file features as a Story
  with the `feature` label.
- Labels in use: `rag`, `ui`, `gateway`, `project-scope`, `evaluation`, `prompting`, `answer-quality`,
  `performance`, `tech-debt`, `bug`.
- New issues are not auto-assigned; set the assignee explicitly. Done transition id is `31`.
- History: the RAG tickets were first filed in REC and moved on 2026-09-27 — REC-59…82 are now
  IRA-1…24 (`IRA-n` = `REC-(n+58)`). References in the code were rewritten, but commit messages up to
  that date still say `REC-NN`; use the mapping when reading `git log`.

## Commands

This is a Windows-primary repo. `Makefile` and `run.ps1` expose the same targets; use `run.ps1` when GNU
make is unavailable.

```bash
make check                              # ruff + full unit suite — the standard pre-commit gate
make test                               # unit tests only
make serve                              # gateway + web client on :8000
make eval                               # retrieval quality + faithfulness benchmark
make gate                               # regression gate; fails on metric regression vs baseline
make eval-chat                          # multi-turn answer-quality suite vs the live gateway (sampled, N trials)
make services-up / services-down        # full docker stack up/down
make ingestion-worker                   # Temporal worker: directory-scan schedule + ingest/index workflows
```

Docker: `docker-compose.yml` defines `qdrant`, `redis`, `gateway`, `temporal`, `temporal-ui`,
`ingestion-worker`, `langflow`, plus an opt-in `ollama` behind the `local-llm` profile — **not** `postgres`;
see Configuration below, Postgres is host-installed, not a compose service (Temporal is the one exception
that provisions its own databases, `temporal`/`temporal_visibility`, on that same host instance — see the
`temporal` service's comment in `docker-compose.yml`). `gateway` and `ingestion-worker` share one image
built from `Dockerfile` and differ only in their `command`. `docker compose up -d --build` runs everything;
`docker compose up -d qdrant redis` gives just the infrastructure for a local `make serve`.
`GATEWAY_HOST_PORT` in `.env` controls the host-side port for the dockerized gateway (defaults to 8001 in
`docker-compose.yml`, but is overridden to `8010` in this machine's `.env` — 8001 and 8000 both collide
with unrelated local projects here, one a Docker container, the other a native, non-Docker Django dev
server). `make serve`/`run.ps1 serve` (the native, non-Docker path) still hardcode port 8000 regardless —
that will also collide with the same native Django server if both run at once on this machine.

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

`tests/unit` mocks Qdrant, Redis and Ollama and runs with no infrastructure. `tests/integration`
and `tests/eval` require live Qdrant + Ollama (`tests/integration/test_identity_postgres.py` needs the migrated
auth database instead, and skips without it).

Unit tests run signed in: `tests/unit/conftest.py` gives every test a fresh `InMemoryIdentityStore`, overrides
the gateway's `optional_user` dependency with an admin `TEST_USER`, and disables the CSRF header check. Chat tests
need a project that can read a document — use the `make_project("doc_id")` fixture (a project with no readable
documents refuses every turn). Tests of auth itself request the `real_auth` fixture to drop the overrides.

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

**Background document scheduling (`services/scheduling/`).** Documents dropped straight into
`data/documents/` (not uploaded through the gateway) are picked up by a Temporal worker, not the gateway
process. `DirectoryScanWorkflow` runs on a recurring Temporal Schedule (`configs/default.yaml`'s
`scheduling.scan_interval_s`, default 60s) and fans each newly-discovered file out to its own
`DocumentIngestWorkflow` (workflow id `ingest-{sha256}`, matching `doc_id`'s own hash so a failed run is
traceable back to its file), which runs the same `IngestionService.parse()` → `IndexingService.chunk_and_index()`
pair the gateway's synchronous `/api/v1/index` route uses — **the interactive upload path stays synchronous
and does not go through Temporal**; only this background directory scan does. Retries are Temporal's own
(`INGEST_RETRY_POLICY`, 3 attempts per activity), not a manually-tracked counter: a document that exhausts
retries surfaces as a Failed workflow execution — visible in the Temporal UI (`:8081`) and in the admin DLQ
view (`/api/v1/queue/dlq`, backed by `services/scheduling/client.py`) — for a deliberate manual replay rather
than being silently retried forever. `services/scheduling/registry.py`'s `data/seen_documents.json` is the
single source of truth mapping a file's hash to its path; it's how both the scan activity's dedup and the
DLQ replay endpoint (recovering a failed run's original `file_path` from its workflow id, rather than parsing
raw Temporal history) work. Run it locally with `make ingestion-worker` / `.\run.ps1 ingestion-worker`; in
Docker it's the `ingestion-worker` service, needing `temporal` (and `qdrant`/`redis`) healthy first.

**Add-a-source jobs (IRA-60).** The Flutter client adds sources through `POST /api/v1/ingest/jobs` (file) and
`/ingest/jobs/url`, which return a job at once; `services/ingestion/jobs.py` runs parse → `_index_owned` →
`_attach_to_session` on a 2-thread pool inside the gateway (not Temporal) and records each stage in the Redis
hash `rag:ingest_jobs`. Clients poll `GET /api/v1/ingest/jobs?session_id=`; progress therefore survives tab
changes and reloads. A job left `running` by a previous gateway process is reported failed (`runner_id`
mismatch). The synchronous `/api/v1/ingest` + `/index` routes remain for the legacy web UI and scripts.
Restart the `rag_gateway` container after code changes — uvicorn does not reload the bind-mounted source.

**Retrieval layering.** `RetrievalService.retrieve()` is the plain hybrid path. Above it:
`AgenticCoordinator.run_plan()` decomposes into sub-queries, runs a retrieval per hop, and grades each hop
through `CRAGEvaluator` (`CONFIDENT` / `AMBIGUOUS` / `REFUSE`) — `AMBIGUOUS` triggers query reformulation
and retry, `REFUSE` returns an explicit refusal rather than an answer. `ContextCompactor` then packs results
into the token budget. The `/api/v1/chat` `mode` field selects the path: `auto`, `agentic`, `graph`, `direct`.

**One chat pipeline.** Every `/api/v1/chat` turn runs through `services/gateway/chat_pipeline.py::ChatPipeline`,
which yields typed events from `contracts/chat.py`. The streaming endpoint serializes them as SSE (`to_sse`)
and the non-streaming one folds them into JSON (`fold_to_response`) — change chat behavior there, never in
`api.py`, or the two transports drift apart again. All prompts are built by
`services/retrieval/prompting.py::build_grounded_prompt` (history → evidence → current question last).
`tests/unit/test_chat_pipeline_contract.py` pins the wire format for every mode.
A project with no `system_prompt` gets the grounding persona from `generation.default_system_prompt`
in `configs/default.yaml` (served to the UI at `/api/v1/prompts/default`). Oversized prompts go through
`fit_prompt`, which cuts the middle of the evidence so the persona and the "Current question:" tail survive.

**Citations are the invariant.** Every `Block`, `Chunk`, `Candidate` and `Citation` carries
`doc_id`, `page`, and `bbox` `[x0, y0, x1, y1]`. Compaction, dedup and table pruning must preserve the bbox
— `/api/v1/preview` renders it onto the page image, so dropping it breaks visual provenance downstream.

**Document identity.** `doc_id` is `{filename_stem_lowercased}_{sha256(content)[:8]}` — content-addressed,
so re-ingesting an identical file is a no-op and an edited file gets a new id. The ingestion worker's
directory-scan activity (`services/scheduling/activities.py`) dedups on this, independent of `doc_id` itself —
see Background Document Scheduling below.

**Accounts and isolation (IRA-32).** Every route is private by default: `auth_gate` (an app-level dependency in
`services/gateway/api.py`) requires a signed-in user except on `/`, `/s/{token}`, `/api/v1/health`,
`/api/v1/auth/*` and `/api/v1/public/*`. Handlers take the user through `Depends(current_user)` /
`Depends(require_admin)`, and project routes through `Depends(owned_session)`, which reports another user's
project as a 404. Login is a random token in the HttpOnly `ri_auth` cookie; state-changing requests must also
send `X-RI-Client: web` (or a same-origin `Origin`). Identity data — users, login sessions, document ownership
(`user_documents`), shares and read-only grants (`doc_grants`) — lives in Postgres behind
`services/identity/store.py`; projects and messages stay in Redis, stamped with `ChatSession.owner_id`.
- **The indexes are shared; access is not.** Identical uploads share one content-addressed doc_id (one ownership
  row per uploader). A user may read what they own, what a live share granted them, and the public web corpus
  (`services/identity/access.py::accessible_doc_ids`). Every scope handed to retrieval, the graph or file
  serving is `resolve_scope(files, accessible)` — exact doc_ids, never a raw filename, so the loose
  stem-matching in `doc_scope.py` can't reach another user's `report_<hash>`.
- **An empty scope refuses, it never widens.** `ChatTurnRequest.doc_ids == []` refuses without retrieving
  (`NO_DOCUMENTS_REFUSAL`); only `None` is unscoped, reserved for internal callers with no project. Never
  reintroduce `session.files or None` — that searched every user's documents.
- **Only the first uploader of a doc_id may re-index it** (`/api/v1/index`): blocks come from the client, so a
  later uploader of the same content could otherwise rewrite someone else's chunks.
- Cross-project views (`/metrics`, `/feedback/summary`, `/ragops/dataset` without `session_id`) and operator
  endpoints (HNSW rebuild, DLQ, web sync, benchmark eval) are admin-only.

**Share links (IRA-35).** `services/sharing/service.py` snapshots a project's messages (internal `metadata`
stripped) at a public `/s/<token>` URL; only the token's sha256 is stored. The snapshot's `doc_ids` are the
sharer's *owned* (or public) documents only — granted ones aren't re-published — and citations to anything else
are dropped. Viewers get citation previews through `/api/v1/public/shares/{token}/preview`, limited to those
docs. Forking copies the history into a new project the caller owns (so `build_conversation_context` continues
from it) and inserts `doc_grants`. Revoking kills the URL and its grants; forks keep their copied history but can
no longer retrieve the documents.

**Token budget.** Generation targets ~4,972 tokens inside an 8K Ollama window (≈3,072 for context passages,
top-6 × 512). This is a hard constraint of the 6 GB VRAM target, not a soft preference — widening context
defaults will push the model into CPU swap.

## Configuration

`load_config()` merges three layers in order: `configs/default.yaml` → profile overlay
`configs/profiles/{quality,fast}.yaml` → environment variables. Profile is selected by the `RAG_PROFILE`
env var, else `hardware.profile` in the YAML. `quality` = `llama3.1:latest` (the 8B model; there is no
`llama3.1:8b` tag installed here), `fast` = `llama3.2:3b` (fully VRAM-resident). `/api/v1/models` lists
only chat-capable models: `services/gateway/model_catalog.py` filters out the embedding and reranker
models Ollama also has installed, and `ChatPipeline` rejects one if a project still has it saved. Add new tunables to the YAML plus the matching Pydantic model in
`services/common/config.py` — nothing reads settings from the environment directly.

Env overrides are opt-in per key and enumerated explicitly at the bottom of `load_config()`:
`POSTGRES_{HOST,PORT,DB,USER,PASSWORD}`, `QDRANT_{HOST,PORT}`, `REDIS_{HOST,PORT}`,
`NEO4J_{URI,USER,PASSWORD,DATABASE}`, `OLLAMA_BASE_URL`.
**Adding a setting that must work in Docker means adding its override there too** — the YAML defaults are
all `127.0.0.1`, which is wrong inside a container, and compose supplies service names through these vars.
`docker-compose.yml` still defines no `neo4j` service — the override now exists so one can be pointed at
(local or external), but until it is, `neo4j_uri` stays `bolt://127.0.0.1:7687` inside a container (its own
loopback), which fails and falls back to a per-process, non-persistent in-memory graph (see Gotchas).

**Auth database.** Run `python -m services.identity.migrate` to create/upgrade the identity tables
(`migrations/*.sql`, tracked in `schema_migrations`) in `auth.database` (default `rag_db`, override with
`RAG_AUTH_DB`). This deliberately does not use `storage.postgres_db`: that honors `POSTGRES_DB`, which this
machine exports system-wide as `trackmyrupee`. Accounts: `python -m services.identity.cli create-admin <email>`
(password prompted, or `RAG_NEW_PASSWORD`); regular users can sign up in the UI unless `auth.allow_signup` is
false. "Try demo" on the sign-in card (`POST /api/v1/auth/demo`, IRA-38) creates a throwaway guest (`is_demo`,
`guest-…@demo.invalid`, random never-shown password, login of `auth.demo_session_hours`, capped per IP by
`auth.demo_max_per_hour`) — a normal isolated user, never admin; turn it off with `auth.allow_demo: false`. Guest
accounts and their projects are not purged automatically yet. `python -m services.identity.migrate --adopt-legacy <admin-email>` hands pre-accounts projects and indexed
documents to that admin — until it runs, those are invisible to everyone. It is idempotent; re-run it after
dropping files straight into `data/documents/` (ingestion-worker-indexed files have no uploader). The gateway falls
back to an in-memory identity store, loudly logged, when Postgres is down or unmigrated.

**Postgres is host-installed, not a `docker-compose` service** (migrated 2026-09-15). This machine already
runs a native PostgreSQL 16 service on `127.0.0.1:5432` (shared with unrelated local projects), database
`rag_db`. `docker-compose.yml`'s `x-app-env` pins `POSTGRES_HOST=host.docker.internal`,
`POSTGRES_DB=rag_db`, `POSTGRES_USER=postgres` directly (not `${VAR:-default}`) rather than reading them
from the shell, because this host also exports `POSTGRES_DB`/`POSTGRES_USER` system-wide for a different
project — letting compose substitution pick those up previously created a stray, wrongly-named database
inside the old `postgres` container. Only `POSTGRES_PASSWORD` is still read from the environment (already
correct system-wide, and mirrored in the gitignored `.env` for compose). Langflow (its own schema/migrations,
confirmed working against `rag_db`) and Temporal (its own `temporal`/`temporal_visibility` databases, see
Background Document Scheduling below) are the only current consumers of this Postgres instance — the app
services (gateway/ingestion-worker) load `storage.postgres_url` but nothing calls it today.

**Langflow's Knowledge Bases Postgres DB provider** (added 2026-09-15) is a second, separate use of the
same host Postgres instance — unrelated to `LANGFLOW_DATABASE_URL` above (Langflow's own app metadata).
Langflow's Settings > DB Providers > Postgres backend (`PostgresBackend` in `lfx.base.knowledge_bases.backends.postgres`)
is configured by one deployment-wide env var, `PGVECTOR_CONNECTION_STRING`
(`docker-compose.yml`'s `langflow` service), pointed at its own database, `langflow_vectors`, kept
separate from `rag_db` so KB embedding tables never collide with the app's own data. Connection string
must use the `postgresql+psycopg://` driver prefix (psycopg3), not plain `postgresql://`.

Two things had to be fixed beyond the env var, both now resolved:
- **`pgvector` Python package missing from the Langflow image.** `langflowai/langflow:latest` ships
  `psycopg`/`langchain-community` (for `LANGFLOW_DATABASE_URL`) but not the `pgvector` package that
  `PostgresBackend` imports from `pgvector.sqlalchemy` — it's behind the opt-in `langflow[pgvector]`
  extra, which no published image tag includes. Fixed by `docker/langflow.Dockerfile`
  (`FROM langflowai/langflow:latest` + `pip install pgvector>=0.4.2`), with `docker-compose.yml`'s
  `langflow` service building that instead of pulling the bare image.
- **`vector` extension missing from this host's native Windows PostgreSQL 16.** Unlike Linux
  (apt/yum packages), Windows has no official pgvector build. Installed via the third-party prebuilt
  binary `andreiramani/pgvector_pgsql_windows` (release `0.8.6_16`, sha256 verified against GitHub's
  reported digest before use) — stopped the `postgresql-x64-16` service, copied `lib\vector.dll` +
  `share\extension\vector*` into `C:\Program Files\PostgreSQL\16\`, restarted the service, then ran
  `CREATE EXTENSION vector;` on `langflow_vectors` (now `pgvector 0.8.6`). This touches a Postgres
  instance shared with unrelated local projects, so it was done deliberately (required an elevated
  terminal), not as a side effect of other work — the same steps would need repeating if this
  Postgres install is ever reinstalled/upgraded to a new major version.

Verified end-to-end 2026-09-15 via `PostgresBackend(...).test_connection()` inside the `rag_langflow`
container → `ok=True, message="Connected to Postgres 16.6 (pgvector 0.8.6)."`. The existing Qdrant +
BM25s retrieval stack this project actually serves is unaffected either way — this DB provider only
feeds Langflow's own built-in Knowledge Bases feature, not `services/retrieval`.

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

**Terminology:** the UI calls the scoped unit a **Project** (gallery = "Projects"). A Project is the backend
`ChatSession` (`/api/v1/sessions`, `session_id`): its `files` are the project's documents, `parameters` its
settings, and telemetry/feedback/eval are keyed by its `session_id`. JS identifiers and `localStorage` keys
still say `workspace` (`ri_workspace_model_*`) — keep them, renaming would drop saved per-project state.

**Signed-in client (IRA-36).** `ui/index.html` wraps `window.fetch` once so every same-origin call sends the auth
cookie and `X-RI-Client`, and a 401 opens the sign-in overlay (`#authGate`) — plain `fetch(...)` calls need no
changes. A `/s/<token>` URL (`SHARE_TOKEN`) renders the chat page read-only (`body.shared-view`), with inspector
previews/figures pointed at the public share endpoints. Chat text and citation fields can be another user's
content there: template them through `escapeHtmlText` / `htmlSafeCitation`, and never build inline event
handlers from them.
