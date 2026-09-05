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

echo "== Registrerer OS og display manager =="
OS_ID="$(. /etc/os-release 2>/dev/null; echo "${ID:-unknown}")"
OS_NAME="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"

DISPLAY_MANAGER="unknown"
if [[ -f /etc/X11/default-display-manager ]]; then
  case "$(cat /etc/X11/default-display-manager)" in
    */gdm3|*/gdm) DISPLAY_MANAGER="gdm3" ;;
    */lightdm) DISPLAY_MANAGER="lightdm" ;;
  esac
fi
if [[ "$DISPLAY_MANAGER" == "unknown" ]]; then
  [[ -f /etc/gdm3/custom.conf ]] && DISPLAY_MANAGER="gdm3"
  [[ -d /etc/lightdm ]] && DISPLAY_MANAGER="lightdm"
fi
echo "OS: $OS_NAME ($OS_ID) — display manager: $DISPLAY_MANAGER — desktop: ${XDG_CURRENT_DESKTOP:-ukendt}"

echo "== kiosk-warden install =="
echo
echo "Du kan udfylde kiosk-navn/URL/MQTT her i terminalen nu,"
echo "eller installere med standardværdier og gøre det bagefter via web-UI'et (Indstillinger)."

CONFIGURE_NOW="${CONFIGURE_NOW:-}"
if [[ -z "$CONFIGURE_NOW" ]]; then
  ans=""
  if [[ -t 0 ]]; then
    read -rp "Konfigurer nu i terminalen? [J/n]: " ans
  elif [[ -r /dev/tty ]]; then
    read -rp "Konfigurer nu i terminalen? [J/n]: " ans </dev/tty
  fi
  if [[ "$ans" =~ ^[Nn] ]]; then
    CONFIGURE_NOW="no"
  else
    CONFIGURE_NOW="yes"
  fi
fi

if [[ "$CONFIGURE_NOW" == "yes" ]]; then
  ask KIOSK_NAME "Navn på kiosken (til Home Assistant device)" "Kiosk"
  ask KIOSK_ID "Kort id (kun a-z 0-9 _)" "kiosk_$(hostname | tr 'A-Z' 'a-z' | tr -c 'a-z0-9' '_')"
  ask KIOSK_URL "URL kiosken skal vise" "http://homeassistant.local:8123"
  ask MQTT_HOST "MQTT broker host/IP" "127.0.0.1"
  ask MQTT_PORT "MQTT broker port" "1883"
  ask MQTT_USER "MQTT brugernavn (blank = ingen auth)" ""
  ask MQTT_PASS "MQTT password" "" silent
  ask STATS_INTERVAL "Stats-interval i sekunder" "10"
  ask VNC_PASSWORD "VNC password til fjernstyring (blankt = generér tilfældigt)" "" silent
else
  echo "Springer terminal-opsætning over — brug web-UI'et (Indstillinger) efter installationen."
  KIOSK_NAME="${KIOSK_NAME:-Kiosk}"
  KIOSK_ID="${KIOSK_ID:-kiosk_$(hostname | tr 'A-Z' 'a-z' | tr -c 'a-z0-9' '_')}"
  KIOSK_URL="${KIOSK_URL:-http://homeassistant.local:8123}"
  MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
  MQTT_PORT="${MQTT_PORT:-1883}"
  MQTT_USER="${MQTT_USER:-}"
  MQTT_PASS="${MQTT_PASS:-}"
  STATS_INTERVAL="${STATS_INTERVAL:-10}"
  VNC_PASSWORD="${VNC_PASSWORD:-}"
fi
BASE_TOPIC="home/kiosk/${KIOSK_ID}"
CODEX_REMOTE_TOPIC="home/codex/${KIOSK_ID}/remote_control"

echo
echo "== Installerer apt-pakker =="
sudo apt-get update -y
sudo apt-get install -y \
  git mosquitto-clients jq bc curl xdotool wmctrl unclutter \
  x11-xserver-utils lm-sensors htop openssh-server dbus-x11 \
  imagemagick gnome-screenshot python3 x11vnc novnc websockify onboard

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
cp "$SRC_DIR/icon.svg" "$HOME/kiosk/icon.svg"
cp "$SRC_DIR/CHANGELOG.md" "$HOME/kiosk/CHANGELOG.md" 2>/dev/null || true
if command -v git >/dev/null 2>&1; then
  git -C "$SRC_DIR" rev-parse HEAD > "$HOME/kiosk/.version" 2>/dev/null || echo unknown > "$HOME/kiosk/.version"
