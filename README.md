# QuizDeck

Self-hosted, single-user spaced-repetition quiz application. Cards are fed by the owner, answers are evaluated by a remote AI judge (written or voice), and an external AI agent can manage everything through MCP.

## Features

- Decks, cards, and first-class tags with full CRUD.
- Continuous review queue (`due <= now`), ordered by due date, with optional daily new/review limits.
- Evaluation modes:
  - `ai_preselect`: the AI proposes a rating and feedback; the user confirms or overrides.
  - `ai_assess`: the AI decides and the review is saved immediately.
  - `self_fallback`: manual rating, only available through a single-use token issued after an actual judge failure.
- Voice answers: automatic recording when microphone permission is granted, an elapsed-time counter, server-side remote STT, and an editable transcript. Settings can send the transcript straight to the judge or wait for validation. Corrections can be judged again before the review is saved. Response time, STT call duration, and audio duration are persisted.
- Pluggable schedulers: FSRS (default, `fsrs` PyPI package) and SM-2, configurable per deck.
- SQL statistics per deck, card, and tag.
- FastMCP server mounted at `/mcp` for external AI agents.
- SQLite by default, swappable through `DATABASE_URL`.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- `ffmpeg`/`ffprobe` on the host for voice duration measurement
- An [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request) model
- A remote OpenAI-compatible STT API (e.g. OpenAI Whisper API, Groq)

No AI models run locally. The judge uses OpenRouter's dedicated `POST /api/alpha/decisions` endpoint, not chat completions. Decision models return typed correctness and rating decisions without prose feedback. The judge and STT are configured through environment variables.

The app loads `.env` automatically ([python-dotenv](https://pypi.org/project/python-dotenv/)). Copy `.env.example` to `.env` and fill in your keys; `.env` is gitignored.

## Configuration

Environment variables can come from the shell or a `.env` file (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./quizdeck.db` | SQLAlchemy database URL |
| `JUDGE_BASE_URL` | `https://openrouter.ai` | OpenRouter root URL; `/api/alpha/decisions` is appended |
| `JUDGE_MODEL` | `inception/mercury-decide` | OpenRouter decision model |
| `JUDGE_API_KEY` | (none) | Judge API key; falls back to `OPENROUTER_API_KEY` |
| `STT_BASE_URL` | (none) | OpenAI-compatible `/v1/audio/transcriptions` base |
| `STT_MODEL` | (none) | STT model |
| `STT_API_KEY` | (none) | STT API key |

Example:

```bash
export DATABASE_URL="sqlite:///./quizdeck.db"
export JUDGE_BASE_URL="https://openrouter.ai"
export JUDGE_MODEL="inception/mercury-decide"
export JUDGE_API_KEY="sk-or-..."
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
- `/settings` — evaluation mode, voice auto-judging, languages, and daily limits
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
