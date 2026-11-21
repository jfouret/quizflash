# syntax=docker/dockerfile:1@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183

FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    DATABASE_URL=sqlite:////data/quizdeck.db \
    PATH="/app/.venv/bin:$PATH"

# Shown in the UI footer; CI passes the immutable X.Y.Z-YYYY-MM-DD image tag.
ARG BUILD_TAG=""
ENV BUILD_TAG=$BUILD_TAG

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
# No lockfile in the repo: dependencies resolve at build time (see docs/release.md).
COPY pyproject.toml LICENSE ./
COPY app ./app

# Test stage: the same interpreter, dependency set and ffmpeg as the runtime image.
FROM base AS test
COPY tests ./tests
RUN uv sync \
    && uv run ruff check . \
    && uv run ruff format --check . \
    && uv run mypy \
    && uv run pytest -q

FROM base AS runtime
RUN uv sync --no-dev \
    # Drop build-time leftovers: uv itself, its 90 MB cache, and pip/setuptools
    # (never used at runtime, and pip vendors libraries with known CVEs).
    && rm -rf /root/.cache /bin/uv /bin/uvx \
    && rm -rf /usr/local/lib/python3.15/site-packages/pip \
        /usr/local/lib/python3.15/site-packages/pip-* \
        /usr/local/lib/python3.15/site-packages/setuptools* \
        /usr/local/bin/pip* \
    && useradd --uid 1000 --create-home appuser \
    && mkdir -p /data \
    && chown -R 1000:1000 /data

USER 1000:1000
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
