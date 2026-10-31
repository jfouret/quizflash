# Changelog

All notable changes to QuizDeck are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-10-31

### Added

- Study sessions can combine several decks: `deck_id` may be repeated on
  `/api/study/next`, `/api/study/batch` and `/api/study/tags`, and the new
  `GET /api/study/due` returns the due count for the current selection. The tag
  list and due count refresh when the deck selection changes.
- Per-deck grading scale: answers are rated from `0` to a deck-defined maximum,
  with optional labels per level (for example `3=Bad, 5=Average, 7=Good`). The
  judge is given the scale and the level is mapped to the scheduler's `1..4`.
- Cards can be edited from the deck page.
- History (`/history`, `GET`/`DELETE /api/history`): past answers with rating,
  judge feedback, expected answer and the stored teacher explanation, filterable
  and clearable per deck or entirely. No audio is retained.
- Statistics (`/stats`, `GET /api/stats/breakdown`): mean rating normalized out
  of 10 and correct rate per card and per tag, charted with a bundled Chart.js.

### Changed

- Rating levels now run from `0` to `max` (default `0..4`) instead of `1..4`.
- Changing a deck's grading scale is refused once the deck has answers; copy the
  deck first. Copies keep the scale.

## [0.5.2] - 2026-10-31

### Changed

- The study menu lists only the tags present in the selected deck, refreshed when
  the deck changes (`GET /api/study/tags` accepts `deck_id`).

### Fixed

- CI no longer publishes an image, attests or creates a release from a pull
  request; publishing stays on `main` pushes and manual refresh runs.

## [0.5.1] - 2026-10-31

### Fixed

- Batch mode: a voice answer is transcribed in the background, so the next card
  appears as soon as recording ends instead of waiting for speech-to-text.
- Batch review waits for **Next** (or Enter) before showing the following card,
  instead of advancing when the explanation audio ends.
- A finished batch shows a completion screen with **Continue** (a new batch, same
  deck and tags) and **Back to menu**, instead of starting a batch automatically.

## [0.5.0] - 2026-10-31

### Added

- Batch study mode: answer a batch of cards (default size 5) back to back, then
  review their explanations. Judging, the teacher and speech run in the
  background, so the next card appears as soon as the current answer is
  submitted. The batch loops back to the first card for review and advances when
  the explanation audio ends. Controlled per user in **Settings → Study flow**.
- The study view waits for a **Start** button, so a deck and tags can be chosen
  first. Available tags can be checked to filter the queue (a card matches when it
  carries at least one checked tag), and each card shows its own tags.
- `GET /api/study/batch` returns up to `size` due cards; `GET /api/study/tags`
  lists the tags available in the queue; `tag` may be repeated on `/api/study/next`
  and `/api/study/batch` to filter.
- `POST /api/study/speak` synthesizes arbitrary text, so a prefetched explanation
  is not generated twice.

### Changed

- The study view shows batch progress dots and animates card changes.

## [0.4.1] - 2026-10-31

### Changed

- Teacher default prompt now asks for a short Markdown answer (at most two
  sentences), so a review round stays fast. Study explanations render Markdown.
- TTS audio streams from OpenRouter to the browser and playback starts before the
  clip is fully generated, with a buffered fallback when the browser cannot stream
  MP3.
- The Verbalizer prompts are optional: its pass only runs when a user enables a
  vocal-ready setting, and empty prompts no longer block saving.
- The Agents page uses monospace prompt fields that keep line breaks, and adds a
  **Restore default prompts** button for the current step.

## [0.4.0] - 2026-10-31

### Added

- Admin **Agents** page with one tab per model step: Judge, Teacher, TTS,
  Verbalizer and STT. Each step stores its model, base URL, API key environment
  variable name, voice (TTS), system prompt and Jinja prompt template.
- Default prompts respect the requested language and keep technical terms,
  proper nouns, code identifiers and abbreviations in their original form.
