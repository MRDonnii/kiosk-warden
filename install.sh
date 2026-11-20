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
  elif { : </dev/tty; } 2>/dev/null; then
    read "${readargs[@]}" val </dev/tty
  fi
  [[ "$silent" == "silent" ]] && echo >&2
  printf -v "$varname" '%s' "${val:-$default}"
}

valid_webui_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1024 && 10#$1 <= 65535 ))
}

webui_port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
    return
  fi
  timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$port" >/dev/null 2>&1
}

# Er der en terminal at spørge i? /dev/tty kan godt være læsbar uden at kunne åbnes (fx når Fleetdeck installerer).
has_tty() { [[ -t 0 ]] || { : </dev/tty; } 2>/dev/null; }

select_webui_port() {
  local requested="${KIOSK_WEBUI_PORT:-8080}" interactive=0
  has_tty && interactive=1
  while true; do
    if ! valid_webui_port "$requested"; then
      echo "Web-UI-port skal være et helt tal mellem 1024 og 65535: $requested" >&2
    elif ! webui_port_in_use "$requested"; then
      KIOSK_WEBUI_PORT="$requested"
      return 0
    else
      echo "Port $requested er allerede i brug. Vælg en anden port til Kiosk Warden Web-UI." >&2
    fi

    if (( interactive == 0 )); then
      echo "Kør installationen igen med f.eks. KIOSK_WEBUI_PORT=8081." >&2
      return 1
    fi
    requested=""
    if [[ -t 0 ]]; then
      read -rp "Ny Web-UI-port [8081]: " requested
    else
      read -rp "Ny Web-UI-port [8081]: " requested </dev/tty
    fi
    requested="${requested:-8081}"
  done
}

echo "== Registrerer OS og display manager =="
OS_ID="$(. /etc/os-release 2>/dev/null; echo "${ID:-unknown}")"
OS_NAME="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
OS_LIKE="$(. /etc/os-release 2>/dev/null; echo "${ID_LIKE:-}")"
ARCH="$(dpkg --print-architecture)"
IS_RASPBERRY_PI=0
if [[ "$OS_ID" == "raspbian" || -r /proc/device-tree/model && "$(tr -d '\0' </proc/device-tree/model)" == *"Raspberry Pi"* ]]; then
  IS_RASPBERRY_PI=1
fi

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
echo "OS: $OS_NAME ($OS_ID) — arkitektur: $ARCH — display manager: $DISPLAY_MANAGER — desktop: ${XDG_CURRENT_DESKTOP:-ukendt}"

if [[ "$IS_RASPBERRY_PI" -eq 1 ]]; then
  KIOSK_MIN_WIDTH="${KIOSK_MIN_WIDTH:-640}"
  KIOSK_MIN_HEIGHT="${KIOSK_MIN_HEIGHT:-400}"
  echo "== Raspberry Pi OS: aktiverer X11/Openbox til Warden-skærmstyring og x11vnc =="
  if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_wayland W1
    echo "Raspberry Pi OS skifter til X11 ved næste genstart."
  else
    echo "raspi-config mangler; X11 skal vælges manuelt før Chrome/VNC-styring virker." >&2
  fi
fi
KIOSK_MIN_WIDTH="${KIOSK_MIN_WIDTH:-1024}"
KIOSK_MIN_HEIGHT="${KIOSK_MIN_HEIGHT:-600}"

echo "== kiosk-warden install =="
echo
echo "Du kan udfylde kiosk-navn/URL/MQTT her i terminalen nu,"
echo "eller installere med standardværdier og gøre det bagefter via web-UI'et (System og Forbindelser)."

CONFIGURE_NOW="${CONFIGURE_NOW:-}"
if [[ -z "$CONFIGURE_NOW" ]]; then
  ans=""
  if [[ -t 0 ]]; then
    read -rp "Konfigurer nu i terminalen? [J/n]: " ans
  elif { : </dev/tty; } 2>/dev/null; then
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
else
  echo "Springer terminal-opsætning over — brug web-UI'et (System og Forbindelser) efter installationen."
  KIOSK_NAME="${KIOSK_NAME:-Kiosk}"
  KIOSK_ID="${KIOSK_ID:-kiosk_$(hostname | tr 'A-Z' 'a-z' | tr -c 'a-z0-9' '_')}"
  KIOSK_URL="${KIOSK_URL:-http://homeassistant.local:8123}"
  MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
  MQTT_PORT="${MQTT_PORT:-1883}"
  MQTT_USER="${MQTT_USER:-}"
  MQTT_PASS="${MQTT_PASS:-}"
  STATS_INTERVAL="${STATS_INTERVAL:-10}"
