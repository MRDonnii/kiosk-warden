#!/usr/bin/env bash
set -uo pipefail
source "$HOME/kiosk/mqtt-lib.sh"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

MODE_FILE="$HOME/kiosk/window_mode"
SCREEN_FILE="$HOME/kiosk/screen_state"
THEME_FILE="$HOME/kiosk/theme"
ZOOM_FILE="$HOME/kiosk/page_zoom"
KEYBOARD_FILE="$HOME/kiosk/keyboard_state"
VERSION_FILE="$HOME/kiosk/version"
ERROR_FILE="$HOME/kiosk/errors"

chrome_window() {
  wmctrl -lx | awk 'tolower($0) ~ /google-chrome|chromium/ {print $1; exit}'
}

focus_chrome() {
  local win
  win="$(chrome_window || true)"
  [[ -n "$win" ]] && wmctrl -ia "$win" || true
  sleep 0.2
}

restart_kiosk() {
  systemctl --user restart kiosk-chrome.service || "$HOME/kiosk/start-kiosk.sh" >/dev/null 2>&1 &
}

publish_state() {
  mqtt_pub "$BASE_TOPIC/state/$1" "$2" -r || true
}

set_conf_value() {
  local key="$1" value="$2"
  python3 - "$HOME/kiosk/kiosk.conf" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text().splitlines()
out = []
seen = False
for line in lines:
    if line.startswith(key + "="):
        out.append(f'{key}="{value}"')
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f'{key}="{value}"')
path.write_text("\n".join(out) + "\n")
PY
}

set_kiosk_url() {
  local url="$1"
  case "$url" in
    http://*|https://*) ;;
    *) return 0 ;;
  esac
  set_conf_value KIOSK_URL "$url"
  source "$HOME/kiosk/kiosk.conf"
  publish_state url "$KIOSK_URL"
  restart_kiosk
}

set_window_mode() {
  local mode="$1"
  case "$mode" in
    kiosk|Kiosk|Maximized|maximized) mode="Kiosk" ;;
    fullscreen|Fullscreen) mode="Fullscreen" ;;
    windowed|Windowed) mode="Windowed" ;;
    *) return 0 ;;
  esac
  printf '%s\n' "$mode" > "$MODE_FILE"
  publish_state window_mode "$mode"
  restart_kiosk
}

set_zoom() {
  local zoom="$1"
  zoom="${zoom%%%}"
  if ! [[ "$zoom" =~ ^[0-9]+$ ]]; then return 0; fi
  case "$zoom" in
    50|75|90|100|110|125|150|175|200) ;;
    *) return 0 ;;
  esac
  printf '%s%%\n' "$zoom" > "$ZOOM_FILE"
  publish_state page_zoom "${zoom}%"
  focus_chrome
  xdotool key ctrl+0 || true
  case "$zoom" in
    50) keys=5; key="ctrl+minus" ;;
    75) keys=3; key="ctrl+minus" ;;
    90) keys=1; key="ctrl+minus" ;;
    100) keys=0; key="" ;;
    110) keys=1; key="ctrl+plus" ;;
    125) keys=2; key="ctrl+plus" ;;
    150) keys=4; key="ctrl+plus" ;;
    175) keys=6; key="ctrl+plus" ;;
    200) keys=7; key="ctrl+plus" ;;
  esac
  if (( keys > 0 )); then
    for _ in $(seq 1 "$keys"); do xdotool key "$key" || true; sleep 0.05; done
  fi
}

screen_on() {
  xset dpms force on || true
  xset s off || true
  xset s noblank || true
  xset -dpms || true
  printf 'ON\n' > "$SCREEN_FILE"
  publish_state screen "ON"
}

screen_off() {
  xset +dpms || true
  xset dpms 0 0 1 || true
  xset dpms force off || true
  printf 'OFF\n' > "$SCREEN_FILE"
  publish_state screen "OFF"
}

keyboard_on() {
  if command -v onboard >/dev/null 2>&1; then
    gsettings set org.onboard.window docking-enabled true 2>/dev/null || true
    gsettings set org.onboard.window docking-edge bottom 2>/dev/null || true
    gsettings set org.onboard.auto-show enabled true 2>/dev/null || true
    pgrep -x onboard >/dev/null || onboard >/dev/null 2>&1 &
  elif command -v gnome-extensions >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled true || true
  fi
  printf 'ON\n' > "$KEYBOARD_FILE"
  publish_state keyboard "ON"
}

