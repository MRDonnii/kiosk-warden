#!/usr/bin/env python3
"""Single sign-on from Kontrolrum (the household dashboard).

Kontrolrum signs a short-lived assertion with a shared key instead of storing
a password here. The format is the one Spamfilter and Fleetdeck use:

    POST {v, aud, sub, iat, exp, nonce, sig}
    sig = hex HMAC-SHA256(key as UTF-8 text,
          "kontrolrum-sso\\n{v}\\n{aud}\\n{sub}\\n{iat}\\n{exp}\\n{nonce}")

This module only knows about its own files in ~/kiosk. Everything it does fails
closed: a missing, corrupt or unreadable file means "SSO is off", never an
exception in the caller. Standard library only, like the rest of the web UI.

Files (all 0600, owned by the kiosk user):
    kontrolrum-sso.json          key, allowed addresses, users that opted in
    kontrolrum-sso-nonces.json   one-time values, kept until they have expired
    kontrolrum-sso-status.json   last login and last refused attempt
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - not on Linux
    fcntl = None

LOG = logging.getLogger("kontrolrum-sso")

CONTEXT = "kontrolrum-sso"
VERSION = 1
MAX_LIFETIME = 120
SKEW = 60
RATE_LIMIT = 10
RATE_WINDOW = 5 * 60
MAX_PEERS = 8
MAX_BODY = 4096
MAX_NONCES = 2048
MAX_TRACKED_PEERS = 1024
REJECT_SAVE_INTERVAL = 30

REASON_TEXT = {
    "wrong_peer": "ikke fra Kontrolrums adresse",
    "rate_limited": "for mange forsøg",
    "sso_disabled": "SSO er slået fra",
    "bad_request": "ugyldig forespørgsel",
    "bad_signature": "forkert signatur",
    "bad_version": "ukendt version",
    "bad_audience": "forkert modtager",
    "expired": "udløbet",
    "replay": "brugt før",
    "unknown_user": "brugeren må ikke logges ind fra Kontrolrum",
    "unavailable": "kunne ikke gemme engangsværdien",
}

_NONCE_RE = re.compile(r"[A-Za-z0-9_-]{16,48}")
_SIG_RE = re.compile(r"[0-9A-Fa-f]{64}")
_KEY_RE = re.compile(r"[0-9a-f]{64}")


def normal_ip(value) -> str:
    """The canonical text of one exact IP address, '' when it is not one."""
    try:
        ip = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return ""
    mapped = getattr(ip, "ipv4_mapped", None)
    return str(mapped or ip)


def normal_user(name) -> str:
    return str(name or "").strip().lower()


def fingerprint(key: str) -> str:
    """Short id of a key (shown, and bound into sessions), never the key."""
    return hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:8]


def assertion_text(a: dict) -> str:
    return "\n".join([CONTEXT, str(a.get("v")), str(a.get("aud")), str(a.get("sub")),
                      str(a.get("iat")), str(a.get("exp")), str(a.get("nonce"))])


def sign(key: str, a: dict) -> str:
    return hmac.new(str(key).encode("utf-8"), assertion_text(a).encode("utf-8"), hashlib.sha256).hexdigest()


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def well_formed(a) -> bool:
    return (isinstance(a, dict) and _is_int(a.get("v")) and isinstance(a.get("aud"), str)
            and isinstance(a.get("sub"), str) and 0 < len(a["sub"]) <= 64 and "\n" not in a["sub"]
            and _is_int(a.get("iat")) and _is_int(a.get("exp"))
            and isinstance(a.get("nonce"), str) and _NONCE_RE.fullmatch(a["nonce"]) is not None
            and isinstance(a.get("sig"), str) and _SIG_RE.fullmatch(a["sig"]) is not None)


def parse_peers(text) -> tuple[list[str], list[str]]:
    """Split a free-text list into (exact addresses, what could not be read)."""
    good, bad = [], []
    for part in re.split(r"[\s,;]+", str(text or "").strip()):
        if not part:
            continue
        ip = normal_ip(part)
        if not ip or ipaddress.ip_address(ip).is_unspecified or ipaddress.ip_address(ip).is_multicast:
            bad.append(part[:64])
        elif ip not in good:
            good.append(ip)
    return good, bad


class Outcome:
    """The answer to one login attempt."""

    __slots__ = ("status", "error", "user", "binding")

    def __init__(self, status, error="", user="", binding=None):
        self.status, self.error, self.user, self.binding = status, error, user, binding

    @property
    def ok(self) -> bool:
        return self.status == 200


class KontrolrumSso:
    def __init__(self, path, audience: str, clock=time.time):
        self.path = Path(path)
        self.audience = audience
        self.clock = clock
        self.nonce_path = self.path.with_name(self.path.stem + "-nonces.json")
        self.status_path = self.path.with_name(self.path.stem + "-status.json")
        self.lock_path = self.path.with_name(self.path.stem + ".lock")
        self._lock = threading.RLock()
        self._cache_sig = None
        self._cache = None
        self._hits: dict[str, list] = {}
        self._rejected = None
        self._rejected_saved = 0.0

    # ------------------------------------------------------------- files
    def _write_json(self, path: Path, payload) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _read_json(self, path: Path):
        """The parsed file; {} when it does not exist; None when unreadable."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def read_state(self):
        """The settings; {} when never configured; None when unreadable."""
        try:
            info = os.stat(self.path)
        except FileNotFoundError:
            return {}
        except OSError:
            return None
        signature = (info.st_mtime_ns, info.st_size, info.st_ino)
        with self._lock:
            if signature == self._cache_sig:
                return self._cache
            state = self._read_json(self.path)
            self._cache_sig, self._cache = signature, state
            return state

    def _mutate(self, change):
        with self._lock:
            handle = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if fcntl is not None:
                    try:
                        handle = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
                        fcntl.flock(handle, fcntl.LOCK_EX)
                    except OSError:  # e.g. no lock daemon on an NFS root
                        if handle is not None:
                            os.close(handle)
                        handle = None
                state = dict(self._read_json(self.path) or {})
                result = change(state)
                self._write_json(self.path, state)
                self._cache_sig = None
                return result
            finally:
                if handle is not None:
                    os.close(handle)

    # ---------------------------------------------------------- settings
    def key(self) -> str:
        state = self.read_state() or {}
        key = state.get("key")
        return key if isinstance(key, str) and _KEY_RE.fullmatch(key) else ""

    def peers(self) -> list[str]:
        state = self.read_state() or {}
        values = state.get("peers")
        if not isinstance(values, list):
            return []
        return [ip for ip in (normal_ip(item) for item in values[:MAX_PEERS]) if ip]

    def users(self) -> list[str]:
        state = self.read_state() or {}
        values = state.get("users")
        return sorted({normal_user(u) for u in values if normal_user(u)}) if isinstance(values, list) else []

    def peer_allowed(self, peer) -> bool:
        ip = normal_ip(peer)
        return bool(ip) and ip in self.peers()

    def user_allowed(self, name) -> bool:
        wanted = normal_user(name)
        return bool(wanted) and wanted in self.users()

    def create_key(self, actor: str = "") -> str:
        """Make a new key (the old one and its sessions stop working) and
        return it. This is the only time it exists outside the file."""
        key = secrets.token_hex(32)

        def change(state):
            state.update(key=key, fingerprint=fingerprint(key), created_at=int(self.clock()),
                         created_by=str(actor or "")[:64])
        self._mutate(change)
        with self._lock:
            self._rejected = None
            for path in (self.nonce_path, self.status_path):
                try:
                    path.unlink()
                except OSError:
                    pass
        return key

    def disable(self) -> bool:
        """Delete the key. The addresses and user choices stay."""
        def change(state):
            had = bool(state.get("key"))
            for field in ("key", "fingerprint", "created_at", "created_by"):
                state.pop(field, None)
            return had
        return self._mutate(change)

    def set_peers(self, ips) -> list[str]:
        clean = []
        for item in ips:
            ip = normal_ip(item)
            if not ip:
                raise ValueError("Ugyldig IP-adresse")
            if ip not in clean:
                clean.append(ip)
        if len(clean) > MAX_PEERS:
            raise ValueError(f"Højst {MAX_PEERS} adresser")
        self._mutate(lambda state: state.update(peers=clean))
        return clean

    def set_user(self, name, allowed: bool) -> bool:
        """Tick or clear a user's opt-in. True when something changed."""
        wanted = normal_user(name)
        if not wanted:
            raise ValueError("Ukendt bruger")

        def change(state):
            values = state.get("users")
            current = {normal_user(u) for u in values} if isinstance(values, list) else set()
            before = wanted in current
            current.add(wanted) if allowed else current.discard(wanted)
            state["users"] = sorted(u for u in current if u)
            return before != bool(allowed)
        return self._mutate(change)

    def status(self) -> dict:
        """Everything the settings page shows. Never the key."""
        state = self.read_state()
        saved = self._read_json(self.status_path) or {}
        with self._lock:
            rejected = self._rejected or saved.get("rejected") or {}
        key = self.key()
        reason = str(rejected.get("reason") or "")
        return {
            "enabled": bool(key),
            "readable": state is not None,
            "fingerprint": fingerprint(key) if key else "",
            "created_at": (state or {}).get("created_at"),
            "created_by": (state or {}).get("created_by") or "",
            "peers": self.peers(),
            "users": self.users(),
            "last_used": saved.get("used") or None,
            "rejected_at": rejected.get("at"),
            "rejected_ip": rejected.get("ip") or "",
            "rejected_reason": reason,
            "rejected_text": REASON_TEXT.get(reason, reason),
        }

    # ------------------------------------------------------------ login
    def _rate_ok(self, peer: str) -> bool:
        now = self.clock()
        with self._lock:
            hit = self._hits.get(peer)
            if hit is None or now - hit[0] >= RATE_WINDOW:
                if hit is None and len(self._hits) >= MAX_TRACKED_PEERS:
                    self._hits = {k: v for k, v in self._hits.items() if now - v[0] < RATE_WINDOW}
                    if len(self._hits) >= MAX_TRACKED_PEERS:
                        return False
                self._hits[peer] = [now, 1]
                return True
            hit[1] += 1
            return hit[1] <= RATE_LIMIT

    def note_rejected(self, peer, reason: str) -> None:
        """Remember the newest refusal. The file is rewritten at most every
        30 seconds, so nobody can make the device write to its disk at will."""
        now = self.clock()
        entry = {"at": int(now), "ip": str(peer or "")[:64], "reason": reason}
        with self._lock:
            self._rejected = entry
            if now - self._rejected_saved < REJECT_SAVE_INTERVAL:
                return
            self._rejected_saved = now
        self._save_status(rejected=entry)

    def _save_status(self, **fields) -> None:
        try:
            with self._lock:
                saved = self._read_json(self.status_path) or {}
                saved.update(fields)
                self._write_json(self.status_path, saved)
        except OSError as error:
            LOG.warning("Could not save the Kontrolrum SSO status: %s", type(error).__name__)

    def gate(self, peer):
        """The checks made before the request body is read. None = go on."""
        ip = normal_ip(peer) or str(peer or "")[:64]
        if not self._rate_ok(ip):
            self.note_rejected(ip, "rate_limited")
            return Outcome(429, "rate_limited")
        if not self.peer_allowed(ip):
            self.note_rejected(ip, "wrong_peer")
            return Outcome(404, "wrong_peer")
        return None

    def _take_nonce(self, nonce: str, exp: int) -> bool:
        """False = seen before. Raises OSError/ValueError when it cannot be
        stored: the login is then refused rather than left open to replay."""
        now = int(self.clock())
        with self._lock:
            seen = self._read_json(self.nonce_path)
            if seen is None:
                raise ValueError("unreadable nonce store")
            seen = {k: v for k, v in seen.items() if _is_int(v) and v >= now}
            if nonce in seen:
                return False
            if len(seen) >= MAX_NONCES:
                raise ValueError("nonce store is full")
            seen[nonce] = max(int(exp), now) + SKEW + 1
            self._write_json(self.nonce_path, seen)
            return True

    def login(self, peer, raw, find_user) -> Outcome:
        """Check one assertion. find_user(sub) returns the account's real
        name when it exists and is active, otherwise a false value."""
        ip = normal_ip(peer)

        def refuse(status, error):
            self.note_rejected(ip, error)
            LOG.warning("Kontrolrum SSO refused (%s) from %s", error, ip)
            return Outcome(status, error)

        key = self.key()
        if not key:
            return refuse(403, "sso_disabled")
        try:
            a = json.loads(raw.decode("utf-8")) if raw else None
        except (AttributeError, UnicodeDecodeError, ValueError, RecursionError):
            a = None
        if not well_formed(a):
            return refuse(400, "bad_request")
        given = bytes.fromhex(a["sig"])
        if not hmac.compare_digest(bytes.fromhex(sign(key, a)), given):
            return refuse(401, "bad_signature")
        if a["v"] != VERSION:
            return refuse(401, "bad_version")
        if a["aud"] != self.audience:
            return refuse(401, "bad_audience")
        now = int(self.clock())
        iat, exp = a["iat"], a["exp"]
        if exp < iat or exp - iat > MAX_LIFETIME or iat > now + SKEW or exp + SKEW < now:
            return refuse(401, "expired")
        try:
            fresh = self._take_nonce(a["nonce"], exp)
        except (OSError, ValueError) as error:
            LOG.warning("Kontrolrum SSO nonce store failed: %s", type(error).__name__)
            return Outcome(503, "unavailable")
        if not fresh:
            return refuse(401, "replay")
        if not self.user_allowed(a["sub"]):
            return refuse(401, "unknown_user")
        user = find_user(a["sub"])
        if not user:
            return refuse(401, "unknown_user")
        self._save_status(used={"at": now, "ip": ip, "user": str(user)[:64]})
        return Outcome(200, "", str(user), {"p": ip, "k": fingerprint(key)})

    def session_problem(self, binding, peer, username) -> str:
        """'' when this request may use the SSO session, else the reason.
        Checked on every request of such a session."""
        if not isinstance(binding, dict):
            return "bad_request"
        key = self.key()
        if not key:
            return "sso_disabled"
        if not hmac.compare_digest(fingerprint(key), str(binding.get("k") or "")):
            return "key_changed"
        if not self.user_allowed(username):
            return "not_allowed"
        ip = normal_ip(peer)
        if not ip or ip != binding.get("p") or not self.peer_allowed(ip):
            return "peer_changed"
        return ""


