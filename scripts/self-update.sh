#!/usr/bin/env bash
# Pulls the latest kiosk-warden from GitHub and installs it in place.
# Run this via `systemd-run --user` (see mqtt-control.sh / webui/server.py)
# so it survives the service restarts it triggers on itself.
set -uo pipefail

REPO_URL="${KIOSK_WARDEN_REPO:-https://github.com/MRDonnii/kiosk-warden.git}"
KIOSK_DIR="$HOME/kiosk"
VERSION_FILE="$KIOSK_DIR/.version"

# shellcheck disable=SC1090,SC1091
source "$KIOSK_DIR/kiosk.conf" 2>/dev/null || true
# shellcheck disable=SC1090,SC1091
source "$KIOSK_DIR/mqtt-lib.sh" 2>/dev/null || true

publish_update_state() {
  local installed="$1" latest="$2"
  [[ -n "${BASE_TOPIC:-}" ]] || return 0
  local payload
  payload="$(printf '{"installed_version":"%s","latest_version":"%s"}' "$installed" "$latest")"
  mqtt_pub "$BASE_TOPIC/update/state" "$payload" -r 2>/dev/null || true
}

current="$(cat "$VERSION_FILE" 2>/dev/null || echo unknown)"

latest="$(git ls-remote "$REPO_URL" HEAD 2>/dev/null | awk '{print $1}')"
if [[ -z "$latest" ]]; then
  echo "ERROR kunne ikke kontakte GitHub"
  exit 1
fi

if [[ "$latest" == "$current" ]]; then
  echo "UPTODATE $latest"
  publish_update_state "${current:0:7}" "${latest:0:7}"
  exit 0
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

if ! git clone --depth 1 "$REPO_URL" "$workdir/repo" -q; then
  echo "ERROR git clone fejlede"
  exit 1
fi
repo="$workdir/repo"
actual_latest="$(git -C "$repo" rev-parse HEAD)"

# Replace files with atomic renames (cp to a .new file, then mv) so any
# script currently executing from the old file (including this one, when
# self-update.sh is among the files being replaced) keeps running from its
# already-open file descriptor instead of reading a half-written file.
replace_atomic() {
  local src="$1" dst="$2" mode="${3:-755}"
  cp "$src" "$dst.new"
  chmod "$mode" "$dst.new"
  mv "$dst.new" "$dst"
}

for f in "$repo"/scripts/*.sh; do
  replace_atomic "$f" "$KIOSK_DIR/$(basename "$f")"
done
[[ -f "$repo/icon.svg" ]] && replace_atomic "$repo/icon.svg" "$KIOSK_DIR/icon.svg" 644
[[ -f "$repo/CHANGELOG.md" ]] && replace_atomic "$repo/CHANGELOG.md" "$KIOSK_DIR/CHANGELOG.md" 644

mkdir -p "$KIOSK_DIR/webui"
for f in "$repo"/webui/*.py; do
  replace_atomic "$f" "$KIOSK_DIR/webui/$(basename "$f")"
done

mkdir -p "$HOME/.config/systemd/user"
for f in "$repo"/systemd/*.service; do
  replace_atomic "$f" "$HOME/.config/systemd/user/$(basename "$f")" 644
done

echo "$actual_latest" > "$VERSION_FILE"

systemctl --user daemon-reload
systemctl --user restart \
  kiosk-mqtt-stats.service kiosk-mqtt-control.service \
  kiosk-watchdog.service kiosk-health.service \
  kiosk-vnc.service kiosk-novnc.service || true
systemctl --user restart kiosk-chrome.service || true

publish_update_state "${actual_latest:0:7}" "${actual_latest:0:7}"
echo "UPDATED $actual_latest"

# Restart the web UI last, after a short delay, so an HTTP-triggered update
# has time to send its response before this process's caller gets killed.
(sleep 2 && systemctl --user restart kiosk-webui.service) >/dev/null 2>&1 &
disown
