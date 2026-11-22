"""Free-SQL path: the model writes the query itself, for questions outside the metric catalog.

Lower trust by design, so every query goes through:
  1. guardrails (AST): one SELECT, table allowlist, no file access, LIMIT cap;
  2. a sandboxed DuckDB: in-memory copy of gold, external access off, config locked, timeout;
  3. the verifier (static aggregation rules, period check, differential when a plan exists).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
from pydantic import BaseModel

from macrosql.guardrails import GuardrailError, check
from macrosql.llm import LLMClient, Message, Response
from macrosql.metrics import Catalog
from macrosql.plan import Prompt, load_prompt


class FreeSQLOutput(BaseModel):
    sql: str
    answer_column: str


def describe_series(catalog: Catalog) -> str:
    """Data dictionary only: id, name, frequency, unit. No aggregation rule."""
    lines = []
    for m in sorted(catalog.metrics.values(), key=lambda m: m.name):
        if m.source is None:
            continue
        lines.append(
            f"- series_id {m.source.series_id} ({m.name}): {m.label}; {m.frequency}; unit {m.unit}"
        )
    return "\n".join(lines)


def sandbox(obs_csv: Path, status_csv: Path) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB holding only gold, with file/network access disabled afterwards."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE obs AS SELECT CAST(series_id AS INT) AS series_id, "
        "CAST(ref_date AS DATE) AS ref_date, CAST(value AS DOUBLE) AS value "
        f"FROM read_csv_auto('{obs_csv.as_posix()}', header = true)"
    )
    con.execute(
        "CREATE TABLE series AS SELECT CAST(series_id AS INT) AS series_id, metric, frequency, "
        "unit, CAST(last_complete_ref_date AS DATE) AS last_complete_ref_date "
        f"FROM read_csv_auto('{status_csv.as_posix()}', header = true)"
    )
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def execute(con: duckdb.DuckDBPyConnection, sql: str, timeout_s: float = 10.0):
    """Run with a wall-clock timeout; returns (columns, first row)."""
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchone()
    finally:
        timer.cancel()


@dataclass
class FreeSQLResult:
    sql: str | None
    value: float | None
    error: str | None
    blocked_by: str | None = None  # guardrail rule that stopped the query
    response: Response | None = None
    executed_sql: str | None = None
    notes: list[str] = field(default_factory=list)


def build_messages(question: str, prompt: Prompt, catalog: Catalog, today: date) -> list[Message]:
    system = prompt.system.format(today=today.isoformat(), series=describe_series(catalog))
    msgs = [Message(role="system", content=system)]
    for shot in prompt.few_shots:
        msgs += [
            Message(role="user", content=shot["user"]),
            Message(role="assistant", content=shot["assistant"]),
        ]
    return msgs + [Message(role="user", content=question)]


def answer(
    question: str,
    client: LLMClient,
    catalog: Catalog,
    con: duckdb.DuckDBPyConnection,
    today: date,
    prompt: Prompt | None = None,
) -> FreeSQLResult:
    prompt = prompt or load_prompt("freesql")
    resp = client.complete(
        build_messages(question, prompt, catalog, today), schema=FreeSQLOutput, cache_key=prompt.key
    )
    if resp.parsed is None:
        return FreeSQLResult(None, None, resp.parse_error or "unparseable output", response=resp)
    out = FreeSQLOutput.model_validate(resp.parsed)
    try:
        checked = check(out.sql)
    except GuardrailError as e:
        return FreeSQLResult(out.sql, None, str(e), blocked_by=e.rule, response=resp)
    try:
        cols, row = execute(con, checked.sql)
    except Exception as e:
        return FreeSQLResult(
            out.sql,
            None,
            f"execution: {type(e).__name__}: {e}"[:300],
            response=resp,
            executed_sql=checked.sql,
        )
    if row is None:
        return FreeSQLResult(out.sql, None, "no rows", response=resp, executed_sql=checked.sql)
    by_name = dict(zip([c.lower() for c in cols], row, strict=True))
    raw = by_name.get(out.answer_column.lower(), row[0] if len(row) == 1 else None)
    try:
        value = None if raw is None else float(raw)
    except (TypeError, ValueError):
        return FreeSQLResult(
            out.sql, None, f"non-numeric answer: {raw!r}", response=resp, executed_sql=checked.sql
        )
    return FreeSQLResult(out.sql, value, None, response=resp, executed_sql=checked.sql)
