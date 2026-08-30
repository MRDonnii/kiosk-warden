#!/usr/bin/env bash
set -euo pipefail
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
systemctl --user restart kiosk-chrome.service
systemctl --user restart kiosk-watchdog.service kiosk-health.service || true
