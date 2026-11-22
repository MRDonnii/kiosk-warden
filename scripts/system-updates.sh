#!/usr/bin/env bash
# Kiosk Warden: operating system updates (apt + snap) for Home Assistant.
#   check    JSON: what apt and snap would update, security updates, whether a restart is needed, the last install
#   summary  the short Danish text Home Assistant shows (summarize: the same for check JSON on stdin)
#   publish  the "System Updates" update entity (discovery, state, attributes) and "Reboot Required" to MQTT
#   install  installs everything through the root helper and reports the progress (Home Assistant's Install button)
#
# The check runs as the kiosk user and only simulates the upgrade (apt-get -s), so phased and held packages are left out
# exactly as a real upgrade would. Installing needs the one-time setup: sudo ~/kiosk/setup-system-updates.sh
set -uo pipefail
export LC_ALL=C LANGUAGE=C

KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
HELPER="${KIOSK_WARDEN_HELPER:-/usr/local/sbin/kiosk-warden-system-update}"
RUN_DIR="${KIOSK_WARDEN_RUN_DIR:-/var/lib/kiosk-warden}"
RUN_STATUS="$RUN_DIR/system-update.json"
RUN_LOCK="$RUN_DIR/system-update.lock"
STATE_CACHE="$KIOSK_DIR/system_updates_state.json"
SETUP_HINT="Installation kræver engangsopsætning: sudo ~/kiosk/setup-system-updates.sh"

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

# ok: installing works; outdated: works, but setup-system-updates.sh should be run again; missing: not set up.
helper_status() {
  [[ -x "$HELPER" ]] && sudo -n -l "$HELPER" >/dev/null 2>&1 || { echo missing; return; }
  local want have
  want="$(grep -o 'helper-version: [0-9]*' "$KIOSK_DIR/system-update-root.sh" 2>/dev/null)"
  have="$(grep -o 'helper-version: [0-9]*' "$HELPER" 2>/dev/null)"
  if [[ -z "$want" || "$want" == "$have" ]]; then echo ok; else echo outdated; fi
}

# The root helper holds its lock for the whole run.
install_running() { [[ -e "$RUN_LOCK" ]] && ! flock -n "$RUN_LOCK" true 2>/dev/null; }

check() {
  local os kernel reboot=false reboot_pkgs="[]" last
  os="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-Linux}")"
  kernel="$(uname -r)"
  if [[ -f /run/reboot-required ]]; then
    reboot=true
    reboot_pkgs="$(sort -u /run/reboot-required.pkgs 2>/dev/null | jq -R . | jq -sc .)"
  fi
  last="$(jq -c . "$RUN_STATUS" 2>/dev/null || echo null)"
  jq -n --arg os "$os" --arg kernel "$kernel" --argjson reboot "$reboot" --argjson reboot_pkgs "$reboot_pkgs" \
    --argjson apt "$(apt_plan | jq -sc .)" --argjson snaps "$(snap_plan | jq -sc .)" --arg checked "$(date -Is)" \
    --arg helper "$(helper_status)" --argjson last "$last" \
    '{os:$os, kernel:$kernel, apt:$apt, snaps:$snaps,
      count:(($apt | length) + ($snaps | length)), security:([$apt[] | select(.security)] | length),
      new_kernel:any($apt[]; .name | test("^linux-image-[0-9]")),
      reboot_required:$reboot, reboot_packages:$reboot_pkgs, helper:$helper, last_run:$last, checked:$checked}'
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

publish_discovery() { # helper status
  local dev payload
  dev="$(jq -cn --arg id "$KIOSK_ID" '{identifiers:[$id]}')"
  # The Install button only exists once the root helper is set up.
  payload="$(jq -cn --arg uniq "${KIOSK_ID}_system_updates" --arg stat "$BASE_TOPIC/system_updates/state" \
    --arg attr "$BASE_TOPIC/system_updates/attributes" --arg cmd "$BASE_TOPIC/system_updates/install" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$dev" --argjson install "$([[ "$1" != missing ]] && echo true || echo false)" \
    '{name:"System Updates", unique_id:$uniq, state_topic:$stat, json_attributes_topic:$attr,
      availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:package-up", device:$dev}
     + (if $install then {command_topic:$cmd, payload_install:"install"} else {} end)')"
  mqtt_pub "homeassistant/update/${KIOSK_ID}/system_updates/config" "$payload" -r || true
  payload="$(jq -cn --arg uniq "${KIOSK_ID}_reboot_required" --arg stat "$BASE_TOPIC/system_updates/reboot_required" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$dev" \
    '{name:"Reboot Required", unique_id:$uniq, state_topic:$stat, payload_on:"ON", payload_off:"OFF",
      availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:restart-alert",
      entity_category:"diagnostic", device:$dev}')"
  mqtt_pub "homeassistant/binary_sensor/${KIOSK_ID}/reboot_required/config" "$payload" -r || true
}

