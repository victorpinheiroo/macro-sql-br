# ruff: noqa: E501  (SVG template lines)
"""Render docs/img/metrics_vs_freesql.svg from evals/results/freesql.md.

    uv run python scripts/make_chart.py

Dumbbell chart, one row per model: share of the 31 golden questions answered correctly when the
model only picks metrics (blue) vs when it writes the SQL itself (orange). Hand-written SVG with
light/dark colors via prefers-color-scheme, so it reads on GitHub in both themes.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "evals" / "results" / "freesql.md"
OUT = ROOT / "docs" / "img" / "metrics_vs_freesql.svg"

NAMES = {
    "databricks-meta-llama-3-3-70b-instruct": "Llama 3.3 70B",
    "databricks-llama-4-maverick": "Llama 4 Maverick",
    "databricks-meta-llama-3-1-8b-instruct": "Llama 3.1 8B",
    "databricks-gpt-oss-120b": "GPT-OSS 120B",
    "databricks-gpt-oss-20b": "GPT-OSS 20B",
    "databricks-qwen3-next-80b-a3b-instruct": "Qwen3-Next 80B",
    "databricks-qwen35-122b-a10b": "Qwen 3.5 122B",
    "databricks-gemma-3-12b": "Gemma 3 12B",
}


def load() -> list[tuple[str, int, int, int]]:
    rows = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] in NAMES:
            free = re.match(r"(\d+)/(\d+)", cells[1])
            met = re.match(r"(\d+)/(\d+)", cells[2])
            rows.append(
                (NAMES[cells[0]], int(met.group(1)), int(free.group(1)), int(free.group(2)))
            )
    return sorted(rows, key=lambda r: r[2], reverse=True)


def render(rows) -> str:
    n = rows[0][3]
    w, left, right, top, row_h = 760, 150, 40, 92, 34
    plot_w = w - left - right
    h = top + row_h * len(rows) + 56

    def x(v: int) -> float:
        return left + plot_w * v / n

    tot_m = sum(r[1] for r in rows)
    tot_f = sum(r[2] for r in rows)
    total = n * len(rows)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="t d" font-family="system-ui, -apple-system, '
        'Segoe UI, Helvetica, Arial, sans-serif">',
        '<title id="t">Correct answers per model: metrics path vs free SQL</title>',
        f'<desc id="d">Out of {n} golden questions. Metrics path {tot_m}/{total} overall, '
        f"free SQL {tot_f}/{total}.</desc>",
        """<style>
  :root { --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --grid:#e4e3df; --m:#2a78d6; --f:#eb6834; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --grid:#383835; --m:#3987e5; --f:#d95926; }
  }
  .bg { fill: var(--bg); } .t1 { fill: var(--ink); } .t2 { fill: var(--ink2); }
  .grid { stroke: var(--grid); stroke-width: 1; } .link { stroke: var(--ink2); stroke-width: 2; opacity: .45; }
  .m { fill: var(--m); stroke: var(--bg); stroke-width: 2; } .f { fill: var(--f); stroke: var(--bg); stroke-width: 2; }
</style>""",
        f'<rect class="bg" width="{w}" height="{h}" rx="8"/>',
        '<text class="t1" x="24" y="32" font-size="17" font-weight="600">'
        "Same 8 free models, same questions: who writes the arithmetic matters</text>",
        f'<text class="t2" x="24" y="54" font-size="13">Correct answers out of {n} golden '
        "questions (expected values from IBGE and the BCB calculator)</text>",
    ]
    # legend
    lx, ly = 24, 78
    parts += [
        f'<circle class="m" cx="{lx + 6}" cy="{ly - 4}" r="6"/>',
        f'<text class="t2" x="{lx + 18}" y="{ly}" font-size="12">LLM picks metrics, '
        f"deterministic layer computes ({tot_m}/{total})</text>",
        f'<circle class="f" cx="{lx + 346}" cy="{ly - 4}" r="6"/>',
        f'<text class="t2" x="{lx + 358}" y="{ly}" font-size="12">LLM writes the SQL '
        f"({tot_f}/{total})</text>",
    ]
    y0 = top + 8
    ybot = top + row_h * len(rows)
    ticks = [v for v in range(0, n, 5) if n - v >= 3]  # keep the max label clear of its neighbor
    for v in ticks:
        parts.append(
            f'<line class="grid" x1="{x(v):.1f}" y1="{y0 - 6}" x2="{x(v):.1f}" y2="{ybot}"/>'
        )
        parts.append(
            f'<text class="t2" x="{x(v):.1f}" y="{ybot + 18}" font-size="11" text-anchor="middle">{v}</text>'
        )
    parts.append(
        f'<line class="grid" x1="{x(n):.1f}" y1="{y0 - 6}" x2="{x(n):.1f}" y2="{ybot}"/>'
        f'<text class="t2" x="{x(n):.1f}" y="{ybot + 18}" font-size="11" text-anchor="middle">{n}</text>'
    )
    for i, (name, met, free, _) in enumerate(rows):
        cy = top + row_h * i + row_h / 2 + 4
        parts += [
            f'<text class="t1" x="{left - 12}" y="{cy + 4}" font-size="13" text-anchor="end">{name}</text>',
            f'<line class="link" x1="{x(free):.1f}" y1="{cy}" x2="{x(met):.1f}" y2="{cy}"/>',
            f'<circle class="f" cx="{x(free):.1f}" cy="{cy}" r="6"><title>{name}: free SQL '
            f"{free}/{n}</title></circle>",
            f'<circle class="m" cx="{x(met):.1f}" cy="{cy}" r="6"><title>{name}: metrics path '
            f"{met}/{n}</title></circle>",
            f'<text class="t2" x="{x(free) - 10:.1f}" y="{cy + 4}" font-size="11" '
            f'text-anchor="end">{free}</text>',
        ]
    parts.append(
        f'<text class="t2" x="24" y="{h - 12}" font-size="11">Source: evals/results/freesql.md '
        "(week 3, metrics path with planner@1). Free SQL gets a data dictionary, not the metric rules.</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    rows = load()
    assert len(rows) == 8, rows
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows) + "\n", encoding="utf-8", newline="\n")
    for r in rows:
        print(r)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
