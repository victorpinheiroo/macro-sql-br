# macro-sql-br

Ask questions about Brazil's interest rates, inflation and public finances in plain language. An LLM
picks governed metrics; a deterministic layer computes them; a verifier catches the classic mistakes
models make with financial time series.

> Status: week 4. Real BCB data in a Databricks bronze/silver/gold pipeline; LLM router and
> planner, free-SQL path, AST guardrails, sandboxed execution, a three-layer verifier, clarification
> and confidence; FastAPI + Streamlit, one `docker compose up`. Everything below is measured.

## Headline numbers

31 golden questions with expected answers taken from IBGE publications and the BCB calculator,
8 free models hosted on Databricks Free Edition, 248 answers per path.

| | metrics path (LLM picks metrics) | free SQL (LLM writes the SQL) |
| --- | --- | --- |
| correct answers | **244/248 (98%)** | **78/248 (31%)**, from 2/31 to 21/31 per model |

| verifier on the 142 wrong free-SQL answers | caught |
| --- | --- |
| all layers (static rules + period check + differential vs metrics path) | **142/142** |
| without the differential (what still works for out-of-catalog questions) | 119/142 (84%) |
| flags on the 78 answers inside tolerance | 4, all IPCA *summed* instead of compounded that landed within 0.02 p.p. on a 6-month window |

The classic mistake shows up exactly as expected: asked for 2024 inflation, models writing their
own SQL sum the monthly IPCA (4.73%) instead of compounding it (4.83%, IBGE).

Red team: 12 adversarial questions (DROP, COPY, ATTACH, file and network reads, catalog probes,
stacked statements): **0 unsafe queries executed**, gold tables unchanged. Seeded mutations on real
data: 114/114 caught, 0/31 false alarms. Details in [evals/results](evals/results).

### End to end: routing decides the model

The same 8 models, now also deciding *how* to answer (metrics, free SQL, ask back, decline), on
43 questions: the 31 above plus ambiguous ones ("Selic" alone), data not yet complete (November
2026 asked on Nov 22), out-of-catalog data (exchange rate, GDP) and forecasts or advice.

| model | correct | metrics | free SQL | clarify | decline | route ok | median model time (s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| databricks-meta-llama-3-3-70b-instruct | **33/43** | 24/31 | 2/3 | 2/4 | 5/5 | 34/43 | 1.9 |
| databricks-llama-4-maverick | **41/43** | 30/31 | 2/3 | 4/4 | 5/5 | 41/43 | 1.0 |
| databricks-meta-llama-3-1-8b-instruct | **9/43** | 3/31 | 0/3 | 1/4 | 5/5 | 12/43 | 0.7 |
| databricks-gpt-oss-120b | **40/43** | 30/31 | 3/3 | 3/4 | 4/5 | 41/43 | 1.3 |
| databricks-gpt-oss-20b | **36/43** | 25/31 | 2/3 | 4/4 | 5/5 | 39/43 | 1.4 |
| databricks-qwen3-next-80b-a3b-instruct | **40/43** | 29/31 | 2/3 | 4/4 | 5/5 | 42/43 | 1.7 |
| databricks-qwen35-122b-a10b | **42/43** | 30/31 | 3/3 | 4/4 | 5/5 | 43/43 | 2.0 |
| databricks-gemma-3-12b | **37/43** | 26/31 | 2/3 | 4/4 | 5/5 | 39/43 | 1.0 |

Routing is where models separate: Llama 3.3 70B scores 31/31 when only planning, but sends
answerable questions to "unavailable" once it also routes. The default model in
[config/models.yml](config/models.yml) is picked from this table. Incomplete periods are caught
deterministically after planning (never left to the model): the answer becomes a clarification
offering the last complete month.

## Run it

```bash
docker compose up                  # API on :8000, app on :8501, committed gold snapshot
```

No account needed for the catalog and the deterministic path:

```bash
curl localhost:8000/v1/metrics
curl -X POST localhost:8000/v1/compute -H 'content-type: application/json' \
     -d '{"metrics": ["ipca"], "start": "2024-01-01", "end": "2024-12-31"}'
```

Questions in natural language (`POST /v1/ask`, or the app) need a model provider:

```bash
DATABRICKS_HOST=... DATABRICKS_TOKEN=... docker compose up            # Databricks Free Edition
MACROSQL_MODEL=ollama:qwen2.5:3b docker compose --profile ollama up   # fully local, ~2 GB pull
```

## Develop

```bash
uv sync
uv run pytest
uv run uvicorn macrosql.api:app --app-dir src     # API
uv run streamlit run app/streamlit_app.py         # app (API_URL, default localhost:8000)
```

Data pipeline on Databricks Free Edition (needs `databricks auth login` once):

```bash
databricks bundle deploy          # wheel + schema + volume + scheduled job
databricks bundle run ingest_sgs   # SGS -> bronze -> silver -> gold
```

Golden set (metrics path) on the committed gold snapshot, no Databricks account needed:

```bash
uv run python -m macrosql.golden evals/golden.jsonl --data data/snapshot/obs.csv
```

Planner (question -> plan -> number) per model, needs `databricks auth login`; responses are
cached in `.cache/llm`:

```bash
uv run python -m macrosql.plan_eval            # models listed in config/models.yml
uv run python -m macrosql.freesql_eval         # free-SQL path + verifier recall
uv run python -m macrosql.redteam              # adversarial questions, unsafe queries executed
uv run python -m macrosql.mutation_report      # seeded mistakes on real data
```

## Layout

```
config/models.yml   which model plans; which models are compared
prompts/            versioned prompts (planner.yml, freesql.yml)
app/                Streamlit front end (renders the API, no logic)
metrics/            one YAML per metric: source series, frequency, unit, aggregation rule
src/macrosql/
  metrics.py        catalog loader + validation
  compile.py        plan -> SQL (DuckDB canonical, transpiled with sqlglot)
  guardrails.py     AST checks: single SELECT, table allowlist, no file access, LIMIT cap
  verify.py         static catalog rules, period check (AST date filters), differential
  mutations.py      seeded wrong queries; mutation_report.py scores the verifier
  ingest.py         SGS -> append-only bronze Parquet with ingested_at
  transform.py      bronze -> silver -> gold, one SQL for DuckDB and Databricks
  golden.py         golden-set runner: compile, guardrail, execute, compare to the oracle
  llm.py            provider-neutral LLMClient, disk cache, structured output, backoff
  plan.py           question -> validated Plan (schema + catalog)
  ask.py            one question end to end: plan, route, freshness, compute, verify
  confidence.py     composite confidence score with the reasons shown to the user
  api.py            FastAPI: /v1/ask, /v1/compute, /v1/metrics, /v1/history
  plan_eval.py      end to end per model on the golden set -> evals/results/planner.md
  freesql.py        free-SQL path: model writes SQL -> guardrails -> sandboxed DuckDB
  freesql_eval.py   free SQL vs metrics path, verifier recall and false alarms
  redteam.py        adversarial questions against the free-SQL path
  sgs.py            BCB SGS client, 10-year windows
pipelines/          Databricks: 00_egress_check.py, 01_bronze_sgs.py, 02_silver_gold.py
evals/golden.jsonl  questions, plans, expected numbers and where each number was published
data/snapshot/      gold snapshot (CSV) used by CI and the DuckDB mode
databricks.yml      Asset Bundle: wheel, schema, volume, scheduled serverless job
tests/              unit tests on synthetic fixtures
```
