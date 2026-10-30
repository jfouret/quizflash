# QuizDeck

Self-hosted, multi-user spaced-repetition quiz application. Each user owns their decks, cards, settings, and progress; decks can be published to a public space where others follow or copy them. Answers are evaluated by a remote AI judge (written or voice), and an external AI agent can act on a user's account through MCP with a personal token.

## Features

- Multi-user accounts with `admin` and `user` roles. Local email/password login, or OpenID Connect (mandatory when configured; the admin role then comes from an IdP claim).
- Strict user perimeter: users only see their own private content. Admins manage users and app settings but cannot read other users' private decks.
- Public space: owners publish a deck; other users **follow** it (train on it, read-only, the owner keeps it updated) or **copy** it (an independent private deck they own). Every learner has their own schedule, logs, and stats.
- Admin console (`/admin`): user list, manual approval of new accounts, suspension, deletion, registration policy, defaults for new users, global teacher/voice switches, public-space switch, and unpublishing of public decks.
- Per-user settings; per-user permanent MCP tokens managed from `/settings`.
- Decks, cards, and first-class tags with full CRUD.
- Continuous review queue (`due <= now`), ordered by due date, with optional daily new/review limits.
- Evaluation modes:
  - `ai_preselect`: the AI proposes a rating and feedback; the user confirms or overrides.
  - `ai_assess`: the AI decides and the review is saved immediately.
  - `self_fallback`: manual rating, only available through a single-use token issued after an actual judge failure.
- Voice answers: automatic recording when microphone permission is granted, an elapsed-time counter, server-side remote STT, and an editable transcript. Settings can send the transcript straight to the judge or wait for validation. Corrections can be judged again before the review is saved. Response time, STT call duration, and audio duration are persisted.
- Deck-level and card-level context fields, plus an optional LLM teacher: after a result, the teacher explains the card using both contexts (toggle in settings; otherwise use the Teacher/Regenerate buttons in the result panel).
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
| `TEACHER_BASE_URL` | `JUDGE_BASE_URL` | Chat-completions base for the teacher; `/api/v1/chat/completions` is appended |
| `TEACHER_MODEL` | (none) | Teacher chat model (required for explanations) |
| `TEACHER_API_KEY` | `JUDGE_API_KEY` / `OPENROUTER_API_KEY` | Teacher API key |
| `COOKIE_SECURE` | `1` | Send the session cookie only over HTTPS (`__Host-session`). Set `0` only for plain-HTTP local development |
| `SESSION_IDLE_HOURS` | `168` | A session expires after this much inactivity |
| `SESSION_MAX_HOURS` | `720` | Absolute session lifetime |
| `SECRET_KEY` | (random per process) | Signs the short-lived OIDC login-state cookie. Required with OIDC |
| `OIDC_ISSUER` | (none) | Issuer URL. When set, OIDC is the only login method |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | (none) | Confidential client credentials (required with OIDC) |
| `OIDC_SCOPES` | `openid email profile` | Requested scopes |
| `OIDC_ROLE_CLAIM` | `roles` | Claim holding roles; dotted paths allowed (e.g. `realm_access.roles` for Keycloak) |
| `OIDC_ADMIN_ROLE` | `admin` | Role value that grants the QuizDeck `admin` role |

Example:

```bash
export DATABASE_URL="sqlite:///./quizdeck.db"
export JUDGE_BASE_URL="https://openrouter.ai"
export JUDGE_MODEL="inception/mercury-decide"
export JUDGE_API_KEY="sk-or-..."
export STT_BASE_URL="https://api.openai.com/v1"
export STT_MODEL="whisper-1"
export STT_API_KEY="sk-..."
export TEACHER_MODEL="openai/gpt-4o-mini"   # reuses JUDGE_BASE_URL and JUDGE_API_KEY
```

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Create the first administrator (local login mode):

```bash
uv run python -m app.cli create-admin --email admin@example.com
```

For plain-HTTP local development, export `COOKIE_SECURE=0`, otherwise the browser drops the session cookie.

Then open:

- `/login` — sign in (or `/signup`, depending on the registration policy)
- `/` — deck and card management
- `/explore` — public decks to follow or copy
- `/admin` — administration (admins only)
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
