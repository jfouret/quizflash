# syntax=docker/dockerfile:1@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183

FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS uv
FROM python:3.15-slim@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5 AS base

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

# Apply Debian security fixes the pinned base image predates: upgrade against the
# trixie-security stanza only, so no point-release or other update slips in.
RUN mkdir /tmp/security \
    && awk -v RS= -v ORS='\n\n' '/debian-security/' /etc/apt/sources.list.d/debian.sources \
        > /tmp/security/security.sources \
    && apt-get update -o Dir::Etc::SourceList=/dev/null -o Dir::Etc::SourceParts=/tmp/security \
    && apt-get upgrade -y -o Dir::Etc::SourceList=/dev/null -o Dir::Etc::SourceParts=/tmp/security \
    && rm -rf /tmp/security \
    && apt-get update \
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
    && uv run pytest -q --cov --cov-report=term --cov-report=json:/app/coverage.json

# Only the coverage report, so CI can export it: docker build --target coverage --output ...
FROM scratch AS coverage
COPY --from=test /app/coverage.json /coverage.json

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
