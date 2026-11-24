#!/usr/bin/env bash
# Codex CLI on the kiosk as a Home Assistant update entity (update.<kiosk>_codex_cli) with an Install button.
# Only when Codex is installed (~/.local/bin/codex); otherwise the entity is removed again.
#
#   check    JSON: installed and latest version (npm dist-tag "latest" of @openai/codex)
#   publish  MQTT discovery + state (mqtt-stats.sh runs it hourly)
#   install  "codex update" as the kiosk user, with progress; no root needed
#
# After a good update only the current and the previous standalone release are kept
# (~/.codex/packages/standalone/releases grows by ~300 MB per version otherwise).
# Running Codex sessions keep the version they started with until they are started again.
set -uo pipefail

KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
CODEX_BIN="${CODEX_BIN:-$HOME/.local/bin/codex}"
CODEX_STANDALONE="${CODEX_STANDALONE:-$HOME/.codex/packages/standalone}"
DIST_TAGS_URL="https://registry.npmjs.org/-/package/@openai/codex/dist-tags"
RUN_DIR="${KIOSK_WARDEN_RUN_DIR:-${XDG_RUNTIME_DIR:-/tmp}/kiosk-warden}"
LOCK="$RUN_DIR/codex-update.lock"
LAST_RUN="$KIOSK_DIR/codex-update.last"
RELEASE_URL="https://github.com/openai/codex/releases"

installed_version() { "$CODEX_BIN" --version 2>/dev/null | awk 'NR == 1 { print $NF }'; }

dist_tags() {
  if [[ -n "${CODEX_DIST_TAGS_FILE:-}" ]]; then cat "$CODEX_DIST_TAGS_FILE"; return; fi
  curl -fsS --max-time 20 "$DIST_TAGS_URL"
}

check() {
  local inst latest
  inst="$(installed_version)"
  latest="$(dist_tags 2>/dev/null | jq -r '.latest // empty' 2>/dev/null)"
  jq -cn --arg inst "$inst" --arg latest "${latest:-$inst}" --argjson known "$([[ -n "$latest" ]] && echo true || echo false)" \
    --slurpfile last <(cat "$LAST_RUN" 2>/dev/null || echo null) \
    '{installed:$inst, latest:$latest, latest_known:$known, last_run:($last[0] // null)}'
}

running() { [[ -f "$LOCK" ]] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; }

publish_state() { # state-json
  mqtt_pub "$BASE_TOPIC/codex_cli/state" "$1" -r || true
}

publish() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  if [[ ! -x "$CODEX_BIN" ]]; then
    mqtt_pub "homeassistant/update/${KIOSK_ID}/codex_cli/config" "" -r || true
    return 0
  fi
  local dev payload state text
  dev="$(jq -cn --arg id "$KIOSK_ID" '{identifiers:[$id]}')"
  payload="$(jq -cn --arg uniq "${KIOSK_ID}_codex_cli" --arg stat "$BASE_TOPIC/codex_cli/state" --arg cmd "$BASE_TOPIC/codex_cli/install" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$dev" \
    '{name:"Codex CLI", unique_id:$uniq, state_topic:$stat, command_topic:$cmd, payload_install:"install",
      availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:console-line", device:$dev}')"
  mqtt_pub "homeassistant/update/${KIOSK_ID}/codex_cli/config" "$payload" -r || true
  if running; then
    publish_state "$(jq -cn --arg v "$(installed_version)" '{installed_version:$v, in_progress:true, title:"Codex CLI"}')"
    return 0
  fi
  state="$(check)"
  text="$(jq -r 'if .last_run.state == "failed" then "Sidste opdatering fejlede: " + .last_run.message + ". " else "" end
    + "Kørende Codex-sessioner beholder deres version, til de startes igen."' <<<"$state")"
  publish_state "$(jq -c --arg text "${text:0:255}" --arg url "$RELEASE_URL" \
    '{installed_version:.installed, latest_version:.latest, title:"Codex CLI", release_url:$url, release_summary:$text, in_progress:false}' <<<"$state")"
}

# Keep the release "current" points at plus the newest other one; remove the rest.
prune_releases() {
  local dir="$CODEX_STANDALONE/releases" cur keep_prev rel
  [[ -d "$dir" && -L "$CODEX_STANDALONE/current" ]] || return 0
  cur="$(basename "$(readlink -f "$CODEX_STANDALONE/current")")"
  [[ -n "$cur" && -d "$dir/$cur" ]] || return 0
  keep_prev="$(find "$dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -vxF "$cur" | sort -V | tail -n 1)"
  while IFS= read -r rel; do
    [[ -z "$rel" || "$rel" == "$cur" || "$rel" == "$keep_prev" ]] && continue
    rm -rf -- "${dir:?}/$rel"
  done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
}

install_update() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  [[ -x "$CODEX_BIN" ]] || { echo "Codex er ikke installeret ($CODEX_BIN)" >&2; return 1; }
  mkdir -p "$RUN_DIR"
  running && return 0
  echo $$ >"$LOCK"
  trap 'rm -f "$LOCK"' EXIT
  publish
  local out rc before after
  before="$(installed_version)"
  out="$(timeout 900 "$CODEX_BIN" update </dev/null 2>&1)"; rc=$?
  after="$(installed_version)"
  if (( rc == 0 )) && [[ -n "$after" ]]; then
    prune_releases
    jq -cn --arg from "$before" --arg to "$after" '{state:"done", from:$from, to:$to, at:(now | floor)}' >"$LAST_RUN"
  else
    (( rc == 0 )) && rc=1
    jq -cn --arg msg "$(tail -n 3 <<<"$out" | tr '\n' ' ' | cut -c1-160)" '{state:"failed", message:$msg, at:(now | floor)}' >"$LAST_RUN"
  fi
  rm -f "$LOCK"
  publish
  return "$rc"
}

case "${1:-}" in
  check) check ;;
  publish) publish ;;
  install) install_update ;;
  *) echo "Brug: $0 check|publish|install" >&2; exit 2 ;;
esac
