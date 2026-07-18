# Routing Bench

Benchmarks NVIDIA-hosted models (OpenAI-compatible endpoint,
`https://integrate.api.nvidia.com/v1`) on stock-image search query
classification: for each query the model must emit, in a single call, a query
`type`, 1–3 `categories`, named `entities` (often correctly empty), and a
retrieval `route`. The gold set is frozen at `data/gold.jsonl` (77 rows).

## Layout

```
data/gold.jsonl     frozen gold labels — never rewritten by code
bench/models.yaml   model roster, methods per model, RPM budget, composite weights
bench/schema.py     enums, output JSON schema, tolerant parse + strict validation
bench/prompts.py    shared system prompt; json-mode / tool-call variants
bench/probe.py      one-off: verify catalog IDs + structured-output support
bench/runner.py     async runner -> results.jsonl (resumable)
bench/scorer.py     per-task metrics + composite leaderboard
bench/export.py     scorer output + per-query drill-down -> web/public/results.json
web/                Next.js static-export dashboard (Vercel-ready)
```

## Run

```sh
uv venv .venv && uv pip install -p .venv/bin/python httpx pyyaml
export NVIDIA_API_KEY=nvapi-…

.venv/bin/python bench/runner.py --limit 3   # smoke test
.venv/bin/python bench/runner.py             # full run (resumes if interrupted)
.venv/bin/python bench/scorer.py             # print leaderboard
.venv/bin/python bench/export.py             # -> web/public/results.json

cd web && npm install && npm run build       # static site in web/out
npx vercel deploy                            # or any static host
```

The API key is only ever read by `runner.py`/`probe.py`; the dashboard is a
static site reading `results.json` and never talks to NVIDIA.

## Methods (adherence is scored)

Every model runs each query under both structured-output methods it supports:

- **json_mode** — `response_format: {"type": "json_object"}` with the schema in
  the system prompt. If the server rejects `response_format`, the runner falls
  back to a strict-prompt parse and records `mode_used: strict_prompt`.
- **tool_call** — one tool `classify_query` whose parameters are the schema,
  with forced `tool_choice`.

Per model × method the scorer reports `json_valid_rate`, `schema_valid_rate`,
`tool_call_rate`, plus which mode actually served each call.

## Scoring

- type: accuracy + macro-F1
- categories (multi-label): micro + macro P/R/F1
- entities: entity-level F1, exact and partial (longest-common-substring
  overlap ≥ 0.5, greedy one-to-one); hallucination rate on the empty-entity rows
- route: accuracy + macro-F1 + 6×6 confusion (5 routes + abstain). Macro-F1 is
  primary: hybrid_v2 is 23/77 so accuracy rewards over-predicting it.
- ops: p50/p95 latency, output tokens, credits (1 per request incl. retries),
  malformed rate

Composite (weights frozen in `models.yaml`):

```
composite  = 0.45·route_macro_f1
           + 0.35·mean(type_macro_f1, category_macro_f1, entity_exact_f1)
           + 0.10·schema_valid_rate
           + 0.10·efficiency
efficiency = 1/(p95_latency_s · credits_per_query), normalized to [0,1] by the
             max across leaderboard rows
```

## Model roster notes (probed 2026-07-15)

Verified live against `GET /v1/models` + a per-model probe (`bench/probe.py`).
`mistralai/mistral-7b-instruct-v0.3` and `google/gemma-3-12b-it` appear in the
catalog but return 404 "not found for account", so the small tier substitutes
other 7–14B-class models. The catalog moves — re-run `probe.py` before trusting
`models.yaml`.
