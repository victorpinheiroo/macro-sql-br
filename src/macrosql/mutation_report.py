"""Run the seeded-error set against the verifier and report recall per layer and false alarms."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import duckdb

from macrosql.compile import Plan, compile_plan
from macrosql.metrics import Catalog
from macrosql.mutations import generate
from macrosql.verify import aggregation_mismatch, differential, period_mismatch


@dataclass
class OperatorStats:
    total: int = 0
    caught_static: int = 0
    caught_differential: int = 0
    caught_period: int = 0
    caught_any: int = 0
    undetectable: int = 0  # mutant returned the same number as the reference on this data


def run(plans: list[Plan], catalog: Catalog, con: duckdb.DuckDBPyConnection) -> dict:
    stats: dict[str, OperatorStats] = defaultdict(OperatorStats)
    for mutant in generate(plans, catalog):
        s = stats[mutant.operator]
        s.total += 1
        static = bool(aggregation_mismatch(mutant.mutant_sql, catalog))
        # The period check compares the SQL with the plan the user's question produced.
        period = any(
            f.rule == "period_mismatch"
            for f in period_mismatch(mutant.mutant_sql, mutant.plan, catalog)
        )
        ref = con.execute(mutant.reference_sql).fetchone()[0]
        got = con.execute(mutant.mutant_sql).fetchone()[0]
        if ref is None or got is None:
            diff = got is not ref
        else:
            diff = bool(differential(got, ref))
            if not diff and not static and not period:
                s.undetectable += 1
        s.caught_static += static
        s.caught_differential += diff
        s.caught_period += period
        s.caught_any += static or diff or period

    correct = [compile_plan(p, catalog) for p in plans]
    false_alarms = sum(bool(aggregation_mismatch(sql, catalog)) for sql in correct)
    period_false_alarms = sum(
        bool(period_mismatch(sql, p, catalog)) for sql, p in zip(correct, plans, strict=True)
    )
    return {
        "operators": dict(stats),
        "correct_queries": len(correct),
        "static_false_alarms": false_alarms,
        "period_false_alarms": period_false_alarms,
    }


def format_report(result: dict) -> str:
    lines = [
        "| operator | mutants | static | differential | period | any |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    tot = OperatorStats()
    keys = ("total", "caught_static", "caught_differential", "caught_period", "caught_any")
    for op, s in sorted(result["operators"].items()):
        lines.append(
            f"| {op} | {s.total} | {s.caught_static} | {s.caught_differential} | "
            f"{s.caught_period} | {s.caught_any} |"
        )
        for k in keys:
            setattr(tot, k, getattr(tot, k) + getattr(s, k))
    lines.append(
        f"| **all** | {tot.total} | {tot.caught_static} | {tot.caught_differential} | "
        f"{tot.caught_period} | **{tot.caught_any}** |"
    )
    n = result["correct_queries"]
    lines.append(
        f"\nFalse alarms on the {n} correct queries: "
        f"static {result['static_false_alarms']}/{n}, period {result['period_false_alarms']}/{n}."
    )
    return "\n".join(lines)


SEED_PLANS = [
    # Fallback seeds for tests; the CLI uses every plan in the golden set.
    Plan(metrics=["ipca"], start=date(2024, 1, 1), end=date(2024, 12, 31)),
    Plan(metrics=["selic"], start=date(2024, 1, 1), end=date(2024, 6, 30)),
    Plan(metrics=["selic_meta"], start=date(2025, 1, 1), end=date(2025, 3, 31)),
    Plan(metrics=["juro_real"], start=date(2023, 1, 1), end=date(2023, 12, 31)),
]


def main(argv: list[str] | None = None) -> None:
    """python -m macrosql.mutation_report [--golden evals/golden.jsonl] [--data obs.csv]"""
    import argparse
    from pathlib import Path

    from macrosql.golden import connect, load_cases
    from macrosql.metrics import load_catalog

    p = argparse.ArgumentParser()
    p.add_argument("--golden", type=Path, default=Path("evals/golden.jsonl"))
    p.add_argument("--data", type=Path, default=Path("data/snapshot/obs.csv"))
    p.add_argument("--metrics", type=Path, default=Path("metrics"))
    args = p.parse_args(argv)

    plans = [c.plan for c in load_cases(args.golden)]
    con = connect(args.data)
    print(f"Seeds: {len(plans)} golden-set plans, real data ({args.data}).\n")
    print(format_report(run(plans, load_catalog(args.metrics), con)))


if __name__ == "__main__":
    main()
