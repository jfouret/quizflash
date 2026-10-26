# Operations

## HTTP API

All API routes are prefixed with `/api`.

### Decks

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/decks` | List decks |
| `POST` | `/api/decks` | Create deck |
| `GET` | `/api/decks/{id}` | Get deck |
| `PATCH` | `/api/decks/{id}` | Update deck (including `eval_mode` override) |
| `DELETE` | `/api/decks/{id}` | Delete deck and all cards, states, and logs |

Deck fields include `scheduler` (`fsrs` or `sm2`), `scheduler_params`, and an optional `eval_mode` (`ai_preselect` or `ai_assess`) that overrides the global setting.

### Cards

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/cards?deck_id=&tag=` | List cards, optional filters |
| `POST` | `/api/cards` | Create card |
| `GET` | `/api/cards/{id}` | Get card |
| `PATCH` | `/api/cards/{id}` | Update card |
| `DELETE` | `/api/cards/{id}` | Delete card, state, and logs |

A card carries `question`, `answer`, optional `details`, optional `expected_time_s`, and tags (many-to-many).

### Tags

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/tags` | List tags |
| `DELETE` | `/api/tags/{id}` | Delete tag and its card links |

### Study

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/study/next?deck_id=` | Next due card, or `null` when the queue is empty |
| `POST` | `/api/study/transcribe` | Multipart audio upload, remote STT, editable transcript |
| `POST` | `/api/study/answer` | Judge, confirm, or save a review |

`/api/study/answer` behavior by mode:

- `ai_assess`: the judge result is persisted immediately.
- `ai_preselect`: the first call returns `status: "pending"` with the AI proposal; a second call with `confirmed: true` and the final `rating`/`is_correct` persists it.
- Judge failure: the first call returns `status: "fallback_required"` with a single-use `fallback_token`; a manual rating is then saved as mode `self_fallback`.

### Stats and settings

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stats?scope=deck|card|tag&id=` | Aggregates: total, correct, incorrect, correct rate, average response time, counts by mode |
| `GET` | `/api/settings` | Global settings |
| `PATCH` | `/api/settings` | Update evaluation mode, languages, and daily limits |

## MCP endpoint

The FastMCP server is mounted at `/mcp` and exposes:

- `list_decks`, `get_deck`, `create_deck`, `update_deck`, `delete_deck`
- `list_cards`, `get_card`, `create_card`, `update_card`, `delete_card`
- `list_tags`
- `list_due(deck_id?)`
- `get_stats(scope, target)` — `target` is a deck/card ID or tag name

Example client URL: `http://127.0.0.1:8000/mcp/`.

## Study flow (voice)

1. `GET /api/study/next` returns the card and starts the browser timer.
2. The browser records audio with `MediaRecorder`.
3. `POST /api/study/transcribe` measures audio duration from the uploaded container, calls the remote STT API, and returns `{text, stt_duration_ms, audio_duration_ms}`.
4. The transcript stays editable in the browser.
5. `POST /api/study/answer` sends the final answer text, `input_method: "voice"`, and all timing values.
6. The judge maps the answer to `rating` (1=Again..4=Easy) and `is_correct` independently.
7. The deck's scheduler reschedules the card and an `AnswerLog` row is persisted.

If the STT call fails, the voice attempt is logged server-side and the user can still answer by text. If the judge fails or times out (5 s), manual self-assessment is offered through a single-use fallback token.

## Schedulers

- `fsrs` (default): wraps the `fsrs` package. Deck parameters: `desired_retention`, `max_interval_days`.
- `sm2`: classic SM-2. Deck parameters: `ease_start`, `min_interval_days`.

Changing a deck's scheduler resets that card's scheduler state on its next review. Low ratings (`Again`, `Hard` for SM-2) are always rescheduled by the scheduler.

## Deployment notes

- Single user, no authentication. Put the app behind a VPN or an authenticating reverse proxy before exposing it.
- Default database is `./quizdeck.db`; the Docker image uses `sqlite:////data/quizdeck.db` on a `/data` volume.
- Judge and STT endpoints are read from environment variables at runtime; no keys are stored in the database.
- `ffmpeg`/`ffprobe` must be available on bare-metal deployments for voice duration measurement.
- Config is environment-only: there is no local model download and no AI-off mode in v1.
