# macro-sql-br

Ask questions about Brazil's interest rates, inflation and public finances in plain language. An LLM
picks governed metrics; a deterministic layer computes them; a verifier catches the classic mistakes
models make with financial time series.

> Status: week 2 — real BCB data in a Databricks bronze/silver/gold pipeline; LLM planner end to
> end on 8 free Databricks-hosted models ([results](evals/results/planner.md)). Golden set v1
> (16 questions, external oracles) is already saturated: 7 of 8 models score 16/16, so it cannot
> rank models yet. Harder questions come next.
> See [docs/PLAN.md](docs/PLAN.md).

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
  verify.py         static checks from the catalog + differential check vs the metrics path
  mutations.py      seeded wrong queries; mutation_report.py scores the verifier
  ingest.py         SGS -> append-only bronze Parquet with ingested_at
  transform.py      bronze -> silver -> gold, one SQL for DuckDB and Databricks
  golden.py         golden-set runner: compile, guardrail, execute, compare to the oracle
  llm.py            provider-neutral LLMClient, disk cache, structured output, backoff
  plan.py           question -> validated Plan (schema + catalog)
  plan_eval.py      planner end to end per model -> evals/results/planner.md
  sgs.py            BCB SGS client, 10-year windows
pipelines/          Databricks: 00_egress_check.py, 01_bronze_sgs.py, 02_silver_gold.py
evals/golden.jsonl  questions, plans, expected numbers and where each number was published
data/snapshot/      gold snapshot (CSV) used by CI and the DuckDB mode
databricks.yml      Asset Bundle: wheel, schema, volume, scheduled serverless job
tests/              unit tests on synthetic fixtures
```
