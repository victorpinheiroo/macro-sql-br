"""Question -> structured Plan. The LLM picks metrics and a period; it never writes the arithmetic.

The output is validated twice: against the JSON schema (PlannerOutput) and against the catalog
(known metric names, start <= end). Anything else is a failed plan, never a guessed one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from macrosql.compile import Plan
from macrosql.llm import LLMClient, Message, Response
from macrosql.metrics import Catalog

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


class PlannerOutput(BaseModel):
    metrics: list[str]
    start: str
    end: str


class Prompt(BaseModel):
    name: str
    version: int
    created_at: str
    system: str
    few_shots: list[dict[str, str]]

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


def load_prompt(name: str = "planner", directory: Path = PROMPTS) -> Prompt:
    return Prompt.model_validate(yaml.safe_load((directory / f"{name}.yml").read_text("utf-8")))


@dataclass(frozen=True)
class SeriesStatus:
    metric: str
    last_complete_ref_date: date


def describe_catalog(catalog: Catalog) -> str:
    lines = []
    for m in sorted(catalog.metrics.values(), key=lambda m: m.name):
        rule = m.aggregation or f"derived from {', '.join(m.derived.inputs)}"
        desc = " ".join(m.description.split())
        lines.append(f"- {m.name}: {m.label}. {desc} [{m.frequency}, {m.unit}, {rule}]")
    return "\n".join(lines)


def build_messages(
    question: str, prompt: Prompt, catalog: Catalog, today: date, status: list[SeriesStatus]
) -> list[Message]:
    status_txt = "\n".join(f"- {s.metric}: {s.last_complete_ref_date}" for s in status)
    system = prompt.system.format(
        today=today.isoformat(), status=status_txt, catalog=describe_catalog(catalog)
    )
    msgs = [Message(role="system", content=system)]
    for shot in prompt.few_shots:
        msgs += [
            Message(role="user", content=shot["user"]),
            Message(role="assistant", content=shot["assistant"]),
        ]
    msgs.append(Message(role="user", content=question))
    return msgs


@dataclass
class PlanResult:
    plan: Plan | None
    error: str | None
    response: Response


def to_plan(raw: dict | None, catalog: Catalog) -> tuple[Plan | None, str | None]:
    if raw is None:
        return None, "no structured output"
    try:
        plan = Plan.model_validate(raw)
    except ValidationError as e:
        return None, f"plan: {e.errors()[0]['msg']}"[:300]
    unknown = [m for m in plan.metrics if m not in catalog.metrics]
    if unknown:
        return None, f"unknown metrics: {unknown}"
    return plan, None


def make_plan(
    question: str,
    client: LLMClient,
    catalog: Catalog,
    today: date,
    status: list[SeriesStatus],
    prompt: Prompt | None = None,
) -> PlanResult:
    prompt = prompt or load_prompt()
    msgs = build_messages(question, prompt, catalog, today, status)
    resp = client.complete(msgs, schema=PlannerOutput, cache_key=prompt.key)
    if resp.parsed is None:
        return PlanResult(None, resp.parse_error or "unparseable output", resp)
    plan, err = to_plan(resp.parsed, catalog)
    return PlanResult(plan, err, resp)
