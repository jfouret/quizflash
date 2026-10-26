# QuizDeck

Self-hosted, single-user spaced-repetition quiz application. Cards are fed by the owner, answers are evaluated by a remote AI judge (written or voice), and an external AI agent can manage everything through MCP.

## Features

- Decks, cards, and first-class tags with full CRUD.
- Continuous review queue (`due <= now`), ordered by due date, with optional daily new/review limits.
- Evaluation modes:
  - `ai_preselect`: the AI proposes a rating and feedback; the user confirms or overrides.
  - `ai_assess`: the AI decides and the review is saved immediately.
  - `self_fallback`: manual rating, only available through a single-use token issued after an actual judge failure.
- Voice answers: browser recording → server-side remote STT API → editable transcript → judge. Response time, STT call duration, and audio duration are all persisted.
- Pluggable schedulers: FSRS (default, `fsrs` PyPI package) and SM-2, configurable per deck.
- SQL statistics per deck, card, and tag.
- FastMCP server mounted at `/mcp` for external AI agents.
- SQLite by default, swappable through `DATABASE_URL`.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- `ffmpeg`/`ffprobe` on the host for voice duration measurement
- A remote OpenAI-compatible judge API
- A remote OpenAI-compatible STT API (e.g. OpenAI Whisper API, Groq)

No AI models run locally. The judge and STT are configured purely through environment variables.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./quizdeck.db` | SQLAlchemy database URL |
| `JUDGE_BASE_URL` | (none) | OpenAI-compatible API base, e.g. `https://api.openai.com/v1` |
| `JUDGE_MODEL` | (none) | Judge chat model |
| `JUDGE_API_KEY` | (none) | Judge API key |
| `STT_BASE_URL` | (none) | OpenAI-compatible `/v1/audio/transcriptions` base |
| `STT_MODEL` | (none) | STT model |
| `STT_API_KEY` | (none) | STT API key |

Example:

```bash
export DATABASE_URL="sqlite:///./quizdeck.db"
export JUDGE_BASE_URL="https://api.openai.com/v1"
export JUDGE_MODEL="gpt-4o-mini"
export JUDGE_API_KEY="sk-..."
export STT_BASE_URL="https://api.openai.com/v1"
export STT_MODEL="whisper-1"
export STT_API_KEY="sk-..."
```

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

- `/` — deck and card management
- `/study` — continuous study queue
- `/settings` — evaluation mode, languages, and daily limits
- `/docs` — generated OpenAPI documentation

## Tests and quality checks

```bash
uv run pytest
uv run mypy --strict
uv run ruff check .
```

## Docker

```bash
docker build -t quizdeck .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v quizdeck-data:/data \
  quizdeck
```

The image runs as a non-root user, stores the database under `/data`, and includes `ffmpeg` for audio duration measurement. No model downloads occur at build time.

## Further documentation

- [`docs/operations.md`](docs/operations.md) — HTTP API, MCP endpoint, study flow, and deployment notes.
