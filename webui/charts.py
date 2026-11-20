"""Server-rendered SVG charts for the Status page (standard library only).

Each plot is an SVG with viewBox 0 0 1000 100 and preserveAspectRatio="none" (strokes use
vector-effect: non-scaling-stroke), so it stretches with the page. Axis text, end labels, crosshair
and tooltip are HTML on top, positioned in percent, so text is never distorted. The small script in
ui_assets.APP_JS adds the shared crosshair, the tooltip, the arrow keys and the period switch.

Colours follow the measurement, never its rank (slot 1 = CPU/first series, 2, 3), and come from CSS
variables with their own steps for the light and the dark theme (validated for colour blindness).
"""
import datetime as dt
import html
import json
import math
import threading

# key, button label, span (s), bucket (s), auto refresh (s)
RANGES = [("1t", "1 t", 3600, 10, 10), ("6t", "6 t", 6 * 3600, 60, 30),
          ("24t", "24 t", 86400, 240, 60), ("7d", "7 dage", 7 * 86400, 1800, 300)]
RANGE = {r[0]: r for r in RANGES}
RANGE_EN = {"1t": "1 h", "6t": "6 h", "24t": "24 h", "7d": "7 days"}
DEFAULT_RANGE = "24t"
DAYS = {"da": ["man", "tir", "ons", "tor", "fre", "lør", "søn"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
BAND_NOTE = {"1t": "10 s", "6t": "1 min", "24t": "4 min", "7d": "30 min"}
_L = threading.local()  # number and date format of the page being rendered ("da" or "en")


def lang():
    return getattr(_L, "lang", "da")
MIN_GAP = 180  # a pause longer than this (WebUI not running) breaks the line
esc = html.escape
TRIANGLE = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1 11 10H1Z"/></svg>'


def local(t):
    return dt.datetime.fromtimestamp(t)


def fmt_num(v, dec=0):
    """7,9 and 1 011 in Danish, 7.9 and 1,011 in English."""
    if v is None:
        return "\u2013"
    if lang() == "en":
        return f"{v:,.{dec}f}"
    return f"{v:,.{dec}f}".replace(",", "\u202f").replace(".", ",")


def fmt_unit(v, dec, unit):
    if v is None:
        return "–"
    return fmt_num(v, dec) + ("%" if unit == "%" else f" {unit}" if unit else "")


# ---------------- data ----------------
def bucketize(records, t0, t1, step, keys):
    """Average, min and max per time bucket. records: [(t, {key: (avg, min, max)})] sorted by t.

    Only buckets with data are returned; a pause shows as a jump in time and breaks the line."""
    out, cur, acc = [], None, None

    def close():
        b = {"t": min(max(cur * step + step / 2, t0), t1)}
        for k, a in acc.items():
            b[k] = (round(a[0] / a[1], 1), round(a[2], 1), round(a[3], 1))
        out.append(b)

    for t, vals in records:
        if t < t0 or t > t1:
            continue
        idx = int(t // step)
        if idx != cur:
            if acc:
                close()
            cur, acc = idx, {}
        for k in keys:
            v = vals.get(k)
            if v is None:
                continue
            a = acc.get(k)
            acc[k] = [v[0], 1, v[1], v[2]] if a is None else [a[0] + v[0], a[1] + 1, min(a[2], v[1]), max(a[3], v[2])]
    if acc:
        close()
    return out


def gap_for(step):
    return max(3 * step, MIN_GAP)


def nice_step(span, n=4):
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def y_domain(buckets, keys, fixed=None, band=False):
    if fixed:
        return fixed[0], fixed[1], (fixed[1] - fixed[0]) / 4
    vals = []
    for b in buckets:
        for k in keys:
            v = b.get(k)
            if v:
                vals += [v[1], v[2]] if band else [v[0]]
    lo, hi = (min(vals), max(vals)) if vals else (0, 1)
    if lo >= 0 and lo < (hi - lo) * 0.6:
        lo = 0
    step = nice_step(max(hi - lo, 1e-6))
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step
    if hi - lo < 1e-9:
        hi = lo + step
    return lo, hi, step


def x_ticks(t0, t1, range_key):
    out = []
    if range_key == "7d":
        d = local(t0).replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
        while d.timestamp() < t1:
            out.append((d.timestamp(), f"{DAYS[lang()][d.weekday()]} {d.day}{'.' if lang() == 'da' else ''}"))
            d += dt.timedelta(days=1)  # naive local time: midnight stays midnight across DST
        return out
    every = {"1t": 600, "6t": 3600, "24t": 4 * 3600}[range_key]
    off = local(t0).utcoffset() or dt.timedelta(0)
    t = (int(t0 + off.total_seconds()) // every + 1) * every - int(off.total_seconds())
    while t < t1:
        out.append((t, local(t).strftime("%H:%M")))
        t += every
    return out


def tip_time(t, range_key):
    d = local(t)
    if range_key == "7d":
        if lang() == "en":
            return f"{DAYS['en'][d.weekday()]} {d.day} {d.strftime('%H:%M')}"
        return f"{DAYS['da'][d.weekday()]} {d.day}. kl. {d.strftime('%H:%M')}"
    return d.strftime("%H:%M:%S" if range_key == "1t" else "%H:%M")


def coverage(times, t0, t1, gap=MIN_GAP, width=60):
    """Intervals in which the WebUI was collecting (from the sample times)."""
    out, start, prev = [], None, None
    for t in times:
        if t > t1:
            break
        if start is None:
            start = prev = t
        elif t - prev > gap:
            out.append((start, prev + width))
            start = t
        prev = t
    if start is not None:
        out.append((start, t1 if t1 - prev <= gap else prev + width))
    return [(max(a, t0), min(b, t1)) for a, b in out if b > t0 and a < t1]


def state_spans(events, kind, t0, t1, covered):
    """[(start, end, value)] for one kind of state event, cut to the time the WebUI was watching."""
    spans, value, since = [], None, t0
    for e in events:
        if e.get("kind") != kind or "value" not in e:
            continue
        if e["t"] <= t0:
            value = e["value"]
            continue
        if e["t"] >= t1:
            break
        if value is not None and e["t"] > since:
            spans.append((since, e["t"], value))
        value, since = e["value"], e["t"]
    if value is not None and since < t1:
        spans.append((since, t1, value))
    out = []
    for a, b, v in spans:
        for ca, cb in covered:
            lo, hi = max(a, ca), min(b, cb)
            if hi > lo:
                out.append((lo, hi, v))
    return out


def share(spans, value):
    known = sum(b - a for a, b, _ in spans)
    return None if known <= 0 else 100 * sum(b - a for a, b, v in spans if v == value) / known


def incidents(recoveries, window=60):
    """Recoveries closer than `window` seconds are one incident (a failed step and the fallback that follows)."""
    count, last = 0, None
    for e in recoveries:
        if last is None or e["t"] - last > window:
            count += 1
        last = e["t"]
    return count


def chrome_restarts(events, t0, t1):
    """Chrome seen stopped and then running again, plus restarts by a recovery too quick to be seen stopped."""
    ups, prev = [], None
    for e in events:
        if e.get("kind") == "chrome":
            if e.get("value") == "up" and prev == "down" and t0 <= e["t"] <= t1:
                ups.append(e["t"])
            prev = e.get("value")
    restarts = [e["t"] for e in events if e.get("kind") == "recovery" and e.get("step") in ("restart", "chrome-restart")
                and t0 <= e["t"] <= t1]
    unseen = [t for t in restarts if not any(0 <= u - t <= 120 for u in ups)]
    return len(ups) + len(unseen)


# ---------------- SVG ----------------
def _px(t, t0, t1):
    return (t - t0) / (t1 - t0) * 1000


def _py(v, lo, hi):
    return 100 - (min(max(v, lo), hi) - lo) / (hi - lo) * 100


def _segments(buckets, key, gap):
    seg, prev = [], None
    for b in buckets:
        v = b.get(key)
        if v is None or (prev is not None and b["t"] - prev > gap):
            if seg:
                yield seg
            seg = []
        if v is not None:
            seg.append((b["t"], v))
            prev = b["t"]
    if seg:
        yield seg


def _path(segs, t0, t1, lo, hi, idx=0):
    out = []
    for seg in segs:
        pts = [f"{_px(t, t0, t1):.1f} {_py(v[idx], lo, hi):.2f}" for t, v in seg]
        if len(pts) == 1:  # a lone point: a short dash so it stays visible
            x, y = pts[0].split()
            pts = [f"{float(x) - 1.5:.1f} {y}", f"{float(x) + 1.5:.1f} {y}"]
        out.append("M" + " L".join(pts))
    return " ".join(out)


def _band(segs, t0, t1, lo, hi):
    parts = []
    for seg in segs:
        if len(seg) < 2:
            continue
        top = [f"{_px(t, t0, t1):.1f} {_py(v[2], lo, hi):.2f}" for t, v in seg]
        bot = [f"{_px(t, t0, t1):.1f} {_py(v[1], lo, hi):.2f}" for t, v in reversed(seg)]
        parts.append("M" + " L".join(top + bot) + "Z")
    return " ".join(parts)


def _xlabels(t0, t1, range_key):
    return "".join(f'<span style="left:{_px(t, t0, t1) / 10:.2f}%">{esc(l)}</span>' for t, l in x_ticks(t0, t1, range_key))


def line_chart(cid, buckets, series, t0, t1, range_key, unit, dec=0, fixed=None, band=False, area=False,
               height=150, group="kg", label=""):
    """series: [(key, label, slot)]; slot 1..3 is the categorical colour of that measurement."""
    keys = [s[0] for s in series]
    if not any(b.get(k) for b in buckets for k in keys):
        return f'<div class="kg-empty" style="height:{height}px">Ingen målinger i perioden endnu.</div>'
    step = RANGE[range_key][3]
    gap = gap_for(step)
    lo, hi, ystep = y_domain(buckets, keys, fixed, band)
    svg = ['<svg class="kg-svg" viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">']
    for i in range(int(round((hi - lo) / ystep)) + 1):
        y = _py(lo + i * ystep, lo, hi)
        svg.append(f'<line class="{"kg-base" if i == 0 else "kg-grid"}" x1="0" x2="1000" y1="{y:.2f}" y2="{y:.2f}"/>')
    for key, _, slot in series:
        segs = list(_segments(buckets, key, gap))
        if band:
            svg.append(f'<path class="kg-band s{slot}" d="{_band(segs, t0, t1, lo, hi)}"/>')
        if area:
            for seg in segs:
                if len(seg) > 1:
                    svg.append(f'<path class="kg-area s{slot}" d="{_path([seg], t0, t1, lo, hi)} L{_px(seg[-1][0], t0, t1):.1f} 100 '
                               f'L{_px(seg[0][0], t0, t1):.1f} 100Z"/>')
        svg.append(f'<path class="kg-line s{slot}" d="{_path(segs, t0, t1, lo, hi)}"/>')
    svg.append("</svg>")
    ydec = 0 if ystep >= 1 else 1
    ylab = "".join(f'<span style="top:{_py(lo + i * ystep, lo, hi):.2f}%">{fmt_num(lo + i * ystep, ydec)}</span>'
                   for i in range(int(round((hi - lo) / ystep)) + 1))
    # Direct end labels; one that would collide is left out (legend and tooltip carry it).
    ends, used = [], []
    for key, lab, slot in series:
        last = next((b for b in reversed(buckets) if b.get(key)), None)
        if not last:
            continue
        y = _py(last[key][0], lo, hi)
        ends.append(f'<i class="kg-end s{slot}" style="left:{_px(last["t"], t0, t1) / 10:.2f}%;top:{y:.2f}%"></i>')
        if all(abs(y - u) > 11 for u in used):
            used.append(y)
            ends.append(f'<span class="kg-endlab" style="top:{y:.2f}%"><b>{fmt_num(last[key][0], dec)}</b> '
                        f'{esc(lab) if len(series) > 1 else ""}</span>')
    data = {"t": [round(b["t"]) for b in buckets], "lo": lo, "hi": hi, "t0": t0, "t1": t1, "unit": unit, "dec": dec,
            "gap": gap, "range": range_key,
            "s": [{"label": l, "slot": sl, "v": [b[k][0] if b.get(k) else None for b in buckets],
                   "mm": [[b[k][1], b[k][2]] if b.get(k) else None for b in buckets] if band else None}
                  for k, l, sl in series]}
    if len(series) > 1:
        legend = '<div class="kg-legend">' + "".join(f'<span><i class="s{sl}"></i>{esc(l)}</span>' for _, l, sl in series) + "</div>"
    elif band:
        sl = series[0][2]
        legend = (f'<div class="kg-legend"><span><i class="s{sl}"></i>gennemsnit</span>'
                  f'<span><i class="band s{sl}"></i>min–maks pr. {BAND_NOTE[range_key]}</span></div>')
    else:
        legend = ""
    aria = label or ", ".join(s[1] for s in series)
    return (f'{legend}<div class="kg-chart" id="{cid}" data-group="{group}" style="--kg-h:{height}px">'
            f'<div class="kg-y">{ylab}</div><div class="kg-plot" tabindex="0" role="img" '
            f'aria-label="{esc(aria)}. Brug piletasterne for værdier; tabelvisning under graferne.">'
            f'{"".join(svg)}{"".join(ends)}<div class="kg-cross"></div><div class="kg-tip" hidden></div></div>'
            f'<div class="kg-x">{_xlabels(t0, t1, range_key)}</div>'
            f'<script type="application/json" class="kg-data">{_json(data)}</script></div>')


def _json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


TIMELINE_ROWS = [("Kiosk", "health", {"ON": ("st-ok", "OK"), "OFF": ("st-bad", "Fejl")}),
                 ("Chrome", "chrome", {"up": ("st-ok", "Kører"), "down": ("st-bad", "Stoppet")}),
                 ("Skærm", "screen", {"ON": ("st-on", "Tændt"), "OFF": ("st-off", "Slukket")})]
STEP_LABELS = {"resize": "skærm genopsat", "resume": "side genoptaget", "reload": "side genindlæst",
               "restart": "Chrome genstartet", "chrome-restart": "Chrome genstartet", "fallback": "offline-side vist",
               "lightdm": "login-skærm genstartet", "failed": "mislykkedes"}


def timeline(cid, spans, recoveries, t0, t1, range_key, group="kg"):
    out = [f'<div class="kg-chart kg-tl" id="{cid}" data-group="{group}"><div class="kg-y kg-tl-lab">']
    out += [f'<span>{esc(l)}</span>' for l, _, _ in TIMELINE_ROWS]
    out.append('<span>Genopretn.</span></div><div class="kg-plot" tabindex="0" role="img" '
               'aria-label="Tidslinje for kiosk, Chrome og skærm med genopretninger. Brug piletasterne.">')
    spans_json = {}
    for _, key, mapping in TIMELINE_ROWS:
        out.append('<div class="kg-tl-row">')
        spans_json[key] = []
        for a, b, val in spans.get(key, []):
            cls, txt = mapping.get(val, ("st-unk", str(val)))
            spans_json[key].append([a, b, txt, cls])
            out.append(f'<i class="{cls}" style="left:{(a - t0) / (t1 - t0) * 100:.3f}%;width:{(b - a) / (t1 - t0) * 100:.3f}%"></i>')
        out.append("</div>")
    out.append('<div class="kg-tl-row kg-tl-ev">')
    evs = []
    for e in recoveries:
        step = str(e.get("step") or "")
        what = STEP_LABELS.get(step, step)
        evs.append([e["t"], what, e.get("reason", ""), tip_time(e["t"], "7d" if range_key == "7d" else "6t")])
        out.append(f'<b class="ev{" ev-bad" if step == "failed" else ""}" style="left:{(e["t"] - t0) / (t1 - t0) * 100:.3f}%">'
                   f'{TRIANGLE}</b>')
    out.append('</div><div class="kg-cross"></div><div class="kg-tip" hidden></div></div>')
    out.append(f'<div class="kg-x">{_xlabels(t0, t1, range_key)}</div>')
    data = {"timeline": True, "t0": t0, "t1": t1, "rows": [[l, k] for l, k, _ in TIMELINE_ROWS], "spans": spans_json,
            "ev": evs, "range": range_key}
    out.append(f'<script type="application/json" class="kg-data">{_json(data)}</script></div>')
    return "".join(out)


TABLE_ROW = {"1t": 300, "6t": 900, "24t": 3600, "7d": 6 * 3600}


def table_view(buckets, series, range_key):
    """series: [(key, label, unit, dec)]. Averages per 5 min / 15 min / hour / 6 hours on the clock, newest first."""
    row = TABLE_ROW[range_key]
    groups = {}
    for b in buckets:
        off = (local(b["t"]).utcoffset() or dt.timedelta(0)).total_seconds()
        start = int((b["t"] + off) // row * row - off)
        groups.setdefault(start, []).append(b)
    head = "".join(f'<th scope="col">{esc(l)}</th>' for _, l, _, _ in series)
    body = []
    for start in sorted(groups, reverse=True):
        chunk = groups[start]
        cells = []
        for k, _, unit, dec in series:
            vs = [b[k][0] for b in chunk if b.get(k)]
            cells.append(f"<td>{fmt_unit(sum(vs) / len(vs), dec, unit) if vs else '–'}</td>")
        body.append(f'<tr><th scope="row">{esc(tip_time(start, "7d" if range_key == "7d" else "6t"))}</th>{"".join(cells)}</tr>')
    if not body:
        body = [f'<tr><td colspan="{len(series) + 1}">Ingen målinger i perioden endnu.</td></tr>']
    return (f'<details class="kg-more" data-k="table"><summary>Vis som tabel</summary><div class="kg-table-wrap">'
            f'<table class="fd-table"><thead><tr><th scope="col">Tidspunkt</th>{head}</tr></thead><tbody>{"".join(body)}'
            f'</tbody></table></div></details>')


def _block(title, note, chart):
    return f'<div class="kg-block"><h3>{esc(title)}<small>{esc(note)}</small></h3>{chart}</div>'


def render_pane(range_key, records, events, ha_power, now, language="da"):
    """The content of the chart panel for one period.

    records: [(t, {key: (avg, min, max)})] sorted, minute records stamped at their middle plus raw samples;
    events: the event log (oldest first); ha_power: whether the Effekt chart applies."""
    _L.lang = "en" if language == "en" else "da"
    key, _, span, step, _ = RANGE[range_key]
    t1 = int(now)
    t0 = t1 - span
    group = "kg-" + range_key
    keys = ["cpu", "ram", "gpu", "cpu_temp", "nvme_temp", "cpu_mhz", "network_kbps", "ha_power", "disk"]
    buckets = bucketize(records, t0, t1, step, keys)
    covered = coverage([t for t, _ in records], t0, t1)
    spans = {k: state_spans(events, k, t0, t1, covered) for _, k, _ in TIMELINE_ROWS}
    recs = [e for e in events if e.get("kind") == "recovery" and t0 <= e["t"] <= t1]

    ok, on = share(spans["health"], "ON"), share(spans["screen"], "ON")
    n_rec = incidents(recs)
    cpu_max = max((b["cpu"][2] for b in buckets if b.get("cpu")), default=None)
    def pct(v):  # 99,58% – never rounded up to a perfect 100%
        if v is None:
            return "–"
        return fmt_num(v, 0) + "%" if v >= 100 or v < 90 else fmt_num(math.floor(v * 100) / 100, 2) + "%"
    stats = (f'<div class="kg-stats"><div><b>{pct(ok)}</b>Kiosk OK</div>'
             f'<div><b class="ic">{TRIANGLE if n_rec else ""}{n_rec}</b>Genopretninger</div>'
             f'<div><b>{chrome_restarts(events, t0, t1)}</b>Chrome-genstarter</div>'
             f'<div><b>{"–" if on is None else fmt_num(on, 0) + "%"}</b>Skærm tændt</div>'
             f'<div><b>{"–" if cpu_max is None else fmt_num(cpu_max, 0) + "%"}</b>Højeste CPU</div></div>')
    tl = timeline(f"kg-tl-{key}", spans, recs, t0, t1, range_key, group)
    keys_html = ('<div class="kg-keys"><span><i class="st-ok"></i>OK / kører</span><span><i class="st-bad"></i>Fejl / stoppet</span>'
                 '<span><i class="st-on"></i>Skærm tændt</span><span><i class="st-off"></i>Skærm slukket</span>'
                 f'<span><i class="st-none"></i>Ingen data</span><span>{TRIANGLE}Genopretning</span></div>')
    banded = step > 10

    def lc(cid, series, unit, dec=0, **kw):
        return line_chart(f"kg-{cid}-{key}", buckets, series, t0, t1, range_key, unit, dec, group=group, **kw)

    charts = (_block("Belastning", "%", lc("load", [("cpu", "CPU", 1), ("ram", "RAM", 2), ("gpu", "GPU", 3)], "%",
                                           fixed=(0, 100), height=150, label="Belastning: CPU, RAM og GPU i procent"))
              + _block("Temperatur", "°C", lc("temp", [("cpu_temp", "CPU", 1), ("nvme_temp", "NVMe", 2)], "°C", 1,
                                              height=120, label="Temperatur: CPU og NVMe i grader"))
              + (_block("Effekt", "W · fra Home Assistant", lc("pow", [("ha_power", "Effekt", 1)], "W", 1, band=banded,
                                                                area=not banded, height=110, label="Effekt i watt"))
                 if ha_power else ""))
    more = ('<details class="kg-more" data-k="more"><summary>Flere målinger (netværk, CPU-frekvens, disk)</summary>'
            '<div class="kg-stack">'
            + _block("Netværk", "KiB/s, ind og ud", lc("net", [("network_kbps", "Netværk", 1)], "KiB/s", 1, band=banded,
                                                       area=not banded, height=110, label="Netværk i KiB/s"))
            + _block("CPU-frekvens", "MHz", lc("mhz", [("cpu_mhz", "Frekvens", 1)], "MHz", 0, band=banded, area=not banded,
                                               height=110, label="CPU-frekvens i MHz"))
            + _block("Disk", "% brugt", lc("disk", [("disk", "Disk", 1)], "%", 1, fixed=(0, 100), height=90,
                                           label="Disk brugt i procent"))
            + "</div></details>")
    table_series = [("cpu", "CPU", "%", 1), ("ram", "RAM", "%", 0), ("gpu", "GPU", "%", 1), ("cpu_temp", "CPU-temp.", "°C", 1),
                    ("nvme_temp", "NVMe-temp.", "°C", 1)] + ([("ha_power", "Effekt", "W", 1)] if ha_power else []) + \
                   [("network_kbps", "Netværk", "KiB/s", 1), ("disk", "Disk", "%", 1)]
    return (f'<div class="kg-pane" data-range="{key}">{stats}{tl}{keys_html}<div class="kg-stack kg-charts">{charts}</div>'
            f'{more}{table_view(buckets, table_series, range_key)}</div>')


def range_buttons(active):
    return ('<div class="seg kg-seg" role="group" aria-label="Periode">' + "".join(
        f'<button type="button" data-kg-range="{k}" data-refresh="{r}" aria-pressed="{"true" if k == active else "false"}">'
        f'{l if lang() == "da" else RANGE_EN[k]}</button>'
        for k, l, _, _, r in RANGES) + "</div>")


def render_panel(range_key, pane_html):
    return (f'<section class="kg-panel" id="kgPanel" data-range="{range_key}" aria-label="Helbred og belastning">'
            '<div class="kg-panel-head"><h2>Helbred og belastning</h2>'
            '<span class="kg-note">Fælles tidsakse · hold musen over for status og værdier</span>'
            f'{range_buttons(range_key)}</div><div class="kg-body">{pane_html}</div></section>')
