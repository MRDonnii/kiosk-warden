#!/usr/bin/env bash
# kiosk-warden installer
# Usage (fresh Ubuntu desktop, logged in as the kiosk user):
#   bash <(curl -fsSL https://raw.githubusercontent.com/<you>/kiosk-warden/main/install.sh)
set -euo pipefail

REPO_URL="${KIOSK_WARDEN_REPO:-https://github.com/MRDonnii/kiosk-warden.git}"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run this as the normal desktop user (not root). It will call sudo when needed." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/scripts/start-kiosk.sh" ]]; then
  SRC_DIR="$SCRIPT_DIR"
  CLEANUP_SRC=0
else
  command -v git >/dev/null 2>&1 || { sudo apt-get update -y && sudo apt-get install -y git; }
  WORKDIR="$(mktemp -d)"
  git clone --depth 1 "$REPO_URL" "$WORKDIR/kiosk-warden"
  SRC_DIR="$WORKDIR/kiosk-warden"
  CLEANUP_SRC=1
fi
cleanup() { [[ "$CLEANUP_SRC" -eq 1 ]] && rm -rf "$(dirname "$SRC_DIR")" || true; }
trap cleanup EXIT

ask() {
  local varname="$1" prompt="$2" default="${3:-}" silent="${4:-}"
  if [[ -n "${!varname:-}" ]]; then return 0; fi
  local val=""
  local -a readargs=(-r -p "$prompt${default:+ [$default]}: ")
  [[ "$silent" == "silent" ]] && readargs+=(-s)
  if [[ -t 0 ]]; then
    read "${readargs[@]}" val
  elif [[ -r /dev/tty ]]; then
    read "${readargs[@]}" val </dev/tty
  fi
  [[ "$silent" == "silent" ]] && echo >&2
  printf -v "$varname" '%s' "${val:-$default}"
}

echo "== kiosk-warden install =="

ask KIOSK_NAME "Navn på kiosken (til Home Assistant device)" "Kiosk"
ask KIOSK_ID "Kort id (kun a-z 0-9 _)" "kiosk_$(hostname | tr 'A-Z' 'a-z' | tr -c 'a-z0-9' '_')"
ask KIOSK_URL "URL kiosken skal vise" "http://homeassistant.local:8123"
ask MQTT_HOST "MQTT broker host/IP" "127.0.0.1"
ask MQTT_PORT "MQTT broker port" "1883"
ask MQTT_USER "MQTT brugernavn (blank = ingen auth)" ""
ask MQTT_PASS "MQTT password" "" silent
ask STATS_INTERVAL "Stats-interval i sekunder" "10"
BASE_TOPIC="home/kiosk/${KIOSK_ID}"
CODEX_REMOTE_TOPIC="home/codex/${KIOSK_ID}/remote_control"

echo
echo "== Installerer apt-pakker =="
sudo apt-get update -y
sudo apt-get install -y \
  mosquitto-clients jq bc curl xdotool wmctrl unclutter \
  x11-xserver-utils lm-sensors htop openssh-server dbus-x11 \
  imagemagick gnome-screenshot python3

if ! command -v google-chrome-stable >/dev/null 2>&1; then
  echo "== Installerer Google Chrome =="
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y google-chrome-stable
fi

