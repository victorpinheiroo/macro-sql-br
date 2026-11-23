# One image for both the API and the Streamlit app.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /srv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --group app --no-install-project
COPY src ./src
COPY metrics ./metrics
COPY prompts ./prompts
COPY config ./config
COPY app ./app
COPY data/snapshot ./data/snapshot
RUN uv sync --frozen --no-dev --group app

RUN useradd --create-home app && mkdir -p /srv/.cache && chown app /srv/.cache
USER app
EXPOSE 8000 8501
CMD ["uvicorn", "macrosql.api:app", "--host", "0.0.0.0", "--port", "8000"]
