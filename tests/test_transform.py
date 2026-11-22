from datetime import date, datetime

import duckdb
import pytest

from macrosql.ingest import write_bronze
from macrosql.transform import Tables, build_local, statements

T1 = datetime(2026, 11, 1, 12, 0)
T2 = datetime(2026, 11, 22, 12, 0)


@pytest.fixture()
def built(tmp_path, catalog):
    ipca = catalog.get("ipca").source.series_id
    selic = catalog.get("selic").source.series_id
    meta = catalog.get("selic_meta").source.series_id
    # Run 1 (Nov 1): October Selic complete but later revised; nothing for November yet.
    write_bronze(
        [
            (ipca, date(2026, 9, 1), 0.82, T1),
            (selic, date(2026, 10, 1), 1.00, T1),  # will be revised in run 2
            (meta, date(2026, 11, 1), 13.75, T1),
        ],
        tmp_path,
        T1,
    )
    # Run 2: October revised, November present but only half-way through the month.
    write_bronze(
        [
            (ipca, date(2026, 9, 1), 0.82, T2),
            (ipca, date(2026, 10, 1), 0.14, T2),
            (selic, date(2026, 10, 1), 1.07, T2),
            (selic, date(2026, 11, 1), 0.66, T2),
            (meta, date(2026, 11, 1), 13.75, T2),
            (meta, date(2026, 11, 22), 13.75, T2),
        ],
        tmp_path,
        T2,
    )
    con = duckdb.connect()
    build_local(con, (tmp_path / "*.parquet").as_posix(), catalog)
    return con, ipca, selic, meta


def test_silver_keeps_latest_landing_per_point(built):
    con, _, selic, _ = built
    got = con.execute(
        f"SELECT value FROM silver WHERE series_id = {selic} AND ref_date = DATE '2026-10-01'"
    ).fetchall()
    assert got == [(1.07,)]


def test_partial_month_is_flagged_and_kept_out_of_gold(built):
    con, _, selic, _ = built
    flag = con.execute(
        f"SELECT is_complete FROM silver WHERE series_id = {selic} AND ref_date = DATE '2026-11-01'"
    ).fetchone()[0]
    assert flag is False
    in_gold = con.execute(
        f"SELECT COUNT(*) FROM obs WHERE series_id = {selic} AND ref_date = DATE '2026-11-01'"
    ).fetchone()[0]
    assert in_gold == 0


def test_daily_point_on_collection_day_is_complete(built):
    con, _, _, meta = built
    n = con.execute(f"SELECT COUNT(*) FROM obs WHERE series_id = {meta}").fetchone()[0]
    assert n == 2


def test_status_reports_last_complete_point_and_collection_time(built):
    con, ipca, selic, _ = built
    rows = dict(
        (r[0], r[1:])
        for r in con.execute(
            "SELECT series_id, last_complete_ref_date, collected_at, partial_points "
            "FROM series_status"
        ).fetchall()
    )
    assert rows[selic] == (date(2026, 10, 1), T2, 1)
    assert rows[ipca] == (date(2026, 10, 1), T2, 0)


def test_statements_transpile_to_databricks(catalog):
    sqls = statements(catalog, Tables("c.b.t", "c.s.t", "c.g.obs", "c.g.status"), "databricks")
    assert len(sqls) == 3
    assert all(s.startswith("CREATE OR REPLACE TABLE") for s in sqls)
    assert "DATE_TRUNC('MONTH'" in sqls[0]
