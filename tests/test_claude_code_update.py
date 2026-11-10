import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "claude-code-update.sh"


class ClaudeCodeUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.log = self.dir / "mqtt.log"
        (self.dir / "mqtt-lib.sh").write_text(
            'KIOSK_ID=test_kiosk\nBASE_TOPIC=home/kiosk/test_kiosk\n'
            f'mqtt_pub() {{ printf "%s\\t%s\\n" "$1" "$2" >> "{self.log}"; }}\n')
        self.version = self.dir / "version"
        self.version.write_text("2.1.280")
        self.claude = self.dir / "claude"
        self.claude.write_text(
            "#!/usr/bin/env bash\n"
            f'if [[ "$1" == --version ]]; then echo "$(cat {self.version}) (Claude Code)"; exit 0; fi\n'
            f'if [[ "$1" == update ]]; then [[ -f {self.dir}/fail ]] && {{ echo "network down"; exit 1; }}; echo 2.1.322 > {self.version}; echo updated; exit 0; fi\n'
            "exit 2\n")
        self.claude.chmod(0o755)
        self.tags = self.dir / "tags.json"
        self.tags.write_text(json.dumps({"latest": "2.1.322", "stable": "2.1.300"}))
        home = self.dir / "home"
        (home / ".claude").mkdir(parents=True)
        self.settings = home / ".claude" / "settings.json"
        self.env = dict(os.environ, HOME=str(home), KIOSK_DIR=str(self.dir), CLAUDE_BIN=str(self.claude),
                        CLAUDE_DIST_TAGS_FILE=str(self.tags), KIOSK_WARDEN_RUN_DIR=str(self.dir / "run"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, check=True):
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.env, capture_output=True, text=True, check=check)

    def topics(self):
        out = {}
        for line in self.log.read_text().splitlines():
            topic, payload = line.split("\t", 1)
            out[topic] = payload
        return out

    def test_check_uses_the_channel_from_settings(self):
        state = json.loads(self.run_script("check").stdout)
        self.assertEqual((state["installed"], state["latest"], state["channel"]), ("2.1.280", "2.1.322", "latest"))
        self.settings.write_text(json.dumps({"autoUpdatesChannel": "stable"}))
        state = json.loads(self.run_script("check").stdout)
        self.assertEqual((state["latest"], state["channel"]), ("2.1.300", "stable"))

    def test_publish_makes_an_update_entity_with_install(self):
        self.run_script("publish")
        t = self.topics()
        config = json.loads(t["homeassistant/update/test_kiosk/claude_code/config"])
        self.assertEqual(config["command_topic"], "home/kiosk/test_kiosk/claude_code/install")
        state = json.loads(t["home/kiosk/test_kiosk/claude_code/state"])
        self.assertEqual((state["installed_version"], state["latest_version"], state["in_progress"]), ("2.1.280", "2.1.322", False))
        self.assertLessEqual(len(state["release_summary"]), 255)

    def test_install_updates_and_reports_the_new_version(self):
        self.run_script("install")
        state = json.loads(self.topics()["home/kiosk/test_kiosk/claude_code/state"])
        self.assertEqual(state["installed_version"], "2.1.322")
        self.assertEqual(json.loads((self.dir / "claude-code-update.last").read_text())["state"], "done")

    def test_a_failed_install_is_shown(self):
        (self.dir / "fail").write_text("")
        self.assertNotEqual(self.run_script("install", check=False).returncode, 0)
        state = json.loads(self.topics()["home/kiosk/test_kiosk/claude_code/state"])
        self.assertTrue(state["release_summary"].startswith("Sidste opdatering fejlede: network down"))

    def test_without_claude_the_entity_is_removed(self):
        self.env["CLAUDE_BIN"] = str(self.dir / "missing")
        self.run_script("publish")
        self.assertEqual(self.topics()["homeassistant/update/test_kiosk/claude_code/config"], "")


if __name__ == "__main__":
    unittest.main()
