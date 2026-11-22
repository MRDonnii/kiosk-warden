#!/usr/bin/env python3
"""Probe usable kiosk capabilities without changing hardware state."""
import glob, json, os, pathlib, platform, re, shutil, subprocess, sys, time

HOME = pathlib.Path.home(); KIOSK = HOME / "kiosk"

def run(*args, timeout=4):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""

def readable(pattern):
    return next((p for p in glob.glob(pattern) if os.access(p, os.R_OK)), None)

def writable(pattern):
    return next((p for p in glob.glob(pattern) if os.access(p, os.R_OK | os.W_OK)), None)

def touch():
    listing = run("xinput", "list") if os.environ.get("DISPLAY") else ""
    line = next((x for x in listing.splitlines() if "touch" in x.lower()), "")
    match = re.search(r"id=(\d+)", line)
    props = run("xinput", "list-props", match.group(1)) if match else ""
    node = re.search(r'Device Node[^:]*:\s*"([^"]+)"', props)
    path = node.group(1) if node else ""
    return {"available": bool(match), "name": re.sub(r".*↳\s*|\s+id=\d+.*", "", line).strip() or None,
            "device": path or None, "guardian": bool(path and shutil.which("evtest") and os.access(path, os.R_OK))}

def probe():
    model = ""
    for path in ("/sys/devices/virtual/dmi/id/product_name", "/proc/device-tree/model"):
        try: model = pathlib.Path(path).read_text(errors="ignore").replace("\0", "").strip()
        except OSError: pass
        if model: break
    backlight = writable("/sys/class/backlight/*/brightness")
    ambient = readable("/sys/bus/iio/devices/*/in_illuminance_*input") or readable("/sys/bus/iio/devices/*/in_illuminance_raw")
    ddc = False
    if shutil.which("ddcutil"):
        ddc = "Display" in run("ddcutil", "detect", "--brief", timeout=8)
    source = run("pactl", "get-default-source") if shutil.which("pactl") else ""
    sink = run("pactl", "get-default-sink") if shutil.which("pactl") else ""
    battery = readable("/sys/class/power_supply/BAT*/capacity")
    session = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    data = {
        "schema": 1, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": {"architecture": platform.machine(), "model": model or platform.node(), "session": session, "desktop": desktop},
        "display": {
            "x11": bool(shutil.which("xrandr") and os.environ.get("DISPLAY")),
            "wayland_wlopm": bool(shutil.which("wlopm") and session == "wayland"),
            "wayland_kde": bool(shutil.which("kscreen-doctor") and session == "wayland"),
            "raspberry_pi": "raspberry pi" in model.lower(), "ddc": ddc,
            "cec": bool(shutil.which("cec-client")), "brightness": bool(backlight or ddc),
            "brightness_backend": "sysfs" if backlight else "ddc" if ddc else None,
            "brightness_path": backlight,
        },
        "touch": touch(),
        "sensors": {"illuminance": bool(ambient), "illuminance_path": ambient,
                    "battery": bool(battery), "battery_path": battery},
        "audio": {"output": bool(sink), "sink": sink or None, "microphone": bool(source), "source": source or None},
        "capture": {"screenshot": bool(shutil.which("gnome-screenshot") or shutil.which("import") or shutil.which("xwd"))},
    }
    return data

if __name__ == "__main__":
    result = probe(); target = KIOSK / "capabilities.json"
    if len(sys.argv) > 1 and sys.argv[1] == "--stdout": print(json.dumps(result)); raise SystemExit()
    target.parent.mkdir(parents=True, exist_ok=True); tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2) + "\n"); tmp.replace(target); print(json.dumps(result))
