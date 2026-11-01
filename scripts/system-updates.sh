#!/usr/bin/env bash
# Kiosk Warden: pending operating system updates (apt + snap) for Home Assistant.
#   check    JSON: what apt and snap would update, security updates, whether a restart is needed
#   summary  the short Danish text Home Assistant shows (summarize: the same for check JSON on stdin)
#   publish  the "System Updates" update entity (discovery, state, attributes) and "Reboot Required" to MQTT
#
# Read-only: it runs as the kiosk user and only simulates the upgrade (apt-get -s), so phased and held packages are left
# out exactly as a real upgrade would. The packages lists come from the system's daily apt refresh.
set -uo pipefail
export LC_ALL=C LANGUAGE=C

KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"

apt_plan() { # one JSON object per package: name, from (empty for new packages), to, security
  local sim
  if [[ -n "${APT_SIMULATION_FILE:-}" ]]; then sim="$(cat "$APT_SIMULATION_FILE")"  # tests
  else command -v apt-get >/dev/null 2>&1 || return 0; sim="$(apt-get -s -q upgrade --with-new-pkgs 2>/dev/null)"; fi
  awk <<<"$sim" '
    /^Inst / {
      name = $2; from = ""; to = ""; sec = "false"
      if ($3 ~ /^\[/) { from = $3; gsub(/[\[\]]/, "", from); to = $4 } else { to = $3 }
      gsub(/^\(/, "", to)
      if ($0 ~ /-security/) sec = "true"
      printf "{\"name\":\"%s\",\"from\":\"%s\",\"to\":\"%s\",\"security\":%s}\n", name, from, to, sec
    }'
}

snap_plan() { # one JSON object per snap: name, to
  if [[ -n "${SNAP_LIST_FILE:-}" ]]; then awk 'NR > 1 && NF >= 2 { printf "{\"name\":\"%s\",\"to\":\"%s\"}\n", $1, $2 }' "$SNAP_LIST_FILE"; return 0; fi  # tests
  command -v snap >/dev/null 2>&1 || return 0
  snap refresh --list 2>/dev/null | awk 'NR > 1 && NF >= 2 { printf "{\"name\":\"%s\",\"to\":\"%s\"}\n", $1, $2 }'
}

check() {
  local os kernel reboot=false reboot_pkgs="[]"
  os="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-Linux}")"
  kernel="$(uname -r)"
  if [[ -f /run/reboot-required ]]; then
    reboot=true
    reboot_pkgs="$(sort -u /run/reboot-required.pkgs 2>/dev/null | jq -R . | jq -sc .)"
  fi
  jq -n --arg os "$os" --arg kernel "$kernel" --argjson reboot "$reboot" --argjson reboot_pkgs "$reboot_pkgs" \
    --argjson apt "$(apt_plan | jq -sc .)" --argjson snaps "$(snap_plan | jq -sc .)" --arg checked "$(date -Is)" \
    '{os:$os, kernel:$kernel, apt:$apt, snaps:$snaps,
      count:(($apt | length) + ($snaps | length)), security:([$apt[] | select(.security)] | length),
      new_kernel:any($apt[]; .name | test("^linux-image-[0-9]")),
      reboot_required:$reboot, reboot_packages:$reboot_pkgs, checked:$checked}'
}

