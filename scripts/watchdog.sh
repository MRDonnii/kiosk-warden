#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/kiosk.conf"
# Restarts LightDM when the kiosk session is gone and only the login screen is showing (see display-guard.sh).
[[ -r "$HOME/kiosk/display-guard.sh" ]] && source "$HOME/kiosk/display-guard.sh"
source "$HOME/kiosk/kiosk-event.sh" 2>/dev/null || kiosk_event() { :; }

chrome_service_starting() {
  local entered now
  entered="$(systemctl --user show kiosk-chrome.service -p ActiveEnterTimestampMonotonic --value 2>/dev/null || echo 0)"
  now="$(awk '{printf "%.0f", $1 * 1000000}' /proc/uptime)"
  [[ "$entered" =~ ^[0-9]+$ && "$entered" -gt 0 && $((now - entered)) -lt 45000000 ]]
}

while true; do
  if declare -F display_guard_tick >/dev/null; then display_guard_tick || true; fi
  if ! pgrep -f "$HOME/.config/chrome-kiosk" >/dev/null; then
    if ! chrome_service_starting && systemctl --user restart kiosk-chrome.service; then
      printf '%s chrome-restart: Chrome not running (watchdog)\n' "$(date -Iseconds)" >>"$HOME/kiosk/recovery.log"
      kiosk_event recovery chrome-restart "Chrome not running" watchdog
    fi
  fi
  sleep 15
done
