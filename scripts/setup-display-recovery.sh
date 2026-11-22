#!/usr/bin/env bash
# One-time setup that lets Kiosk Warden recover the screen by itself when the kiosk session has ended and LightDM is
# showing its login screen. Run it as the kiosk user with sudo:  sudo ~/kiosk/setup-display-recovery.sh
#
# It installs display-recover-root.sh as /usr/local/sbin/kiosk-warden-display-recover (owned by root, so the kiosk user
# cannot change it) and a sudoers rule that lets that user run exactly this file, with no arguments, without a password.
# The watchdog (display-guard.sh) then restarts LightDM when the login screen has been showing for a minute.
# If the login screen is showing right now, it is fixed immediately. Undo: --remove.
set -euo pipefail
HELPER=/usr/local/sbin/kiosk-warden-display-recover
RULE=/etc/sudoers.d/kiosk-warden-display-recover
[[ $EUID -eq 0 ]] || { echo "Run it with sudo: sudo $0" >&2; exit 1; }
user="${SUDO_USER:-}"
[[ -n "$user" && "$user" != root ]] || { echo "Run it with sudo from the kiosk user (not as root)." >&2; exit 1; }
if [[ "${1:-}" == "--remove" ]]; then
  rm -f "$RULE" "$HELPER"
  echo "Removed: $RULE and $HELPER"
  exit 0
fi
src="$(dirname "$(readlink -f "$0")")/display-recover-root.sh"
[[ -f "$src" ]] || { echo "Missing $src" >&2; exit 1; }
for tool in flock loginctl lightdm; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Not installed: $tool (this setup is for LightDM kiosks); nothing changed." >&2; exit 1; }
done
install -o root -g root -m 0755 "$src" "$HELPER"
install -d -o root -g root -m 0755 /var/lib/kiosk-warden
tmp="$(mktemp)"
# The trailing "" allows the command only without arguments.
printf '%s ALL=(root) NOPASSWD: %s ""\n' "$user" "$HELPER" >"$tmp"
if ! visudo -cf "$tmp" >/dev/null; then rm -f "$tmp"; echo "visudo rejected the sudoers rule" >&2; exit 1; fi
install -o root -g root -m 0440 "$tmp" "$RULE"
rm -f "$tmp"
echo "OK: $user can now let Kiosk Warden restart LightDM when the login screen is stuck ($HELPER)."
# Fix a login screen that is showing right now. Exit 10 (session exists) is the normal, healthy answer.
rc=0
SUDO_USER="$user" "$HELPER" || rc=$?
case "$rc" in
  0)  echo "The login screen was showing: LightDM restarted, the kiosk session starts again." ;;
  10) echo "The kiosk session is running; nothing to recover." ;;
  *)  echo "Recovery helper answered $rc (see /var/log or 'journalctl -t kiosk-warden-display-recover')." ;;
esac
exit 0
