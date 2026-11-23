"""Composite confidence: where the number came from and what the verifier said about it.

Deliberately simple and explainable: every deduction comes with a reason shown to the user.
"""

from __future__ import annotations

from pydantic import BaseModel

BASE = {"metrics": 0.95, "free_sql": 0.6}
HARD = {"aggregation_mismatch", "unknown_series", "period_mismatch", "differential"}
SOFT = {"period_unverified", "period_open"}


class Confidence(BaseModel):
    score: float
    level: str
    reasons: list[str]


def score(path: str, findings: list[str], warnings: list[str] | None = None) -> Confidence:
    if path not in BASE:
        return Confidence(score=0.0, level="none", reasons=["no number returned"])
    s = BASE[path]
    reasons = [
        "metric computed by the governed metrics layer"
        if path == "metrics"
        else "SQL written by the model (outside the metric catalog)"
    ]
    hard = sorted(set(findings) & HARD)
    soft = sorted(set(findings) & SOFT)
    if hard:
        s -= 0.5
        reasons.append(f"verifier flagged: {', '.join(hard)}")
    if soft:
        s -= 0.15
        reasons.append(f"could not verify: {', '.join(soft)}")
    for w in warnings or []:
        s -= 0.05
        reasons.append(w)
    s = round(max(0.0, min(1.0, s)), 2)
    level = "high" if s >= 0.8 else "medium" if s >= 0.5 else "low"
    return Confidence(score=s, level=level, reasons=reasons)
