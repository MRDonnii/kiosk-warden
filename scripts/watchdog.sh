#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/kiosk.conf"

chrome_service_starting() {
  local entered now
  entered="$(systemctl --user show kiosk-chrome.service -p ActiveEnterTimestampMonotonic --value 2>/dev/null || echo 0)"
  now="$(awk '{printf "%.0f", $1 * 1000000}' /proc/uptime)"
  [[ "$entered" =~ ^[0-9]+$ && "$entered" -gt 0 && $((now - entered)) -lt 45000000 ]]
}

while true; do
  if ! pgrep -f "$HOME/.config/chrome-kiosk" >/dev/null; then
    chrome_service_starting || systemctl --user restart kiosk-chrome.service || true
  fi
  sleep 15
done
