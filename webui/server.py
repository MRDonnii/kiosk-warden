#!/usr/bin/env python3
"""kiosk-warden web UI: setup + local control panel.

Stdlib-only on purpose (no pip installs needed on the kiosk). Binds to
0.0.0.0:8080 by default so it can be reached from other devices on the LAN
(e.g. a phone) — see README for restricting it to localhost instead.
"""
import collections
import http.cookies
import hashlib
import hmac
import html
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import subprocess
import threading
import time
import urllib.parse

import ha_client

HOME = os.path.expanduser("~")
KIOSK_DIR = os.path.join(HOME, "kiosk")
CONF_PATH = os.path.join(KIOSK_DIR, "kiosk.conf")
SCREENSHOT_PATH = os.path.join(KIOSK_DIR, "screenshots", "latest.jpg")
ICON_PATH = os.path.join(KIOSK_DIR, "icon.svg")
VNC_PASSWD_PATH = os.path.join(HOME, ".vnc", "passwd")
CHANGELOG_PATH = os.path.join(KIOSK_DIR, "CHANGELOG.md")
VERSION_PATH = os.path.join(KIOSK_DIR, "version")
UPDATE_CHANNEL_PATH = os.path.join(KIOSK_DIR, "update_channel")
UPDATE_STATUS_PATH = os.path.join(KIOSK_DIR, "update_status.json")
SMARTDASH_STATUS_PATH = os.path.join(KIOSK_DIR, "smartdash_status.json")
WARDEN_STATE_PATH = os.path.join(KIOSK_DIR, "warden_state.json")
SELF_TEST_PATH = os.path.join(KIOSK_DIR, "self_test.json")
DIAGNOSTICS_DIR = os.path.join(KIOSK_DIR, "diagnostics")
CAPABILITIES_PATH = os.path.join(KIOSK_DIR, "capabilities.json")
PROFILES_PATH = os.path.join(KIOSK_DIR, "profiles.json")
REPO_URL = os.environ.get("KIOSK_WARDEN_REPO", "https://github.com/MRDonnii/kiosk-warden.git")

FALLBACK_ICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2563eb"/>
      <stop offset="1" stop-color="#7c3aed"/>
    </linearGradient>
  </defs>
  <path d="M50 4 L90 18 V46 C90 74 72 90 50 97 C28 90 10 74 10 46 V18 Z" fill="url(#g)"/>
  <rect x="28" y="30" width="44" height="30" rx="4" fill="#0f172a"/>
  <rect x="31" y="33" width="38" height="21" rx="2" fill="#e2e8f0"/>
  <polyline points="35,46 42,46 46,38 51,52 55,42 58,46 65,46" fill="none" stroke="#22c55e" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="44" y="60" width="12" height="6" fill="#0f172a"/>
  <rect x="37" y="66" width="26" height="4" rx="2" fill="#0f172a"/>
