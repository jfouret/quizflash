# Releases, versioning and image tags

## One version, one place

`pyproject.toml` holds the version. The app reads it at import time
(`app.__version__`) and exposes it on `/healthz` and in the OpenAPI schema, so the
running container always reports the version it was built from.

`scripts/check-version.sh` runs on every pull request:

| Pull request | Requirement |
|---|---|
| Touches `app/`, `Dockerfile` or `pyproject.toml` | Version must be greater than `main` |
| Touches shipped code and is not a `renovate/*` branch | `CHANGELOG.md` needs a `## [x.y.z]` section |
| Docs, workflow or test-only change | No bump required |

Use patch for a fix, minor for a feature, major for a breaking change.

## What happens when a version bump reaches `main`

`.github/workflows/ci.yml` runs, in order:

1. Repository scan (Trivy: secrets and configuration).
2. `docker build --target test`: ruff, `ruff format --check`, mypy and pytest inside
   the production image (same Python, same dependencies, same ffmpeg).
3. Runtime image build.
4. Image scan; a fixable HIGH or CRITICAL vulnerability fails the job.
5. `scripts/smoke-test.sh`: the image must start read-only and non-root, and refuse
   anonymous access on the REST API and on `/mcp`, in local and OIDC mode.
6. Push the image tags, attach a build provenance attestation, push the `vX.Y.Z` tag
   and create the GitHub Release from the changelog section.

The image that was scanned and smoke-tested is the one that gets pushed: the job
builds once and retags locally, so no second dependency resolution can change it.

## Image tags

| Tag | Meaning | Moves? |
|---|---|---|
| `0.2.0-2026-10-31` | Version 0.2.0, built on that UTC date | Never |
| `0.2.0` | Newest build of 0.2.0 | On refresh only |
| `0.2` | Newest 0.2.x | On release or refresh |
| `latest` | Newest release | On release or refresh |
| `sha-<commit>` | First build of that commit | Never |

Pin the dated tag in production for a fully reproducible reference, or `0.2.0` to
follow rebuilds of the same version.

Note for Renovate users: a hyphen suffix reads as a variant or pre-release, so point
Renovate at the plain `X.Y.Z` tag, not the dated one.

## Refresh: same version, newer dependencies

`uv.lock` is not committed, so dependencies resolve at build time. A version can
therefore be rebuilt later with newer (for example patched) dependencies:

```bash
gh workflow run ci.yml --ref main -f refresh=true
```

That publishes a new `X.Y.Z-<date>` tag and moves `X.Y.Z`, `X.Y` and `latest`, but
does not create a release and never moves the `vX.Y.Z` git tag. The daily `scan`
workflow triggers this automatically when the published image has a fixable
HIGH/CRITICAL vulnerability.

## Verifying an image

```bash
gh attestation verify oci://ghcr.io/jfouret/quizflash:0.2.2 --repo jfouret/quizflash
docker run --rm ghcr.io/jfouret/quizflash:0.2.2 cat /app/pyproject.toml | grep ^version
```

Each release also carries `quizflash.intoto.jsonl`, the same SLSA provenance
bundle, so the image digest can be checked offline:

```bash
gh release download v0.2.2 -p quizflash.intoto.jsonl
slsa-verifier verify-image ghcr.io/jfouret/quizflash:0.2.2 \
  --provenance-path quizflash.intoto.jsonl --source-uri github.com/jfouret/quizflash
```

## Renovate policy

- Minor, patch, digest and security updates automerge once the required checks pass.
- Major updates, and Python minor versions (3.15 → 3.16), get a separate PR that waits
  for review.
- Every dependency PR bumps the patch version, so merging it releases a new image.
- Docker base images and GitHub Actions are pinned to immutable digests.
- PyPI releases must be at least three days old; security fixes skip that wait.

## Accepting a known vulnerability

Add an entry with an expiry date to `.trivyignore.yaml` and mention it in the PR:

```yaml
vulnerabilities:
  - id: CVE-2026-00000
    statement: Not reachable; the affected code path is unused.
    expired_at: 2026-12-31
```

Unfixed vulnerabilities are already excluded from the gate (`ignore-unfixed`), so an
entry is only needed for a fixable finding you deliberately postpone.

## Required checks and repository settings

These are one-time settings, applied with `gh`:

```bash
# Auto-merge (Renovate uses the platform feature, which waits for required checks)
gh api -X PATCH repos/jfouret/quizflash -f allow_auto_merge=true

# Immutable releases: a published tag can no longer be moved or deleted
gh api -X PUT repos/jfouret/quizflash/immutable-releases

# Private vulnerability reporting
gh api -X PUT repos/jfouret/quizflash/private-vulnerability-reporting

# Dependabot alerts (Renovate opens the PRs)
gh api -X PUT repos/jfouret/quizflash/vulnerability-alerts

# Required checks on main
gh api -X POST repos/jfouret/quizflash/rulesets --input - <<'JSON'
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "scan" },
          { "context": "version" },
          { "context": "build" }
        ]
      } },
    { "type": "code_scanning",
      "parameters": {
        "code_scanning_tools": [
          { "tool": "CodeQL", "security_alerts_threshold": "high_or_higher", "alerts_threshold": "errors" }
        ]
      } }
  ]
}
JSON
```

CodeQL uses GitHub's default setup (Settings → Code security → Code scanning), which
needs no workflow file.
