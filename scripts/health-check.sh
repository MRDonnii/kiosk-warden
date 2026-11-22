#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
source "$HOME/kiosk/mqtt-lib.sh"
source "$HOME/kiosk/kiosk-event.sh" 2>/dev/null || kiosk_event() { :; }

STATE_FILE="$HOME/kiosk/health_state"
DETAIL_FILE="$HOME/kiosk/health_detail"
ERROR_FILE="$HOME/kiosk/errors"
LAST_RECOVERY_FILE="$HOME/kiosk/last_recovery"
FAIL_COUNT_FILE="$HOME/kiosk/blank_fail_count"
FALLBACK_FILE="$HOME/kiosk/fallback_active"

fallback_url() { printf '%s://127.0.0.1:%s/offline\n' "${KIOSK_WEBUI_SCHEME:-http}" "${KIOSK_WEBUI_PORT:-8080}"; }

activate_fallback() {
  "$HOME/kiosk/chrome-lifecycle.py" navigate "$(fallback_url)" >/dev/null 2>&1 || return 1
  date -Iseconds >"$FALLBACK_FILE"
  return 0
}

primary_available() { curl -fsS -o /dev/null --max-time 5 "$KIOSK_URL"; }

chrome_json() {
  curl -s --max-time 3 http://127.0.0.1:9222/json/list 2>/dev/null || true
}

page_field() {
  local field="$1"
  chrome_json | jq -r --arg field "$field" '[.[] | select(.type=="page")][0][$field] // ""' 2>/dev/null || true
}

publish_health() {
  local status="$1" detail="$2"
  printf '%s\n' "$status" > "$STATE_FILE"
  printf '%s\n' "$detail" > "$DETAIL_FILE"
  mqtt_pub "$BASE_TOPIC/health/status" "$status" -r || true
  mqtt_pub "$BASE_TOPIC/health/detail" "$detail" -r || true
  mqtt_pub "$BASE_TOPIC/diagnostic/errors" "$(cat "$ERROR_FILE" 2>/dev/null || echo 0)" || true
}

chrome_service_starting() {
  local entered now transition
  transition="$(jq -r '.state // ""' "$HOME/kiosk/warden_state.json" 2>/dev/null || true)"
  [[ "$transition" == WAKING || "$transition" == SLEEPING || "$transition" == RECOVERING ]] && return 0
  entered="$(systemctl --user show kiosk-chrome.service -p ActiveEnterTimestampMonotonic --value 2>/dev/null || echo 0)"
  now="$(awk '{printf "%.0f", $1 * 1000000}' /proc/uptime)"
  [[ "$entered" =~ ^[0-9]+$ && "$entered" -gt 0 && $((now - entered)) -lt 45000000 ]]
}

recover() {
  local reason="$1"
  local failures
  failures="$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)"
  failures=$((failures + 1))
  printf '%s\n' "$failures" > "$FAIL_COUNT_FILE"

  # warden-state.sh logs the step that worked (or that every step failed) itself.
  if ! "$HOME/kiosk/warden-state.sh" recover "$reason" >/dev/null 2>&1; then
    if activate_fallback; then
      printf '%s fallback: %s\n' "$(date -Iseconds)" "$reason" >>"$HOME/kiosk/recovery.log"
      kiosk_event recovery fallback "$reason" health-check
    fi
  fi
  (( failures >= 2 )) && printf '0\n' > "$FAIL_COUNT_FILE"

  date -Iseconds > "$LAST_RECOVERY_FILE"
}

# A problem has to be seen on two checks in a row (20 s apart) before it is recovered. A page that is only reloading
# (Home Assistant's standby refresh) is blank or has no page for a moment; recovering it then reloaded or restarted
# Chrome on top of the reload (and, before Kiosk Warden 1.24.0, also woke the dark screen).
SEEN_PROBLEM=""
confirm_recover() {
  local reason="$1" kind="$2"
  if [[ "$SEEN_PROBLEM" == "$kind" ]]; then SEEN_PROBLEM=""; recover "$reason"; else SEEN_PROBLEM="$kind"; fi
}

while true; do
  source "$HOME/kiosk/kiosk.conf"
  title="$(page_field title)"
  url="$(page_field url)"
  chrome_running="off"
  pgrep -f "$HOME/.config/chrome-kiosk" >/dev/null && chrome_running="on"

  if [[ "$chrome_running" != "on" ]]; then
    if chrome_service_starting; then
      SEEN_PROBLEM=""
      publish_health "STARTING" "Chrome is starting"
    else
      # Written by display-guard.sh (watchdog): "missing" = the kiosk session ended and only the login screen shows.
      case "$(cat "$HOME/kiosk/display_session" 2>/dev/null)" in
        missing|recovering) publish_health "OFF" "No graphical session (login screen showing); Kiosk Warden restarts LightDM" ;;
        not-set-up) publish_health "OFF" "No graphical session (login screen showing); run: sudo ~/kiosk/setup-display-recovery.sh" ;;
        rate-limited) publish_health "OFF" "No graphical session (login screen showing); automatic recovery gave up for now (3 restarts per hour)" ;;
        *) publish_health "OFF" "Chrome is not running" ;;
      esac
      confirm_recover "Chrome not running" chrome
    fi
  elif [[ -f "$FALLBACK_FILE" ]]; then
    if primary_available; then
      "$HOME/kiosk/chrome-lifecycle.py" navigate "$KIOSK_URL" >/dev/null 2>&1 || true
      rm -f "$FALLBACK_FILE"; sleep 5
    else
      publish_health "OFF" "Fallback active; primary dashboard unavailable"
    fi
  elif [[ -z "$url" ]]; then
    publish_health "OFF" "Chrome has no debuggable page"
    confirm_recover "No Chrome page" nopage
  elif [[ "$url" == "chrome-error://"* || "$title" == *"Aw, Snap"* || "$title" == *"This site can"* ]]; then
    publish_health "OFF" "Chrome error page: $title $url"
    confirm_recover "Chrome error page: $title $url" error
  elif [[ "$url" != "$KIOSK_URL"* ]]; then
    publish_health "OFF" "Unexpected URL: $url"
    confirm_recover "Unexpected URL: $url" url
  elif [[ -z "$title" || "$title" == "about:blank" || "$title" == "New Tab" ]]; then
    publish_health "OFF" "Blank-looking page: title='$title' url='$url'"
    confirm_recover "Blank-looking page: $title $url" blank
  else
    SEEN_PROBLEM=""
    printf '0\n' > "$FAIL_COUNT_FILE"
    publish_health "ON" "OK: $title"
  fi

  sleep 20
done
