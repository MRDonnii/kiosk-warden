#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/kiosk.conf" 2>/dev/null || true
json='[]'
pid_belongs_to_service() {
  local pid="$1" root="$2" parent
  while [[ "$pid" =~ ^[0-9]+$ ]] && (( pid > 1 )); do
    [[ "$pid" == "$root" ]] && return 0
    parent="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    [[ -n "$parent" && "$parent" != "$pid" ]] || break
    pid="$parent"
  done
  return 1
}
check_port() {
  local name="$1" port="$2" service="$3" listener="" listener_pid="" service_pid="" conflict=false
  listener="$(ss -H -ltnp "sport = :$port" 2>/dev/null | head -n1 || true)"
  listener_pid="$(sed -nE 's/.*pid=([0-9]+).*/\1/p' <<<"$listener")"
  service_pid="$(systemctl --user show "$service" -p MainPID --value 2>/dev/null || echo 0)"
  if [[ -n "$listener" ]] && ! pid_belongs_to_service "$listener_pid" "$service_pid"; then conflict=true; fi
  json="$(jq -c --arg name "$name" --argjson port "$port" --arg service "$service" --arg listener "$listener" --argjson conflict "$conflict" \
    '. + [{name:$name,port:$port,service:$service,listening:($listener!=""),conflict:$conflict,listener:$listener}]' <<<"$json")"
}
check_port webui "${KIOSK_WEBUI_PORT:-8080}" kiosk-webui.service
check_port vnc "${KIOSK_VNC_PORT:-5900}" kiosk-vnc.service
check_port novnc "${KIOSK_NOVNC_PORT:-6080}" kiosk-novnc.service
printf '%s\n' "$json"
