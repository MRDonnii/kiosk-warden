#!/usr/bin/env bash
# Kiosk Warden display recovery, root part. helper-version: 1
#
# setup-display-recovery.sh installs this file as /usr/local/sbin/kiosk-warden-display-recover and lets the kiosk user
# run exactly that, without arguments and without a password (sudoers).
#
# Problem it solves: LightDM auto-logs in once per seat. When the kiosk session ends (the X server or Openbox exits,
# a crash, a USB/touch hiccup), LightDM falls back to its login screen and never logs in again by itself, so the screen
# shows a greeter and Chrome crash-loops ("Missing X server") until someone restarts LightDM or reboots the machine.
#
# What it does: restarts lightdm so the autologin runs again, but only when ALL of this holds, so it cannot be used
# for anything else and cannot loop:
#   - it is run through sudo by the kiosk user (SUDO_USER) and lightdm is the enabled display manager
#   - lightdm is configured to auto-login exactly that user (otherwise a restart would only show the greeter again)
#   - nobody has a graphical session on seat0 (a running kiosk or a person logged in is never disturbed)
#   - lightdm has not just been (re)started (a login may be in progress)
#   - at most 3 restarts per hour and 2 minutes apart
#
# Exit codes: 0 lightdm restarted; 2 not run through sudo; 10 nothing to do (session exists / login in progress);
# 11 rate limited; 12 autologin is not set up for this user; 13 lightdm is not the display manager; 14 restart failed.
set -uo pipefail
export LC_ALL=C

STATE_DIR=/var/lib/kiosk-warden
MAX_PER_HOUR=3
MIN_GAP=120
SETTLE=90
if (( EUID != 0 )); then
  # Test mode only: as root the environment is ignored (sudo also resets it).
  [[ "${KIOSK_WARDEN_TEST:-}" == 1 ]] || { echo "Run through sudo: sudo $0" >&2; exit 2; }
  STATE_DIR="${KIOSK_WARDEN_TEST_STATE_DIR:?}"
  NOW="${KIOSK_WARDEN_TEST_NOW:-$(date +%s)}"
  UPTIME_S="${KIOSK_WARDEN_TEST_UPTIME:-$(cut -d. -f1 /proc/uptime)}"
else
  export PATH=/usr/sbin:/usr/bin:/sbin:/bin
  NOW="$(date +%s)"
  UPTIME_S="$(cut -d. -f1 /proc/uptime)"
fi

say() { logger -t kiosk-warden-display-recover "$*" 2>/dev/null || true; echo "$*"; }

user="${SUDO_USER:-}"
[[ -n "$user" && "$user" != root ]] || { echo "Run through sudo from the kiosk user (not as root)." >&2; exit 2; }

# lightdm must be the display manager.
systemctl is-enabled --quiet lightdm 2>/dev/null || { say "lightdm is not the display manager; nothing to do"; exit 13; }

# lightdm must auto-login this very user, otherwise a restart only brings the greeter back.
autologin="$(lightdm --show-config 2>/dev/null | sed -n 's/^[A-Z ]*autologin-user=//p' | tail -n 1)"
[[ "$autologin" == "$user" ]] || { say "autologin is not set up for $user (it is '${autologin:-none}'); not restarting lightdm"; exit 12; }

# A graphical session (the kiosk, or a person) must not be disturbed.
if loginctl list-sessions --no-legend 2>/dev/null | awk '$4 == "seat0" && $6 == "user" { f = 1 } END { exit !f }'; then
  echo "A graphical session exists on seat0; nothing to do"
  exit 10
fi

# A login may be in progress right after lightdm (re)started.
entered="$(systemctl show lightdm -p ActiveEnterTimestampMonotonic --value 2>/dev/null || echo 0)"
if [[ "$entered" =~ ^[0-9]+$ && "$entered" -gt 0 ]] && (( UPTIME_S - entered / 1000000 < SETTLE )); then
  echo "lightdm started less than ${SETTLE}s ago; waiting for the login"
  exit 10
fi

# Rate limit (a lock keeps two callers from both restarting).
mkdir -p "$STATE_DIR" 2>/dev/null
exec 9>"$STATE_DIR/display-recover.lock"
flock -w 10 9 || { say "another recovery is running"; exit 11; }
times="$STATE_DIR/display-recover.times"
recent="$(awk -v now="$NOW" 'now - $1 < 3600 { print $1 }' "$times" 2>/dev/null)"
count="$(printf '%s' "$recent" | grep -c . || true)"
last="$(printf '%s\n' "$recent" | tail -n 1)"
if (( count >= MAX_PER_HOUR )) || { [[ -n "$last" ]] && (( NOW - last < MIN_GAP )); }; then
  say "rate limited ($count restarts in the last hour); not restarting lightdm"
  exit 11
fi
{ [[ -n "$recent" ]] && printf '%s\n' "$recent"; printf '%s\n' "$NOW"; } >"$times"

say "no graphical session on seat0 (login screen showing); restarting lightdm so $user is logged in again"
systemctl restart lightdm || { say "systemctl restart lightdm failed"; exit 14; }
exit 0
