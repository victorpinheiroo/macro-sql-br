"""Free-SQL path vs metrics path on the golden set, and how much the verifier catches.

    python -m macrosql.freesql_eval                 # models from config/models.yml

Every golden question also has a catalog answer, so we can ask each model to write the SQL itself
and compare with the external oracle. For each free-SQL answer the verifier runs with the plan
the same model produced (what production would have):
  static      aggregation rule from the catalog (e.g. inflation summed)
  period      ref_date filter vs the plan's period
  differential  free-SQL number vs metrics-path number for that plan
Reported per model: free-SQL accuracy, guardrail blocks, and the verifier's recall on wrong answers
and false-alarm rate on right ones. Writes evals/results/freesql.{md,jsonl}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from macrosql.compile import compile_plan
from macrosql.freesql import answer, sandbox
from macrosql.golden import load_cases
from macrosql.llm import make_client
from macrosql.metrics import load_catalog
from macrosql.plan import load_prompt, make_plan
from macrosql.plan_eval import load_status
from macrosql.verify import aggregation_mismatch, differential, period_mismatch

HARD_FINDINGS = {"aggregation_mismatch", "unknown_series", "period_mismatch", "differential"}


def verify_answer(sql: str, value: float, plan, catalog, con) -> list[str]:
    rules = [f.rule for f in aggregation_mismatch(sql, catalog)]
    if plan is not None:
        rules += [f.rule for f in period_mismatch(sql, plan, catalog)]
        ref = con.execute(compile_plan(plan, catalog)).fetchone()
        ref_vals = [v for v in ref[: len(plan.metrics)] if v is not None]
        if ref_vals:
            rules += [f.rule for f in differential(value, ref_vals[0], abs_tol_pp=0.05)]
    return rules


def evaluate(model, cases, con, catalog, today, status, cache_dir) -> list[dict]:
    client = make_client(model, cache_dir=cache_dir)
    p_plan, p_sql = load_prompt("planner"), load_prompt("freesql")
    rows = []
    for case in cases:
        as_of = case.as_of or today
        row = {"model": model, "id": case.id, "trap": case.trap, "difficulty": case.difficulty}
        try:
            pr = make_plan(case.question, client, catalog, as_of, status, p_plan)
            fr = answer(case.question, client, catalog, con, as_of, p_sql)
        except Exception as e:
            rows.append(
                {
                    **row,
                    "provider_error": True,
                    "correct": False,
                    "error": f"{type(e).__name__}: {e}".split("\n")[0][:200],
                }
            )
            continue
        exp_metric, exp_value = next(iter(case.expected.items()))
        correct = fr.value is not None and abs(fr.value - exp_value) <= case.tolerance_pp
        rules = (
            verify_answer(fr.executed_sql, fr.value, pr.plan, catalog, con)
            if (fr.value is not None)
            else []
        )
        rows.append(
            {
                **row,
                "sql": fr.sql,
                "value": fr.value,
                "expected": exp_value,
                "correct": correct,
                "blocked_by": fr.blocked_by,
                "error": fr.error,
                "findings": rules,
                "flagged": bool(set(rules) & HARD_FINDINGS),
                "unverified": bool({"period_unverified", "period_open"} & set(rules)),
                "plan": pr.plan.model_dump(mode="json") if pr.plan else None,
            }
        )
    return rows


def summarize(rows: list[dict], models: list[str], n: int) -> str:
    out = [
        f"Free-SQL path on the golden set ({n} questions; model writes the SQL from a data "
        "dictionary, no metric rules). Verifier = static + period + differential vs metrics path.",
        "",
        "| model | free SQL correct | metrics path correct | provider errors | no answer | "
        "guardrail blocks | wrong answers flagged | right answers flagged | unverifiable period |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    planner = {}
    p = Path("evals/results/planner.jsonl")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            planner.setdefault(r["model"], []).append(r["correct"])
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        answered = [r for r in rs if r.get("value") is not None]
        wrong = [r for r in answered if not r["correct"]]
        right = [r for r in answered if r["correct"]]
        mp = planner.get(m, [])
        out.append(
            f"| {m} | {sum(r['correct'] for r in rs)}/{len(rs)} | "
            f"{sum(mp)}/{len(mp) if mp else '?'} | "
            f"{sum(bool(r.get('provider_error')) for r in rs)} | "
            f"{sum(1 for r in rs if r.get('value') is None and not r.get('provider_error'))} | "
            f"{sum(bool(r.get('blocked_by')) for r in rs)} | "
            f"{sum(r['flagged'] for r in wrong)}/{len(wrong)} | "
            f"{sum(r['flagged'] for r in right)}/{len(right)} | "
            f"{sum(r['unverified'] for r in answered)} |"
        )
    wrong_all = [r for r in rows if r.get("value") is not None and not r["correct"]]
    right_all = [r for r in rows if r.get("value") is not None and r["correct"]]
    out += [
        "",
        f"All models: verifier flagged {sum(r['flagged'] for r in wrong_all)}/{len(wrong_all)} "
        f"wrong answers and {sum(r['flagged'] for r in right_all)}/{len(right_all)} right ones.",
    ]
    missed = [r for r in wrong_all if not r["flagged"]]
    if missed:
        out += [
            "",
            "Wrong answers the verifier did not flag:",
            "",
            "| model | id | trap | got | expected | findings |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in missed:
            out.append(
                f"| {r['model']} | {r['id']} | {r['trap']} | {r['value']:.4f} | "
                f"{r['expected']:.4f} | {', '.join(r['findings']) or '-'} |"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+")
    p.add_argument("--config", type=Path, default=Path("config/models.yml"))
    p.add_argument("--golden", type=Path, default=Path("evals/golden.jsonl"))
    p.add_argument("--data", type=Path, default=Path("data/snapshot"))
    p.add_argument("--metrics", type=Path, default=Path("metrics"))
    p.add_argument("--out", type=Path, default=Path("evals/results"))
    args = p.parse_args(argv)

    models = args.models or yaml.safe_load(args.config.read_text(encoding="utf-8"))["eval"]
    catalog = load_catalog(args.metrics)
    cases = load_cases(args.golden)
    con = sandbox(args.data / "obs.csv", args.data / "series_status.csv")
    today, status = load_status(args.data / "series_status.csv")
    rows = []
    for m in models:
        print(f"{m} ...", file=sys.stderr)
        rows += evaluate(m, cases, con, catalog, today, status, Path(".cache/llm"))

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "freesql.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    table = summarize(rows, models, len(cases))
    (args.out / "freesql.md").write_text(table + "\n", encoding="utf-8", newline="\n")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
