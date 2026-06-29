FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "mcp_surveys.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
