"""Mechanics of the seeded-error set on SYNTHETIC data.

These tests prove the harness works. They are NOT the headline numbers: those come from running
the same harness on real data and the real golden set.
"""

from datetime import date

from macrosql.compile import Plan, compile_plan
from macrosql.mutation_report import format_report, run
from macrosql.mutations import _shift_month, generate
from macrosql.verify import aggregation_mismatch, differential

Q1 = dict(start=date(2024, 1, 1), end=date(2024, 3, 31))
PLANS = [
    Plan(metrics=["ipca"], **Q1),
    Plan(metrics=["selic"], **Q1),
    Plan(metrics=["selic_meta"], **Q1),
    Plan(metrics=["juro_real"], **Q1),
]


def test_every_operator_produces_mutants(catalog):
    ops = {m.operator for m in generate(PLANS, catalog)}
    assert ops == {
        "rate_summed",
        "level_compounded",
        "series_swap",
        "fisher_as_subtraction",
        "period_shift",
    }


def test_mutants_differ_from_reference(catalog):
    for m in generate(PLANS, catalog):
        assert m.mutant_sql != m.reference_sql, m.description


def test_static_layer_catches_aggregation_errors(catalog):
    for m in generate(PLANS, catalog):
        if m.operator in {"rate_summed", "level_compounded"}:
            assert aggregation_mismatch(m.mutant_sql, catalog), m.description


def test_static_layer_has_no_false_alarms_on_correct_sql(catalog):
    for p in PLANS:
        assert aggregation_mismatch(compile_plan(p, catalog), catalog) == []


def test_fisher_subtraction_needs_differential_layer(con, catalog):
    (m,) = [x for x in generate(PLANS, catalog) if x.operator == "fisher_as_subtraction"]
    assert aggregation_mismatch(m.mutant_sql, catalog) == []  # static is blind to this one
    ref = con.execute(m.reference_sql).fetchone()[0]
    got = con.execute(m.mutant_sql).fetchone()[0]
    assert differential(got, ref)


def test_report_runs_end_to_end(con, catalog):
    result = run(PLANS, catalog, con)
    text = format_report(result)
    assert "rate_summed" in text and "false alarms" in text
    assert result["static_false_alarms"] == 0


def test_shift_month_crosses_year():
    assert _shift_month(date(2024, 12, 15), 1) == date(2025, 1, 1)
