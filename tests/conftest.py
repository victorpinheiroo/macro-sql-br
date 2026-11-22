from datetime import date
from pathlib import Path

import duckdb
import pytest

from macrosql.metrics import load_catalog

ROOT = Path(__file__).resolve().parents[1]

# SYNTHETIC fixture values, chosen to make arithmetic easy to check by hand.
# They are NOT real IPCA/Selic figures. Real values come from the M1 ingest.
SYNTH_IPCA = [1.0, 2.0, 3.0]  # Jan-Mar
SYNTH_SELIC = [1.0, 1.0, 1.0]  # Jan-Mar


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(ROOT / "metrics")


@pytest.fixture()
def con(catalog):
    c = duckdb.connect()
    c.execute("CREATE TABLE obs (series_id INT, ref_date DATE, value DOUBLE)")
    ipca_id = catalog.get("ipca").source.series_id
    selic_id = catalog.get("selic").source.series_id
    meta_id = catalog.get("selic_meta").source.series_id
    rows = []
    for i, (p, s) in enumerate(zip(SYNTH_IPCA, SYNTH_SELIC, strict=True), start=1):
        rows.append((ipca_id, date(2024, i, 1), p))
        rows.append((selic_id, date(2024, i, 1), s))
    rows += [(meta_id, date(2024, 1, 2), 11.75), (meta_id, date(2024, 3, 21), 10.75)]
    c.executemany("INSERT INTO obs VALUES (?, ?, ?)", rows)
    return c
