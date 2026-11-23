from datetime import date

import pytest
from fastapi.testclient import TestClient

from macrosql import api
from macrosql.ask import Context
from macrosql.llm import Response, parse_json


class FakeClient:
    provider, model = "fake", "fake-1"

    def __init__(self, text: str):
        self.text = text

    def complete(self, messages, schema=None, tools=None, cache_key=None):
        parsed, err = parse_json(self.text, schema) if schema else (None, None)
        return Response(
            text=self.text,
            parsed=parsed,
            parse_error=err,
            provider="fake",
            model="fake-1",
            latency_ms=1,
            structured_mode="prompted",
        )


def plan_json(action="answer", metrics=("ipca",), start="2024-01-01", end="2024-12-31", opts=()):
    import json

    return json.dumps(
        {
            "action": action,
            "metrics": list(metrics),
            "start": start,
            "end": end,
            "options": list(opts),
        }
    )


@pytest.fixture()
def client(monkeypatch):
    def with_answer(text):
        today, status = api.load_status(api.DATA / "series_status.csv")
        ctx = Context(FakeClient(text), api.catalog(), api.data_con(), today, status)
        monkeypatch.setattr(api, "context", lambda: ctx)
        return TestClient(api.app)

    return with_answer


def test_metrics_lists_catalog_with_freshness():
    r = TestClient(api.app).get("/v1/metrics")
    names = {m["name"]: m for m in r.json()["metrics"]}
    assert {"ipca", "selic", "selic_meta", "juro_real"} <= set(names)
    assert names["ipca"]["last_complete_ref_date"] == "2026-10-01"


def test_compute_needs_no_model():
    r = TestClient(api.app).post(
        "/v1/compute", json={"metrics": ["ipca"], "start": "2024-01-01", "end": "2024-12-31"}
    )
    assert r.status_code == 200
    assert r.json()["values"]["ipca"] == pytest.approx(4.83, abs=0.02)  # IBGE: 4.83


def test_ask_metrics_path_returns_number_sql_and_high_confidence(client):
    r = client(plan_json()).post("/v1/ask", json={"question": "IPCA de 2024?"})
    a = r.json()
    assert a["path"] == "metrics" and a["values"]["ipca"] == pytest.approx(4.83, abs=0.02)
    assert "EXP" in a["sql"].upper() and a["confidence"]["level"] == "high"


def test_partial_month_becomes_a_clarification(client):
    body = plan_json(metrics=("selic",), start="2026-11-01", end="2026-11-30")
    a = client(body).post("/v1/ask", json={"question": "Selic de novembro de 2026"}).json()
    assert a["path"] == "clarify" and a["values"] is None and a["options"]


def test_decline_paths_carry_a_message(client):
    a = (
        client(plan_json(action="out_of_scope", metrics=(), start="", end=""))
        .post("/v1/ask", json={"question": "A Selic vai cair?"})
        .json()
    )
    assert a["path"] == "out_of_scope" and "previsões" in a["message"]


def test_history_records_answers(client):
    c = client(plan_json())
    c.post("/v1/ask", json={"question": "IPCA de 2024?"})
    assert c.get("/v1/history").json()[0]["question"] == "IPCA de 2024?"


def test_freshness_is_independent_of_the_model(catalog):
    from macrosql.ask import freshness
    from macrosql.compile import Plan
    from macrosql.plan import SeriesStatus

    status = [SeriesStatus("ipca", date(2026, 10, 1)), SeriesStatus("selic", date(2026, 10, 1))]
    ok = Plan(metrics=["juro_real"], start=date(2026, 1, 1), end=date(2026, 10, 31))
    late = Plan(metrics=["juro_real"], start=date(2026, 1, 1), end=date(2026, 11, 30))
    assert freshness(ok, catalog, status) == []
    assert len(freshness(late, catalog, status)) == 2
