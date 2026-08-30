#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/mqtt-lib.sh"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

dir="$HOME/kiosk/screenshots"
mkdir -p "$dir"
stamp="$(date +%Y%m%d-%H%M%S)"
png="$dir/kiosk-$stamp.png"
jpg="$dir/kiosk-$stamp.jpg"
latest_png="$dir/latest.png"
latest_jpg="$dir/latest.jpg"

if command -v gnome-screenshot >/dev/null 2>&1; then
  gnome-screenshot -f "$png"
elif command -v import >/dev/null 2>&1; then
  import -window root "$png"
elif command -v xwd >/dev/null 2>&1 && command -v convert >/dev/null 2>&1; then
  xwd -root -silent | convert xwd:- "$png"
else
  echo "No screenshot tool with PNG output available" >&2
  exit 1
fi

cp "$png" "$latest_png"
if command -v convert >/dev/null 2>&1; then
  convert "$png" -resize '1280x720>' -quality 82 "$jpg"
else
  jpg="$png"
fi
cp "$jpg" "$latest_jpg"

mqtt_pub "$BASE_TOPIC/state/screenshot" "$(date '+%Y-%m-%d %H:%M:%S')" -r || true
mqtt_pub "$BASE_TOPIC/diagnostic/screenshot_path" "$latest_jpg" -r || true

args=(-h "$MQTT_HOST" -p "$MQTT_PORT" -t "$BASE_TOPIC/image/screenshot" -r -f "$latest_jpg")
[[ -n "${MQTT_USER:-}" ]] && args+=(-u "$MQTT_USER")
[[ -n "${MQTT_PASS:-}" ]] && args+=(-P "$MQTT_PASS")
mosquitto_pub "${args[@]}" || true

echo "$latest_jpg"
