# Changes

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
