"""Planner + metrics path, end to end, per model, on the golden set.

    python -m macrosql.plan_eval                      # models from config/models.yml
    python -m macrosql.plan_eval --models databricks-gpt-oss-120b

For each model and golden question: ask the planner for a Plan, compile it, run it on the gold
snapshot and compare with the external oracle. Reports, per model:
  valid   share of questions that produced a schema- and catalog-valid Plan
  exact   share whose Plan equals the hand-written one (metrics and dates)
  correct share whose final number is within the oracle's tolerance
Writes evals/results/planner.md (table) and planner.jsonl (every case, for later analysis).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

import yaml

from macrosql.golden import connect, load_cases, run_case
from macrosql.llm import make_client
from macrosql.metrics import load_catalog
from macrosql.plan import SeriesStatus, load_prompt, make_plan


def load_status(path: Path) -> tuple[date, list[SeriesStatus]]:
    """'Today' is the snapshot's collection date, so prompts (and the cache) are reproducible."""
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    today = max(date.fromisoformat(r["collected_at"][:10]) for r in rows)
    status = [
        SeriesStatus(r["metric"], date.fromisoformat(r["last_complete_ref_date"]))
        for r in sorted(rows, key=lambda r: r["metric"])
    ]
    return today, status


def evaluate(model: str, cases, con, catalog, today, status, prompt, cache_dir) -> list[dict]:
    client = make_client(model, cache_dir=cache_dir)
    rows = []
    for case in cases:
        try:
            pr = make_plan(case.question, client, catalog, case.as_of or today, status, prompt)
        except Exception as e:  # provider error = failed case, run continues
            rows.append(
                {
                    "model": model,
                    "id": case.id,
                    "trap": case.trap,
                    "difficulty": case.difficulty,
                    "valid": False,
                    "exact": False,
                    "correct": False,
                    "provider_error": True,
                    "expected_plan": case.plan.model_dump(mode="json"),
                    "error": f"{type(e).__name__}: {e}".split("\n")[0][:200],
                }
            )
            continue
        r = pr.response
        row = {
            "model": model,
            "id": case.id,
            "trap": case.trap,
            "difficulty": case.difficulty,
            "valid": pr.plan is not None,
            "exact": pr.plan == case.plan,
            "correct": False,
            "plan": pr.plan.model_dump(mode="json") if pr.plan else None,
            "expected_plan": case.plan.model_dump(mode="json"),
            "error": pr.error,
            "structured_mode": r.structured_mode,
            "latency_ms": r.latency_ms,
            "cached": r.cached,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
        }
        if pr.plan is not None:
            res = run_case(case.model_copy(update={"plan": pr.plan}), con, catalog)
            row["correct"] = res.passed
            row["got"] = res.got
        rows.append(row)
    return rows


def summarize(rows: list[dict], models: list[str], n_cases: int, prompt_key: str) -> str:
    out = [
        f"Planner `{prompt_key}` on the golden set ({n_cases} questions, metrics path; "
        "basic = v1, hard = relative dates, paraphrases, custom windows). "
        "Numbers are shares of questions.",
        "",
        "| model | correct: all | basic | hard | valid plan | exact plan | provider errors | "
        "structured output | median latency (s) | mean tokens in/out |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in models:
        rs = [r for r in rows if r["model"] == m]

        def pct(k: str, rs: list[dict] = rs) -> str:
            return f"{sum(r[k] for r in rs)}/{len(rs)}"

        # Cached responses keep the latency measured when they were first produced.
        lat = [r["latency_ms"] for r in rs if r.get("latency_ms")]
        modes = sorted({r.get("structured_mode") for r in rs if r.get("structured_mode")})
        tin = [r["input_tokens"] for r in rs if r.get("input_tokens")] or [0]
        tout = [r["output_tokens"] for r in rs if r.get("output_tokens")] or [0]
        median_s = f"{statistics.median(lat) / 1000:.1f}" if lat else "n/a"

        def by(level: str, rs: list[dict] = rs) -> str:
            sub = [r for r in rs if r.get("difficulty", "basic") == level]
            return f"{sum(r['correct'] for r in sub)}/{len(sub)}"

        out.append(
            f"| {m} | {pct('correct')} | {by('basic')} | {by('hard')} | {pct('valid')} | "
            f"{pct('exact')} | {sum(bool(r.get('provider_error')) for r in rs)} | "
            f"{', '.join(modes)} | {median_s} | "
            f"{statistics.mean(tin):.0f} / {statistics.mean(tout):.0f} |"
        )
    misses = [r for r in rows if not r["correct"]]
    if misses:
        out += [
            "",
            "Misses:",
            "",
            "| model | id | trap | got plan | expected plan | error |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in misses:
            out.append(
                f"| {r['model']} | {r['id']} | {r.get('trap', '')} | `{json.dumps(r.get('plan'))}` "
                f"| `{json.dumps(r.get('expected_plan'))}` | {r.get('error') or ''} |"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", help="default: `eval` list in config/models.yml")
    p.add_argument("--config", type=Path, default=Path("config/models.yml"))
    p.add_argument("--golden", type=Path, default=Path("evals/golden.jsonl"))
    p.add_argument("--data", type=Path, default=Path("data/snapshot"))
    p.add_argument("--metrics", type=Path, default=Path("metrics"))
    p.add_argument("--out", type=Path, default=Path("evals/results"))
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    models = args.models or yaml.safe_load(args.config.read_text(encoding="utf-8"))["eval"]
    catalog = load_catalog(args.metrics)
    cases = load_cases(args.golden)
    con = connect(args.data / "obs.csv")
    today, status = load_status(args.data / "series_status.csv")
    prompt = load_prompt()
    cache_dir = None if args.no_cache else Path(".cache/llm")

    rows = []
    for m in models:
        print(f"{m} ...", file=sys.stderr)
        rows += evaluate(m, cases, con, catalog, today, status, prompt, cache_dir)

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