fi
if [[ -f "$HOME/kiosk/kiosk.conf" ]]; then
  existing_webui_port="$(sed -n -E 's/^KIOSK_WEBUI_PORT=\"?([0-9]+)\"?$/\1/p' "$HOME/kiosk/kiosk.conf" | tail -n1)"
  KIOSK_WEBUI_PORT="${KIOSK_WEBUI_PORT:-${existing_webui_port:-8080}}"
  valid_webui_port "$KIOSK_WEBUI_PORT" || {
    echo "Eksisterende KIOSK_WEBUI_PORT er ugyldig: $KIOSK_WEBUI_PORT" >&2
    exit 1
  }
else
  select_webui_port
fi
BASE_TOPIC="home/kiosk/${KIOSK_ID}"
CODEX_REMOTE_TOPIC="home/codex/${KIOSK_ID}/remote_control"

echo
echo "== Installerer apt-pakker =="
sudo apt-get update -y
required_packages=(git mosquitto-clients jq bc curl gnupg xdotool wmctrl unclutter
  x11-xserver-utils xinput xprintidle evtest lm-sensors openssh-server dbus-x11 python3 zip
  python3-websocket x11vnc novnc websockify)
sudo apt-get install -y "${required_packages[@]}"
if getent group input >/dev/null 2>&1; then
  sudo usermod -aG input "$USER"
fi

# Desktop conveniences and hardware telemetry differ between Ubuntu, Mint,
# Debian and Raspberry Pi OS. Missing optional packages must not abort install.
for package in htop onboard power-profiles-daemon linux-tools-common; do
  apt-cache show "$package" >/dev/null 2>&1 && sudo apt-get install -y "$package" || true
done

if ! command -v google-chrome-stable >/dev/null 2>&1 && ! command -v google-chrome >/dev/null 2>&1 \
   && ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  if [[ "$ARCH" == "amd64" ]]; then
  echo "== Installerer Google Chrome =="
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y google-chrome-stable
  else
    echo "== Installerer Chromium til $ARCH =="
    sudo apt-get install -y chromium || sudo apt-get install -y chromium-browser
  fi
fi

command -v google-chrome-stable >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1 \
  || command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 \
  || { echo "Ingen kompatibel Chrome/Chromium-browser blev installeret." >&2; exit 1; }

