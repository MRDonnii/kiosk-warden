#!/usr/bin/env bash
set -euo pipefail
KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
while true; do
  source "$KIOSK_DIR/kiosk.conf"
  if [[ "${KIOSK_AUTO_BRIGHTNESS:-false}" == true ]]; then
    lux="$($KIOSK_DIR/hardware-control.py illuminance-get 2>/dev/null || true)"
    if [[ "$lux" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      target="$(awk -v l="$lux" -v low="${KIOSK_BRIGHTNESS_MIN:-15}" -v high="${KIOSK_BRIGHTNESS_MAX:-100}" 'BEGIN{v=low+(high-low)*(l/(l+150)); printf "%.0f",v}')"
      "$KIOSK_DIR/hardware-control.py" brightness-set "$target" >/dev/null 2>&1 || true
    fi
  fi
  sleep 30
done
