"""One question, end to end: plan -> route -> compute -> verify -> confidence.

    ctx = Context.from_snapshot(Path("data/snapshot"), make_client("..."))
    ask("Quanto foi o IPCA em 2024?", ctx)

The LLM interprets and routes. Numbers come from the metrics layer (high trust) or from
model-written SQL that passed the guardrails and the verifier (lower trust, said so). A plan that
asks for data not yet complete is turned into a clarification, deterministically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel

from macrosql import freesql
from macrosql.compile import Plan, compile_plan
from macrosql.confidence import Confidence, score
from macrosql.guardrails import GuardrailError, check
from macrosql.llm import LLMClient
from macrosql.metrics import Catalog, load_catalog
from macrosql.plan import SeriesStatus, load_prompt, load_status, make_plan
from macrosql.verify import aggregation_mismatch

Path_ = Literal["metrics", "free_sql", "clarify", "unavailable", "out_of_scope", "error"]

MESSAGES = {
    "unavailable": "Esse dado não está no catálogo (hoje: IPCA, Selic acumulada, meta Selic e "
    "juro real).",
    "out_of_scope": "Este sistema informa quanto foram os números; não faz previsões nem "
    "recomendações.",
}


class Answer(BaseModel):
    question: str
    path: Path_
    values: dict[str, float | None] | None = None
    sql: str | None = None
    plan: Plan | None = None
    options: list[str] = []
    message: str | None = None
    findings: list[str] = []
    confidence: Confidence
    data_as_of: dict[str, date] = {}
    model: str
    latency_ms: int
    llm_latency_ms: int = 0  # time spent in model calls, as first measured (survives cache)


@dataclass
class Context:
    client: LLMClient
    catalog: Catalog
    con: duckdb.DuckDBPyConnection  # sandboxed, holds gold only
    today: date
    status: list[SeriesStatus]

    @classmethod
    def from_snapshot(cls, data: Path, client: LLMClient, metrics: Path = Path("metrics")):
        today, status = load_status(data / "series_status.csv")
        con = freesql.sandbox(data / "obs.csv", data / "series_status.csv")
        return cls(client, load_catalog(metrics), con, today, status)


def _month_label(d: date) -> str:
    months = "jan fev mar abr mai jun jul ago set out nov dez".split()
    return f"{months[d.month - 1]}/{d.year}"


def freshness(plan: Plan, catalog: Catalog, status: list[SeriesStatus]) -> list[str]:
    """Options to offer when the plan reaches past the last complete point of any input series."""
    last = {s.metric: s.last_complete_ref_date for s in status}
    bases = []
    for name in plan.metrics:
        m = catalog.get(name)
        bases += [catalog.get(d) for d in m.derived.inputs] if m.derived else [m]
    late = [
        (b, last[b.name])
        for b in bases
        if b.name in last and plan.end > _period_end(b, last[b.name])
    ]
    if not late:
        return []
    metric, lc = min(late, key=lambda t: t[1])
    label = _month_label(lc) if metric.frequency == "monthly" else lc.strftime("%d/%m/%Y")
    opts = [f"Usar o último dado completo de {metric.label} ({label})"]
    if plan.start <= lc:
        opts.append(f"Mesmo período, mas só até {label}")
    return opts


def _period_end(metric, last_complete: date) -> date:
    """Last calendar day covered by the last complete point."""
    if metric.frequency == "monthly":
        nxt = date(last_complete.year + last_complete.month // 12, last_complete.month % 12 + 1, 1)
        return date.fromordinal(nxt.toordinal() - 1)
    return last_complete


def ask(question: str, ctx: Context, today: date | None = None) -> Answer:
    t0 = time.perf_counter()
    today = today or ctx.today
    as_of = {s.metric: s.last_complete_ref_date for s in ctx.status}

    llm_ms = [0]

    def done(**kw) -> Answer:
        kw.setdefault("confidence", score(kw["path"], kw.get("findings", [])))
        return Answer(
            question=question,
            model=ctx.client.model,
            data_as_of=as_of,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            llm_latency_ms=llm_ms[0],
            **kw,
        )

    try:
        pr = make_plan(question, ctx.client, ctx.catalog, today, ctx.status, load_prompt())
    except Exception as e:
        return done(path="error", message=f"planner unavailable: {type(e).__name__}")
    llm_ms[0] += pr.response.latency_ms if pr.response else 0
    if pr.action is None or (pr.action == "answer" and pr.plan is None):
        return done(path="error", message=f"could not plan the question: {pr.error}")

    if pr.action in ("unavailable", "out_of_scope"):
        return done(path=pr.action, message=MESSAGES[pr.action])
    if pr.action == "clarify":
        return done(
            path="clarify", options=pr.options, message="A pergunta tem mais de uma leitura."
        )

    if pr.action == "free_sql":
        fr = freesql.answer(question, ctx.client, ctx.catalog, ctx.con, today)
        llm_ms[0] += fr.response.latency_ms if fr.response else 0
        if fr.value is None:
            return done(path="error", sql=fr.sql, message=fr.error)
        findings = [f.rule for f in aggregation_mismatch(fr.executed_sql, ctx.catalog)]
        return done(
            path="free_sql", sql=fr.executed_sql, values={"answer": fr.value}, findings=findings
        )

    plan = pr.plan
    options = freshness(plan, ctx.catalog, ctx.status)
    if options:
        return done(
            path="clarify",
            plan=plan,
            options=options,
            message="O período pedido vai além do último dado completo publicado.",
        )
    sql = check(compile_plan(plan, ctx.catalog)).sql
    try:
        cur = ctx.con.execute(sql)
    except (GuardrailError, duckdb.Error) as e:
        return done(path="error", sql=sql, message=f"execution: {e}")
    cols = [d[0] for d in cur.description]
    row = dict(zip(cols, cur.fetchone(), strict=True))
    values = {m: row.get(m) for m in plan.metrics}
    if all(v is None for v in values.values()):
        return done(path="error", sql=sql, plan=plan, message="no data in the requested period")
    return done(path="metrics", sql=sql, plan=plan, values=values)
