"""Verification for generated SQL.

Layer 1 (static, deterministic): the catalog says how each series must be aggregated; the AST
says how the SQL aggregates it. A mismatch is a finding. No LLM involved.

Layer 2 (differential): when the question maps to the catalog, the metrics path is the reference
and any divergence beyond tolerance is a finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

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


# --- Layer 3: period check -------------------------------------------------------------------
# The differential misses a shifted period whenever the series did not move in between (e.g. the
# Selic target between two Copom meetings). So we read the date filter straight from the AST and
# compare the observations it selects with the ones the plan asks for.


def _as_date(node: exp.Expression) -> date | None:
    if isinstance(node, exp.Cast):
        node = node.this
    if isinstance(node, exp.Literal) and node.is_string:
        try:
            return date.fromisoformat(node.this[:10])
        except ValueError:
            return None
    return None


def _as_int(node: exp.Expression) -> int | None:
    if isinstance(node, exp.Literal):
        try:
            return int(str(node.this))
        except ValueError:
            return None
    return None


def _is_ref_date(node: exp.Expression) -> bool:
    return isinstance(node, exp.Column) and node.name.lower() == "ref_date"


def _year_of_ref_date(node: exp.Expression) -> bool:
    """YEAR(ref_date), EXTRACT(YEAR FROM ref_date), strftime(ref_date, '%Y')."""
    if isinstance(node, exp.Year):
        return _is_ref_date(node.this)
    if isinstance(node, exp.Extract):
        return node.this.name.upper() == "YEAR" and _is_ref_date(node.expression)
    if isinstance(node, exp.TimeToStr):
        return _is_ref_date(node.this) and node.args.get("format").name == "%Y"
    return False


_FLIP = {exp.GT: exp.LT, exp.GTE: exp.LTE, exp.LT: exp.GT, exp.LTE: exp.GTE, exp.EQ: exp.EQ}


def _bound(pred: exp.Expression) -> tuple[date | None, date | None] | None:
    """(low, high) implied by one predicate on ref_date; None if we cannot read it."""
    if isinstance(pred, exp.Between) and _is_ref_date(pred.this):
        lo, hi = _as_date(pred.args["low"]), _as_date(pred.args["high"])
        return (lo, hi) if lo and hi else None
    if type(pred) not in _FLIP:
        return None
    left, right, op = pred.this, pred.expression, type(pred)

    def _trunc(n: exp.Expression) -> bool:
        return isinstance(n, exp.TimestampTrunc) and _is_ref_date(n.this)

    if not (_is_ref_date(left) or _year_of_ref_date(left) or _trunc(left)):
        left, right, op = right, left, _FLIP[op]
    if _year_of_ref_date(left):
        year = (
            _as_int(right)
            if not isinstance(right, exp.Literal) or not right.is_string
            else (int(right.this) if right.this.isdigit() else None)
        )
        if year is None:
            return None
        first, last = date(year, 1, 1), date(year, 12, 31)
        return {
            exp.EQ: (first, last),
            exp.GTE: (first, None),
            exp.GT: (date(year + 1, 1, 1), None),
            exp.LTE: (None, last),
            exp.LT: (None, date(year - 1, 12, 31)),
        }[op]
    if isinstance(left, exp.TimestampTrunc) and _is_ref_date(left.this) and op is exp.EQ:
        d = _as_date(right)
        if d and left.args["unit"].name.upper() == "YEAR":
            return date(d.year, 1, 1), date(d.year, 12, 31)
        return None
    if not _is_ref_date(left):
        return None
    d = _as_date(right)
    if d is None:
        return None
    one = timedelta(days=1)
    return {
        exp.EQ: (d, d),
        exp.GTE: (d, None),
        exp.GT: (d + one, None),
        exp.LTE: (None, d),
        exp.LT: (None, d - one),
    }[op]


def _period_of(select: exp.Select) -> tuple[date | None, date | None] | None:
    """Intersection of all ref_date predicates in this SELECT's WHERE; None if any is unreadable."""
    where = select.args.get("where")
    if where is None:
        return (None, None)
    for disj in where.find_all(exp.Or):
        if any(_is_ref_date(c) for c in disj.find_all(exp.Column)):
            return None  # OR over dates: an intersection would be wrong; do not guess
    lo: date | None = None
    hi: date | None = None
    for pred in where.find_all(exp.Predicate):
        refs = any(_is_ref_date(c) for c in pred.find_all(exp.Column))
        if not refs or isinstance(pred, (exp.And, exp.Or)):
            continue
        if pred.find_ancestor(exp.Predicate) is not None and not isinstance(
            pred.find_ancestor(exp.Predicate), (exp.And,)
        ):
            continue  # nested inside another predicate (e.g. Between's operands)
        b = _bound(pred)
        if b is None:
            return None
        lo = b[0] if lo is None or (b[0] and b[0] > lo) else lo
        hi = b[1] if hi is None or (b[1] and b[1] < hi) else hi
    return lo, hi


def _months(lo: date, hi: date) -> set[tuple[int, int]]:
    out, y, m = set(), lo.year, lo.month
    if lo.day > 1:  # monthly points are dated on day 1
        m += 1
        if m == 13:
            y, m = y + 1, 1
    while date(y, m, 1) <= hi:
        out.add((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def period_mismatch(sql: str, plan, catalog: Catalog, dialect: str = "duckdb") -> list[Finding]:
    """Flag SELECTs whose ref_date filter selects different observations than the plan."""
    metric_by_id = {m.source.series_id: m for m in catalog.metrics.values() if m.source}
    findings: list[Finding] = []
    tree = sqlglot.parse_one(sql, read=dialect)
    for select in tree.find_all(exp.Select):
        sids = _series_ids_in_scope(select)
        if not sids:
            continue
        period = _period_of(select)
        if period is None:
            findings.append(Finding("period_unverified", "date filter could not be read"))
            continue
        lo, hi = period
        if lo is None or hi is None:
            findings.append(Finding("period_open", f"date filter is open-ended: {lo}..{hi}"))
            continue
        for sid in sids:
            m = metric_by_id.get(sid)
            if m is None:
                continue
            if m.frequency == "monthly":
                got, want = _months(lo, hi), _months(plan.start, plan.end)
                if got != want:
                    findings.append(
                        Finding(
                            "period_mismatch",
                            f"'{m.name}' uses {len(got)} months {lo}..{hi}, "
                            f"plan asks {len(want)} months {plan.start}..{plan.end}",
                        )
                    )
            elif m.aggregation == "last" and hi != plan.end:
                findings.append(
                    Finding(
                        "period_mismatch",
                        f"'{m.name}' reads the level at {hi}, plan asks {plan.end}",
                    )
                )
            elif m.aggregation != "last" and (lo, hi) != (plan.start, plan.end):
                findings.append(
                    Finding(
                        "period_mismatch",
                        f"'{m.name}' uses {lo}..{hi}, plan asks {plan.start}..{plan.end}",
                    )
                )
    return findings
