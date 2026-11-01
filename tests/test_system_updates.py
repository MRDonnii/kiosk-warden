import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "system-updates.sh"

APT_SIMULATION = """\
NOTE: This is only a simulation!
Inst google-chrome-stable [155.0.8059.79-1] (156.0.8078.79-1 Google:1.0/stable [amd64])
Inst libssl3t64 [3.0.13-0ubuntu3.5] (3.0.13-0ubuntu3.6 Ubuntu:24.04/noble-security [amd64])
Inst linux-image-7.0.0-42-generic (7.0.0-42.42~24.04.1 Ubuntu:24.04/noble-updates [amd64])
Inst xserver-xorg-core [2:21.1.12-1ubuntu1.8] (2:21.1.12-1ubuntu1.9 Ubuntu:24.04/noble-updates [amd64])
Conf google-chrome-stable (156.0.8078.79-1 Google:1.0/stable [amd64])
"""

SNAP_LIST = """\
Name     Version  Rev   Size   Publisher  Notes
firefox  159.0-1  9137  297MB  mozilla**  -
"""


def run(*args, stdin=None, files=True):
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        if files:
            apt = pathlib.Path(tmp) / "apt.txt"
            apt.write_text(APT_SIMULATION)
            snap = pathlib.Path(tmp) / "snap.txt"
            snap.write_text(SNAP_LIST)
            env.update(APT_SIMULATION_FILE=str(apt), SNAP_LIST_FILE=str(snap))
        return subprocess.run(["bash", str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=env, check=True).stdout


class SystemUpdatesTest(unittest.TestCase):
    def test_check_reads_the_simulated_upgrade(self):
        state = json.loads(run("check"))
        names = [p["name"] for p in state["apt"]]
        self.assertEqual(names, ["google-chrome-stable", "libssl3t64", "linux-image-7.0.0-42-generic", "xserver-xorg-core"])
        chrome = state["apt"][0]
        self.assertEqual((chrome["from"], chrome["to"]), ("155.0.8059.79-1", "156.0.8078.79-1"))
        kernel = state["apt"][2]
        self.assertEqual((kernel["from"], kernel["to"]), ("", "7.0.0-42.42~24.04.1"))
        self.assertEqual(state["snaps"], [{"name": "firefox", "to": "159.0-1"}])
        self.assertEqual((state["count"], state["security"], state["new_kernel"]), (5, 1, True))

    def test_summary_names_known_packages_and_counts_the_rest(self):
        text = run("summary")
        self.assertIn("kerne 7.0.0-42-generic", text)
        self.assertIn("Chrome 156.0.8078.79", text)
        self.assertIn("Xorg 21.1.12", text)
        self.assertIn("Firefox 159.0", text)
        self.assertIn("+ 1 anden", text)
        self.assertIn("1 sikkerhedsopdatering. Kræver", text)
        self.assertIn("Kræver genstart bagefter.", text)
        self.assertLessEqual(len(text.strip()), 255)

    def test_summary_when_nothing_is_pending(self):
        state = {"apt": [], "snaps": [], "count": 0, "security": 0, "new_kernel": False, "reboot_required": True}
        text = run("summarize", stdin=json.dumps(state), files=False).strip()
        self.assertEqual(text, "Alt er opdateret. Genstart kiosken for at tage de sidste opdateringer i brug.")


if __name__ == "__main__":
    unittest.main()
