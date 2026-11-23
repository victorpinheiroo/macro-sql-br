"""HTTP API. All logic lives here (and below); the Streamlit app only renders.

    uvicorn macrosql.api:app --port 8000

POST /v1/ask       question -> routed answer with number, SQL, confidence, options
POST /v1/compute   explicit plan -> number from the metrics layer (no LLM involved)
GET  /v1/metrics   catalog + last complete reference date per metric
GET  /v1/history   last answers served by this process
GET  /healthz

Configuration (env): MACROSQL_DATA (gold snapshot dir), MACROSQL_MODEL (`provider:model`; default
from config/models.yml), DATABRICKS_HOST/DATABRICKS_TOKEN or OLLAMA_HOST for the model provider.
The API starts without any model credentials; only /v1/ask needs them.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from macrosql.ask import Answer, Context, ask
from macrosql.compile import Plan, compile_plan
from macrosql.freesql import sandbox
from macrosql.guardrails import check
from macrosql.llm import make_client
from macrosql.metrics import load_catalog
from macrosql.plan import load_status

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("MACROSQL_DATA", ROOT / "data" / "snapshot"))
METRICS = Path(os.environ.get("MACROSQL_METRICS", ROOT / "metrics"))
CONFIG = ROOT / "config" / "models.yml"

app = FastAPI(title="macro-sql-br", version="0.1.0")
HISTORY: deque[Answer] = deque(maxlen=200)
# One in-memory DuckDB connection is shared; requests run in a thread pool, so serialize access.
DB_LOCK = threading.Lock()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def model_name() -> str:
    if os.environ.get("MACROSQL_MODEL"):
        return os.environ["MACROSQL_MODEL"]
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["planner"]


@lru_cache(maxsize=1)
def catalog():
    return load_catalog(METRICS)


@lru_cache(maxsize=1)
def data_con():
    return sandbox(DATA / "obs.csv", DATA / "series_status.csv")


@lru_cache(maxsize=1)
def context() -> Context:
    today, status = load_status(DATA / "series_status.csv")
    client = make_client(
        model_name(), cache_dir=Path(os.environ.get("MACROSQL_CACHE", ".cache/llm"))
    )
    return Context(client, catalog(), data_con(), today, status)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "data": str(DATA), "model": model_name()}


@app.get("/v1/metrics")
def metrics() -> dict:
    _, status = load_status(DATA / "series_status.csv")
    last = {s.metric: s.last_complete_ref_date for s in status}
    return {
        "metrics": [
            {
                "name": m.name,
                "label": m.label,
                "frequency": m.frequency,
                "unit": m.unit,
                "aggregation": m.aggregation,
                "derived_from": m.derived.inputs if m.derived else None,
                "last_complete_ref_date": last.get(m.name),
            }
            for m in sorted(catalog().metrics.values(), key=lambda m: m.name)
        ]
    }


@app.post("/v1/compute")
def compute(plan: Plan) -> dict:
    """Deterministic path only: useful for tests, scripts and checking an answer by hand."""
    try:
        sql = check(compile_plan(plan, catalog())).sql
    except KeyError as e:
        raise HTTPException(422, str(e)) from e
    with DB_LOCK:
        cur = data_con().execute(sql)
        cols = [d[0] for d in cur.description]
        row = dict(zip(cols, cur.fetchone(), strict=True))
    return {"plan": plan, "values": {m: row.get(m) for m in plan.metrics}, "sql": sql}


@app.post("/v1/ask", response_model=Answer)
def ask_endpoint(req: AskRequest) -> Answer:
    try:
        ctx = context()
    except Exception as e:  # missing credentials, unreachable provider
        raise HTTPException(503, f"model provider not configured: {type(e).__name__}: {e}") from e
    with DB_LOCK:
        answer = ask(req.question, ctx)
    HISTORY.append(answer)
    return answer


@app.get("/v1/history")
def history(limit: int = 20) -> list[Answer]:
    return list(HISTORY)[-limit:][::-1]
