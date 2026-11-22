"""Minimal Home Assistant REST client - stdlib only, no dependencies.

Lets Kiosk Warden read a handful of things back FROM Home Assistant (a
smart-plug power/energy sensor, its recent history) for the "PC overblik"
page and the Connections connection test. Never writes anything to HA -
read-only, on purpose. Also runnable as a one-shot CLI so mqtt-stats.sh
(bash) can call it without embedding a second HTTP client.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

TIMEOUT_SECONDS = 5


class HAClientError(Exception):
    """Raised for any failure talking to Home Assistant."""


def _request(ha_url: str, token: str, path: str):
    url = ha_url.rstrip("/") + path
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raise HAClientError(f"HTTP {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise HAClientError(str(err.reason)) from err
    except (TimeoutError, OSError, json.JSONDecodeError) as err:
        raise HAClientError(str(err)) from err


def test_connection(ha_url: str, token: str) -> tuple[bool, str]:
    """Return (ok, message) - a plain-language result for the Settings page."""
    if not ha_url or not token:
        return False, "URL og token skal begge udfyldes."
    try:
        data = _request(ha_url, token, "/api/")
    except HAClientError as err:
        return False, f"Kunne ikke forbinde: {err}"
    message = data.get("message") if isinstance(data, dict) else None
    return True, message or "Forbindelse OK."


def get_state(ha_url: str, token: str, entity_id: str) -> dict | None:
    if not ha_url or not token or not entity_id:
        return None
    try:
        return _request(ha_url, token, f"/api/states/{entity_id}")
    except HAClientError:
        return None


def get_history(ha_url: str, token: str, entity_id: str, hours: int = 24) -> list[dict]:
    """Minimal state-change history for one entity over the last `hours`."""
    if not ha_url or not token or not entity_id:
        return []
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = f"/api/history/period/{start}?filter_entity_id={entity_id}&minimal_response"
    try:
        data = _request(ha_url, token, path)
    except HAClientError:
        return []
    if isinstance(data, list) and data:
        return data[0]
    return []


def list_entities(
    ha_url: str, token: str, domain: str | None = None, device_classes: tuple[str, ...] = ()
) -> list[dict]:
    """Candidate entities for the Settings page's measurement picker.

    Never a free-text field for the user to guess an entity_id into - this
    is what populates the dropdown instead.
    """
    if not ha_url or not token:
        return []
    try:
        states = _request(ha_url, token, "/api/states")
    except HAClientError:
        return []
    if not isinstance(states, list):
        return []
    results = []
    for state in states:
        entity_id = state.get("entity_id", "")
        if domain and not entity_id.startswith(f"{domain}."):
            continue
        attributes = state.get("attributes", {})
        if device_classes and attributes.get("device_class") not in device_classes:
            continue
        results.append(
            {
                "entity_id": entity_id,
                "name": attributes.get("friendly_name", entity_id),
                "device_class": attributes.get("device_class"),
            }
        )
    results.sort(key=lambda item: item["name"].lower())
    return results


def _main() -> int:
    if len(sys.argv) < 4:
        print(
            "usage: ha_client.py <test_connection|get_state> <ha_url> <token> [entity_id]",
            file=sys.stderr,
        )
        return 2
    command, ha_url, token = sys.argv[1], sys.argv[2], sys.argv[3]
    if command == "test_connection":
        ok, message = test_connection(ha_url, token)
        print(json.dumps({"ok": ok, "message": message}))
        return 0 if ok else 1
    if command == "get_state":
        if len(sys.argv) < 5:
            print("get_state requires an entity_id", file=sys.stderr)
            return 2
        state = get_state(ha_url, token, sys.argv[4])
        print(json.dumps(state))
        return 0 if state is not None else 1
    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
