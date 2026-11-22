"""Plan + catalog -> SQL. The LLM picks metrics and a period; this module writes the arithmetic."""

from __future__ import annotations

from datetime import date

import sqlglot
from pydantic import BaseModel, model_validator

from macrosql.metrics import Catalog, Metric

OBS_TABLE = "obs"  # gold table: (series_id INT, ref_date DATE, value DOUBLE)

_AGG_SQL = {
    # Rates in percent are compounded, never summed: prod(1 + r) - 1.
    "compound": "(EXP(SUM(LN(1 + value / 100))) - 1) * 100",
    "sum": "SUM(value)",
    "avg": "AVG(value)",
    "last": "MAX_BY(value, ref_date)",
}


class Plan(BaseModel):
    """Structured output the planner LLM must produce (validated, never trusted as text)."""

    metrics: list[str]
    start: date
    end: date

    @model_validator(mode="after")
    def _period(self) -> Plan:
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if not self.metrics:
            raise ValueError("plan needs at least one metric")
        return self


def _base_cte(m: Metric, start: date, end: date) -> str:
    assert m.source is not None and m.aggregation is not None
    return (
        f"{m.name} AS (\n"
        f"  SELECT {_AGG_SQL[m.aggregation]} AS {m.name}, COUNT(*) AS n_{m.name}\n"
        f"  FROM {OBS_TABLE}\n"
        f"  WHERE series_id = {m.source.series_id}\n"
        f"    AND ref_date BETWEEN DATE '{start.isoformat()}' AND DATE '{end.isoformat()}'\n"
        f")"
    )


def compile_plan(plan: Plan, catalog: Catalog, dialect: str = "duckdb") -> str:
    """Return one SELECT statement answering the plan in the requested SQL dialect."""
    requested = [catalog.get(n) for n in plan.metrics]

    bases: dict[str, Metric] = {}
    for m in requested:
        deps = [catalog.get(d) for d in m.derived.inputs] if m.derived else [m]
        for dep in deps:
            bases[dep.name] = dep

    ctes = [_base_cte(b, plan.start, plan.end) for b in bases.values()]
    select_cols = []
    for m in requested:
        expr = f"({m.derived.formula})" if m.derived else m.name
        select_cols.append(f"{expr} AS {m.name}")
    select_cols += [f"n_{b}" for b in bases]

    sql = (
        "WITH "
        + ",\n".join(ctes)
        + "\nSELECT "
        + ", ".join(select_cols)
        + "\nFROM "
        + " CROSS JOIN ".join(bases)
    )
    # Parse once in our canonical dialect; fails loudly if we generated something invalid.
    return sqlglot.transpile(sql, read="duckdb", write=dialect, pretty=True)[0]
