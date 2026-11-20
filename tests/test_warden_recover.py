import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WARDEN = ROOT / "scripts" / "warden-state.sh"


class Kiosk:
    """A kiosk dir with stub screen backend, Chrome lifecycle and X tools, so warden-state.sh runs without X or Chrome."""

    def __init__(self, screen="ON", page_state="active"):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.calls = self.dir / "calls.log"
        (self.dir / "kiosk.conf").write_text('KIOSK_URL="http://dash.test/"\nKIOSK_WAKE_VERIFY_TRIES=2\n')
        (self.dir / "screen_state").write_text(screen + "\n")
        (self.dir / "page_state").write_text(page_state)
        (self.dir / "screen-backend.sh").write_text("\n".join(
            f'{fn}() {{ echo "{fn}" >> "{self.calls}"; }}'
            for fn in ("screen_prepare_on", "screen_show", "screen_hide")
        ) + '\nscreen_geometry() { echo "{}"; }\nscreen_power_state() { echo On; }\n')
        lifecycle = self.dir / "chrome-lifecycle.py"
        lifecycle.write_text(f"""#!/bin/sh
echo "chrome $*" >> "{self.calls}"
case "$1" in
  active|idle) printf %s "$1" > "{self.dir}/page_state" ;;
  verify) [ "$(cat "{self.dir}/page_state")" = "${{2:-active}}" ] ;;
esac
""")
        lifecycle.chmod(0o755)
        self.stub("xdotool", 'echo "1920 1080"')
        self.stub("curl", """echo '[{"type":"page","url":"http://dash.test/"}]'""")
        self.stub("systemctl", 'echo "systemctl $*" >> "%s"' % self.calls)
        self.stub("sleep", "exit 0")

    def stub(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(0o755)

    def run(self, *args):
        env = dict(os.environ, KIOSK_DIR=str(self.dir), PATH=f"{self.bin}:{os.environ['PATH']}")
        return subprocess.run(["bash", str(WARDEN), *args], env=env, capture_output=True, text=True)

    def log(self):
        return self.calls.read_text().split("\n") if self.calls.exists() else []

    def state(self):
        return json.loads((self.dir / "warden_state.json").read_text())["state"]

    def close(self):
        self.tmp.cleanup()


class RecoverTests(unittest.TestCase):
    def test_recovery_keeps_a_sleeping_screen_asleep(self):
        k = Kiosk(screen="OFF", page_state="active")  # e.g. a restarted Chrome that came back running
        self.addCleanup(k.close)
        r = k.run("recover", "No Chrome page")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = k.log()
        self.assertNotIn("screen_show", calls)
        self.assertNotIn("screen_prepare_on", calls)
        self.assertIn("screen_hide", calls)
        self.assertIn("chrome idle", calls)
        self.assertNotIn("chrome active", calls)
        self.assertIn("chrome verify idle", calls)
        self.assertEqual((k.dir / "page_state").read_text(), "idle")
        self.assertEqual(k.state(), "OFF")

    def test_recovery_of_a_lit_screen_wakes_it_as_before(self):
        k = Kiosk(screen="ON", page_state="idle")
        self.addCleanup(k.close)
        r = k.run("recover", "No Chrome page")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = k.log()
        self.assertIn("screen_show", calls)
        self.assertIn("chrome active", calls)
        self.assertNotIn("screen_hide", calls)
        self.assertEqual(k.state(), "ON")

    def test_failed_recovery_while_off_still_does_not_wake(self):
        k = Kiosk(screen="OFF")
        self.addCleanup(k.close)
        k.stub("curl", "exit 7")  # no page at all, every step fails
        r = k.run("recover", "No Chrome page")
        self.assertNotEqual(r.returncode, 0)
        calls = k.log()
        self.assertNotIn("screen_show", calls)
        self.assertNotIn("screen_prepare_on", calls)

    def test_wake_still_requires_a_running_page(self):
        k = Kiosk(screen="OFF", page_state="idle")
        self.addCleanup(k.close)
        r = k.run("on", "test")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("chrome verify active", k.log())
        self.assertEqual(k.state(), "ON")
        self.assertEqual((k.dir / "screen_state").read_text().strip(), "ON")


if __name__ == "__main__":
    unittest.main()
