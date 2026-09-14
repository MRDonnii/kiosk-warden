#!/usr/bin/env bash
set -euo pipefail
REPO_SLUG="${KIOSK_WARDEN_REPO_SLUG:-MRDonnii/kiosk-warden}"
REPO_URL="${KIOSK_WARDEN_REPO:-https://github.com/${REPO_SLUG}.git}"
KIOSK_DIR="$HOME/kiosk"
CHANNEL_FILE="$KIOSK_DIR/update_channel"
BACKUP_DIR="$KIOSK_DIR/backups/releases"
STATUS_FILE="$KIOSK_DIR/update_status.json"
ACTION="${1:-install}"
CHANNEL="${2:-$(cat "$CHANNEL_FILE" 2>/dev/null || echo stable)}"
[[ "$CHANNEL" == beta ]] || CHANNEL=stable
source "$KIOSK_DIR/kiosk.conf" 2>/dev/null || true
source "$KIOSK_DIR/mqtt-lib.sh" 2>/dev/null || true

publish_update_json() {
  [[ -n "${BASE_TOPIC:-}" ]] || return 0
  mqtt_pub "$BASE_TOPIC/update/state" "$(jq -c '{installed_version,latest_version,title,release_url,release_summary,in_progress} | with_entries(select(.value != null))' <<<"$1")" -r 2>/dev/null || true
}

write_status() {
  local stage="$1" percent="$2" message="$3" result="${4:-running}" restart="${5:-false}"
  local tmp="$STATUS_FILE.tmp"
  jq -cn --arg stage "$stage" --argjson percent "$percent" --arg message "$message" \
    --arg result "$result" --argjson restart_required "$restart" --arg updated_at "$(date -Iseconds)" \
    '{stage:$stage,percent:$percent,message:$message,result:$result,restart_required:$restart_required,updated_at:$updated_at}' > "$tmp"
  mv "$tmp" "$STATUS_FILE"
}

reset_progress_on_failure() {
  local code=$?
  trap - EXIT
  if (( code != 0 )) && [[ -n "${UPDATE_FAILURE_STATE:-}" ]]; then
    publish_update_json "$UPDATE_FAILURE_STATE"
    write_status failed 100 "Opdateringen fejlede. Den tidligere version er fortsat aktiv." failed false
  fi
  exit "$code"
}

