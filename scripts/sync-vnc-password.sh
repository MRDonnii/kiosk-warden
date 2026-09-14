#!/usr/bin/env bash
set -euo pipefail

CONF="${KIOSK_CONF:-$HOME/kiosk/kiosk.conf}"
VNC_PASSWD="${VNC_PASSWD_PATH:-$HOME/.vnc/passwd}"

stored="$(sed -n 's/^WEBUI_PASSWORD_HASH="\(.*\)"$/\1/p' "$CONF" | tail -n1)"
[[ -n "$stored" ]] || exit 0
password="${stored#*:}"
password="${password:0:8}"
[[ -n "$password" ]] || exit 0

mkdir -p "$(dirname "$VNC_PASSWD")"
x11vnc -storepasswd "$password" "$VNC_PASSWD" >/dev/null
chmod 600 "$VNC_PASSWD"
