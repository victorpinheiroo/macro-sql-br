"""Verification for generated SQL.

Layer 1 (static, deterministic): the catalog says how each series must be aggregated; the AST
says how the SQL aggregates it. A mismatch is a finding. No LLM involved.

Layer 2 (differential): when the question maps to the catalog, the metrics path is the reference
and any divergence beyond tolerance is a finding.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from macrosql.metrics import Catalog


@dataclass(frozen=True)
class Finding:
    rule: str
    detail: str


def _series_ids_in_scope(select: exp.Select) -> set[int]:
    ids: set[int] = set()
    where = select.args.get("where")
    if where is None:
        return ids
    for eq in where.find_all(exp.EQ):
        if isinstance(eq.left, exp.Column) and eq.left.name.lower() == "series_id":
            if isinstance(eq.right, exp.Literal):
                ids.add(int(eq.right.this))
    for in_ in where.find_all(exp.In):
        if isinstance(in_.this, exp.Column) and in_.this.name.lower() == "series_id":
            ids |= {int(e.this) for e in in_.expressions if isinstance(e, exp.Literal)}
    return ids


def _refs_value(node: exp.Expression) -> bool:
    return any(c.name.lower() == "value" for c in node.find_all(exp.Column))


def _aggregation_patterns(select: exp.Select) -> set[str]:
    """Classify how this SELECT aggregates the `value` column."""
    found: set[str] = set()
    for agg in select.find_all(exp.AggFunc):
        if agg.find_ancestor(exp.Select) is not select or not _refs_value(agg):
            continue
        if isinstance(agg, exp.Sum):
            found.add("compound" if agg.find(exp.Ln) else "sum")
        elif isinstance(agg, exp.Avg):
            found.add("avg")
        elif isinstance(agg, (exp.ArgMax, exp.Max, exp.Min, exp.ArgMin, exp.Last)):
            found.add("last")
        else:
            found.add(type(agg).__name__.lower())
    return found


def aggregation_mismatch(sql: str, catalog: Catalog, dialect: str = "duckdb") -> list[Finding]:
    """Flag any SELECT that aggregates a series differently from its catalog rule.

    Covers: inflation summed instead of compounded; a level (Selic target) compounded or summed;
    a series swapped for one with a different rule.
    """
    metric_by_id = {m.source.series_id: m for m in catalog.metrics.values() if m.source}
    findings = []
    tree = sqlglot.parse_one(sql, read=dialect)
    for select in tree.find_all(exp.Select):
        patterns = _aggregation_patterns(select)
        if not patterns:
            continue
        for sid in _series_ids_in_scope(select):
            metric = metric_by_id.get(sid)
            if metric is None:
                findings.append(Finding("unknown_series", f"series {sid} is not in the catalog"))
                continue
            for p in patterns - {metric.aggregation}:
                findings.append(
                    Finding(
                        "aggregation_mismatch",
                        f"'{metric.name}' (series {sid}) aggregated as '{p}', "
                        f"catalog rule is '{metric.aggregation}'",
                    )
                )
    return findings


def differential(candidate: float, reference: float, abs_tol_pp: float = 0.01) -> list[Finding]:
    """Compare a free-SQL answer with the metrics-path answer, in percentage points."""
    if abs(candidate - reference) > abs_tol_pp:
        return [
            Finding(
                "differential",
                f"answer {candidate:.4f} differs from metrics path {reference:.4f}",
            )
        ]
    return []
