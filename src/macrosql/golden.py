"""Golden-set runner for the metrics path.

Each case carries a hand-written plan and an expected number taken from an external oracle
(IBGE publication, BCB calculator), never from this code. The runner compiles the plan, checks
the SQL against the guardrails, executes it on the gold snapshot and compares.

Until the LLM planner exists, this measures the deterministic half: if a case fails here, the
metric layer itself is wrong, whatever the model does.

    python -m macrosql.golden evals/golden.jsonl --data data/snapshot/obs.csv
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel

from macrosql.compile import OBS_TABLE, Plan, compile_plan
from macrosql.guardrails import check
from macrosql.metrics import Catalog, load_catalog


class Oracle(BaseModel):
    kind: Literal["publicado", "calculadora_bcb", "calculadora_bcb+publicado", "planilha"]
    source: str
    retrieved: str


class GoldenCase(BaseModel):
    id: str
    question: str
    expected_path: Literal["metrics", "free_sql", "clarify"]
    plan: Plan
    expected: dict[str, float]
    tolerance_pp: float
    oracle: Oracle
    trap: str


class Result(BaseModel):
    case: GoldenCase
    got: dict[str, float | None]
    passed: bool
    error: str | None = None


def load_cases(path: Path) -> list[GoldenCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    cases = [GoldenCase.model_validate_json(line) for line in lines if line.strip()]
    ids = [c.id for c in cases]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        raise ValueError(f"duplicate golden ids: {dupes}")
    return cases


def connect(data: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        f"CREATE TABLE {OBS_TABLE} AS SELECT CAST(series_id AS INT) AS series_id, "
        f"CAST(ref_date AS DATE) AS ref_date, CAST(value AS DOUBLE) AS value "
        f"FROM read_csv_auto('{data.as_posix()}', header = true)"
    )
    return con


def run_case(case: GoldenCase, con: duckdb.DuckDBPyConnection, catalog: Catalog) -> Result:
    try:
        sql = compile_plan(case.plan, catalog)
        check(sql)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        row = dict(zip(cols, cur.fetchone(), strict=True))
    except Exception as e:  # a crash is a failed case, not a crashed run
        return Result(case=case, got={}, passed=False, error=f"{type(e).__name__}: {e}")
    got = {m: row.get(m) for m in case.expected}
    passed = all(
        got[m] is not None and abs(got[m] - exp) <= case.tolerance_pp
        for m, exp in case.expected.items()
    )
    return Result(case=case, got=got, passed=passed)


def report(results: list[Result]) -> str:
    lines = ["id   | ok | metric      | expected   | got        | diff     | oracle"]
    for r in results:
        for m, exp in r.case.expected.items():
            got = r.got.get(m)
            diff = "" if got is None else f"{got - exp:+.4f}"
            got_s = r.error or ("" if got is None else f"{got:.4f}")
            lines.append(
                f"{r.case.id:4} | {'ok' if r.passed else 'XX':2} | {m:11} | {exp:10.4f} | "
                f"{got_s:10} | {diff:8} | {r.case.oracle.kind}"
            )
    n_ok = sum(r.passed for r in results)
    lines.append(f"\nmetrics path: {n_ok}/{len(results)} within tolerance")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("golden", type=Path)
    p.add_argument("--data", type=Path, default=Path("data/snapshot/obs.csv"))
    p.add_argument("--metrics", type=Path, default=Path("metrics"))
    args = p.parse_args(argv)

    catalog = load_catalog(args.metrics)
    con = connect(args.data)
    results = [run_case(c, con, catalog) for c in load_cases(args.golden)]
    print(report(results))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
