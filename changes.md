# Changes

## IRA-60 — Source upload/parse runs on the backend; progress survives tab changes

**Problem.** On the project Sources tab, switching tabs while a file was uploading/parsing made the
progress indicator and the file disappear. Add-a-source was a client-driven chain (`/ingest` ->
`/index` -> `/files`) whose progress lived in the Sources screen's `State`, so leaving the tab disposed
it, and a page reload killed the chain with nothing recorded server-side.

**Fix.** The gateway owns the chain. An upload (or URL) returns a job immediately; a small thread pool
parses, indexes and attaches it to the project, recording each stage; clients poll the job list.

- `contracts/ingest_job.py` (new): `IngestJob` (status `queued|running|done|failed`, `stage`, `doc_id`,
  `blocks`, `error`) and request/list models.
- `services/ingestion/jobs.py` (new): `IngestJobStore` (Redis hash `rag:ingest_jobs`, in-memory fallback;
  finished jobs expire after 24 h) and `IngestJobRunner` (2 workers). A job still queued/running under a
  different `runner_id` belongs to a gateway process that no longer exists and is reported failed
  ("restarted while in progress") instead of spinning forever.
- `services/gateway/api.py`: `POST /api/v1/ingest/jobs` (multipart, `session_id` + `route`) and
  `POST /api/v1/ingest/jobs/url` -> 202 + job; `GET /api/v1/ingest/jobs?session_id=`;
  `DELETE /api/v1/ingest/jobs/{id}` (finished jobs only). Index and attach bodies are now the reusable
  `_index_owned` / `_attach_to_session` (same ownership rules); indexing is serialised by a lock because
  BM25/graph are in-process state. `/api/v1/ingest`, `/ingest/url`, `/index` are unchanged.
- Flutter: `IngestJobsNotifier` (`ingestJobsProvider`, app-level, polls every 1.5 s while a job is active)
  replaces `uploadIngestIndexAndAttach` / `ingestUrlIndexAndAttach`; the Sources screen renders jobs from
  it (spinner + stage, failed rows with the error and a dismiss button). A file still being sent shows
  as a local "Uploading" row, and a rejected upload becomes a dismissible failed row rather than vanishing.
  When a job finishes the project and library lists refresh.
- Tests: `tests/unit/test_ingest_jobs.py` (9), `app_flutter/test/ingest_jobs_test.dart` (4),
  `app_flutter/test/project_sources_progress_test.dart` (leave the tab and return -> row still there).

**Verified.** Live gateway: POST returns 202 in ~0.15 s, stages `Parsing -> Indexing N blocks ->
Attaching -> Ready` observed from a separate client with no shared state, file attached, chat cites it.

**Heads-up.** On this machine `localhost` resolves to `::1` first and Docker's IPv6 proxy black-holes it, so
every *new* connection to `localhost:<port>` waits ~21 s before falling back to IPv4 (`127.0.0.1` is
instant). Not part of this change; use `127.0.0.1` in scripts.

## IRA-59 — Run reasoning models (qwen3.5:4b) without losing the answer

**Problem.** Reasoning models report the `thinking` capability in Ollama and write their reasoning to a
separate `thinking` field before `response`. The gateway caps generation at `NUM_PREDICT = 256` and reads
only `response`, so the reasoning used the whole budget and answers came back empty or truncated.
llama3.x has no thinking mode, which is why it worked.

**Fix.** Send `think: false` to models that advertise `thinking`; never to others (Ollama rejects the field).

- `services/common/ollama_options.py` (new): `supports_thinking()` reads `/api/show` capabilities (cached per
  base URL + model; failed lookups are not cached) and `no_think()` returns `{"think": False}` or `{}`.
- `services/gateway/chat_pipeline.py`: chat generate request spreads `no_think(...)`.
- `services/evaluation/online.py`: LLM judge (`num_predict: 8`) uses it.
- `services/evaluation/project.py`: question generator uses it.
- `tests/unit/test_ollama_options.py` (new): thinking model, plain model, lookup failure.

**Verified.** `ruff` clean, 256 unit tests pass; live: `qwen3.5:4b` answers in 21 tokens with no thinking
output, `llama3.1:latest` receives no extra field.

**Not changed.** The query decomposer is still hardcoded to `llama3.2:3b` (`decomposer.py:30`).
