#!/usr/bin/env bash
# Kiosk Warden system updates, root part. helper-version: 1
#
# setup-system-updates.sh installs this file as /usr/local/sbin/kiosk-warden-system-update and lets the kiosk user run
# exactly that, without arguments and without a password (sudoers). It installs the pending apt upgrades (new kernels
# included) and snap refreshes, writes its progress to /var/lib/kiosk-warden/system-update.json (read by
# system-updates.sh) and its output to /var/log/kiosk-warden-system-update.log.
#
# No service is restarted on purpose (NEEDRESTART_SUSPEND): the kiosk keeps running on the old libraries until the next
# restart, and system-updates.sh restarts the browser itself once the screen is off.
set -uo pipefail
export LC_ALL=C LANGUAGE=C DEBIAN_FRONTEND=noninteractive NEEDRESTART_SUSPEND=1
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[[ $# -eq 0 ]] || { echo "usage: $0 (no arguments)" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }

DIR=/var/lib/kiosk-warden
STATUS="$DIR/system-update.json"
LOG=/var/log/kiosk-warden-system-update.log
install -d -m 755 "$DIR"
exec 9>"$DIR/system-update.lock"
flock -n 9 || { echo "already running" >&2; exit 75; }

started="$(date -Is)"
finished=""
step=""
done_n=0
total=0
rc=""

write_status() { # state message
  local reboot=false tmp="$STATUS.tmp"
  [[ -f /run/reboot-required ]] && reboot=true
  jq -n --arg state "$1" --arg message "${2:-}" --arg step "$step" --arg started "$started" --arg finished "$finished" \
    --argjson done "$done_n" --argjson total "$total" --arg rc "$rc" --argjson reboot "$reboot" \
    '{state:$state, step:$step, message:$message, started:$started, done:$done, total:$total, reboot_required:$reboot}
     + (if $finished != "" then {finished:$finished, exit_code:($rc | tonumber? // null)} else {} end)' >"$tmp" \
    && chmod 644 "$tmp" && mv "$tmp" "$STATUS"
}

finish() { # state message
  finished="$(date -Is)"
  step=done
  write_status "$1" "$2"
  echo "=== $(date -Is) $1: $2" >>"$LOG"
}

echo "=== $(date -Is) system update started" >>"$LOG"

step=apt_update
write_status running "Henter pakkelister"
if command -v apt-get >/dev/null 2>&1; then
  # A run that was cut off earlier leaves dpkg half-configured and blocks every later upgrade.
  dpkg --configure -a >>"$LOG" 2>&1 || true
  if ! apt-get -q -o DPkg::Lock::Timeout=600 update >>"$LOG" 2>&1; then
    rc=1; finish failed "apt-get update fejlede – se $LOG"; exit 1
  fi
  # The same plan the check shows: phased and held packages stay out, new kernel packages come along.
  total="$(apt-get -s -q upgrade --with-new-pkgs 2>/dev/null | grep -c '^Inst ' || true)"
  step=apt_upgrade
  write_status running "Installerer $total pakker"
  apt-get -q -y -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
    upgrade --with-new-pkgs 2>&1 | while IFS= read -r line; do
      printf '%s\n' "$line" >>"$LOG"
      if [[ "$line" == "Setting up "* ]]; then
        (( done_n < total )) && done_n=$((done_n + 1))
        write_status running "Installerer $total pakker"
      fi
    done
  rc="${PIPESTATUS[0]}"
  done_n="$total"
  if [[ "$rc" != 0 ]]; then finish failed "apt-get upgrade fejlede (kode $rc) – se $LOG"; exit "$rc"; fi
fi

snap_note=""
if command -v snap >/dev/null 2>&1; then
  step=snap
  write_status running "Opdaterer snaps"
  # A snap whose app is running may be held back by snapd; that is not a failed update.
  snap refresh >>"$LOG" 2>&1 || snap_note=" (en snap blev udskudt – se $LOG)"
fi

rc=0
finish ok "Opdateret$snap_note"
