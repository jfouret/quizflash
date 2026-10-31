#!/usr/bin/env bash
# Build app/static/style.css from app/static/css/input.css with the Tailwind v4
# standalone binary. No Node.js: the release ships a static executable, checked
# against the sha256 published with it.
#
# The built stylesheet is committed (like every other vendored asset), so a plain
# `uv run uvicorn` serves the real thing. CI re-runs this script and fails on a
# diff, which is what keeps the committed file honest.
#
set -euo pipefail

# Renovate cannot bump a downloaded binary: update both values by hand on upgrade
# (the checksums come from the same release's sha256sums.txt).
tailwind_version="4.3.3"
sha_linux_x64="dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a"
sha_linux_arm64="55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/quizdeck"
binary="$cache_dir/tailwindcss-$tailwind_version"

case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) asset="tailwindcss-linux-x64"; sha="$sha_linux_x64" ;;
  Linux/aarch64 | Linux/arm64) asset="tailwindcss-linux-arm64"; sha="$sha_linux_arm64" ;;
  *)
    echo "::error::no pinned Tailwind binary for $(uname -s)/$(uname -m)." >&2
    echo "Add the checksum from the v$tailwind_version sha256sums.txt to this script." >&2
    exit 1
    ;;
esac

if [ ! -x "$binary" ]; then
  mkdir -p "$cache_dir"
  url="https://github.com/tailwindlabs/tailwindcss/releases/download/v$tailwind_version/$asset"
  echo "Downloading Tailwind v$tailwind_version ($asset)…" >&2
  curl -fsSL "$url" -o "$binary.tmp"
  echo "$sha  $binary.tmp" | sha256sum --check --status || {
    rm -f "$binary.tmp"
    echo "::error::checksum mismatch for $asset" >&2
    exit 1
  }
  chmod +x "$binary.tmp"
  mv "$binary.tmp" "$binary"
fi

cd "$root"
"$binary" --input app/static/css/input.css --output app/static/style.css --minify
echo "Wrote app/static/style.css" >&2
