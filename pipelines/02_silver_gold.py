"""Silver + gold on Databricks: the same SQL as `macrosql.transform`, transpiled by sqlglot.

Runs after 01_bronze_sgs.py in the same job. Ends by exporting gold `obs` as Parquet to the
`exports` volume, which is what the DuckDB / Docker mode reads.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyspark.sql import SparkSession

from macrosql.metrics import load_catalog
from macrosql.transform import Tables, statements


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--bronze-schema", required=True)
    p.add_argument("--silver-schema", required=True)
    p.add_argument("--gold-schema", required=True)
    p.add_argument("--metrics", type=Path, required=True)
    args = p.parse_args()

    c = args.catalog
    t = Tables(
        bronze=f"{c}.{args.bronze_schema}.sgs_observations",
        silver=f"{c}.{args.silver_schema}.sgs_observations",
        gold_obs=f"{c}.{args.gold_schema}.obs",
        gold_status=f"{c}.{args.gold_schema}.series_status",
    )
    spark = SparkSession.builder.getOrCreate()
    for sql in statements(load_catalog(args.metrics), t, dialect="databricks"):
        spark.sql(sql)

    for row in spark.table(t.gold_status).orderBy("series_id").collect():
        print(row.asDict())
    n_gold = spark.table(t.gold_obs).count()
    if n_gold == 0:
        raise RuntimeError("gold obs is empty")

    export = f"/Volumes/{c}/{args.gold_schema}/exports/obs"
    spark.table(t.gold_obs).coalesce(1).write.mode("overwrite").parquet(export)
    print(f"gold obs: {n_gold} rows, exported to {export}")


if __name__ == "__main__":
    main()
