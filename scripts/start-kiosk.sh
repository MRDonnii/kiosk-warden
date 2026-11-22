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

# On GNOME desktops gsd-power fights kiosk-warden's own xset dpms calls -
# it resets DPMS state back to on/0-0-0 within roughly a minute of a manual
# screen_off(), so the monitor visually blanks (dashboard idle state) but
# never actually powers down, risking burn-in overnight. kiosk-warden owns
# all screen scheduling via MQTT/HA already, so this GNOME daemon is pure
# interference here. No-op (and harmless) on non-GNOME kiosks.
if [[ ":${XDG_CURRENT_DESKTOP:-}:" == *":GNOME:"* ]] && \
   systemctl --user list-unit-files org.gnome.SettingsDaemon.Power.service --no-legend 2>/dev/null | grep -q '^org\.gnome\.SettingsDaemon\.Power\.service'; then
  timeout 3s systemctl --user mask org.gnome.SettingsDaemon.Power.service >/dev/null 2>&1 || true
  timeout 3s systemctl --user kill org.gnome.SettingsDaemon.Power.service >/dev/null 2>&1 || true
fi

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
  xset +dpms || true
  timeout 3s xset dpms force on || true
  xset s off || true
  xset s noblank || true
  xset dpms 0 0 0 || true
fi
pgrep -x unclutter >/dev/null || unclutter -idle 0.5 -root >/dev/null 2>&1 &

"$HOME/kiosk/cleanup-owned-browsers.sh" >/dev/null 2>&1 || true
sleep 2

if ! pgrep -f "$PROFILE_DIR" >/dev/null 2>&1; then
  rm -f "$PROFILE_DIR"/SingletonLock "$PROFILE_DIR"/SingletonCookie "$PROFILE_DIR"/SingletonSocket
fi

wmctrl -c "Indstillinger" >/dev/null 2>&1 || true
wmctrl -c "Settings" >/dev/null 2>&1 || true

# Preserve physical OFF state across a real restart, but never freeze rendering.
if [[ "$screen_state" == "OFF" ]]; then
  (
    for _ in $(seq 1 20); do
      sleep 0.5
      if curl -fsS --max-time 1 http://127.0.0.1:9222/json/list >/dev/null 2>&1; then
        [[ "$(cat "$HOME/kiosk/screen_state" 2>/dev/null || echo ON)" == "OFF" ]] || break
        "$HOME/kiosk/chrome-lifecycle.py" idle >/dev/null 2>&1 || true
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
