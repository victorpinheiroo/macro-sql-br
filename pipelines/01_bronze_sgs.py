"""Bronze: fetch every SGS series in the metrics catalog and append it to Delta.

Runs as a serverless Python task (see databricks.yml). Each run:
  1. fetches the full history from --start for every `bcb_sgs` metric,
  2. writes one Parquet file to the `landing` volume (never overwritten),
  3. appends those rows to `<catalog>.<schema>.sgs_observations`.

Same code path as `python -m macrosql.ingest` on a laptop; only the destination changes.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from pyspark.sql import SparkSession

from macrosql import sgs
from macrosql.ingest import bronze_rows, sgs_series, write_bronze
from macrosql.metrics import load_catalog


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    # Passed in by the bundle: development mode prefixes schema names, so never hardcode it.
    p.add_argument("--schema", required=True)
    p.add_argument("--metrics", type=Path, required=True)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = p.parse_args()

    ingested_at = datetime.now(UTC).replace(tzinfo=None)
    rows = []
    for series_id in sgs_series(load_catalog(args.metrics)):
        obs = sgs.fetch(series_id, args.start, args.end)
        print(f"series {series_id}: {len(obs)} observations")
        rows += bronze_rows(obs, ingested_at)
    if not rows:
        raise RuntimeError("SGS returned no observations at all; refusing to land an empty run")

    # DuckDB writes to local disk first; the file is then copied to the UC volume.
    with tempfile.TemporaryDirectory() as tmp:
        local = write_bronze(rows, Path(tmp), ingested_at)
        landing = Path(f"/Volumes/{args.catalog}/{args.schema}/landing/sgs")
        landing.mkdir(parents=True, exist_ok=True)
        dest = landing / local.name
        if dest.exists():
            raise FileExistsError(f"{dest} exists; bronze is append-only")
        shutil.copy(local, dest)
    print(f"landed {dest}")

    spark = SparkSession.builder.getOrCreate()
    table = f"{args.catalog}.{args.schema}.sgs_observations"
    (
        spark.read.parquet(str(dest))
        .write.format("delta")
        .mode("append")
        .option("mergeSchema", "false")
        .saveAsTable(table)
    )
    n = spark.sql(f"SELECT COUNT(*) FROM {table} WHERE ingested_at = '{ingested_at}'").first()[0]
    print(f"appended {n} rows to {table}")
    if n != len(rows):
        raise RuntimeError(f"row count mismatch: fetched {len(rows)}, landed {n}")


if __name__ == "__main__":
    main()
