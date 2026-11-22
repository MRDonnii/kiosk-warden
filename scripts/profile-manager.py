#!/usr/bin/env python3
"""Manage named kiosk URL/zoom profiles without exposing kiosk.conf secrets."""
import json, pathlib, re, subprocess, sys, time
HOME=pathlib.Path.home(); KIOSK=HOME/"kiosk"; PATH=KIOSK/"profiles.json"; CONF=KIOSK/"kiosk.conf"; ACTIVE=KIOSK/"active_profile"; ZOOM_FILE=KIOSK/"page_zoom"
AUTOMATION_DEFAULT={"enabled":False,"mode":"cycle","cycle_minutes":15,"cycle_profiles":[],"schedule":[]}

def config():
    out={}
    try:
        for line in CONF.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k,v=line.split("=",1); out[k.strip()]=v.strip().strip('"')
    except OSError: pass
    return out
def load():
    try: data=json.loads(PATH.read_text())
    except (OSError,ValueError): data={"profiles":[]}
    if not data.get("profiles"):
        data={"profiles":[{"name":"Default","url":config().get("KIOSK_URL","http://homeassistant.local:8123"),"zoom":100}]}
    data["automation"]={**AUTOMATION_DEFAULT,**(data.get("automation") or {})}; save(data)
    return data
def save(data):
    tmp=PATH.with_suffix(".tmp"); tmp.write_text(json.dumps(data,indent=2)+"\n"); tmp.replace(PATH)
ZOOMS={50:(5,"ctrl+minus"),75:(3,"ctrl+minus"),90:(1,"ctrl+minus"),100:(0,""),110:(1,"ctrl+plus"),125:(2,"ctrl+plus"),150:(4,"ctrl+plus"),175:(6,"ctrl+plus"),200:(7,"ctrl+plus")}
def valid(name,url,zoom):
    return bool(re.fullmatch(r"[A-Za-z0-9 ÆØÅæøå._-]{1,40}", name) and re.fullmatch(r"https?://[^\s\"'\\]+", url) and int(zoom) in ZOOMS)
def set_conf_url(url):
    lines=CONF.read_text().splitlines(); found=False; out=[]
    for line in lines:
        if line.startswith("KIOSK_URL="): out.append(f'KIOSK_URL="{url}"'); found=True
        else: out.append(line)
    if not found: out.append(f'KIOSK_URL="{url}"')
    tmp=CONF.with_suffix(".tmp"); tmp.write_text("\n".join(out)+"\n"); tmp.chmod(0o600); tmp.replace(CONF)
def switch(name):
    item=next((x for x in load()["profiles"] if x["name"]==name),None)
    if not item: return 1
    set_conf_url(item["url"]); ACTIVE.write_text(name+"\n")
    (KIOSK/"profile_automation_state.json").write_text(json.dumps({"last_switch":int(time.time()),"profile":name})+"\n")
    subprocess.run([str(KIOSK/"chrome-lifecycle.py"),"navigate",item["url"]],check=False)
    zoom=int(item.get("zoom",100)); ZOOM_FILE.write_text(str(zoom)+"\n")
    return 0
def set_active_url(url):
    current=ACTIVE.read_text().strip() if ACTIVE.exists() else load()["profiles"][0]["name"]
    data=load(); item=next((x for x in data["profiles"] if x["name"]==current),None)
    if not item or not re.fullmatch(r"https?://[^\s\"'\\]+",url): return 2
    item["url"]=url; data["profiles"]=[x for x in data["profiles"] if x["name"]!=current]+[item]; save(data); return switch(current)
def set_active_zoom(zoom):
    current=ACTIVE.read_text().strip() if ACTIVE.exists() else load()["profiles"][0]["name"]
    data=load(); item=next((x for x in data["profiles"] if x["name"]==current),None)
    if not item: return 1
    zoom=int(zoom)
    if zoom not in ZOOMS: return 2
    item["zoom"]=zoom; data["profiles"]=[x for x in data["profiles"] if x["name"]!=current]+[item]; save(data); return switch(current)
def main():
    action=sys.argv[1] if len(sys.argv)>1 else "list"; data=load()
    if action=="list": print(json.dumps(data)); return 0
    if action=="status": print(ACTIVE.read_text().strip() if ACTIVE.exists() else data["profiles"][0]["name"]); return 0
    if action=="switch" and len(sys.argv)==3: return switch(sys.argv[2])
    if action=="add" and len(sys.argv)==5:
        name,url,zoom=sys.argv[2],sys.argv[3],int(sys.argv[4])
        if not valid(name,url,zoom): return 2
        data["profiles"]=[x for x in data["profiles"] if x["name"]!=name]+[{"name":name,"url":url,"zoom":zoom}]; save(data); return 0
    if action=="remove" and len(sys.argv)==3:
        current=ACTIVE.read_text().strip() if ACTIVE.exists() else data["profiles"][0]["name"]
        if len(data["profiles"])<=1 or current==sys.argv[2]: return 2
        data["profiles"]=[x for x in data["profiles"] if x["name"]!=sys.argv[2]]
        data["automation"]["schedule"]=[x for x in data["automation"].get("schedule",[]) if x.get("profile")!=sys.argv[2]]
        data["automation"]["cycle_profiles"]=[x for x in data["automation"].get("cycle_profiles",[]) if x!=sys.argv[2]]
        save(data); return 0
    if action=="automation" and len(sys.argv)==7:
        enabled=sys.argv[2].lower()=="true"; mode=sys.argv[3]; minutes=int(sys.argv[4]); cycle_profiles=json.loads(sys.argv[5]); schedule=json.loads(sys.argv[6])
        names={x["name"] for x in data["profiles"]}
        valid_cycle=isinstance(cycle_profiles,list) and len(cycle_profiles)==len(set(cycle_profiles)) and all(x in names for x in cycle_profiles)
        valid_schedule=isinstance(schedule,list) and all(isinstance(x,dict) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",str(x.get("time",""))) and x.get("profile") in names for x in schedule)
        if mode not in {"cycle","schedule"} or not 1<=minutes<=1440 or not valid_cycle or not valid_schedule or (enabled and mode=="cycle" and len(cycle_profiles)<2): return 2
        data["automation"]={"enabled":enabled,"mode":mode,"cycle_minutes":minutes,"cycle_profiles":cycle_profiles,"schedule":sorted(schedule,key=lambda x:x["time"])}; save(data); return 0
    if action=="set-active-url" and len(sys.argv)==3: return set_active_url(sys.argv[2])
    if action=="set-active-zoom" and len(sys.argv)==3: return set_active_zoom(sys.argv[2])
    print("Usage: profile-manager.py list|status|add NAME URL ZOOM|remove NAME|switch NAME|set-active-url URL|set-active-zoom ZOOM|automation ENABLED MODE MINUTES CYCLE_JSON SCHEDULE_JSON",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
