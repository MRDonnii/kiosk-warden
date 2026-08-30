#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
source "$HOME/kiosk/mqtt-lib.sh"

MODE_FILE="$HOME/kiosk/window_mode"
SCREEN_FILE="$HOME/kiosk/screen_state"
THEME_FILE="$HOME/kiosk/theme"
ZOOM_FILE="$HOME/kiosk/page_zoom"
KEYBOARD_FILE="$HOME/kiosk/keyboard_state"
VERSION_FILE="$HOME/kiosk/version"
ERROR_FILE="$HOME/kiosk/errors"

read_cpu_total_idle() {
  awk '/^cpu / {idle=$5; total=0; for (i=2;i<=NF;i++) total+=$i; print total, idle}' /proc/stat
}

package_upgrades() {
  apt list --upgradable 2>/dev/null | awk 'NR>1 {count++} END {print count+0}'
}

host_model() {
  cat /sys/devices/virtual/dmi/id/product_name 2>/dev/null || hostnamectl chassis 2>/dev/null || echo "Unknown"
}

serial_number() {
  cat /sys/devices/virtual/dmi/id/product_serial 2>/dev/null | tr -d '\n' || echo "Unknown"
}

memory_size_gib() {
  awk '/^MemTotal:/ {printf "%.2f GiB", $2/1024/1024}' /proc/meminfo
}

UPDATE_CHECK_INTERVAL=1800
UPDATE_REPO_URL="${KIOSK_WARDEN_REPO:-https://github.com/MRDonnii/kiosk-warden.git}"
VERSION_MARKER="$HOME/kiosk/.version"
last_update_check=0

check_for_update() {
  local now latest current
  now="$(date +%s)"
  if (( now - last_update_check < UPDATE_CHECK_INTERVAL )); then
    return 0
  fi
  last_update_check="$now"
  latest="$(git ls-remote "$UPDATE_REPO_URL" HEAD 2>/dev/null | awk '{print $1}')" || true
  if [[ -z "$latest" ]]; then
    return 0
  fi
  current="$(cat "$VERSION_MARKER" 2>/dev/null || echo unknown)"
  mqtt_pub "$BASE_TOPIC/update/state" \
    "$(jq -cn --arg inst "${current:0:7}" --arg lat "${latest:0:7}" '{installed_version:$inst, latest_version:$lat}')" \
    -r || true
}

prev="$(read_cpu_total_idle)"
mqtt_pub "$BASE_TOPIC/online/status" "online" -r || true

while true; do
  sleep "$STATS_INTERVAL"
  curr="$(read_cpu_total_idle)"
  cpu_load="$(awk -v p="$prev" -v c="$curr" 'BEGIN {split(p,pa," "); split(c,ca," "); dt=ca[1]-pa[1]; di=ca[2]-pa[2]; if (dt>0) printf "%.1f", (100*(dt-di)/dt); else print "0"}')"
  prev="$curr"
  ram_used="$(free | awk '/^Mem:/ {printf "%.1f", ($3/$2)*100}')"
  cpu_temp="$(sensors 2>/dev/null | awk '/Package id 0|Tctl|CPU/ {gsub(/[+°C]/,"",$4); print $4; exit}')"
  cpu_temp="${cpu_temp:-0}"
  uptime_text="$(uptime -p | sed 's/^up //')"
  uptime_minutes="$(awk '{print int($1/60)}' /proc/uptime)"
  ip_addr="$(hostname -I | awk '{print $1}')"
  if pgrep -f "$HOME/.config/chrome-kiosk" >/dev/null; then chrome_running="on"; else chrome_running="off"; fi
  keyboard_state="$(cat "$KEYBOARD_FILE" 2>/dev/null || echo OFF)"
  if command -v pactl >/dev/null 2>&1; then
    volume="$(pactl get-sink-volume @DEFAULT_SINK@ 2>/dev/null | awk -F'/' 'NR==1 {gsub(/[% ]/,"",$2); print $2; exit}' || true)"
  else
    volume=""
  fi
  volume="${volume:-$(cat "$HOME/kiosk/volume" 2>/dev/null || echo 100)}"
  heartbeat="$(date -Iseconds)"

  mqtt_pub "$BASE_TOPIC/online/status" "online" -r || true
  mqtt_pub "$BASE_TOPIC/stats/cpu_load" "$cpu_load" || true
  mqtt_pub "$BASE_TOPIC/stats/processor_usage" "$cpu_load" || true
  mqtt_pub "$BASE_TOPIC/stats/ram_used" "$ram_used" || true
  mqtt_pub "$BASE_TOPIC/stats/memory_usage" "$ram_used" || true
  mqtt_pub "$BASE_TOPIC/stats/memory_size" "$(memory_size_gib)" -r || true
  mqtt_pub "$BASE_TOPIC/stats/cpu_temperature" "$cpu_temp" || true
  mqtt_pub "$BASE_TOPIC/stats/processor_temperature" "$cpu_temp" || true
  mqtt_pub "$BASE_TOPIC/stats/uptime" "$uptime_text" || true
  mqtt_pub "$BASE_TOPIC/stats/uptime_minutes" "$uptime_minutes" || true
  mqtt_pub "$BASE_TOPIC/stats/ip_address" "$ip_addr" || true
  mqtt_pub "$BASE_TOPIC/stats/network_address" "$ip_addr" || true
  mqtt_pub "$BASE_TOPIC/stats/host_name" "$(hostname)" -r || true
  mqtt_pub "$BASE_TOPIC/stats/model" "$(host_model)" -r || true
  mqtt_pub "$BASE_TOPIC/stats/serial_number" "$(serial_number)" -r || true
  mqtt_pub "$BASE_TOPIC/stats/package_upgrades" "$(package_upgrades)" || true
  mqtt_pub "$BASE_TOPIC/stats/chrome_running" "$chrome_running" || true
  mqtt_pub "$BASE_TOPIC/state/window_mode" "$(cat "$MODE_FILE" 2>/dev/null || echo Kiosk)" -r || true
  mqtt_pub "$BASE_TOPIC/state/screen" "$(cat "$SCREEN_FILE" 2>/dev/null || echo ON)" -r || true
  mqtt_pub "$BASE_TOPIC/state/url" "$KIOSK_URL" -r || true
  mqtt_pub "$BASE_TOPIC/state/keyboard" "$keyboard_state" -r || true
  mqtt_pub "$BASE_TOPIC/state/theme" "$(cat "$THEME_FILE" 2>/dev/null || echo Dark)" -r || true
  mqtt_pub "$BASE_TOPIC/state/page_zoom" "$(cat "$ZOOM_FILE" 2>/dev/null || echo 100)" -r || true
  mqtt_pub "$BASE_TOPIC/state/volume" "$volume" -r || true
  mqtt_pub "$BASE_TOPIC/diagnostic/errors" "$(cat "$ERROR_FILE" 2>/dev/null || echo 0)" || true
  mqtt_pub "$BASE_TOPIC/diagnostic/heartbeat" "$heartbeat" || true
  mqtt_pub "$BASE_TOPIC/diagnostic/last_active" "$heartbeat" || true
  mqtt_pub "$BASE_TOPIC/diagnostic/version" "$(cat "$VERSION_FILE" 2>/dev/null || echo 1.5.0)" -r || true
  check_for_update
done
