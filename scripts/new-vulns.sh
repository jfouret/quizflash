#!/usr/bin/env bash
# Fail when the new Trivy JSON report has findings (CVE + package) absent from the
# published one. A missing or unreadable published report counts as empty.
#
# Usage: scripts/new-vulns.sh <published.json> <new.json>
set -euo pipefail
export LC_ALL=C

ids() {
  { jq -r '.Results[]?.Vulnerabilities[]? | "\(.VulnerabilityID) \(.PkgName)"' "$1" 2>/dev/null || true; } | sort -u
}

[ -f "$2" ] || { echo "::error::no scan report at $2"; exit 1; }
known="$(comm -12 <(ids "$1") <(ids "$2"))"
new="$(comm -13 <(ids "$1") <(ids "$2"))"

if [ -n "$known" ]; then
  echo "::warning::Fixable vulnerabilities already in the published image (not blocking): $(echo "$known" | paste -sd, -)"
fi
if [ -n "$new" ]; then
  echo "::error::Fixable HIGH/CRITICAL vulnerabilities introduced by this build: $(echo "$new" | paste -sd, -)"
  exit 1
fi
echo "No new fixable HIGH/CRITICAL vulnerability."
