#!/usr/bin/env bash
set -euo pipefail
source "$HOME/kiosk/mqtt-lib.sh"

dir="$HOME/kiosk/backups"
mkdir -p "$dir"
file="$dir/kiosk-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
# Extra patterns kept out of the backup (files with secrets, for instance), from kiosk.conf:
#   KIOSK_BACKUP_EXCLUDE="kiosk/some-secret* kiosk/.other*"
# tar matches member names relative to -C "$HOME": "$HOME/kiosk/backups" never matched, so every backup also held all
# earlier backups (and a part of itself).
# The minute telemetry behind the Status charts (~2 MB) is not worth backing up; events.jsonl is small and kept.
excludes=(--exclude="kiosk/backups" --exclude="kiosk/telemetry" --exclude="kiosk/screenshots" --exclude="kiosk/kontrolrum-sso*" --exclude="kiosk/.kontrolrum-sso*")
read -r -a extra <<<"${KIOSK_BACKUP_EXCLUDE:-}"
for pattern in "${extra[@]}"; do excludes+=(--exclude="$pattern"); done
tar "${excludes[@]}" -czf "$file" -C "$HOME" kiosk
mqtt_pub "$BASE_TOPIC/diagnostic/last_backup" "$(date '+%Y-%m-%d %H:%M:%S')" -r || true
mqtt_pub "$BASE_TOPIC/diagnostic/backup_path" "$file" -r || true
echo "$file"
