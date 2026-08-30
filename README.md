# kiosk-warden

Self-healing Ubuntu Chrome kiosk with full Home Assistant MQTT control — a
scripted, TouchKio-style parity layer built on bash + systemd instead of
Electron.

Turns a plain Ubuntu desktop machine into a kiosk that:

- Boots straight into Chrome, fullscreen, on a URL you choose.
- Publishes CPU/RAM/temperature/uptime/IP stats to MQTT every N seconds.
- Exposes Home Assistant MQTT-discovery entities: screen on/off, window mode
  (Kiosk/Fullscreen/Windowed), theme, zoom, volume, on-screen keyboard, URL
  text field, reboot/shutdown/refresh buttons, screenshot image entity, and
  health/diagnostic sensors.
- Watches itself: a health-check loop polls Chrome via remote debugging every
  20s, reloads on a blank/error page, and restarts Chrome after repeated
  failures. A separate watchdog restarts Chrome if the process dies outright.
- Takes on-demand screenshots and config backups, both triggerable from
  Home Assistant.
- Ships a small built-in **web UI** for setup and local control — no SSH or
  terminal needed after the first install.
- Bundles browser-based **VNC remote control** (x11vnc + noVNC): click
  directly on the kiosk's screen from the web UI, including a fullscreen
  toggle.
- Ships its own icon (`icon.svg`) — used as the browser favicon and as the
  icon for both desktop shortcuts.

## Install

