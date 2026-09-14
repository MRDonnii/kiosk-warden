#!/usr/bin/env bash
set -euo pipefail
PROFILE="$HOME/.config/chrome-kiosk"
SERVICE_PID="$(systemctl --user show kiosk-chrome.service -p MainPID --value 2>/dev/null || echo 0)"

is_descendant() {
  local pid="$1" parent
  while [[ "$pid" =~ ^[0-9]+$ ]] && (( pid > 1 )); do
    [[ "$pid" == "$SERVICE_PID" ]] && return 0
    parent="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    [[ -n "$parent" && "$parent" != "$pid" ]] || break
    pid="$parent"
  done
  return 1
}

mapfile -t owned < <(pgrep -f -- "--user-data-dir=$PROFILE" || true)
for pid in "${owned[@]}"; do
  [[ "$pid" == "$$" ]] && continue
  is_descendant "$pid" && continue
  cmd="$(tr '\0' ' ' </proc/"$pid"/cmdline 2>/dev/null || true)"
  [[ "$cmd" == *"--user-data-dir=$PROFILE"* ]] || continue
  kill -TERM "$pid" 2>/dev/null || true
done
