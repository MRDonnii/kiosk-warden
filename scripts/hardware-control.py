#!/usr/bin/env python3
"""Capability-gated brightness, microphone, illuminance and battery I/O."""
import json, pathlib, subprocess, sys
KIOSK = pathlib.Path.home() / "kiosk"; CAPS = KIOSK / "capabilities.json"

def caps():
    try: return json.loads(CAPS.read_text())
    except (OSError, ValueError): return {}
def run(*args): return subprocess.run(args, capture_output=True, text=True, timeout=10)
def read_num(path): return float(pathlib.Path(path).read_text().strip())
def brightness_get(c):
    d=c.get("display", {}); backend=d.get("brightness_backend")
    if backend=="sysfs":
        path=pathlib.Path(d["brightness_path"]); maximum=read_num(path.parent/"max_brightness"); return round(read_num(path)*100/maximum)
    if backend=="ddc":
        out=run("ddcutil","getvcp","10","--brief").stdout
        parts=[int(x) for x in out.split() if x.isdigit()]; return round(parts[-2]*100/parts[-1]) if len(parts)>=2 else None
def brightness_set(c, value):
    value=max(1,min(100,int(value))); d=c.get("display", {}); backend=d.get("brightness_backend")
    if backend=="sysfs":
        path=pathlib.Path(d["brightness_path"]); maximum=read_num(path.parent/"max_brightness"); path.write_text(str(round(maximum*value/100))+"\n"); return value
    if backend=="ddc":
        result=run("ddcutil","setvcp","10",str(value)); return value if result.returncode==0 else None
def microphone_get(c):
    if not c.get("audio",{}).get("microphone"): return None
    out=run("pactl","get-source-volume","@DEFAULT_SOURCE@").stdout
    import re; match=re.search(r"(\d+)%",out); return int(match.group(1)) if match else None
def microphone_set(c,value):
    if not c.get("audio",{}).get("microphone"): return None
    value=max(0,min(100,int(value))); r=run("pactl","set-source-volume","@DEFAULT_SOURCE@",f"{value}%"); return value if r.returncode==0 else None
def sensor_get(c,name):
    section=c.get("sensors",{}); path=section.get(name+"_path")
    return read_num(path) if section.get(name) and path else None

def main():
    c=caps(); action=sys.argv[1] if len(sys.argv)>1 else "status"; value=sys.argv[2] if len(sys.argv)>2 else None
    if action=="brightness-get": result=brightness_get(c)
    elif action=="brightness-set": result=brightness_set(c,value)
    elif action=="microphone-get": result=microphone_get(c)
    elif action=="microphone-set": result=microphone_set(c,value)
    elif action=="illuminance-get": result=sensor_get(c,"illuminance")
    elif action=="battery-get": result=sensor_get(c,"battery")
    else: print("Usage: hardware-control.py brightness-get|brightness-set N|microphone-get|microphone-set N|illuminance-get|battery-get",file=sys.stderr); return 2
    if result is None: return 1
    print(result); return 0
if __name__=="__main__": raise SystemExit(main())