</svg>
"""

BIND_HOST = os.environ.get("KIOSK_WEBUI_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("KIOSK_WEBUI_PORT", "8080"))

os.environ.setdefault("DISPLAY", ":0")
os.environ.setdefault("XAUTHORITY", os.path.join(HOME, ".Xauthority"))

CONF_ORDER = [
    "KIOSK_NAME", "KIOSK_ID", "KIOSK_URL", "MQTT_HOST", "MQTT_PORT",
    "MQTT_USER", "MQTT_PASS", "BASE_TOPIC", "CODEX_REMOTE_TOPIC",
    "STATS_INTERVAL", "KIOSK_WEBUI_PORT", "KIOSK_VNC_PORT", "KIOSK_NOVNC_PORT",
    "KIOSK_SCREEN_BACKEND", "KIOSK_MIN_WIDTH", "KIOSK_MIN_HEIGHT", "KIOSK_TOUCH_WAKE", "KIOSK_TOUCH_RELEASE_DELAY",
    "KIOSK_AUTO_BRIGHTNESS", "KIOSK_BRIGHTNESS_MIN", "KIOSK_BRIGHTNESS_MAX", "UI_LANGUAGE", "WEBUI_USERNAME", "WEBUI_PASSWORD_HASH",
    "HA_URL", "HA_TOKEN", "HA_POWER_ENTITY",
]

DEFAULTS = {
    "KIOSK_NAME": "Kiosk",
    "KIOSK_ID": "kiosk",
    "KIOSK_URL": "http://homeassistant.local:8123",
    "MQTT_HOST": "127.0.0.1",
    "MQTT_PORT": "1883",
    "MQTT_USER": "",
    "MQTT_PASS": "",
    "BASE_TOPIC": "home/kiosk/kiosk",
    "CODEX_REMOTE_TOPIC": "home/codex/kiosk/remote_control",
    "STATS_INTERVAL": "10",
    "KIOSK_WEBUI_PORT": "8080",
    "KIOSK_VNC_PORT": "5900",
    "KIOSK_NOVNC_PORT": "6080",
    "KIOSK_SCREEN_BACKEND": "auto",
    "KIOSK_MIN_WIDTH": "1024",
    "KIOSK_MIN_HEIGHT": "600",
    "KIOSK_TOUCH_WAKE": "true",
    "KIOSK_TOUCH_RELEASE_DELAY": "1.2",
    "KIOSK_AUTO_BRIGHTNESS": "false",
    "KIOSK_BRIGHTNESS_MIN": "15",
    "KIOSK_BRIGHTNESS_MAX": "100",
    "UI_LANGUAGE": "en",
    "WEBUI_USERNAME": "admin",
    "WEBUI_PASSWORD_HASH": "",
    "HA_URL": "",
    "HA_TOKEN": "",
    "HA_POWER_ENTITY": "",
}

# The templates use Danish as their canonical fallback because this project
# originated there. English is the product default; localisation happens once
# at the response boundary so dynamic messages and every page follow the same
# setting without duplicating templates or rebuilding the browser DOM.
ENGLISH_TEXT = {
    "Opsætning": "Setup",
    "Velkommen til Kiosk Warden": "Welcome to Kiosk Warden",
    "Opret administrator-login for at beskytte Kiosk Warden, før du gør noget andet.": "Create an administrator login to protect Kiosk Warden before doing anything else.",
    "Log ind": "Sign in", "Log ud": "Sign out", "Brugernavn": "Username", "Fortsæt til Kiosk Warden": "Continue to Kiosk Warden",
    "Forkert brugernavn eller password.": "Incorrect username or password.", "For mange loginforsøg. Prøv igen om lidt.": "Too many sign-in attempts. Try again shortly.",
    "Opret administrator": "Create administrator", "Opret login": "Create login",
    "Sæt password": "Set password", "Gentag password": "Repeat password", "Gem password": "Save password",
    "🏠 Oversigt": "🏠 Overview", "🖱️ Fjernstyring": "🖱️ Remote Control", "🎛️ Styring": "🎛️ Control",
    "⬇️ Opdateringer": "⬇️ Updates", "⚙️ Indstillinger": "⚙️ Settings",
    "Opdateringer": "Updates", "Ny version klar": "New version available", "Opdateret": "Up to date",
    "Installeret": "Installed", "Seneste på": "Latest on", "Release-kanal og installation": "Release channel and installation",
    "Opdateringskanal": "Update channel", "Tjek for updates": "Check for updates", "Gem kanal": "Save channel",
    "Installer v": "Install v", "Forbereder…": "Preparing…", "Opdateringen er installeret.": "The update is installed.",
    "Vælg hvad der skal genstartes, eller fortsæt uden genstart.": "Choose what to restart, or continue without restarting.",
    "Genstart Kiosk Warden": "Restart Kiosk Warden", "Genstart maskinen": "Restart machine", "Senere": "Later",
    "Seneste release": "Latest release", "Se hele releasen på GitHub": "View the full release on GitHub",
    "Gendan tidligere version": "Restore previous version", "Lokal snapshot": "Local snapshot",
    "Ingen snapshots endnu": "No snapshots yet", "Gendan valgt version": "Restore selected version",
    "Komplet changelog": "Complete changelog", "Tjekker GitHub Releases…": "Checking GitHub Releases…",
    "Starter opdateringen…": "Starting update…", "Arbejder…": "Working…", "Fejl": "Error",
    "Genstarter om": "Restarting in", "sekunder…": "seconds…", "Kører fint": "Healthy", "Ukendt": "Unknown",
    "Ny version tilgængelig": "New version available", "åbn Opdateringer": "open Updates", "Kører": "Running", "Stoppet": "Stopped",
    "Temperatur": "Temperature", "CPU-frekvens": "CPU frequency", "NVMe temperatur": "NVMe temperature", "Netværk": "Network",
    "seneste 60 minutter": "last 60 minutes", "CPU- og NVMe-temperatur": "CPU and NVMe temperature", "Netværkstrafik": "Network traffic",
    "Styring": "Control", "Strømprofil": "Power profile", "Strømbesparelse": "Power Saver", "Balanceret": "Balanced", "Ydelse": "Performance",
    "Strømbesparelse bruger mindst strøm. Balanceret og Ydelse giver gradvist mere CPU-kraft.": "Power Saver uses the least energy. Balanced and Performance progressively allow more CPU performance.",
    "Aktiv profil": "Active profile", "Skift strømprofil": "Change power profile", "Kiosk og Warden": "Kiosk and Warden",
    "Genindlæs side": "Reload page", "Genstart Chrome": "Restart Chrome", "Tag screenshot": "Take screenshot", "Backup config": "Back up config",
    "Skærmbillede": "Screenshot", "Seneste billede af den aktive kiosk-skærm. Brug Tag screenshot ovenfor for at opdatere det.": "Latest image of the active kiosk screen. Use Take screenshot above to refresh it.",
    "Seneste screenshot af kiosk-skærmen": "Latest screenshot of the kiosk screen", "Der er ikke taget et screenshot endnu.": "No screenshot has been taken yet.",
    "Maskine": "Machine", "Genstart maskine": "Restart machine", "Sluk maskine": "Shut down machine", "Kiosk Warden genstarter…": "Kiosk Warden is restarting…",
    "Indstillinger": "Settings", "Navn på kiosken": "Kiosk name", "bruges i MQTT-topics": "used in MQTT topics",
    "Web-UI port": "Web UI port", "Porten skal være mellem 1024 og 65535.": "The port must be between 1024 and 65535.",
    "Web-UI porten er allerede i brug.": "The Web UI port is already in use.",
    "Når porten ændres, genstarter kun Web-UI'en, og browseren viderestilles automatisk.": "When the port changes, only the Web UI restarts and the browser is redirected automatically.",
    "Web-UI porten er ændret": "The Web UI port has changed", "Forbinder til den nye adresse…": "Connecting to the new address…",
    "URL kiosken skal vise": "URL displayed by the kiosk", "MQTT brugernavn": "MQTT username",
    "MQTT password (tomt = behold nuværende)": "MQTT password (empty = keep current)", "Stats-interval (sekunder)": "Stats interval (seconds)",
    "Gem og genstart": "Save and restart", "Skift password": "Change password", "Nyt password": "New password",
    "Nyt VNC password": "New VNC password", "Gentag nyt VNC password": "Repeat new VNC password",
    "Separat fra login på denne side. Klassisk VNC-password — kun de første 8 tegn bruges.": "Separate from this page's login. Classic VNC password — only the first 8 characters are used.",
    "Fjernstyring": "Remote Control", "Fuld skærm": "Full screen", "Genopfrisk forbindelse": "Refresh connection",
    "Kræver VNC-password (separat fra login på denne side) ved forbindelse.": "A VNC password (separate from this page's login) is required when connecting.",
    "Brugerfladesprog": "Interface language", "Dansk": "Danish",
    "Password skal være mindst 8 tegn og matche i begge felter.": "Password must be at least 8 characters and match in both fields.",
    "VNC password skal være mindst 4 tegn og matche i begge felter.": "VNC password must be at least 4 characters and match in both fields.",
    "Password skiftet.": "Password changed.", "VNC password skiftet.": "VNC password changed.",
    "Ugyldig strømprofil.": "Invalid power profile.", "Kunne ikke skifte strømprofil": "Could not change power profile",
    "Strømprofil sat til": "Power profile changed to", "Ugyldig rollback-version.": "Invalid rollback version.",
    "Rollback fejlede.": "Rollback failed.", "Opdatering fejlede.": "Update failed.",
    "Allerede på nyeste version": "Already on the latest version", "Siden genstarter om et par sekunder…": "The page will restart in a few seconds…",
    "Smartdash-forbindelse": "Smartdash connection", "Automatisk registrering": "Automatic detection", "Forbundet": "Connected", "Ikke registreret": "Not detected",
    "Warden registrerer automatisk Smartdash på den aktive kiosk-URL. Ingen MQTT- eller IP-kobling skal opsættes.": "Warden automatically detects Smartdash at the active kiosk URL. No MQTT or IP link needs configuration.",
    'Pause og genoptagelse af <strong>animationer, livekameraer og rendering virker kun, når kiosken viser HA Smartdash</strong>. Skærmens almindelige tænd/sluk via DPMS virker fortsat med andre dashboards, men Warden kan ikke stoppe deres interne animationer eller mediearbejde. HA Smartdash registreres automatisk via Chromes lokale debug-port og kan også styres fra Home Assistant gennem MQTT-entityen Smartdash Rendering.':
        'Pausing and resuming <strong>animations, live cameras, and rendering only works when the kiosk displays HA Smartdash</strong>. Regular DPMS screen on/off still works with other dashboards, but Warden cannot stop their internal animations or media work. HA Smartdash is detected automatically through Chrome\'s local debug port and can also be controlled from Home Assistant through the Smartdash Rendering MQTT entity.',
    "Tilstand": "State", "Build": "Build", "Kontroller igen": "Check again",
    "Afhængighed mangler": "Dependency missing", "Kontakt fejlede": "Contact failed",
    "Python-modulet 'websocket' (python3-websocket) mangler. Kør installations- eller opdateringsscriptet igen.": "The 'websocket' Python module (python3-websocket) is missing. Run the install or update script again.",
    "Chromes debug-port (127.0.0.1:9222) svarer ikke. Chrome kører muligvis ikke, eller blev startet uden --remote-debugging-port.": "Chrome's debug port (127.0.0.1:9222) is not responding. Chrome may not be running, or was started without --remote-debugging-port.",
    "Chrome kører, men ingen synlig side blev fundet (flere faner/vinduer, eller siden er ikke indlæst endnu).": "Chrome is running, but no visible page was found (multiple tabs/windows, or the page hasn't loaded yet).",
    "Kiosk-id må kun indeholde a-z, 0-9 og _.": "Kiosk ID may only contain a-z, 0-9 and _.",
    "MQTT port skal være et tal.": "MQTT port must be a number.", "Stats-interval skal være et tal.": "Stats interval must be a number.",
    "Valgfrit. Lader Kiosk Warden vise et strøm/energi-tal fra Home Assistant på Oversigt-siden.": "Optional. Lets Kiosk Warden show a power/energy reading from Home Assistant on the Overview page.",
    "Home Assistant URL": "Home Assistant URL",
    "Opret et Long-Lived Access Token i Home Assistant →": "Create a Long-Lived Access Token in Home Assistant →",
    "Long-Lived Access Token (tomt ved gem = behold nuværende)": "Long-Lived Access Token (leave empty when saving to keep the current one)",
    "Strøm/energi-måler": "Power/energy sensor",
    "Ingen strøm- eller energi-målere fundet i Home Assistant.": "No power or energy sensors found in Home Assistant.",
    "Gem og test forbindelsen ovenfor for at vælge måleren.": "Save and test the connection above to choose the sensor.",
    "Gem og test forbindelse": "Save and test connection",
    "Effekt (Home Assistant)": "Power (Home Assistant)",
    "Effekt": "Power",
    "URL og token skal begge udfyldes.": "URL and token must both be filled in.",
    "Kunne ikke forbinde": "Could not connect",
    "Forbindelse OK.": "Connection OK.",
    "Home Assistant-forbindelse gemt.": "Home Assistant connection saved.",
}

SESSION_COOKIE = "warden_session"
SESSION_TTL = 12 * 60 * 60
_sessions = {}
_session_lock = threading.Lock()
_login_failures = {}


def localize_html(body, language):
    if language == "da":
        return body.replace('<html lang="en">', '<html lang="da">')
    for source in sorted(ENGLISH_TEXT, key=len, reverse=True):
        body = body.replace(source, ENGLISH_TEXT[source])
    return body


def read_conf():
    conf = dict(DEFAULTS)
    if os.path.exists(CONF_PATH):
        with open(CONF_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                    val = val[1:-1]
                conf[key] = val
    return conf


def write_conf(conf):
    os.makedirs(KIOSK_DIR, exist_ok=True)
    lines = [f'{key}="{conf.get(key, "")}"' for key in CONF_ORDER]
    tmp = CONF_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONF_PATH)


def hash_password(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}:{dk.hex()}"


def verify_password(password, stored):
    if not stored or ":" not in stored:
        return False
    salt, hashed = stored.split(":", 1)
    try:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), hashed)


def create_session():
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _session_lock:
        for old_token, expires in list(_sessions.items()):
            if expires <= now:
                _sessions.pop(old_token, None)
        _sessions[token] = now + SESSION_TTL
    return token


def valid_session(token):
    if not token:
        return False
    now = time.time()
    with _session_lock:
        expires = _sessions.get(token, 0)
        if expires <= now:
            _sessions.pop(token, None)
            return False
        _sessions[token] = now + SESSION_TTL
    return True


def destroy_session(token):
    with _session_lock:
        _sessions.pop(token, None)


def login_blocked(client_ip):
    now = time.time()
    with _session_lock:
        attempts = [stamp for stamp in _login_failures.get(client_ip, []) if now - stamp < 300]
        _login_failures[client_ip] = attempts
    return len(attempts) >= 5


def record_login_failure(client_ip):
    with _session_lock:
        _login_failures.setdefault(client_ip, []).append(time.time())


def clear_login_failures(client_ip):
    with _session_lock:
        _login_failures.pop(client_ip, None)


def set_vnc_password(password):
    vnc_dir = os.path.dirname(VNC_PASSWD_PATH)
    os.makedirs(vnc_dir, exist_ok=True)
    try:
        result = subprocess.run(["x11vnc", "-storepasswd", password, VNC_PASSWD_PATH],
                                 capture_output=True, text=True, timeout=10)
    except Exception as exc:
        return False, f"Kunne ikke sætte VNC password: {exc}"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "Kunne ikke sætte VNC password.").strip()
    try:
        os.chmod(VNC_PASSWD_PATH, 0o600)
    except OSError:
        pass
    run("systemctl", "--user", "restart", "kiosk-vnc.service")
    return True, "VNC password skiftet."


def run(*args, timeout=15):
    try:
        subprocess.run(list(args), timeout=timeout, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def run_bg(*args):
    try:
        subprocess.Popen(list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def current_version():
    return read_file(VERSION_PATH, "ukendt")


def version_newer(candidate, installed):
    pattern = r"^\d+\.\d+\.\d+$"
    if not re.match(pattern, candidate or "") or not re.match(pattern, installed or ""):
        return False
    return tuple(map(int, candidate.split("."))) > tuple(map(int, installed.split(".")))


POWER_PROFILES = {
    "power-saver": "Strømbesparelse",
    "balanced": "Balanceret",
    "performance": "Ydelse",
}


def current_power_profile():
    try:
        result = subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True, timeout=5)
        profile = result.stdout.strip()
        return profile if result.returncode == 0 and profile in POWER_PROFILES else "ukendt"
    except (OSError, subprocess.SubprocessError):
        return "ukendt"


def set_power_profile(profile):
    if profile not in POWER_PROFILES:
        return False, "Ugyldig strømprofil."
    try:
        result = subprocess.run(["powerprofilesctl", "set", profile], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Kunne ikke skifte strømprofil: {exc}"
    if result.returncode != 0:
        return False, (result.stderr or "Kunne ikke skifte strømprofil.").strip()
    return True, f"Strømprofil sat til {POWER_PROFILES[profile]}."


UPDATE_CHECK_INTERVAL = 1800  # 30 minutter
_update_cache = {"latest": None, "checked_at": 0.0, "error": None}
_update_lock = threading.Lock()
_telemetry = collections.deque(maxlen=2160)  # six hours at ten-second intervals
_telemetry_lock = threading.Lock()
_cpu_previous = None
_net_previous = None


def _do_update_check():
    try:
        latest = check_latest_version()
        with _update_lock:
            _update_cache["latest"] = latest
            _update_cache["error"] = None
    except Exception as exc:
        with _update_lock:
            _update_cache["error"] = str(exc)
    with _update_lock:
        _update_cache["checked_at"] = time.time()


def trigger_update_check():
    threading.Thread(target=_do_update_check, daemon=True).start()


def background_update_checker():
    while True:
        _do_update_check()
        time.sleep(UPDATE_CHECK_INTERVAL)


def get_cached_latest_version():
    with _update_lock:
        return _update_cache.get("latest")


def check_latest_version():
    channel = read_file(UPDATE_CHANNEL_PATH, "stable")
    result = subprocess.run([os.path.join(KIOSK_DIR, "self-update.sh"), "check", channel],
                             capture_output=True, text=True, timeout=25)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "kunne ikke kontakte GitHub")
    return json.loads(result.stdout)


def run_self_update(channel=None):
    # Runs the shared self-update.sh (also used by the MQTT "install" button)
    # in its own transient systemd scope via systemd-run, so restarting
    # kiosk-webui.service (or any other unit it restarts) at the end can't
    # kill the update process out from under itself.
    script = os.path.join(KIOSK_DIR, "self-update.sh")
    try:
        result = subprocess.run(
            ["systemd-run", "--user", "--wait", "--pipe", "--collect",
             "--unit", f"kiosk-self-update-{int(time.time())}", script, "install", channel or read_file(UPDATE_CHANNEL_PATH, "stable")],
            capture_output=True, text=True, timeout=90,
        )
    except Exception as exc:
        return False, f"Kunne ikke starte opdatering: {exc}"

    output = (result.stdout or "").strip()
    if output.startswith("UPTODATE"):
        return False, f"Allerede på nyeste version ({output.split()[1]})."
    if output.startswith("UPDATED"):
        return True, f"Opdateret til {output.split()[1]}. Siden genstarter om et par sekunder…"
    if output.startswith("ERROR"):
        return False, output[len("ERROR "):] or "Opdatering fejlede."
    return False, f"Uventet svar fra opdatering: {output or result.stderr.strip()}"


def start_self_update(channel):
    script = os.path.join(KIOSK_DIR, "self-update.sh")
    unit = f"kiosk-self-update-{int(time.time())}"
    result = subprocess.run(
        ["systemd-run", "--user", "--collect", "--unit", unit,
         script, "install", channel], capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "Kunne ikke starte opdateringen."
    return True, unit


def update_status():
    try:
        with open(UPDATE_STATUS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {}
        if data.get("result") == "complete":
            match = re.search(r"Kiosk Warden (\d+\.\d+\.\d+)", str(data.get("message", "")))
            if match and match.group(1) != current_version():
                return {"stage": "idle", "percent": 0, "message": "Klar til at tjekke efter opdateringer.", "result": "idle", "restart_required": False}
        return data
    except (OSError, ValueError):
        return {"stage": "idle", "percent": 0, "message": "Klar til at tjekke efter opdateringer.", "result": "idle", "restart_required": False}


def chrome_focus_and_key(key):
    try:
        out = subprocess.run(["wmctrl", "-lx"], capture_output=True, text=True, timeout=5).stdout
        win_id = None
        for line in out.splitlines():
            if "google-chrome" in line.lower() or "chromium" in line.lower():
                win_id = line.split()[0]
                break
        if win_id:
            subprocess.run(["wmctrl", "-ia", win_id], timeout=5)
        subprocess.run(["xdotool", "key", key], timeout=5)
    except Exception:
        pass


def read_file(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return default


def read_dmi(name, default="Ukendt"):
    try:
        with open(f"/sys/devices/virtual/dmi/id/{name}", encoding="utf-8") as f:
            val = f.read().strip()
            return val or default
    except OSError:
        return default


def read_uptime_human():
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            seconds = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return "?"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if days or hours:
        parts.append(f"{hours}t")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def read_loadavg():
    try:
        one, five, fifteen = os.getloadavg()
        return f"{one:.2f} / {five:.2f} / {fifteen:.2f}"
    except OSError:
        return "?"


def read_ram_percent():
    try:
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                parts = rest.strip().split()
                if parts:
                    info[key] = int(parts[0])
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", total)
        if total <= 0:
            return None
        return round(100 * (total - avail) / total, 1)
    except (OSError, ValueError):
        return None


def read_disk_percent():
    try:
        usage = shutil.disk_usage("/")
        if usage.total <= 0:
            return None
        return round(100 * usage.used / usage.total, 1)
    except OSError:
        return None


def read_cpu_temp():
    try:
        out = subprocess.run(["sensors"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if "Package id 0" in line or "Tctl" in line or re.match(r"^CPU", line):
            parts = line.split()
            if len(parts) >= 4:
                val = parts[3].lstrip("+").rstrip("°C").rstrip("C")
                try:
                    return round(float(val), 1)
                except ValueError:
                    continue
    return None


def read_nvme_temp():
    try:
        out = subprocess.run(["sensors"], capture_output=True, text=True, timeout=3).stdout
        block = out.split("nvme-pci-", 1)[1]
        match = re.search(r"Composite:\s+\+?([0-9.]+)°C", block)
        return round(float(match.group(1)), 1) if match else None
    except (Exception, IndexError):
        return None


def read_cpu_frequency():
    values = []
    for path in __import__("glob").glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"):
        try:
            values.append(int(read_file(path)))
        except ValueError:
            pass
    return round(sum(values) / len(values) / 1000) if values else None


def read_cpu_usage():
    global _cpu_previous
    try:
        fields = read_file("/proc/stat").splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
        total, idle = sum(values), values[3] + values[4]
    except (ValueError, IndexError):
        return None
    previous, _cpu_previous = _cpu_previous, (total, idle)
    if not previous or total == previous[0]:
        return 0.0
    return round(100 * (1 - (idle - previous[1]) / (total - previous[0])), 1)


def read_network_rate():
    global _net_previous
    total = 0
    try:
        for line in read_file("/proc/net/dev").splitlines()[2:]:
            name, data = line.split(":", 1)
            if name.strip() != "lo":
                fields = data.split(); total += int(fields[0]) + int(fields[8])
    except (ValueError, IndexError):
        return None
    now = time.time(); previous, _net_previous = _net_previous, (now, total)
    if not previous or now <= previous[0]:
        return 0.0
    return round((total - previous[1]) / (now - previous[0]) / 1024, 1)


def read_gpu_usage():
    try:
        result = subprocess.run(["turbostat", "--no-msr", "--no-perf", "--quiet", "--Summary",
                                 "--interval", "0.1", "--num_iterations", "1"],
                                capture_output=True, text=True, timeout=2)
        lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) >= 2 and "GFX%rc6" in lines[0]:
            rc6 = float(lines[1][lines[0].index("GFX%rc6")])
            return round(max(0.0, min(100.0, 100.0 - rc6)), 1)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        pass
    return None


def read_ha_power():
    """Current reading of the configured HA power/energy entity, or None.

    None (not an error) whenever HA_TOKEN/HA_POWER_ENTITY are unset, so this
    stays a no-op network call for installs that never set up the optional
    Home Assistant connection.
    """
    conf = read_conf()
    ha_url = conf.get("HA_URL", "")
    token = conf.get("HA_TOKEN", "")
    entity_id = conf.get("HA_POWER_ENTITY", "")
    if not ha_url or not token or not entity_id:
        return None
    state = ha_client.get_state(ha_url, token, entity_id)
    if not state:
        return None
    try:
        return round(float(state.get("state")), 1)
    except (TypeError, ValueError):
        return None


def collect_telemetry():
    sample_count = 0
    last_gpu = None
    while True:
        gpu = read_gpu_usage() if sample_count % 3 == 0 else last_gpu
        if gpu is not None:
            last_gpu = gpu
        sample = {"time": int(time.time()), "cpu": read_cpu_usage(), "ram": read_ram_percent(),
                  "gpu": last_gpu, "cpu_temp": read_cpu_temp(), "nvme_temp": read_nvme_temp(),
                  "cpu_mhz": read_cpu_frequency(), "network_kbps": read_network_rate(),
                  "ha_power": read_ha_power()}
        with _telemetry_lock:
            _telemetry.append(sample)
        sample_count += 1
        time.sleep(10)


def telemetry_data():
    with _telemetry_lock:
        return list(_telemetry)


def read_ip():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3).stdout
        parts = out.split()
        return parts[0] if parts else "?"
    except Exception:
        return "?"


def chrome_is_running():
    profile_dir = os.path.join(HOME, ".config", "chrome-kiosk")
    try:
        result = subprocess.run(["pgrep", "-f", profile_dir], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=3)
        return result.returncode == 0
    except Exception:
        return False


def get_stats():
    return {
        "hostname": os.uname().nodename,
        "ip": read_ip(),
        "uptime": read_uptime_human(),
        "loadavg": read_loadavg(),
        "ram_percent": read_ram_percent(),
        "disk_percent": read_disk_percent(),
        "cpu_temp": read_cpu_temp(),
        "chrome_running": chrome_is_running(),
        "model": read_dmi("product_name"),
    }


def level_for(value, warn, crit):
    if value is None:
        return "neutral"
    if value >= crit:
        return "err"
    if value >= warn:
        return "warn"
    return "ok"


def render_tile(icon, label, value, level="neutral"):
    return (
        f'<div class="tile tile-{level}">'
        f'<div class="tile-icon">{icon}</div>'
        f'<div class="tile-body">'
        f'<div class="tile-label">{esc(label)}</div>'
        f'<div class="tile-value">{esc(value)}</div>'
        f'</div></div>'
    )


def webui_port_available(port):
    """Return whether a new WebUI listener can bind on all interfaces."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((BIND_HOST, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def validate_settings(fields):
    kiosk_id = fields.get("KIOSK_ID", [""])[0].strip()
    kiosk_url = fields.get("KIOSK_URL", [""])[0].strip()
    mqtt_port = fields.get("MQTT_PORT", [""])[0].strip()
    stats_interval = fields.get("STATS_INTERVAL", [""])[0].strip()
    webui_port = fields.get("KIOSK_WEBUI_PORT", [str(BIND_PORT)])[0].strip()
    vnc_port = fields.get("KIOSK_VNC_PORT", ["5900"])[0].strip()
    novnc_port = fields.get("KIOSK_NOVNC_PORT", ["6080"])[0].strip()
    backend = fields.get("KIOSK_SCREEN_BACKEND", ["auto"])[0].strip()
    brightness_min = fields.get("KIOSK_BRIGHTNESS_MIN", ["15"])[0].strip()
    brightness_max = fields.get("KIOSK_BRIGHTNESS_MAX", ["100"])[0].strip()
    if not re.match(r"^[a-z0-9_]+$", kiosk_id):
        return "Kiosk-id må kun indeholde a-z, 0-9 og _."
    if not re.fullmatch(r"https?://[^\s\"'\\]+", kiosk_url):
        return "URL skal starte med http:// eller https://."
    if not mqtt_port.isdigit():
        return "MQTT port skal være et tal."
    if not stats_interval.isdigit():
        return "Stats-interval skal være et tal."
    if not webui_port.isdigit() or not 1024 <= int(webui_port) <= 65535:
        return "Porten skal være mellem 1024 og 65535."
    if int(webui_port) != BIND_PORT and not webui_port_available(int(webui_port)):
        return "Web-UI porten er allerede i brug."
    current = read_conf()
    ports = {"VNC": vnc_port, "noVNC": novnc_port}
    for name, port in ports.items():
        if not port.isdigit() or not 1024 <= int(port) <= 65535:
            return f"{name}-porten skal være mellem 1024 og 65535."
        current_key = "KIOSK_VNC_PORT" if name == "VNC" else "KIOSK_NOVNC_PORT"
        if port != current.get(current_key) and not webui_port_available(int(port)):
            return f"{name}-porten er allerede i brug."
    if len({webui_port, vnc_port, novnc_port}) != 3:
        return "Web-UI, VNC og noVNC skal bruge hver sin port."
    if backend not in {"auto", "gnome-x11", "cinnamon-x11", "x11", "wayland-wlopm", "wayland-kde", "raspberry-pi", "ddc", "cec"}:
        return "Ugyldig skærm-backend."
    if not brightness_min.isdigit() or not brightness_max.isdigit() or not 1 <= int(brightness_min) <= int(brightness_max) <= 100:
        return "Lysstyrkegrænser skal være 1–100, og minimum må ikke være større end maksimum."
    return None


