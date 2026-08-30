#!/usr/bin/env bash
source "$HOME/kiosk/kiosk.conf"

mqtt_args() {
  local args=(-h "$MQTT_HOST" -p "$MQTT_PORT")
  if [[ -n "${MQTT_USER:-}" ]]; then
    args+=(-u "$MQTT_USER")
  fi
  if [[ -n "${MQTT_PASS:-}" ]]; then
    args+=(-P "$MQTT_PASS")
  fi
  printf '%q ' "${args[@]}"
}

mqtt_pub() {
  local topic="$1"
  local payload="$2"
  shift 2
  local args=(-h "$MQTT_HOST" -p "$MQTT_PORT" -t "$topic" -m "$payload" "$@")
  [[ -n "${MQTT_USER:-}" ]] && args+=(-u "$MQTT_USER")
  [[ -n "${MQTT_PASS:-}" ]] && args+=(-P "$MQTT_PASS")
  mosquitto_pub "${args[@]}"
}

mqtt_sub() {
  local topic="$1"
  local args=(-h "$MQTT_HOST" -p "$MQTT_PORT" -t "$topic")
  [[ -n "${MQTT_USER:-}" ]] && args+=(-u "$MQTT_USER")
  [[ -n "${MQTT_PASS:-}" ]] && args+=(-P "$MQTT_PASS")
  mosquitto_sub "${args[@]}"
}
