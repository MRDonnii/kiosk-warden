#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/mqtt-lib.sh"

device_json="$(jq -cn --arg id "$KIOSK_ID" --arg name "$KIOSK_NAME" \
  '{identifiers:[$id], name:$name, manufacturer:"Ubuntu Kiosk", model:"i5-8400T 32GB"}')"

publish_config() {
  mqtt_pub "homeassistant/$1/${KIOSK_ID}/$2/config" "$3" -r
}

sensor() {
  local object="$1" name="$2" topic="$3" unit="${4:-}" icon="${5:-}" device_class="${6:-}" state_class="${7:-}" category="${8:-}"
  local payload
  payload="$(jq -cn --arg name "$name" --arg uniq "${KIOSK_ID}_${object}" --arg stat "$BASE_TOPIC/$topic" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" --arg unit "$unit" --arg icon "$icon" --arg dc "$device_class" --arg sc "$state_class" --arg cat "$category" \
    '{name:$name, unique_id:$uniq, state_topic:$stat, availability_topic:$av, payload_available:"online", payload_not_available:"offline", device:$dev}
     + (if $unit != "" then {unit_of_measurement:$unit} else {} end)
     + (if $icon != "" then {icon:$icon} else {} end)
     + (if $dc != "" then {device_class:$dc} else {} end)
     + (if $sc != "" then {state_class:$sc} else {} end)
     + (if $cat != "" then {entity_category:$cat} else {} end)')"
  publish_config sensor "$object" "$payload"
}

button() {
  local object="$1" name="$2" payload_press="$3" icon="${4:-}" command_topic="${5:-$BASE_TOPIC/command}"
  local payload
  payload="$(jq -cn --arg name "$name" --arg uniq "${KIOSK_ID}_${object}" --arg cmd "$command_topic" --arg payload "$payload_press" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" --arg icon "$icon" \
    '{name:$name, unique_id:$uniq, command_topic:$cmd, payload_press:$payload, availability_topic:$av, payload_available:"online", payload_not_available:"offline", device:$dev}
     + (if $icon != "" then {icon:$icon} else {} end)')"
  publish_config button "$object" "$payload"
}




light_entity() {
  local payload
  payload="$(jq -cn --arg name "Screen" --arg uniq "${KIOSK_ID}_screen_light" --arg cmd "$BASE_TOPIC/command" \
    --arg stat "$BASE_TOPIC/state/screen" --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" \
    '{name:$name, unique_id:$uniq, command_topic:$cmd, state_topic:$stat, payload_on:"ON", payload_off:"OFF", availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:monitor", device:$dev}')"
  publish_config light screen "$payload"
}

image_entity() {
  local payload
  payload="$(jq -cn --arg name "Screenshot" --arg uniq "${KIOSK_ID}_screenshot_image" --arg img "$BASE_TOPIC/image/screenshot" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" \
    '{name:$name, unique_id:$uniq, image_topic:$img, content_type:"image/jpeg", availability_topic:$av, payload_available:"online", payload_not_available:"offline", device:$dev}')"
  publish_config image screenshot_image "$payload"
}

binary_sensor_entity() {
  local payload
  payload="$(jq -cn --arg name "Kiosk Health" --arg uniq "${KIOSK_ID}_health" --arg stat "$BASE_TOPIC/health/status" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" \
    '{name:$name, unique_id:$uniq, state_topic:$stat, payload_on:"ON", payload_off:"OFF", device_class:"connectivity", availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:heart-pulse", device:$dev}')"
  publish_config binary_sensor health "$payload"
}

update_entity() {
  local payload
  payload="$(jq -cn --arg name "Kiosk Warden Update" --arg uniq "${KIOSK_ID}_update" \
    --arg stat "$BASE_TOPIC/update/state" --arg cmd "$BASE_TOPIC/update/install" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" \
    '{name:$name, unique_id:$uniq, state_topic:$stat, command_topic:$cmd, payload_install:"install",
      availability_topic:$av, payload_available:"online", payload_not_available:"offline",
      title:"Kiosk Warden", icon:"mdi:update", device:$dev}')"
  publish_config update update "$payload"
}

