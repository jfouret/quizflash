# Changelog

All notable changes to QuizDeck are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/).

## [0.11.0] - 2026-11-01

### Added

- **Pause** next to the recorder: it pauses the recording (the elapsed counter stops with it)
  and resumes it, so an answer can be interrupted without losing what was already said.
- A floating player for spoken audio, with its own **Pause**/**Resume**, **Stop** and the same
  meter. Stop cancels the download of a clip still being synthesized, not just the sound, and
  Space toggles pause while a clip plays.
- The voice meters are redrawn: bars mirrored around a centre axis, inside a hairline frame,
  accent-coloured, and dimmed while a recording is paused.

## [0.10.0] - 2026-11-01

### Added

- The review panel repeats the question of the card being reviewed, above the answer that was
  judged.
- **Read questions aloud** (`auto_speak_questions`, a button on the study page and a switch in
  settings): each question is spoken when its card appears, the questions two cards ahead are
  synthesized in advance through the same queue and retry path, and with the microphone allowed
  the recording starts when the clip ends instead of when the card appears.
- The microphone is requested once when a session starts, so a batch does not stop at each
  permission prompt.
- The screen wake lock is held while a clip plays or a recording runs, so a phone does not sleep
  mid-answer.

### Changed

- The default teacher prompt no longer restates the question or the expected answer, which the
  learner already reads. It receives the rating, its label and the deck scale, and is asked to
  name what was missing and, when the answer was correct but below the top of the scale, what a
  stronger answer would have added. Existing installations keep their saved prompt: **Restore
  default prompts** on `/admin/agents` picks up the new one.

## [0.9.0] - 2026-11-01

### Added

- A review card whose transcription failed offers **Retry transcription** (and **Retry
  judging** when only the judge failed). The recording never leaves the browser tab until a
  transcription succeeds, so the audio is only kept long enough to retry, and nothing is
  written server-side.

### Fixed

- Speech-to-text calls are queued and start two seconds apart instead of bursting: a batch
  of voice answers reached the provider as five simultaneous requests and came back
  `429 Too Many Requests`. Speech synthesis queues the same way, one second apart.
- Upstream retries wait longer before giving up: 2 s, 5 s, then 15 s (was 1 s then 3 s), and
  a `Retry-After` is honoured up to 30 s.

## [0.8.0] - 2026-10-31

### Added

- The study result panel shows **Your answer** in a box above the expected answer,
  green when the judgement says the answer was correct and red when it says it was
  wrong (neutral while no judgement exists yet, for example after a judge failure
  awaiting a manual rating). The box is filled from the answer that was judged, so
  it also shows a transcribed voice answer.

## [0.7.6] - 2026-10-31

### Fixed

- Transient upstream failures no longer fail an answer outright. A rate-limited
  or overloaded provider (429, 5xx) or a dropped connection used to lose the
  review: the judge, the teacher, the verbalizer, speech-to-text and speech
  synthesis now retry twice, waiting 1 s then 3 s, and wait longer when the
  provider sends a short `Retry-After`. A four-hundred answer is never retried.
- The batch review no longer blocks on a card whose judging, transcription or
  explanation is still running: **Next** moves on, and the card fills in when the
  background work lands, if the user is still on it. Previously the review waited
  with the button disabled, which looked like a hang after a rate-limited
  transcription.

## [0.7.5] - 2026-10-31

### Fixed

- Speech synthesis failures now surface as an error instead of silent silence.
  The TTS provider call ran inside the streamed response, so a provider failure
  (wrong model or voice, expired key, timeout) was raised only after the `200 OK`
  header had left: the browser received an empty body labelled `audio/mpeg`,
  refused to decode it (`Media resource blob:… could not be decoded`) and the
  study view gave no clue. The call and its first chunk now happen before the
  response starts, so the route answers `502` with the usual message, and the
  content type the provider actually answered is passed on to the browser
  instead of a hardcoded `audio/mpeg`. A non-audio answer (for example an error
  body labelled `application/json`) is refused the same way.
- A failed explanation-audio prefetch is visible during the batch review
  (**explanation audio unavailable**) instead of leaving the card silent, and the
  study view releases the audio blobs it no longer plays.

## [0.7.4] - 2026-10-31

### Fixed

- The study view raising the phone keyboard is fixed for real, and the automatic
  voice flow can now be interrupted. Three changes:
  - The autofocus decision no longer trusts a media query. A pen counts as a fine
    pointer on some devices, which made the previous check focus the field anyway.
    `study.js` now watches the input actually in use: a touch or pen press disables
    autofocus for the rest of the session, a mouse press re-enables it.
  - **Type instead** (the old "Use text input") is an interrupt: it stops the
    recording in progress instead of letting the automatic flow transcribe and
    submit it, and it is the only action that raises the keyboard on purpose.
  - Each card starts as a text answer again, so a transcribed card no longer leaves
    the next one tagged as a voice answer.

## [0.7.3] - 2026-10-31

### Fixed

- The study view no longer raises the on-screen keyboard by itself. Every new card
  focused the answer field, and on a phone that keyboard then covered the question.
  The field is only focused when the device has a fine pointer (mouse or trackpad);
  a touch-only device is left alone. Submitting an answer also drops focus now, so
  the keyboard no longer sits over the result panel, and the `autofocus` attribute
  is gone from the study page.

## [0.7.2] - 2026-10-31

### Changed

- New decks start on a shipped notation: level `0` to `5`, labelled
  `0=False or absent, 1=Bad, 2=Average, 3=Better than average, 4=Good, 5=Perfect`.
  The maximum and the labels stay editable per deck, and existing decks keep the
  scale they were created with. The new-deck dialog says so, the study rating list
  shows the labels, and the judge's fallback scale follows the same default.

## [0.7.1] - 2026-10-31

### Fixed

- Icon-only links in the sidebar (admin, agents, settings) rendered as inline
  anchors, so their size was ignored: the glyphs sat off-centre, unevenly spaced,
  and under the 24 px minimum target size. An `.icon-btn` is a flex box now, like
  the icon buttons beside it.
- The theme button gave no clue which of its three states was in force: it kept one
  icon and only changed its tooltip. The icon now shows the state (sun, moon, or
  half sun/moon for "follow the system") and the label names the current state and
  what a click does next.

## [0.7.0] - 2026-10-31

### Added

- Own design system, built with the Tailwind CSS standalone CLI from
  `app/static/css/input.css` and committed as `app/static/style.css`. Colours,
  spacing, radii, shadows and motion are semantic tokens; light and dark come from
  one declaration each through `light-dark()`, so the duplicated palettes are gone.
- Persistent sidebar on desktop (brand, primary navigation, utility icons, account),
  which becomes a wrapped top bar below 1024px. One DOM, no drawer script.
- Real switch control for settings (`role="switch"`), replacing the framework's.
- `volume` and `close` symbols in the icon sprite, so no emoji remains as an icon.
- Accessibility pass: focus ring declared outside the cascade layers so nothing can
  override it, skip link to the content, WCAG 2.2 target sizes, and a global
  `prefers-reduced-motion` rule.

### Changed

- Every page restyled on the new tokens: quieter badges, hairline borders, measured
  elevation, one accent colour, larger question type on the study card, and a
  session start panel aligned with the card column.
- The charts and the voice meter read their colour from a resolved `color`
  property: a `light-dark()` token read through `getPropertyValue` came back
  unresolved.
- `scripts/build-css.sh` builds the stylesheet; CI rebuilds it and fails on a diff,
  so the committed file cannot drift from its source.

### Removed

- Pico CSS. Upstream archived the project on 2026-10-04 with v2.1.1 as its final
  release, and the vendored file shipped 83 KB of unmaintained CSS. Its element
  styling and the `--pico-*` variables are replaced by `input.css`.

### Fixed

- Navigation no longer drops its labels on tablets, and the current page stays
  marked with `aria-current` on both layouts.

## [0.6.2] - 2026-10-31

### Fixed

- Content-Security-Policy: htmx injected a `<style>` element for its indicator
  rules, which the strict `style-src 'self'` refused. `includeIndicatorStyles`
  is now off through the `htmx-config` meta tag and the rules live in
  `style.css`, so the page produces no CSP violation.
- The light/dark toggle stopped responding after an `hx-boost` navigation:
  htmx replaces the header, which removed the listener bound directly to the
  button. The toggle is now handled by delegation on `document`, and its label
  resyncs after each swap.

## [0.6.1] - 2026-10-31

### Fixed

- The stats charts rendered nothing: the data attribute was written with raw
  quotes, so the browser truncated it and `JSON.parse` failed. The JSON is now
  escaped for the attribute, and the chart colour is read correctly.

### Changed

- Nav is slimmer: primary links keep an icon and label, while settings, admin,
  agents, theme and logout are icon-only buttons with accessible labels and
  tooltips. Icons come from a vendored [Lucide](https://lucide.dev) sprite
  (`app/static/icons.svg`, ISC).

### Added

- Favicon and app icons: `favicon.svg`, `favicon.ico`, `apple-touch-icon.png`,
  a web app manifest, a `/favicon.ico` route, and the matching `<link>` tags.

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
