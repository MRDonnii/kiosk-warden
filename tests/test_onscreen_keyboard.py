"""On-screen keyboard helpers in mqtt-control.sh (Claude AI, 2026-11-21).

The functions are cut out of the script and run with stub commands, so no X server is needed.
"""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "mqtt-control.sh").read_text(encoding="utf-8")


def function(name):
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", SCRIPT, re.S | re.M)
    if not match:
        raise AssertionError(f"{name} not found in mqtt-control.sh")
    return match.group(0)


def run(call, symbols="pc+us+inet(evdev)", layout="dk", geometry="1920 1080"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        log = tmp / "calls.log"
        stubs = {
            "setxkbmap": f'echo "setxkbmap $*" >> "{log}"',
            "xkbcomp": f"printf 'xkb_keymap {{\\n  xkb_symbols \"{symbols}\" {{\\n'",
            "xdotool": f'echo "{geometry}"',
            "gsettings": f'echo "gsettings $*" >> "{log}"',
        }
        for name, body in stubs.items():
            path = tmp / name
            path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
            path.chmod(0o755)
        defaults = tmp / "keyboard"
        defaults.write_text(f'XKBMODEL="pc105"\nXKBLAYOUT="{layout}"\n', encoding="utf-8")
        env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}", KIOSK_KEYBOARD_DEFAULTS=str(defaults), DISPLAY=":0")
        script = function("apply_system_keymap") + function("prepare_onboard") + call + "\n"
        subprocess.run(["bash", "-c", script], env=env, check=True)
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


class OnscreenKeyboardTest(unittest.TestCase):
    def test_keymap_follows_system_layout(self):
        self.assertEqual(run("apply_system_keymap"), ["setxkbmap dk"])

    def test_keymap_left_alone_when_already_active(self):
        self.assertEqual(run("apply_system_keymap", symbols="pc+dk+inet(evdev)"), [])

    def test_first_layout_of_a_list_is_used(self):
        self.assertEqual(run("apply_system_keymap", layout="dk,us"), ["setxkbmap dk"])

    def test_onboard_undocked_on_top_over_bottom_third(self):
        calls = run("prepare_onboard")
        self.assertIn("gsettings set org.onboard.window docking-enabled false", calls)
        self.assertIn("gsettings set org.onboard.window force-to-top true", calls)
        self.assertIn("gsettings set org.onboard.window.landscape y 720", calls)
        self.assertIn("gsettings set org.onboard.window.landscape width 1920", calls)
        self.assertIn("gsettings set org.onboard.window.landscape height 360", calls)

    def test_portrait_screen_uses_portrait_geometry(self):
        calls = run("prepare_onboard", geometry="1080 1920")
        self.assertIn("gsettings set org.onboard.window.portrait y 1280", calls)
        self.assertIn("gsettings set org.onboard.window.portrait height 640", calls)


if __name__ == "__main__":
    unittest.main()
