# macro-sql-br

Ask questions about Brazil's interest rates, inflation and public finances in plain language. An LLM
picks governed metrics; a deterministic layer computes them; a verifier catches the classic mistakes
models make with financial time series.

> Status: week 3. Real BCB data in a Databricks bronze/silver/gold pipeline; LLM planner, free-SQL
> path, AST guardrails, sandboxed execution and a three-layer verifier, all measured below.

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

## Quickstart

```bash
uv sync
uv run pytest
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
prompts/            versioned prompts (planner.yml)
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
  plan_eval.py      planner end to end per model -> evals/results/planner.md
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
