"""Status page charts (1.26.0): minute history, event log, chart maths and the recovery events from the scripts."""
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webui"))
os.environ["TZ"] = "Europe/Copenhagen"
time.tzset()

import charts  # noqa: E402
import history  # noqa: E402

SPEC = importlib.util.spec_from_file_location("warden_server_charts", ROOT / "webui" / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)

NOW = 1795175400  # 2026-11-20 10:50 local time


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


def sample(t, **values):
    base = {"time": t, "cpu": 10.0, "ram": 40.0, "gpu": 5.0, "cpu_temp": 45.0, "nvme_temp": 36.0, "cpu_mhz": 1200,
            "network_kbps": 3.0, "ha_power": None, "disk": 38.0}
    base.update(values)
    return base


class MinuteStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "telemetry")
        self.clock = Clock()

    def store(self):
        return history.MinuteStore(self.dir, clock=self.clock)

    def test_average_min_and_max_per_minute_survive_a_restart(self):
        s = self.store()
        m = NOW // 60 * 60
        for i, cpu in enumerate((10, 30, 20)):
            s.add_sample(sample(m + i * 10, cpu=cpu))
        s.add_sample(sample(m + 60, cpu=50))  # next minute closes the first
        (t, vals), (t2, partial) = s.records(0)
        self.assertEqual(t, m)
        self.assertEqual(tuple(round(v, 1) for v in vals["cpu"]), (20.0, 10.0, 30.0))
        self.assertNotIn("ha_power", vals)  # never measured: no value, no zero
        self.assertEqual(partial["cpu"], (50.0, 50.0, 50.0))  # the minute in progress is shown too
        again = self.store()
        self.assertEqual(again.load(), 1)
        (t, vals), = again.records(0)
        self.assertEqual((t, round(vals["cpu"][0], 1), vals["disk"]), (m, 20.0, (38.0, 38.0, 38.0)))

    def test_a_half_written_line_is_skipped_and_the_next_line_starts_fresh(self):
        s = self.store()
        m = NOW // 60 * 60
        s.add_sample(sample(m))
        s.add_sample(sample(m + 60))
        path = os.path.join(self.dir, time.strftime("%Y-%m-%d", time.localtime(m)) + ".jsonl")
        with open(path, "a") as f:
            f.write('{"t":%d,"c":[1' % (m + 60))  # power cut mid-write
        s.add_sample(sample(m + 120))  # closes minute m+60
        lines = pathlib.Path(path).read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[-1])["t"], m + 60)
        again = self.store()
        self.assertEqual(again.load(), 2)

    def test_old_days_are_deleted_and_memory_trimmed(self):
        os.makedirs(self.dir)
        old = time.strftime("%Y-%m-%d", time.localtime(NOW - 10 * 86400))
        keep = time.strftime("%Y-%m-%d", time.localtime(NOW - 86400))
        pathlib.Path(self.dir, old + ".jsonl").write_text('{"t":%d,"c":5}\n' % (NOW - 10 * 86400))
        pathlib.Path(self.dir, keep + ".jsonl").write_text('{"t":%d,"c":5}\n{"t":%d,"c":6}\n' % (NOW - 86400, NOW - 9 * 86400))
        pathlib.Path(self.dir, "notes.txt").write_text("not ours")
        s = self.store()
        self.assertEqual(s.load(), 1)
        self.assertEqual(sorted(os.listdir(self.dir)), sorted([keep + ".jsonl", "notes.txt"]))

    def test_a_day_on_disk_stays_small(self):
        s = self.store()
        start = NOW // 86400 * 86400
        for t in range(start, start + 86400, 10):
            s.add_sample(sample(t, cpu=(t % 97) / 1.3, ram=40 + (t % 13) / 10, cpu_mhz=800 + t % 2000,
                                network_kbps=(t % 37) / 3, ha_power=12.3 + (t % 7) / 10))
        size = sum(os.path.getsize(os.path.join(self.dir, n)) for n in os.listdir(self.dir))
        self.assertLess(size, 300 * 1024)  # ~2 MB for 8 days


class EventLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "events.jsonl")
        self.clock = Clock()
        self.log = history.EventLog(self.path, max_lines=50, clock=self.clock)

    def test_reasons_lose_secrets(self):
        e = self.log.append("recovery", step="reload", reason="Unexpected URL: https://me:pw@ha.local/lovelace?auth_callback=1&token=abc "
                            "and api_key=xyz", source="health-check")
        text = pathlib.Path(self.path).read_text()
        for secret in ("pw@", "abc", "xyz", "auth_callback"):
            self.assertNotIn(secret, text)
        self.assertIn("https://ha.local/lovelace", e["reason"])
        self.assertEqual(self.log.read()[0]["step"], "reload")

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            self.log.append("password", value="x")

    def test_trim_keeps_eight_days_and_the_state_before(self):
        self.log.append("screen", value="OFF", t=NOW - 20 * 86400)
        self.log.append("screen", value="ON", t=NOW - 10 * 86400)
        self.log.append("recovery", step="reload", t=NOW - 9 * 86400)
        for i in range(60):
            self.log.append("recovery", step="resume", t=NOW - 3600 + i)
        with open(self.path, "a") as f:
            f.write("garbage\n")
        self.assertGreater(self.log.trim(), 0)
        items = self.log.read()
        self.assertEqual(items[0], {"t": NOW - 10 * 86400, "kind": "screen", "value": "ON"})
        self.assertEqual(len(items), 51)
        self.assertEqual(self.log.last_values(), {"screen": "ON"})
        self.assertEqual(self.log.trim(), 0)


