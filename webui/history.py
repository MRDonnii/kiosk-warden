"""Telemetry history and the event log behind the charts on the Status page (standard library only).

MinuteStore keeps the average, minimum and maximum of every measurement per minute, in memory as compact
arrays (about 1.3 MB for 8 days) and on disk as one JSON line per minute in ~/kiosk/telemetry/YYYY-MM-DD.jsonl
(about 250 KB per day). Files older than the retention are deleted, a half-written line is skipped when loading,
and the history is loaded again at start, so it survives restarts and updates.

EventLog is ~/kiosk/events.jsonl: one JSON line per change of the kiosk's health, Chrome, the screen and every
recovery. The WebUI writes the state changes, the shell scripts write recoveries through kiosk-event.sh; both take
the same flock, so trimming the file (8 days, at most MAX_EVENT_LINES lines) never loses a line written meanwhile.
Reasons are cleaned of URL queries and credentials before they are written.
"""
import array
import bisect
import fcntl
import json
import math
import os
import re
import threading
import time

RETENTION = 8 * 86400
MAX_EVENT_LINES = 5000
KEYS = ("cpu", "ram", "gpu", "cpu_temp", "nvme_temp", "cpu_mhz", "network_kbps", "ha_power", "disk")
# Short names on disk keep a day's file around 250 KB.
SHORT = {"cpu": "c", "ram": "r", "gpu": "g", "cpu_temp": "ct", "nvme_temp": "nt", "cpu_mhz": "f",
         "network_kbps": "n", "ha_power": "p", "disk": "d"}
LONG = {v: k for k, v in SHORT.items()}
DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
NAN = float("nan")


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return None if math.isnan(value) or math.isinf(value) else float(value)


def _r(value):
    value = round(value, 1)
    return int(value) if value == int(value) else value


def append_line(path, line):
    """Append one line in a single write. If the file ends in a half line (power cut mid-write),
    start on a fresh line, so the broken line is the only one lost."""
    data = line.encode("utf-8") + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size:
            with open(path, "rb") as f:
                f.seek(size - 1)
                if f.read(1) != b"\n":
                    data = b"\n" + data
        os.write(fd, data)
    finally:
        os.close(fd)


def read_json_lines(path):
    """Every complete JSON object in a JSON-lines file; broken or half lines are skipped."""
    out = []
    try:
        with open(path, "rb") as f:
            for raw in f:
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    out.append(item)
    except OSError:
        pass
    return out


class MinuteStore:
    def __init__(self, directory, keys=KEYS, retention=RETENTION, clock=time.time):
        self.dir = directory
        self.keys = tuple(keys)
        self.retention = retention
        self.clock = clock
        self.lock = threading.Lock()
        self.t = array.array("q")
        self.cols = {k: (array.array("f"), array.array("f"), array.array("f")) for k in self.keys}
        self._minute = None
        self._acc = {}
        self._pruned_day = None

    # ---- loading and pruning ----
    def _day(self, t):
        return time.strftime("%Y-%m-%d", time.localtime(t))

    def load(self):
        """Read the day files inside the retention (oldest first) into memory."""
        cutoff = self.clock() - self.retention
        rows = {}
        try:
            names = sorted(os.listdir(self.dir))
        except OSError:
            names = []
        for name in names:
            m = DAY_FILE.match(name)
            if not m or m.group(1) < self._day(cutoff):
                continue
            for item in read_json_lines(os.path.join(self.dir, name)):
                t = item.get("t")
                if isinstance(t, int) and t >= cutoff:
                    rows[t] = item
        with self.lock:
            self.t = array.array("q")
            self.cols = {k: (array.array("f"), array.array("f"), array.array("f")) for k in self.keys}
            for t in sorted(rows):
                self._push(t, self._decode(rows[t]))
        self.prune()
        return len(self.t)

    def _decode(self, item):
        vals = {}
        for short, value in item.items():
            key = LONG.get(short)
            if key not in self.cols:
                continue
            if isinstance(value, list) and len(value) == 3 and all(_num(v) is not None for v in value):
                vals[key] = tuple(float(v) for v in value)
            elif _num(value) is not None:
                vals[key] = (float(value),) * 3
        return vals

    def prune(self):
        now = self.clock()
        cutoff = now - self.retention
        with self.lock:
            n = 0
            while n < len(self.t) and self.t[n] < cutoff:
                n += 1
            if n:
                del self.t[:n]
                for cols in self.cols.values():
                    for col in cols:
                        del col[:n]
        oldest_day = self._day(cutoff)
        try:
            for name in os.listdir(self.dir):
                m = DAY_FILE.match(name)
                if m and m.group(1) < oldest_day:
                    os.unlink(os.path.join(self.dir, name))
        except OSError:
            pass
        self._pruned_day = self._day(now)

    # ---- collecting ----
    def _push(self, t, vals):
        self.t.append(t)
        for k, cols in self.cols.items():
            v = vals.get(k)
            for i, col in enumerate(cols):
                col.append(v[i] if v else NAN)

    def add_sample(self, sample):
        """Fold one raw sample (dict with "time" and the measurements) into its minute."""
        t = sample.get("time")
        if not isinstance(t, (int, float)):
            return
        minute = int(t) // 60 * 60
        record = None
        with self.lock:
            if self._minute is not None and minute != self._minute:
                record = self._close_minute()
            self._minute = minute
            for k in self.keys:
                v = _num(sample.get(k))
                if v is None:
                    continue
                a = self._acc.get(k)
                self._acc[k] = [v, 1, v, v] if a is None else [a[0] + v, a[1] + 1, min(a[2], v), max(a[3], v)]
        if record:
            self._write(record)

    def _close_minute(self):
        vals = {k: (a[0] / a[1], a[2], a[3]) for k, a in self._acc.items()}
        t, self._acc = self._minute, {}
        if not vals or (len(self.t) and self.t[-1] >= t):
            return None
        self._push(t, vals)
        return t, vals

    def _write(self, record):
        t, vals = record
        line = {"t": t}
        for k, (avg, lo, hi) in vals.items():
            line[SHORT.get(k, k)] = _r(avg) if lo == hi == avg else [_r(avg), _r(lo), _r(hi)]
        try:
            os.makedirs(self.dir, mode=0o700, exist_ok=True)
            append_line(os.path.join(self.dir, self._day(t) + ".jsonl"), json.dumps(line, separators=(",", ":")))
        except OSError:
            pass
        if self._day(self.clock()) != self._pruned_day:
            self.prune()

    # ---- reading ----
    def records(self, since):
        """[(t, {key: (avg, min, max)})] from `since`, the minute in progress included."""
        out = []
        with self.lock:
            start = bisect.bisect_left(self.t, int(since))
            for i in range(start, len(self.t)):
                vals = {}
                for k, (a, lo, hi) in self.cols.items():
                    if a[i] == a[i]:  # not NaN
                        vals[k] = (a[i], lo[i], hi[i])
                out.append((self.t[i], vals))
            if self._minute is not None and self._acc and self._minute >= since:
                out.append((self._minute, {k: (a[0] / a[1], a[2], a[3]) for k, a in self._acc.items()}))
        return out

    def first_time(self):
        with self.lock:
            return self.t[0] if len(self.t) else None