release_json() {
  local url="https://api.github.com/repos/$REPO_SLUG/releases/latest" feed tag
  if [[ -n "${KIOSK_WARDEN_FORCE_TAG:-}" ]]; then
    tag="$KIOSK_WARDEN_FORCE_TAG"
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'ERROR invalid forced release tag' >&2; return 1; }
    jq -cn --arg tag "$tag" --arg url "https://github.com/$REPO_SLUG/releases/tag/$tag" \
      '{tag_name:$tag,html_url:$url,body:"",prerelease:true}'
    return 0
  fi
  [[ "$CHANNEL" == beta ]] && url="https://api.github.com/repos/$REPO_SLUG/releases?per_page=1"
  local data tag release_url
  if data="$(curl -fsSL --max-time 20 -H 'Accept: application/vnd.github+json' -H 'User-Agent: kiosk-warden' "$url" 2>/dev/null)"; then
    [[ "$CHANNEL" == beta ]] && jq '.[0]' <<<"$data" || printf '%s\n' "$data"
    return 0
  fi

  # The anonymous GitHub API is rate-limited per public IP. GitHub's public
  # Atom feed lists prereleases too and remains available without API quota,
  # so Beta discovery must not stop at 5% merely because the API returns 403.
  if [[ "$CHANNEL" == beta ]]; then
    feed="$(curl -fsSL --max-time 20 -H 'Cache-Control: no-cache' -H 'User-Agent: kiosk-warden' "https://github.com/$REPO_SLUG/releases.atom?warden_check=$(date +%s)" 2>/dev/null)" || return 1
    tag="$(sed -n -E 's@.*href="https://github.com/[^/]+/[^/]+/releases/tag/(v[0-9]+\.[0-9]+\.[0-9]+)".*@\1@p' <<<"$feed" | head -n1)"
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
    jq -cn --arg tag "$tag" --arg url "https://github.com/$REPO_SLUG/releases/tag/$tag" \
      '{tag_name:$tag,html_url:$url,body:"",prerelease:true}'
    return 0
  fi

  # Stable discovery remains available when GitHub's unauthenticated API quota
  # for the public IP is exhausted. The public redirect does not use API quota.
  if [[ "$CHANNEL" == stable ]]; then
    release_url="$(curl -fsSL --max-time 20 -H 'Cache-Control: no-cache' -o /dev/null -w '%{url_effective}' "https://github.com/$REPO_SLUG/releases/latest?warden_check=$(date +%s)")" || return 1
    tag="${release_url##*/}"
    tag="${tag%%\?*}"
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
    release_url="https://github.com/$REPO_SLUG/releases/tag/$tag"
    jq -cn --arg tag "$tag" --arg url "$release_url" '{tag_name:$tag,html_url:$url,body:"",prerelease:false}'
    return 0
  fi
  return 1
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
  owned=(kiosk/version kiosk/.version kiosk/CHANGELOG.md kiosk/icon.svg kiosk/webui)
  for file in "$KIOSK_DIR"/*.sh "$KIOSK_DIR"/*.py; do [[ -f "$file" ]] && owned+=("kiosk/$(basename "$file")"); done
  for file in "$HOME"/.config/systemd/user/kiosk-capabilities.service "$HOME"/.config/systemd/user/kiosk-capabilities.timer \
    "$HOME"/.config/systemd/user/kiosk-input-guardian.service "$HOME"/.config/systemd/user/kiosk-adaptive-brightness.service; do
    [[ -f "$file" ]] && owned+=(".config/systemd/user/$(basename "$file")")
  done
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

ensure_system_dependencies() {
  # self-update only replaces script/webui files, never apt packages, so a
  # kiosk provisioned before python3-websocket was added to install.sh's
  # required_packages (Smartdash auto-detection) would silently keep missing
  # it forever. Best-effort, non-interactive: never blocks or fails the
  # release install if apt/sudo isn't cooperative.
  local -a packages=()
  python3 -c 'import websocket' 2>/dev/null || packages+=(python3-websocket)
  command -v evtest >/dev/null 2>&1 || packages+=(evtest)
  command -v xinput >/dev/null 2>&1 || packages+=(xinput)
  command -v xprintidle >/dev/null 2>&1 || packages+=(xprintidle)
  command -v zip >/dev/null 2>&1 || packages+=(zip)
  (( ${#packages[@]} == 0 )) && return 0
  echo "Valgfrie hardware-afhængigheder mangler - forsøger automatisk installation…"
  sudo -n apt-get install -y "${packages[@]}" >/dev/null 2>&1 || true
  if ! python3 -c 'import websocket' 2>/dev/null; then
    echo "ADVARSEL: python3-websocket kunne ikke installeres automatisk. Kør: sudo apt-get install -y python3-websocket" >&2
  fi
  return 0
}

restart_warden() {
  systemctl --user daemon-reload
  systemctl --user restart kiosk-mqtt-stats.service kiosk-mqtt-control.service kiosk-watchdog.service kiosk-health.service || true
  systemctl --user disable --now kiosk-vnc.service kiosk-novnc.service >/dev/null 2>&1 || true
  systemctl --user enable --now kiosk-capabilities.timer kiosk-input-guardian.service kiosk-adaptive-brightness.service >/dev/null 2>&1 || true
  systemctl --user start kiosk-capabilities.service >/dev/null 2>&1 || true
  systemctl --user restart kiosk-chrome.service || true
  systemd-run --user --collect --on-active=2s \
    --unit="kiosk-webui-restart-$(date +%s)" \
    /usr/bin/systemctl --user restart kiosk-webui.service >/dev/null
}

restore_snapshot() {
  local archive="$1"
  [[ -f "$archive" ]] || return 1
  tar -xzf "$archive" -C "$HOME"
  restart_warden
}

runtime_release_healthy() {
  local expected="$1"
  RUNTIME_FAILURE=""
  [[ "$(cat "$KIOSK_DIR/version" 2>/dev/null)" == "$expected" ]] || { RUNTIME_FAILURE="version"; return 1; }
  systemctl --user is-active --quiet kiosk-webui.service || { RUNTIME_FAILURE="webui"; return 1; }
  [[ -s "$KIOSK_DIR/webui/server.py" ]] || { RUNTIME_FAILURE="webui-file"; return 1; }
  return 0
}

verify_or_rollback() {
  local backup="$1" expected="$2" timeout_seconds="${KIOSK_UPDATE_VERIFY_TIMEOUT:-30}" deadline
  deadline=$((SECONDS + timeout_seconds))
  write_status verifying 95 "Verificerer installeret version og WebUI…"
  while (( SECONDS < deadline )); do
    if runtime_release_healthy "$expected"; then
      return 0
    fi
    sleep 2
  done
  # Hardware, MQTT, Chrome rendering, ports and screen power vary between
  # installations. They belong in diagnostics and must never downgrade an
  # otherwise installed release to an old snapshot. Keep the new files and
  # report the exact failed essential check for remote troubleshooting.
  write_status complete 100 "Kiosk Warden $expected er installeret. Advarsel: efterkontrol fejlede: ${RUNTIME_FAILURE:-unknown}." complete false
  echo "UPDATED_WITH_WARNING $expected check=${RUNTIME_FAILURE:-unknown} backup=$backup" >&2
  return 0
}

install_release() {
  local state tag expected installed workdir repo backup file
  write_status checking 5 "Tjekker GitHub Releases…"
  state="$(check_release)" || return 1
  tag="$(jq -r .tag <<<"$state")"; expected="$(jq -r .latest_version <<<"$state")"; installed="$(jq -r .installed_version <<<"$state")"
  version_newer "$expected" "$installed" || { write_status complete 100 "Kiosk Warden $installed er allerede opdateret." complete false; echo "UPTODATE $installed"; return 0; }
  UPDATE_FAILURE_STATE="$(jq -c '. + {in_progress:false}' <<<"$state")"
  trap reset_progress_on_failure EXIT
  publish_update_json "$(jq -c '. + {in_progress:true}' <<<"$state")"
  write_status downloading 20 "Henter Kiosk Warden $tag…"
  workdir="$(mktemp -d)"; trap 'rm -rf "$workdir"' RETURN
  git clone --depth 1 --branch "$tag" "$REPO_URL" "$workdir/repo" -q || { echo 'ERROR release download failed'; return 1; }
  repo="$workdir/repo"
  write_status validating 40 "Validerer release og versionsmetadata…"
  [[ "$(cat "$repo/VERSION" 2>/dev/null)" == "$expected" ]] || { echo 'ERROR release version validation failed'; return 1; }
  for file in scripts/self-update.sh scripts/mqtt-control.sh scripts/mqtt-stats.sh scripts/chrome-lifecycle.py scripts/capability-probe.py scripts/input-guardian.sh scripts/profile-manager.py webui/server.py; do [[ -f "$repo/$file" ]] || { echo "ERROR release missing $file"; return 1; }; done
  write_status backup 55 "Opretter rollback-snapshot af den nuværende version…"
  backup="$(snapshot_current)" || { echo 'ERROR could not create pre-update backup'; return 1; }
  write_status installing 70 "Installerer validerede releasefiler…"
  for file in "$repo"/scripts/*.sh "$repo"/scripts/*.py; do replace_atomic "$file" "$KIOSK_DIR/$(basename "$file")"; done
  replace_atomic "$repo/VERSION" "$KIOSK_DIR/version" 644; replace_atomic "$repo/icon.svg" "$KIOSK_DIR/icon.svg" 644; replace_atomic "$repo/CHANGELOG.md" "$KIOSK_DIR/CHANGELOG.md" 644
  mkdir -p "$KIOSK_DIR/webui" "$HOME/.config/systemd/user"
  for file in "$repo"/webui/*.py; do replace_atomic "$file" "$KIOSK_DIR/webui/$(basename "$file")"; done
  for file in "$repo"/systemd/*.service "$repo"/systemd/*.timer; do replace_atomic "$file" "$HOME/.config/systemd/user/$(basename "$file")" 644; done
  git -C "$repo" rev-parse HEAD > "$KIOSK_DIR/.version"
  write_status dependencies 80 "Tjekker system-afhængigheder…"
  ensure_system_dependencies
  "$KIOSK_DIR/mqtt-discovery.sh" >/dev/null 2>&1 || true
  write_status services 90 "Genstarter Kiosk Warden-tjenester…"
  publish_update_json "$(jq -cn --arg version "$expected" --arg channel "$CHANNEL" '{installed_version:$version,latest_version:$version,title:"Kiosk Warden",channel:$channel,in_progress:false}')"
  trap - EXIT
  restart_warden
  verify_or_rollback "$backup" "$expected" || return 1
  write_status complete 100 "Kiosk Warden $expected er installeret og genstartet." complete false
  echo "UPDATED $expected backup=$backup"
}

rollback_release() {
  local wanted="${2:-}" archive current_backup
  [[ "$wanted" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'ERROR rollback requires MAJOR.MINOR.PATCH'; return 1; }
  archive="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "${wanted}-*.tar.gz" -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1 {$1=""; sub(/^ /,""); print}')"
  [[ -n "$archive" ]] || { echo "ERROR no backup for $wanted"; return 1; }
  current_backup="$(snapshot_current)" || return 1
  restore_snapshot "$archive"
  echo "ROLLEDBACK $wanted backup=$current_backup"
}

case "$ACTION" in
  check) check_release ;;
  install) install_release ;;
  rollback) rollback_release "$@" ;;
  list) mkdir -p "$BACKUP_DIR"; find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.tar.gz' -printf '%f\n' | sort -Vr ;;
  *) echo 'Usage: self-update.sh check|install|list|rollback VERSION [stable|beta]' >&2; exit 2 ;;
esac
