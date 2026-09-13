#!/usr/bin/env python3
"""Freeze or resume the kiosk page through Chrome DevTools Protocol."""

import json
import sys
import urllib.request

try:
    import websocket
except ImportError:
    print("python3-websocket is required for browser power saving", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"active", "frozen"}:
        print(f"Usage: {sys.argv[0]} active|frozen", file=sys.stderr)
        return 2
    state = sys.argv[1]
    with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=3) as response:
        targets = json.load(response)
    page = next(
        (target for target in targets if target.get("type") == "page" and target.get("url", "").startswith(("http://", "https://"))),
        None,
    )
    if page is None:
        print("No kiosk page found", file=sys.stderr)
        return 1
    connection = websocket.create_connection(
        page["webSocketDebuggerUrl"], timeout=3, suppress_origin=True
    )
    try:
        connection.send(json.dumps({
            "id": 1,
            "method": "Page.setWebLifecycleState",
            "params": {"state": state},
        }))
        while True:
            result = json.loads(connection.recv())
            if result.get("id") == 1:
                break
        if "error" in result:
            print(result["error"].get("message", "Chrome lifecycle command failed"), file=sys.stderr)
            return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