def esc(value):
    return html.escape(str(value), quote=True)


PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="apple-touch-icon" href="/icon.svg">
<title>Kiosk Warden{title_suffix}</title>
<style>
  :root {{
    color-scheme: light dark;
    --accent: #2563eb; --accent-2: #7c3aed;
    --ok: #22c55e; --warn: #f59e0b; --err: #ef4444;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: min(1200px, 95vw); margin: 0 auto;
    padding: 1.4rem 1rem 3rem; line-height: 1.45;
    background:
      radial-gradient(1100px circle at 12% -10%, rgba(37,99,235,.12), transparent 55%),
      radial-gradient(900px circle at 100% 0%, rgba(124,58,237,.10), transparent 55%);
    background-attachment: fixed;
  }}
  .narrow {{ max-width: 640px; }}
  .brand {{ display:flex; align-items:center; gap:.55rem; margin-bottom: 1.2rem; }}
  .brand img {{ width:1.6rem; height:1.6rem; display:block; filter: drop-shadow(0 1px 3px rgba(0,0,0,.25)); }}
  .brand span {{ font-size:.78rem; letter-spacing:.09em; text-transform:uppercase; opacity:.55; font-weight:700; }}
  .header-row {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; flex-wrap:wrap; margin-bottom: .3rem; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 .15rem; letter-spacing: -.01em; }}
  .sub {{ opacity: .6; font-size: .85rem; margin-bottom: 1.3rem; }}
  fieldset {{
    border: 1px solid rgba(128,128,128,.26); border-radius: 16px; margin-bottom: 1.1rem;
    padding: 1rem 1.1rem 1.2rem; background: rgba(128,128,128,.04);
    backdrop-filter: blur(6px);
  }}
  legend {{ padding: 0 .5rem; font-weight: 700; font-size: .95rem; }}
  label {{ display:block; margin-top:.75rem; font-size:.82rem; opacity: .8; }}
  input[type=text], input[type=password], input[type=number] {{
    width:100%; padding:.6rem .7rem; margin-top:.3rem; box-sizing:border-box;
    border-radius:9px; border:1px solid rgba(128,128,128,.4); font-size: 1rem;
    background: rgba(128,128,128,.05); color: inherit;
  }}
  select {{ width:100%; padding:.6rem .7rem; margin-top:.3rem; border-radius:9px;
    border:1px solid rgba(128,128,128,.4); font-size:1rem; background:rgba(128,128,128,.05); color:inherit; }}
  input:focus {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
  .row {{ display:flex; gap:.5rem; flex-wrap:wrap; margin-top: .7rem; }}
  button {{
    padding:.65rem 1.15rem; border-radius:10px; border:1px solid rgba(128,128,128,.4);
    cursor:pointer; font-size:.92rem; font-weight:600; background: rgba(128,128,128,.08); color: inherit;
    transition: filter .1s ease, transform .05s ease;
  }}
  button:hover {{ filter: brightness(1.1); }}
  button:active {{ transform: scale(.98); }}
  button.primary {{ background: linear-gradient(135deg, var(--accent), var(--accent-2)); color:#fff; border-color: transparent;
    box-shadow: 0 4px 14px rgba(37,99,235,.35); }}
  button.accent {{ background: linear-gradient(135deg, #06b6d4, var(--accent-2)); color:#fff; border-color: transparent;
    box-shadow: 0 4px 14px rgba(124,58,237,.3); }}
  button:disabled {{ cursor:not-allowed; opacity:.38; filter:grayscale(.75); box-shadow:none; }}
  button:disabled:hover {{ filter:grayscale(.75); }}
  button:disabled:active {{ transform:none; }}
  button.danger {{ background: linear-gradient(135deg, #ef4444, #b91c1c); color:#fff; border-color: transparent; }}
  .msg {{ padding:.7rem 1rem; border-radius:10px; margin-bottom:1rem; font-size:.9rem; font-weight:600; }}
  .msg.error {{ background:rgba(239,68,68,.15); color:#dc2626; }}
  .msg.ok {{ background:rgba(34,197,94,.15); color:#16a34a; }}
  img.shot {{ max-width:100%; border-radius:12px; border:1px solid rgba(128,128,128,.3); display:block; }}
  .status {{ font-size:.85rem; opacity:.7; margin-top:.4rem; }}
  a {{ color: var(--accent); }}
  .pill {{ padding:.35rem .8rem; border-radius:999px; font-size:.78rem; font-weight:700; white-space:nowrap; }}
  .pill.ok {{ background:rgba(34,197,94,.18); color:#16a34a; }}
  .pill.err {{ background:rgba(239,68,68,.18); color:#dc2626; }}
  .pill.warn {{ background:rgba(245,158,11,.18); color:#b45309; }}
  .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(190px,1fr)); gap:.7rem; margin: 0 0 1.3rem; }}
  .tile {{
    display:flex; align-items:center; gap:.7rem;
    background: rgba(128,128,128,.05); border:1px solid rgba(128,128,128,.2); border-left: 4px solid var(--accent);
    border-radius: 12px; padding:.7rem .8rem;
  }}
  .tile-icon {{
    width:2.2rem; height:2.2rem; border-radius:10px; font-size:1.25rem; flex-shrink:0;
    display:flex; align-items:center; justify-content:center; background: rgba(37,99,235,.12);
  }}
  .tile-ok {{ border-left-color: var(--ok); }}
  .tile-ok .tile-icon {{ background: rgba(34,197,94,.16); }}
  .tile-ok .tile-value {{ color:#16a34a; }}
  .tile-warn {{ border-left-color: var(--warn); }}
  .tile-warn .tile-icon {{ background: rgba(245,158,11,.16); }}
  .tile-warn .tile-value {{ color:#b45309; }}
  .tile-err {{ border-left-color: var(--err); }}
  .tile-err .tile-icon {{ background: rgba(239,68,68,.16); }}
  .tile-err .tile-value {{ color:#dc2626; }}
  .tile-body {{ min-width:0; }}
  .tile-label {{ font-size:.66rem; text-transform:uppercase; letter-spacing:.06em; opacity:.55; margin-bottom:.2rem; font-weight:700; }}
  .tile-value {{ font-size:1.1rem; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .nav {{ display:flex; gap:.5rem; margin: 1.1rem 0 1.4rem; flex-wrap:wrap; }}
  .nav a {{ text-decoration:none; }}
  .nav-btn {{
    display:inline-block; padding:.55rem 1.05rem; border-radius:10px; font-size:.85rem; font-weight:700;
    background: rgba(128,128,128,.07); border:1px solid rgba(128,128,128,.25); color:inherit;
  }}
  .nav-btn.active {{ background: linear-gradient(135deg, var(--accent), var(--accent-2)); color:#fff; border-color: transparent;
    box-shadow: 0 4px 14px rgba(37,99,235,.3); }}
  .update-banner {{
    background: linear-gradient(135deg, var(--accent), var(--accent-2)); color:#fff; font-weight:700;
    padding:.8rem 1.1rem; border-radius:12px; margin-bottom:1.1rem; box-shadow: 0 4px 14px rgba(37,99,235,.3);
  }}
  .changelog h2 {{ font-size:1.05rem; margin: 1.4rem 0 .4rem; }}
  .changelog h2:first-child {{ margin-top: 0; }}
  .changelog ul {{ padding-left:1.3rem; margin:.3rem 0 0; }}
  .changelog li {{ margin:.3rem 0; }}
  .changelog p {{ opacity:.75; font-size:.85rem; margin:.2rem 0 .6rem; }}
  .version-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:.7rem; margin-bottom:1rem; }}
  .version-card {{ border:1px solid rgba(128,128,128,.24); border-radius:14px; padding:1rem; background:rgba(128,128,128,.05); }}
  .version-card span {{ display:block; opacity:.6; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }}
  .version-card strong {{ display:block; font-size:1.35rem; margin-top:.25rem; }}
  .release-notes {{ border-left:4px solid var(--accent); padding:.2rem 0 .2rem 1rem; margin:1rem 0; }}
  .progress-shell {{ display:none; margin-top:1rem; }}
  .progress-track {{ height:14px; overflow:hidden; border-radius:999px; background:rgba(128,128,128,.18); }}
  .progress-fill {{ width:0; height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--accent),var(--accent-2)); transition:width .35s ease; }}
  .progress-meta {{ display:flex; justify-content:space-between; gap:1rem; margin-top:.45rem; font-size:.82rem; }}
  .restart-choice {{ display:none; margin-top:1rem; padding:1rem; border-radius:12px; background:rgba(34,197,94,.12); }}
  .countdown {{ font-size:1.1rem; font-weight:800; color:var(--warn); }}
  .charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:.8rem; margin-bottom:1.1rem; }}
  .chart-card {{ border:1px solid rgba(128,128,128,.24); border-radius:14px; padding:.8rem; background:rgba(128,128,128,.04); }}
  .chart-title {{ font-size:.8rem; font-weight:700; margin-bottom:.45rem; opacity:.8; }}
  canvas.telemetry-chart {{ display:block; width:100%; height:150px; }}
  @media (max-width:600px) {{ .charts {{ grid-template-columns:1fr; }} }}
  .login-shell {{ min-height:calc(100vh - 6rem); display:grid; place-items:center; }}
  .login-card {{ width:min(430px, 100%); padding:2rem; border:1px solid rgba(128,128,128,.28); border-radius:24px;
    background:rgba(20,24,34,.82); box-shadow:0 24px 80px rgba(0,0,0,.35); backdrop-filter:blur(18px); }}
  .login-mark {{ width:64px; height:64px; margin:0 auto .8rem; display:grid; place-items:center; border-radius:18px;
    background:linear-gradient(135deg,rgba(37,99,235,.24),rgba(124,58,237,.24)); }}
  .login-mark img {{ width:44px; height:44px; }}
  .login-product {{ text-align:center; text-transform:uppercase; letter-spacing:.13em; font-size:.72rem; font-weight:800; opacity:.55; }}
  .login-card h1 {{ text-align:center; font-size:1.85rem; margin:.35rem 0 .15rem; }}
  .login-card .sub {{ text-align:center; margin-bottom:1.25rem; }}
  .login-button {{ width:100%; margin-top:1.25rem; padding:.8rem; }}
  .login-note {{ text-align:center; opacity:.45; font-size:.72rem; margin:1.2rem 0 0; }}
</style>
</head>
<body>
<div class="brand"><img src="/icon.svg" alt=""><span>Kiosk Warden</span></div>
"""

PAGE_TAIL = "</body></html>"


def render_message(message, error):
    out = ""
    if error:
        out += f'<div class="msg error">{esc(error)}</div>'
    if message:
        out += f'<div class="msg ok">{esc(message)}</div>'
    return out


def render_first_run(message=None, error=None):
    body = PAGE_HEAD.format(title_suffix=" — Opsætning")
    body += '<main class="login-shell"><section class="login-card">'
    body += '<div class="login-mark"><img src="/icon.svg" alt=""></div><div class="login-product">Kiosk Warden</div>'
    body += "<h1>Velkommen</h1>"
    body += '<div class="sub">Opret administrator-login for at beskytte Kiosk Warden, før du gør noget andet.</div>'
    body += render_message(message, error)
    body += f"""
<form method="post" action="/set-password">
    <label>Brugernavn</label>
    <input type="text" name="username" value="admin" required minlength="3" maxlength="40" autocomplete="username">
    <label>Password (min. 8 tegn)</label>
    <input type="password" name="password" required minlength="8" autocomplete="new-password">
    <label>Gentag password</label>
    <input type="password" name="password2" required minlength="8" autocomplete="new-password">
    <button class="primary login-button" type="submit">Opret login</button>
</form>
<p class="login-note">Lokal administration · login kan ændres senere</p>
"""
    body += "</section></main>"
    body += PAGE_TAIL
    return body


def render_login(conf, next_path="/", error=None):
    safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    body = PAGE_HEAD.format(title_suffix=" — Log ind")
    body += f"""
<main class="login-shell">
  <section class="login-card">
    <div class="login-mark"><img src="/icon.svg" alt=""></div>
    <div class="login-product">Kiosk Warden</div>
    <h1>Log ind</h1>
    <p class="sub">{esc(conf.get('KIOSK_NAME', 'Kiosk'))}</p>
    {render_message(None, error)}
    <form method="post" action="/login">
      <input type="hidden" name="next" value="{esc(safe_next)}">
      <label>Brugernavn</label>
      <input type="text" name="username" required autofocus autocomplete="username">
      <label>Password</label>
      <input type="password" name="password" required autocomplete="current-password">
      <button class="primary login-button" type="submit">Fortsæt til Kiosk Warden</button>
    </form>
    <p class="login-note">Lokal administration · sessionen udløber automatisk</p>
  </section>
</main>
"""
    return body + PAGE_TAIL


def render_nav(active):
    items = [
        ("/", "🏠 Oversigt"),
        ("/vnc", "🖱️ Fjernstyring"),
        ("/control", "🎛️ Styring"),
        ("/updates", "⬇️ Opdateringer"),
        ("/settings", "⚙️ Indstillinger"),
        ("/logout", "↪ Log ud"),
    ]
    parts = []
    for path, label in items:
        cls = "nav-btn active" if path == active else "nav-btn"
        parts.append(f'<a href="{path}"><span class="{cls}">{label}</span></a>')
    return '<div class="nav">' + "".join(parts) + "</div>"


def render_markdown_lite(text):
    lines_out = []
    in_list = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if in_list:
                lines_out.append("</ul>")
                in_list = False
            lines_out.append(f"<h2>{esc(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                lines_out.append("</ul>")
                in_list = False
            lines_out.append(f"<h2>{esc(line[2:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                lines_out.append("<ul>")
                in_list = True
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(line[2:]))
            lines_out.append(f"<li>{content}</li>")
        elif line == "":
            if in_list:
                lines_out.append("</ul>")
                in_list = False
        else:
            if in_list:
                lines_out.append("</ul>")
                in_list = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(line))
            lines_out.append(f"<p>{content}</p>")
    if in_list:
        lines_out.append("</ul>")
    return "\n".join(lines_out)


def render_updates(conf, message=None, error=None):
    channel = read_file(UPDATE_CHANNEL_PATH, "stable")
    latest = get_cached_latest_version()
    if not isinstance(latest, dict):
        try:
            latest = check_latest_version()
        except Exception:
            latest = {}
    installed = current_version()
    latest_version = latest.get("latest_version", "ukendt")
    prerelease = bool(latest.get("prerelease"))
    release_url = latest.get("release_url", "")
    release_summary = latest.get("release_summary", "Ingen release-noter tilgængelige.")
    try:
        backups = subprocess.run([os.path.join(KIOSK_DIR, "self-update.sh"), "list"],
                                 capture_output=True, text=True, timeout=10).stdout.splitlines()
    except Exception:
        backups = []
    versions = []
    for name in backups:
        match = re.match(r"^(\d+\.\d+\.\d+)-", name)
        if match and match.group(1) not in versions:
            versions.append(match.group(1))
    rollback_options = "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in versions)
    update_ready = version_newer(latest_version, installed)
    body = PAGE_HEAD.format(title_suffix=" — Opdateringer")
    body += f"""
<div class="header-row">
  <div>
    <h1>Opdateringer</h1>
    <div class="sub">{esc(conf.get('KIOSK_NAME', 'Kiosk'))}</div>
  </div>
  <span class="pill {'warn' if update_ready else 'ok'}">{'Ny version klar' if update_ready else 'Opdateret'}</span>
</div>
"""
    body += render_nav("/updates")
    body += render_message(message, error)
    body += f"""
<div class="version-grid">
  <div class="version-card"><span>Installeret</span><strong>v{esc(installed)}</strong></div>
  <div class="version-card"><span>Seneste på {esc(channel.title())}</span><strong>v{esc(latest_version)}</strong></div>
</div>
<fieldset>
  <legend>Release-kanal og installation</legend>
  <form method="post" action="/update">
    <label>Opdateringskanal</label>
    <select name="channel"><option value="stable"{' selected' if channel == 'stable' else ''}>Stable</option><option value="beta"{' selected' if channel == 'beta' else ''}>Beta</option></select>
    <div class="row"><button type="button" id="checkUpdates">Tjek for updates</button><button type="submit" formaction="/update-channel">Gem kanal</button><button class="accent" type="submit" id="installUpdate"{' disabled' if not update_ready else ''}>⬇️ Installer v{esc(latest_version)}</button></div>
  </form>
  <div class="progress-shell" id="updateProgress"><div class="progress-track"><div class="progress-fill" id="updateProgressFill"></div></div><div class="progress-meta"><span id="updateProgressText">Forbereder…</span><strong id="updateProgressPercent">0%</strong></div></div>
  <div class="restart-choice" id="restartChoice"><strong>Opdateringen er installeret.</strong><p>Vælg hvad der skal genstartes, eller fortsæt uden genstart.</p><div class="row"><button class="primary" type="button" id="restartWarden">Genstart Kiosk Warden</button><button type="button" id="restartMachine">Genstart maskinen</button><button type="button" id="restartLater">Senere</button></div><div class="countdown" id="restartCountdown"></div></div>
  <div class="release-notes changelog"><strong>Seneste release{' · Beta' if prerelease else ''}</strong>{render_markdown_lite(release_summary)}</div>
  {f'<a href="{esc(release_url)}" target="_blank" rel="noreferrer">Se hele releasen på GitHub</a>' if release_url else ''}
</fieldset>
<fieldset>
  <legend>Gendan tidligere version</legend>
  <form method="post" action="/rollback">
    <label>Lokal snapshot</label>
    <select name="version" {'disabled' if not versions else ''}>{rollback_options or '<option>Ingen snapshots endnu</option>'}</select>
    <div class="row"><button type="submit" {'disabled' if not versions else ''} onclick="return confirm('Gendan den valgte version?');">Gendan valgt version</button></div>
  </form>
</fieldset>
<fieldset><legend>Komplet changelog</legend>
"""
    text = read_file(CHANGELOG_PATH, "Ingen changelog fundet endnu.")
    body += '<div class="changelog">'
    body += render_markdown_lite(text)
    body += "</div></fieldset>"
    body += """
<script>
const progress = document.getElementById('updateProgress');
const fill = document.getElementById('updateProgressFill');
const progressText = document.getElementById('updateProgressText');
const progressPercent = document.getElementById('updateProgressPercent');
const restartChoice = document.getElementById('restartChoice');
let pollTimer = null;
function ensureStatusPolling() {
  if (!pollTimer) pollTimer = setInterval(pollStatus, 800);
}
function showStatus(status) {
  const percent = Math.max(0, Math.min(100, Number(status.percent || 0)));
  if (status.result !== 'idle') progress.style.display = 'block';
  fill.style.width = percent + '%'; progressPercent.textContent = percent + '%';
  progressText.textContent = status.message || status.stage || 'Arbejder…';
  // The install form redirects to /updates?started=1. That navigation tears
  // down the interval started by the submitting page, so the fresh page must
  // resume polling when its initial status read says the updater is running.
  // Without this it commonly rendered the download stage (20%) forever even
  // though self-update.sh continued and completed successfully in systemd.
  if (status.result === 'running') { ensureStatusPolling(); return; }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (status.result === 'complete' && status.restart_required && localStorage.getItem('kiosk-restart-later') !== status.updated_at) restartChoice.style.display = 'block';
}
async function pollStatus() {
  try { const response = await fetch('/api/update-status', {cache:'no-store'}); if (response.ok) showStatus(await response.json()); } catch (_) {}
}
document.getElementById('checkUpdates').addEventListener('click', async () => {
  progress.style.display = 'block'; progressText.textContent = 'Tjekker GitHub Releases…'; fill.style.width = '10%'; progressPercent.textContent = '10%';
  try { const response = await fetch('/api/update-check', {method:'POST'}); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Update-tjek fejlede'); location.reload(); }
  catch (error) { progressText.textContent = error.message; fill.style.width = '100%'; progressPercent.textContent = 'Fejl'; }
});
document.getElementById('installUpdate').closest('form').addEventListener('submit', event => {
  if (event.submitter && event.submitter.id !== 'installUpdate') return;
  progress.style.display = 'block'; showStatus({percent:2,message:'Starter opdateringen…',result:'running'});
  setTimeout(pollStatus, 250);
});
document.getElementById('restartLater').addEventListener('click', async () => { const response = await fetch('/api/update-status', {cache:'no-store'}); const status = await response.json(); restartChoice.style.display = 'none'; localStorage.setItem('kiosk-restart-later', status.updated_at || '1'); });
function restartCountdown(action, button, label) {
  let seconds = 5; button.disabled = true; label.textContent = `Genstarter om ${seconds} sekunder…`;
  const timer = setInterval(async () => { seconds -= 1; label.textContent = `Genstarter om ${seconds} sekunder…`; if (seconds <= 0) { clearInterval(timer); await fetch('/action', {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'do=' + encodeURIComponent(action)}); } }, 1000);
}
document.getElementById('restartWarden').addEventListener('click', event => restartCountdown('restart_warden', event.currentTarget, document.getElementById('restartCountdown')));
document.getElementById('restartMachine').addEventListener('click', event => restartCountdown('reboot', event.currentTarget, document.getElementById('restartCountdown')));
pollStatus();
</script>
"""
    body += PAGE_TAIL
    return body


def render_dashboard(conf, message=None, error=None):
    health_state = read_file(os.path.join(KIOSK_DIR, "health_state"), "?")
    health_detail = read_file(os.path.join(KIOSK_DIR, "health_detail"), "")
    stats = get_stats()
    history = telemetry_data()
    live = history[-1] if history else {}

    pill_class = "ok" if health_state == "ON" else ("err" if health_state == "OFF" else "warn")
    pill_label = {"ON": "Kører fint", "OFF": "Fejl"}.get(health_state, health_state or "Ukendt")

    body = PAGE_HEAD.format(title_suffix=f" — {esc(conf.get('KIOSK_NAME', 'Kiosk'))}")
    body += f"""
<div class="header-row">
  <div>
    <h1>{esc(conf.get('KIOSK_NAME', 'Kiosk'))}</h1>
    <div class="sub">Kiosk-id: {esc(conf.get("KIOSK_ID",""))}</div>
  </div>
  <span class="pill {pill_class}">{esc(pill_label)}</span>
</div>
"""
    body += render_nav("/")

    latest = get_cached_latest_version()
    current = current_version()
    latest_version = latest.get("latest_version") if isinstance(latest, dict) else None
    if latest_version and version_newer(latest_version, current):
        body += f"""
<a href="/updates" style="text-decoration:none; color:inherit;">
  <div class="update-banner">🔔 Ny version tilgængelig ({esc(latest_version)}) — åbn Opdateringer</div>
</a>
"""

    body += render_message(message, error)

    chrome_label = "Kører" if stats["chrome_running"] else "Stoppet"
    chrome_level = "ok" if stats["chrome_running"] else "err"
    temp_val = f'{stats["cpu_temp"]}°C' if stats["cpu_temp"] is not None else "?"
    ram_val = f'{stats["ram_percent"]}%' if stats["ram_percent"] is not None else "?"
    disk_val = f'{stats["disk_percent"]}%' if stats["disk_percent"] is not None else "?"

    body += '<div class="grid">'
    body += render_tile("🌐", "IP", stats["ip"])
    body += render_tile("⏱️", "Oppetid", stats["uptime"])
    body += render_tile("🧠", "RAM", ram_val, level_for(stats["ram_percent"], 70, 90))
    body += render_tile("💾", "Disk", disk_val, level_for(stats["disk_percent"], 80, 93))
    body += render_tile("🌡️", "Temperatur", temp_val, level_for(stats["cpu_temp"], 65, 80))
    body += render_tile("📈", "CPU", f'{live.get("cpu")}%' if live.get("cpu") is not None else stats["loadavg"].split(" / ")[0])
    body += render_tile("🎮", "GPU", f'{live.get("gpu")}%' if live.get("gpu") is not None else "?")
    body += render_tile("⚡", "CPU-frekvens", f'{live.get("cpu_mhz")} MHz' if live.get("cpu_mhz") is not None else "?")
    body += render_tile("🌡️", "NVMe temperatur", f'{live.get("nvme_temp")}°C' if live.get("nvme_temp") is not None else "?")
    body += render_tile("↕️", "Netværk", f'{live.get("network_kbps")} KiB/s' if live.get("network_kbps") is not None else "?")
    body += render_tile("🖥️", "Chrome", chrome_label, chrome_level)
    body += render_tile("🏷️", "Model", stats["model"])
    ha_power_configured = bool(conf.get("HA_TOKEN") and conf.get("HA_POWER_ENTITY"))
    if ha_power_configured:
        power_val = f'{live.get("ha_power")} W' if live.get("ha_power") is not None else "?"
        body += render_tile("⚡", "Effekt", power_val)
    body += "</div>"

    body += f'<div class="status">{esc(health_detail)}</div>'
    power_chart = (
        '<div class="chart-card"><div class="chart-title">Effekt (Home Assistant) · seneste 60 minutter</div>'
        '<canvas class="telemetry-chart" id="powerChart"></canvas></div>'
        if ha_power_configured else ""
    )
    power_draw = (
        "drawChart('powerChart',rows,[{key:'ha_power',label:'W',color:'#facc15'}]);"
        if ha_power_configured else ""
    )
    body += f"""
<div class="charts">
  <div class="chart-card"><div class="chart-title">CPU, RAM og GPU · seneste 60 minutter</div><canvas class="telemetry-chart" id="usageChart"></canvas></div>
  <div class="chart-card"><div class="chart-title">CPU- og NVMe-temperatur · seneste 60 minutter</div><canvas class="telemetry-chart" id="temperatureChart"></canvas></div>
  <div class="chart-card"><div class="chart-title">CPU-frekvens · seneste 60 minutter</div><canvas class="telemetry-chart" id="frequencyChart"></canvas></div>
  <div class="chart-card"><div class="chart-title">Netværkstrafik · seneste 60 minutter</div><canvas class="telemetry-chart" id="networkChart"></canvas></div>
  {power_chart}
</div>
<script>
function drawChart(id, rows, series, maxValue) {{
  const canvas=document.getElementById(id), ratio=window.devicePixelRatio||1, width=canvas.clientWidth, height=canvas.clientHeight;
  canvas.width=width*ratio; canvas.height=height*ratio; const c=canvas.getContext('2d'); c.scale(ratio,ratio); c.clearRect(0,0,width,height);
  c.strokeStyle='rgba(128,128,128,.22)'; c.lineWidth=1; for(let i=0;i<=4;i++){{const y=8+(height-20)*i/4;c.beginPath();c.moveTo(0,y);c.lineTo(width,y);c.stroke();}}
  const visible=rows.slice(-360); if(visible.length<2)return;
  const values=visible.flatMap(r=>series.map(s=>Number(r[s.key])).filter(Number.isFinite)); const top=maxValue||Math.max(1,...values)*1.12;
  for(const s of series){{c.strokeStyle=s.color;c.lineWidth=2;c.beginPath();let started=false;visible.forEach((r,i)=>{{const v=Number(r[s.key]);if(!Number.isFinite(v))return;const x=i*width/(visible.length-1),y=height-8-Math.min(top,v)*(height-20)/top;if(!started){{c.moveTo(x,y);started=true}}else c.lineTo(x,y)}});c.stroke();}}
  c.font='11px system-ui'; let x=8; for(const s of series){{c.fillStyle=s.color;c.fillText(s.label,x,height-2);x+=c.measureText(s.label).width+16;}}
}}
async function updateTelemetry(){{try{{const r=await fetch('/api/telemetry',{{cache:'no-store'}});if(!r.ok)return;const rows=await r.json();drawChart('usageChart',rows,[{{key:'cpu',label:'CPU',color:'#3b82f6'}},{{key:'ram',label:'RAM',color:'#8b5cf6'}},{{key:'gpu',label:'GPU',color:'#22c55e'}}],100);drawChart('temperatureChart',rows,[{{key:'cpu_temp',label:'CPU °C',color:'#ef4444'}},{{key:'nvme_temp',label:'NVMe °C',color:'#f59e0b'}}],100);drawChart('frequencyChart',rows,[{{key:'cpu_mhz',label:'MHz',color:'#06b6d4'}}]);drawChart('networkChart',rows,[{{key:'network_kbps',label:'KiB/s',color:'#a855f7'}}]);{power_draw}}}catch(_){{}}}}
updateTelemetry();setInterval(updateTelemetry,10000);addEventListener('resize',updateTelemetry);
</script>
"""

    body += PAGE_TAIL
    return body


def render_control(conf, message=None, error=None):
    try:
        subprocess.run([os.path.join(KIOSK_DIR, "chrome-lifecycle.py"), "status"], timeout=4, check=False, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        with open(SMARTDASH_STATUS_PATH, encoding="utf-8") as status_file:
            smartdash = json.load(status_file)
    except (OSError, ValueError):
        smartdash = {}
    profile = current_power_profile()
    has_screenshot = os.path.exists(SCREENSHOT_PATH)
    has_diagnostics = os.path.isdir(DIAGNOSTICS_DIR) and any(name.endswith(".zip") for name in os.listdir(DIAGNOSTICS_DIR))
    try:
        state = json.loads(read_file(WARDEN_STATE_PATH, '{"state":"UNKNOWN"}'))
    except ValueError:
        state = {"state": "UNKNOWN"}
    try:
        self_test = json.loads(read_file(SELF_TEST_PATH, '{}'))
    except ValueError:
        self_test = {}
    try:
        display_result = subprocess.run([os.path.join(KIOSK_DIR, "warden-state.sh"), "status"], capture_output=True, text=True, timeout=5)
        display_status = json.loads(display_result.stdout).get("display", {})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        display_status = {}
    try:
        capabilities = json.loads(read_file(CAPABILITIES_PATH, '{}'))
    except ValueError:
        capabilities = {}
    try:
        profile_script = os.path.join(KIOSK_DIR, "profile-manager.py")
        profiles = json.loads(subprocess.run([profile_script, "list"], capture_output=True, text=True, timeout=3).stdout).get("profiles", [])
        active_profile = subprocess.run([profile_script, "status"], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        profiles, active_profile = [], ""
    try:
        touch_output = subprocess.run(["xinput", "list"], capture_output=True, text=True, timeout=3).stdout
        touch_line = next((line.strip() for line in touch_output.splitlines() if "touch" in line.lower()), "")
        touch_name = re.sub(r".*↳\s*|\s+id=\d+.*", "", touch_line).strip() or "Ikke registreret"
        touch_id = re.search(r"id=(\d+)", touch_line)
        touch_props = subprocess.run(["xinput", "list-props", touch_id.group(1)], capture_output=True, text=True, timeout=3).stdout if touch_id else ""
        matrix = re.search(r"Coordinate Transformation Matrix[^:]*:\s*(.+)", touch_props)
        touch_calibration = matrix.group(1).strip() if matrix else "Standard/ukendt"
    except (OSError, subprocess.TimeoutExpired):
        touch_name = "Ikke registreret"
        touch_calibration = "Ukendt"
    try:
        idle_ms = int(subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=3).stdout.strip())
        last_input = f"{idle_ms // 1000} sek. siden"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        last_input = "Ukendt"
    options = "".join(
        f'<option value="{key}"{" selected" if key == profile else ""}>{label}</option>'
        for key, label in POWER_PROFILES.items()
    )
    body = PAGE_HEAD.format(title_suffix=" — Styring")
    body += f'<div class="header-row"><div><h1>Styring</h1><div class="sub">{esc(conf.get("KIOSK_NAME", "Kiosk"))}</div></div></div>'
    body += render_nav("/control") + render_message(message, error)
    body += f"""
<fieldset><legend>Kiosktilstand og diagnostik</legend>
  <div class="grid"><div class="tile"><span>Tilstandsmaskine</span><strong>{esc(state.get('state', 'UNKNOWN'))}</strong></div><div class="tile"><span>Seneste selvtest</span><strong>{esc(self_test.get('result', '—'))}</strong></div><div class="tile"><span>Wake-tid</span><strong>{esc(str(self_test.get('wake_time_ms', '—')) + (' ms' if self_test.get('wake_time_ms') is not None else ''))}</strong></div></div>
  <p class="status">Selvtesten gennemfører en rigtig OFF→ON-cyklus og kontrollerer backend/DPMS, opløsning, Chrome-side, renderer/layout, screenshot og serviceporte.</p>
  <div class="row"><form method="post" action="/action"><input type="hidden" name="do" value="self_test"><button class="primary" type="submit">🧪 Kør OFF→ON-test</button></form><form method="post" action="/action"><input type="hidden" name="do" value="recover"><button type="submit">🩹 Trinvis recovery</button></form><form method="post" action="/action"><input type="hidden" name="do" value="diagnostics"><button type="submit">📦 Lav sikker diagnostik-ZIP</button></form>{'<a class="nav-btn" href="/diagnostics/latest.zip">⬇ Download seneste ZIP</a>' if has_diagnostics else ''}</div>
</fieldset>
<fieldset><legend>Skærm og touch</legend><div class="grid">
  <div class="tile"><span>Aktiv skærm</span><strong>{esc(display_status.get('output', '—'))}</strong></div>
  <div class="tile"><span>Opløsning</span><strong>{esc(str(display_status.get('width', '—')) + '×' + str(display_status.get('height', '—')))}</strong></div>
  <div class="tile"><span>Refresh rate</span><strong>{esc(str(display_status.get('refresh_hz', '—')) + ' Hz')}</strong></div>
  <div class="tile"><span>Touchscreen</span><strong>{esc(touch_name)}</strong></div>
  <div class="tile"><span>Kalibrering</span><strong>{esc(touch_calibration)}</strong></div>
  <div class="tile"><span>Seneste input</span><strong>{esc(last_input)}</strong></div>
  <div class="tile"><span>Backend</span><strong>{esc(display_status.get('backend', '—'))}</strong></div>
</div></fieldset>
<fieldset><legend>Hardware capabilities</legend><div class="grid">
  <div class="tile"><span>Touch wake</span><strong>{'Understøttet' if capabilities.get('touch',{}).get('guardian') else 'Ikke tilgængelig'}</strong></div>
  <div class="tile"><span>Lysstyrke</span><strong>{esc(capabilities.get('display',{}).get('brightness_backend') or 'Ikke tilgængelig')}</strong></div>
  <div class="tile"><span>Lyssensor</span><strong>{'Understøttet' if capabilities.get('sensors',{}).get('illuminance') else 'Ikke tilgængelig'}</strong></div>
  <div class="tile"><span>Mikrofon</span><strong>{'Understøttet' if capabilities.get('audio',{}).get('microphone') else 'Ikke tilgængelig'}</strong></div>
  <div class="tile"><span>Batteri</span><strong>{'Understøttet' if capabilities.get('sensors',{}).get('battery') else 'Ikke tilgængelig'}</strong></div>
</div><div class="row"><form method="post" action="/action"><input type="hidden" name="do" value="probe_capabilities"><button type="submit">🔎 Kontroller hardware igen</button></form></div></fieldset>
<fieldset><legend>Kioskprofiler</legend>
  <p class="status">Hver profil har sin egen URL og zoom. Warden verifierer den valgte URL og bruger den lokale offline-side, hvis dashboardet ikke kan nås.</p>
  <div class="row">{''.join(f'<form method="post" action="/profile-switch"><input type="hidden" name="name" value="{esc(item.get("name",""))}"><button class="{"primary" if item.get("name")==active_profile else ""}" type="submit">{esc(item.get("name","Profil"))} · {esc(item.get("zoom",100))}%</button></form><form method="post" action="/profile-remove"><input type="hidden" name="name" value="{esc(item.get("name",""))}"><button type="submit" title="Fjern profil">×</button></form>' for item in profiles)}</div>
  <form method="post" action="/profile-add"><label>Profilnavn</label><input type="text" name="name" required maxlength="40"><label>URL</label><input type="text" name="url" required placeholder="https://..."><label>Zoom</label><select name="zoom">{''.join(f'<option value="{z}"{" selected" if z == 100 else ""}>{z}%</option>' for z in (50,75,90,100,110,125,150,175,200))}</select><div class="row"><button type="submit">Tilføj eller opdatér profil</button></div></form>
</fieldset>
<fieldset><legend>Strømprofil</legend>
  <p class="status">Strømbesparelse bruger mindst strøm. Balanceret og Ydelse giver gradvist mere CPU-kraft.</p>
  <form method="post" action="/power-profile"><label>Aktiv profil</label><select name="profile">{options}</select><div class="row"><button class="primary" type="submit">Skift strømprofil</button></div></form>
</fieldset>
<fieldset><legend>Smartdash-forbindelse</legend>
  <p class="status">Pause og genoptagelse af <strong>animationer, livekameraer og rendering virker kun, når kiosken viser HA Smartdash</strong>. Skærmens almindelige tænd/sluk via DPMS virker fortsat med andre dashboards, men Warden kan ikke stoppe deres interne animationer eller mediearbejde. HA Smartdash registreres automatisk via Chromes lokale debug-port og kan også styres fra Home Assistant gennem MQTT-entityen Smartdash Rendering.</p>
  <div class="grid"><div class="tile"><span>Automatisk registrering</span><strong id="smartdashDetected">{'Forbundet' if smartdash.get('supported') else ('Afhængighed mangler' if smartdash.get('error') == 'missing_dependency' else 'Kontakt fejlede' if smartdash.get('error') else 'Ikke registreret')}</strong></div><div class="tile"><span>Tilstand</span><strong id="smartdashState">{esc(smartdash.get('state') or '—')}</strong></div><div class="tile"><span>Build</span><strong id="smartdashBuild">{esc(smartdash.get('release') or smartdash.get('build') or '—')}</strong></div></div>
  {f'<p class="status" id="smartdashErrorDetail">{esc(smartdash.get("error_message"))}</p>' if smartdash.get('error') else '<p class="status" id="smartdashErrorDetail" style="display:none"></p>'}
  <div class="row"><button type="button" id="refreshSmartdash">Kontroller igen</button></div>
</fieldset>
<fieldset><legend>Kiosk og Warden</legend><div class="row">
  <form method="post" action="/action"><input type="hidden" name="do" value="reload"><button type="submit">🔄 Genindlæs side</button></form>
  <form method="post" action="/action"><input type="hidden" name="do" value="restart_chrome"><button type="submit">🔁 Genstart Chrome</button></form>
  <button class="primary" type="button" id="restartWardenManual">🛡️ Genstart Kiosk Warden</button>
  <form method="post" action="/action"><input type="hidden" name="do" value="screenshot"><button type="submit">📷 Tag screenshot</button></form>
  <form method="post" action="/action"><input type="hidden" name="do" value="backup"><button type="submit">🗄️ Backup config</button></form>
</div><div class="countdown" id="manualRestartCountdown"></div></fieldset>
<fieldset><legend>Skærmbillede</legend>
  <p class="status">Seneste billede af den aktive kiosk-skærm. Brug Tag screenshot ovenfor for at opdatere det.</p>
  {f'<img class="shot" src="/screenshot.jpg?_={secrets.token_hex(4)}" alt="Seneste screenshot af kiosk-skærmen">' if has_screenshot else '<div class="status">Der er ikke taget et screenshot endnu.</div>'}
</fieldset>
<fieldset><legend>Maskine</legend><div class="row">
  <form method="post" action="/action" onsubmit="return confirm('Genstarte maskinen nu?');"><input type="hidden" name="do" value="reboot"><button class="danger" type="submit">⟳ Genstart maskine</button></form>
  <form method="post" action="/action" onsubmit="return confirm('Slukke maskinen nu?');"><input type="hidden" name="do" value="shutdown"><button class="danger" type="submit">⏻ Sluk maskine</button></form>
</div></fieldset>
<script>
document.getElementById('refreshSmartdash').addEventListener('click', async () => {{
  const response = await fetch('/api/smartdash-status', {{cache:'no-store'}});
  const data = await response.json();
  const detected = data.supported ? 'Forbundet' : (data.error === 'missing_dependency' ? 'Afhængighed mangler' : (data.error ? 'Kontakt fejlede' : 'Ikke registreret'));
  document.getElementById('smartdashDetected').textContent = detected;
  document.getElementById('smartdashState').textContent = data.state || '—';
  document.getElementById('smartdashBuild').textContent = data.release || data.build || '—';
  const detail = document.getElementById('smartdashErrorDetail');
  if (data.error_message) {{ detail.textContent = data.error_message; detail.style.display = ''; }} else {{ detail.style.display = 'none'; }}
}});
document.getElementById('restartWardenManual').addEventListener('click', event => {{
  let seconds = 5; const button = event.currentTarget; const label = document.getElementById('manualRestartCountdown'); button.disabled = true; label.textContent = `Genstarter om ${{seconds}} sekunder…`;
  const timer = setInterval(async () => {{ seconds -= 1; label.textContent = `Genstarter om ${{seconds}} sekunder…`; if (seconds <= 0) {{ clearInterval(timer); await fetch('/action', {{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'do=restart_warden'}}); label.textContent = 'Kiosk Warden genstarter…'; }} }}, 1000);
}});
</script>"""
    return body + PAGE_TAIL


def render_offline():
    return PAGE_HEAD.format(title_suffix=" — Offline") + """
<div class="narrow"><fieldset><legend>Kiosk dashboard unavailable</legend>
<h1>Kiosk Warden</h1><p>The configured dashboard cannot be reached. Warden is
still running locally and will return automatically when the dashboard is
healthy again.</p><p class="status">Check network, DNS, the dashboard service,
or open Warden from another device for diagnostics.</p></fieldset></div>
<script>setTimeout(()=>location.reload(),30000)</script>""" + PAGE_TAIL


def render_ha_fieldset(conf):
    """Optional 'connect to Home Assistant' section of Indstillinger.

    HA_POWER_ENTITY is always a real <select> populated from HA's own
    entity list once a token is saved - never a free-text field the user
    has to guess an entity_id into.
    """
    ha_url = conf.get("HA_URL", "")
    has_token = bool(conf.get("HA_TOKEN"))
    current_entity = conf.get("HA_POWER_ENTITY", "")

    link = ""
    if ha_url:
        link = (
            f'<div class="sub"><a href="{esc(ha_url.rstrip("/"))}/profile/security" '
            f'target="_blank" rel="noopener">Opret et Long-Lived Access Token i Home Assistant →</a></div>'
        )

    if has_token:
        candidates = ha_client.list_entities(
            ha_url, conf.get("HA_TOKEN", ""), domain="sensor", device_classes=("power", "energy")
        )
        known_ids = {item["entity_id"] for item in candidates}
        if current_entity and current_entity not in known_ids:
            candidates.append({"entity_id": current_entity, "name": current_entity})
        if candidates:
            options = "".join(
                f'<option value="{esc(item["entity_id"])}"'
                f'{" selected" if item["entity_id"] == current_entity else ""}>'
                f'{esc(item["name"])} ({esc(item["entity_id"])})</option>'
                for item in candidates
            )
            entity_field = f'<label>Strøm/energi-måler</label><select name="HA_POWER_ENTITY">{options}</select>'
        else:
            entity_field = '<div class="sub">Ingen strøm- eller energi-målere fundet i Home Assistant.</div>'
    else:
        entity_field = '<div class="sub">Gem og test forbindelsen ovenfor for at vælge måleren.</div>'

    return f"""
<form method="post" action="/save-ha">
  <fieldset>
    <legend>Home Assistant</legend>
    <div class="sub">Valgfrit. Lader Kiosk Warden vise et strøm/energi-tal fra Home Assistant på Oversigt-siden.</div>
    <label>Home Assistant URL</label>
    <input type="text" name="HA_URL" value="{esc(ha_url)}" placeholder="http://homeassistant.local:8123">
    {link}
    <label>Long-Lived Access Token (tomt ved gem = behold nuværende)</label>
    <input type="password" name="HA_TOKEN" placeholder="••••••••">
    {entity_field}
    <div class="row"><button type="submit">Gem og test forbindelse</button></div>
  </fieldset>
</form>
"""


def render_settings(conf, message=None, error=None):
    body = PAGE_HEAD.format(title_suffix=" — Indstillinger")
    body += f"""
<div class="header-row">
  <div>
    <h1>Indstillinger</h1>
    <div class="sub">{esc(conf.get('KIOSK_NAME', 'Kiosk'))}</div>
  </div>
</div>
"""
    body += render_nav("/settings")
    body += render_message(message, error)

    body += '<div class="narrow">'
    body += f"""
<form method="post" action="/save">
  <fieldset>
    <legend>Kiosk &amp; MQTT</legend>
    <label>Navn på kiosken</label>
    <input type="text" name="KIOSK_NAME" value="{esc(conf.get('KIOSK_NAME',''))}" required>
    <label>Kiosk-id (a-z 0-9 _, bruges i MQTT-topics)</label>
    <input type="text" name="KIOSK_ID" value="{esc(conf.get('KIOSK_ID',''))}" required>
    <label>URL kiosken skal vise</label>
    <input type="text" name="KIOSK_URL" value="{esc(conf.get('KIOSK_URL',''))}" required>
    <label>MQTT broker host/IP</label>
    <input type="text" name="MQTT_HOST" value="{esc(conf.get('MQTT_HOST',''))}" required>
    <label>MQTT broker port</label>
    <input type="number" name="MQTT_PORT" value="{esc(conf.get('MQTT_PORT',''))}" required>
    <label>MQTT brugernavn</label>
    <input type="text" name="MQTT_USER" value="{esc(conf.get('MQTT_USER',''))}">
    <label>MQTT password (tomt = behold nuværende)</label>
    <input type="password" name="MQTT_PASS" placeholder="••••••••">
    <label>Stats-interval (sekunder)</label>
    <input type="number" name="STATS_INTERVAL" value="{esc(conf.get('STATS_INTERVAL',''))}" required>
    <label>Web-UI port</label>
    <input type="number" name="KIOSK_WEBUI_PORT" min="1024" max="65535" value="{esc(conf.get('KIOSK_WEBUI_PORT', BIND_PORT))}" required>
    <div class="status">Når porten ændres, genstarter kun Web-UI'en, og browseren viderestilles automatisk.</div>
    <label>VNC port</label><input type="number" name="KIOSK_VNC_PORT" min="1024" max="65535" value="{esc(conf.get('KIOSK_VNC_PORT', '5900'))}" required>
    <label>noVNC port</label><input type="number" name="KIOSK_NOVNC_PORT" min="1024" max="65535" value="{esc(conf.get('KIOSK_NOVNC_PORT', '6080'))}" required>
    <div class="status">Alle tre lokale serviceporte konfliktkontrolleres før de gemmes.</div>
    <label>Skærm-backend</label><select name="KIOSK_SCREEN_BACKEND">{''.join(f'<option value="{item}"{" selected" if conf.get("KIOSK_SCREEN_BACKEND", "auto") == item else ""}>{item}</option>' for item in ('auto','gnome-x11','cinnamon-x11','x11','wayland-wlopm','wayland-kde','raspberry-pi','ddc','cec'))}</select>
    <label><input type="checkbox" name="KIOSK_TOUCH_WAKE" value="true"{' checked' if conf.get('KIOSK_TOUCH_WAKE','true') == 'true' else ''}> Sikker touch-to-wake</label>
    <label><input type="checkbox" name="KIOSK_AUTO_BRIGHTNESS" value="true"{' checked' if conf.get('KIOSK_AUTO_BRIGHTNESS') == 'true' else ''}> Automatisk lysstyrke, når både skærm og lyssensor understøttes</label>
    <label>Minimum lysstyrke (%)</label><input type="number" name="KIOSK_BRIGHTNESS_MIN" min="1" max="100" value="{esc(conf.get('KIOSK_BRIGHTNESS_MIN','15'))}">
    <label>Maksimum lysstyrke (%)</label><input type="number" name="KIOSK_BRIGHTNESS_MAX" min="1" max="100" value="{esc(conf.get('KIOSK_BRIGHTNESS_MAX','100'))}">
    <label>Brugerfladesprog</label>
    <select name="UI_LANGUAGE"><option value="en"{' selected' if conf.get('UI_LANGUAGE', 'en') == 'en' else ''}>English</option><option value="da"{' selected' if conf.get('UI_LANGUAGE') == 'da' else ''}>Dansk</option></select>
    <div class="row"><button class="primary" type="submit">Gem og genstart</button></div>
  </fieldset>
</form>

{render_ha_fieldset(conf)}

<form method="post" action="/change-password">
  <fieldset>
    <legend>Skift administrator-login</legend>
    <label>Brugernavn</label>
    <input type="text" name="username" value="{esc(conf.get('WEBUI_USERNAME', 'admin'))}" required minlength="3" maxlength="40" autocomplete="username">
    <label>Nyt password (min. 8 tegn)</label>
    <input type="password" name="password" required minlength="8">
    <label>Gentag nyt password</label>
    <input type="password" name="password2" required minlength="8">
    <div class="row"><button type="submit">Skift password</button></div>
  </fieldset>
</form>

<form method="post" action="/vnc-password">
  <fieldset>
    <legend>Fjernstyring (VNC) password</legend>
    <div class="sub">Separat fra login på denne side. Klassisk VNC-password — kun de første 8 tegn bruges.</div>
    <label>Nyt VNC password</label>
    <input type="password" name="password" required minlength="4" maxlength="8">
    <label>Gentag nyt VNC password</label>
    <input type="password" name="password2" required minlength="4" maxlength="8">
    <div class="row"><button type="submit">Skift VNC password</button></div>
  </fieldset>
</form>

"""
    body += "</div>"
    body += PAGE_TAIL
    return body


def render_port_change(conf, new_port):
    body = PAGE_HEAD.format(title_suffix=" — Web-UI port")
    body += f"""
<div class="narrow">
  <div class="brand"><img src="/icon.svg" alt=""><span>Kiosk Warden</span></div>
  <fieldset>
    <legend>Web-UI porten er ændret</legend>
    <p>Forbinder til den nye adresse…</p>
    <p class="status"><a id="newWebuiUrl" href="#">Fortsæt manuelt</a></p>
  </fieldset>
</div>
<script>
  const target = `${{location.protocol}}//${{location.hostname}}:{int(new_port)}/settings`;
  document.getElementById('newWebuiUrl').href = target;
  setTimeout(() => location.replace(target), 3500);
</script>
"""
    body += PAGE_TAIL
    return body


def render_vnc(conf):
    body = PAGE_HEAD.format(title_suffix=" — Fjernstyring")
    body += f"""
<div class="header-row">
  <div>
    <h1>Fjernstyring</h1>
    <div class="sub">{esc(conf.get('KIOSK_NAME','Kiosk'))}</div>
  </div>
</div>
"""
    body += render_nav("/vnc")
    body += """
<div class="row">
  <button class="primary" type="button" onclick="document.getElementById('vncframe').requestFullscreen()">Fuld skærm</button>
  <button type="button" onclick="reloadFrame()">Genopfrisk forbindelse</button>
</div>
<div style="margin-top:.8rem; border-radius:14px; overflow:hidden; border:1px solid rgba(128,128,128,.3);">
  <iframe id="vncframe" allowfullscreen
    style="width:100%; height:calc(100vh - 190px); min-height:420px; border:0; display:block; background:#000;"></iframe>
</div>
<div class="status">Kræver VNC-password (separat fra login på denne side) ved forbindelse.</div>
<script>
  function vncUrl() {
    return 'http://' + location.hostname + ':{int(conf.get("KIOSK_NOVNC_PORT", "6080"))}/vnc.html?autoconnect=true&resize=scale&reconnect=true&_=' + Date.now();
  }
  function reloadFrame() {
    document.getElementById('vncframe').src = vncUrl();
  }
  reloadFrame();
</script>
"""
    body += PAGE_TAIL
    return body


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "KioskWarden/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send_html(self, body, status=200):
        body = localize_html(body, read_conf().get("UI_LANGUAGE", "en"))
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status=200):
        language = read_conf().get("UI_LANGUAGE", "en")
        if language == "en" and isinstance(payload, dict):
            payload = {key: localize_html(value, "en") if isinstance(value, str) else value for key, value in payload.items()}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _session_token(self):
        try:
            cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            return cookies[SESSION_COOKIE].value if SESSION_COOKIE in cookies else ""
        except (http.cookies.CookieError, KeyError):
            return ""

    def _session_cookie(self, token, max_age=SESSION_TTL):
        return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"

    def _authenticated(self, conf):
        return bool(conf.get("WEBUI_PASSWORD_HASH")) and valid_session(self._session_token())

    def _login_redirect(self, requested="/"):
        target = requested if requested.startswith("/") and not requested.startswith("//") else "/"
        return self._redirect("/login?" + urllib.parse.urlencode({"next": target}))

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path == "/icon.svg":
            return self._serve_icon()
        if parsed.path == "/offline":
            return self._send_html(render_offline())

        conf = read_conf()
        password_set = bool(conf.get("WEBUI_PASSWORD_HASH"))

        if not password_set:
            if parsed.path in ("/", ""):
                return self._send_html(render_first_run())
            self.send_response(404)
            self.end_headers()
            return

        if parsed.path == "/login":
            if self._authenticated(conf):
                return self._redirect("/")
            next_path = urllib.parse.parse_qs(parsed.query).get("next", ["/"])[0]
            return self._send_html(render_login(conf, next_path))

        if parsed.path == "/logout":
            destroy_session(self._session_token())
            return self._redirect("/login", self._session_cookie("", 0))

        if not self._authenticated(conf):
            return self._login_redirect(self.path)

        if parsed.path == "/screenshot.jpg":
            return self._serve_screenshot()
        if parsed.path == "/diagnostics/latest.zip":
            return self._serve_latest_diagnostics()
        if parsed.path == "/api/warden-status":
            try:
                result = subprocess.run([os.path.join(KIOSK_DIR, "warden-state.sh"), "status"], timeout=5, check=False, capture_output=True, text=True)
                return self._send_json(json.loads(result.stdout) if result.stdout else {"state": "UNKNOWN"})
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return self._send_json({"state": "UNKNOWN"})
        if parsed.path == "/api/update-status":
            return self._send_json(update_status())
        if parsed.path == "/api/telemetry":
            return self._send_json(telemetry_data())
        if parsed.path == "/api/smartdash-status":
            try:
                result = subprocess.run([os.path.join(KIOSK_DIR, "chrome-lifecycle.py"), "status"], timeout=4, check=False, capture_output=True, text=True)
                return self._send_json(json.loads(result.stdout) if result.stdout else {"supported": False})
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return self._send_json({"supported": False})
        if parsed.path == "/vnc":
            return self._send_html(render_vnc(conf))
        if parsed.path == "/control":
            return self._send_html(render_control(conf))
        if parsed.path in ("/updates", "/changelog"):
            return self._send_html(render_updates(conf))
        if parsed.path == "/settings":
            return self._send_html(render_settings(conf))
        if parsed.path in ("/", ""):
            return self._send_html(render_dashboard(conf))
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        conf = read_conf()
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length).decode() if length else ""
        fields = urllib.parse.parse_qs(raw)
        password_set = bool(conf.get("WEBUI_PASSWORD_HASH"))

        if parsed.path == "/set-password" and not password_set:
            username = fields.get("username", [""])[0].strip()
            pw = fields.get("password", [""])[0]
            pw2 = fields.get("password2", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", username):
                return self._send_html(render_first_run(error="Brugernavn skal være 3–40 tegn og kun bruge bogstaver, tal, punktum, bindestreg eller underscore."))
            if len(pw) < 8 or pw != pw2:
                return self._send_html(render_first_run(error="Password skal være mindst 8 tegn og matche i begge felter."))
            conf["WEBUI_USERNAME"] = username
            conf["WEBUI_PASSWORD_HASH"] = hash_password(pw)
            write_conf(conf)
            token = create_session()
            return self._redirect("/", self._session_cookie(token))

        if not password_set:
            self.send_response(404)
            self.end_headers()
            return

        if parsed.path == "/login":
            client_ip = self.client_address[0]
            next_path = fields.get("next", ["/"])[0]
            if login_blocked(client_ip):
                return self._send_html(render_login(conf, next_path, "For mange loginforsøg. Prøv igen om lidt."), status=429)
            username = fields.get("username", [""])[0].strip()
            password = fields.get("password", [""])[0]
            expected_username = conf.get("WEBUI_USERNAME", "admin") or "admin"
            username_ok = hmac.compare_digest(username, expected_username)
            password_ok = verify_password(password, conf.get("WEBUI_PASSWORD_HASH", ""))
            if not username_ok or not password_ok:
                record_login_failure(client_ip)
                return self._send_html(render_login(conf, next_path, "Forkert brugernavn eller password."), status=401)
            clear_login_failures(client_ip)
            token = create_session()
            safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
            return self._redirect(safe_next, self._session_cookie(token))

        if not self._authenticated(conf):
            return self._login_redirect(parsed.path)

        if parsed.path == "/api/update-check":
            try:
                latest = check_latest_version()
                with _update_lock:
                    _update_cache["latest"] = latest
                    _update_cache["checked_at"] = time.time()
                    _update_cache["error"] = None
                return self._send_json(latest)
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 502)

        if parsed.path == "/save":
            err = validate_settings(fields)
            if err:
                return self._send_html(render_settings(conf, error=err))
            previous_conf = dict(conf)
            old_webui_port = int(conf.get("KIOSK_WEBUI_PORT", BIND_PORT))
            for key in ["KIOSK_NAME", "KIOSK_ID", "KIOSK_URL", "MQTT_HOST", "MQTT_USER", "MQTT_PORT", "STATS_INTERVAL", "KIOSK_WEBUI_PORT", "KIOSK_VNC_PORT", "KIOSK_NOVNC_PORT", "KIOSK_SCREEN_BACKEND", "KIOSK_BRIGHTNESS_MIN", "KIOSK_BRIGHTNESS_MAX"]:
                if key in fields:
                    conf[key] = fields[key][0].strip()
            conf["KIOSK_TOUCH_WAKE"] = "true" if fields.get("KIOSK_TOUCH_WAKE", ["false"])[0] == "true" else "false"
            conf["KIOSK_AUTO_BRIGHTNESS"] = "true" if fields.get("KIOSK_AUTO_BRIGHTNESS", ["false"])[0] == "true" else "false"
            conf["UI_LANGUAGE"] = "da" if fields.get("UI_LANGUAGE", ["en"])[0] == "da" else "en"
            pw = fields.get("MQTT_PASS", [""])[0]
            if pw:
                conf["MQTT_PASS"] = pw
            conf["BASE_TOPIC"] = f'home/kiosk/{conf["KIOSK_ID"]}'
            conf["CODEX_REMOTE_TOPIC"] = f'home/codex/{conf["KIOSK_ID"]}/remote_control'
            write_conf(conf)
            new_webui_port = int(conf["KIOSK_WEBUI_PORT"])
            non_port_changed = any(
                conf.get(key, "") != previous_conf.get(key, "")
                for key in CONF_ORDER if key != "KIOSK_WEBUI_PORT"
            )
            if non_port_changed:
                run("systemctl", "--user", "restart", "kiosk-mqtt-stats.service", "kiosk-mqtt-control.service")
                run("systemctl", "--user", "restart", "kiosk-chrome.service", "kiosk-watchdog.service", "kiosk-health.service")
                run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
            if new_webui_port != old_webui_port:
                unit = f"kiosk-webui-port-change-{int(time.time())}"
                result = subprocess.run(
                    ["systemd-run", "--user", "--collect", "--on-active=2s", "--unit", unit,
                     "/usr/bin/systemctl", "--user", "restart", "kiosk-webui.service"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    conf["KIOSK_WEBUI_PORT"] = str(old_webui_port)
                    write_conf(conf)
                    return self._send_html(render_settings(conf, error=result.stderr.strip() or "Kunne ikke genstarte Web-UI."))
                return self._send_html(render_port_change(conf, new_webui_port))
            return self._redirect("/settings")

        if parsed.path == "/save-ha":
            conf["HA_URL"] = fields.get("HA_URL", [""])[0].strip()
            token = fields.get("HA_TOKEN", [""])[0]
            if token:
                conf["HA_TOKEN"] = token
            if "HA_POWER_ENTITY" in fields:
                conf["HA_POWER_ENTITY"] = fields["HA_POWER_ENTITY"][0].strip()
            write_conf(conf)
            if conf.get("HA_URL") and conf.get("HA_TOKEN"):
                ok, msg = ha_client.test_connection(conf["HA_URL"], conf["HA_TOKEN"])
                if ok:
                    return self._send_html(render_settings(conf, message=f"Home Assistant-forbindelse gemt. {msg}"))
                return self._send_html(render_settings(conf, error=msg))
            return self._send_html(render_settings(conf, message="Home Assistant-forbindelse gemt."))

        if parsed.path == "/change-password":
            username = fields.get("username", [""])[0].strip()
            pw = fields.get("password", [""])[0]
            pw2 = fields.get("password2", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", username) or len(pw) < 8 or pw != pw2:
                return self._send_html(render_settings(conf, error="Password skal være mindst 8 tegn og matche i begge felter."))
            conf["WEBUI_USERNAME"] = username
            conf["WEBUI_PASSWORD_HASH"] = hash_password(pw)
            write_conf(conf)
            with _session_lock:
                _sessions.clear()
            token = create_session()
            return self._redirect("/settings", self._session_cookie(token))

        if parsed.path == "/vnc-password":
            pw = fields.get("password", [""])[0]
            pw2 = fields.get("password2", [""])[0]
            if len(pw) < 4 or pw != pw2:
                return self._send_html(render_settings(conf, error="VNC password skal være mindst 4 tegn og matche i begge felter."))
            ok, msg = set_vnc_password(pw)
            if ok:
                return self._send_html(render_settings(conf, message=msg))
            return self._send_html(render_settings(conf, error=msg))

        if parsed.path == "/update":
            channel = fields.get("channel", [read_file(UPDATE_CHANNEL_PATH, "stable")])[0]
            channel = "beta" if channel == "beta" else "stable"
            with open(UPDATE_CHANNEL_PATH, "w", encoding="utf-8") as handle:
                handle.write(channel + "\n")
            ok, msg = start_self_update(channel)
            if ok:
                return self._redirect("/updates?started=1")
            return self._send_html(render_updates(conf, error=msg))

        if parsed.path == "/update-channel":
            channel = "beta" if fields.get("channel", ["stable"])[0] == "beta" else "stable"
            with open(UPDATE_CHANNEL_PATH, "w", encoding="utf-8") as handle:
                handle.write(channel + "\n")
            try:
                latest = check_latest_version()
                with _update_lock:
                    _update_cache["latest"] = latest
                    _update_cache["checked_at"] = time.time()
                    _update_cache["error"] = None
            except Exception as exc:
                return self._send_html(render_updates(conf, error=f"Kanalen blev gemt, men update-tjek fejlede: {exc}"))
            return self._send_html(render_updates(conf, message=f"Opdateringskanal sat til {channel.title()}."))

        if parsed.path == "/power-profile":
            ok, msg = set_power_profile(fields.get("profile", [""])[0])
            if ok:
                run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
                return self._send_html(render_control(conf, message=msg))
            return self._send_html(render_control(conf, error=msg))

        if parsed.path == "/profile-add":
            name = fields.get("name", [""])[0].strip()
            url = fields.get("url", [""])[0].strip()
            zoom = fields.get("zoom", ["100"])[0].strip()
            if not re.fullmatch(r"[A-Za-z0-9 ÆØÅæøå._-]{1,40}", name) or not re.fullmatch(r"https?://[^\s\"'\\]+", url) or not zoom.isdigit() or int(zoom) not in {50,75,90,100,110,125,150,175,200}:
                return self._send_html(render_control(conf, error="Ugyldig profil, URL eller zoom."))
            result = subprocess.run([os.path.join(KIOSK_DIR, "profile-manager.py"), "add", name, url, zoom], timeout=10)
            if result.returncode == 0:
                run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
            return self._send_html(render_control(read_conf(), message="Kioskprofil gemt." if result.returncode == 0 else None, error="Profilen kunne ikke gemmes." if result.returncode else None))

        if parsed.path == "/profile-remove":
            name = fields.get("name", [""])[0]
            result = subprocess.run([os.path.join(KIOSK_DIR, "profile-manager.py"), "remove", name], timeout=10)
            if result.returncode == 0:
                run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
                return self._send_html(render_control(read_conf(), message=f"Profilen {name} er fjernet."))
            return self._send_html(render_control(conf, error="Den sidste profil eller den valgte profil kunne ikke fjernes."))

        if parsed.path == "/profile-switch":
            name = fields.get("name", [""])[0]
            result = subprocess.run([os.path.join(KIOSK_DIR, "profile-manager.py"), "switch", name], timeout=15)
            if result.returncode == 0:
                run("systemctl", "--user", "restart", "kiosk-mqtt-control.service")
                run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
                return self._send_html(render_control(read_conf(), message=f"Skiftet til profilen {name}."))
            return self._send_html(render_control(conf, error="Profilen kunne ikke aktiveres."))

        if parsed.path == "/rollback":
            version = fields.get("version", [""])[0]
            if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                return self._send_html(render_updates(conf, error="Ugyldig rollback-version."))
            script = os.path.join(KIOSK_DIR, "self-update.sh")
            result = subprocess.run(["systemd-run", "--user", "--wait", "--pipe", "--collect",
                                     "--unit", f"kiosk-rollback-{int(time.time())}", script, "rollback", version],
                                    capture_output=True, text=True, timeout=90)
            output = (result.stdout or result.stderr).strip()
            if output.startswith("ROLLEDBACK"):
                return self._send_html(render_updates(conf, message=f"Gendannet til {version}. Siden genstarter…"))
            return self._send_html(render_updates(conf, error=output or "Rollback fejlede."))

        if parsed.path == "/action":
            action = fields.get("do", [""])[0]
            if action == "reload":
                chrome_focus_and_key("F5")
            elif action == "restart_chrome":
                run("systemctl", "--user", "restart", "kiosk-chrome.service")
            elif action == "screenshot":
                run(os.path.join(KIOSK_DIR, "take-screenshot.sh"), timeout=20)
            elif action == "backup":
                run(os.path.join(KIOSK_DIR, "backup-kiosk.sh"), timeout=30)
            elif action == "self_test":
                result = subprocess.run([os.path.join(KIOSK_DIR, "kiosk-self-test.sh")], capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    return self._send_html(render_control(conf, message="OFF→ON-test bestået."))
                return self._send_html(render_control(conf, error="OFF→ON-test fejlede. Se testresultatet og diagnostikpakken."))
            elif action == "recover":
                result = subprocess.run([os.path.join(KIOSK_DIR, "warden-state.sh"), "recover", "WebUI command"], capture_output=True, text=True, timeout=90)
                if result.returncode == 0:
                    return self._send_html(render_control(conf, message="Trinvis recovery blev godkendt."))
                return self._send_html(render_control(conf, error="Recovery kunne ikke godkende kiosken."))
            elif action == "diagnostics":
                result = subprocess.run([os.path.join(KIOSK_DIR, "create-diagnostics.sh")], capture_output=True, text=True, timeout=45)
                if result.returncode == 0:
                    return self._send_html(render_control(conf, message="Diagnostikpakken er klar til download."))
                return self._send_html(render_control(conf, error="Diagnostikpakken kunne ikke oprettes."))
            elif action == "probe_capabilities":
                result = subprocess.run([os.path.join(KIOSK_DIR, "capability-probe.py")], capture_output=True, text=True, timeout=20)
                if result.returncode == 0:
                    run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
                    return self._send_html(render_control(conf, message="Hardware-capabilities er opdateret."))
                return self._send_html(render_control(conf, error="Hardware-proben fejlede."))
            elif action == "restart_warden":
                unit = f"kiosk-warden-restart-{int(time.time())}"
                subprocess.run(["systemd-run", "--user", "--collect", "--on-active=1s", "--unit", unit,
                                "/usr/bin/systemctl", "--user", "restart",
                                "kiosk-mqtt-stats.service", "kiosk-mqtt-control.service",
                                "kiosk-watchdog.service", "kiosk-health.service",
                                "kiosk-vnc.service", "kiosk-novnc.service",
                                "kiosk-capabilities.service", "kiosk-input-guardian.service", "kiosk-adaptive-brightness.service",
                                "kiosk-chrome.service", "kiosk-webui.service"],
                               timeout=10, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif action == "reboot":
                run_bg("sudo", "/sbin/reboot")
            elif action == "shutdown":
                run_bg("sudo", "/sbin/poweroff")
            return self._redirect("/control")

        self.send_response(404)
        self.end_headers()

    def _serve_icon(self):
        if os.path.exists(ICON_PATH):
            with open(ICON_PATH, "rb") as f:
                data = f.read()
        else:
            data = FALLBACK_ICON_SVG
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _serve_screenshot(self):
        if not os.path.exists(SCREENSHOT_PATH):
            self.send_response(404)
            self.end_headers()
            return
        with open(SCREENSHOT_PATH, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_latest_diagnostics(self):
        try:
            candidates = [os.path.join(DIAGNOSTICS_DIR, name) for name in os.listdir(DIAGNOSTICS_DIR)
                          if re.fullmatch(r"kiosk-warden-diagnostics-[0-9-]+\.zip", name)]
            path = max(candidates, key=os.path.getmtime)
            with open(path, "rb") as handle:
                data = handle.read()
        except (OSError, ValueError):
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    os.makedirs(KIOSK_DIR, exist_ok=True)
    threading.Thread(target=background_update_checker, daemon=True).start()
    threading.Thread(target=collect_telemetry, daemon=True).start()
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
