#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

source "$HOME/kiosk/kiosk.conf"

exec 9>"$HOME/kiosk/start-kiosk.lock"
flock -n 9 || exit 0

CHROME="$(command -v google-chrome-stable || command -v google-chrome || command -v chromium || command -v chromium-browser)"
PROFILE_DIR="$HOME/.config/chrome-kiosk"
MODE_FILE="$HOME/kiosk/window_mode"
SCREEN_FILE="$HOME/kiosk/screen_state"
WAKE_FILE="$HOME/kiosk/wake_pending"
mkdir -p "$PROFILE_DIR"

mode="$(cat "$MODE_FILE" 2>/dev/null || echo Kiosk)"
case "$mode" in
  Kiosk|kiosk) chrome_mode=(--kiosk --start-fullscreen) ;;
  Fullscreen|fullscreen) chrome_mode=(--start-fullscreen) ;;
  Windowed|windowed) chrome_mode=(--new-window) ;;
  *) chrome_mode=(--kiosk --start-fullscreen); mode="Kiosk" ;;
esac
printf '%s\n' "$mode" > "$MODE_FILE"

# Never expose the desktop while Chrome starts behind an OFF monitor. The
# screen_on path removes WAKE_FILE only after the dashboard page is ready.
screen_state="$(cat "$SCREEN_FILE" 2>/dev/null || echo ON)"
if [[ "$screen_state" != "OFF" ]]; then
  xset s off || true
  xset s noblank || true
  xset -dpms || true
fi
pgrep -x unclutter >/dev/null || unclutter -idle 0.5 -root >/dev/null 2>&1 &

pkill -f "$PROFILE_DIR" >/dev/null 2>&1 || true
sleep 2

if ! pgrep -f "$PROFILE_DIR" >/dev/null 2>&1; then
  rm -f "$PROFILE_DIR"/SingletonLock "$PROFILE_DIR"/SingletonCookie "$PROFILE_DIR"/SingletonSocket
fi

wmctrl -c "Indstillinger" >/dev/null 2>&1 || true
wmctrl -c "Settings" >/dev/null 2>&1 || true

# A Chrome restart must preserve both the physical OFF state and the frozen
# renderer. screen_on starts a fresh renderer behind the powered-off monitor
# before exposing it, so Chromium cannot leave a stale grey surface.
if [[ "$screen_state" == "OFF" && ! -f "$WAKE_FILE" ]]; then
  (
    for _ in $(seq 1 20); do
      sleep 0.5
      if curl -fsS --max-time 1 http://127.0.0.1:9222/json/list >/dev/null 2>&1; then
        # screen_on may have arrived while Chrome was starting. Never let this
        # delayed restore overwrite the newer requested state.
        [[ "$(cat "$HOME/kiosk/screen_state" 2>/dev/null || echo ON)" == "OFF" ]] || break
        "$HOME/kiosk/chrome-lifecycle.py" frozen >/dev/null 2>&1 || continue
        xset +dpms >/dev/null 2>&1 || true
        xset dpms 0 0 1 >/dev/null 2>&1 || true
        xset dpms force off >/dev/null 2>&1 || true
        break
      fi
    done
  ) &
fi

exec "$CHROME" \
  "${chrome_mode[@]}" \
  --no-first-run \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --password-store=basic \
  --use-mock-keychain \
  --disable-save-password-bubble \
  --disable-features=TranslateUI,PasswordManagerOnboarding \
  --autoplay-policy=no-user-gesture-required \
  --ignore-gpu-blocklist \
  --enable-gpu-rasterization \
  --enable-zero-copy \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir="$PROFILE_DIR" \
  "$KIOSK_URL"
