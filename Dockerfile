FROM ghcr.io/astral-sh/uv:0.7.7 AS uv
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DATABASE_URL=sqlite:////data/quizdeck.db \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
# No lockfile in the repo (gitignored): dependencies resolve at build time.
COPY pyproject.toml ./
COPY app ./app
RUN uv sync --no-dev \
    && useradd --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data

USER appuser
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
