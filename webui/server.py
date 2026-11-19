#!/usr/bin/env python3
"""kiosk-warden web UI: setup + local control panel.

Stdlib-only on purpose (no pip installs needed on the kiosk). Binds to
0.0.0.0:8080 by default so it can be reached from other devices on the LAN
(e.g. a phone) — see README for restricting it to localhost instead.
"""
import base64
import binascii
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
import sys
import threading
import time
import urllib.parse

import ha_client
import ui_assets
from ui_assets import icon

# Sign-in from Kontrolrum is an extra: if the module cannot be loaded, the web UI
# carries on with its normal login and the endpoint answers 404.
try:
    import kontrolrum_sso
except Exception:  # noqa: BLE001 - whatever is wrong with it must stay here
    kontrolrum_sso = None

HOME = os.path.expanduser("~")
KIOSK_DIR = os.path.join(HOME, "kiosk")
CONF_PATH = os.path.join(KIOSK_DIR, "kiosk.conf")
ICON_PATH = os.path.join(KIOSK_DIR, "icon.svg")
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
    "KIOSK_AUTO_BRIGHTNESS", "KIOSK_BRIGHTNESS_MIN", "KIOSK_BRIGHTNESS_MAX", "UI_LANGUAGE", "WEBUI_AUTO_LOGOUT", "WEBUI_USERNAME", "WEBUI_PASSWORD_HASH",
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
    "WEBUI_AUTO_LOGOUT": "true",
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
    "🏠 Status": "🏠 Status", "🎛️ Kiosk": "🎛️ Kiosk", "🖱️ Fjernstyring": "🖱️ Remote Control",
    "📡 Forbindelser": "📡 Connections", "⬇️ Opdateringer": "⬇️ Updates", "⚙️ System": "⚙️ System",
    "Driftsstatus, ressourceforbrug og den aktive kiosks helbred.": "Operating status, resource usage, and health of the active kiosk.",
    "Styr skærm, profiler, hardware og kioskens driftsfunktioner.": "Control the display, profiles, hardware, and kiosk operations.",
    "Åbn en midlertidig fjernsession til kioskens aktuelle skærm.": "Open a temporary remote session to the kiosk's current screen.",
    "Opsæt MQTT og den valgfrie forbindelse til Home Assistant.": "Configure MQTT and the optional Home Assistant connection.",
    "Vælg releasekanal, installer opdateringer eller gendan en tidligere version.": "Choose a release channel, install updates, or restore an earlier version.",
    "Tilpas identitet, lokale porte, skærm, login og strømfunktioner.": "Configure identity, local ports, display, login, and power features.",
    "Aktiv kiosk": "Active kiosk", "Forbindelser": "Connections", "System": "System",
    "Aktiv visning": "Active view", "Ingen profil": "No profile",
    "Kiosktilstand og diagnostik": "Kiosk state and diagnostics", "Tilstandsmaskine": "State machine",
    "Seneste selvtest": "Latest self-test", "Wake-tid": "Wake time",
    "Selvtesten gennemfører en rigtig OFF→ON-cyklus og kontrollerer backend/DPMS, opløsning, Chrome-side, renderer/layout og serviceporte.": "The self-test performs a real OFF→ON cycle and checks the backend/DPMS, resolution, Chrome page, renderer/layout, and service ports.",
    "Kør OFF→ON-test": "Run OFF→ON test", "Trinvis recovery": "Step-by-step recovery", "Lav sikker diagnostik-ZIP": "Create safe diagnostics ZIP", "Download seneste ZIP": "Download latest ZIP",
    "Skærm og touch": "Display and touch", "Aktiv skærm": "Active display", "Opløsning": "Resolution", "Refresh rate": "Refresh rate",
    "Touchscreen": "Touchscreen", "Kalibrering": "Calibration", "Seneste input": "Latest input", "Ikke registreret": "Not detected",
    "Standard/ukendt": "Default/unknown", "Hardware capabilities": "Hardware capabilities", "Touch wake": "Touch wake",
    "Understøttet": "Supported", "Ikke tilgængelig": "Unavailable", "Lysstyrke": "Brightness", "Lyssensor": "Ambient light sensor",
    "Mikrofon": "Microphone", "Batteri": "Battery", "Kontroller hardware igen": "Check hardware again",
    "Touch er ikke registreret": "Touch is not detected", "Touch-enheden er frakoblet": "The touch device is disconnected",
    "evtest mangler": "evtest is missing", "Mangler adgang til touch-enheden": "No access to the touch device", "Klar": "Ready",
    "Kioskprofiler": "Kiosk profiles", "Hver profil har sin egen URL og zoom. Warden verifierer den valgte URL og bruger den lokale offline-side, hvis dashboardet ikke kan nås.": "Each profile has its own URL and zoom. Warden verifies the selected URL and uses the local offline page when the dashboard cannot be reached.",
    "Fjern profil": "Remove profile", "Opdatér profil": "Update profile", "Nyt profilnavn": "New profile name", "Tilføj profil": "Add profile",
    "VNC er slukket. Tryk på Start VNC for at forbinde.": "VNC is off. Press Start VNC to connect.",
    "VNC er aktiv og lukker automatisk, når siden lukkes.": "VNC is active and stops automatically when the page is closed.",
    "Kiosk-id bestemmer topic'et og bruges af MQTT discovery.": "The kiosk ID determines the topic and is used by MQTT discovery.",
    "Base topic (bruges af MQTT og Home Assistant)": "Base topic (used by MQTT and Home Assistant)",
    "Alle tre lokale serviceporte konfliktkontrolleres før de gemmes.": "All three local service ports are checked for conflicts before saving.",
    "Skærm-backend": "Display backend", "Sikker touch-to-wake": "Safe touch-to-wake",
    "Automatisk lysstyrke, når både skærm og lyssensor understøttes": "Automatic brightness when both display and ambient light sensor are supported",
    "Minimum lysstyrke (%)": "Minimum brightness (%)", "Maksimum lysstyrke (%)": "Maximum brightness (%)",
    "Automatisk logud efter 12 timer": "Automatic sign-out after 12 hours", "Til": "On", "Fra": "Off",
    "Skift administrator-login": "Change administrator login", "Gentag nyt password": "Repeat new password",
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
    "CPU, RAM og GPU": "CPU, RAM and GPU",
    "seneste 60 minutter": "last 60 minutes", "CPU- og NVMe-temperatur": "CPU and NVMe temperature", "Netværkstrafik": "Network traffic",
    "Styring": "Control", "Strømprofil": "Power profile", "Strømbesparelse": "Power Saver", "Balanceret": "Balanced", "Ydelse": "Performance",
    "Strømbesparelse bruger mindst strøm. Balanceret og Ydelse giver gradvist mere CPU-kraft.": "Power Saver uses the least energy. Balanced and Performance progressively allow more CPU performance.",
    "Aktiv profil": "Active profile", "Skift strømprofil": "Change power profile", "Kiosk og Warden": "Kiosk and Warden",
    "Genindlæs side": "Reload page", "Genstart Chrome": "Restart Chrome", "Backup config": "Back up config",
    "Maskine": "Machine", "Genstart maskine": "Restart machine", "Sluk maskine": "Shut down machine", "Kiosk Warden genstarter…": "Kiosk Warden is restarting…",
    "Indstillinger": "Settings", "Navn på kiosken": "Kiosk name", "bruges i MQTT-topics": "used in MQTT topics",
    "Web-UI port": "Web UI port", "Porten skal være mellem 1024 og 65535.": "The port must be between 1024 and 65535.",
    "Web-UI porten er allerede i brug.": "The Web UI port is already in use.",
    "Når porten ændres, genstarter kun Web-UI'en, og browseren viderestilles automatisk.": "When the port changes, only the Web UI restarts and the browser is redirected automatically.",
    "Web-UI porten er ændret": "The Web UI port has changed", "Forbinder til den nye adresse…": "Connecting to the new address…",
    "URL kiosken skal vise": "URL displayed by the kiosk", "MQTT brugernavn": "MQTT username",
    "MQTT password (tomt = behold nuværende)": "MQTT password (empty = keep current)", "Stats-interval (sekunder)": "Stats interval (seconds)",
    "Gem og genstart": "Save and restart", "Skift password": "Change password", "Nyt password": "New password",
    "Fjernstyring": "Remote Control", "Fuld skærm": "Full screen", "Genopfrisk forbindelse": "Refresh connection",
    "Automatisk profilskift": "Automatic profile switching", "Aktivér automatisk profilskift": "Enable automatic profile switching",
    "Automatiktype": "Automation mode", "Bestemte tidspunkter": "Specific times", "Skift hvert antal minutter (cycle mode)": "Switch every number of minutes (cycle mode)",
    "Tidsplan (én linje pr. skift: TT:MM=Profilnavn)": "Schedule (one switch per line: HH:MM=Profile name)",
    "Cycle følger profilernes rækkefølge. Tidsplanen gentages hver dag og bruger maskinens lokale tid.": "Cycle follows the profile order. The schedule repeats daily and uses the machine's local time.",
    "Gem automatisk profilskift": "Save automatic profile switching",
    "Profiler i cycle mode": "Profiles in cycle mode", "Vælg mindst to profiler, når cycle mode er aktiv.": "Select at least two profiles when cycle mode is enabled.",
    "Start VNC": "Start VNC", "VNC er startet. Prøv forbindelsen igen.": "VNC has started. Try the connection again.",
    "VNC bruger automatisk dit Kiosk Warden-login. Der skal ikke skrives et separat password.": "VNC uses your Kiosk Warden login automatically. No separate password is required.",
    "VNC-passworden styres automatisk af Kiosk Warden-login og skal ikke indtastes.": "The VNC password is managed automatically from your Kiosk Warden login and does not need to be entered.",
    "Brugerfladesprog": "Interface language", "Dansk": "Danish",
    "MQTT": "MQTT", "Broker": "Broker", "Broker host/IP": "Broker host/IP",
    "Broker port": "Broker port", "Brugernavn": "Username",
    "Password (tomt = behold nuværende)": "Password (empty = keep current)",
    "Gem og genstart MQTT": "Save and restart MQTT",
    "Base topic": "Base topic", "Kiosk-id": "Kiosk ID",
    "MQTT-indstillingerne er gemt og services er genstartet.": "MQTT settings saved and services restarted.",
    "MQTT host må ikke være tom.": "MQTT host cannot be empty.",
    "MQTT porten skal være mellem 1 og 65535.": "MQTT port must be between 1 and 65535.",
    "Stats-interval skal være mindst 1 sekund.": "Stats interval must be at least 1 second.",
    "Password skal være mindst 8 tegn og matche i begge felter.": "Password must be at least 8 characters and match in both fields.",
    "Password skiftet.": "Password changed.",
    "Tilpasset": "Custom", "Ikke installeret (xprintidle)": "Not installed (xprintidle)",
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
    "Base topic må kun indeholde a-z, 0-9, _ og - i hvert topic-led, adskilt af /": "Base topic may only use a-z, 0-9, _ and - in each topic segment, separated by /",
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
    "Test MQTT-forbindelse": "Test MQTT connection", "Test Home Assistant-forbindelse": "Test Home Assistant connection",
    "MQTT-forbindelsen virker.": "The MQTT connection works.", "MQTT-forbindelsen fejlede": "The MQTT connection failed",
    "Home Assistant-forbindelsen virker.": "The Home Assistant connection works.",
    "Sikkerhedskontrollen afviste forespørgslen. Genindlæs siden og prøv igen.": "The security check rejected the request. Reload the page and try again.",
    "Forespørgslen er for stor.": "The request is too large.",
    # Fleetdeck redesign: menu, appearance and new labels. Short words carry their markup so
    # the plain substring replacement cannot hit longer Danish words.
    "Udseende": "Appearance", "</svg>Stil<": "</svg>Style<", ">Stil<": ">Style<", ">Tema<": ">Theme<",
    ">Lyst<": ">Light<", ">Mørkt<": ">Dark<", "Som systemet": "Follow system", ">I siden<": ">Side<", ">I toppen<": ">Top<",
    "– skarp og rolig": "– sharp and calm", "– farver og glas": "– colour and glass",
    "Gemmes i denne browser. Standard er forslag A.": "Saved in this browser. Proposal A is the default.",
    "A · Command, mørk, sidemenu": "A · Command, dark, side menu", "B · Aurora, lys, topmenu": "B · Aurora, light, top menu",
    ">Forslag A<": ">Proposal A<", ">Forslag B<": ">Proposal B<", ">Forslag<": ">Proposal<",
    "Søg efter sider og indstillinger…": "Search pages and settings…", 'aria-label="Søg"': 'aria-label="Search"',
    ">Konto<": ">Account<", 'aria-label="Konto"': 'aria-label="Account"', ">Mere</button>": ">More</button>",
    'aria-label="Faner"': 'aria-label="Tabs"', "</span>Opdatér</a>": "</span>Update</a>", "</span>Fjern</a>": "</span>Remote</a>",
    "Åbn Opdateringer for at installere.": "Open Updates to install.", ">Åbn Opdateringer</a>": ">Open Updates</a>",
    "Du kører en nyere version end den seneste udgivelse på": "You are running a newer version than the latest release on",
    "Der er intet at installere.": "There is nothing to install.", "Nyere end seneste udgivelse": "Newer than latest release",
    "<b>Ny version tilgængelig (": "<b>New version available (", "<div>Du kører ": "<div>You are running ",
    ">Oppetid<": ">Uptime<", "fra Home Assistant": "from Home Assistant", "Chrome kører": "Chrome running", "Chrome stoppet": "Chrome stopped",
    "Skærm og hardware": "Display and hardware", "Strøm og Smartdash": "Power and Smartdash",
    "</svg>Drift</button>": "</svg>Operation</button>", "</svg>Profiler</button>": "</svg>Profiles</button>",
    ">Aktiv</button>": ">Active</button>", ">Skift</button>": ">Switch</button>", "Ingen profiler endnu.": "No profiles yet.",
    "Spørger om bekræftelse før genstart eller sluk.": "Asks for confirmation before restarting or shutting down.",
    "Lokal administration · login kan ændres senere": "Local administration · login can be changed later",
    "Lokal administration · sessionen udløber automatisk": "Local administration · the session expires automatically",
    "Ingen release-noter tilgængelige.": "No release notes available.",
}

