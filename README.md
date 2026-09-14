# kiosk-warden

## Kiosk lifecycle and recovery

Warden uses a locked state machine (`OFF`, `WAKING`, `ON`, `SLEEPING`, and
`RECOVERING`). A wake is shown only after the minimum resolution, expected
Chrome URL, completed document, renderer state, dashboard width, and a
non-blank screenshot have been verified. Recovery proceeds through resize,
renderer resume, reload, and finally a Chrome restart.

The Control page can run a real OFF→ON acceptance test and create a sanitized
diagnostics ZIP. Updates run the same test and restore their pre-update snapshot
if it does not pass before the deadline.

Choose display control with `KIOSK_SCREEN_BACKEND`: `auto` (recommended),
`gnome-x11`, `cinnamon-x11`, `x11`, `raspberry-pi`, `ddc`, or `cec`. Local
WebUI, VNC, and noVNC ports are configurable in Settings and conflict-checked.
Browser cleanup is restricted to Wardens dedicated `~/.config/chrome-kiosk`
profile. Diagnostics never include `kiosk.conf` and redact common password,
token, and Authorization patterns.

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
- Turns on a touch on-screen keyboard by default on install, using
  `onboard` so it works the same on GNOME, Cinnamon (Linux Mint), MATE, or
  Xfce — toggle it off/on later from the web UI or Home Assistant.
- Watches itself: a health-check loop polls Chrome via remote debugging every
  20s, reloads on a blank/error page, and restarts Chrome after repeated
  failures. A separate watchdog restarts Chrome if the process dies outright.
- Takes on-demand screenshots and config backups, both triggerable from
  Home Assistant.
- Ships a small built-in **web UI** for setup and local control — no SSH or
  terminal needed after the first install.
- Bundles browser-based **VNC remote control** (x11vnc + noVNC): click
  directly on the kiosk's screen from the web UI, including a fullscreen
  toggle. VNC only runs after you press **Start VNC**, and it stops when the
  remote-control page is closed.
- Ships its own icon (`icon.svg`) — used as the browser favicon and as the
  icon for both desktop shortcuts.
- Uses monitor DPMS for reliable presence-driven sleep while Smartdash remains
  paintable. Repeated ON commands never restart a healthy Chrome process;
  restart recovery is reserved for a missing process or dashboard page.
- The animation, live-camera, and rendering pause bridge only works with **HA
  Smartdash**. Screen DPMS control still works for other dashboards, but
  Warden cannot pause their internal visual work.
- Publishes retained `Smartdash Connection` diagnostics and an available-only
  `Smartdash Rendering` MQTT switch in Home Assistant. The switch sends
  `active`/`idle` through the same local Chrome bridge used by automatic screen
  control.
- Uses GitHub Releases with selectable Stable/Beta channels, semantic
  versions, release notes, automatic pre-update snapshots, and rollback.
- Provides a dedicated **Updates** page in the web UI with channel selection,
  release details, install controls, snapshot history, rollback, and the full
  changelog.
- Shows persistent stage-by-stage update progress, offers reboot now/later,
  and displays a five-second countdown before an update-triggered reboot.

## Install

Supported desktop platforms include Ubuntu, Linux Mint, Debian-derived desktop
systems, and Raspberry Pi OS Desktop on `amd64`, `arm64`, or `armhf`. The
installer selects Google Chrome on `amd64` and Chromium on ARM. Raspberry Pi OS
Bookworm and newer default to Wayland; Kiosk Warden switches Raspberry Pi OS to
the X11/Openbox backend during installation because its DPMS, xdotool,
screenshot, and x11vnc controls currently require X11. Reboot after installation
to activate that change. Raspberry Pi OS Lite is not supported without first
installing a desktop environment.

