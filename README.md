# QuizDeck

[![ci](https://github.com/jfouret/quizflash/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jfouret/quizflash/actions/workflows/ci.yml?query=branch%3Amain)
[![image scan](https://github.com/jfouret/quizflash/actions/workflows/scan.yml/badge.svg?branch=main)](https://github.com/jfouret/quizflash/security)
[![CodeQL](https://github.com/jfouret/quizflash/actions/workflows/github-code-scanning/codeql/badge.svg?branch=main)](https://github.com/jfouret/quizflash/security)
[![CodeFactor](https://www.codefactor.io/repository/github/jfouret/quizflash/badge)](https://www.codefactor.io/repository/github/jfouret/quizflash)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/jfouret/quizflash/badge)](https://scorecard.dev/viewer/?uri=github.com/jfouret/quizflash)
[![release](https://img.shields.io/github/v/release/jfouret/quizflash)](https://github.com/jfouret/quizflash/releases/latest)
[![ghcr](https://img.shields.io/badge/ghcr.io-jfouret%2Fquizflash-blue?logo=docker&logoColor=white)](https://github.com/jfouret/quizflash/pkgs/container/quizflash)

Self-hosted, multi-user spaced-repetition quiz application. Each user owns their decks, cards, settings, and progress; decks can be published to a public space where others follow or copy them. Answers are evaluated by a remote AI judge (written or voice), and an external AI agent can act on a user's account through MCP with a personal token.

## Features

- Multi-user accounts with `admin` and `user` roles. Local email/password login, or OpenID Connect (mandatory when configured; the admin role then comes from an IdP claim).
- Strict user perimeter: users only see their own private content. Admins manage users and app settings but cannot read other users' private decks.
- Public space: owners publish a deck; other users **follow** it (train on it, read-only, the owner keeps it updated) or **copy** it (an independent private deck they own). Every learner has their own schedule, logs, and stats.
- Admin console (`/admin`): user list, manual approval of new accounts, suspension, deletion, registration policy, defaults for new users, global teacher/voice switches, public-space switch, and unpublishing of public decks.
- Per-user settings; per-user permanent MCP tokens managed from `/settings`.
- Decks, cards, and first-class tags with full CRUD.
- Continuous review queue (`due <= now`), ordered by due date, with optional daily new/review limits.
- Batch study mode (on by default, batch size 5): answer a batch of cards back to back, then review their explanations. Judging, speech-to-text, the teacher and speech are prefetched in the background, so the next card appears as soon as the answer is submitted. The batch loops back to the first card for review and waits for **Next** (or Enter). Sessions start on a **Start** button, so a deck and tags can be chosen first; each card shows its tags. A finished batch offers **Continue** (a new batch, same deck and tags) or **Back to menu**.
- Evaluation modes:
  - `ai_preselect`: the AI proposes a rating and feedback; the user confirms or overrides.
  - `ai_assess`: the AI decides and the review is saved immediately.
  - `self_fallback`: manual rating, only available through a single-use token issued after an actual judge failure.
- Voice answers: automatic recording when microphone permission is granted, an elapsed-time counter, server-side remote STT, and an editable transcript. Settings can send the transcript straight to the judge or wait for validation. Corrections can be judged again before the review is saved. Response time, STT call duration, and audio duration are persisted.
- Deck-level and card-level context fields, plus an optional LLM teacher: after a result, the teacher explains the card using both contexts (toggle in settings; otherwise use the Teacher/Regenerate buttons in the result panel). Explanations render as Markdown.
- Spoken output (TTS via OpenRouter): per-user toggle speaks the question and the teacher explanation aloud; optional extra LLM passes ("vocal-ready") rewrite question and explanation into plain spoken sentences before synthesis. Playback streams so it starts before the clip is fully generated. Admin can disable TTS globally.
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
| `BUILD_TAG` | (none) | Build identifier shown in the UI footer; the image build sets it |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai` | Shared OpenRouter root; every `X_BASE_URL` below falls back to it |
| `OPENROUTER_API_KEY` | (none) | Shared key; every `X_API_KEY` below falls back to it |
| `JUDGE_BASE_URL` | `OPENROUTER_BASE_URL` | Judge root URL; `/api/alpha/decisions` is appended |
| `JUDGE_MODEL` | `inception/mercury-decide` | OpenRouter decision model |
| `JUDGE_API_KEY` | `OPENROUTER_API_KEY` | Judge API key |
| `STT_BASE_URL` | `OPENROUTER_BASE_URL` | Speech-to-text base; `/api/v1/audio/transcriptions` is appended (or `/audio/transcriptions` when the base already ends in `/v1`) |
| `STT_MODEL` | (none) | STT model |
| `STT_API_KEY` | `OPENROUTER_API_KEY` | STT API key |
| `TEACHER_BASE_URL` | `JUDGE_BASE_URL` → `OPENROUTER_BASE_URL` | Chat-completions base for the teacher; `/api/v1/chat/completions` is appended |
| `TEACHER_MODEL` | (none) | Teacher chat model (required for explanations) |
| `TEACHER_API_KEY` | `JUDGE_API_KEY` → `OPENROUTER_API_KEY` | Teacher API key |
| `VOCAL_MODEL` | `TEACHER_MODEL` | Cheap model for the vocal-ready (TTS) rewrite pass |
| `TTS_BASE_URL` | `TEACHER_BASE_URL` → `OPENROUTER_BASE_URL` | Speech base; `/api/v1/audio/speech` is appended |
| `TTS_MODEL` | (none) | TTS model (required for spoken output) |
| `TTS_API_KEY` | `TEACHER_API_KEY` → `OPENROUTER_API_KEY` | TTS API key |
| `TTS_VOICE` | `en_paul_neutral` | TTS voice; must be one of the model's `supported_voices` |
| `COOKIE_SECURE` | `1` | Send the session cookie only over HTTPS (`__Host-session`). Set `0` only for plain-HTTP local development |
| `SESSION_IDLE_HOURS` | `168` | A session expires after this much inactivity |
| `SESSION_MAX_HOURS` | `720` | Absolute session lifetime |
| `SECRET_KEY` | (random per process) | Signs the short-lived OIDC login-state cookie. Required with OIDC |
| `OIDC_ISSUER` | (none) | Issuer URL. When set, OIDC is the only login method |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | (none) | Confidential client credentials (required with OIDC) |
| `OIDC_SCOPES` | `openid email profile` | Requested scopes |
| `OIDC_ROLE_CLAIM` | `roles` | Claim holding roles; dotted paths allowed (e.g. `realm_access.roles` for Keycloak). Read from the ID token, the access token, and userinfo — whichever carries it |
| `OIDC_ADMIN_ROLE` | `admin` | Role value that grants the QuizDeck `admin` role |

Example:

```bash
export DATABASE_URL="sqlite:///./quizdeck.db"
export OPENROUTER_API_KEY="sk-or-..."        # shared by judge, STT, teacher and TTS
export JUDGE_MODEL="inception/mercury-decide"
export STT_MODEL="whisper-1"                 # STT base URL defaults to OPENROUTER_BASE_URL
export TEACHER_MODEL="openai/gpt-4o-mini"
export TTS_MODEL="openai/gpt-4o-mini-tts"
```

## Agent configuration

Administrators get an **Agents** page (`/admin/agents`) with one tab per model
step: Judge, Teacher, TTS, Verbalizer and STT. Each tab can override the model,
base URL, API key environment variable name, voice (TTS), system prompt and Jinja
prompt template. Empty fields fall back to the environment variables shown in
the form.

API keys are environment-only. The page stores the *name* of the variable (for
example `TEACHER_API_KEY`) but never the key value, and saving a tab fails until
that variable, or `OPENROUTER_API_KEY`, is set.

Prompt templates receive the card and answer context. For example:

```jinja
Question: {{ card.question }}
Expected answer: {{ card.answer }}
User answer: {{ user_answer }}
```

The defaults tell every model to respect the requested language and to keep
technical terms, proper nouns, code identifiers and abbreviations in their
original form instead of over-translating them. The Teacher default asks for a
short, Markdown answer (at most two sentences) so a review round stays fast. A
**Restore default prompts** button resets the system prompt and template of the
current step to the values shipped with the running version.

The Verbalizer step is optional: its pass only runs when a user enables a
vocal-ready option in their settings, and its prompts may be left empty.

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
- `/settings` — evaluation mode, batch size, voice auto-judging, languages, and daily limits
- `/docs` — generated OpenAPI documentation

## Tests and quality checks

```bash
uv run pytest
uv run mypy --strict
uv run ruff check .
uv run ruff format --check .
```

The same commands run inside the production image on every pull request
(`docker build --target test .`). `tests/test_security.py` asserts that no HTTP route
and no MCP method accepts an unauthenticated request, in local and OIDC mode.

## Docker

```bash
docker build -t quizdeck .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v quizdeck-data:/data \
  quizdeck
```

The image runs as uid 1000, stores the database under `/data`, includes `ffmpeg` for
audio duration measurement, and exposes `/healthz` for its `HEALTHCHECK`. No model
downloads occur at build time.

Published images live on GHCR:

```bash
docker run --rm -p 8000:8000 --env-file .env -v quizdeck-data:/data \
  ghcr.io/jfouret/quizflash:0.2.0
```

| Tag | Meaning |
|---|---|
| `0.2.0-2026-10-31` | Version 0.2.0, built on that date (never moves) |
| `0.2.0` | Newest build of 0.2.0 (moves on refresh) |
| `0.2`, `latest` | Newest 0.2.x / newest release |
| `sha-<commit>` | First build of that commit |

Releases are cut by CI when a version bump reaches `main`; dependency updates are
merged by Renovate and release a patch version each time. See
[`docs/release.md`](docs/release.md) for the full flow and how to verify an image.

## Further documentation

- [`docs/operations.md`](docs/operations.md) — HTTP API, MCP endpoint, study flow, and deployment notes.
- [`docs/release.md`](docs/release.md) — versioning, image tags, release and refresh flow, Renovate policy, required checks.
- [`SECURITY.md`](SECURITY.md) — how to report a vulnerability and what is in place.

## Licence

QuizDeck is distributed under the [European Union Public Licence v. 1.2](LICENSE)
(`EUPL-1.2`), the European Commission's own open-source licence. You may use, modify
and redistribute it, including commercially; if you distribute a modified version,
that version stays under the EUPL. Running it as a service creates no obligation to
publish your changes. The licence text is available in 23 languages from
[joinup.ec.europa.eu](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12).
