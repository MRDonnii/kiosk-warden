#!/usr/bin/env bash
# Kiosk Warden display guard. Sourced by watchdog.sh (display_guard_tick, once per watchdog round); run on its own it
# prints the state:  ~/kiosk/display-guard.sh   ->  ok | missing | not-applicable
#
# Problem: LightDM auto-logs in once per seat. If the kiosk session ends (X or Openbox exits), LightDM shows its login
# screen and never logs in again by itself: no screen, and Chrome crash-loops ("Missing X server") until someone
# restarts LightDM or reboots. Here the "graphical session" is a logind session on seat0 with class "user".
#
# When there has been none for KIOSK_DISPLAY_GUARD_GRACE seconds (default 60; never during the first 3 minutes after
# boot, when the autologin is still running), the guard asks the root helper (setup-display-recovery.sh) to restart
# LightDM, at most once every 5 minutes (the helper has its own limits too). Turn it off with KIOSK_DISPLAY_RECOVERY=false
# in kiosk.conf. Everything is written to ~/kiosk/recovery.log; the current state is in ~/kiosk/display_session.

DISPLAY_GUARD_DIR="${KIOSK_DIR:-$HOME/kiosk}"
DISPLAY_GUARD_CMD_DEFAULT="sudo -n /usr/local/sbin/kiosk-warden-display-recover"

_dg_now() { echo "${KIOSK_DISPLAY_GUARD_NOW:-$(date +%s)}"; }
_dg_uptime() { echo "${KIOSK_DISPLAY_GUARD_UPTIME:-$(cut -d. -f1 /proc/uptime)}"; }
_dg_log() { printf '%s display-recover: %s\n' "$(date -Iseconds)" "$*" >>"$DISPLAY_GUARD_DIR/recovery.log" 2>/dev/null || true; }
_dg_state() { printf '%s\n' "$1" >"$DISPLAY_GUARD_DIR/display_session" 2>/dev/null || true; }

# Does this machine run the LightDM kiosk setup the guard is for?
display_guard_applicable() {
  [[ "${KIOSK_DISPLAY_RECOVERY:-true}" != false ]] || return 1
  command -v loginctl >/dev/null 2>&1 || return 1
  systemctl is-active --quiet lightdm 2>/dev/null
}

# Is there a graphical session on seat0 (the kiosk, or a person logged in)?
display_session_present() {
  loginctl list-sessions --no-legend 2>/dev/null | awk '$4 == "seat0" && $6 == "user" { f = 1 } END { exit !f }'
}

# One round. State lives in DISPLAY_BROKEN_SINCE / DISPLAY_LAST_ATTEMPT / DISPLAY_NOTICE_AT of the calling shell.
display_guard_tick() {
  local now rc cmd
  now="$(_dg_now)"
  if ! display_guard_applicable; then DISPLAY_BROKEN_SINCE=0; _dg_state not-applicable; return 0; fi
  if display_session_present; then
    if [[ "${DISPLAY_BROKEN_SINCE:-0}" -gt 0 ]]; then _dg_log "graphical session is back after $((now - DISPLAY_BROKEN_SINCE))s"; fi
    DISPLAY_BROKEN_SINCE=0; _dg_state ok; return 0
  fi
  # No graphical session. Right after boot the autologin is still on its way: wait.
  if (( $(_dg_uptime) < 180 )); then DISPLAY_BROKEN_SINCE=0; _dg_state starting; return 0; fi
  _dg_state missing
  if [[ "${DISPLAY_BROKEN_SINCE:-0}" -le 0 ]]; then DISPLAY_BROKEN_SINCE="$now"; return 0; fi
  (( now - DISPLAY_BROKEN_SINCE >= ${KIOSK_DISPLAY_GUARD_GRACE:-60} )) || return 0
  (( now - ${DISPLAY_LAST_ATTEMPT:-0} >= 300 )) || return 0
  DISPLAY_LAST_ATTEMPT="$now"
  cmd="${KIOSK_DISPLAY_RECOVER_CMD:-$DISPLAY_GUARD_CMD_DEFAULT}"
  rc=0
  $cmd >/dev/null 2>&1 || rc=$?
  case "$rc" in
    0)  _dg_log "no graphical session for $((now - DISPLAY_BROKEN_SINCE))s (login screen showing); restarted lightdm"; _dg_state recovering ;;
    10) _dg_log "root helper sees a session or a login in progress; waiting" ;;
    11) _dg_log "root helper is rate limited (3 restarts per hour); giving up for now"; _dg_state rate-limited ;;
    12|13) _dg_log "autologin is not set up for this user or lightdm is not the display manager (helper answered $rc)"; _dg_state not-set-up ;;
    *)
      # sudo itself failed (helper missing, or no sudoers rule): say it once an hour.
      _dg_state not-set-up
      if (( now - ${DISPLAY_NOTICE_AT:-0} >= 3600 )); then
        DISPLAY_NOTICE_AT="$now"
        _dg_log "login screen is showing but recovery is not set up (helper answered $rc); run: sudo ~/kiosk/setup-display-recovery.sh"
      fi
      ;;
  esac
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if ! display_guard_applicable; then echo not-applicable
  elif display_session_present; then echo ok
  else echo missing; fi
fi