On a fresh Ubuntu Desktop machine, logged in as the user that should run the
kiosk:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/MRDonnii/kiosk-warden/main/install.sh)
```

Early on it asks: **configure now in the terminal, or skip and finish later
in the web UI?** Answering no (or piping in `CONFIGURE_NOW=no`) installs
everything with placeholder values and skips straight to the apt/systemd
setup — you then create the administrator login and open the web UI's Settings page to set the
real kiosk name/URL/MQTT details and passwords. Answering yes asks for kiosk
name/id, the URL to display, MQTT broker host/user/password, and a VNC
password (input is read from your terminal even when piped through `curl`).

You can skip all of it non-interactively by pre-setting environment
variables before running it (this also skips the corresponding prompts even
when `CONFIGURE_NOW` isn't set):

```bash
KIOSK_NAME="Kitchen" KIOSK_ID="kiosk_kitchen" KIOSK_URL="http://homeassistant.local:8123" \
MQTT_HOST="192.168.1.10" MQTT_USER="local" MQTT_PASS="secret" \
KIOSK_WEBUI_PORT="8081" \
bash <(curl -fsSL https://raw.githubusercontent.com/MRDonnii/kiosk-warden/main/install.sh)
```

Or force the terminal question itself to a fixed answer:

```bash
CONFIGURE_NOW=no bash <(curl -fsSL https://raw.githubusercontent.com/MRDonnii/kiosk-warden/main/install.sh)
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
- Installs `onboard` and enables it as the on-screen keyboard by default
  (falls back to GNOME's own accessibility keyboard only when GNOME Shell
  is actually the desktop in use).
- Detects the display manager and sets up autologin for your user
  accordingly: GDM (Ubuntu/GNOME, X11 forced — touch/kiosk automation needs
  it) or LightDM (Linux Mint and others).
- Installs the web UI (`~/kiosk/webui/server.py`) as a systemd user service.
  Port 8080 is used by default; if it is occupied, the interactive installer
  asks for another port. Non-interactive installs set `KIOSK_WEBUI_PORT`.
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

The port can be changed later under **Settings → Web UI port**. Warden checks
that the new port is valid and free, restarts only the Web UI after returning
the confirmation page, and redirects the browser to the new address. If a host
firewall is enabled, the new TCP port must also be allowed there.

It binds to `0.0.0.0` by default so you can finish setup from your phone
without plugging in a keyboard. **The first thing you must do is open it and
create an administrator username and password** — until a login is created,
the page only shows that setup form (nothing else is reachable). Afterwards,
the built-in login page creates a private, signed browser session that survives
WebUI restarts and updates. **Remember me** keeps it for up to 30 days; changing
the administrator password invalidates existing sessions. Every page remains
protected. Because the port is reachable from your whole LAN,
don't leave that first-run window open longer than necessary.

From the web UI you can:

- Use English by default or switch the complete interface to Danish from
  **Settings → Interface language**. The selection persists across updates.
- Monitor CPU, RAM, Intel GPU activity, CPU frequency, CPU/NVMe temperatures
  and network throughput with live status tiles and one-hour history graphs on
  Overview. Samples are retained in memory for up to six hours.
- Edit `KIOSK_NAME`, `KIOSK_ID`, `KIOSK_URL`, MQTT host/port/user/password,
  and the stats interval — saving restarts the affected services and
  re-publishes Home Assistant discovery automatically.
- Use the dedicated **Styring** page to reload the dashboard, restart Chrome
  or all Kiosk Warden services, take a screenshot, create a config backup, or
  reboot/shut down the machine. The latest screenshot is displayed on the same
  page, keeping Overview focused on essential live status.
- Switch the machine between **Strømbesparelse**, **Balanceret** and **Ydelse**;
  the same power-profile control is published to Home Assistant over MQTT.
- Change the web UI password.

If you'd rather keep it off the network entirely, set `KIOSK_WEBUI_HOST=127.0.0.1`
as an `Environment=` line in `~/.config/systemd/user/kiosk-webui.service`
and run `systemctl --user restart kiosk-webui.service`.

## Remote control (VNC)

The installer sets up `x11vnc` (shares the live X11 session) and bridges it to
the browser with `noVNC` + `websockify`:

- Raw VNC (for a normal VNC client like TigerVNC/RealVNC): `<kiosk-ip>:5900`
- Browser-based (noVNC): `http://<kiosk-ip>:6080/vnc.html`
- Or just click **Fjernstyring (VNC)** on the web UI dashboard, which embeds
  the same viewer with a fullscreen button — you can click directly on the
  kiosk's screen from your phone or laptop.

The VNC password is managed automatically from your Kiosk Warden login. The
WebUI embeds noVNC with that password, so you do not have to enter a separate
VNC password. VNC can connect while the physical display is OFF because
`x11vnc` keeps polling the framebuffer with DPMS handling disabled.

VNC is disabled by default. The Remote Control page starts both services only
when you press **Start VNC**, switches the same button to **Stop VNC** while
they are active, and sends a close beacon when the tab leaves or closes. A
short heartbeat timeout also stops the services if that beacon is missed.
Services: `kiosk-vnc.service` (x11vnc) and `kiosk-novnc.service` (the web
bridge on port 6080). Changing the WebUI login password also updates the VNC
password.

## Updating

Click **⬇️ Tjek og opdater fra GitHub** under Indstillinger in the web UI —
it pulls the latest commit, replaces the scripts/web UI/systemd units in
place, and restarts the affected services. The current version (short
commit hash) is shown right above the button; release notes are on the
**Nyheder** tab (rendered from `CHANGELOG.md`).

It also shows up in Home Assistant: a `update.kiosk_..._update` entity
reports `installed_version`/`latest_version` (checked every 30 minutes) and
its **Install** button triggers the same update over MQTT — no need to open
the web UI at all. Both paths run `scripts/self-update.sh` in its own
`systemd-run --user` scope, so it survives restarting `kiosk-webui.service`
or `kiosk-mqtt-control.service` on itself.

## Layout

```
scripts/    the kiosk scripts, installed to ~/kiosk/ (includes self-update.sh)
webui/      the web UI (Python 3 stdlib, no pip installs), installed to ~/kiosk/webui/
systemd/    user service units, installed to ~/.config/systemd/user/
install.sh  the installer above
icon.svg    logo used as favicon and desktop-shortcut icon
CHANGELOG.md  shown in the web UI's Nyheder tab
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

Both `KIOSK_ID` and `BASE_TOPIC` can also be changed later from Settings.
Changing `KIOSK_ID` updates the Codex remote topic; `BASE_TOPIC` stays exactly
as entered, so custom MQTT layouts are preserved.

## MQTT topics

Base topic: `home/kiosk/<KIOSK_ID>`

```
.../online/status
.../stats/*            (cpu_load, ram_used, cpu_temperature, uptime, ip_address, ...)
.../state/*            (url, window_mode, screen, keyboard, theme, page_zoom, volume, power_profile, ...)
.../health/status       ON/OFF
.../health/detail
.../diagnostic/*        (errors, heartbeat, version, last_backup, last_recovery, ...)
.../stats/web_ui_url    (complete Web UI address, for example http://192.0.2.10:8080)
.../command             (reload, hard_reload, restart_chrome, restart_warden, screen_on, screen_off,
                          fullscreen, home, reboot, shutdown, screenshot, backup,
                          Kiosk/Fullscreen/Windowed, Dark/Light/Auto, or a raw http(s) URL)
.../set_url
.../set_zoom
.../set_theme
.../set_volume
.../set_power_profile   (Strømbesparelse, Balanceret or Ydelse)
.../image/screenshot    (retained JPEG, also mirrored to homeassistant/image/... discovery)
.../update/state        (JSON: installed_version/latest_version, checked every 30 min)
.../update/install      (send "install" to trigger self-update.sh, same as the HA update entity's button)
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