# Short Danish summary for Home Assistant (max 255 characters): the packages people know first, then the rest as a count.
summary() {
  jq -r '
    def short(v): v | sub("^[0-9]+:"; "") | sub("-[^-]*$"; "") | sub("\\+ubuntu.*$"; "");
    def known:
      {"google-chrome-stable":"Chrome", "chromium":"Chromium", "chromium-browser":"Chromium", "gnome-shell":"GNOME Shell",
       "xserver-xorg-core":"Xorg", "tailscale":"Tailscale", "nodejs":"Node.js", "snapd":"snapd", "openssh-server":"OpenSSH",
       "firefox":"Firefox", "cloud-init":"cloud-init"};
    . as $c
    | [ $c.apt[] | select(.name | test("^linux-image-[0-9]")) | "kerne " + (.name | sub("^linux-image-"; "")) ] as $kernel
    | [ ($c.apt + $c.snaps)[] | select(known[.name]) | known[.name] + " " + short(.to) ] as $named
    | ($kernel + $named) as $shown
    | ($c.count - ($shown | length)) as $rest
    | if $c.count == 0 then
        (if $c.reboot_required then "Alt er opdateret. Genstart kiosken for at tage de sidste opdateringer i brug." else "Alt er opdateret." end)
      else
        ($shown | join(" · "))
        + (if $rest > 0 then (if ($shown | length) > 0 then " + " else "" end) + "\($rest) " + (if $rest == 1 then "anden" else "andre" end) else "" end)
        + (if $c.security > 0 then ". \($c.security) sikkerhedsopdatering" + (if $c.security == 1 then "" else "er" end) else "" end)
        + (if $c.new_kernel or $c.reboot_required then ". Kræver genstart bagefter." else "." end)
      end
    | .[0:255]'
}

publish() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  local state count installed latest dev attributes payload
  state="$(check)" || return 1
  count="$(jq -r .count <<<"$state")"
  installed="$(jq -r .os <<<"$state")"
  if (( count == 1 )); then latest="1 opdatering"; elif (( count > 1 )); then latest="$count opdateringer"; else latest="$installed"; fi
  dev="$(jq -cn --arg id "$KIOSK_ID" '{identifiers:[$id]}')"

  payload="$(jq -cn --arg uniq "${KIOSK_ID}_system_updates" --arg stat "$BASE_TOPIC/system_updates/state" \
    --arg attr "$BASE_TOPIC/system_updates/attributes" --arg av "$BASE_TOPIC/online/status" --arg title "$installed" --argjson dev "$dev" \
    '{name:"System Updates", unique_id:$uniq, state_topic:$stat, json_attributes_topic:$attr, title:$title,
      availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:package-up", device:$dev}')"
  mqtt_pub "homeassistant/update/${KIOSK_ID}/system_updates/config" "$payload" -r || true
  payload="$(jq -cn --arg uniq "${KIOSK_ID}_reboot_required" --arg stat "$BASE_TOPIC/system_updates/reboot_required" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$dev" \
    '{name:"Reboot Required", unique_id:$uniq, state_topic:$stat, payload_on:"ON", payload_off:"OFF",
      availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:restart-alert",
      entity_category:"diagnostic", device:$dev}')"
  mqtt_pub "homeassistant/binary_sensor/${KIOSK_ID}/reboot_required/config" "$payload" -r || true

  mqtt_pub "$BASE_TOPIC/system_updates/state" "$(jq -c --arg latest "$latest" --arg summary "$(summary <<<"$state")" \
    '{installed_version:.os, latest_version:$latest, title:.os, release_summary:$summary}' <<<"$state")" -r || true
  attributes="$(jq -c '{packages:[.apt[] | .name + " " + (if .from != "" then .from + " → " else "ny: " end) + .to] | .[0:80],
    snaps:[.snaps[] | .name + " → " + .to], security, kernel, new_kernel, reboot_required, reboot_packages, checked}' <<<"$state")"
  mqtt_pub "$BASE_TOPIC/system_updates/attributes" "$attributes" -r || true
  mqtt_pub "$BASE_TOPIC/system_updates/reboot_required" "$(jq -r 'if .reboot_required then "ON" else "OFF" end' <<<"$state")" -r || true
}

case "${1:-check}" in
  check) check ;;
  summary) check | summary ;;
  summarize) summary ;;  # check JSON on stdin
  publish) publish ;;
  *) echo "usage: $0 check|summary|publish" >&2; exit 2 ;;
esac
