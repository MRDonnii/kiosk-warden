#!/usr/bin/env python3
"""kiosk-warden web UI: setup + local control panel.

Stdlib-only on purpose (no pip installs needed on the kiosk). Binds to
0.0.0.0:8080 by default so it can be reached from other devices on the LAN
(e.g. a phone) — see README for restricting it to localhost instead.
"""
import base64
import hashlib
import hmac
import html
import http.server
import os
import re
import secrets
import shutil
import socketserver
import subprocess
import urllib.parse

HOME = os.path.expanduser("~")
KIOSK_DIR = os.path.join(HOME, "kiosk")
CONF_PATH = os.path.join(KIOSK_DIR, "kiosk.conf")
SCREENSHOT_PATH = os.path.join(KIOSK_DIR, "screenshots", "latest.jpg")

BIND_HOST = os.environ.get("KIOSK_WEBUI_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("KIOSK_WEBUI_PORT", "8080"))

os.environ.setdefault("DISPLAY", ":0")
os.environ.setdefault("XAUTHORITY", os.path.join(HOME, ".Xauthority"))

CONF_ORDER = [
    "KIOSK_NAME", "KIOSK_ID", "KIOSK_URL", "MQTT_HOST", "MQTT_PORT",
    "MQTT_USER", "MQTT_PASS", "BASE_TOPIC", "CODEX_REMOTE_TOPIC",
    "STATS_INTERVAL", "WEBUI_PASSWORD_HASH",
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
    "WEBUI_PASSWORD_HASH": "",
}


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


def validate_settings(fields):
    kiosk_id = fields.get("KIOSK_ID", [""])[0].strip()
    kiosk_url = fields.get("KIOSK_URL", [""])[0].strip()
    mqtt_port = fields.get("MQTT_PORT", [""])[0].strip()
    stats_interval = fields.get("STATS_INTERVAL", [""])[0].strip()
    if not re.match(r"^[a-z0-9_]+$", kiosk_id):
        return "Kiosk-id må kun indeholde a-z, 0-9 og _."
    if not re.match(r"^https?://", kiosk_url):
        return "URL skal starte med http:// eller https://."
    if not mqtt_port.isdigit():
        return "MQTT port skal være et tal."
    if not stats_interval.isdigit():
        return "Stats-interval skal være et tal."
    return None


def esc(value):
    return html.escape(str(value), quote=True)


PAGE_HEAD = """<!doctype html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kiosk Warden{title_suffix}</title>
<style>
  :root {{ color-scheme: light dark; --accent: #2563eb; --accent-2: #7c3aed; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: 680px; margin: 0 auto;
    padding: 1.4rem 1rem 3rem; line-height: 1.45;
  }}
  body.wide {{ max-width: min(1500px, 97vw); }}
  .brand {{
    display:flex; align-items:center; gap:.6rem; margin-bottom: 1.1rem;
  }}
  .brand .dot {{
    width:.6rem; height:.6rem; border-radius:50%;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: 0 0 0 4px rgba(124,58,237,.15);
  }}
  .brand span {{ font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; opacity:.55; font-weight:600; }}
  .header-row {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; flex-wrap:wrap; margin-bottom: .3rem; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .15rem; letter-spacing: -.01em; }}
  .sub {{ opacity: .6; font-size: .85rem; margin-bottom: 1.3rem; }}
  fieldset {{
    border: 1px solid rgba(128,128,128,.28); border-radius: 14px; margin-bottom: 1.1rem;
    padding: 1rem 1.1rem 1.2rem; background: rgba(128,128,128,.035);
  }}
  legend {{ padding: 0 .5rem; font-weight: 650; font-size: .95rem; }}
  label {{ display:block; margin-top:.75rem; font-size:.82rem; opacity: .8; }}
  input[type=text], input[type=password], input[type=number] {{
    width:100%; padding:.6rem .7rem; margin-top:.3rem; box-sizing:border-box;
    border-radius:9px; border:1px solid rgba(128,128,128,.4); font-size: 1rem;
    background: rgba(128,128,128,.05); color: inherit;
  }}
  input:focus {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
  .row {{ display:flex; gap:.5rem; flex-wrap:wrap; margin-top: .7rem; }}
  button {{
    padding:.65rem 1.15rem; border-radius:9px; border:1px solid rgba(128,128,128,.4);
    cursor:pointer; font-size:.92rem; font-weight:500; background: rgba(128,128,128,.08); color: inherit;
    transition: filter .1s ease;
  }}
  button:hover {{ filter: brightness(1.08); }}
  button.primary {{ background: linear-gradient(135deg, var(--accent), var(--accent-2)); color:#fff; border-color: transparent; }}
  button.danger {{ background:#dc2626; color:#fff; border-color:#dc2626; }}
  .msg {{ padding:.7rem 1rem; border-radius:10px; margin-bottom:1rem; font-size:.9rem; }}
  .msg.error {{ background:#fee2e2; color:#7f1d1d; }}
  .msg.ok {{ background:#dcfce7; color:#14532d; }}
  img.shot {{ max-width:100%; border-radius:12px; border:1px solid rgba(128,128,128,.3); display:block; }}
  .status {{ font-size:.85rem; opacity:.7; margin-top:.4rem; }}
  a {{ color: var(--accent); }}
  .pill {{
    padding:.3rem .75rem; border-radius:999px; font-size:.78rem; font-weight:650; white-space:nowrap;
  }}
  .pill.ok {{ background:#dcfce7; color:#14532d; }}
  .pill.err {{ background:#fee2e2; color:#7f1d1d; }}
  .pill.warn {{ background:#fef3c7; color:#78350f; }}
  .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(118px,1fr)); gap:.6rem; margin: 0 0 1.3rem; }}
  .tile {{
    background: rgba(128,128,128,.06); border:1px solid rgba(128,128,128,.22); border-radius: 12px;
    padding:.75rem .85rem;
  }}
  .tile-label {{ font-size:.68rem; text-transform:uppercase; letter-spacing:.06em; opacity:.55; margin-bottom:.25rem; font-weight:600; }}
  .tile-value {{ font-size:1.2rem; font-weight:650; }}
  .tile-value.small {{ font-size:.95rem; }}
</style>
</head>
<body class="{body_class}">
<div class="brand"><span class="dot"></span><span>Kiosk Warden</span></div>
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
    body = PAGE_HEAD.format(title_suffix=" — Opsætning", body_class="")
    body += "<h1>Velkommen til Kiosk Warden</h1>"
    body += '<div class="sub">Sæt et password for at beskytte opsætningssiden, før du gør noget andet.</div>'
    body += render_message(message, error)
    body += """
<form method="post" action="/set-password">
  <fieldset>
    <legend>Sæt password</legend>
    <label>Password (min. 8 tegn)</label>
    <input type="password" name="password" required minlength="8">
    <label>Gentag password</label>
    <input type="password" name="password2" required minlength="8">
    <div class="row"><button class="primary" type="submit">Gem password</button></div>
  </fieldset>
</form>
"""
    body += PAGE_TAIL
    return body


def render_dashboard(conf, message=None, error=None):
    health_state = read_file(os.path.join(KIOSK_DIR, "health_state"), "?")
    health_detail = read_file(os.path.join(KIOSK_DIR, "health_detail"), "")
    has_screenshot = os.path.exists(SCREENSHOT_PATH)
    stats = get_stats()

    pill_class = "ok" if health_state == "ON" else ("err" if health_state == "OFF" else "warn")
    pill_label = {"ON": "Kører fint", "OFF": "Fejl"}.get(health_state, health_state or "Ukendt")

    body = PAGE_HEAD.format(title_suffix=f" — {esc(conf.get('KIOSK_NAME', 'Kiosk'))}", body_class="")
    body += f"""
<div class="header-row">
  <div>
    <h1>{esc(conf.get('KIOSK_NAME', 'Kiosk'))}</h1>
    <div class="sub">Kiosk-id: {esc(conf.get("KIOSK_ID",""))}</div>
  </div>
  <span class="pill {pill_class}">{esc(pill_label)}</span>
</div>
"""
    body += render_message(message, error)

    chrome_label = "● Kører" if stats["chrome_running"] else "○ Stoppet"
    temp_val = f'{stats["cpu_temp"]}°C' if stats["cpu_temp"] is not None else "?"
    ram_val = f'{stats["ram_percent"]}%' if stats["ram_percent"] is not None else "?"
    disk_val = f'{stats["disk_percent"]}%' if stats["disk_percent"] is not None else "?"

    body += f"""
<div class="grid">
  <div class="tile"><div class="tile-label">IP</div><div class="tile-value small">{esc(stats["ip"])}</div></div>
  <div class="tile"><div class="tile-label">Oppetid</div><div class="tile-value small">{esc(stats["uptime"])}</div></div>
  <div class="tile"><div class="tile-label">RAM</div><div class="tile-value">{esc(ram_val)}</div></div>
  <div class="tile"><div class="tile-label">Disk</div><div class="tile-value">{esc(disk_val)}</div></div>
  <div class="tile"><div class="tile-label">Temp</div><div class="tile-value">{esc(temp_val)}</div></div>
  <div class="tile"><div class="tile-label">Load (1/5/15m)</div><div class="tile-value small">{esc(stats["loadavg"])}</div></div>
  <div class="tile"><div class="tile-label">Chrome</div><div class="tile-value small">{esc(chrome_label)}</div></div>
  <div class="tile"><div class="tile-label">Model</div><div class="tile-value small">{esc(stats["model"])}</div></div>
</div>
"""

    if has_screenshot:
        body += f'<img class="shot" src="/screenshot.jpg?_={secrets.token_hex(4)}" alt="Seneste screenshot">'
        body += f'<div class="status">{esc(health_detail)}</div>'

    body += """
<fieldset>
  <legend>Handlinger</legend>
  <div class="row">
    <form method="post" action="/action"><input type="hidden" name="do" value="reload"><button type="submit">Genindlæs side</button></form>
    <form method="post" action="/action"><input type="hidden" name="do" value="restart_chrome"><button type="submit">Genstart Chrome</button></form>
    <form method="post" action="/action"><input type="hidden" name="do" value="screenshot"><button type="submit">Tag screenshot</button></form>
    <form method="post" action="/action"><input type="hidden" name="do" value="backup"><button type="submit">Backup config</button></form>
    <a href="/vnc"><button type="button">Fjernstyring (VNC)</button></a>
  </div>
  <div class="row">
    <form method="post" action="/action" onsubmit="return confirm('Genstarte maskinen nu?');"><input type="hidden" name="do" value="reboot"><button class="danger" type="submit">Genstart maskine</button></form>
    <form method="post" action="/action" onsubmit="return confirm('Slukke maskinen nu?');"><input type="hidden" name="do" value="shutdown"><button class="danger" type="submit">Sluk maskine</button></form>
  </div>
</fieldset>
"""

    body += f"""
<form method="post" action="/save">
  <fieldset>
    <legend>Opsætning</legend>
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
    <div class="row"><button class="primary" type="submit">Gem og genstart</button></div>
  </fieldset>
</form>

<form method="post" action="/change-password">
  <fieldset>
    <legend>Skift password</legend>
    <label>Nyt password (min. 8 tegn)</label>
    <input type="password" name="password" required minlength="8">
    <label>Gentag nyt password</label>
    <input type="password" name="password2" required minlength="8">
    <div class="row"><button type="submit">Skift password</button></div>
  </fieldset>
</form>
"""
    body += PAGE_TAIL
    return body


def render_vnc(conf):
    body = PAGE_HEAD.format(title_suffix=" — Fjernstyring", body_class="wide")
    body += f"""
<div class="header-row">
  <div>
    <h1>Fjernstyring</h1>
    <div class="sub"><a href="/">&larr; Tilbage til {esc(conf.get('KIOSK_NAME','Kiosk'))}</a></div>
  </div>
</div>
"""
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
    return 'http://' + location.hostname + ':6080/vnc.html?autoconnect=true&resize=scale&reconnect=true&_=' + Date.now();
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
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Kiosk Warden"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Login required")

    def _authenticated(self, conf):
        stored = conf.get("WEBUI_PASSWORD_HASH", "")
        if not stored:
            return False
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode()
        except Exception:
            return False
        _, _, pw = decoded.partition(":")
        return verify_password(pw, stored)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        conf = read_conf()
        password_set = bool(conf.get("WEBUI_PASSWORD_HASH"))

        if not password_set:
            if parsed.path in ("/", ""):
                return self._send_html(render_first_run())
            self.send_response(404)
            self.end_headers()
            return

        if not self._authenticated(conf):
            return self._require_auth()

        if parsed.path == "/screenshot.jpg":
            return self._serve_screenshot()
        if parsed.path == "/vnc":
            return self._send_html(render_vnc(conf))
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
            pw = fields.get("password", [""])[0]
            pw2 = fields.get("password2", [""])[0]
            if len(pw) < 8 or pw != pw2:
                return self._send_html(render_first_run(error="Password skal være mindst 8 tegn og matche i begge felter."))
            conf["WEBUI_PASSWORD_HASH"] = hash_password(pw)
            write_conf(conf)
            return self._redirect("/")

        if not password_set:
            self.send_response(404)
            self.end_headers()
            return

        if not self._authenticated(conf):
            return self._require_auth()

        if parsed.path == "/save":
            err = validate_settings(fields)
            if err:
                return self._send_html(render_dashboard(conf, error=err))
            for key in ["KIOSK_NAME", "KIOSK_ID", "KIOSK_URL", "MQTT_HOST", "MQTT_USER", "MQTT_PORT", "STATS_INTERVAL"]:
                if key in fields:
                    conf[key] = fields[key][0].strip()
            pw = fields.get("MQTT_PASS", [""])[0]
            if pw:
                conf["MQTT_PASS"] = pw
            conf["BASE_TOPIC"] = f'home/kiosk/{conf["KIOSK_ID"]}'
            conf["CODEX_REMOTE_TOPIC"] = f'home/codex/{conf["KIOSK_ID"]}/remote_control'
            write_conf(conf)
            run("systemctl", "--user", "restart", "kiosk-mqtt-stats.service", "kiosk-mqtt-control.service")
            run("systemctl", "--user", "restart", "kiosk-chrome.service", "kiosk-watchdog.service", "kiosk-health.service")
            run(os.path.join(KIOSK_DIR, "mqtt-discovery.sh"))
            return self._redirect("/")

        if parsed.path == "/change-password":
            pw = fields.get("password", [""])[0]
            pw2 = fields.get("password2", [""])[0]
            if len(pw) < 8 or pw != pw2:
                return self._send_html(render_dashboard(conf, error="Password skal være mindst 8 tegn og matche i begge felter."))
            conf["WEBUI_PASSWORD_HASH"] = hash_password(pw)
            write_conf(conf)
            return self._send_html(render_dashboard(conf, message="Password skiftet."))

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
            elif action == "reboot":
                run_bg("sudo", "/sbin/reboot")
            elif action == "shutdown":
                run_bg("sudo", "/sbin/poweroff")
            return self._redirect("/")

        self.send_response(404)
        self.end_headers()

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


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    os.makedirs(KIOSK_DIR, exist_ok=True)
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
