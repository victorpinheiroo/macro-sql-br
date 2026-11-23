import re
from datetime import date
from pathlib import Path

from macrosql.golden import load_cases
from macrosql.llm import CachedClient, Message, Response, parse_json
from macrosql.plan import PlannerOutput, SeriesStatus, build_messages, load_prompt, make_plan

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 22)


def out(metrics, start, end):
    import json

    return json.dumps(
        {"action": "answer", "metrics": metrics, "start": start, "end": end, "options": []}
    )


STATUS = [SeriesStatus("ipca", date(2026, 10, 1))]


class FakeClient:
    provider, model = "fake", "fake-1"

    def __init__(self, text: str):
        self.text, self.calls = text, 0

    def complete(self, messages, schema=None, tools=None, cache_key=None) -> Response:
        self.calls += 1
        parsed, err = parse_json(self.text, schema) if schema else (None, None)
        return Response(
            text=self.text,
            parsed=parsed,
            parse_error=err,
            provider=self.provider,
            model=self.model,
            latency_ms=1,
            structured_mode="prompted",
        )


def test_valid_output_becomes_a_plan(catalog):
    c = FakeClient(out(["ipca"], "2019-01-01", "2019-12-31"))
    r = make_plan("Inflação de 2019?", c, catalog, TODAY, STATUS)
    assert r.error is None and r.plan.metrics == ["ipca"] and r.plan.end == date(2019, 12, 31)


def test_json_wrapped_in_prose_is_still_parsed(catalog):
    c = FakeClient("Claro! " + out(["ipca"], "2019-01-01", "2019-12-31") + " ok")
    assert make_plan("x", c, catalog, TODAY, STATUS).plan is not None


def test_unknown_metric_is_a_failed_plan_not_a_guess(catalog):
    c = FakeClient(out(["pib"], "2019-01-01", "2019-12-31"))
    r = make_plan("PIB de 2019?", c, catalog, TODAY, STATUS)
    assert r.plan is None and "unknown metrics" in r.error


def test_inverted_period_is_rejected(catalog):
    c = FakeClient(out(["ipca"], "2019-12-31", "2019-01-01"))
    assert make_plan("x", c, catalog, TODAY, STATUS).plan is None


def test_garbage_is_rejected(catalog):
    assert make_plan("x", FakeClient("não sei"), catalog, TODAY, STATUS).plan is None


def test_prompt_renders_catalog_status_and_shots(catalog):
    p = load_prompt()
    msgs = build_messages("pergunta", p, catalog, TODAY, STATUS)
    assert "2026-11-22" in msgs[0].content and "selic_meta" in msgs[0].content
    assert "ipca: 2026-10-01" in msgs[0].content
    assert len(msgs) == 1 + 2 * len(p.few_shots) + 1 and msgs[-1].content == "pergunta"


def test_few_shots_do_not_leak_golden_questions_or_years():
    cases = load_cases(ROOT / "evals" / "golden.jsonl")
    golden_years = {str(y) for c in cases if c.plan for y in (c.plan.start.year, c.plan.end.year)}
    golden_years |= {y for c in cases for y in re.findall(r"20\d\d", c.question)}
    for shot in load_prompt().few_shots:
        assert shot["user"] not in {c.question for c in cases}
        assert not (set(re.findall(r"\b(?:19|20)\d\d\b", " ".join(shot.values()))) & golden_years)


def test_cache_hits_skip_the_provider(tmp_path):
    inner = FakeClient(out(["ipca"], "2019-01-01", "2019-12-31"))
    c = CachedClient(inner, tmp_path)
    msgs = [Message(role="user", content="oi")]
    a = c.complete(msgs, schema=PlannerOutput, cache_key="planner@1")
    b = c.complete(msgs, schema=PlannerOutput, cache_key="planner@1")
    c.complete(msgs, schema=PlannerOutput, cache_key="planner@2")  # new prompt version
    assert inner.calls == 2 and not a.cached and b.cached and b.parsed == a.parsed


def test_clarify_carries_options_and_no_plan(catalog):
    c = FakeClient(
        '{"action": "clarify", "metrics": [], "start": "", "end": "", '
        '"options": ["Meta Selic no fim de 2019", "Selic acumulada em 2019"]}'
    )
    r = make_plan("Selic de 2019?", c, catalog, TODAY, STATUS)
    assert r.action == "clarify" and r.plan is None and len(r.options) == 2


def test_clarify_without_options_is_a_failure(catalog):
    c = FakeClient('{"action": "clarify", "metrics": [], "start": "", "end": "", "options": []}')
    assert make_plan("x", c, catalog, TODAY, STATUS).error == "clarify without options"


def test_free_sql_keeps_the_period(catalog):
    c = FakeClient(
        '{"action": "free_sql", "metrics": [], "start": "2017-01-01", "end": "2017-12-31", '
        '"options": []}'
    )
    r = make_plan("mês mais alto de 2017?", c, catalog, TODAY, STATUS)
    assert r.action == "free_sql" and r.period == (date(2017, 1, 1), date(2017, 12, 31))
