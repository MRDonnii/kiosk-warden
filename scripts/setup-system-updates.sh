#!/usr/bin/env bash
# One-time setup that lets Kiosk Warden install operating system updates (Home Assistant's Install button on
# update.<kiosk>_system_updates). Run it as the kiosk user with sudo:  sudo ~/kiosk/setup-system-updates.sh
#
# It installs system-update-root.sh as /usr/local/sbin/kiosk-warden-system-update (owned by root, so the kiosk user
# cannot change it) and a sudoers rule that lets that user run exactly this file, with no arguments, without a password.
# Run it again after an update that changes the helper (Home Assistant then says so). Undo: --remove.
set -euo pipefail

HELPER=/usr/local/sbin/kiosk-warden-system-update
RULE=/etc/sudoers.d/kiosk-warden-system-update

[[ $EUID -eq 0 ]] || { echo "Kør den med sudo: sudo $0" >&2; exit 1; }
user="${SUDO_USER:-}"
[[ -n "$user" && "$user" != root ]] || { echo "Kør den med sudo fra kiosk-brugeren (ikke som root)." >&2; exit 1; }

if [[ "${1:-}" == "--remove" ]]; then
  rm -f "$RULE" "$HELPER"
  echo "Fjernet: $RULE og $HELPER"
  exit 0
fi

src="$(dirname "$(readlink -f "$0")")/system-update-root.sh"
[[ -f "$src" ]] || { echo "Mangler $src" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "Mangler jq (sudo apt-get install jq)" >&2; exit 1; }

install -o root -g root -m 0755 "$src" "$HELPER"
install -d -o root -g root -m 0755 /var/lib/kiosk-warden

tmp="$(mktemp)"
# The trailing "" allows the command only without arguments.
printf '%s ALL=(root) NOPASSWD: %s ""\n' "$user" "$HELPER" >"$tmp"
if ! visudo -cf "$tmp" >/dev/null; then rm -f "$tmp"; echo "sudoers-reglen blev afvist af visudo" >&2; exit 1; fi
install -o root -g root -m 0440 "$tmp" "$RULE"
rm -f "$tmp"

echo "OK: $user kan nu installere systemopdateringer via Kiosk Warden ($HELPER)."
