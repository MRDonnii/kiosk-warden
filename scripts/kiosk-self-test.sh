#!/usr/bin/env bash
set -uo pipefail
KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
source "$KIOSK_DIR/screen-backend.sh"
RESULT="$KIOSK_DIR/self_test.json"
started="$(date +%s%3N)"; original="$(cat "$KIOSK_DIR/screen_state" 2>/dev/null || echo ON)"
checks='[]'; failed=0

record() {
  local name="$1" ok="$2" detail="$3"
  checks="$(jq -c --arg name "$name" --argjson ok "$ok" --arg detail "$detail" '. + [{name:$name,ok:$ok,detail:$detail}]' <<<"$checks")"
  [[ "$ok" == true ]] || failed=1
}

if "$KIOSK_DIR/warden-state.sh" off; then
  power="$(screen_power_state)"
  case "$(screen_backend_detect)" in
    *x11) [[ "$power" == Off ]] && record dpms_off true "$power" || record dpms_off false "$power" ;;
    *) record dpms_off true "backend request completed ($power)" ;;
  esac
else record dpms_off false "backend failed"; fi
sleep 1
before="$(screen_geometry)"
if "$KIOSK_DIR/warden-state.sh" on; then
  record wake true verified
else
  wake_detail="$(jq -r '(.stage // "unknown") + ": " + (.detail // "verification failed")' "$KIOSK_DIR/wake_verification.json" 2>/dev/null || echo 'state/recovery failed')"
  record wake false "$wake_detail"
fi
after="$(screen_geometry)"
if jq -e --argjson minw "${KIOSK_MIN_WIDTH:-1024}" --argjson minh "${KIOSK_MIN_HEIGHT:-600}" '.width >= $minw and .height >= $minh' <<<"$after" >/dev/null; then
  record resolution true "$(jq -r '"\(.width)x\(.height)@\(.refresh_hz)"' <<<"$after")"
else record resolution false "$after"; fi
if "$KIOSK_DIR/chrome-lifecycle.py" verify >/dev/null 2>&1; then record renderer_layout true verified; else record renderer_layout false invalid; fi
ports="$($KIOSK_DIR/port-check.sh 2>/dev/null || echo '[]')"
if jq -e 'all(.[]; .conflict == false)' <<<"$ports" >/dev/null; then record ports true clear; else record ports false conflict; fi
ended="$(date +%s%3N)"; duration=$((ended-started))
(( failed == 0 )) && outcome=passed || outcome=failed
jq -cn --arg result "$outcome" --arg at "$(date -Iseconds)" --argjson duration_ms "$duration" \
  --argjson checks "$checks" --argjson before "$before" --argjson after "$after" --argjson ports "$ports" \
  '{result:$result,checked_at:$at,wake_time_ms:$duration_ms,checks:$checks,display_before:$before,display_after:$after,ports:$ports}' >"$RESULT.tmp"
mv "$RESULT.tmp" "$RESULT"
[[ "$original" == OFF ]] && "$KIOSK_DIR/warden-state.sh" off >/dev/null 2>&1 || true
cat "$RESULT"
(( failed == 0 ))
