import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "display-recover-root.sh"
GUARD = ROOT / "scripts" / "display-guard.sh"

GREETER_ONLY = "c2 106 lightdm seat0 900 greeter - no -\n1 1000 donnii - 800 manager - no -\n"
KIOSK_UP = "2 1000 donnii seat0 901 user - no -\n1 1000 donnii - 800 manager - no -\n"


class Env:
    """A temp dir with stub loginctl/lightdm/systemctl/logger/sudo, so the scripts run without root or systemd."""

    def __init__(self, sessions=GREETER_ONLY, autologin="donnii", lightdm_enabled=True, lightdm_since_us=1_000_000):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.state = self.dir / "state"
        self.kiosk = self.dir / "kiosk"
        self.kiosk.mkdir()
        self.calls = self.dir / "calls.log"
        self.set_sessions(sessions)
        self.stub("loginctl", f'cat "{self.dir}/sessions"')
        # Like the real lightdm, the configuration goes to stderr.
        self.stub("lightdm", f'[ "$1" = --show-config ] && printf "A  [Seat:*]\\nE  autologin-user={autologin}\\n" >&2' if autologin else 'exit 0')
        self.stub(
            "systemctl",
            f'''case "$1" in
  is-enabled) {"exit 0" if lightdm_enabled else "exit 1"} ;;
  is-active) [ -f "{self.dir}/lightdm-inactive" ] && exit 3; exit 0 ;;
  show) echo {lightdm_since_us} ;;
  restart) echo "systemctl $*" >> "{self.calls}" ;;
esac''',
        )
        self.stub("logger", "exit 0")

    def set_sessions(self, text):
        (self.dir / "sessions").write_text(text)

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def env(self, **extra):
        env = dict(os.environ)
        env.update(
            PATH=f"{self.bin}:{env['PATH']}",
            KIOSK_DIR=str(self.kiosk),
            KIOSK_WARDEN_TEST="1",
            KIOSK_WARDEN_TEST_STATE_DIR=str(self.state),
            SUDO_USER="donnii",
        )
        env.update(extra)
        return env

    def helper(self, **extra):
        return subprocess.run(["bash", str(HELPER)], env=self.env(**extra), capture_output=True, text=True)

    def restarts(self):
        return self.calls.read_text().count("restart lightdm") if self.calls.exists() else 0

    def log(self):
        path = self.kiosk / "recovery.log"
        return path.read_text() if path.exists() else ""

    def session_state(self):
        path = self.kiosk / "display_session"
        return path.read_text().strip() if path.exists() else ""

    def close(self):
        self.tmp.cleanup()


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.addCleanup(self.e.close)

    def test_restarts_lightdm_when_only_the_greeter_shows(self):
        r = self.e.helper(KIOSK_WARDEN_TEST_UPTIME="5000", KIOSK_WARDEN_TEST_NOW="100000")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.e.restarts(), 1)

    def test_does_nothing_when_a_graphical_session_exists(self):
        self.e.set_sessions(KIOSK_UP)
        r = self.e.helper(KIOSK_WARDEN_TEST_UPTIME="5000")
        self.assertEqual(r.returncode, 10)
        self.assertEqual(self.e.restarts(), 0)

    def test_manager_session_without_seat_does_not_count_as_graphical(self):
        self.e.set_sessions("1 1000 donnii - 800 manager - no -\n7 1000 donnii - 801 user - no -\n")
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_UPTIME="5000").returncode, 0)

    def test_refuses_when_autologin_is_for_someone_else(self):
        r = self.e.helper(KIOSK_WARDEN_TEST_UPTIME="5000", SUDO_USER="mallory")
        self.assertEqual(r.returncode, 12)
        self.assertEqual(self.e.restarts(), 0)

    def test_refuses_when_autologin_is_not_configured(self):
        e = Env(autologin="")
        self.addCleanup(e.close)
        self.assertEqual(e.helper(KIOSK_WARDEN_TEST_UPTIME="5000").returncode, 12)
        self.assertEqual(e.restarts(), 0)

    def test_refuses_when_lightdm_is_not_the_display_manager(self):
        e = Env(lightdm_enabled=False)
        self.addCleanup(e.close)
        self.assertEqual(e.helper(KIOSK_WARDEN_TEST_UPTIME="5000").returncode, 13)
        self.assertEqual(e.restarts(), 0)

    def test_waits_while_lightdm_has_just_started(self):
        e = Env(lightdm_since_us=4_950_000_000)  # started at 4950 s, now 5000 s
        self.addCleanup(e.close)
        self.assertEqual(e.helper(KIOSK_WARDEN_TEST_UPTIME="5000").returncode, 10)
        self.assertEqual(e.restarts(), 0)

    def test_needs_sudo_user(self):
        env = self.e.env()
        env.pop("SUDO_USER")
        r = subprocess.run(["bash", str(HELPER)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_refuses_to_run_as_non_root_without_test_mode(self):
        env = self.e.env()
        env.pop("KIOSK_WARDEN_TEST")
        r = subprocess.run(["bash", str(HELPER)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_rate_limits_to_three_per_hour_and_two_minutes_apart(self):
        now = 100000
        kw = dict(KIOSK_WARDEN_TEST_UPTIME="5000")
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_NOW=str(now), **kw).returncode, 0)
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_NOW=str(now + 60), **kw).returncode, 11)  # too soon
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_NOW=str(now + 200), **kw).returncode, 0)
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_NOW=str(now + 400), **kw).returncode, 0)
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_NOW=str(now + 600), **kw).returncode, 11)  # 4th within the hour
        self.assertEqual(self.e.restarts(), 3)
        # An hour after the first restart one slot is free again.
        self.assertEqual(self.e.helper(KIOSK_WARDEN_TEST_NOW=str(now + 3700), **kw).returncode, 0)
        self.assertEqual(self.e.restarts(), 4)


