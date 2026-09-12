#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(cat "$ROOT/VERSION")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
grep -q "^## v${version} " "$ROOT/CHANGELOG.md"
test -f "$ROOT/RELEASES.md"
for file in "$ROOT"/install.sh "$ROOT"/scripts/*.sh; do bash -n "$file"; done
python3 -m py_compile "$ROOT"/scripts/*.py "$ROOT"/webui/*.py
python3 -m unittest discover -s "$ROOT/tests" -p 'test_*.py'
rg -q 'python3-websocket' "$ROOT/install.sh"
rg -q 'scripts/\*\.py' "$ROOT/install.sh"
rg -q 'scripts/\*\.py' "$ROOT/scripts/self-update.sh"
echo "Kiosk Warden release checks passed: v$version"
