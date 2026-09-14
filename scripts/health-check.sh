#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
source "$HOME/kiosk/mqtt-lib.sh"

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

grey_surface() {
  [[ "$(cat "$HOME/kiosk/screen_state" 2>/dev/null || echo ON)" == "ON" ]] || return 1
  command -v identify >/dev/null 2>&1 || return 1
  local shot colors result=1
  shot="$(mktemp --suffix=.png)"
  if command -v import >/dev/null 2>&1; then
    DISPLAY=:0 XAUTHORITY="$HOME/.Xauthority" import -window root "$shot" >/dev/null 2>&1 || {
      rm -f "$shot"
      return 1
    }
  elif command -v gnome-screenshot >/dev/null 2>&1; then
    DISPLAY=:0 XAUTHORITY="$HOME/.Xauthority" gnome-screenshot -f "$shot" >/dev/null 2>&1 || {
      rm -f "$shot"
      return 1
    }
  else
    rm -f "$shot"
    return 1
  fi
  colors="$(identify -format '%k' "$shot" 2>/dev/null || echo 999)"
  [[ "$colors" =~ ^[0-9]+$ ]] && (( colors <= 8 )) && result=0
  rm -f "$shot"
  return "$result"
}

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

recover() {
  local reason="$1"
  local failures
  failures="$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)"
  failures=$((failures + 1))
  printf '%s\n' "$failures" > "$FAIL_COUNT_FILE"

  if ! "$HOME/kiosk/warden-state.sh" recover "$reason" >/dev/null 2>&1; then
    activate_fallback || true
  fi
  (( failures >= 2 )) && printf '0\n' > "$FAIL_COUNT_FILE"

  date -Iseconds > "$LAST_RECOVERY_FILE"
  echo "$reason" >> "$HOME/kiosk/recovery.log"
}

while true; do
  source "$HOME/kiosk/kiosk.conf"
  title="$(page_field title)"
  url="$(page_field url)"
  chrome_running="off"
  pgrep -f "$HOME/.config/chrome-kiosk" >/dev/null && chrome_running="on"

  if [[ "$chrome_running" != "on" ]]; then
    publish_health "OFF" "Chrome is not running"
    recover "Chrome not running"
  elif [[ -f "$FALLBACK_FILE" ]]; then
    if primary_available; then
      "$HOME/kiosk/chrome-lifecycle.py" navigate "$KIOSK_URL" >/dev/null 2>&1 || true
      rm -f "$FALLBACK_FILE"; sleep 5
    else
      publish_health "OFF" "Fallback active; primary dashboard unavailable"
    fi
  elif [[ -z "$url" ]]; then
    publish_health "OFF" "Chrome has no debuggable page"
    recover "No Chrome page"
  elif [[ "$url" == "chrome-error://"* || "$title" == *"Aw, Snap"* || "$title" == *"This site can"* ]]; then
    publish_health "OFF" "Chrome error page: $title $url"
    recover "Chrome error page: $title $url"
  elif [[ "$url" != "$KIOSK_URL"* ]]; then
    publish_health "OFF" "Unexpected URL: $url"
    recover "Unexpected URL: $url"
  elif [[ -z "$title" || "$title" == "about:blank" || "$title" == "New Tab" ]]; then
    publish_health "OFF" "Blank-looking page: title='$title' url='$url'"
    recover "Blank-looking page: $title $url"
  elif grey_surface; then
    publish_health "OFF" "Chrome surface is blank or solid grey"
    recover "Blank or solid-grey Chrome surface"
  else
    printf '0\n' > "$FAIL_COUNT_FILE"
    publish_health "ON" "OK: $title"
  fi

  sleep 20
done
