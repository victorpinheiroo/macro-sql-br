"""Seeded-error set: the denominator for "% of classic mistakes caught by the verifier".

Each operator produces a WRONG query for a question whose correct query we know. We mutate the
catalog or the plan (not SQL strings), so every mutant is valid SQL that runs and returns a
believable number, which is exactly what makes these mistakes dangerous.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date

from macrosql.compile import Plan, compile_plan
from macrosql.metrics import Catalog


@dataclass(frozen=True)
class Mutant:
    operator: str
    description: str
    plan: Plan
    reference_sql: str
    mutant_sql: str


def _shift_month(d: date, months: int) -> date:
    m = d.month - 1 + months
    return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)


def _with_metric(catalog: Catalog, name: str, **changes) -> Catalog:
    cat = catalog.model_copy(deep=True)
    metric = cat.metrics[name]
    for key, value in changes.items():
        parent, _, attr = key.rpartition(".")
        target = getattr(metric, parent) if parent else metric
        setattr(target, attr, value)
    return cat


Operator = Callable[[Plan, Catalog], Iterator[tuple[str, Plan, Catalog]]]


def rate_summed(plan, catalog):
    for name in plan.metrics:
        m = catalog.get(name)
        if m.aggregation == "compound":
            yield (
                f"{name}: compounded rate summed",
                plan,
                _with_metric(catalog, name, aggregation="sum"),
            )


def level_compounded(plan, catalog):
    for name in plan.metrics:
        m = catalog.get(name)
        if m.aggregation == "last":
            yield (
                f"{name}: level compounded",
                plan,
                _with_metric(catalog, name, aggregation="compound"),
            )
            yield f"{name}: level summed", plan, _with_metric(catalog, name, aggregation="sum")


def series_swap(plan, catalog):
    """Right formula, wrong series (e.g. Selic target where effective Selic was asked)."""
    for name in plan.metrics:
        m = catalog.get(name)
        if m.source is None:
            continue
        for other in catalog.metrics.values():
            if other.source and other.name != name and other.frequency == m.frequency:
                yield (
                    f"{name}: series swapped for {other.name}",
                    plan,
                    _with_metric(catalog, name, **{"source.series_id": other.source.series_id}),
                )


def fisher_as_subtraction(plan, catalog):
    for name in plan.metrics:
        if name == "juro_real":
            yield (
                "juro_real: selic - ipca instead of Fisher",
                plan,
                _with_metric(catalog, name, **{"derived.formula": "selic - ipca"}),
            )


def period_shift(plan, catalog):
    first_after_new_end = _shift_month(plan.end, 2)  # 1st day, two months after end's month
    shifted = Plan(
        metrics=plan.metrics,
        start=_shift_month(plan.start, 1),
        end=date.fromordinal(first_after_new_end.toordinal() - 1),
    )
    yield "period shifted by one month", shifted, catalog


def window_off_by_one(plan, catalog):
    """The 12-month trap: one extra month at the start (13 points instead of 12).

    Skipped when every metric is a level ('last'): an earlier start does not change the answer,
    so it would not be a mistake.
    """
    if all(catalog.get(n).aggregation == "last" for n in plan.metrics):
        return
    yield (
        "window starts one month early",
        Plan(metrics=plan.metrics, start=_shift_month(plan.start, -1), end=plan.end),
        catalog,
    )


OPERATORS: dict[str, Operator] = {
    "rate_summed": rate_summed,
    "level_compounded": level_compounded,
    "series_swap": series_swap,
    "fisher_as_subtraction": fisher_as_subtraction,
    "period_shift": period_shift,
    "window_off_by_one": window_off_by_one,
}


def generate(plans: list[Plan], catalog: Catalog) -> list[Mutant]:
    mutants = []
    for plan in plans:
        reference = compile_plan(plan, catalog)
        for op_name, op in OPERATORS.items():
            for description, m_plan, m_catalog in op(plan, catalog):
                mutants.append(
                    Mutant(
                        operator=op_name,
                        description=description,
                        plan=plan,
                        reference_sql=reference,
                        mutant_sql=compile_plan(m_plan, m_catalog),
                    )
                )
    return mutants