class ChartMathTests(unittest.TestCase):
    def test_buckets_keep_short_peaks(self):
        recs = [(t, {"cpu": (v, v, v)}) for t, v in ((1000, 5), (1010, 95), (1020, 5))]
        (b,) = charts.bucketize(recs, 900, 1300, 240, ["cpu"])
        self.assertEqual(b["cpu"], (35.0, 5, 95))

    def test_a_pause_breaks_the_line(self):
        recs = [(t, {"cpu": (1.0, 1.0, 1.0)}) for t in list(range(0, 600, 60)) + list(range(1800, 2400, 60))]
        buckets = charts.bucketize(recs, 0, 2400, 60, ["cpu"])
        segs = list(charts._segments(buckets, "cpu", charts.gap_for(60)))
        self.assertEqual(len(segs), 2)
        html = charts.line_chart("x", buckets, [("cpu", "CPU", 1)], 0, 2400, "1t", "%", fixed=(0, 100))
        path = re.search(r'class="kg-line s1" d="([^"]+)"', html).group(1)
        self.assertEqual(path.count("M"), 2)

    def test_axis_steps(self):
        self.assertEqual(charts.nice_step(70), 20)
        self.assertEqual(charts.y_domain([{"t": 0, "a": (43, 41, 48)}, {"t": 1, "a": (61, 60, 63)}], ["a"]), (40, 65, 5))
        ticks = charts.x_ticks(NOW - 86400, NOW, "24t")
        self.assertEqual([label for _, label in ticks], ["13:00", "17:00", "21:00", "01:00", "05:00", "09:00"])
        days = charts.x_ticks(NOW - 7 * 86400, NOW, "7d")
        self.assertTrue(all(time.localtime(t).tm_hour == 0 for t, _ in days))
        self.assertEqual(len(days), 7)

    def test_number_format_follows_the_language(self):
        charts._L.lang = "da"
        self.assertEqual(charts.fmt_unit(1011.46, 1, "MHz"), "1 011,5 MHz")
        self.assertEqual(charts.fmt_unit(7.94, 1, "%"), "7,9%")
        charts._L.lang = "en"
        self.assertEqual(charts.fmt_unit(1011.46, 1, "MHz"), "1,011.5 MHz")
        charts._L.lang = "da"

    def test_state_spans_share_and_unknown_time(self):
        events = [{"t": 0, "kind": "health", "value": "ON"}, {"t": 600, "kind": "health", "value": "OFF"},
                  {"t": 660, "kind": "health", "value": "ON"}]
        covered = charts.coverage(list(range(0, 1200, 60)) + list(range(2400, 3600, 60)), 0, 3600)
        self.assertEqual(covered, [(0, 1200), (2400, 3600)])
        spans = charts.state_spans(events, "health", 0, 3600, covered)
        self.assertEqual(spans, [(0, 600, "ON"), (600, 660, "OFF"), (660, 1200, "ON"), (2400, 3600, "ON")])
        self.assertAlmostEqual(charts.share(spans, "ON"), 100 * 2340 / 2400)
        self.assertIsNone(charts.share([], "ON"))

    def test_counting_recoveries_and_chrome_restarts(self):
        events = [{"t": 100, "kind": "recovery", "step": "failed"}, {"t": 110, "kind": "recovery", "step": "fallback"},
                  {"t": 500, "kind": "recovery", "step": "restart"},  # too quick to be seen stopped
                  {"t": 900, "kind": "chrome", "value": "down"}, {"t": 905, "kind": "recovery", "step": "chrome-restart"},
                  {"t": 920, "kind": "chrome", "value": "up"}]
        recs = [e for e in events if e["kind"] == "recovery"]
        self.assertEqual(charts.incidents(recs), 3)
        self.assertEqual(charts.chrome_restarts(events, 0, 1000), 2)

    def test_pane_renders_without_any_data(self):
        pane = charts.render_pane("7d", [], [], True, NOW)
        self.assertIn("Ingen målinger i perioden endnu.", pane)
        self.assertIn("<b>–</b>Kiosk OK", pane)

    def test_pane_with_data(self):
        recs = [(t + 30, {"cpu": (12.0, 3.0, 60.0), "ram": (41.0, 41.0, 41.0), "ha_power": (14.5, 14.0, 15.0)})
                for t in range(NOW - 86400, NOW, 60)]
        events = [{"t": NOW - 90000, "kind": "health", "value": "ON"}, {"t": NOW - 90000, "kind": "screen", "value": "ON"},
                  {"t": NOW - 3000, "kind": "recovery", "step": "reload", "reason": "No Chrome page"}]
        pane = charts.render_pane("24t", recs, events, True, NOW)
        self.assertIn("<b>100%</b>Kiosk OK", pane)
        self.assertIn("60%</b>Højeste CPU", pane)
        self.assertIn('id="kg-pow-24t"', pane)
        self.assertNotIn('id="kg-pow-24t"', charts.render_pane("24t", recs, events, False, NOW))
        self.assertEqual(pane.count('class="ev"'), 1)
        self.assertIn("side genindlæst", pane)
        for data in re.findall(r'class="kg-data">(.*?)</script>', pane):
            json.loads(data)  # valid, and no "</" can end the script early
        rows = re.findall(r'<tr><th scope="row">([^<]+)</th>', pane)
        self.assertEqual(len(rows), 25)
        self.assertTrue(rows[1].endswith(":00"))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = SERVER.KIOSK_DIR
        SERVER.KIOSK_DIR = self.tmp.name
        self.addCleanup(setattr, SERVER, "KIOSK_DIR", self.old)
        SERVER._last_states.clear()
        SERVER._chart_cache.clear()

    def test_status_page_has_the_new_charts_and_no_canvas(self):
        conf = {"KIOSK_NAME": "Test", "UI_LANGUAGE": "da"}
        page = SERVER.render_dashboard(conf, chart_range="7d")
        self.assertIn('id="kgPanel" data-range="7d"', page)
        self.assertIn('data-kg-range="7d" data-refresh="300" aria-pressed="true"', page)
        self.assertNotIn("<canvas", page)
        self.assertNotIn("drawChart", page)
        self.assertNotIn("kg-pow-", page)  # no Effekt without Home Assistant
        self.assertLess(page.index('id="kgPanel"'), page.index('class="kv-grid"'))

    def test_state_changes_are_logged_once(self):
        pathlib.Path(self.tmp.name, "health_state").write_text("ON\n")
        pathlib.Path(self.tmp.name, "screen_state").write_text("OFF\n")
        original = SERVER.chrome_is_running
        SERVER.chrome_is_running = lambda: True
        self.addCleanup(setattr, SERVER, "chrome_is_running", original)
        _, events = SERVER.history_stores()
        SERVER.observe_states(events)
        SERVER.observe_states(events)
        pathlib.Path(self.tmp.name, "health_state").write_text("OFF\n")
        SERVER.observe_states(events)
        kinds = [(e["kind"], e["value"]) for e in events.read()]
        self.assertEqual(sorted(kinds), sorted([("health", "ON"), ("screen", "OFF"), ("chrome", "up"), ("health", "OFF")]))
        SERVER._last_states.clear()  # a restarted WebUI picks up where the log left off
        SERVER.observe_states(events)
        self.assertEqual(len(events.read()), 4)

    def test_english_labels_do_not_get_translated_twice(self):
        conf = {"KIOSK_NAME": "Test", "UI_LANGUAGE": "en"}
        page = SERVER.localize_html(SERVER.render_dashboard(conf), "en")
        panel = page[page.index('id="kgPanel"'):page.index('class="kv-grid"')]
        for danish in ("Belastning", "Genopretn", "Skærm", "Vis som tabel", "Tidspunkt", "målinger"):
            self.assertNotIn(danish, panel)
        self.assertNotIn("Temperaturee", panel)
        self.assertIn("Health and load", panel)


class RecoveryEventScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)

    @unittest.skipUnless(shutil.which("jq"), "jq not installed")
    def test_helper_writes_clean_json_lines(self):
        script = f'source "{ROOT}/scripts/kiosk-event.sh"; kiosk_event recovery reload "Unexpected URL: http://u:p@h/x?token=s3cret" health-check; ' \
                 'kiosk_event health ON'
        r = subprocess.run(["bash", "-c", script], env=dict(os.environ, KIOSK_DIR=str(self.dir)), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = (self.dir / "events.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        e = json.loads(lines[0])
        self.assertEqual((e["kind"], e["step"], e["reason"], e["src"]), ("recovery", "reload", "Unexpected URL: http://h/x", "health-check"))

    @unittest.skipUnless(shutil.which("jq"), "jq not installed")
    def test_warden_recovery_is_logged_as_an_event(self):
        from test_warden_recover import Kiosk
        k = Kiosk(screen="ON", page_state="idle")
        self.addCleanup(k.close)
        shutil.copy(ROOT / "scripts" / "kiosk-event.sh", k.dir / "kiosk-event.sh")
        r = k.run("recover", "No Chrome page")
        self.assertEqual(r.returncode, 0, r.stderr)
        (e,) = [json.loads(line) for line in (k.dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual((e["kind"], e["reason"], e["src"]), ("recovery", "No Chrome page", "warden"))
        self.assertIn(e["step"], ("resize", "resume", "reload", "restart"))

    def test_scripts_log_recoveries_and_keep_telemetry_out_of_backups(self):
        health = (ROOT / "scripts" / "health-check.sh").read_text()
        self.assertNotIn('echo "$reason" >> "$HOME/kiosk/recovery.log"', health)  # the old line without a time
        self.assertIn("kiosk_event recovery fallback", health)
        self.assertIn("kiosk_event recovery chrome-restart", (ROOT / "scripts" / "watchdog.sh").read_text())
        self.assertIn("kiosk_event recovery lightdm", (ROOT / "scripts" / "display-guard.sh").read_text())
        self.assertIn('--exclude="kiosk/telemetry"', (ROOT / "scripts" / "backup-kiosk.sh").read_text())
        for installer in ("install.sh", "scripts/self-update.sh"):
            text = (ROOT / installer).read_text()
            self.assertNotRegex(text, r"rm [^\n]*(telemetry|events\.jsonl)")


if __name__ == "__main__":
    unittest.main()
