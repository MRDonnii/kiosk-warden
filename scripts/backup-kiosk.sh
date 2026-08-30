#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/mqtt-lib.sh"

dir="$HOME/kiosk/backups"
mkdir -p "$dir"
file="$dir/kiosk-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
tar --exclude="$HOME/kiosk/backups" --exclude="$HOME/kiosk/screenshots" -czf "$file" -C "$HOME" kiosk
mqtt_pub "$BASE_TOPIC/diagnostic/last_backup" "$(date '+%Y-%m-%d %H:%M:%S')" -r || true
mqtt_pub "$BASE_TOPIC/diagnostic/backup_path" "$file" -r || true
echo "$file"
