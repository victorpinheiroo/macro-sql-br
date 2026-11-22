# macro-sql-br

Ask questions about Brazil's interest rates, inflation and public finances in plain language. An LLM
picks governed metrics; a deterministic layer computes them; a verifier catches the classic mistakes
models make with financial time series.

> Status: week 1 — real BCB data in a Databricks bronze/silver/gold pipeline; golden set v1
> (16 questions, external oracles) passes 16/16 on the metrics path in both DuckDB and Databricks.
> No LLM yet.
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

## Layout

```
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
  sgs.py            BCB SGS client, 10-year windows
pipelines/          Databricks: 00_egress_check.py, 01_bronze_sgs.py, 02_silver_gold.py
evals/golden.jsonl  questions, plans, expected numbers and where each number was published
data/snapshot/      gold snapshot (CSV) used by CI and the DuckDB mode
databricks.yml      Asset Bundle: wheel, schema, volume, scheduled serverless job
tests/              unit tests on synthetic fixtures
```