# ---------------- events ----------------
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]*@")
_URL_QUERY = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s?#]*)[?#]\S*")
_SECRETS = re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key|auth)=\S+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def clean_text(text, limit=200):
    """Reasons may hold a URL with an access token in its query: keep scheme, host and path only."""
    text = _CONTROL.sub(" ", str(text or ""))
    text = _URL_CREDENTIALS.sub(r"\1", text)
    text = _URL_QUERY.sub(r"\1", text)
    text = _SECRETS.sub(r"\1=…", text)
    text = text.strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


class EventLog:
    KINDS = ("health", "chrome", "screen", "recovery")

    def __init__(self, path, retention=RETENTION, max_lines=MAX_EVENT_LINES, clock=time.time):
        self.path = path
        self.retention = retention
        self.max_lines = max_lines
        self.clock = clock
        self._cache = (None, [])

    def _locked(self):
        fd = os.open(self.path + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def append(self, kind, value=None, step=None, reason=None, source=None, t=None):
        if kind not in self.KINDS:
            raise ValueError(kind)
        item = {"t": int(self.clock() if t is None else t), "kind": kind}
        for name, field in (("value", value), ("step", step), ("reason", reason), ("src", source)):
            if field not in (None, ""):
                item[name] = clean_text(field, 60 if name != "reason" else 200)
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            fd = self._locked()
            try:
                append_line(self.path, json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            finally:
                os.close(fd)
        except OSError:
            return None
        return item

    def read(self):
        """All events, oldest first. Cached on the file's size and mtime."""
        try:
            st = os.stat(self.path)
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            return []
        if self._cache[0] == key:
            return self._cache[1]
        items = [e for e in read_json_lines(self.path)
                 if isinstance(e.get("t"), (int, float)) and e.get("kind") in self.KINDS]
        items.sort(key=lambda e: e["t"])
        self._cache = (key, items)
        return items

    def last_values(self):
        last = {}
        for e in self.read():
            if e["kind"] != "recovery" and "value" in e:
                last[e["kind"]] = e["value"]
        return last

    def trim(self):
        """Drop events older than the retention and keep at most max_lines (rewritten atomically)."""
        if not os.path.exists(self.path):
            return 0
        cutoff = self.clock() - self.retention
        try:
            fd = self._locked()
        except OSError:
            return 0
        try:
            items = [e for e in read_json_lines(self.path) if isinstance(e.get("t"), (int, float))]
            keep = [e for e in items if e["t"] >= cutoff][-self.max_lines:]
            # Keep the newest state before the cutoff, so the timeline still knows the state at its start.
            for kind in ("health", "chrome", "screen"):
                old = [e for e in items if e["t"] < cutoff and e.get("kind") == kind]
                if old:
                    keep.append(old[-1])
            keep.sort(key=lambda e: e["t"])
            if len(keep) == len(items):
                return 0
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for e in keep:
                    f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            return len(items) - len(keep)
        except OSError:
            return 0
        finally:
            os.close(fd)
