#!/usr/bin/env bash
# Kiosk Warden event log helper. Source it and call:
#   kiosk_event recovery STEP "REASON" SOURCE     (STEP: resize|resume|reload|restart|chrome-restart|fallback|lightdm|failed)
# One JSON line per event goes to ~/kiosk/events.jsonl (the timeline on the Status page). The WebUI writes the state
# changes (health, Chrome, screen) to the same file and trims it to 8 days; both take the same flock. URL queries,
# credentials in URLs and token=/password= values are removed from the reason, so no secret ends up in the log.
# Never fails the caller: without jq or a writable kiosk dir the event is simply not logged.

kiosk_event() {
  local kind="${1:-}" step="${2:-}" reason="${3:-}" source="${4:-}" dir="${KIOSK_DIR:-$HOME/kiosk}" line
  [[ "$kind" == recovery ]] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  line="$(jq -cn --arg kind "$kind" --arg step "$step" --arg reason "$reason" --arg src "$source" --argjson t "$(date +%s)" '
    def clean: gsub("[\\x00-\\x1f\\x7f]+"; " ")
      | gsub("(?<s>[A-Za-z][A-Za-z0-9+.-]*://)[^/\\s@]*@"; "\(.s)")
      | gsub("(?<u>[A-Za-z][A-Za-z0-9+.-]*://[^\\s?#]*)[?#]\\S*"; "\(.u)")
      | gsub("(?<k>\\b(token|password|passwd|secret|api[_-]?key|auth))=\\S+"; "\(.k)=…"; "i")
      | if length > 200 then .[:199] + "…" else . end;
    {t: $t, kind: $kind, step: ($step | clean | .[:60]), reason: ($reason | clean), src: ($src | .[:60])}
    | with_entries(select(.value != ""))' 2>/dev/null)" || return 0
  [[ -n "$line" ]] || return 0
  {
    if command -v flock >/dev/null 2>&1; then flock -w 2 9 || true; fi
    # Start on a fresh line if a write was cut off halfway (power cut), so only that line is lost.
    if [[ -s "$dir/events.jsonl" && "$(tail -c 1 "$dir/events.jsonl" | od -An -c | tr -d ' ')" != '\n' ]]; then
      printf '\n' >>"$dir/events.jsonl"
    fi
    printf '%s\n' "$line" >>"$dir/events.jsonl"
  } 9>>"$dir/events.jsonl.lock" 2>/dev/null || true
  return 0
}
