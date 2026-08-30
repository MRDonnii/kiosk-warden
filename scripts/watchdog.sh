#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/kiosk.conf"

while true; do
  if ! pgrep -f "$HOME/.config/chrome-kiosk" >/dev/null; then
    systemctl --user restart kiosk-chrome.service || true
  fi
  sleep 15
done
