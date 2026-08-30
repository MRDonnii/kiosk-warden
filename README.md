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
- Adds a "Start Kiosk" desktop shortcut that restarts Chrome + the watchdog.

A reboot after install is recommended so GDM autologin and the boot-time
services take effect.

## Layout

```
scripts/    the kiosk scripts, installed to ~/kiosk/
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
systemctl --user status  kiosk-chrome kiosk-mqtt-stats kiosk-mqtt-control kiosk-watchdog kiosk-health
systemctl --user restart kiosk-chrome kiosk-mqtt-stats kiosk-mqtt-control kiosk-watchdog kiosk-health
```

## Multi-machine

`KIOSK_ID` namespaces everything (MQTT topics, HA unique_ids, sudoers file
name is shared but scoped to the local user), so you can run the installer
on as many kiosks as you like against the same broker — just give each one
a distinct `KIOSK_ID`.
