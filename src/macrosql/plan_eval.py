"""End-to-end eval per model: question -> route -> number, on the whole golden set.

    python -m macrosql.plan_eval                      # models from config/models.yml
    python -m macrosql.plan_eval --models databricks-gpt-oss-120b

Every golden question goes through `ask()` exactly as the API runs it. A case is correct when the
path matches the expected one (metrics, free_sql, clarify, unavailable, out_of_scope) and, for
the two answering paths, the number is within the oracle's tolerance.
Writes evals/results/planner.md (table) and planner.jsonl (every case).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import yaml

from macrosql.ask import Context, ask
from macrosql.golden import load_cases
from macrosql.llm import make_client
from macrosql.plan import load_prompt

GROUPS = {
    "metrics": "metrics",
    "free_sql": "free SQL",
    "clarify": "clarify",
    "unavailable": "decline",
    "out_of_scope": "decline",
}


def evaluate(model: str, cases, data: Path, cache_dir) -> list[dict]:
    ctx = Context.from_snapshot(data, make_client(model, cache_dir=cache_dir))
    rows = []
    for case in cases:
        a = ask(case.question, ctx, today=case.as_of)
        value = None
        correct = a.path == case.expected_path
        if correct and case.expected:
            ((metric, exp_value),) = case.expected.items()
            key = metric if a.path == "metrics" else "answer"
            value = (a.values or {}).get(key)
            correct = value is not None and abs(value - exp_value) <= case.tolerance_pp
        rows.append(
            {
                "model": model,
                "id": case.id,
                "trap": case.trap,
                "difficulty": case.difficulty,
                "expected_path": case.expected_path,
                "path": a.path,
                "route_ok": a.path == case.expected_path,
                "correct": correct,
                "value": value,
                "plan": a.plan.model_dump(mode="json") if a.plan else None,
                "expected_plan": case.plan.model_dump(mode="json") if case.plan else None,
                "exact": bool(case.plan and a.plan == case.plan),
                "options": a.options,
                "message": a.message,
                "confidence": a.confidence.score,
                "latency_ms": a.llm_latency_ms,
            }
        )
    return rows


def summarize(rows: list[dict], models: list[str], n_cases: int, prompt_key: str) -> str:
    groups = list(dict.fromkeys(GROUPS.values()))
    out = [
        f"End to end on the golden set ({n_cases} questions), planner `{prompt_key}`. A case is "
        "correct when the route matches and, when a number is expected, it is within tolerance.",
        "",
        "| model | correct | " + " | ".join(groups) + " | route ok | median model time (s) |",
        "| --- | --- | " + " | ".join("---" for _ in groups) + " | --- | --- |",
    ]
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        cells = []
        for g in groups:
            sub = [r for r in rs if GROUPS[r["expected_path"]] == g]
            cells.append(f"{sum(r['correct'] for r in sub)}/{len(sub)}")
        lat = [r["latency_ms"] for r in rs if r.get("latency_ms")]
        med = f"{statistics.median(lat) / 1000:.1f}" if lat else "n/a"
        out.append(
            f"| {m} | **{sum(r['correct'] for r in rs)}/{len(rs)}** | "
            + " | ".join(cells)
            + f" | {sum(r['route_ok'] for r in rs)}/{len(rs)} | {med} |"
        )
    misses = [r for r in rows if not r["correct"]]
    if misses:
        out += [
            "",
            "Misses:",
            "",
            "| model | id | trap | expected | got | detail |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in misses:
            detail = r["message"] or ""
            if r["path"] == "metrics" and r["plan"]:
                detail = f"plan {json.dumps(r['plan'])} value {r['value']}"
            detail = detail.replace("|", "/")[:160]
            out.append(
                f"| {r['model']} | {r['id']} | {r['trap']} | {r['expected_path']} | {r['path']} "
                f"| {detail} |"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", help="default: `eval` list in config/models.yml")
    p.add_argument("--config", type=Path, default=Path("config/models.yml"))
    p.add_argument("--golden", type=Path, default=Path("evals/golden.jsonl"))
    p.add_argument("--data", type=Path, default=Path("data/snapshot"))
    p.add_argument("--out", type=Path, default=Path("evals/results"))
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    models = args.models or yaml.safe_load(args.config.read_text(encoding="utf-8"))["eval"]
    cases = load_cases(args.golden)
    prompt = load_prompt()
    cache_dir = None if args.no_cache else Path(".cache/llm")
    rows = []
    for m in models:
        print(f"{m} ...", file=sys.stderr)
        rows += evaluate(m, cases, args.data, cache_dir)

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "planner.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({**r, "prompt": prompt.key}, ensure_ascii=False) + "\n")
    table = summarize(rows, models, len(cases), prompt.key)
    (args.out / "planner.md").write_text(table + "\n", encoding="utf-8", newline="\n")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
