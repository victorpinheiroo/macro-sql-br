"""Provider-neutral LLM client with a disk cache.

    client = make_client("databricks-llama-4-maverick")
    resp = client.complete(messages, schema=PlannerOutput, cache_key="planner@3")

Every Response carries provider, model, tokens, latency and how structured output was obtained
(`constrained` = provider enforced the JSON schema; `prompted` = schema only in the prompt, parsed
by us). The model name comes from config / CLI, never from code that uses the client.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ValidationError


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Response(BaseModel):
    text: str
    parsed: dict[str, Any] | None = None
    parse_error: str | None = None
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int
    structured_mode: Literal["constrained", "prompted", "none"] = "none"
    cached: bool = False


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        messages: list[Message],
        schema: type[BaseModel] | None = None,
        tools: list[dict] | None = None,
        cache_key: str | None = None,
    ) -> Response: ...


def _strip_titles(node: Any) -> Any:
    """Pydantic schemas carry `title` and `format`; some grammar engines reject them."""
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if k not in ("title", "format")}
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


def json_schema(model: type[BaseModel]) -> dict:
    s = _strip_titles(model.model_json_schema())
    s["additionalProperties"] = False
    return s


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(text: str, schema: type[BaseModel]) -> tuple[dict | None, str | None]:
    """Validate the first JSON object in `text` against `schema`."""
    m = _JSON_BLOCK.search(text)
    if not m:
        return None, "no JSON object in output"
    try:
        return schema.model_validate_json(m.group(0)).model_dump(mode="json"), None
    except ValidationError as e:
        return None, f"schema: {e.errors()[0]['msg']}"[:300]


class DatabricksClient:
    """Databricks Model Serving (Free Edition foundation models), OpenAI-style chat payload."""

    provider = "databricks"

    def __init__(self, model: str, timeout: float = 120, max_tokens: int = 1500):
        from databricks.sdk import WorkspaceClient  # imported lazily: optional at runtime

        self.model = model
        self._w = WorkspaceClient()
        self._http = httpx.Client(timeout=timeout)
        self._max_tokens = max_tokens

    def _post(self, payload: dict, max_retries: int = 6) -> httpx.Response:
        """POST with backoff on 429/5xx: free-tier endpoints rate-limit aggressively."""
        url = f"{self._w.config.host}/serving-endpoints/{self.model}/invocations"
        for attempt in range(max_retries + 1):
            resp = self._http.post(url, headers=self._w.config.authenticate(), json=payload)
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            if attempt == max_retries:
                return resp
            retry_after = resp.headers.get("retry-after")
            wait = (
                float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt + 1)
            )
            time.sleep(min(wait, 60))
        return resp

    def complete(self, messages, schema=None, tools=None, cache_key=None) -> Response:
        if tools:
            raise NotImplementedError("tool calling arrives with project C")
        payload: dict[str, Any] = {
            "messages": [m.model_dump() for m in messages],
            "temperature": 0,
            "max_tokens": self._max_tokens,
        }
        mode: Literal["constrained", "prompted", "none"] = "none"
        t0 = time.perf_counter()
        if schema is not None:
            mode = "constrained"
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": json_schema(schema),
                    "strict": True,
                },
            }
        resp = self._post(payload)
        if schema is not None and resp.status_code == 400:
            # Grammar engine refused the schema: fall back to asking for JSON in the prompt.
            mode = "prompted"
            payload.pop("response_format")
            hint = (
                "\n\nAnswer with a single JSON object only, matching this JSON schema:\n"
                + json.dumps(json_schema(schema))
            )
            msgs = payload["messages"]
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + hint}
            resp = self._post(payload)
        latency = int((time.perf_counter() - t0) * 1000)
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):  # reasoning models return typed parts
            content = "".join(p.get("text", "") for p in content if p.get("type") == "text")
        usage = body.get("usage") or {}
        out = Response(
            text=content,
            provider=self.provider,
            model=self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency,
            structured_mode=mode,
        )
        if schema is not None:
            out.parsed, out.parse_error = parse_json(content, schema)
        return out


class CachedClient:
    """Disk cache keyed by (cache_key = prompt version, provider, model, hash of the input)."""

    def __init__(self, inner: LLMClient, directory: Path = Path(".cache/llm")):
        self.inner = inner
        self.provider, self.model = inner.provider, inner.model
        self.dir = directory

    def _path(self, messages, schema, cache_key) -> Path:
        blob = json.dumps(
            {
                "k": cache_key,
                "p": self.provider,
                "m": self.model,
                "msgs": [m.model_dump() for m in messages],
                "schema": json_schema(schema) if schema else None,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return self.dir / f"{hashlib.sha256(blob.encode()).hexdigest()}.json"

    def complete(self, messages, schema=None, tools=None, cache_key=None) -> Response:
        path = self._path(messages, schema, cache_key)
        if path.exists():
            return Response.model_validate_json(path.read_text(encoding="utf-8")).model_copy(
                update={"cached": True}
            )
        resp = self.inner.complete(messages, schema=schema, tools=tools, cache_key=cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.model_dump_json(), encoding="utf-8")
        return resp


def make_client(model: str, cache_dir: Path | None = Path(".cache/llm")) -> LLMClient:
    """`model` is a Databricks serving endpoint name today; other providers plug in here."""
    client: LLMClient = DatabricksClient(model)
    return CachedClient(client, cache_dir) if cache_dir else client
