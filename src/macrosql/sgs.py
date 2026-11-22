"""Client for the BCB SGS API.

Since 2025-03-26 SGS caps JSON/CSV queries on daily series: a date filter is mandatory and the
window may not exceed 10 years. We always fetch in windows of at most 10 years.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import httpx
from pydantic import BaseModel

BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
MAX_WINDOW_YEARS = 10


class Observation(BaseModel):
    series_id: int
    ref_date: date
    value: float


def windows(start: date, end: date, years: int = MAX_WINDOW_YEARS) -> Iterator[tuple[date, date]]:
    """Split [start, end] into consecutive, non-overlapping windows of at most `years` years."""
    cur = start
    while cur <= end:
        try:
            nxt = cur.replace(year=cur.year + years)
        except ValueError:  # Feb 29
            nxt = cur.replace(year=cur.year + years, day=28)
        win_end = min(end, date.fromordinal(nxt.toordinal() - 1))
        yield cur, win_end
        cur = date.fromordinal(win_end.toordinal() + 1)


def _parse(series_id: int, rows: list[dict]) -> list[Observation]:
    return [
        Observation(
            series_id=series_id,
            ref_date=datetime.strptime(r["data"], "%d/%m/%Y").date(),
            value=float(str(r["valor"]).replace(",", ".")),
        )
        for r in rows
    ]


def fetch(
    series_id: int, start: date, end: date, client: httpx.Client | None = None
) -> list[Observation]:
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        out: list[Observation] = []
        for w_start, w_end in windows(start, end):
            resp = client.get(
                BASE_URL.format(series_id=series_id),
                params={
                    "formato": "json",
                    "dataInicial": w_start.strftime("%d/%m/%Y"),
                    "dataFinal": w_end.strftime("%d/%m/%Y"),
                },
            )
            # TODO(M1): check how SGS answers an empty window and handle it explicitly.
            resp.raise_for_status()
            out.extend(_parse(series_id, resp.json()))
        return out
    finally:
        if own:
            client.close()
