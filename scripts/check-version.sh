#!/usr/bin/env bash
# Pull-request gate: shipped code must come with a version bump, and a human change
# must document it in CHANGELOG.md. Renovate bumps the patch version itself.
#
# Usage: scripts/check-version.sh [base-ref]   (default: origin/main)
set -euo pipefail

base_ref="${1:-origin/main}"
fail() {
  echo "::error::$*"
  exit 1
}

read_version() {
  sed -n 's/^version = "\(.*\)"/\1/p' "$1" | head -1
}

current="$(read_version pyproject.toml)"
base="$(git show "$base_ref:pyproject.toml" | sed -n 's/^version = "\(.*\)"/\1/p' | head -1)"
[ -n "$current" ] || fail "pyproject.toml has no version"
[ -n "$base" ] || fail "cannot read the version on $base_ref"

if [ "$current" = "$base" ]; then
  if git diff --quiet "$base_ref...HEAD" -- app Dockerfile pyproject.toml; then
    echo "No shipped code changed (app/, Dockerfile, pyproject.toml): version bump not required."
    exit 0
  fi
  fail "version is still $base: bump it (patch = fix, minor = feature, major = breaking change)."
fi

highest="$(printf '%s\n%s\n' "$base" "$current" | sort -V | tail -1)"
[ "$highest" = "$current" ] || fail "version $current is not greater than $base on $base_ref"

case "${GITHUB_HEAD_REF:-}" in
  renovate/*) echo "Renovate branch: CHANGELOG entry not required." ;;
  *)
    grep -q "^## \[$current\]" CHANGELOG.md \
      || fail "CHANGELOG.md has no '## [$current]' section."
    ;;
esac

echo "Version $base -> $current OK."
