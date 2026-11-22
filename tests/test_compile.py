from datetime import date

import pytest

from macrosql.compile import Plan, compile_plan
from macrosql.guardrails import check

Q1 = dict(start=date(2024, 1, 1), end=date(2024, 3, 31))


def test_inflation_is_compounded_not_summed(con, catalog):
    sql = compile_plan(Plan(metrics=["ipca"], **Q1), catalog)
    value = con.execute(sql).fetchone()[0]
    expected = (1.01 * 1.02 * 1.03 - 1) * 100  # 6.1106
    assert value == pytest.approx(expected)
    assert value != pytest.approx(6.0)  # the classic wrong answer: 1 + 2 + 3


def test_real_rate_uses_fisher_not_subtraction(con, catalog):
    sql = compile_plan(Plan(metrics=["juro_real"], **Q1), catalog)
    value = con.execute(sql).fetchone()[0]
    selic = 1.01**3 - 1
    ipca = 1.01 * 1.02 * 1.03 - 1
    assert value == pytest.approx(((1 + selic) / (1 + ipca) - 1) * 100)
    assert value != pytest.approx((selic - ipca) * 100)


def test_level_series_takes_last_value(con, catalog):
    sql = compile_plan(Plan(metrics=["selic_meta"], **Q1), catalog)
    assert con.execute(sql).fetchone()[0] == pytest.approx(10.75)


def test_compiled_sql_passes_guardrails(catalog):
    sql = compile_plan(Plan(metrics=["juro_real", "selic_meta"], **Q1), catalog)
    check(sql)


def test_transpiles_to_databricks(catalog):
    sql = compile_plan(Plan(metrics=["ipca"], **Q1), catalog, dialect="databricks")
    assert "EXP" in sql.upper() and "LN" in sql.upper()


def test_plan_rejects_inverted_period():
    with pytest.raises(ValueError):
        Plan(metrics=["ipca"], start=date(2024, 3, 1), end=date(2024, 1, 1))


def test_unknown_metric_is_rejected(catalog):
    with pytest.raises(KeyError):
        compile_plan(Plan(metrics=["pib_magico"], **Q1), catalog)
