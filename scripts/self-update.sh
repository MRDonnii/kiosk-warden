#!/usr/bin/env bash
set -euo pipefail
REPO_SLUG="${KIOSK_WARDEN_REPO_SLUG:-MRDonnii/kiosk-warden}"
REPO_URL="${KIOSK_WARDEN_REPO:-https://github.com/${REPO_SLUG}.git}"
KIOSK_DIR="$HOME/kiosk"
CHANNEL_FILE="$KIOSK_DIR/update_channel"
BACKUP_DIR="$KIOSK_DIR/backups/releases"
ACTION="${1:-install}"
CHANNEL="${2:-$(cat "$CHANNEL_FILE" 2>/dev/null || echo stable)}"
[[ "$CHANNEL" == beta ]] || CHANNEL=stable
source "$KIOSK_DIR/kiosk.conf" 2>/dev/null || true
source "$KIOSK_DIR/mqtt-lib.sh" 2>/dev/null || true

publish_update_json() {
  [[ -n "${BASE_TOPIC:-}" ]] || return 0
  mqtt_pub "$BASE_TOPIC/update/state" "$(jq -c '{installed_version,latest_version,title,release_url,release_summary,in_progress} | with_entries(select(.value != null))' <<<"$1")" -r 2>/dev/null || true
}

release_json() {
  local url="https://api.github.com/repos/$REPO_SLUG/releases/latest"
  [[ "$CHANNEL" == beta ]] && url="https://api.github.com/repos/$REPO_SLUG/releases?per_page=1"
  local data
  data="$(curl -fsSL --max-time 20 -H 'Accept: application/vnd.github+json' -H 'User-Agent: kiosk-warden' "$url")"
  [[ "$CHANNEL" == beta ]] && jq '.[0]' <<<"$data" || printf '%s\n' "$data"
}

check_release() {
  local release tag latest installed
  release="$(release_json)" || { echo 'ERROR could not contact GitHub Releases'; return 1; }
  tag="$(jq -r '.tag_name // empty' <<<"$release")"
  [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'ERROR invalid release tag'; return 1; }
  latest="${tag#v}"
  installed="$(cat "$KIOSK_DIR/version" 2>/dev/null || echo unknown)"
  jq -cn --arg installed "$installed" --arg latest "$latest" --arg channel "$CHANNEL" \
    --arg tag "$tag" --arg url "$(jq -r '.html_url // ""' <<<"$release")" \
    --arg summary "$(jq -r '.body // ""' <<<"$release" | head -c 255)" \
    --argjson prerelease "$(jq '.prerelease // false' <<<"$release")" \
    '{installed_version:$installed,latest_version:$latest,title:"Kiosk Warden",release_url:$url,release_summary:$summary,channel:$channel,tag:$tag,prerelease:$prerelease}'
}

