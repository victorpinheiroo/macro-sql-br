from datetime import date, datetime

import duckdb
import pytest

from macrosql.ingest import bronze_rows, sgs_series, write_bronze
from macrosql.sgs import Observation

TS = datetime(2026, 11, 18, 4, 0, 0)


def test_catalog_series_are_collected(catalog):
    assert sgs_series(catalog) == sorted(
        {m.source.series_id for m in catalog.metrics.values() if m.source}
    )


def test_bronze_is_append_only(tmp_path):
    rows = bronze_rows([Observation(series_id=432, ref_date=date(2024, 1, 2), value=11.75)], TS)
    path = write_bronze(rows, tmp_path, TS)
    got = duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}')").fetchall()
    assert got == [(432, date(2024, 1, 2), 11.75, TS)]
    with pytest.raises(FileExistsError):
        write_bronze(rows, tmp_path, TS)
