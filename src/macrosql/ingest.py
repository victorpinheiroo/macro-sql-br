"""Bronze ingestion for every SGS-backed metric in the catalog.

Runs anywhere Python runs (laptop, GitHub Actions, Databricks). Output is append-only Parquet:
each run writes a new file stamped with `ingested_at`, so later runs never overwrite earlier ones.
That keeps "as of" questions and revision tracking possible later, if we decide to claim them.

    python -m macrosql.ingest --start 2015-01-01 --out data/bronze
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from macrosql import sgs
from macrosql.metrics import Catalog, load_catalog


def bronze_rows(
    observations: list[sgs.Observation], ingested_at: datetime
) -> list[tuple[int, date, float, datetime]]:
    return [(o.series_id, o.ref_date, o.value, ingested_at) for o in observations]


def write_bronze(rows: list[tuple], out_dir: Path, ingested_at: datetime) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sgs_{ingested_at:%Y%m%dT%H%M%SZ}.parquet"
    if path.exists():
        raise FileExistsError(f"{path} exists; bronze is append-only")
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE b (series_id INT, ref_date DATE, value DOUBLE, ingested_at TIMESTAMP)"
    )
    con.executemany("INSERT INTO b VALUES (?, ?, ?, ?)", rows)
    con.execute(f"COPY b TO '{path.as_posix()}' (FORMAT parquet)")
    return path


def sgs_series(catalog: Catalog) -> list[int]:
    return sorted(
        {
            m.source.series_id
            for m in catalog.metrics.values()
            if m.source and m.source.system == "bcb_sgs"
        }
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    p.add_argument("--out", type=Path, default=Path("data/bronze"))
    p.add_argument("--metrics", type=Path, default=Path("metrics"))
    args = p.parse_args()

    ingested_at = datetime.now(UTC).replace(tzinfo=None)
    rows = []
    for series_id in sgs_series(load_catalog(args.metrics)):
        obs = sgs.fetch(series_id, args.start, args.end)
        print(f"series {series_id}: {len(obs)} observations")
        rows += bronze_rows(obs, ingested_at)
    print(f"wrote {write_bronze(rows, args.out, ingested_at)}")


if __name__ == "__main__":
    main()
