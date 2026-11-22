#!/usr/bin/env bash
# Claude Code CLI on the kiosk as a Home Assistant update entity (update.<kiosk>_claude_code) with an Install button.
# Only when Claude Code's native install is there (~/.local/bin/claude); otherwise the entity is removed again.
#
#   check    JSON: installed and latest version (npm dist-tag of the channel in ~/.claude/settings.json, default latest)
#   publish  MQTT discovery + state (mqtt-stats.sh runs it hourly)
#   install  "claude update" as the kiosk user, with progress; no root needed
#
# Running Claude sessions keep the version they started with until they are started again.
set -uo pipefail

KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
DIST_TAGS_URL="https://registry.npmjs.org/-/package/@anthropic-ai/claude-code/dist-tags"
RUN_DIR="${KIOSK_WARDEN_RUN_DIR:-${XDG_RUNTIME_DIR:-/tmp}/kiosk-warden}"
LOCK="$RUN_DIR/claude-code-update.lock"
LAST_RUN="$KIOSK_DIR/claude-code-update.last"
RELEASE_URL="https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"

installed_version() { "$CLAUDE_BIN" --version 2>/dev/null | awk 'NR == 1 { print $1 }'; }

channel() {
  local ch
  ch="$(jq -r '.autoUpdatesChannel // empty' "$HOME/.claude/settings.json" 2>/dev/null)"
  [[ "$ch" == stable ]] && echo stable || echo latest
}

dist_tags() {
  if [[ -n "${CLAUDE_DIST_TAGS_FILE:-}" ]]; then cat "$CLAUDE_DIST_TAGS_FILE"; return; fi
  curl -fsS --max-time 20 "$DIST_TAGS_URL"
}

check() {
  local inst ch latest
  inst="$(installed_version)"
  ch="$(channel)"
  latest="$(dist_tags 2>/dev/null | jq -r --arg ch "$ch" '.[$ch] // empty' 2>/dev/null)"
  jq -cn --arg inst "$inst" --arg latest "${latest:-$inst}" --arg ch "$ch" --argjson known "$([[ -n "$latest" ]] && echo true || echo false)" \
    --slurpfile last <(cat "$LAST_RUN" 2>/dev/null || echo null) \
    '{installed:$inst, latest:$latest, channel:$ch, latest_known:$known, last_run:($last[0] // null)}'
}

running() { [[ -f "$LOCK" ]] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; }

publish_state() { # state-json
  mqtt_pub "$BASE_TOPIC/claude_code/state" "$1" -r || true
}

publish() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  if [[ ! -x "$CLAUDE_BIN" ]]; then
    mqtt_pub "homeassistant/update/${KIOSK_ID}/claude_code/config" "" -r || true
    return 0
  fi
  local dev payload state text
  dev="$(jq -cn --arg id "$KIOSK_ID" '{identifiers:[$id]}')"
  payload="$(jq -cn --arg uniq "${KIOSK_ID}_claude_code" --arg stat "$BASE_TOPIC/claude_code/state" --arg cmd "$BASE_TOPIC/claude_code/install" \
    --arg av "$BASE_TOPIC/online/status" --argjson dev "$dev" \
    '{name:"Claude Code", unique_id:$uniq, state_topic:$stat, command_topic:$cmd, payload_install:"install",
      availability_topic:$av, payload_available:"online", payload_not_available:"offline", icon:"mdi:console", device:$dev}')"
  mqtt_pub "homeassistant/update/${KIOSK_ID}/claude_code/config" "$payload" -r || true
  if running; then
    publish_state "$(jq -cn --arg v "$(installed_version)" '{installed_version:$v, in_progress:true, title:"Claude Code"}')"
    return 0
  fi
  state="$(check)"
  text="$(jq -r 'if .last_run.state == "failed" then "Sidste opdatering fejlede: " + .last_run.message + ". " else "" end
    + "Kanal: " + .channel + ". Kørende Claude-sessioner beholder deres version, til de startes igen."' <<<"$state")"
  publish_state "$(jq -c --arg text "${text:0:255}" --arg url "$RELEASE_URL" \
    '{installed_version:.installed, latest_version:.latest, title:"Claude Code", release_url:$url, release_summary:$text, in_progress:false}' <<<"$state")"
}

install_update() {
  # shellcheck source=/dev/null
  source "$KIOSK_DIR/mqtt-lib.sh"
  [[ -x "$CLAUDE_BIN" ]] || { echo "Claude Code er ikke installeret ($CLAUDE_BIN)" >&2; return 1; }
  mkdir -p "$RUN_DIR"
  running && return 0
  echo $$ >"$LOCK"
  trap 'rm -f "$LOCK"' EXIT
  publish
  local out rc before after
  before="$(installed_version)"
  out="$(timeout 900 "$CLAUDE_BIN" update 2>&1)"; rc=$?
  after="$(installed_version)"
  if (( rc == 0 )); then
    jq -cn --arg from "$before" --arg to "$after" '{state:"done", from:$from, to:$to, at:(now | floor)}' >"$LAST_RUN"
  else
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
