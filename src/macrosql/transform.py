"""Bronze -> silver -> gold, written once in DuckDB SQL and transpiled for Databricks.

silver.sgs_observations   latest landed value per (series, ref_date), typed with the catalog's
                          frequency and unit, and an `is_complete` flag: a monthly point dated in
                          the month it was collected is still accumulating (e.g. SGS 4390 shows
                          the current month mid-way), so it is kept but flagged.
gold.obs                  what the compiler reads: complete points only.
gold.series_status        per series: last complete reference date and when it was collected.
                          "Latest data" answers come from here, never from MAX(ref_date) alone.

    python -m macrosql.transform --bronze "data/bronze/*.parquet" --out data/snapshot
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import duckdb
import sqlglot

from macrosql.metrics import Catalog, load_catalog


@dataclass(frozen=True)
class Tables:
    bronze: str
    silver: str
    gold_obs: str
    gold_status: str


def _series_values(catalog: Catalog) -> str:
    rows = [
        f"({m.source.series_id}, '{m.name}', '{m.frequency}', '{m.unit}')"
        for m in sorted(catalog.metrics.values(), key=lambda m: m.name)
        if m.source is not None
    ]
    return ",\n    ".join(rows)


def statements(catalog: Catalog, t: Tables, dialect: str = "duckdb") -> list[str]:
    """The three CREATE statements, in dependency order, in the requested dialect."""
    silver = f"""
CREATE OR REPLACE TABLE {t.silver} AS
WITH ranked AS (
  SELECT b.series_id, b.ref_date, b.value, b.ingested_at,
         ROW_NUMBER() OVER (PARTITION BY b.series_id, b.ref_date ORDER BY b.ingested_at DESC) AS rn
  FROM {t.bronze} AS b
),
series AS (
  SELECT * FROM (VALUES
    {_series_values(catalog)}
  ) AS s(series_id, metric, frequency, unit)
)
SELECT r.series_id, s.metric, s.frequency, s.unit, r.ref_date, r.value, r.ingested_at,
       CASE
         WHEN s.frequency = 'monthly'
           THEN r.ref_date < CAST(DATE_TRUNC('month', r.ingested_at) AS DATE)
         WHEN s.frequency = 'quarterly'
           THEN r.ref_date < CAST(DATE_TRUNC('quarter', r.ingested_at) AS DATE)
         ELSE r.ref_date <= CAST(r.ingested_at AS DATE)
       END AS is_complete
FROM ranked AS r
JOIN series AS s ON s.series_id = r.series_id
WHERE r.rn = 1
"""
    gold_obs = f"""
CREATE OR REPLACE TABLE {t.gold_obs} AS
SELECT series_id, ref_date, value
FROM {t.silver}
WHERE is_complete
"""
    gold_status = f"""
CREATE OR REPLACE TABLE {t.gold_status} AS
SELECT series_id, metric, frequency, unit,
       MAX(CASE WHEN is_complete THEN ref_date END) AS last_complete_ref_date,
       MAX(ingested_at) AS collected_at,
       SUM(CASE WHEN is_complete THEN 0 ELSE 1 END) AS partial_points
FROM {t.silver}
GROUP BY series_id, metric, frequency, unit
"""
    return [
        sqlglot.transpile(s, read="duckdb", write=dialect)[0]
        for s in (silver, gold_obs, gold_status)
    ]


def build_local(con: duckdb.DuckDBPyConnection, bronze_glob: str, catalog: Catalog) -> None:
    """Run the transform in DuckDB with tables named like the compiler expects (`obs`)."""
    con.execute(f"CREATE OR REPLACE VIEW bronze AS SELECT * FROM read_parquet('{bronze_glob}')")
    for sql in statements(catalog, Tables("bronze", "silver", "obs", "series_status")):
        con.execute(sql)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bronze", required=True, help="glob of bronze Parquet files")
    p.add_argument("--out", type=Path, default=Path("data/snapshot"))
    p.add_argument("--metrics", type=Path, default=Path("metrics"))
    args = p.parse_args()

    con = duckdb.connect()
    build_local(con, Path(args.bronze).as_posix(), load_catalog(args.metrics))
    args.out.mkdir(parents=True, exist_ok=True)
    for table in ("obs", "series_status"):
        path = (args.out / f"{table}.csv").as_posix()
        con.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO '{path}' (HEADER)")
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"wrote {path} ({n} rows)")


if __name__ == "__main__":
    main()
