from pathlib import Path

import pytest

from macrosql.golden import connect, load_cases, main, run_case
from macrosql.metrics import Catalog

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "golden.jsonl"
SNAPSHOT = ROOT / "data" / "snapshot" / "obs.csv"


@pytest.fixture(scope="module")
def snapshot():
    return connect(SNAPSHOT)


def _with_aggregation(catalog: Catalog, metric: str, aggregation: str) -> Catalog:
    metrics = dict(catalog.metrics)
    metrics[metric] = metrics[metric].model_copy(update={"aggregation": aggregation})
    return Catalog(metrics=metrics)


def test_golden_file_is_valid_and_has_external_oracles():
    cases = load_cases(GOLDEN)
    assert len(cases) >= 15
    assert all(c.oracle.kind != "planilha" for c in cases if c.oracle)


def test_golden_set_passes_on_snapshot():
    assert main([str(GOLDEN), "--data", str(SNAPSHOT), "--metrics", str(ROOT / "metrics")]) == 0


@pytest.mark.parametrize(
    "metric, wrong, trap",
    [("ipca", "sum", "inflation_summed"), ("selic_meta", "sum", "level_aggregated")],
)
def test_runner_catches_wrong_aggregation(snapshot, catalog, metric, wrong, trap):
    """The golden set must fail if the catalog regresses to the classic mistake."""
    broken = _with_aggregation(catalog, metric, wrong)
    cases = [c for c in load_cases(GOLDEN) if c.trap == trap]
    assert cases
    assert not any(run_case(c, snapshot, broken).passed for c in cases)