keyboard_off() {
  pkill -x onboard >/dev/null 2>&1 || true
  gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled false || true
  printf 'OFF\n' > "$KEYBOARD_FILE"
  publish_state keyboard "OFF"
}

set_theme() {
  local theme="$1"
  case "$theme" in
    Dark|dark) theme="Dark"; gsettings set org.gnome.desktop.interface color-scheme prefer-dark || true ;;
    Light|light) theme="Light"; gsettings set org.gnome.desktop.interface color-scheme prefer-light || true ;;
    Auto|auto) theme="Auto"; gsettings reset org.gnome.desktop.interface color-scheme || true ;;
    *) return 0 ;;
  esac
  printf '%s\n' "$theme" > "$THEME_FILE"
  publish_state theme "$theme"
}

set_volume() {
  local volume="$1"
  volume="${volume%%%}"
  if ! [[ "$volume" =~ ^[0-9]+$ ]]; then return 0; fi
  if (( volume > 100 )); then volume=100; fi
  if command -v pactl >/dev/null 2>&1; then
    pactl set-sink-volume @DEFAULT_SINK@ "${volume}%" >/dev/null 2>&1 || true
  fi
  printf '%s\n' "$volume" > "$HOME/kiosk/volume"
  publish_state volume "$volume"
}

take_screenshot() {
  "$HOME/kiosk/take-screenshot.sh" >/dev/null 2>&1 || true
}

backup_kiosk() {
  "$HOME/kiosk/backup-kiosk.sh" >/dev/null 2>&1 || true
}

restart_codex_remote() {
  systemctl --user restart codex-remote-control.service
}

handle_update_install() {
  systemd-run --user --collect --unit="kiosk-self-update-$(date +%s)" \
    "$HOME/kiosk/self-update.sh" >/dev/null 2>&1 || true
}

handle_codex_remote_command() {
  case "$1" in
    restart) restart_codex_remote ;;
  esac
}

handle_command() {
  case "$1" in
    reload|refresh) focus_chrome; xdotool key F5 || true ;;
    hard_reload) focus_chrome; xdotool key ctrl+F5 || true ;;
    restart_chrome|home) restart_kiosk ;;
    screen_off|OFF) screen_off ;;
    screen_on|ON) screen_on ;;
    keyboard_on) keyboard_on ;;
    keyboard_off) keyboard_off ;;
    fullscreen) focus_chrome; xdotool key F11 || true ;;
    Kiosk|Fullscreen|Windowed|Maximized|kiosk|fullscreen|windowed|maximized) set_window_mode "$1" ;;
    Dark|Light|Auto|dark|light|auto) set_theme "$1" ;;
    http://*|https://*) set_kiosk_url "$1" ;;
    screenshot) take_screenshot ;;
    backup) backup_kiosk ;;
    reboot) sudo /sbin/reboot ;;
    shutdown) sudo /sbin/poweroff ;;
  esac
}

listen_topic() {
  local topic="$1" handler="$2"
  while true; do
    mqtt_sub "$topic" | while IFS= read -r payload; do
      "$handler" "$payload"
    done
    sleep 5
  done
}

source "$HOME/kiosk/kiosk.conf"
publish_state url "$KIOSK_URL"
publish_state window_mode "$(cat "$MODE_FILE" 2>/dev/null || echo Kiosk)"
publish_state screen "$(cat "$SCREEN_FILE" 2>/dev/null || echo ON)"
publish_state keyboard "$(cat "$KEYBOARD_FILE" 2>/dev/null || echo OFF)"
publish_state theme "$(cat "$THEME_FILE" 2>/dev/null || echo Dark)"
publish_state page_zoom "$(cat "$ZOOM_FILE" 2>/dev/null || echo 100)"
publish_state version "$(cat "$VERSION_FILE" 2>/dev/null || echo 1.5.0)"

listen_topic "$BASE_TOPIC/set_url" set_kiosk_url &
listen_topic "$BASE_TOPIC/set_zoom" set_zoom &
listen_topic "$BASE_TOPIC/set_theme" set_theme &
listen_topic "$BASE_TOPIC/set_volume" set_volume &
listen_topic "$CODEX_REMOTE_TOPIC/command" handle_codex_remote_command &
listen_topic "$BASE_TOPIC/update/install" handle_update_install &
listen_topic "$BASE_TOPIC/command" handle_command