snapshot_current() {
  local version stamp archive file
  local -a owned
  version="$(cat "$KIOSK_DIR/version" 2>/dev/null || echo legacy)"
  stamp="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$BACKUP_DIR"
  archive="$BACKUP_DIR/${version}-${stamp}.tar.gz"
  owned=(kiosk/version kiosk/.version kiosk/CHANGELOG.md kiosk/icon.svg kiosk/chrome-lifecycle.py kiosk/webui)
  for file in "$KIOSK_DIR"/*.sh; do [[ -f "$file" ]] && owned+=("kiosk/$(basename "$file")"); done
  tar -czf "$archive" -C "$HOME" --ignore-failed-read "${owned[@]}" \
    .config/systemd/user/kiosk-chrome.service .config/systemd/user/kiosk-mqtt-stats.service \
    .config/systemd/user/kiosk-mqtt-control.service .config/systemd/user/kiosk-watchdog.service \
    .config/systemd/user/kiosk-health.service .config/systemd/user/kiosk-webui.service \
    .config/systemd/user/kiosk-vnc.service .config/systemd/user/kiosk-novnc.service
  printf '%s\n' "$archive"
}

replace_atomic() { local src="$1" dst="$2" mode="${3:-755}"; cp "$src" "$dst.new"; chmod "$mode" "$dst.new"; mv "$dst.new" "$dst"; }

version_newer() {
  [[ "$1" != "$2" && "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1)" == "$1" ]]
}

restart_warden() {
  systemctl --user daemon-reload
  systemctl --user restart kiosk-mqtt-stats.service kiosk-mqtt-control.service kiosk-watchdog.service kiosk-health.service kiosk-vnc.service kiosk-novnc.service || true
  systemctl --user restart kiosk-chrome.service || true
  (sleep 2 && systemctl --user restart kiosk-webui.service) >/dev/null 2>&1 & disown
}

install_release() {
  local state tag expected installed workdir repo backup file
  state="$(check_release)" || return 1
  tag="$(jq -r .tag <<<"$state")"; expected="$(jq -r .latest_version <<<"$state")"; installed="$(jq -r .installed_version <<<"$state")"
  version_newer "$expected" "$installed" || { echo "UPTODATE $installed"; return 0; }
  publish_update_json "$(jq -c '. + {in_progress:true}' <<<"$state")"
  workdir="$(mktemp -d)"; trap 'rm -rf "$workdir"' RETURN
  git clone --depth 1 --branch "$tag" "$REPO_URL" "$workdir/repo" -q || { echo 'ERROR release download failed'; return 1; }
  repo="$workdir/repo"
  [[ "$(cat "$repo/VERSION" 2>/dev/null)" == "$expected" ]] || { echo 'ERROR release version validation failed'; return 1; }
  for file in scripts/self-update.sh scripts/mqtt-control.sh scripts/mqtt-stats.sh scripts/chrome-lifecycle.py webui/server.py; do [[ -f "$repo/$file" ]] || { echo "ERROR release missing $file"; return 1; }; done
  backup="$(snapshot_current)" || { echo 'ERROR could not create pre-update backup'; return 1; }
  for file in "$repo"/scripts/*.sh "$repo"/scripts/*.py; do replace_atomic "$file" "$KIOSK_DIR/$(basename "$file")"; done
  replace_atomic "$repo/VERSION" "$KIOSK_DIR/version" 644; replace_atomic "$repo/icon.svg" "$KIOSK_DIR/icon.svg" 644; replace_atomic "$repo/CHANGELOG.md" "$KIOSK_DIR/CHANGELOG.md" 644
  mkdir -p "$KIOSK_DIR/webui" "$HOME/.config/systemd/user"
  for file in "$repo"/webui/*.py; do replace_atomic "$file" "$KIOSK_DIR/webui/$(basename "$file")"; done
  for file in "$repo"/systemd/*.service; do replace_atomic "$file" "$HOME/.config/systemd/user/$(basename "$file")" 644; done
  git -C "$repo" rev-parse HEAD > "$KIOSK_DIR/.version"
  publish_update_json "$(jq -cn --arg version "$expected" --arg channel "$CHANNEL" '{installed_version:$version,latest_version:$version,title:"Kiosk Warden",channel:$channel,in_progress:false}')"
  restart_warden
  echo "UPDATED $expected backup=$backup"
}

rollback_release() {
  local wanted="${2:-}" archive current_backup
  [[ "$wanted" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'ERROR rollback requires MAJOR.MINOR.PATCH'; return 1; }
  archive="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "${wanted}-*.tar.gz" -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1 {$1=""; sub(/^ /,""); print}')"
  [[ -n "$archive" ]] || { echo "ERROR no backup for $wanted"; return 1; }
  current_backup="$(snapshot_current)" || return 1
  tar -xzf "$archive" -C "$HOME"; restart_warden
  echo "ROLLEDBACK $wanted backup=$current_backup"
}

case "$ACTION" in
  check) check_release ;;
  install) install_release ;;
  rollback) rollback_release "$@" ;;
  list) mkdir -p "$BACKUP_DIR"; find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.tar.gz' -printf '%f\n' | sort -Vr ;;
  *) echo 'Usage: self-update.sh check|install|list|rollback VERSION [stable|beta]' >&2; exit 2 ;;
esac