echo "== Kopierer scripts til ~/kiosk =="
mkdir -p "$HOME/kiosk/backups"
cp "$SRC_DIR"/scripts/*.sh "$HOME/kiosk/"
cp "$SRC_DIR"/scripts/*.py "$HOME/kiosk/"
chmod +x "$HOME"/kiosk/*.sh "$HOME"/kiosk/*.py
rm -f "$HOME/kiosk/take-screenshot.sh"
if [[ -d "$HOME/kiosk/screenshots" ]]; then
  find "$HOME/kiosk/screenshots" -maxdepth 1 -type f -delete
  rmdir "$HOME/kiosk/screenshots" 2>/dev/null || true
fi
cp "$SRC_DIR/VERSION" "$HOME/kiosk/version"
[[ -f "$HOME/kiosk/update_channel" ]] || printf 'stable\n' > "$HOME/kiosk/update_channel"
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
KIOSK_WEBUI_PORT=$KIOSK_WEBUI_PORT
KIOSK_VNC_PORT=${KIOSK_VNC_PORT:-5900}
KIOSK_NOVNC_PORT=${KIOSK_NOVNC_PORT:-6080}
KIOSK_SCREEN_BACKEND="${KIOSK_SCREEN_BACKEND:-auto}"
KIOSK_MIN_WIDTH=$KIOSK_MIN_WIDTH
KIOSK_MIN_HEIGHT=$KIOSK_MIN_HEIGHT
KIOSK_TOUCH_WAKE=${KIOSK_TOUCH_WAKE:-true}
KIOSK_TOUCH_RELEASE_DELAY=${KIOSK_TOUCH_RELEASE_DELAY:-1.2}
KIOSK_AUTO_BRIGHTNESS=${KIOSK_AUTO_BRIGHTNESS:-false}
KIOSK_BRIGHTNESS_MIN=${KIOSK_BRIGHTNESS_MIN:-15}
KIOSK_BRIGHTNESS_MAX=${KIOSK_BRIGHTNESS_MAX:-100}
EOF
  chmod 600 "$HOME/kiosk/kiosk.conf"
else
  echo "~/kiosk/kiosk.conf findes allerede — rører den ikke."
fi

# Refuse ambiguous or occupied ports before starting a fresh local service.
source "$HOME/kiosk/kiosk.conf"
for port in "${KIOSK_WEBUI_PORT:-8080}" "${KIOSK_VNC_PORT:-5900}" "${KIOSK_NOVNC_PORT:-6080}"; do
  valid_webui_port "$port" || { echo "Ugyldig lokal serviceport: $port" >&2; exit 1; }
done
[[ "${KIOSK_WEBUI_PORT:-8080}" != "${KIOSK_VNC_PORT:-5900}" && "${KIOSK_WEBUI_PORT:-8080}" != "${KIOSK_NOVNC_PORT:-6080}" && "${KIOSK_VNC_PORT:-5900}" != "${KIOSK_NOVNC_PORT:-6080}" ]] \
  || { echo "Web-UI, VNC og noVNC skal bruge hver sin port." >&2; exit 1; }
if ! systemctl --user is-active --quiet kiosk-webui.service 2>/dev/null; then
  for port in "${KIOSK_WEBUI_PORT:-8080}" "${KIOSK_VNC_PORT:-5900}" "${KIOSK_NOVNC_PORT:-6080}"; do
    webui_port_in_use "$port" && { echo "Lokal serviceport $port er allerede i brug." >&2; exit 1; }
  done
fi

echo "== Kopierer web-UI til ~/kiosk/webui =="
mkdir -p "$HOME/kiosk/webui"
cp "$SRC_DIR"/webui/*.py "$HOME/kiosk/webui/"
chmod +x "$HOME/kiosk/webui/server.py"

echo "== Installerer systemd user services =="
mkdir -p "$HOME/.config/systemd/user"
cp "$SRC_DIR"/systemd/*.service "$SRC_DIR"/systemd/*.timer "$SRC_DIR"/systemd/*.target "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable kiosk-chrome.service kiosk-mqtt-stats.service \
  kiosk-mqtt-control.service kiosk-watchdog.service kiosk-health.service kiosk-webui.service \
  kiosk-input-guardian.service \
  kiosk-adaptive-brightness.service kiosk-profile-scheduler.service kiosk-capabilities.timer
loginctl enable-linger "$USER" || true
systemctl --user start kiosk-mqtt-stats.service kiosk-mqtt-control.service kiosk-webui.service || true
systemctl --user disable --now kiosk-vnc.service kiosk-novnc.service >/dev/null 2>&1 || true
if [[ -n "${DISPLAY:-}" ]]; then
  systemctl --user start kiosk-capabilities.service kiosk-capabilities.timer kiosk-chrome.service kiosk-watchdog.service kiosk-health.service \
    kiosk-input-guardian.service kiosk-adaptive-brightness.service kiosk-profile-scheduler.service || true
else
  echo "Ingen grafisk session lige nu — Chrome-relaterede services starter ved næste login/reboot."
fi

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  echo "== Åbner porte i ufw (web-UI, VNC) =="
  sudo ufw allow "$KIOSK_WEBUI_PORT/tcp" || true
  sudo ufw allow "${KIOSK_NOVNC_PORT:-6080}/tcp" || true
  sudo ufw allow "${KIOSK_VNC_PORT:-5900}/tcp" || true
fi

echo "== Sudoers regel til reboot/shutdown =="
SUDOERS_FILE=/etc/sudoers.d/kiosk-warden
echo "$USER ALL=(root) NOPASSWD: /sbin/reboot, /sbin/poweroff" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 0440 "$SUDOERS_FILE"
sudo visudo -c -f "$SUDOERS_FILE"
# Lets Home Assistant's Install button on System Updates install the operating system updates (see the README).
sudo "$HOME/kiosk/setup-system-updates.sh"

echo "== Deaktiverer sleep/suspend/hibernate =="
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

echo "== Aktiverer skærmtastatur =="
if [[ -n "${DISPLAY:-}" ]]; then
  if command -v onboard >/dev/null 2>&1; then
    pgrep -x onboard >/dev/null || onboard >/dev/null 2>&1 &
    disown 2>/dev/null || true
    sleep 1
    if command -v xdotool >/dev/null 2>&1 && command -v wmctrl >/dev/null 2>&1; then
      geo="$(xdotool getdisplaygeometry 2>/dev/null)"
      scr_w="$(awk '{print $1}' <<<"$geo")"
      scr_h="$(awk '{print $2}' <<<"$geo")"
      if [[ -n "$scr_w" && -n "$scr_h" ]]; then
        kb_h=$(( scr_h / 3 ))
        kb_y=$(( scr_h - kb_h ))
        wmctrl -r onboard -e "0,0,$kb_y,$scr_w,$kb_h" 2>/dev/null || true
      fi
    fi
    echo "Bruger onboard, flyttet til bunden af skærmen med wmctrl (virker uanset desktop-miljø: GNOME, Cinnamon, MATE, Xfce...)."
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

# GNOME 49+ (fx Ubuntu 26.04) har ingen X11-session: så bruger kiosken sin egen lille X11-session
# (LightDM med autologin + Openbox, X uden markør; touch via libinput), så xdotool, xset/DPMS, x11vnc og RustDesk virker.
# KIOSK_SESSION=x11 tvinger den, KIOSK_SESSION=desktop beholder skrivebordets egen session.
gnome_has_x11() { ls /usr/share/xsessions/*.desktop >/dev/null 2>&1 && grep -lqiE 'gnome|ubuntu' /usr/share/xsessions/*.desktop 2>/dev/null; }
KIOSK_SESSION="${KIOSK_SESSION:-auto}"
if [[ "$KIOSK_SESSION" == "auto" ]]; then
  KIOSK_SESSION=desktop
  if [[ "$DISPLAY_MANAGER" == "gdm3" ]] && ! gnome_has_x11; then KIOSK_SESSION=x11; fi
fi
if [[ "$KIOSK_SESSION" == "x11" ]]; then
  echo "== Installerer X11-kiosksession (LightDM + Openbox, ingen markør) for $USER =="
  ts="$(date +%Y%m%d-%H%M%S)"
  if [[ -f /etc/gdm3/custom.conf ]]; then sudo cp /etc/gdm3/custom.conf "/etc/gdm3/custom.conf.bak.$ts"; fi
  echo "lightdm shared/default-x-display-manager select lightdm" | sudo debconf-set-selections
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confold \
    lightdm lightdm-gtk-greeter openbox xserver-xorg-core xserver-xorg-input-libinput xinit
  sudo mkdir -p /usr/share/xsessions /etc/lightdm/lightdm.conf.d
  printf '%s\n' '[Desktop Entry]' 'Name=Kiosk (X11)' \
    'Comment=Kiosk Warden: Chrome-kiosk på X11 med Openbox – touch, ingen markør' \
    "Exec=$HOME/kiosk/x11-kiosk-session.sh" 'Type=Application' 'DesktopNames=Kiosk' \
    | sudo tee /usr/share/xsessions/kiosk-x11.desktop >/dev/null
  printf '%s\n' '# Kiosk Warden: autologin i X11-kiosksessionen; X uden markør (touch virker stadig)' '[Seat:*]' \
    "autologin-user=$USER" 'autologin-user-timeout=0' 'autologin-session=kiosk-x11' 'user-session=kiosk-x11' \
    'xserver-command=X -nocursor' 'greeter-session=lightdm-gtk-greeter' \
    | sudo tee /etc/lightdm/lightdm.conf.d/50-kiosk-warden.conf >/dev/null
  sudo groupadd -f autologin
  sudo usermod -aG autologin "$USER"
  echo /usr/sbin/lightdm | sudo tee /etc/X11/default-display-manager >/dev/null
  sudo systemctl disable gdm3 >/dev/null 2>&1 || true
  sudo systemctl enable lightdm >/dev/null 2>&1 || sudo ln -sf /usr/lib/systemd/system/lightdm.service /etc/systemd/system/display-manager.service
  # GNOME-tjenester uden mening i kiosksessionen (velkomstguiden efter opgradering, Bluetooth-mediestyring) fejler ellers ved hver login
  systemctl --user mask gnome-initial-setup-upgrade-login.service mpris-proxy.service snap.firmware-updater.firmware-notifier.service >/dev/null 2>&1 || true
  DISPLAY_MANAGER=lightdm-kiosk
  echo "X11-kiosksession klar efter genstart. Tilbage til GDM: sudo sh ~/kiosk/rollback-to-gdm.sh"
fi

# LightDM kiosks (also the X11 kiosk session just set up above): lets the watchdog restart LightDM by itself when the kiosk session has ended and only the login screen
# shows (see the README). Not fatal if it cannot run now; the watchdog logs how to do it later.
if [[ "$DISPLAY_MANAGER" == lightdm* ]]; then
  sudo "$HOME/kiosk/setup-display-recovery.sh" || echo "Run later: sudo ~/kiosk/setup-display-recovery.sh"
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
Exec=xdg-open http://localhost:$KIOSK_WEBUI_PORT
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
echo "  http://localhost:$KIOSK_WEBUI_PORT  (på selve maskinen)"
[[ -n "$IP_ADDR" ]] && echo "  http://$IP_ADDR:$KIOSK_WEBUI_PORT  (fra andre enheder på netværket, fx telefonen)"
echo "Første besøg beder dig oprette administrator-login — gør det med det samme, siden UI'et er tilgængeligt på netværket."
echo "Fjernstyring (klik direkte på skærmen i browseren): klik 'Fjernstyring' i web-UI'et, eller åbn direkte:"
[[ -n "$IP_ADDR" ]] && echo "  http://$IP_ADDR:${KIOSK_NOVNC_PORT:-6080}/vnc.html"
echo "VNC bruger automatisk administrator-loginet fra Kiosk Warden; der oprettes ingen separat VNC-kode."
echo "Kør 'bash ~/kiosk/mqtt-discovery.sh' for at (gen)publicere Home Assistant entities."
echo "Genstart maskinen for at få GDM-autologin og kiosk-chrome til at starte ved boot."
