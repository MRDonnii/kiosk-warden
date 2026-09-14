#!/usr/bin/env python3
"""Apply cycle or daily time-based kiosk profile automation."""
import json, pathlib, subprocess, time

HOME=pathlib.Path.home(); KIOSK=HOME/"kiosk"; PROFILES=KIOSK/"profiles.json"; ACTIVE=KIOSK/"active_profile"; STATE=KIOSK/"profile_automation_state.json"

def read_json(path, fallback):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return fallback

def switch(name):
    active=ACTIVE.read_text().strip() if ACTIVE.exists() else ""
    if name != active:
        subprocess.run([str(KIOSK/"profile-manager.py"),"switch",name],check=False,timeout=20)

def tick(now=None):
    now=now or time.time(); data=read_json(PROFILES,{"profiles":[]}); profiles=data.get("profiles",[]); automation=data.get("automation",{})
    if not automation.get("enabled") or len(profiles)<2: return
    mode=automation.get("mode","cycle")
    if mode=="cycle":
        state=read_json(STATE,{}); last=int(state.get("last_switch",0) or 0); interval=max(1,int(automation.get("cycle_minutes",15)))*60
        if not last: STATE.write_text(json.dumps({"last_switch":int(now)})+"\n"); return
        if now-last>=interval:
            active=ACTIVE.read_text().strip() if ACTIVE.exists() else profiles[0]["name"]
            names=[x["name"] for x in profiles]; switch(names[(names.index(active)+1)%len(names)] if active in names else names[0])
    elif mode=="schedule":
        entries=automation.get("schedule",[])
        if not entries: return
        current=time.strftime("%H:%M",time.localtime(now)); eligible=[x for x in entries if x["time"]<=current]
        switch((eligible[-1] if eligible else entries[-1])["profile"])

if __name__=="__main__":
    while True:
        try: tick()
        except Exception: pass
        time.sleep(15)
