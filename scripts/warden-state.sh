#!/usr/bin/env bash
set -euo pipefail

KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
source "$KIOSK_DIR/kiosk.conf"
source "$KIOSK_DIR/screen-backend.sh"
STATE_FILE="$KIOSK_DIR/warden_state.json"
LOCK_FILE="$KIOSK_DIR/warden-state.lock"
CHROME_LIFECYCLE="$KIOSK_DIR/chrome-lifecycle.py"
SCREEN_FILE="$KIOSK_DIR/screen_state"
WAKE_FILE="$KIOSK_DIR/wake_pending"

write_state() {
  local state="$1" reason="${2:-}" tmp="$STATE_FILE.tmp"
  jq -cn --arg state "$state" --arg reason "$reason" --arg at "$(date -Iseconds)" \
    '{state:$state,reason:$reason,changed_at:$at}' >"$tmp"
  mv "$tmp" "$STATE_FILE"
  printf '%s\n' "$state" >"$KIOSK_DIR/warden_state"
}

chrome_page_json() {
  curl -fsS --max-time 3 http://127.0.0.1:9222/json/list 2>/dev/null \
    | jq -c '[.[] | select(.type=="page" and (.url|startswith("http")))][0] // empty' 2>/dev/null || true
}

wait_geometry() {
  local geometry width height
  for _ in $(seq 1 "${KIOSK_WAKE_GEOMETRY_TRIES:-30}"); do
    geometry="$(xdotool getdisplaygeometry 2>/dev/null || true)"
    read -r width height <<<"$geometry"
    [[ "${width:-0}" -ge "${KIOSK_MIN_WIDTH:-1024}" && "${height:-0}" -ge "${KIOSK_MIN_HEIGHT:-600}" ]] && return 0
    sleep 0.2
  done
  return 1
}

verify_page() {
  local page url fallback
  page="$(chrome_page_json)"; [[ -n "$page" ]] || return 1
  url="$(jq -r '.url // ""' <<<"$page")"
  fallback="${KIOSK_WEBUI_SCHEME:-http}://127.0.0.1:${KIOSK_WEBUI_PORT:-8080}/offline"
  [[ "$url" == "$KIOSK_URL"* || ( -f "$KIOSK_DIR/fallback_active" && "$url" == "$fallback"* ) ]] || return 1
  "$CHROME_LIFECYCLE" verify >/dev/null
}

verify_screenshot() {
  local shot colors
  shot="$(mktemp --suffix=.png)"
  if command -v import >/dev/null; then
    import -window root "$shot" >/dev/null 2>&1 || { rm -f "$shot"; return 1; }
  elif command -v gnome-screenshot >/dev/null; then
    gnome-screenshot -f "$shot" >/dev/null 2>&1 || { rm -f "$shot"; return 1; }
  else
    rm -f "$shot"
    return 0
  fi
  [[ -s "$shot" ]] || { rm -f "$shot"; return 1; }
  if command -v identify >/dev/null; then
    colors="$(identify -format '%k' "$shot" 2>/dev/null || echo 0)"
    [[ "$colors" =~ ^[0-9]+$ ]] && (( colors > 8 )) || { rm -f "$shot"; return 1; }
  fi
  rm -f "$shot"
}

verify_wake() { wait_geometry && verify_page && verify_screenshot; }

wait_verify_wake() {
  local tries="${KIOSK_WAKE_VERIFY_TRIES:-8}"
  for _ in $(seq 1 "$tries"); do
    verify_wake && return 0
    sleep 1
  done
  return 1
}

recover_staged() {
  local reason="${1:-verification failed}" step
  write_state RECOVERING "$reason"
  for step in resize resume reload restart; do
    case "$step" in
      resize) screen_prepare_on; wait_geometry || true ;;
      resume) "$CHROME_LIFECYCLE" active >/dev/null 2>&1 || true ;;
      reload) "$CHROME_LIFECYCLE" reload >/dev/null 2>&1 || true; sleep 3 ;;
      restart) systemctl --user restart kiosk-chrome.service; sleep 6 ;;
    esac
    if wait_verify_wake; then
      printf '%s %s: %s\n' "$(date -Iseconds)" "$step" "$reason" >>"$KIOSK_DIR/recovery.log"
      return 0
    fi
  done
  return 1
}

wake() {
  local source="${1:-command}"
  write_state WAKING "wake requested by $source"; touch "$WAKE_FILE"
  screen_prepare_on || true
  wait_geometry || true
  "$CHROME_LIFECYCLE" active >/dev/null 2>&1 || true
  if ! wait_verify_wake; then recover_staged "wake verification failed" || { write_state RECOVERING "wake recovery exhausted"; return 1; }; fi
  screen_show
  rm -f "$WAKE_FILE"; printf 'ON\n' >"$SCREEN_FILE"
  write_state ON "wake verified"
}

sleep_screen() {
  write_state SLEEPING "sleep requested"
  "$CHROME_LIFECYCLE" idle >/dev/null 2>&1 || true
  screen_hide
  printf 'OFF\n' >"$SCREEN_FILE"; rm -f "$WAKE_FILE"
  write_state OFF "screen backend confirmed request"
}

status() {
  local display
  display="$(screen_geometry)"
  jq -cn --argjson machine "$(cat "$STATE_FILE" 2>/dev/null || echo '{"state":"UNKNOWN"}')" \
    --argjson display "$display" --arg power "$(screen_power_state)" \
    '$machine + {display:$display,power:$power}'
}

exec 9>"$LOCK_FILE"
flock -w 30 9 || { echo 'State transition already in progress' >&2; exit 75; }
case "${1:-status}" in
  on|wake) wake "${2:-command}" ;;
  off|sleep) sleep_screen ;;
  recover) recover_staged "${2:-manual recovery}" && screen_show && write_state ON "recovery verified" ;;
  verify) verify_wake ;;
  status) status ;;
  *) echo 'Usage: warden-state.sh on|off|recover|verify|status' >&2; exit 2 ;;
esac
