#!/usr/bin/env bash
# Container smoke test: the image must start read-only, stay non-root, and refuse
# anonymous access on both the REST API and the MCP endpoint, with and without OIDC.
#
# Usage: scripts/smoke-test.sh <image> <expected-version>
set -euo pipefail

IMAGE="${1:?usage: smoke-test.sh <image> <version>}"
VERSION="${2:?usage: smoke-test.sh <image> <version>}"
PORT="${PORT:-18080}"
BASE="http://127.0.0.1:$PORT"
CONTAINER="quizflash-smoke-$$"

fail() {
  echo "FAIL: $*" >&2
  docker logs "$CONTAINER" >&2 || true
  exit 1
}

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

start() {
  cleanup
  docker run -d --name "$CONTAINER" \
    --read-only --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /data:uid=1000,gid=1000,mode=0750 --tmpfs /tmp \
    -p "127.0.0.1:$PORT:8000" \
    "$@" "$IMAGE" >/dev/null
}

wait_ready() {
  for _ in $(seq 1 60); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz" || true)" = "200" ]; then
      return 0
    fi
    sleep 1
  done
  fail "the app did not answer /healthz within 60s"
}

expect() {
  local want="$1" method="$2" path="$3"
  shift 3
  local got
  got=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$@" "$BASE$path")
  [ "$got" = "$want" ] || fail "$method $path returned $got, expected $want"
}

expect_header() {
  local path="$1" name="$2" pattern="$3"
  curl -s -D - -o /dev/null "$BASE$path" | grep -qiE "^$name: .*$pattern" \
    || fail "$path is missing header $name matching /$pattern/"
}

check_anonymous_denied() {
  expect 401 GET /api/decks
  expect 401 GET /api/settings
  expect 401 GET /api/admin/users
  expect 401 POST /api/decks -H 'Content-Type: application/json' -d '{"name":"x"}'
  expect 401 POST /api/study/answer -H 'Content-Type: application/json' -d '{"card_id":1}'
  expect 401 GET /api/decks -H "Authorization: Bearer qd_smoke"
  expect 303 GET /admin
  expect 303 GET /
  expect 401 POST /mcp/ -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
  expect 401 POST /mcp/ -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer qd_smoke' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
}

check_hardening() {
  expect_header /login content-security-policy "script-src 'self'"
  expect_header /login strict-transport-security "max-age="
  expect_header /login permissions-policy "microphone=\\(self\\)"
  expect_header /login x-content-type-options "nosniff"
  if curl -s "$BASE/login" | grep -qE '<script>'; then
    fail "/login still contains an inline <script> block"
  fi
  if [ "$(docker inspect --format '{{.Config.User}}' "$IMAGE")" != "1000:1000" ]; then
    fail "the image does not run as uid 1000"
  fi
}

echo "== local login mode"
start
wait_ready
[ "$(curl -s "$BASE/healthz" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')" = "$VERSION" ] \
  || fail "/healthz does not report version $VERSION"
check_anonymous_denied
check_hardening
[ "$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER")" != "unhealthy" ] \
  || fail "container healthcheck reports unhealthy"
echo "OK: local mode"

echo "== OIDC mode"
start \
  -e OIDC_ISSUER=https://idp.invalid/realms/smoke \
  -e OIDC_CLIENT_ID=smoke \
  -e OIDC_CLIENT_SECRET=smoke-secret \
  -e SECRET_KEY=smoke-secret-key-value-0123456789
wait_ready
check_anonymous_denied
expect 404 POST /login -d 'email=a@b.c&password=x'
expect 404 GET /signup
curl -s "$BASE/login" | grep -q '/auth/oidc/login' || fail "/login does not offer single sign-on"
echo "OK: OIDC mode"

echo "All smoke checks passed."