switch_entity() {
  local object="$1" name="$2" state_topic="$3" on_payload="$4" off_payload="$5" icon="$6"
  local payload
  payload="$(jq -cn --arg name "$name" --arg uniq "${KIOSK_ID}_${object}" --arg cmd "$BASE_TOPIC/command" \
    --arg stat "$BASE_TOPIC/$state_topic" --arg on "$on_payload" --arg off "$off_payload" --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" --arg icon "$icon" \
    '{name:$name, unique_id:$uniq, command_topic:$cmd, state_topic:$stat, payload_on:$on, payload_off:$off, state_on:"ON", state_off:"OFF", availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:$icon, device:$dev}')"
  publish_config switch "$object" "$payload"
}

select_entity() {
  local object="$1" name="$2" state_topic="$3" command_topic="$4" icon="$5"
  shift 5
  local options_json payload
  options_json="$(printf '%s\n' "$@" | jq -R . | jq -s .)"
  payload="$(jq -cn --arg name "$name" --arg uniq "${KIOSK_ID}_${object}" --arg cmd "$BASE_TOPIC/$command_topic" \
    --arg stat "$BASE_TOPIC/$state_topic" --arg av "$BASE_TOPIC/online/status" --argjson opts "$options_json" --argjson dev "$device_json" --arg icon "$icon" \
    '{name:$name, unique_id:$uniq, command_topic:$cmd, state_topic:$stat, options:$opts, availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:$icon, device:$dev}')"
  publish_config select "$object" "$payload"
}

number_entity() {
  local object="$1" name="$2" state_topic="$3" command_topic="$4" min="$5" max="$6" step="$7" unit="$8" icon="$9"
  local payload
  payload="$(jq -cn --arg name "$name" --arg uniq "${KIOSK_ID}_${object}" --arg cmd "$BASE_TOPIC/$command_topic" \
    --arg stat "$BASE_TOPIC/$state_topic" --argjson min "$min" --argjson max "$max" --argjson step "$step" --arg unit "$unit" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" --arg icon "$icon" \
    '{name:$name, unique_id:$uniq, command_topic:$cmd, state_topic:$stat, min:$min, max:$max, step:$step, mode:"slider", availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:$icon, device:$dev}
     + (if $unit != "" then {unit_of_measurement:$unit} else {} end)')"
  publish_config number "$object" "$payload"
}

text_entity() {
  local payload
  source "$HOME/kiosk/kiosk.conf"
  payload="$(jq -cn --arg name "Page Url" --arg uniq "${KIOSK_ID}_url" --arg cmd "$BASE_TOPIC/set_url" \
    --arg stat "$BASE_TOPIC/state/url" --arg av "$BASE_TOPIC/online/status" --argjson dev "$device_json" \
    '{name:$name, unique_id:$uniq, command_topic:$cmd, state_topic:$stat, mode:"text", min:8, max:255, availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:web", device:$dev}')"
  publish_config text url "$payload"
}

sensor status "Status" "online/status" "" "mdi:lan-connectivity"
sensor host_name "Host Name" "stats/host_name" "" "mdi:monitor"
sensor last_active "Last Active" "diagnostic/last_active" "" "mdi:clock-outline" "" "" "diagnostic"
sensor memory_size "Memory Size" "stats/memory_size" "" "mdi:memory"
sensor memory_usage "Memory Usage" "stats/memory_usage" "%" "mdi:memory" "" "measurement"
sensor model "Model" "stats/model" "" "mdi:chip"
sensor network_address "Network Address" "stats/network_address" "" "mdi:ip-network"
sensor package_upgrades "Package Upgrades" "stats/package_upgrades" "" "mdi:package-up"
sensor processor_temperature "Processor Temperature" "stats/processor_temperature" "°C" "mdi:thermometer" "temperature" "measurement"
sensor processor_usage "Processor Usage" "stats/processor_usage" "%" "mdi:cpu-64-bit" "" "measurement"
sensor serial_number "Serial Number" "stats/serial_number" "" "mdi:identifier"
sensor uptime_minutes "Up Time" "stats/uptime_minutes" "min" "mdi:timer-outline"
sensor chrome_running "Chrome Running" "stats/chrome_running" "" "mdi:google-chrome"
sensor errors "Errors" "diagnostic/errors" "" "mdi:alert-circle" "" "" "diagnostic"
sensor heartbeat "Heartbeat" "diagnostic/heartbeat" "" "mdi:heart-pulse" "" "" "diagnostic"
sensor screenshot "Screenshot" "state/screenshot" "" "mdi:image" "" "" "diagnostic"
sensor version "Version" "diagnostic/version" "" "mdi:tag" "" "" "diagnostic"

