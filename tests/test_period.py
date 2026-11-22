from datetime import date

import pytest

from macrosql.compile import Plan, compile_plan
from macrosql.verify import period_mismatch

Y2024 = Plan(metrics=["ipca"], start=date(2024, 1, 1), end=date(2024, 12, 31))


def rules(findings):
    return [f.rule for f in findings]


def test_compiled_sql_has_no_period_finding(catalog):
    for metrics in (["ipca"], ["juro_real"], ["selic_meta"]):
        plan = Y2024.model_copy(update={"metrics": metrics})
        assert period_mismatch(compile_plan(plan, catalog), plan, catalog) == []


@pytest.mark.parametrize(
    "where",
    [
        "ref_date BETWEEN DATE '2024-01-01' AND DATE '2024-12-31'",
        "ref_date >= '2024-01-01' AND ref_date < '2025-01-01'",
        "EXTRACT(YEAR FROM ref_date) = 2024",
        "YEAR(ref_date) = 2024",
        "strftime(ref_date, '%Y') = '2024'",
        "date_trunc('year', ref_date) = DATE '2024-01-01'",
        # Monthly points are dated on day 1, so ending on Dec 1 selects the same 12 months.
        "ref_date BETWEEN '2024-01-01' AND '2024-12-01'",
    ],
)
def test_equivalent_filters_are_accepted(catalog, where):
    sql = f"SELECT SUM(value) FROM obs WHERE series_id = 433 AND {where}"
    assert period_mismatch(sql, Y2024, catalog) == []


@pytest.mark.parametrize(
    "where",
    [
        "ref_date BETWEEN '2023-12-01' AND '2024-12-31'",  # 13 months: the 12-month trap
        "ref_date BETWEEN '2024-02-01' AND '2024-12-31'",  # 11 months
        "YEAR(ref_date) = 2023",
        "ref_date > '2024-01-01' AND ref_date <= '2024-12-31'",  # drops January
    ],
)
def test_shifted_windows_are_flagged(catalog, where):
    sql = f"SELECT SUM(value) FROM obs WHERE series_id = 433 AND {where}"
    assert rules(period_mismatch(sql, Y2024, catalog)) == ["period_mismatch"]


def test_level_read_on_wrong_date_is_flagged_even_if_value_is_equal(catalog):
    """The case the differential misses: the target did not move between the two dates."""
    plan = Plan(metrics=["selic_meta"], start=date(2023, 1, 1), end=date(2023, 6, 30))
    sql = (
        "SELECT MAX_BY(value, ref_date) FROM obs WHERE series_id = 432 "
        "AND ref_date BETWEEN '2023-01-01' AND '2023-06-15'"
    )
    assert rules(period_mismatch(sql, plan, catalog)) == ["period_mismatch"]


def test_unreadable_or_open_filters_are_reported_not_guessed(catalog):
    base = "SELECT SUM(value) FROM obs WHERE series_id = 433 AND "
    assert rules(period_mismatch(base + "MONTH(ref_date) <= 6", Y2024, catalog)) == [
        "period_unverified"
    ]
    assert rules(
        period_mismatch(
            base + "(ref_date < '2020-01-01' OR ref_date > '2024-01-01')", Y2024, catalog
        )
    ) == ["period_unverified"]
    assert rules(period_mismatch(base + "ref_date >= '2024-01-01'", Y2024, catalog)) == [
        "period_open"
    ]
