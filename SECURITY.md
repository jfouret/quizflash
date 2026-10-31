# Security policy

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting:
<https://github.com/jfouret/quizflash/security/advisories/new>.

Include the affected version (`/healthz` reports it), the steps to reproduce, and
the impact you expect. You should get an answer within a week.

## Supported versions

The newest release and the newest build of the current minor version receive fixes.
Older minor versions are not maintained.

## What is in place

| Area | Measure |
|---|---|
| Authentication | Server-side sessions (opaque token, hash stored), scrypt passwords, OIDC authorization code + PKCE, login throttling |
| Session cookies | `__Host-` prefix, `HttpOnly`, `Secure`, `SameSite=Lax`, idle and absolute expiry, revoked on logout, suspension and role change |
| CSRF | Per-session token on every unsafe request, cross-site `Origin` rejected |
| Authorization | Strict per-user perimeter; foreign private content answers 404; admins cannot read user content |
| MCP | Personal hashed tokens only, never cookies; suspended or deleted users lose access immediately |
| Transport | HSTS, `Permissions-Policy`, `X-Frame-Options: DENY`, `nosniff` |
| XSS | Jinja autoescaping, strict `Content-Security-Policy` (`script-src 'self'`), no inline script or style |
| Uploads | 25 MB cap, audio formats and local-file protocol only for ffmpeg |
| Supply chain | Dependencies with upper bounds, digest-pinned base images and actions, Trivy and CodeQL scans, build provenance attestations, OpenSSF Scorecard |
| Tests | `tests/test_security.py` asserts anonymous access is refused on every route and MCP method, in local and OIDC mode |

## Hardening a deployment

- Serve over HTTPS and keep `COOKIE_SECURE=1`.
- Run the container with a read-only root filesystem and a tmpfs for `/data`:

  ```bash
  docker run -d --read-only --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /data:uid=1000,gid=1000,mode=0750 --tmpfs /tmp -p 127.0.0.1:8000:8000 \
    --env-file .env ghcr.io/jfouret/quizflash:0.2.0
  ```

- Put a reverse proxy in front for TLS, and keep the original `Host` header so OIDC
  redirect URIs stay `https`.
- Run a single worker: the login throttle and judge-fallback tokens live in process
  memory.
