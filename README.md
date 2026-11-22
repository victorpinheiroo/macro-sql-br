# macro-sql-br

Ask questions about Brazil's interest rates, inflation and public finances in plain language. An LLM
picks governed metrics; a deterministic layer computes them; a verifier catches the classic mistakes
models make with financial time series.

> Status: M0 — metrics layer, compiler, guardrails, two-layer verifier, mutation set, SGS ingest.
> See [docs/PLAN.md](docs/PLAN.md).

## Quickstart

```bash
uv sync
uv run pytest
```

Data pipeline on Databricks Free Edition (needs `databricks auth login` once):

```bash
databricks bundle deploy          # wheel + schema + volume + scheduled job
databricks bundle run ingest_sgs   # SGS -> bronze Delta table
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
  sgs.py            BCB SGS client, 10-year windows
pipelines/          Databricks: 00_egress_check.py (network test), 01_bronze_sgs.py (bronze job)
databricks.yml      Asset Bundle: wheel, schema, volume, scheduled serverless job
tests/              unit tests on synthetic fixtures
```
