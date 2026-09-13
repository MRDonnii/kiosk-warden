#!/usr/bin/env python3
"""Tell the kiosk page whether it should run actively or idle."""

import json
import pathlib
import sys
import time
import urllib.request

def _write_status(details):
    status_path = pathlib.Path.home() / "kiosk" / "smartdash_status.json"
    temp_path = status_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(details), encoding="utf-8")
    temp_path.replace(status_path)


try:
    import websocket
except ImportError:
    error_details = {
        "supported": False,
        "error": "missing_dependency",
        "error_message": "Python-modulet 'websocket' (python3-websocket) mangler. Kør installations- eller opdateringsscriptet igen.",
        "checked_at": int(time.time()),
    }
    _write_status(error_details)
    print(json.dumps(error_details))
    print("python3-websocket is required for browser power saving", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"active", "idle", "status"}:
        print(f"Usage: {sys.argv[0]} active|idle|status", file=sys.stderr)
        return 2
    state = sys.argv[1]
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=3) as response:
            targets = json.load(response)
    except (OSError, ValueError) as exc:
        error_details = {
            "supported": False,
            "error": "debug_port_unreachable",
            "error_message": "Chromes debug-port (127.0.0.1:9222) svarer ikke. Chrome kører muligvis ikke, eller blev startet uden --remote-debugging-port.",
            "checked_at": int(time.time()),
        }
        _write_status(error_details)
        print(f"Chrome debug port unreachable: {exc}", file=sys.stderr)
        if state == "status":
            print(json.dumps(error_details))
        return 1
    page = next(
        (target for target in targets if target.get("type") == "page" and target.get("url", "").startswith(("http://", "https://"))),
        None,
    )
    if page is None:
        error_details = {
            "supported": False,
            "error": "no_page_found",
            "error_message": "Chrome kører, men ingen synlig side blev fundet (flere faner/vinduer, eller siden er ikke indlæst endnu).",
            "checked_at": int(time.time()),
        }
        _write_status(error_details)
        print("No kiosk page found", file=sys.stderr)
        if state == "status":
            print(json.dumps(error_details))
        return 1
    connection = websocket.create_connection(
        page["webSocketDebuggerUrl"], timeout=3, suppress_origin=True
    )
    try:
        requested = json.dumps(state)
        expression = f"""(() => {{
          const supported = Boolean(window.BeastPower?.getState && window.BeastPower?.setState);
          if ({requested} !== 'status') {{
            if (supported) window.BeastPower.setState({requested});
            else window.postMessage({{type:'kiosk-warden-power',state:{requested}}}, window.location.origin);
          }}
          return {{supported, name: supported ? 'HA Smartdash' : null,
            state: supported ? window.BeastPower.getState() : null,
            build: document.querySelector('meta[name="beast-build"]')?.content || null,
            release: document.querySelector('meta[name="beast-release-tag"]')?.content || null,
            url: location.href}};
        }})()"""
        connection.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }))
        while True:
            result = json.loads(connection.recv())
            if result.get("id") == 1:
                break
        if "error" in result:
            print(result["error"].get("message", "Browser power-state command failed"), file=sys.stderr)
            return 1
        details = result.get("result", {}).get("result", {}).get("value", {})
        details["checked_at"] = int(time.time())
        status_path = pathlib.Path.home() / "kiosk" / "smartdash_status.json"
        temp_path = status_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(details), encoding="utf-8")
        temp_path.replace(status_path)
        if state == "status": print(json.dumps(details))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