echo "== Kopierer scripts til ~/kiosk =="
mkdir -p "$HOME/kiosk/backups" "$HOME/kiosk/screenshots"
cp "$SRC_DIR"/scripts/*.sh "$HOME/kiosk/"
chmod +x "$HOME"/kiosk/*.sh

if [[ ! -f "$HOME/kiosk/kiosk.conf" ]]; then
  cat > "$HOME/kiosk/kiosk.conf" <<EOF
KIOSK_NAME="$KIOSK_NAME"
KIOSK_ID="$KIOSK_ID"
KIOSK_URL="$KIOSK_URL"
MQTT_HOST="$MQTT_HOST"
MQTT_PORT=$MQTT_PORT
MQTT_USER="$MQTT_USER"
MQTT_PASS="$MQTT_PASS"
BASE_TOPIC="$BASE_TOPIC"
CODEX_REMOTE_TOPIC="$CODEX_REMOTE_TOPIC"
STATS_INTERVAL=$STATS_INTERVAL
EOF
  chmod 600 "$HOME/kiosk/kiosk.conf"
else
  echo "~/kiosk/kiosk.conf findes allerede — rører den ikke."
fi

echo "== Kopierer web-UI til ~/kiosk/webui =="
mkdir -p "$HOME/kiosk/webui"
cp "$SRC_DIR"/webui/*.py "$HOME/kiosk/webui/"
chmod +x "$HOME/kiosk/webui/server.py"

echo "== Installerer systemd user services =="
mkdir -p "$HOME/.config/systemd/user"
cp "$SRC_DIR"/systemd/*.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable kiosk-chrome.service kiosk-mqtt-stats.service \
  kiosk-mqtt-control.service kiosk-watchdog.service kiosk-health.service kiosk-webui.service
loginctl enable-linger "$USER" || true
systemctl --user start kiosk-mqtt-stats.service kiosk-mqtt-control.service kiosk-webui.service || true
if [[ -n "${DISPLAY:-}" ]]; then
  systemctl --user start kiosk-chrome.service kiosk-watchdog.service kiosk-health.service || true
else
  echo "Ingen grafisk session lige nu — Chrome-relaterede services starter ved næste login/reboot."
fi

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  echo "== Åbner port 8080 i ufw (web-UI) =="
  sudo ufw allow 8080/tcp || true
fi

echo "== Sudoers regel til reboot/shutdown =="
SUDOERS_FILE=/etc/sudoers.d/kiosk-warden
echo "$USER ALL=(root) NOPASSWD: /sbin/reboot, /sbin/poweroff" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 0440 "$SUDOERS_FILE"
sudo visudo -c -f "$SUDOERS_FILE"

echo "== Deaktiverer sleep/suspend/hibernate =="
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

if [[ -f /etc/gdm3/custom.conf ]]; then
  echo "== Sætter GDM autologin + X11 for $USER =="
  sudo cp /etc/gdm3/custom.conf "/etc/gdm3/custom.conf.bak.$(date +%s)"
  sudo python3 - "$USER" <<'PY'
import re, sys
user = sys.argv[1]
path = "/etc/gdm3/custom.conf"
with open(path) as f:
    text = f.read()
if "[daemon]" not in text:
    text += "\n[daemon]\n"
def upsert(text, key, value):
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text)
    return re.sub(r"(\[daemon\]\n)", rf"\1{line}\n", text, count=1)
text = upsert(text, "WaylandEnable", "false")
text = upsert(text, "AutomaticLoginEnable", "true")
text = upsert(text, "AutomaticLogin", user)
with open(path, "w") as f:
    f.write(text)
PY
  echo "GDM ændret. En genstart er nødvendig før autologin virker."
else
  echo "Ingen /etc/gdm3/custom.conf fundet — spring GDM-autologin over (sæt det manuelt hvis du bruger en anden display manager)."
fi

echo "== Desktop-genvej =="
DESKTOP_DIR="$HOME/Desktop"
[[ -d "$HOME/Skrivebord" ]] && DESKTOP_DIR="$HOME/Skrivebord"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/Start Kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Start Kiosk
Comment=Start eller genstart Chrome kiosk
Exec=$HOME/kiosk/restart-kiosk-desktop.sh
Icon=google-chrome
Terminal=false
Categories=Utility;
StartupNotify=true
EOF
chmod +x "$DESKTOP_DIR/Start Kiosk.desktop"

cat > "$DESKTOP_DIR/Kiosk Setup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kiosk Setup
Comment=Åbn kiosk-warden opsætning og kontrolpanel i browseren
Exec=xdg-open http://localhost:8080
Icon=preferences-system
Terminal=false
Categories=Utility;
StartupNotify=true
EOF
chmod +x "$DESKTOP_DIR/Kiosk Setup.desktop"

IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "== Færdig =="
echo "Konfiguration: ~/kiosk/kiosk.conf"
echo "Web-UI (opsætning + kontrolpanel):"
echo "  http://localhost:8080  (på selve maskinen)"
[[ -n "$IP_ADDR" ]] && echo "  http://$IP_ADDR:8080  (fra andre enheder på netværket, fx telefonen)"
echo "Første besøg beder dig sætte et password — gør det med det samme, siden UI'et er tilgængeligt på netværket."
echo "Kør 'bash ~/kiosk/mqtt-discovery.sh' for at (gen)publicere Home Assistant entities."
echo "Genstart maskinen for at få GDM-autologin og kiosk-chrome til at starte ved boot."
