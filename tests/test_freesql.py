import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from macrosql.freesql import answer, execute, sandbox
from macrosql.llm import Response, parse_json

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "snapshot"


class FakeClient:
    provider, model = "fake", "fake-1"

    def __init__(self, sql: str, col: str = "answer"):
        self.text = json.dumps({"sql": sql, "answer_column": col})

    def complete(self, messages, schema=None, tools=None, cache_key=None):
        parsed, err = parse_json(self.text, schema)
        return Response(
            text=self.text,
            parsed=parsed,
            parse_error=err,
            provider="fake",
            model="fake-1",
            latency_ms=1,
            structured_mode="prompted",
        )


@pytest.fixture(scope="module")
def con():
    return sandbox(SNAP / "obs.csv", SNAP / "series_status.csv")


def ask(sql, catalog, con, col="answer"):
    return answer("q", FakeClient(sql, col), catalog, con, date(2026, 11, 22))


def test_safe_select_runs_and_returns_the_named_column(catalog, con):
    r = ask("SELECT 1 AS other, 4.83 AS answer", catalog, con)
    assert r.value == pytest.approx(4.83) and r.error is None


def test_guardrail_blocks_before_execution(catalog, con):
    r = ask("DROP TABLE obs", catalog, con)
    assert r.blocked_by == "select_only" and r.value is None
    assert con.execute("SELECT COUNT(*) FROM obs").fetchone()[0] > 0


def test_sandbox_refuses_file_access_even_without_guardrails(con):
    with pytest.raises(duckdb.Error):
        execute(con, f"SELECT * FROM read_csv_auto('{(SNAP / 'obs.csv').as_posix()}')")


def test_sandbox_config_is_locked(con):
    with pytest.raises(duckdb.Error):
        execute(con, "SET enable_external_access = true")


def test_non_numeric_answer_is_an_error_not_a_number(catalog, con):
    r = ask("SELECT 'não sei' AS answer", catalog, con)
    assert r.value is None and "non-numeric" in r.error
