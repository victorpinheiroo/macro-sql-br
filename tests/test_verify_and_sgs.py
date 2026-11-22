from datetime import date

import httpx

from macrosql import sgs
from macrosql.compile import Plan, compile_plan
from macrosql.verify import aggregation_mismatch


def test_detects_summed_inflation(catalog):
    wrong = "SELECT SUM(value) FROM obs WHERE series_id = 433 AND ref_date >= DATE '2024-01-01'"
    findings = aggregation_mismatch(wrong, catalog)
    assert [f.rule for f in findings] == ["aggregation_mismatch"]


def test_compiled_compounding_is_not_flagged(catalog):
    sql = compile_plan(
        Plan(metrics=["ipca"], start=date(2024, 1, 1), end=date(2024, 12, 31)), catalog
    )
    assert aggregation_mismatch(sql, catalog) == []


def test_windows_never_exceed_ten_years_and_cover_range():
    ws = list(sgs.windows(date(1999, 3, 5), date(2026, 11, 18)))
    assert ws[0][0] == date(1999, 3, 5) and ws[-1][1] == date(2026, 11, 18)
    for (_a, b), (c, _) in zip(ws, ws[1:], strict=False):
        assert (c - b).days == 1  # contiguous, no overlap
    for a, b in ws:
        assert b < a.replace(year=a.year + 10)


def test_fetch_parses_brazilian_format():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "dataInicial" in request.url.params
        return httpx.Response(200, json=[{"data": "02/01/2024", "valor": "11.75"}])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = sgs.fetch(432, date(2024, 1, 1), date(2024, 1, 31), client=client)
    assert obs[0].ref_date == date(2024, 1, 2) and obs[0].value == 11.75


def test_fetch_treats_not_found_window_as_empty():
    # Shape of the real SGS answer for a window with no data (checked 2026-11-22).
    body = {"erro": {"statusCode": 404, "detail": "SGSNegocioException: Value(s) not found"}}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, json=body)))
    assert sgs.fetch(433, date(2030, 1, 1), date(2030, 1, 31), client=client) == []


def test_fetch_still_raises_on_other_404():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, text="nope")))
    try:
        sgs.fetch(999999, date(2024, 1, 1), date(2024, 1, 31), client=client)
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected HTTPStatusError")