KONTROLRUM_SSO_PATH = os.path.join(KIOSK_DIR, "kontrolrum-sso.json")
SESSION_COOKIE = "warden_session"
SESSION_TTL = 12 * 60 * 60
REMEMBER_TTL = 30 * 24 * 60 * 60
MAX_POST_BYTES = 1024 * 1024
_session_lock = threading.Lock()
_login_failures = {}


def localize_html(body, language):
    if language == "da":
        return body.replace('<html lang="en">', '<html lang="da">')
    for source in sorted(ENGLISH_TEXT, key=len, reverse=True):
        body = body.replace(source, ENGLISH_TEXT[source])
    return body


def csrf_token(session_token, conf):
    return hmac.new(_session_key(conf), ("csrf:" + session_token).encode(), hashlib.sha256).hexdigest()


def inject_csrf(body, token):
    hidden = f'<input type="hidden" name="csrf_token" value="{esc(token)}">'
    body = re.sub(r'(<form\b[^>]*\bmethod="post"[^>]*>)', lambda match: match.group(1) + hidden, body, flags=re.I)
    return body.replace("</head>", f'<meta name="warden-csrf" content="{esc(token)}">\n</head>', 1)


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


def _session_key(conf):
    material = "kiosk-warden-session-v1:" + conf.get("WEBUI_PASSWORD_HASH", "")
    return hashlib.sha256(material.encode()).digest()


def create_session(conf, duration=SESSION_TTL):
    expires = int(time.time()) + max(1, int(duration))
    payload = f"{expires}:{secrets.token_urlsafe(24)}".encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(_session_key(conf), encoded.encode(), hashlib.sha256).digest()
    signed = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded}.{signed}"


def _create_kontrolrum_sso():
    if kontrolrum_sso is None:
        return None
    try:
        return kontrolrum_sso.KontrolrumSso(KONTROLRUM_SSO_PATH, "kioskwarden")
    except Exception:  # noqa: BLE001 - never stop the web UI for this
        return None


SSO = _create_kontrolrum_sso()


def _kontrolrum_session_key(conf):
    # A key of its own: a version without this code cannot accept these sessions
    # as ordinary ones, which would drop the binding to Kontrolrum's address.
    material = "kiosk-warden-kontrolrum-session-v1:" + conf.get("WEBUI_PASSWORD_HASH", "")
    return hashlib.sha256(material.encode()).digest()