# While the helper runs: the last published state with progress from its status file (no apt simulation meanwhile).
publish_progress() {
  local state
  state="$(jq -c --slurpfile run "$RUN_STATUS" '
    ($run[0] // {}) as $r
    | . + {in_progress:true,
           update_percentage:(if $r.step == "apt_upgrade" and ($r.total // 0) > 0 then 5 + (85 * $r.done / $r.total | floor)
                              elif $r.step == "snap" then 92 elif $r.step == "done" then 100 else 2 end)}' \
    "$STATE_CACHE" 2>/dev/null)" || return 0
  mqtt_pub "$BASE_TOPIC/system_updates/state" "$state" -r || true
}

publish() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  if install_running; then publish_progress; return 0; fi
  local state count installed latest text helper failed state_json attributes
  state="$(check)" || return 1
  helper="$(jq -r .helper <<<"$state")"
  publish_discovery "$helper"
  count="$(jq -r .count <<<"$state")"
  installed="$(jq -r .os <<<"$state")"
  if (( count == 1 )); then latest="1 opdatering"; elif (( count > 1 )); then latest="$count opdateringer"; else latest="$installed"; fi
  text="$(summary <<<"$state")"
  failed="$(jq -r 'if .last_run.state == "failed" then .last_run.message else "" end' <<<"$state")"
  if (( count > 0 )) && [[ "$helper" == missing ]]; then text="$SETUP_HINT. $text"
  elif [[ -n "$failed" ]]; then text="Sidste installation fejlede: $failed. $text"; fi
  state_json="$(jq -cn --arg os "$installed" --arg latest "$latest" --arg text "${text:0:255}" \
    '{installed_version:$os, latest_version:$latest, title:$os, release_summary:$text, in_progress:false}')"
  printf '%s\n' "$state_json" >"$STATE_CACHE"
  mqtt_pub "$BASE_TOPIC/system_updates/state" "$state_json" -r || true
  attributes="$(jq -c --arg hint "$SETUP_HINT" '{packages:[.apt[] | .name + " " + (if .from != "" then .from + " → " else "ny: " end) + .to] | .[0:80],
    snaps:[.snaps[] | .name + " → " + .to], security, kernel, new_kernel, reboot_required, reboot_packages,
    install:.helper, last_run, checked} + (if .helper == "ok" then {} else {setup:$hint} end)' <<<"$state")"
  mqtt_pub "$BASE_TOPIC/system_updates/attributes" "$attributes" -r || true
  mqtt_pub "$BASE_TOPIC/system_updates/reboot_required" "$(jq -r 'if .reboot_required then "ON" else "OFF" end' <<<"$state")" -r || true
}

browser_versions() {
  dpkg-query -W -f='${Package} ${Version}\n' google-chrome-stable chromium chromium-browser 2>/dev/null
  snap list chromium 2>/dev/null | awk 'NR > 1 { print $1, $2 }'
}

install_updates() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  if [[ "$(helper_status)" == missing ]]; then publish; echo "$SETUP_HINT" >&2; return 1; fi
  install_running && return 0
  local before after pid rc
  before="$(browser_versions)"
  [[ -f "$STATE_CACHE" ]] || publish
  sudo -n "$HELPER" >/dev/null 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do sleep 3; publish_progress; done
  wait "$pid"; rc=$?
  publish
  after="$(browser_versions)"
  # The running browser keeps its old files until it restarts; do that while nobody looks at the screen.
  if [[ "$before" != "$after" ]] && systemctl --user cat kiosk-chrome.service >/dev/null 2>&1; then
    systemd-run --user --collect --unit="kiosk-browser-restart-after-update" bash -c '
      for _ in $(seq 1 1440); do [[ "$(cat "$HOME/kiosk/screen_state" 2>/dev/null)" == OFF ]] && break; sleep 60; done
      systemctl --user restart kiosk-chrome.service' >/dev/null 2>&1 || true
  fi
  return "$rc"
}

case "${1:-check}" in
  check) check ;;
  summary) check | summary ;;
  summarize) summary ;;  # check JSON on stdin
  publish) publish ;;
  install) install_updates ;;
  *) echo "usage: $0 check|summary|publish|install" >&2; exit 2 ;;
esac