def guard(e, script, **extra):
    """Run a bash snippet that sources display-guard.sh; the snippet can call display_guard_tick repeatedly."""
    env = e.env(**extra)
    env["KIOSK_DISPLAY_RECOVER_CMD"] = f"bash {HELPER}"
    return subprocess.run(
        ["bash", "-c", f'source "{GUARD}"\n{script}'], env=env, capture_output=True, text=True
    )


BASE = 100000  # fake epoch seconds; the tests pass offsets from it


def ticks(offsets):
    return "\n".join(f'KIOSK_DISPLAY_GUARD_NOW={BASE + t} display_guard_tick' for t in offsets)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.addCleanup(self.e.close)
        self.kw = dict(KIOSK_DISPLAY_GUARD_UPTIME="5000", KIOSK_WARDEN_TEST_UPTIME="5000")

    def test_healthy_session_does_nothing(self):
        self.e.set_sessions(KIOSK_UP)
        r = guard(self.e, ticks([0, 15, 30, 200]), **self.kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.e.restarts(), 0)
        self.assertEqual(self.e.session_state(), "ok")

    def test_login_screen_is_recovered_after_the_grace_period(self):
        r = guard(self.e, ticks([0, 15, 30, 45]), **self.kw)  # 45 s: still waiting
        self.assertEqual(self.e.restarts(), 0, r.stderr)
        self.assertEqual(self.e.session_state(), "missing")
        r = guard(self.e, ticks([0, 30, 61]), **self.kw)  # 61 s: recover
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.e.restarts(), 1)
        self.assertIn("restarted lightdm", self.e.log())
        self.assertEqual(self.e.session_state(), "recovering")

    def test_a_short_glitch_is_not_recovered(self):
        script = "\n".join(
            [
                f"KIOSK_DISPLAY_GUARD_NOW={BASE + 0} display_guard_tick",  # missing
                f'cp "{self.e.dir}/sessions" "{self.e.dir}/sessions.greeter"',
                f'printf "%s" "{KIOSK_UP}" > "{self.e.dir}/sessions"',
                f"KIOSK_DISPLAY_GUARD_NOW={BASE + 30} display_guard_tick",  # back
                f'cp "{self.e.dir}/sessions.greeter" "{self.e.dir}/sessions"',
                f"KIOSK_DISPLAY_GUARD_NOW={BASE + 50} display_guard_tick",  # missing again, clock restarts
                f"KIOSK_DISPLAY_GUARD_NOW={BASE + 100} display_guard_tick",  # only 50 s since it restarted
            ]
        )
        guard(self.e, script, **self.kw)
        self.assertEqual(self.e.restarts(), 0)

    def test_waits_for_the_autologin_right_after_boot(self):
        r = guard(self.e, ticks([0, 100, 200]), KIOSK_DISPLAY_GUARD_UPTIME="120", KIOSK_WARDEN_TEST_UPTIME="120")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.e.restarts(), 0)
        self.assertEqual(self.e.session_state(), "starting")

    def test_does_not_try_again_within_five_minutes(self):
        # The helper's own gap is 2 minutes; the guard's cooldown is 5 minutes, so only one restart in 4 minutes.
        guard(self.e, ticks([0, 61, 100, 200, 300]), **self.kw)
        self.assertEqual(self.e.restarts(), 1)

    def test_not_applicable_when_lightdm_is_not_running(self):
        (self.e.dir / "lightdm-inactive").write_text("")
        guard(self.e, ticks([0, 100]), **self.kw)
        self.assertEqual(self.e.restarts(), 0)
        self.assertEqual(self.e.session_state(), "not-applicable")

    def test_can_be_turned_off(self):
        guard(self.e, ticks([0, 100]), KIOSK_DISPLAY_RECOVERY="false", **self.kw)
        self.assertEqual(self.e.restarts(), 0)

    def test_missing_setup_is_reported_once_an_hour(self):
        env_script = ticks([0, 61, 500, 900])
        r = subprocess.run(
            ["bash", "-c", f'source "{GUARD}"\n{env_script}'],
            env=self.e.env(KIOSK_DISPLAY_RECOVER_CMD="/nonexistent-helper", **self.kw),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.e.log().count("recovery is not set up"), 1)
        self.assertIn("setup-display-recovery.sh", self.e.log())
        self.assertEqual(self.e.session_state(), "not-set-up")

    def test_cli_prints_the_state(self):
        for sessions, expected in ((GREETER_ONLY, "missing"), (KIOSK_UP, "ok")):
            self.e.set_sessions(sessions)
            r = subprocess.run(["bash", str(GUARD)], env=self.e.env(), capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), expected, r.stderr)


if __name__ == "__main__":
    unittest.main()