# ---------------------------------------------------------------- command line
USAGE = """Brug:
  kontrolrum_sso.py kontrolrum-sso <bruger> [bruger ...] [--peer IP ...]
      Lav en ny nøgle, sæt fluebenet for brugerne, og skriv KUN nøglen på stdout.
  kontrolrum_sso.py status
  kontrolrum_sso.py peers [IP ...]     Sæt Kontrolrums adresser (ingen IP = fjern dem)
  kontrolrum_sso.py user <bruger> on|off
  kontrolrum_sso.py off                Slet nøglen og slå login fra Kontrolrum fra"""


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def run_cli(argv, sso: KontrolrumSso, find_user) -> int:
    """find_user(name) returns the account's real name, or a false value."""
    if not argv or argv[0] in ("-h", "--help"):
        _say(USAGE)
        return 2
    folder = sso.path.parent
    try:
        owner = folder.stat().st_uid
    except OSError:
        _say(f"Mappen {folder} kan ikke læses.")
        return 1
    if os.geteuid() != owner:
        _say(f"Kør kommandoen som ejeren af {folder} (uid {owner}), så filerne får den rigtige ejer.")
        return 1

    command, rest = argv[0], list(argv[1:])
    if command == "kontrolrum-sso":
        names, peers = [], []
        while rest:
            item = rest.pop(0)
            if item == "--peer":
                if not rest:
                    _say(USAGE)
                    return 2
                peers.append(rest.pop(0))
            else:
                names.append(item)
        if not names:
            _say(USAGE)
            return 2
        missing = [name for name in names if not find_user(name)]
        if missing:
            _say("Ukendte brugere: " + ", ".join(missing))
            return 1
        good, bad = parse_peers(" ".join(peers))
        if bad:
            _say("Kunne ikke læse: " + ", ".join(bad))
            return 1
        key = sso.create_key("kommandolinjen")
        for name in names:
            sso.set_user(name, True)
        if good:
            sso.set_peers(sorted(set(sso.peers()) | set(good)))
        _say(f"SSO-nøgle lavet ({fingerprint(key)}), flueben sat for: {', '.join(names)}.")
        if not sso.peers():
            _say("Kontrolrums IP-adresse mangler. Prøv login fra Kontrolrum, se adressen med 'status', og sæt den med 'peers'.")
        sys.stdout.write(key)
        sys.stdout.flush()
        return 0
    if command == "status":
        info = sso.status()
        print("Slået til" if info["enabled"] else "Slået fra")
        if info["fingerprint"]:
            print(f"Nøgle: {info['fingerprint']}...")
        print("Kontrolrums adresser: " + (", ".join(info["peers"]) or "ingen"))
        print("Brugere: " + (", ".join(info["users"]) or "ingen"))
        if info["last_used"]:
            used = info["last_used"]
            print(f"Senest brugt: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(used.get('at', 0)))} fra {used.get('ip')} som {used.get('user')}")
        if info["rejected_ip"]:
            print(f"Seneste afviste forsøg: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['rejected_at'] or 0))} fra {info['rejected_ip']} ({info['rejected_text']})")
        return 0
    if command == "peers":
        good, bad = parse_peers(" ".join(rest))
        if bad:
            _say("Kunne ikke læse: " + ", ".join(bad))
            return 1
        try:
            saved = sso.set_peers(good)
        except ValueError as error:
            _say(str(error))
            return 1
        _say("Kontrolrums adresser: " + (", ".join(saved) or "ingen"))
        return 0
    if command == "user" and len(rest) == 2 and rest[1] in ("on", "off"):
        if rest[1] == "on" and not find_user(rest[0]):
            _say("Ukendt bruger: " + rest[0])
            return 1
        sso.set_user(rest[0], rest[1] == "on")
        _say(f"{rest[0]}: {'må' if rest[1] == 'on' else 'må ikke'} logges ind fra Kontrolrum.")
        return 0
    if command == "off":
        _say("Login fra Kontrolrum er slået fra." if sso.disable() else "Login fra Kontrolrum var ikke slået til.")
        return 0
    _say(USAGE)
    return 2


def _configured_username(conf_path) -> str:
    """WEBUI_USERNAME from kiosk.conf, without loading the web server."""
    name = "admin"
    try:
        with open(conf_path, encoding="utf-8") as handle:
            for line in handle:
                field, separator, value = line.strip().partition("=")
                if separator and field.strip() == "WEBUI_USERNAME":
                    name = value.strip().strip('"') or "admin"
    except OSError:
        pass
    return name


def _main() -> int:
    kiosk_dir = Path(os.path.expanduser("~")) / "kiosk"
    username = _configured_username(kiosk_dir / "kiosk.conf")

    def find_user(name):
        return username if hmac.compare_digest(str(name).encode(), username.encode()) else None

    return run_cli(sys.argv[1:], KontrolrumSso(kiosk_dir / "kontrolrum-sso.json", "kioskwarden"), find_user)


if __name__ == "__main__":
    raise SystemExit(_main())
