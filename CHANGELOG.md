# Changelog

All notable changes to QuizDeck are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/).

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