else
  echo unknown > "$HOME/kiosk/.version"
fi

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

echo "== VNC password =="
if [[ ! -f "$HOME/.vnc/passwd" ]]; then
  mkdir -p "$HOME/.vnc"
  if [[ -z "${VNC_PASSWORD:-}" ]]; then
    VNC_PASSWORD="$(head -c9 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c12)"
    echo "Genereret VNC password: $VNC_PASSWORD (skriv det ned — det kan skiftes senere i web-UI'et under Indstillinger)"
  fi
  x11vnc -storepasswd "$VNC_PASSWORD" "$HOME/.vnc/passwd" >/dev/null
  chmod 600 "$HOME/.vnc/passwd"
else
  echo "~/.vnc/passwd findes allerede — rører den ikke."
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
  kiosk-mqtt-control.service kiosk-watchdog.service kiosk-health.service kiosk-webui.service \
  kiosk-vnc.service kiosk-novnc.service
loginctl enable-linger "$USER" || true
systemctl --user start kiosk-mqtt-stats.service kiosk-mqtt-control.service kiosk-webui.service || true
if [[ -n "${DISPLAY:-}" ]]; then
  systemctl --user start kiosk-chrome.service kiosk-watchdog.service kiosk-health.service \
    kiosk-vnc.service kiosk-novnc.service || true
else
  echo "Ingen grafisk session lige nu — Chrome/VNC-relaterede services starter ved næste login/reboot."
fi

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  echo "== Åbner porte i ufw (web-UI, VNC) =="
  sudo ufw allow 8080/tcp || true
  sudo ufw allow 6080/tcp || true
  sudo ufw allow 5900/tcp || true
fi

echo "== Sudoers regel til reboot/shutdown =="
SUDOERS_FILE=/etc/sudoers.d/kiosk-warden
echo "$USER ALL=(root) NOPASSWD: /sbin/reboot, /sbin/poweroff" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 0440 "$SUDOERS_FILE"
sudo visudo -c -f "$SUDOERS_FILE"

echo "== Deaktiverer sleep/suspend/hibernate =="
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

echo "== Aktiverer skærmtastatur =="
if [[ -n "${DISPLAY:-}" ]]; then
  if command -v onboard >/dev/null 2>&1; then
    pgrep -x onboard >/dev/null || onboard >/dev/null 2>&1 &
    disown 2>/dev/null || true
    echo "Bruger onboard (virker uanset desktop-miljø: GNOME, Cinnamon, MATE, Xfce...)."
  elif [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]] && command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled true || true
    echo "onboard ikke tilgængelig — brugte GNOME's indbyggede skærmtastatur i stedet (kun virker under GNOME Shell)."
  else
    echo "Kunne ikke aktivere et skærmtastatur automatisk — installer/sæt det manuelt for dit skrivebordsmiljø."
  fi
  echo "ON" > "$HOME/kiosk/keyboard_state"
else
  echo "Ingen grafisk session lige nu — sæt den til fra web-UI'et (Keyboard) eller Home Assistant efter reboot."
fi

if [[ "$DISPLAY_MANAGER" == "gdm3" && -f /etc/gdm3/custom.conf ]]; then
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
elif [[ "$DISPLAY_MANAGER" == "lightdm" ]]; then
  echo "== Sætter LightDM autologin for $USER (Linux Mint m.fl.) =="
  sudo mkdir -p /etc/lightdm/lightdm.conf.d
  sudo tee /etc/lightdm/lightdm.conf.d/50-kiosk-warden.conf >/dev/null <<EOF
[Seat:*]
autologin-user=$USER
autologin-user-timeout=0
EOF
  echo "LightDM ændret. En genstart er nødvendig før autologin virker."
else
  echo "Ingen kendt display manager (GDM/LightDM) fundet — sæt autologin manuelt."
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
Icon=$HOME/kiosk/icon.svg
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
Icon=$HOME/kiosk/icon.svg
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
echo "Fjernstyring (klik direkte på skærmen i browseren): klik 'Fjernstyring' i web-UI'et, eller åbn direkte:"
[[ -n "$IP_ADDR" ]] && echo "  http://$IP_ADDR:6080/vnc.html"
echo "Kræver VNC-passwordet sat ovenfor (separat fra web-UI-passwordet)."
echo "Kør 'bash ~/kiosk/mqtt-discovery.sh' for at (gen)publicere Home Assistant entities."
echo "Genstart maskinen for at få GDM-autologin og kiosk-chrome til at starte ved boot."
