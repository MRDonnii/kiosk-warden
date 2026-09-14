#!/usr/bin/env bash
set -euo pipefail
KIOSK_DIR="${KIOSK_DIR:-$HOME/kiosk}"
out_dir="$KIOSK_DIR/diagnostics"; mkdir -p "$out_dir"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
stamp="$(date +%Y%m%d-%H%M%S)"; bundle="$out_dir/kiosk-warden-diagnostics-$stamp.zip"

capture() { local name="$1"; shift; { "$@" || true; } >"$work/$name" 2>&1; }
capture version.txt sh -c 'printf "version="; cat "$HOME/kiosk/version" 2>/dev/null; printf "commit="; cat "$HOME/kiosk/.version" 2>/dev/null'
capture state.json "$KIOSK_DIR/warden-state.sh" status
capture ports.json "$KIOSK_DIR/port-check.sh"
capture display.txt sh -c 'xrandr --query; xset q'
capture touch.txt sh -c 'xinput list; printf "\nProperties:\n"; for id in $(xinput list --id-only "touch" 2>/dev/null); do xinput list-props "$id"; done'
capture chrome.json curl -fsS --max-time 3 http://127.0.0.1:9222/json/list
capture renderer.json "$KIOSK_DIR/chrome-lifecycle.py" status
capture services.txt systemctl --user --no-pager status kiosk-chrome.service kiosk-mqtt-control.service kiosk-health.service kiosk-watchdog.service kiosk-webui.service kiosk-vnc.service kiosk-novnc.service
capture journal.txt journalctl --user --no-pager -n 300 -u kiosk-chrome.service -u kiosk-mqtt-control.service -u kiosk-health.service -u kiosk-watchdog.service -u kiosk-webui.service
capture input.txt sh -c 'printf "last_input_epoch="; xprintidle 2>/dev/null | awk -v now=$(date +%s) "{print now-int(\$1/1000)}"'
[[ -f "$KIOSK_DIR/self_test.json" ]] && cp "$KIOSK_DIR/self_test.json" "$work/self_test.json"
[[ -f "$KIOSK_DIR/recovery.log" ]] && tail -n 200 "$KIOSK_DIR/recovery.log" >"$work/recovery.log"
# Defense in depth: redact common credential/token forms from every text file.
find "$work" -type f -print0 | xargs -0 sed -i -E \
  -e 's/(MQTT_PASS|HA_TOKEN|WEBUI_PASSWORD_HASH|password|token)([=: ]+)[^ ,\"[:space:]]+/\1\2[REDACTED]/Ig' \
  -e 's/(Authorization: *(Bearer|Basic) +)[A-Za-z0-9._~+\/-]+/\1[REDACTED]/Ig'
(cd "$work" && zip -q -r "$bundle" .)
chmod 600 "$bundle"
printf '%s\n' "$bundle"