- Prompt templates render card, deck and answer fields such as
  `{{ card.question }}`, `{{ card.answer }}`, `{{ deck.context }}` and
  `{{ user_answer }}`.

### Changed

- API keys are read from environment variables only. The Agents UI never stores
  or displays a key, and saving a step requires the named variable to be set.
- The Verbalizer has its own agent settings instead of sharing the Teacher model.

## [0.3.0] - 2026-10-31

### Added

- The UI footer shows the application version and the image build tag
  (`X.Y.Z-YYYY-MM-DD`), so the running release is visible without calling
  `/healthz`.

### Fixed

- Speech-to-text calls the OpenRouter `/api/v1/audio/transcriptions` endpoint
  instead of the nonexistent root `/audio/transcriptions` path.
- The default TTS voice is `en_paul_neutral`, which Mistral Voxtral TTS accepts;
  the previous `alloy` default made the provider return 404. `TTS_VOICE` must
  match one of the configured model's `supported_voices`.
- TTS and STT base URLs that already end in `/api/v1` or `/v1` no longer get a
  duplicated path prefix.

## [0.2.2] - 2026-10-31

### Added

- `LICENSE`: the project is now distributed under the European Union Public
  Licence v. 1.2 (`EUPL-1.2`).
- Releases ship the SLSA build provenance bundle as `quizflash.intoto.jsonl`, so
  the published image digest can be verified from the release page.

### Changed

- Docker base images are pinned by digest; Renovate keeps the digests current.
- The container smoke test parses the version from `/healthz` without piping a
  download into an interpreter.

## [0.2.1] - 2026-10-31

### Fixed

- Deck form redirects build their target with a literal prefix instead of an
  f-string, so CodeQL can prove they never leave the site (`py/url-redirection`).
- The API docs CSP test compares exact directive tokens instead of searching the
  header for a URL substring (`py/incomplete-url-substring-sanitization`).

## [0.2.0] - 2026-10-31

### Added

- Release pipeline: the version in `pyproject.toml` is the single source of truth.
  Merging a version bump on `main` builds, tests and scans the image, publishes it
  under immutable tags (`0.2.0`, `0.2.0-2026-10-31`, `0.2`, `latest`, `sha-<commit>`),
  attaches a build provenance attestation, then tags the commit and opens a GitHub
  Release with the matching changelog section.
- CI gates on every pull request: ruff, mypy and pytest inside the production image,
  Trivy repository and image scans (SARIF in the Security tab), a container smoke test
  in local and OIDC modes, and a version/changelog check.
- Daily rescan of the published image; a fixable HIGH/CRITICAL finding triggers a
  refresh rebuild with fresh dependencies. OpenSSF Scorecard runs weekly.
- `tests/test_security.py`: no unauthenticated access on any HTTP route or MCP method,
  in local and OIDC mode, plus cookie, CSRF, token and CSP regression tests.
- `/healthz` endpoint and a container `HEALTHCHECK`.
- `SECURITY.md` and `docs/release.md`.

### Changed

- htmx is served by the application instead of a CDN, and the Content-Security-Policy
  now restricts scripts and styles to `'self'`. Inline scripts and styles moved to
  `app/static/js/` and `app/static/style.css`; static URLs carry the app version.
- Added `Strict-Transport-Security` and `Permissions-Policy` response headers.
- Renovate: major updates (and Python minor versions) need manual review, Docker base
  images and GitHub Actions are pinned to digests, PyPI releases wait three days
  (security fixes excepted), and every dependency PR bumps the patch version.
- The Docker image is built in stages: the test stage runs the checks, the runtime
  stage ships without uv, pip or the build cache, and runs as uid 1000.
- Free-text fields have length limits; uploaded audio is parsed with a restricted
  ffmpeg protocol and format whitelist.
- Dependency ranges have upper bounds, so major versions only arrive through Renovate.

### Removed

- Per-commit container tags: images are published per release, plus `sha-<commit>`.

## [0.1.1] - 2026-10-30