sensor health_detail "Health Detail" "health/detail" "" "mdi:clipboard-pulse" "" "" "diagnostic"
sensor last_recovery "Last Recovery" "diagnostic/last_recovery" "" "mdi:restore" "" "" "diagnostic"
sensor screenshot_path "Screenshot Path" "diagnostic/screenshot_path" "" "mdi:file-image" "" "" "diagnostic"
sensor last_backup "Last Backup" "diagnostic/last_backup" "" "mdi:backup-restore" "" "" "diagnostic"
sensor backup_path "Backup Path" "diagnostic/backup_path" "" "mdi:folder-zip" "" "" "diagnostic"

light_entity
image_entity
binary_sensor_entity
update_entity
switch_entity keyboard "Keyboard" "state/keyboard" "keyboard_on" "keyboard_off" "mdi:keyboard"
select_entity window_mode "Kiosk" "state/window_mode" "command" "mdi:window-maximize" "Kiosk" "Fullscreen" "Windowed"
select_entity theme "Theme" "state/theme" "set_theme" "mdi:theme-light-dark" "Dark" "Light" "Auto"
text_entity
select_entity page_zoom "Page Zoom" "state/page_zoom" "set_zoom" "mdi:magnify-plus" "50%" "75%" "90%" "100%" "110%" "125%" "150%" "175%" "200%"
number_entity volume "Volume" "state/volume" "set_volume" 0 100 1 "%" "mdi:volume-high"

button reboot "Reboot" "reboot" "mdi:restart-alert"
button refresh "Refresh" "refresh" "mdi:web-refresh"
button shutdown "Shutdown" "shutdown" "mdi:power"
button restart_chrome "Restart Chrome" "restart_chrome" "mdi:restart"
button restart_codex_remote "Genstart Codex Remote" "restart" "mdi:remote-desktop" "$CODEX_REMOTE_TOPIC/command"
button hard_reload "Hard Reload" "hard_reload" "mdi:reload-alert"
button screenshot_button "Take Screenshot" "screenshot" "mdi:camera"
button backup "Backup" "backup" "mdi:backup-restore"

mqtt_pub "$BASE_TOPIC/online/status" "online" -r
source "$HOME/kiosk/kiosk.conf"
mqtt_pub "$BASE_TOPIC/state/url" "$KIOSK_URL" -r
mqtt_pub "$BASE_TOPIC/state/window_mode" "$(cat "$HOME/kiosk/window_mode" 2>/dev/null || echo Kiosk)" -r
mqtt_pub "$BASE_TOPIC/state/screen" "$(cat "$HOME/kiosk/screen_state" 2>/dev/null || echo ON)" -r
mqtt_pub "$BASE_TOPIC/state/keyboard" "$(cat "$HOME/kiosk/keyboard_state" 2>/dev/null || echo OFF)" -r
mqtt_pub "$BASE_TOPIC/state/theme" "$(cat "$HOME/kiosk/theme" 2>/dev/null || echo Dark)" -r
mqtt_pub "$BASE_TOPIC/state/page_zoom" "$(cat "$HOME/kiosk/page_zoom" 2>/dev/null || echo 100)" -r
mqtt_pub "$BASE_TOPIC/state/volume" "$(cat "$HOME/kiosk/volume" 2>/dev/null || echo 100)" -r
mqtt_pub "$BASE_TOPIC/diagnostic/version" "$(cat "$HOME/kiosk/version" 2>/dev/null || echo 1.5.0)" -r

mqtt_pub "$BASE_TOPIC/health/status" "$(cat "$HOME/kiosk/health_state" 2>/dev/null || echo ON)" -r
mqtt_pub "$BASE_TOPIC/health/detail" "$(cat "$HOME/kiosk/health_detail" 2>/dev/null || echo Pending)" -r

current_version="$(cat "$HOME/kiosk/.version" 2>/dev/null || echo unknown)"
mqtt_pub "$BASE_TOPIC/update/state" "$(jq -cn --arg v "${current_version:0:7}" '{installed_version:$v, latest_version:$v}')" -r
