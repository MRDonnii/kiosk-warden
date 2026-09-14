#!/usr/bin/env bash
set -euo pipefail
KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"; export DISPLAY="${DISPLAY:-:0}" XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

while true; do
  source "$KIOSK_DIR/kiosk.conf"
  [[ "${KIOSK_TOUCH_WAKE:-true}" == true ]] || { sleep 10; continue; }
  [[ "$(cat "$KIOSK_DIR/screen_state" 2>/dev/null || echo ON)" == OFF ]] || { sleep 1; continue; }
  device="$(jq -r '.touch.device // empty' "$KIOSK_DIR/capabilities.json" 2>/dev/null || true)"
  supported="$(jq -r '.touch.guardian // false' "$KIOSK_DIR/capabilities.json" 2>/dev/null || true)"
  [[ "$supported" == true && -r "$device" ]] || { sleep 10; continue; }
  # Short grabs ensure a presence/MQTT wake cannot leave input captured while
  # the screen is already ON; the maximum release latency is two seconds.
  event="$(timeout 2s evtest --grab "$device" 2>/dev/null | awk '/EV_KEY.*(BTN_TOUCH|BTN_LEFT).*value 1/{print "touch"; fflush(); exit}' || true)"
  [[ "$event" == touch ]] || continue
  printf '%s\n' "$(date -Iseconds)" >"$KIOSK_DIR/last_touch_wake"
  "$KIOSK_DIR/warden-state.sh" on touch >/dev/null 2>&1 || true
  # The triggering gesture was consumed by evtest's exclusive grab. Delay
  # re-entry so its release/tail events cannot activate the freshly shown UI.
  sleep "${KIOSK_TOUCH_RELEASE_DELAY:-1.2}"
done