On a fresh Ubuntu Desktop machine, logged in as the user that should run the
kiosk:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/MRDonnii/kiosk-warden/main/install.sh)
```

The installer asks for kiosk name/id, the URL to display, and your MQTT
broker host/user/password (input is read from your terminal even when piped
through `curl`). You can skip the prompts by pre-setting environment
variables before running it:

```bash
KIOSK_NAME="Kitchen" KIOSK_ID="kiosk_kitchen" KIOSK_URL="http://homeassistant.local:8123" \
MQTT_HOST="192.168.1.10" MQTT_USER="local" MQTT_PASS="secret" \
bash <(curl -fsSL https://raw.githubusercontent.com/MRDonnii/kiosk-warden/main/install.sh)
```

What it does:

- Installs required apt packages and Google Chrome (adds Google's apt repo
  if missing).
- Copies the scripts to `~/kiosk/` and unit files to
  `~/.config/systemd/user/`.
- Writes `~/kiosk/kiosk.conf` from your answers (never overwrites an
  existing one).
- Enables and starts the systemd **user** services.
- Adds a passwordless sudo rule for `reboot`/`poweroff` only.
- Masks sleep/suspend/hibernate so the screen never sleeps.
- Sets GDM to X11 and enables autologin for your user (Wayland is disabled;
  touch/kiosk automation needs X11).
- Installs the web UI (`~/kiosk/webui/server.py`) as a systemd user service
  on port 8080.
- Adds two desktop shortcuts: **Start Kiosk** (restarts Chrome + the
  watchdog) and **Kiosk Setup** (opens the web UI in a browser).

A reboot after install is recommended so GDM autologin and the boot-time
services take effect.

## Web UI (setup + control)

The installer starts a small web server on the kiosk itself:

```
http://localhost:8080         — from the kiosk machine
http://<kiosk-ip>:8080        — from any device on the same network (phone, laptop)
```

It binds to `0.0.0.0` by default so you can finish setup from your phone
without plugging in a keyboard. **The first thing you must do is open it and
set a password** — until a password is set, the page only shows the
password form (nothing else is reachable), and once it's set every page
requires HTTP Basic Auth. Because the port is reachable from your whole LAN,
don't leave that first-run window open longer than necessary.

From the web UI you can:

- Edit `KIOSK_NAME`, `KIOSK_ID`, `KIOSK_URL`, MQTT host/port/user/password,
  and the stats interval — saving restarts the affected services and
  re-publishes Home Assistant discovery automatically.
- Reload the page, restart Chrome, take a screenshot (shown inline), trigger
  a config backup, or reboot/shut down the machine.
- Change the web UI password.

If you'd rather keep it off the network entirely, set `KIOSK_WEBUI_HOST=127.0.0.1`
as an `Environment=` line in `~/.config/systemd/user/kiosk-webui.service`
and run `systemctl --user restart kiosk-webui.service`.

## Remote control (VNC)

The installer sets up `x11vnc` (shares the live X11 session, protected by a
VNC password you set during install) and bridges it to the browser with
`noVNC` + `websockify`:

- Raw VNC (for a normal VNC client like TigerVNC/RealVNC): `<kiosk-ip>:5900`
- Browser-based (noVNC): `http://<kiosk-ip>:6080/vnc.html`
- Or just click **Fjernstyring (VNC)** on the web UI dashboard, which embeds
  the same viewer with a fullscreen button — you can click directly on the
  kiosk's screen from your phone or laptop.

The VNC password is separate from the web UI password — it's asked for
(or auto-generated and printed once) during `install.sh`, and stored in
`~/.vnc/passwd`. Services: `kiosk-vnc.service` (x11vnc) and
`kiosk-novnc.service` (the web bridge on port 6080).

To change the VNC password later:

```bash
x11vnc -storepasswd <new-password> ~/.vnc/passwd
systemctl --user restart kiosk-vnc.service
```

## Layout

```
scripts/    the kiosk scripts, installed to ~/kiosk/
webui/      the web UI (Python 3 stdlib, no pip installs), installed to ~/kiosk/webui/
systemd/    user service units, installed to ~/.config/systemd/user/
install.sh  the installer above
kiosk.conf.example  reference for the config file the installer generates
```

## Config

Everything lives in `~/kiosk/kiosk.conf` (not tracked in git — see
`kiosk.conf.example`):

```bash
KIOSK_NAME="My Kiosk"
KIOSK_ID="my_kiosk"
KIOSK_URL="http://homeassistant.local:8123"
MQTT_HOST="127.0.0.1"
MQTT_PORT=1883
MQTT_USER=""
MQTT_PASS=""
BASE_TOPIC="home/kiosk/my_kiosk"
CODEX_REMOTE_TOPIC="home/codex/my_kiosk/remote_control"
STATS_INTERVAL=10
```

After editing it by hand, restart the affected services and re-run
discovery:

```bash
systemctl --user restart kiosk-chrome.service kiosk-mqtt-stats.service kiosk-mqtt-control.service
~/kiosk/mqtt-discovery.sh
```

`CODEX_REMOTE_TOPIC` drives an optional "Genstart Codex Remote" button that
restarts a `codex-remote-control.service` unit if you happen to run one; it's
a harmless no-op otherwise.

## MQTT topics

Base topic: `home/kiosk/<KIOSK_ID>`

```
.../online/status
.../stats/*            (cpu_load, ram_used, cpu_temperature, uptime, ip_address, ...)
.../state/*            (url, window_mode, screen, keyboard, theme, page_zoom, volume, ...)
.../health/status       ON/OFF
.../health/detail
.../diagnostic/*        (errors, heartbeat, version, last_backup, last_recovery, ...)
.../command             (reload, hard_reload, restart_chrome, screen_on, screen_off,
                          fullscreen, home, reboot, shutdown, screenshot, backup,
                          Kiosk/Fullscreen/Windowed, Dark/Light/Auto, or a raw http(s) URL)
.../set_url
.../set_zoom
.../set_theme
.../set_volume
.../image/screenshot    (retained JPEG, also mirrored to homeassistant/image/... discovery)
```

Test manually:

```bash
mosquitto_sub -h <MQTT_HOST> -t 'home/kiosk/<KIOSK_ID>/#' -v
mosquitto_pub -h <MQTT_HOST> -t 'home/kiosk/<KIOSK_ID>/command' -m reload
```

## Services

```bash
systemctl --user status  kiosk-chrome kiosk-mqtt-stats kiosk-mqtt-control kiosk-watchdog kiosk-health kiosk-webui kiosk-vnc kiosk-novnc
systemctl --user restart kiosk-chrome kiosk-mqtt-stats kiosk-mqtt-control kiosk-watchdog kiosk-health kiosk-webui kiosk-vnc kiosk-novnc
```

## Multi-machine

`KIOSK_ID` namespaces everything (MQTT topics, HA unique_ids, sudoers file
name is shared but scoped to the local user), so you can run the installer
on as many kiosks as you like against the same broker — just give each one
a distinct `KIOSK_ID`.
