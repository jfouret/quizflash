# Operations

## Authentication and sessions

- **Local mode** (no `OIDC_ISSUER`): email/password accounts. Passwords are hashed with scrypt. Login attempts are throttled per client IP and email (5 failures per 15 minutes, in-memory per process). Bootstrap the first admin with `uv run python -m app.cli create-admin --email ...`.
- **OIDC mode** (`OIDC_ISSUER` set): `/login` only offers single sign-on (authorization code + PKCE); password login and `/signup` return 404. Users are matched on the `(iss, sub)` pair only, never by email; a new identity whose email is already taken is refused. The role is re-synced from `OIDC_ROLE_CLAIM` at every login (`admin` when it contains `OIDC_ADMIN_ROLE`), and a role change revokes existing sessions. Register `https://<host>/auth/oidc/callback` as redirect URI.
- **Registration policy** (admin setting): `open` (active immediately), `approval` (default; an admin validates the account), or `closed`. It applies to OIDC first logins too; IdP admins are always active.
- **Sessions** are server-side. The cookie holds a random opaque token (only its SHA-256 is stored), is `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, and named `__Host-session`. A fresh token is issued at every login; logout deletes it. Sessions expire after `SESSION_IDLE_HOURS` of inactivity or `SESSION_MAX_HOURS` in total. Suspending, deleting, or changing the role of a user revokes all their sessions.
- **CSRF**: every unsafe request (`POST`, `PATCH`, `DELETE`) needs the per-session token, sent as the `X-CSRF-Token` header or a `csrf_token` form field, and a cross-site `Origin` header is rejected. `GET /api/auth/me` returns the token for API clients; pages embed it.
- The REST API accepts **only** the browser session. Bearer tokens are rejected there.

## Perimeter rules

| Resource | Owner | Follower (public deck) | Any user (public deck) | Others / admins (private deck) |
|---|---|---|---|---|
| Read deck, cards | yes | yes | yes | 404 |
| Train (`/api/study/*`), stats | yes | yes | 403 until followed | 404 |
| Edit or delete deck, cards | yes | 403 | 403 | 404 |
| Copy | yes | yes | yes | 404 |

Settings, tags, tokens, schedules, answer logs, and stats are always per user: an owner never sees followers' answers. Unpublishing a deck cuts followers' access (their progress stays dormant); deleting it removes every learner's progress.

## HTTP API

All API routes are prefixed with `/api` and require a session (401 otherwise).

### Decks

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/decks` | List decks |
| `POST` | `/api/decks` | Create deck |
| `GET` | `/api/decks/{id}` | Get deck |
| `PATCH` | `/api/decks/{id}` | Update deck (including `eval_mode` override) |
| `DELETE` | `/api/decks/{id}` | Delete deck and all cards, states, and logs |

| `POST` | `/api/decks/{id}/follow` | Follow a public deck |
| `DELETE` | `/api/decks/{id}/follow` | Unfollow |
| `POST` | `/api/decks/{id}/copy` | Copy a readable deck into a new private deck you own |
| `GET` | `/api/public/decks` | Public decks with owner name, card count, and whether you follow them |

Deck fields include `scheduler` (`fsrs` or `sm2`), `scheduler_params`, an optional `eval_mode` (`ai_preselect` or `ai_assess`) that overrides the user setting, `visibility` (`private` or `public`), `owner_id`, and `source_deck_id` for copies.

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

- `ai_assess`: the judge result is persisted immediately by default. With `preview: true`, it returns `status: "pending"` without persisting; a second call with `confirmed: true` and the final `rating`/`is_correct` persists it. The study UI uses this preview so the input can be corrected and judged again before saving.
- `ai_preselect`: the first call returns `status: "pending"` with the AI proposal; a second call with `confirmed: true` and the final `rating`/`is_correct` persists it.
- Judge failure: the first call returns `status: "fallback_required"` with a single-use `fallback_token`; a manual rating is then saved as mode `self_fallback`.

### Stats and settings

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stats?scope=deck|card|tag&id=` | Aggregates: total, correct, incorrect, correct rate, average response time, counts by mode |
| `GET` | `/api/settings` | Your settings |
| `PATCH` | `/api/settings` | Update evaluation mode, voice auto-judging, languages, and daily limits |
| `GET` | `/api/settings/tokens` | Your MCP tokens (metadata only) |
| `POST` | `/api/settings/tokens` | Create an MCP token; the raw value is returned once |
| `DELETE` | `/api/settings/tokens/{id}` | Revoke an MCP token |
| `GET` | `/api/auth/me` | Current user and CSRF token |

### Admin (role `admin`, 403 otherwise)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/admin/users` | List users |
| `PATCH` | `/api/admin/users/{id}` | Set `status` (`pending`, `active`, `disabled`) or `role` (local mode only) |
| `DELETE` | `/api/admin/users/{id}` | Delete a user, their decks, and all their progress |
| `GET`/`PATCH` | `/api/admin/settings` | `registration`, `allow_public_decks`, `teacher_allowed`, `voice_allowed`, `default_settings` (applied to new users) |
| `POST` | `/api/admin/decks/{id}/unpublish` | Make a public deck private |

Admins cannot modify their own account, and the last active admin cannot be removed. `teacher_allowed: false` and `voice_allowed: false` override every user's settings.

## MCP endpoint

The FastMCP server is mounted at `/mcp` (stateless streamable HTTP, JSON responses). Every request needs a personal token created on `/settings`:

```
Authorization: Bearer qd_...
```

Tokens never expire, are stored hashed, are shown only once, and act with exactly the owner's perimeter. Revoke them from `/settings`; a suspended user's tokens stop working. Browser cookies are not accepted on `/mcp`.

Tools:

- `list_decks`, `get_deck`, `create_deck`, `update_deck`, `delete_deck`
- `list_cards`, `get_card`, `create_card`, `update_card`, `delete_card`
- `list_tags`
- `list_due(deck_id?)`
- `get_stats(scope, target)` — `target` is a deck/card ID or tag name
- `explain_card(card_id)`
- `list_public_decks`, `follow_deck(deck_id)`, `copy_deck(deck_id)`

Example client URL: `http://127.0.0.1:8000/mcp/`.

## Study flow (voice)

1. `GET /api/study/next` returns the card and starts the browser timer.
2. If the Permissions API reports an authorized microphone, recording starts automatically; otherwise the Record voice button requests access. An elapsed-time counter is visible while recording.
3. `POST /api/study/transcribe` measures audio duration from the uploaded container, calls the remote STT API, and returns `{text, stt_duration_ms, audio_duration_ms}`.
4. The transcript stays editable. The `voice_auto_judge` setting chooses between immediate judging and waiting for transcript validation.
5. `POST /api/study/answer` sends the final answer text, `input_method: "voice"`, all timing values, and `preview: true` from the study UI.
6. The OpenRouter Decisions API (`POST /api/alpha/decisions`) maps the answer to `rating` (1=Again..4=Easy) and `is_correct` independently. It returns no prose feedback.
7. The input can be corrected and judged again. In `ai_assess`, Next card saves the latest preview; in `ai_preselect`, Confirm review saves it. The deck's scheduler then reschedules the card and an `AnswerLog` row is persisted.

If the STT call fails, the voice attempt is logged server-side and the user can still answer by text. If the judge fails or times out (5 s), manual self-assessment is offered through a single-use fallback token.

## Schedulers

- `fsrs` (default): wraps the `fsrs` package. Deck parameters: `desired_retention`, `max_interval_days`.
- `sm2`: classic SM-2. Deck parameters: `ease_start`, `min_interval_days`.

Changing a deck's scheduler resets that card's scheduler state on its next review. Low ratings (`Again`, `Hard` for SM-2) are always rescheduled by the scheduler.

## Deployment notes

- Serve over HTTPS. Behind a TLS-terminating reverse proxy, keep the original `Host` header and run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy ip>` so OIDC redirect URIs use `https`.
- Every response carries `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy`, `Strict-Transport-Security` (when `COOKIE_SECURE=1`) and a strict `Content-Security-Policy` (`script-src 'self'`; no inline script or style). The generated docs at `/docs` and `/redoc` get a relaxed policy because Swagger UI loads from a CDN.
- `GET /healthz` is public and returns `{"status": "ok", "version": "x.y.z"}`; the image uses it for its `HEALTHCHECK`. It is the only unauthenticated application route besides login, signup, the OIDC endpoints and the API docs.
- The container runs as uid 1000 and can run with a read-only root filesystem:

  ```bash
  docker run --read-only --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /data:uid=1000,gid=1000,mode=0750 --tmpfs /tmp -p 127.0.0.1:8000:8000 \
    --env-file .env ghcr.io/jfouret/quizflash:0.2.0
  ```

- Voice uploads are capped at 25 MB server-side; raise `client_max_body_size` on the reverse proxy if you proxy them.
- The login throttle and judge-fallback tokens live in process memory: run a single worker, or move them to a shared store first.
- Schema migrations are managed by Alembic (`app/migrations`) and run automatically at startup. After a model change: `uv run alembic revision --autogenerate -m "..."`. Databases from the single-user version are not migrated; start from a new file.
- Default database is `./quizdeck.db`; the Docker image uses `sqlite:////data/quizdeck.db` on a `/data` volume.
- Judge and STT endpoints are read from environment variables at runtime; no keys are stored in the database.
- `ffmpeg`/`ffprobe` must be available on bare-metal deployments for voice duration measurement.
- Config is environment-only: there is no local model download and no AI-off mode in v1.