def _kontrolrum_signature(conf, encoded):
    digest = hmac.new(_kontrolrum_session_key(conf), encoded.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def create_kontrolrum_session(conf, binding, user, duration=SESSION_TTL):
    expires = int(time.time()) + max(1, int(duration))
    claims = json.dumps({"p": binding["p"], "k": binding["k"], "u": user}, separators=(",", ":"))
    payload = f"{expires}:{secrets.token_urlsafe(24)}:{claims}".encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{encoded}.{_kontrolrum_signature(conf, encoded)}"


def valid_kontrolrum_session(token, conf, peer):
    """A session from Kontrolrum: signed, unexpired, and used from Kontrolrum's
    own address with the current key by a user who is still ticked."""
    if SSO is None or not peer:
        return False
    try:
        encoded, supplied = token.split(".", 1)
        if not hmac.compare_digest(supplied.encode(), _kontrolrum_signature(conf, encoded).encode()):
            return False
        padded = encoded + "=" * (-len(encoded) % 4)
        expires, _, claims = base64.urlsafe_b64decode(padded).decode().split(":", 2)
        claims = json.loads(claims)
        if int(expires) <= int(time.time()) or claims.get("u") != (conf.get("WEBUI_USERNAME") or "admin"):
            return False
        return SSO.session_problem({"p": claims.get("p"), "k": claims.get("k")}, peer, claims.get("u")) == ""
    except Exception:  # noqa: BLE001 - a fault here refuses the session, nothing more
        return False


def valid_session(token, conf, peer=None):
    if not token or "." not in token or not conf.get("WEBUI_PASSWORD_HASH"):
        return False
    encoded, supplied_signature = token.split(".", 1)
    expected = base64.urlsafe_b64encode(
        hmac.new(_session_key(conf), encoded.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    if not hmac.compare_digest(supplied_signature.encode(), expected.encode()):
        return valid_kontrolrum_session(token, conf, peer)
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        expires = int(base64.urlsafe_b64decode(padded).decode().split(":", 1)[0])
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    return expires > int(time.time())


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


def vnc_password_from_conf(conf):
    stored = conf.get("WEBUI_PASSWORD_HASH", "")
    if not stored:
        return ""
    password = stored.split(":", 1)[1] if ":" in stored else stored
    return password[:8]


VNC_PAGE_IDLE_STOP = 5.0
_vnc_last_seen = 0.0
_vnc_watchdog_lock = threading.Lock()


def vnc_is_active():
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet",
             "kiosk-vnc.service", "kiosk-novnc.service"],
            capture_output=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def vnc_is_ready():
    conf = read_conf()
    for key in ("KIOSK_VNC_PORT", "KIOSK_NOVNC_PORT"):
        try:
            with socket.create_connection(("127.0.0.1", int(conf.get(key, ""))), timeout=0.2):
                pass
        except (OSError, ValueError):
            return False
    return True


def mark_vnc_activity():
    global _vnc_last_seen
    with _vnc_watchdog_lock:
        _vnc_last_seen = time.monotonic()


def stop_vnc_services():
    global _vnc_last_seen
    run("systemctl", "--user", "stop", "kiosk-novnc.service", "kiosk-vnc.service")
    run("systemctl", "--user", "reset-failed", "kiosk-novnc.service", "kiosk-vnc.service")
    with _vnc_watchdog_lock:
        _vnc_last_seen = 0.0


def vnc_page_watchdog():
    while True:
        time.sleep(1)
        if not vnc_is_active():
            continue
        with _vnc_watchdog_lock:
            last_seen = _vnc_last_seen
        if not last_seen or time.monotonic() - last_seen > VNC_PAGE_IDLE_STOP:
            stop_vnc_services()


threading.Thread(target=vnc_page_watchdog, name="vnc-page-watchdog", daemon=True).start()


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


def test_mqtt_connection(conf):
    command = [
        "mosquitto_pub", "-h", conf.get("MQTT_HOST", ""),
        "-p", str(conf.get("MQTT_PORT", "1883")),
        "-t", f'{conf.get("BASE_TOPIC", "home/kiosk/kiosk")}/diagnostics/connection_test',
        "-m", json.dumps({"source": "kiosk-warden", "timestamp": int(time.time())}),
    ]
    if conf.get("MQTT_USER"):
        command.extend(["-u", conf["MQTT_USER"]])
    if conf.get("MQTT_PASS"):
        command.extend(["-P", conf["MQTT_PASS"]])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


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


def render_tile(icon_name, label, value, level="neutral", bar=None, sub=""):
    """Fleetdeck KPI tile: dimmed icon + label, the value, optional mini bar (percent) and sub text."""
    value_cls = " err" if level == "err" else (" warn" if level == "warn" else "")
    bar_html = ""
    if bar is not None:
        width = max(0, min(100, float(bar)))
        bar_html = f'<div class="fd-minibar"><i class="bar-{level}" style="width:{width:g}%"></i></div>'
    sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
    return (
        f'<div class="paper kpi tile-{level}">'
        f'<div class="lbl">{icon(icon_name)}{esc(label)}</div>'
        f'<div class="val{value_cls}">{esc(value)}</div>{bar_html}{sub_html}</div>'
    )


def render_kv(icon_name, label, value_html):
    return f'<div><div class="k">{icon(icon_name)}{esc(label)}</div><div class="v">{value_html}</div></div>'


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
    base_topic = fields.get("BASE_TOPIC", [""])[0].strip()
    webui_port = fields.get("KIOSK_WEBUI_PORT", [str(BIND_PORT)])[0].strip()
    vnc_port = fields.get("KIOSK_VNC_PORT", ["5900"])[0].strip()
    novnc_port = fields.get("KIOSK_NOVNC_PORT", ["6080"])[0].strip()
    backend = fields.get("KIOSK_SCREEN_BACKEND", ["auto"])[0].strip()
    brightness_min = fields.get("KIOSK_BRIGHTNESS_MIN", ["15"])[0].strip()
    brightness_max = fields.get("KIOSK_BRIGHTNESS_MAX", ["100"])[0].strip()
    if not re.fullmatch(r"[a-z0-9_]+", kiosk_id):
        return "Kiosk-id må kun indeholde a-z, 0-9 og _."
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", base_topic):
        return "Base topic må kun indeholde a-z, 0-9, _ og - i hvert topic-led, adskilt af /"
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


ASSET_VERSION = hashlib.sha256((ui_assets.APP_CSS + ui_assets.APP_JS).encode("utf-8")).hexdigest()[:12]
STATIC_ASSETS = {
    "/static/app.css": ("text/css; charset=utf-8", ui_assets.APP_CSS.encode("utf-8")),
    "/static/app.js": ("text/javascript; charset=utf-8", ui_assets.APP_JS.encode("utf-8")),
    "/static/inter.woff2": ("font/woff2", ui_assets.INTER_WOFF2),
}
# Kiosk Warden's mark: a screen with a check, white on the Fleetdeck logo gradient.
LOGO_PATHS = '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="M9.5 10l2 2 3.5-3.5"/>'


def render_logo(size=30, cls=""):
    inner = round(size * 0.62)
    return (f'<span class="fd-logo {cls}" style="width:{size}px;height:{size}px">'
            f'<svg viewBox="0 0 24 24" width="{inner}" height="{inner}">{LOGO_PATHS}</svg></span>')


# Appearance (Fleetdeck's "Udseende") is stored in this browser's localStorage. Standard is
# forslag A: Command, dark, side menu. The tiny head script applies it before the first paint.
PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<script>(function(){{var d=document.documentElement,g=function(k,v){{try{{return localStorage.getItem(k)||v}}catch(e){{return v}}}},t=g('kw-theme','dark');if(t==='auto')t=window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';d.setAttribute('data-skin',g('kw-skin','command'));d.setAttribute('data-theme',t);d.setAttribute('data-nav',g('kw-nav','side'));}})();</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b0b0d">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="apple-touch-icon" href="/icon.svg">
<link rel="preload" href="/static/inter.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/static/app.css?v=@@ASSET@@">
<script src="/static/app.js?v=@@ASSET@@" defer></script>
<title>Kiosk Warden{title_suffix}</title>
</head>
<body>
<main class="fd-main">
""".replace("@@ASSET@@", ASSET_VERSION)

PAGE_TAIL = "</main></body></html>"


def render_message(message, error):
    out = ""
    if error:
        out += f'<div class="msg error" role="alert">{icon("alert-triangle")}<div>{esc(error)}</div></div>'
    if message:
        out += f'<div class="msg ok" role="status">{icon("circle-check")}<div>{esc(message)}</div></div>'
    return out


def render_first_run(message=None, error=None):
    body = PAGE_HEAD.format(title_suffix=" — Opsætning")
    body += '<div class="login-shell"><section class="login-card">'
    body += f'{render_logo(56, "login-mark")}<div class="login-product">Kiosk Warden</div>'
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
    body += "</section></div>"
    body += PAGE_TAIL
    return body


def render_login(conf, next_path="/", error=None):
    safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    body = PAGE_HEAD.format(title_suffix=" — Log ind")
    body += f"""
<div class="login-shell">
  <section class="login-card">
    {render_logo(56, "login-mark")}
    <div class="login-product">Kiosk Warden</div>
    <h1>Log ind</h1>
    <p class="sub">{esc(conf.get('KIOSK_NAME', 'Kiosk'))}</p>
    {render_message(None, error)}
    <form method="post" action="/login" onkeydown="if (event.key === 'Enter' && event.target.tagName !== 'BUTTON') {{ event.preventDefault(); this.requestSubmit(); }}">
      <input type="hidden" name="next" value="{esc(safe_next)}">
      <label>Brugernavn</label>
      <input type="text" name="username" required autofocus autocomplete="username">
      <label>Password</label>
      <input type="password" name="password" required autocomplete="current-password">
      <label><input type="checkbox" name="remember" value="true" checked> Husk mig i 30 dage</label>
      <button class="primary login-button" type="submit">Fortsæt til Kiosk Warden</button>
    </form>
    <p class="login-note">Lokal administration · sessionen udløber automatisk</p>
  </section>
</div>
"""
    return body + PAGE_TAIL


# Menu (Fleetdeck AppShell): main pages, then the "Opsætning" group. Each entry:
# (path, label, icon, short label for the mobile tab bar, search keywords).
NAV_MAIN = [
    ("/", "Status", "layout-dashboard", "Status", "oversigt cpu ram disk temperatur telemetri"),
    ("/control", "Kiosk", "device-tv", "Kiosk", "skærm touch profiler strømprofil smartdash selvtest diagnostik genstart sluk"),
    ("/vnc", "Fjernstyring", "pointer", "Fjern", "vnc fjernskrivebord skærm"),
]
NAV_GROUPS = [
    ("Opsætning", [
        ("/mqtt", "Forbindelser", "plug", "Forbindelser", "mqtt broker home assistant token"),
        ("/updates", "Opdateringer", "download", "Opdatér", "version kanal beta stable changelog gendan"),
        ("/settings", "System", "settings", "System", "navn port sprog login password lysstyrke backend udseende"),
    ]),
]
TABBAR = ("/", "/control", "/vnc", "/updates")


def _nav_items():
    return NAV_MAIN + [item for _, items in NAV_GROUPS for item in items]


def _look_menu_items():
    """Fleetdeck's LookMenu: style, theme and menu position, saved in this browser."""
    def item(key, value, label, note="", left=""):
        note_html = f' <span class="note">{note}</span>' if note else ""
        left_html = icon(left) if left else ""
        return (f'<button type="button" data-look="{key}" data-value="{value}">{left_html}'
                f'<span>{label}{note_html}</span>{icon("check", "chk off")}</button>')
    return (
        '<div class="lbl">Stil</div>'
        + item("skin", "command", "Command", "– skarp og rolig")
        + item("skin", "aurora", "Aurora", "– farver og glas")
        + '<hr><div class="lbl">Tema</div>'
        + item("theme", "light", "Lyst", left="sun")
        + item("theme", "dark", "Mørkt", left="moon")
        + item("theme", "auto", "Som systemet", left="sun-moon")
        + '<hr><div class="lbl">Menu</div>'
        + item("nav", "side", "I siden", left="layout-sidebar")
        + item("nav", "top", "I toppen", left="layout-navbar")
    )


def render_look_panel():
    """Fleetdeck's LookPanel (Udseende) with the two design proposals as shortcuts."""
    def seg(key, options):
        buttons = "".join(f'<button type="button" data-look="{key}" data-value="{value}">{label}</button>' for value, label in options)
        return f'<div class="seg">{buttons}</div>'
    return f"""
<fieldset id="udseende">
  <legend>Udseende</legend>
  <p class="status">Gemmes i denne browser. Standard er forslag A.</p>
  <div class="look-row"><span>Forslag</span>{seg("preset", [("a", "A · Command, mørk, sidemenu"), ("b", "B · Aurora, lys, topmenu")])}</div>
  <div class="look-row"><span>Menu</span>{seg("nav", [("side", "I siden"), ("top", "I toppen")])}</div>
  <div class="look-row"><span>Stil</span>{seg("skin", [("command", "Command"), ("aurora", "Aurora")])}</div>
  <div class="look-row"><span>Tema</span>{seg("theme", [("light", "Lyst"), ("dark", "Mørkt"), ("auto", "Som systemet")])}</div>
</fieldset>
"""


def _header_status():
    """Health of the active kiosk for the top bar (same wording as before on Status)."""
    state = read_file(os.path.join(KIOSK_DIR, "health_state"), "?")
    tone = "ok" if state == "ON" else ("bad" if state == "OFF" else "warn")
    label = {"ON": "Kører fint", "OFF": "Fejl"}.get(state, state if state not in ("", "?") else "Ukendt")
    return tone, label


def _update_available():
    latest = get_cached_latest_version()
    latest_version = latest.get("latest_version") if isinstance(latest, dict) else None
    return bool(latest_version and version_newer(latest_version, current_version()))


def render_nav(active, conf=None):
    """Fleetdeck shell: top bar, side menu or top menu, mobile tab bar and the "Mere" sheet."""
    conf = read_conf() if conf is None else conf
    items = _nav_items()
    current = next((item for item in items if item[0] == active), items[0])
    updates = 1 if _update_available() else 0

    def count(path, tag="span"):
        if path == "/updates" and updates:
            return '<span class="fd-count">1</span>' if tag == "span" else "<b>1</b>"
        return ""

    def nav_link(item):
        path, label, ico, _, _ = item
        on = " data-active" if path == active else ""
        return f'<a class="fd-nav" href="{path}"{on}>{icon(ico)}<span>{esc(label)}</span>{count(path)}</a>'

    side = (
        '<nav class="fd-navbar" aria-label="Menu"><div class="fd-brandrow"><a class="fd-brand" href="/" style="font-size:17px">'
        + render_logo(30) + '<span>Kiosk Warden</span></a></div><div class="grow">'
        + "".join(nav_link(item) for item in NAV_MAIN)
        + "".join(f'<div class="fd-group">{esc(group)}</div>' + "".join(nav_link(i) for i in group_items) for group, group_items in NAV_GROUPS)
        + f'</div><div class="fd-foot">Kiosk Warden {esc(current_version())}</div></nav>'
    )

    top_parts = []
    for path, label, _, _, _ in NAV_MAIN:
        on = " data-active" if path == active else ""
        top_parts.append(f'<a class="fd-top" href="{path}"{on}>{esc(label)}{count(path)}</a>')
    for group, group_items in NAV_GROUPS:
        on = " data-active" if any(i[0] == active for i in group_items) else ""
        drop = "".join(
            f'<a href="{p}"{" data-active" if p == active else ""}>{icon(ico)}<span>{esc(lbl)}</span>'
            + ('<span class="badge b-blue" style="margin-left:auto">1</span>' if p == "/updates" and updates else "") + "</a>"
            for p, lbl, ico, _, _ in group_items
        )
        top_parts.append(
            f'<span class="fd-menu"><a class="fd-top" role="button" data-menu-toggle aria-expanded="false"{on}>{esc(group)}{count("/updates") if any(i[0] == "/updates" for i in group_items) else ""} {icon("chevron-down")}</a>'
            f'<div class="fd-drop">{drop}</div></span>'
        )
    top = '<div class="fd-topnav only-desktop">' + "".join(top_parts) + "</div>"

    search_links = "".join(
        f'<a href="{p}" data-keywords="{esc(keys)}">{icon(ico)}<span>{esc(lbl)}</span></a>' for p, lbl, ico, _, keys in items
    ) + f'<a href="/settings#udseende" data-keywords="tema mørkt lyst command aurora menu">{icon("palette")}<span>Udseende</span></a>'
    search = (
        f'<label class="fd-search only-desktop top-hide">{icon("search")}'
        f'<input id="fdSearch" type="search" autocomplete="off" placeholder="Søg efter sider og indstillinger…" aria-label="Søg">'
        f'<kbd>Ctrl K</kbd><div class="fd-drop" id="fdSearchResults" hidden>{search_links}</div></label>'
    )

    tone, health = _header_status()
    username = conf.get("WEBUI_USERNAME", "admin") or "admin"
    initials = esc(username[:2].upper())
    header = (
        '<header class="fd-header">'
        f'<a class="only-mobile" href="/" aria-label="Kiosk Warden">{render_logo(26)}</a>'
        f'<a class="fd-brand only-desktop top-only" href="/" style="margin-right:8px">{render_logo(26)}<span>Kiosk Warden</span></a>'
        + top + search
        + f'<span class="fd-mtitle only-mobile">{esc(current[1])}</span><div class="spacer"></div>'
        f'<span class="ctx only-desktop" title="Aktiv kiosk">{icon("device-desktop")}<span><span class="dim">Aktiv kiosk:</span> {esc(conf.get("KIOSK_NAME", "Kiosk"))}</span></span>'
        f'<span class="fd-activity {tone}"><span class="fd-dot c-{tone}"></span><span>{esc(health)}</span></span>'
        '<span class="fd-menu end only-desktop"><button class="fd-icon-btn" type="button" data-menu-toggle aria-label="Udseende" aria-expanded="false">'
        f'<span data-theme-icon="dark">{icon("moon")}</span><span data-theme-icon="light" hidden>{icon("sun")}</span></button>'
        f'<div class="fd-drop" style="width:240px">{_look_menu_items()}</div></span>'
        f'<span class="fd-menu end"><button class="fd-avatar" type="button" data-menu-toggle aria-label="Konto" aria-expanded="false">{initials}</button>'
        f'<div class="fd-drop"><div class="who"><b>{esc(username)}</b><span class="dim">Administrator</span></div><hr>'
        f'<a href="/settings#udseende">{icon("palette")}<span>Udseende</span></a><a href="/settings">{icon("user")}<span>Skift administrator-login</span></a><hr>'
        f'<a class="danger" href="/logout">{icon("logout")}<span>Log ud</span></a></div></span>'
        '</header>'
    )

    tabbar = ['<nav class="fd-tabbar" aria-label="Faner">']
    for path in TABBAR:
        item = next(i for i in items if i[0] == path)
        on = " data-active data-current" if path == active else ""
        tabbar.append(f'<a href="{path}"{on}><span>{icon(item[2])}{count(path, "b")}</span>{esc(item[3])}</a>')
    tabbar.append(f'<button type="button" data-sheet-toggle{" data-active" if active not in TABBAR else ""}><span>{icon("dots")}</span>Mere</button></nav>')

    rest = [i for i in NAV_MAIN if i[0] not in TABBAR]
    sheet = '<div class="fd-sheet">' + "".join(nav_link(i) for i in rest)
    for group, group_items in NAV_GROUPS:
        visible = [i for i in group_items if i[0] not in TABBAR]
        if visible:
            sheet += f'<div class="fd-group">{esc(group)}</div>' + "".join(nav_link(i) for i in visible)
    sheet += (
        '<div class="fd-group">Udseende</div><div class="fd-look">'
        + render_look_panel_compact()
        + '</div><div class="fd-group">Konto</div>'
        f'<a class="fd-nav" href="/settings">{icon("user")}<span>Skift administrator-login</span></a>'
        f'<a class="fd-nav" href="/logout" style="color:var(--fd-bad)">{icon("logout")}<span>Log ud</span></a>'
        f'<div class="fd-foot">Kiosk Warden {esc(current_version())}</div></div>'
    )
    return header + side + sheet + "".join(tabbar)


def render_look_panel_compact():
    def seg(key, options):
        return '<div class="seg">' + "".join(f'<button type="button" data-look="{key}" data-value="{v}">{l}</button>' for v, l in options) + "</div>"
    return (seg("preset", [("a", "Forslag A"), ("b", "Forslag B")])
            + seg("skin", [("command", "Command"), ("aurora", "Aurora")])
            + seg("theme", [("light", "Lyst"), ("dark", "Mørkt"), ("auto", "Som systemet")]))


def render_zoom_options(selected=100):
    try:
        selected = int(selected)
    except (TypeError, ValueError):
        selected = 100
    return "".join(
        f'<option value="{zoom}"{" selected" if zoom == selected else ""}>{zoom}%</option>'
        for zoom in (50, 75, 90, 100, 110, 125, 150, 175, 200)
    )


def touch_guardian_label(capabilities):
    touch = capabilities.get("touch", {})
    reason = touch.get("guardian_reason")
    if touch.get("guardian"):
        return "Klar"
    return {
        "touch_not_detected": "Touch er ikke registreret",
        "event_device_missing": "Touch-enheden er frakoblet",
        "evtest_missing": "evtest mangler",
        "permission_denied": "Mangler adgang til touch-enheden",
    }.get(reason, "Ikke tilgængelig")


def calibration_label(raw_matrix):
    try:
        values = [float(value.strip()) for value in raw_matrix.split(",")]
    except (AttributeError, ValueError):
        return "Standard/ukendt"
    identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    if len(values) == 9 and all(abs(value - expected) < 0.000001 for value, expected in zip(values, identity)):
        return "Standard"
    return "Tilpasset"


def render_page_header(title, conf, description, aside=""):
    # Fleetdeck page head: Title order 2 + dimmed sub. The active kiosk is shown in the top bar.
    aside_html = f'<div class="aside">{aside}</div>' if aside else ""
    return f"""
<div class="fd-head">
  <div>
    <h1 class="fd-title">{esc(title)}</h1>
    <div class="fd-sub">{esc(description)}</div>
  </div>
  {aside_html}
</div>
"""


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
    # Installed build is newer than the newest release on this channel (e.g. a build that was never released).
    ahead = latest_version != "ukendt" and version_newer(installed, latest_version)
    body = PAGE_HEAD.format(title_suffix=" — Opdateringer")
    body += render_page_header(
        "Opdateringer", conf,
        "Vælg releasekanal, installer opdateringer eller gendan en tidligere version.",
        f'<span class="pill {"warn" if update_ready else ("info" if ahead else "ok")}">{"Ny version klar" if update_ready else ("Nyere end seneste udgivelse" if ahead else "Opdateret")}</span>',
    )
    body += render_nav("/updates", conf)
    body += render_message(message, error)
    body += f"""
<div class="version-grid">
  <div class="version-card"><span>Installeret</span><strong>v{esc(installed)}</strong></div>
  <div class="version-card"><span>Seneste på {esc(channel.title())}</span><strong>v{esc(latest_version)}</strong></div>
</div>
{f'<div class="msg ok" style="font-weight:400">{icon("info-circle")}<div>Du kører en nyere version end den seneste udgivelse på {esc(channel.title())}. Der er intet at installere.</div></div>' if ahead else ''}
<fieldset>
  <legend>Release-kanal og installation</legend>
  <form method="post" action="/update">
    <label>Opdateringskanal</label>
    <select name="channel"><option value="stable"{' selected' if channel == 'stable' else ''}>Stable</option><option value="beta"{' selected' if channel == 'beta' else ''}>Beta</option></select>
    <div class="row"><button type="button" id="checkUpdates">{icon("refresh")}Tjek for updates</button><button type="submit" formaction="/update-channel">{icon("device-floppy")}Gem kanal</button><button class="accent" type="submit" id="installUpdate"{' disabled' if not update_ready else ''}>{icon("download")}Installer v{esc(latest_version)}</button></div>
  </form>
  <div class="progress-shell" id="updateProgress"><div class="progress-track"><div class="progress-fill" id="updateProgressFill"></div></div><div class="progress-meta"><span id="updateProgressText">Forbereder…</span><strong id="updateProgressPercent">0%</strong></div></div>
  <div class="restart-choice" id="restartChoice"><strong>Opdateringen er installeret.</strong><p>Vælg hvad der skal genstartes, eller fortsæt uden genstart.</p><div class="row"><button class="primary" type="button" id="restartWarden">Genstart Kiosk Warden</button><button type="button" id="restartMachine">Genstart maskinen</button><button type="button" id="restartLater">Senere</button></div><div class="countdown" id="restartCountdown"></div></div>
  <div class="release-notes changelog"><strong>Seneste release{' · Beta' if prerelease else ''}</strong>{render_markdown_lite(release_summary)}</div>
  {f'<a class="btn subtle" href="{esc(release_url)}" target="_blank" rel="noreferrer">{icon("external-link")}Se hele releasen på GitHub</a>' if release_url else ''}
</fieldset>
<fieldset>
  <legend>Gendan tidligere version</legend>
  <form method="post" action="/rollback">
    <label>Lokal snapshot</label>
    <select name="version" {'disabled' if not versions else ''}>{rollback_options or '<option>Ingen snapshots endnu</option>'}</select>
    <div class="row"><button type="submit" {'disabled' if not versions else ''} onclick="return confirm('Gendan den valgte version?');">{icon("arrow-back-up")}Gendan valgt version</button></div>
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
  try { const response = await fetch('/api/update-check', {method:'POST',headers:{'X-Warden-CSRF':document.querySelector('meta[name="warden-csrf"]').content}}); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Update-tjek fejlede'); location.reload(); }
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
  const timer = setInterval(async () => { seconds -= 1; label.textContent = `Genstarter om ${seconds} sekunder…`; if (seconds <= 0) { clearInterval(timer); await fetch('/action', {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','X-Warden-CSRF':document.querySelector('meta[name="warden-csrf"]').content},body:'do=' + encodeURIComponent(action)}); } }, 1000);
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

    body = PAGE_HEAD.format(title_suffix=" — Status")
    body += render_page_header("Status", conf, "Driftsstatus, ressourceforbrug og den aktive kiosks helbred.")
    body += render_nav("/", conf)

    latest = get_cached_latest_version()
    current = current_version()
    latest_version = latest.get("latest_version") if isinstance(latest, dict) else None
    body += '<div class="stack">'
    if latest_version and version_newer(latest_version, current):
        body += f"""
<div class="alert">{icon("bell")}<div style="flex:1"><b>Ny version tilgængelig ({esc(latest_version)})</b><div>Du kører {esc(current)}. Åbn Opdateringer for at installere.</div></div><a class="btn sm light" href="/updates">Åbn Opdateringer</a></div>
"""

    body += render_message(message, error)

    chrome_label = "Kører" if stats["chrome_running"] else "Stoppet"
    temp_val = f'{stats["cpu_temp"]}°C' if stats["cpu_temp"] is not None else "?"
    ram_val = f'{stats["ram_percent"]}%' if stats["ram_percent"] is not None else "?"
    disk_val = f'{stats["disk_percent"]}%' if stats["disk_percent"] is not None else "?"
    cpu_val = f'{live.get("cpu")}%' if live.get("cpu") is not None else stats["loadavg"].split(" / ")[0]
    healthy = health_state == "ON" and stats["chrome_running"]
    hero_value = "Kører" if healthy else ("Fejl" if health_state == "OFF" or not stats["chrome_running"] else (health_state if health_state not in ("", "?") else "Ukendt"))
    hero_sub = f'Chrome {chrome_label.lower()} · {health_state if health_state not in ("", "?") else "ukendt"}'
    spark_rows = [row for row in history[-12:] if isinstance(row, dict)]
    spark = "".join(f'<b style="height:{max(8, min(100, int(row.get("cpu") or 0)))}%"></b>' for row in spark_rows) if spark_rows else ""

    body += '<div class="kpis">'
    body += (f'<div class="paper kpi fd-kpi-hero"><div class="lbl">{icon("device-tv")}Kiosk</div><div class="val">{esc(hero_value)}</div>'
             f'<div class="sub">{esc(hero_sub)}</div>' + (f'<div class="fd-spark" title="CPU">{spark}</div>' if spark else "") + '</div>')
    body += render_tile("cpu", "CPU", cpu_val, level_for(live.get("cpu"), 80, 95), live.get("cpu"))
    body += render_tile("box", "RAM", ram_val, level_for(stats["ram_percent"], 70, 90), stats["ram_percent"])
    body += render_tile("package", "Disk", disk_val, level_for(stats["disk_percent"], 80, 93), stats["disk_percent"])
    body += render_tile("temperature", "Temperatur", temp_val, level_for(stats["cpu_temp"], 65, 80), stats["cpu_temp"])
    ha_power_configured = bool(conf.get("HA_TOKEN") and conf.get("HA_POWER_ENTITY"))
    if ha_power_configured:
        power_val = f'{live.get("ha_power")} W' if live.get("ha_power") is not None else "?"
        body += render_tile("bolt", "Effekt", power_val, sub="fra Home Assistant")
    body += "</div>"

    chrome_badge = f'<span class="badge {"b-ok" if stats["chrome_running"] else "b-bad"}">{esc(chrome_label)}</span>'
    body += '<div class="paper flush"><div class="kv-grid">'
    body += render_kv("world", "IP", esc(stats["ip"]))
    body += render_kv("clock", "Oppetid", esc(stats["uptime"]))
    body += render_kv("activity", "GPU", esc(f'{live.get("gpu")}%' if live.get("gpu") is not None else "?"))
    body += render_kv("gauge", "CPU-frekvens", esc(f'{live.get("cpu_mhz")} MHz' if live.get("cpu_mhz") is not None else "?"))
    body += render_kv("temperature", "NVMe temperatur", esc(f'{live.get("nvme_temp")}°C' if live.get("nvme_temp") is not None else "?"))
    body += render_kv("wifi", "Netværk", esc(f'{live.get("network_kbps")} KiB/s' if live.get("network_kbps") is not None else "?"))
    body += render_kv("device-desktop", "Chrome", chrome_badge)
    body += render_kv("info-circle", "Model", esc(stats["model"]))
    body += "</div></div>"

    if health_detail:
        body += f'<div class="status" style="margin:0">{esc(health_detail)}</div>'
    window = '<small>seneste 60 minutter</small>'
    def legend(*series):
        return '<div class="legend">' + "".join(f'<span><i style="background:{color}"></i>{label}</span>' for label, color in series) + "</div>"
    power_chart = (
        f'<div class="chart-card"><div class="chart-title">Effekt (Home Assistant){window}</div>{legend(("W", "#facc15"))}'
        '<canvas class="telemetry-chart" id="powerChart"></canvas></div>'
        if ha_power_configured else ""
    )
    power_draw = (
        "drawChart('powerChart',rows,[{key:'ha_power',label:'W',color:'#facc15'}],0,true);"
        if ha_power_configured else ""
    )
    body += f"""
<div class="charts">
  <div class="chart-card"><div class="chart-title">CPU, RAM og GPU{window}</div>{legend(("CPU", "#3b82f6"), ("RAM", "#8b5cf6"), ("GPU", "#22c55e"))}<canvas class="telemetry-chart" id="usageChart"></canvas></div>
  <div class="chart-card"><div class="chart-title">CPU- og NVMe-temperatur{window}</div>{legend(("CPU °C", "#ef4444"), ("NVMe °C", "#f59e0b"))}<canvas class="telemetry-chart" id="temperatureChart"></canvas></div>
  <div class="chart-card"><div class="chart-title">CPU-frekvens{window}</div>{legend(("MHz", "#06b6d4"))}<canvas class="telemetry-chart" id="frequencyChart"></canvas></div>
  <div class="chart-card"><div class="chart-title">Netværkstrafik{window}</div>{legend(("KiB/s", "#a855f7"))}<canvas class="telemetry-chart" id="networkChart"></canvas></div>
  {power_chart}
</div>
</div>
<script>
function drawChart(id, rows, series, maxValue, fill) {{
  const canvas=document.getElementById(id), ratio=window.devicePixelRatio||1, width=canvas.clientWidth, height=canvas.clientHeight;
  canvas.width=width*ratio; canvas.height=height*ratio; const c=canvas.getContext('2d'); c.scale(ratio,ratio); c.clearRect(0,0,width,height);
  const css=getComputedStyle(document.documentElement); c.strokeStyle=css.getPropertyValue('--fd-border').trim()||'rgba(128,128,128,.22)';
  c.lineWidth=1; for(let i=0;i<=4;i++){{const y=Math.round(6+(height-12)*i/4)+.5;c.beginPath();c.moveTo(0,y);c.lineTo(width,y);c.stroke();}}
  const visible=rows.slice(-360); if(visible.length<2)return;
  const values=visible.flatMap(r=>series.map(s=>Number(r[s.key])).filter(Number.isFinite)); const top=maxValue||Math.max(1,...values)*1.12;
  const fillSeries=fill||series.length===1;
  for(const s of series){{const pts=[];visible.forEach((r,i)=>{{const v=Number(r[s.key]);if(!Number.isFinite(v))return;pts.push([i*width/(visible.length-1),height-6-Math.min(top,v)*(height-16)/top]);}});if(pts.length<2)continue;
    if(fillSeries){{c.globalAlpha=.12;c.fillStyle=s.color;c.beginPath();c.moveTo(pts[0][0],height);pts.forEach(p=>c.lineTo(p[0],p[1]));c.lineTo(pts[pts.length-1][0],height);c.closePath();c.fill();c.globalAlpha=1;}}
    c.strokeStyle=s.color;c.lineWidth=2;c.lineJoin='round';c.beginPath();pts.forEach((p,i)=>i?c.lineTo(p[0],p[1]):c.moveTo(p[0],p[1]));c.stroke();}}
}}
let lastRows=null;
function drawAll(rows){{drawChart('usageChart',rows,[{{key:'cpu',label:'CPU',color:'#3b82f6'}},{{key:'ram',label:'RAM',color:'#8b5cf6'}},{{key:'gpu',label:'GPU',color:'#22c55e'}}],100);drawChart('temperatureChart',rows,[{{key:'cpu_temp',label:'CPU °C',color:'#ef4444'}},{{key:'nvme_temp',label:'NVMe °C',color:'#f59e0b'}}],100);drawChart('frequencyChart',rows,[{{key:'cpu_mhz',label:'MHz',color:'#06b6d4'}}]);drawChart('networkChart',rows,[{{key:'network_kbps',label:'KiB/s',color:'#a855f7'}}]);{power_draw}}}
async function updateTelemetry(){{try{{const r=await fetch('/api/telemetry',{{cache:'no-store'}});if(!r.ok)return;lastRows=await r.json();drawAll(lastRows);}}catch(_){{}}}}
updateTelemetry();setInterval(updateTelemetry,10000);addEventListener('resize',()=>lastRows&&drawAll(lastRows));addEventListener('kw-look',()=>lastRows&&drawAll(lastRows));
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
        profile_data = json.loads(subprocess.run([profile_script, "list"], capture_output=True, text=True, timeout=3).stdout)
        profiles = profile_data.get("profiles", [])
        profile_automation = profile_data.get("automation", {})
        active_profile = subprocess.run([profile_script, "status"], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        profiles, active_profile, profile_automation = [], "", {}
    try:
        touch_output = subprocess.run(["xinput", "list"], capture_output=True, text=True, timeout=3).stdout
        touch_line = next((line.strip() for line in touch_output.splitlines() if "touch" in line.lower()), "")
        touch_name = re.sub(r".*↳\s*|\s+id=\d+.*", "", touch_line).strip() or "Ikke registreret"
        touch_id = re.search(r"id=(\d+)", touch_line)
        touch_props = subprocess.run(["xinput", "list-props", touch_id.group(1)], capture_output=True, text=True, timeout=3).stdout if touch_id else ""
        matrix = re.search(r"Coordinate Transformation Matrix[^:]*:\s*(.+)", touch_props)
        touch_calibration = calibration_label(matrix.group(1)) if matrix else "Standard/ukendt"
    except (OSError, subprocess.TimeoutExpired):
        touch_name = "Ikke registreret"
        touch_calibration = "Ukendt"
    if not shutil.which("xprintidle"):
        last_input = "Ikke installeret (xprintidle)"
    else:
        try:
            idle_ms = int(subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=3).stdout.strip())
            last_input = f"{idle_ms // 1000} sek. siden"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            last_input = "Ukendt"
    options = "".join(
        f'<option value="{key}"{" selected" if key == profile else ""}>{label}</option>'
        for key, label in POWER_PROFILES.items()
    )
    body = PAGE_HEAD.format(title_suffix=" — Kiosk")
    active_profile_url = next((item.get("url", "") for item in profiles if item.get("name") == active_profile), "")
    body += render_page_header(
        "Kiosk", conf, "Styr skærm, profiler, hardware og kioskens driftsfunktioner.",
        f'<button type="button" class="primary" id="restartWardenManual">{icon("shield-check")}Genstart Kiosk Warden</button>',
    )
    body += render_nav("/control", conf) + render_message(message, error)
    body += f'<p class="status" style="margin:-12px 0 16px">Aktiv visning: <strong>{esc(active_profile_url or "Ingen profil")}</strong></p>'
    body += '<div class="countdown" id="manualRestartCountdown" style="margin:-8px 0 12px"></div>'

    def action(do, label, ico, cls="", confirm_text=""):
        onsubmit = f' onsubmit="return confirm(\'{confirm_text}\');"' if confirm_text else ""
        cls_attr = f' class="{cls}"' if cls else ""
        return f'<form method="post" action="/action"{onsubmit}><input type="hidden" name="do" value="{do}"><button{cls_attr} type="submit">{icon(ico)}{label}</button></form>'

    def profile_row(item):
        name = item.get("name", "")
        on = name == active_profile
        return (
            f'<div class="list-row"><span class="fd-dot {"c-ok" if on else "c-off"}"></span>'
            f'<div style="min-width:0;flex:1"><b>{esc(name or "Profil")}</b> <span class="badge b-gray">{esc(item.get("zoom", 100))}%</span>'
            f'<div class="xs dim" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{esc(item.get("url", ""))}</div></div>'
            f'<form method="post" action="/profile-switch"><input type="hidden" name="name" value="{esc(name)}"><button class="{"light" if on else ""}" type="submit">{"Aktiv" if on else "Skift"}</button></form>'
            f'<form method="post" action="/profile-remove"><input type="hidden" name="name" value="{esc(name)}"><button class="subtle icon-only" type="submit" title="Fjern profil" aria-label="Fjern profil">{icon("trash")}</button></form></div>'
        )

    tabs = [
        ("tab-drift", "Drift", "activity"),
        ("tab-skaerm", "Skærm og hardware", "device-desktop"),
        ("tab-profiler", "Profiler", "device-tv"),
        ("tab-strom", "Strøm og Smartdash", "bolt"),
        ("tab-maskine", "Maskine", "power"),
    ]
    body += '<div class="tabs" role="tablist" data-tabs="control">' + "".join(
        f'<button type="button" role="tab" id="{tid}-btn" aria-controls="{tid}" aria-selected="false">{icon(ico)}{label}</button>' for tid, label, ico in tabs
    ) + "</div>"
    body += f"""
<section class="tab-panel" id="tab-drift" role="tabpanel" aria-labelledby="tab-drift-btn"><div class="tab-cols"><div>
<fieldset><legend>Kiosktilstand og diagnostik</legend>
  <div class="grid g3"><div class="tile"><span>Tilstandsmaskine</span><strong>{esc(state.get('state', 'UNKNOWN'))}</strong></div><div class="tile"><span>Seneste selvtest</span><strong>{esc(self_test.get('result', '—'))}</strong></div><div class="tile"><span>Wake-tid</span><strong>{esc(str(self_test.get('wake_time_ms', '—')) + (' ms' if self_test.get('wake_time_ms') is not None else ''))}</strong></div></div>
  <p class="status">Selvtesten gennemfører en rigtig OFF→ON-cyklus og kontrollerer backend/DPMS, opløsning, Chrome-side, renderer/layout og serviceporte.</p>
  <div class="row">{action("self_test", "Kør OFF→ON-test", "player-play", "primary")}{action("recover", "Trinvis recovery", "first-aid-kit")}{action("diagnostics", "Lav sikker diagnostik-ZIP", "package")}{f'<a class="btn subtle" href="/diagnostics/latest.zip">{icon("download")}Download seneste ZIP</a>' if has_diagnostics else ''}</div>
</fieldset>
</div><div>
<fieldset><legend>Kiosk og Warden</legend><div class="row">
  {action("reload", "Genindlæs side", "refresh")}
  {action("restart_chrome", "Genstart Chrome", "rotate-clockwise")}
  {action("backup", "Backup config", "archive")}
</div></fieldset>
</div></div></section>

<section class="tab-panel" id="tab-skaerm" role="tabpanel" aria-labelledby="tab-skaerm-btn" hidden><div class="tab-cols"><div>
<fieldset><legend>Skærm og touch</legend><div class="grid">
  <div class="tile"><span>Aktiv skærm</span><strong>{esc(display_status.get('output', '—'))}</strong></div>
  <div class="tile"><span>Opløsning</span><strong>{esc(str(display_status.get('width', '—')) + '×' + str(display_status.get('height', '—')))}</strong></div>
  <div class="tile"><span>Refresh rate</span><strong>{esc(str(display_status.get('refresh_hz', '—')) + ' Hz')}</strong></div>
  <div class="tile"><span>Touchscreen</span><strong>{esc(touch_name)}</strong></div>
  <div class="tile"><span>Kalibrering</span><strong>{esc(touch_calibration)}</strong></div>
  <div class="tile"><span>Seneste input</span><strong>{esc(last_input)}</strong></div>
  <div class="tile"><span>Backend</span><strong>{esc(display_status.get('backend', '—'))}</strong></div>
</div></fieldset>
</div><div>
<fieldset><legend>Hardware capabilities</legend><div class="grid">
  <div class="tile"><span>Touch wake</span><strong>{esc(touch_guardian_label(capabilities))}</strong></div>
  <div class="tile"><span>Lysstyrke</span><strong>{esc(capabilities.get('display',{}).get('brightness_backend') or 'Ikke tilgængelig')}</strong></div>
  <div class="tile"><span>Lyssensor</span><strong>{'Understøttet' if capabilities.get('sensors',{}).get('illuminance') else 'Ikke tilgængelig'}</strong></div>
  <div class="tile"><span>Mikrofon</span><strong>{'Understøttet' if capabilities.get('audio',{}).get('microphone') else 'Ikke tilgængelig'}</strong></div>
  <div class="tile"><span>Batteri</span><strong>{'Understøttet' if capabilities.get('sensors',{}).get('battery') else 'Ikke tilgængelig'}</strong></div>
</div><div class="row"><form method="post" action="/action"><input type="hidden" name="do" value="probe_capabilities"><button type="submit">{icon("zoom-scan")}Kontroller hardware igen</button></form></div></fieldset>
</div></div></section>

<section class="tab-panel" id="tab-profiler" role="tabpanel" aria-labelledby="tab-profiler-btn" hidden><div class="tab-cols"><div>
<fieldset><legend>Kioskprofiler</legend>
  <p class="status">Hver profil har sin egen URL og zoom. Warden verifierer den valgte URL og bruger den lokale offline-side, hvis dashboardet ikke kan nås.</p>
  <div>{''.join(profile_row(item) for item in profiles) or '<p class="status">Ingen profiler endnu.</p>'}</div>
  {''.join(f'<fieldset><legend>{esc(item.get("name","Profil"))}</legend><form method="post" action="/profile-add"><input type="hidden" name="name" value="{esc(item.get("name",""))}"><label>{esc(item.get("name","Profil"))} URL</label><input type="text" name="url" value="{esc(item.get("url",""))}" required><label>Zoom</label><select name="zoom">{render_zoom_options(item.get("zoom",100))}</select><div class="row"><button type="submit">{icon("device-floppy")}Opdatér profil</button></div></form></fieldset>' for item in profiles)}
  <fieldset><legend>Tilføj profil</legend><form method="post" action="/profile-add"><label>Nyt profilnavn</label><input type="text" name="name" required maxlength="40"><label>URL</label><input type="text" name="url" required placeholder="https://..."><label>Zoom</label><select name="zoom">{render_zoom_options()}</select><div class="row"><button type="submit">{icon("plus")}Tilføj profil</button></div></form></fieldset>
</fieldset>
</div><div>
  <form method="post" action="/profile-automation">
    <fieldset><legend>Automatisk profilskift</legend>
      <label><input type="checkbox" name="enabled" value="true"{' checked' if profile_automation.get('enabled') else ''}> Aktivér automatisk profilskift</label>
      <label>Automatiktype</label><select name="mode"><option value="cycle"{' selected' if profile_automation.get('mode','cycle') == 'cycle' else ''}>Cycle mode</option><option value="schedule"{' selected' if profile_automation.get('mode') == 'schedule' else ''}>Bestemte tidspunkter</option></select>
      <label>Skift hvert antal minutter (cycle mode)</label><input type="number" name="cycle_minutes" min="1" max="1440" value="{esc(profile_automation.get('cycle_minutes',15))}" required>
      <label>Profiler i cycle mode</label><div class="choice-grid">{''.join(f'<label><input type="checkbox" name="cycle_profile" value="{esc(item.get("name",""))}"{" checked" if item.get("name") in profile_automation.get("cycle_profiles",[]) else ""}> {esc(item.get("name","Profil"))}</label>' for item in profiles)}</div>
      <p class="status">Vælg mindst to profiler, når cycle mode er aktiv.</p>
      <label>Tidsplan (én linje pr. skift: TT:MM=Profilnavn)</label><textarea name="schedule" rows="6" placeholder="07:00=Morgen&#10;18:00=Aften">{esc(chr(10).join(f'{entry.get("time","")}={entry.get("profile","")}' for entry in profile_automation.get('schedule',[])))}</textarea>
      <p class="status">Cycle følger profilernes rækkefølge. Tidsplanen gentages hver dag og bruger maskinens lokale tid.</p>
      <div class="row"><button class="primary" type="submit">Gem automatisk profilskift</button></div>
    </fieldset>
  </form>
</div></div></section>

<section class="tab-panel" id="tab-strom" role="tabpanel" aria-labelledby="tab-strom-btn" hidden><div class="tab-cols"><div>
<fieldset><legend>Strømprofil</legend>
  <p class="status">Strømbesparelse bruger mindst strøm. Balanceret og Ydelse giver gradvist mere CPU-kraft.</p>
  <form method="post" action="/power-profile"><label>Aktiv profil</label><select name="profile">{options}</select><div class="row"><button class="primary" type="submit">Skift strømprofil</button></div></form>
</fieldset>
</div><div>
<fieldset><legend>Smartdash-forbindelse</legend>
  <p class="status">Pause og genoptagelse af <strong>animationer, livekameraer og rendering virker kun, når kiosken viser HA Smartdash</strong>. Skærmens almindelige tænd/sluk via DPMS virker fortsat med andre dashboards, men Warden kan ikke stoppe deres interne animationer eller mediearbejde. HA Smartdash registreres automatisk via Chromes lokale debug-port og kan også styres fra Home Assistant gennem MQTT-entityen Smartdash Rendering.</p>
  <div class="grid g3" style="margin-top:12px"><div class="tile"><span>Automatisk registrering</span><strong id="smartdashDetected">{'Forbundet' if smartdash.get('supported') else ('Afhængighed mangler' if smartdash.get('error') == 'missing_dependency' else 'Kontakt fejlede' if smartdash.get('error') else 'Ikke registreret')}</strong></div><div class="tile"><span>Tilstand</span><strong id="smartdashState">{esc(smartdash.get('state') or '—')}</strong></div><div class="tile"><span>Build</span><strong id="smartdashBuild">{esc(smartdash.get('release') or smartdash.get('build') or '—')}</strong></div></div>
  {f'<p class="status" id="smartdashErrorDetail">{esc(smartdash.get("error_message"))}</p>' if smartdash.get('error') else '<p class="status" id="smartdashErrorDetail" style="display:none"></p>'}
  <div class="row"><button type="button" id="refreshSmartdash">{icon("refresh")}Kontroller igen</button></div>
</fieldset>
</div></div></section>

<section class="tab-panel" id="tab-maskine" role="tabpanel" aria-labelledby="tab-maskine-btn" hidden><div class="tab-cols"><div>
<fieldset><legend>Maskine</legend>
  <p class="status">Spørger om bekræftelse før genstart eller sluk.</p>
  <div class="row">
  {action("reboot", "Genstart maskine", "refresh", "danger", "Genstarte maskinen nu?")}
  {action("shutdown", "Sluk maskine", "power", "danger", "Slukke maskinen nu?")}
</div></fieldset>
</div><div></div></div></section>
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
  const timer = setInterval(async () => {{ seconds -= 1; label.textContent = `Genstarter om ${{seconds}} sekunder…`; if (seconds <= 0) {{ clearInterval(timer); await fetch('/action', {{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded','X-Warden-CSRF':document.querySelector('meta[name="warden-csrf"]').content}},body:'do=restart_warden'}}); label.textContent = 'Kiosk Warden genstarter…'; }} }}, 1000);
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
    """Optional Home Assistant connection section on Connections.

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
    <div class="row"><button class="primary" type="submit">{icon("device-floppy")}Gem og test forbindelse</button></div>
  </fieldset>
</form>
<form method="post" action="/test-ha"><div class="row" style="margin:0 0 16px"><button type="submit">{icon("plug")}Test Home Assistant-forbindelse</button></div></form>
"""


def render_mqtt(conf, message=None, error=None):
    body = PAGE_HEAD.format(title_suffix=" — Forbindelser")
    body += render_page_header("Forbindelser", conf, "Opsæt MQTT og den valgfrie forbindelse til Home Assistant.")
    body += render_nav("/mqtt", conf) + render_message(message, error)
    topic = f'home/kiosk/{conf.get("KIOSK_ID", "kiosk")}'
    body += f"""
<div class="tab-cols"><div>
<form method="post" action="/save-mqtt">
  <fieldset>
    <legend>Broker</legend>
    <label>Broker host/IP</label>
    <input type="text" name="MQTT_HOST" value="{esc(conf.get('MQTT_HOST',''))}" required>
    <label>Broker port</label>
    <input type="number" name="MQTT_PORT" value="{esc(conf.get('MQTT_PORT',''))}" required>
    <label>Brugernavn</label>
    <input type="text" name="MQTT_USER" value="{esc(conf.get('MQTT_USER',''))}">
    <label>Password (tomt = behold nuværende)</label>
    <input type="password" name="MQTT_PASS" placeholder="••••••••">
    <label>Stats-interval (sekunder)</label>
    <input type="number" name="STATS_INTERVAL" value="{esc(conf.get('STATS_INTERVAL',''))}" required>
    <div class="row"><button class="primary" type="submit">{icon("device-floppy")}Gem og genstart MQTT</button></div>
  </fieldset>
</form>
<form method="post" action="/test-mqtt"><div class="row" style="margin:0 0 16px"><button type="submit">{icon("plug")}Test MQTT-forbindelse</button></div></form>
</div><div>
  <fieldset>
    <legend>Home Assistant</legend>
    <p class="status">Kiosk-id bestemmer topic'et og bruges af MQTT discovery.</p>
    <div class="grid g2" style="margin-top:12px"><div class="tile"><span>Base topic</span><strong>{esc(topic)}</strong></div><div class="tile"><span>Kiosk-id</span><strong>{esc(conf.get('KIOSK_ID', 'kiosk'))}</strong></div></div>
  </fieldset>
{render_ha_fieldset(conf)}
</div></div>
"""
    return body + PAGE_TAIL


def render_settings(conf, message=None, error=None):
    body = PAGE_HEAD.format(title_suffix=" — System")
    body += render_page_header("System", conf, "Tilpas identitet, lokale porte, skærm, login og strømfunktioner.")
    body += render_nav("/settings", conf)
    body += render_message(message, error)

    body += '<div class="tab-cols"><div>'
    body += f"""
<form method="post" action="/save">
  <fieldset>
    <legend>Kiosk</legend>
    <label>Navn på kiosken</label>
    <input type="text" name="KIOSK_NAME" value="{esc(conf.get('KIOSK_NAME',''))}" required>
    <label>Kiosk-id (a-z 0-9 _, bruges i MQTT-topics)</label>
    <input type="text" name="KIOSK_ID" value="{esc(conf.get('KIOSK_ID',''))}" required>
    <label>Base topic (bruges af MQTT og Home Assistant)</label>
    <input type="text" name="BASE_TOPIC" value="{esc(conf.get('BASE_TOPIC',''))}" required>
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
    <label>Automatisk logud efter 12 timer</label>
    <select name="WEBUI_AUTO_LOGOUT"><option value="true"{' selected' if conf.get('WEBUI_AUTO_LOGOUT', 'true') == 'true' else ''}>Til</option><option value="false"{' selected' if conf.get('WEBUI_AUTO_LOGOUT') == 'false' else ''}>Fra</option></select>
    <div class="row"><button class="primary" type="submit">{icon("device-floppy")}Gem og genstart</button></div>
  </fieldset>
</form>
</div><div>
{render_look_panel()}
<form method="post" action="/change-password">
  <fieldset>
    <legend>Skift administrator-login</legend>
    <label>Brugernavn</label>
    <input type="text" name="username" value="{esc(conf.get('WEBUI_USERNAME', 'admin'))}" required minlength="3" maxlength="40" autocomplete="username">
    <label>Nyt password (min. 8 tegn)</label>
    <input type="password" name="password" required minlength="8">
    <label>Gentag nyt password</label>
    <input type="password" name="password2" required minlength="8">
    <div class="row"><button type="submit">{icon("key")}Skift password</button></div>
  </fieldset>
</form>

<div class="status">VNC-passworden styres automatisk af Kiosk Warden-login og skal ikke indtastes.</div>

"""
    body += render_kontrolrum_card(conf)
    body += "</div></div>"
    body += PAGE_TAIL
    return body


def render_kontrolrum_card(conf):
    if SSO is None:
        return ""
    info = SSO.status()
    username = conf.get("WEBUI_USERNAME") or "admin"
    ticked = SSO.user_allowed(username)
    if info["enabled"]:
        state = f"Slået til. Nøgle {esc(info['fingerprint'])}…"
    elif not info["readable"]:
        state = "Indstillingerne kan ikke læses. Lav en ny SSO-nøgle."
    else:
        state = "Slået fra. Lav en SSO-nøgle, og sæt den ind i Kontrolrum."
    used = info["last_used"]
    used_text = "Ikke brugt endnu."
    if used:
        stamp = time.strftime("%d-%m-%Y %H:%M", time.localtime(used.get("at", 0)))
        used_text = f"Senest brugt {esc(stamp)} fra {esc(used.get('ip', ''))} som {esc(used.get('user', ''))}."
    rejected = ""
    if info["rejected_ip"]:
        stamp = time.strftime("%d-%m-%Y %H:%M", time.localtime(info["rejected_at"] or 0))
        rejected = f'<div class="msg error">Seneste afviste forsøg {esc(stamp)} fra {esc(info["rejected_ip"])} ({esc(info["rejected_text"])}).</div>'
    missing = ""
    if info["enabled"] and not info["peers"]:
        missing = '<div class="msg error">Skriv Kontrolrums IP-adresse herunder. Indtil da afvises alle login fra Kontrolrum.</div>'
    off_form = ""
    if info["enabled"]:
        off_form = """<form method="post" action="/kontrolrum/off" onsubmit="return confirm('Slå login fra Kontrolrum fra? Nøglen slettes.')"><div class="row"><button type="submit">Slå fra</button></div></form>"""
    key_label = "Ny nøgle" if info["enabled"] else "Lav SSO-nøgle"
    key_confirm = ' onsubmit="return confirm(\'Lav en ny nøgle? Den gamle holder op med at virke med det samme.\')"' if info["enabled"] else ""
    return f"""
<fieldset id="kontrolrum">
  <legend>Login fra Kontrolrum</legend>
  <div class="status">Kontrolrum logger ind med en nøgle i stedet for et password. Det virker kun fra Kontrolrums egen adresse.</div>
  <div class="status">{state}</div>
  <div class="status">{used_text}</div>
  {rejected}{missing}
  <form method="post" action="/kontrolrum/key"{key_confirm}><div class="row"><button type="submit">{key_label}</button></div></form>
  {off_form}
  <form method="post" action="/kontrolrum/peers">
    <label>Kontrolrums IP-adresse</label>
    <input type="text" name="ips" value="{esc(', '.join(info['peers']))}" maxlength="400" autocomplete="off" spellcheck="false" placeholder="fx 10.0.0.28">
    <div class="row"><button type="submit">Gem adresse</button></div>
  </form>
  <form method="post" action="/kontrolrum/user">
    <label><input type="checkbox" name="allowed" value="true"{' checked' if ticked else ''}> {esc(username)} må logges ind fra Kontrolrum</label>
    <div class="row"><button type="submit">Gem</button></div>
  </form>
</fieldset>
"""


def render_kontrolrum_key(conf, key):
    body = PAGE_HEAD.format(title_suffix=" — Kontrolrum")
    body += render_page_header("Login fra Kontrolrum", conf, "Sæt nøglen ind under Automatisk login på Kiosk Warden-tjenesten i Kontrolrum.")
    body += render_nav("/settings")
    body += f"""
<div class="narrow">
  <div class="msg error">Kopiér nøglen nu. Den vises kun denne ene gang.</div>
  <fieldset><legend>SSO-nøgle</legend><code style="overflow-wrap:anywhere">{esc(key)}</code></fieldset>
  <div class="row"><a href="/settings#kontrolrum">Færdig</a></div>
</div>
"""
    body += PAGE_TAIL
    return body


def render_port_change(conf, new_port):
    body = PAGE_HEAD.format(title_suffix=" — Web-UI port")
    body += f"""
<div class="narrow">
  <div class="row" style="margin:0 0 16px">{render_logo(30)}<b style="font-size:17px">Kiosk Warden</b></div>
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


def render_vnc(conf, message=None, error=None, active=None):
    body = PAGE_HEAD.format(title_suffix=" — Fjernstyring")
    body += render_page_header("Fjernstyring", conf, "Åbn en midlertidig fjernsession til kioskens aktuelle skærm.")
    active = vnc_is_active() if active is None else active
    body += render_nav("/vnc", conf)
    body += render_message(message, error)
    if active:
        body += f"""
<div class="row">
  <button class="primary" type="button" onclick="document.getElementById('vncframe').requestFullscreen()">{icon("maximize")}Fuld skærm</button>
  <button type="button" onclick="reloadFrame()">{icon("refresh")}Genopfrisk forbindelse</button>
  <form method="post" action="/vnc/stop" style="display:inline">
    <button class="danger" type="submit">{icon("player-stop")}Stop VNC</button>
  </form>
</div>
<div class="vnc-frame">
  <iframe id="vncframe" allowfullscreen></iframe>
</div>
<div class="status">VNC er aktiv og lukker automatisk, når siden lukkes.</div>
<script>
  const vncPassword = "{esc(vnc_password_from_conf(conf))}";
  function vncUrl() {{
    const host = encodeURIComponent(location.hostname);
    const port = {int(conf.get("KIOSK_NOVNC_PORT", "6080"))};
    return 'http://' + host + ':' + port + '/vnc.html?autoconnect=true&resize=scale&reconnect=true&host=' + host + '&port=' + port + '&_=' + Date.now() + '#password=' + encodeURIComponent(vncPassword);
  }}
  function reloadFrame() {{
    document.getElementById('vncframe').src = vncUrl();
  }}
  async function startFrame() {{
    for (let attempt = 0; attempt < 24; attempt++) {{
      try {{
        const response = await fetch('/vnc/status', {{cache: 'no-store'}});
        if ((await response.json()).ready) break;
      }} catch (error) {{}}
      await new Promise(resolve => setTimeout(resolve, 250));
    }}
    reloadFrame();
  }}
  function heartbeat() {{
    fetch('/vnc/heartbeat', {{method: 'POST', cache: 'no-store', keepalive: true, headers: {{'X-Warden-CSRF': document.querySelector('meta[name="warden-csrf"]').content}}}});
  }}
  heartbeat();
  setInterval(heartbeat, 1000);
  startFrame();
</script>
"""
    else:
        body += f"""
<div class="row">
  <form method="post" action="/vnc/start" style="display:inline">
    <button class="primary" type="submit">{icon("player-play")}Start VNC</button>
  </form>
</div>
<div class="vnc-empty">
  <div>{icon("device-desktop")}<div class="status">VNC er slukket. Tryk på Start VNC for at forbinde.</div></div>
</div>
"""
    body += PAGE_TAIL
    return body


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "KioskWarden/1.0"

    def log_message(self, fmt, *args):
        pass

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-src http: https:; connect-src 'self'")

    def _send_html(self, body, status=200):
        conf = read_conf()
        if self._authenticated(conf):
            body = inject_csrf(body, csrf_token(self._session_token(), conf))
        body = localize_html(body, conf.get("UI_LANGUAGE", "en"))
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status=200, cookie=None):
        language = read_conf().get("UI_LANGUAGE", "en")
        if language == "en" and isinstance(payload, dict):
            payload = {key: localize_html(value, "en") if isinstance(value, str) else value for key, value in payload.items()}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self._security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, path):
        """Design assets (CSS, script, font) are public so the login page is styled too."""
        content_type, data = STATIC_ASSETS[path]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        # Links carry ?v=<hash of the assets>, so a new build is always fetched.
        self.send_header("Cache-Control", "public, max-age=604800")
        self._security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self._security_headers()
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
        return bool(conf.get("WEBUI_PASSWORD_HASH")) and valid_session(self._session_token(), conf, self.client_address[0])

    def _login_redirect(self, requested="/"):
        target = requested if requested.startswith("/") and not requested.startswith("//") else "/"
        return self._redirect("/login?" + urllib.parse.urlencode({"next": target}))

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path == "/icon.svg":
            return self._serve_icon()
        if parsed.path in STATIC_ASSETS:
            return self._serve_static(parsed.path)
        if parsed.path == "/offline":
            return self._send_html(render_offline())
        if parsed.path == "/login/kontrolrum":
            self.send_response(404)
            self.end_headers()
            return

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
            return self._redirect("/login", self._session_cookie("", 0))

        if not self._authenticated(conf):
            return self._login_redirect(self.path)

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
        if parsed.path == "/mqtt":
            return self._send_html(render_mqtt(conf))
        if parsed.path in ("/", ""):
            return self._send_html(render_dashboard(conf))
        self.send_response(404)
        self.end_headers()

    def _kontrolrum_login(self, conf):
        """POST /login/kontrolrum: sign-in from Kontrolrum. Whatever goes wrong
        in here ends with this one request being refused."""
        if SSO is None or not conf.get("WEBUI_PASSWORD_HASH"):
            self.send_response(404)
            self.end_headers()
            return
        client_ip = self.client_address[0]
        username = conf.get("WEBUI_USERNAME") or "admin"

        def find_user(name):
            return username if hmac.compare_digest(str(name).encode(), username.encode()) else None

        try:
            refusal = SSO.gate(client_ip)
            if refusal is not None:
                return self._send_json({"error": refusal.error}, refusal.status)
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except ValueError:
                length = -1
            raw = self.rfile.read(length) if 0 < length <= kontrolrum_sso.MAX_BODY else b""
            outcome = SSO.login(client_ip, raw, find_user)
            if not outcome.ok:
                return self._send_json({"error": outcome.error}, outcome.status)
            token = create_kontrolrum_session(conf, outcome.binding, outcome.user)
        except Exception as error:  # noqa: BLE001 - see the docstring
            print(f"kontrolrum sign-in failed: {type(error).__name__}", file=sys.stderr, flush=True)
            return self._send_json({"error": "unavailable"}, 503)
        print(f"kontrolrum sign-in from {client_ip}", file=sys.stderr, flush=True)
        return self._send_json({"ok": True, "user": outcome.user}, cookie=self._session_cookie(token, SESSION_TTL))

    def _kontrolrum_settings(self, path, fields, conf):
        if SSO is None:
            return self._send_html(render_settings(conf, error="Login fra Kontrolrum er ikke tilgængeligt."), status=503)
        try:
            if path == "/kontrolrum/key":
                return self._send_html(render_kontrolrum_key(conf, SSO.create_key(conf.get("WEBUI_USERNAME") or "admin")))
            if path == "/kontrolrum/off":
                SSO.disable()
                return self._send_html(render_settings(conf, message="Login fra Kontrolrum er slået fra."))
            if path == "/kontrolrum/peers":
                good, bad = kontrolrum_sso.parse_peers(fields.get("ips", [""])[0][:400])
                if bad:
                    return self._send_html(render_settings(conf, error="Kunne ikke læse: " + ", ".join(bad[:3])))
                SSO.set_peers(good)
                return self._send_html(render_settings(conf, message="Kontrolrums adresse er gemt."))
            SSO.set_user(conf.get("WEBUI_USERNAME") or "admin", fields.get("allowed", [""])[0] == "true")
            return self._send_html(render_settings(conf, message="Gemt."))
        except (OSError, ValueError) as error:
            detail = str(error) if isinstance(error, ValueError) else "Indstillingen kunne ikke gemmes."
            return self._send_html(render_settings(conf, error=detail))

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        conf = read_conf()
        if parsed.path == "/login/kontrolrum":
            return self._kontrolrum_login(conf)
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = MAX_POST_BYTES + 1
        if length < 0 or length > MAX_POST_BYTES:
            return self._send_html("<h1>Forespørgslen er for stor.</h1>", status=413)
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
            run("systemctl", "--user", "restart", "kiosk-vnc.service")
            token = create_session(conf)
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
            remember = fields.get("remember", ["false"])[0] == "true"
            duration = REMEMBER_TTL if remember or conf.get("WEBUI_AUTO_LOGOUT", "true") == "false" else SESSION_TTL
            token = create_session(conf, duration)
            safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
            return self._redirect(safe_next, self._session_cookie(token, duration))

        if not self._authenticated(conf):
            return self._login_redirect(parsed.path)

        supplied_csrf = fields.get("csrf_token", [""])[0] or self.headers.get("X-Warden-CSRF", "") or urllib.parse.parse_qs(parsed.query).get("csrf", [""])[0]
        expected_csrf = csrf_token(self._session_token(), conf)
        if not hmac.compare_digest(supplied_csrf, expected_csrf):
            return self._send_html("<h1>Sikkerhedskontrollen afviste forespørgslen. Genindlæs siden og prøv igen.</h1>", status=403)

        if parsed.path in ("/kontrolrum/key", "/kontrolrum/off", "/kontrolrum/peers", "/kontrolrum/user"):
            return self._kontrolrum_settings(parsed.path, fields, conf)

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
            for key in ["KIOSK_NAME", "KIOSK_ID", "BASE_TOPIC", "MQTT_HOST", "MQTT_USER", "MQTT_PORT", "STATS_INTERVAL", "KIOSK_WEBUI_PORT", "KIOSK_VNC_PORT", "KIOSK_NOVNC_PORT", "KIOSK_SCREEN_BACKEND", "KIOSK_BRIGHTNESS_MIN", "KIOSK_BRIGHTNESS_MAX"]:
                if key in fields:
                    conf[key] = fields[key][0].strip()
            conf["KIOSK_TOUCH_WAKE"] = "true" if fields.get("KIOSK_TOUCH_WAKE", ["false"])[0] == "true" else "false"
            conf["KIOSK_AUTO_BRIGHTNESS"] = "true" if fields.get("KIOSK_AUTO_BRIGHTNESS", ["false"])[0] == "true" else "false"
            conf["WEBUI_AUTO_LOGOUT"] = "true" if fields.get("WEBUI_AUTO_LOGOUT", ["true"])[0] == "true" else "false"
            conf["UI_LANGUAGE"] = "da" if fields.get("UI_LANGUAGE", ["en"])[0] == "da" else "en"
            pw = fields.get("MQTT_PASS", [""])[0]
            if pw:
                conf["MQTT_PASS"] = pw
            if not conf.get("BASE_TOPIC"):
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

        if parsed.path == "/save-mqtt":
            host = fields.get("MQTT_HOST", [""])[0].strip()
            port = fields.get("MQTT_PORT", [""])[0].strip()
            interval = fields.get("STATS_INTERVAL", [""])[0].strip()
            if not host:
                return self._send_html(render_mqtt(conf, error="MQTT host må ikke være tom."))
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                return self._send_html(render_mqtt(conf, error="MQTT porten skal være mellem 1 og 65535."))
            if not interval.isdigit() or int(interval) < 1:
                return self._send_html(render_mqtt(conf, error="Stats-interval skal være mindst 1 sekund."))
            conf["MQTT_HOST"] = host
            conf["MQTT_PORT"] = port
            conf["MQTT_USER"] = fields.get("MQTT_USER", [""])[0].strip()
            conf["STATS_INTERVAL"] = interval
            password = fields.get("MQTT_PASS", [""])[0]
            if password:
                conf["MQTT_PASS"] = password
            write_conf(conf)
            run("systemctl", "--user", "restart", "kiosk-mqtt-stats.service", "kiosk-mqtt-control.service")
            run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
            return self._send_html(render_mqtt(read_conf(), message="MQTT-indstillingerne er gemt og services er genstartet."))

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
                    return self._send_html(render_mqtt(conf, message=f"Home Assistant-forbindelse gemt. {msg}"))
                return self._send_html(render_mqtt(conf, error=msg))
            return self._send_html(render_mqtt(conf, message="Home Assistant-forbindelse gemt."))

        if parsed.path == "/test-mqtt":
            ok, detail = test_mqtt_connection(conf)
            if ok:
                return self._send_html(render_mqtt(conf, message="MQTT-forbindelsen virker."))
            return self._send_html(render_mqtt(conf, error=f"MQTT-forbindelsen fejlede: {detail or 'ingen forbindelse'}"))

        if parsed.path == "/test-ha":
            if not conf.get("HA_URL") or not conf.get("HA_TOKEN"):
                return self._send_html(render_mqtt(conf, error="URL og token skal begge udfyldes."))
            ok, detail = ha_client.test_connection(conf["HA_URL"], conf["HA_TOKEN"])
            if ok:
                return self._send_html(render_mqtt(conf, message=f"Home Assistant-forbindelsen virker. {detail}"))
            return self._send_html(render_mqtt(conf, error=detail))

        if parsed.path == "/change-password":
            username = fields.get("username", [""])[0].strip()
            pw = fields.get("password", [""])[0]
            pw2 = fields.get("password2", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", username) or len(pw) < 8 or pw != pw2:
                return self._send_html(render_settings(conf, error="Password skal være mindst 8 tegn og matche i begge felter."))
            conf["WEBUI_USERNAME"] = username
            conf["WEBUI_PASSWORD_HASH"] = hash_password(pw)
            write_conf(conf)
            run("systemctl", "--user", "restart", "kiosk-vnc.service")
            token = create_session(conf)
            return self._redirect("/settings", self._session_cookie(token))

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

        if parsed.path == "/profile-automation":
            enabled = "true" if fields.get("enabled", ["false"])[0] == "true" else "false"
            mode = fields.get("mode", ["cycle"])[0]
            minutes = fields.get("cycle_minutes", ["15"])[0].strip()
            cycle_profiles = [name.strip() for name in fields.get("cycle_profile", []) if name.strip()]
            schedule = []
            try:
                if not minutes.isdigit() or not 1 <= int(minutes) <= 1440:
                    raise ValueError
                for raw in fields.get("schedule", [""])[0].splitlines():
                    if not raw.strip():
                        continue
                    clock, profile = (part.strip() for part in raw.split("=", 1))
                    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
                        raise ValueError
                    schedule.append({"time": clock, "profile": profile})
            except (ValueError, TypeError):
                return self._send_html(render_control(conf, error="Tidsplanen skal bruge formatet TT:MM=Profilnavn."))
            result = subprocess.run([os.path.join(KIOSK_DIR, "profile-manager.py"), "automation", enabled, mode, minutes, json.dumps(cycle_profiles), json.dumps(schedule)], timeout=10)
            if result.returncode != 0:
                return self._send_html(render_control(conf, error="Automatisk profilskift kunne ikke gemmes. Kontroller profilnavnene."))
            run("systemctl", "--user", "restart", "kiosk-profile-scheduler.service")
            return self._send_html(render_control(read_conf(), message="Automatisk profilskift er gemt."))

        if parsed.path == "/vnc/start":
            mark_vnc_activity()
            run("systemctl", "--user", "restart", "kiosk-vnc.service", "kiosk-novnc.service")
            return self._redirect("/vnc")

        if parsed.path == "/vnc/stop":
            stop_vnc_services()
            return self._redirect("/vnc")

        if parsed.path == "/vnc/heartbeat":
            mark_vnc_activity()
            return self._send_json({"active": vnc_is_active()})

        if parsed.path == "/vnc/status":
            return self._send_json({"active": vnc_is_active(), "ready": vnc_is_ready()})

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
                                "kiosk-profile-scheduler.service",
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
