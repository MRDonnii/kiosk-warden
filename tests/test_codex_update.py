import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "codex-update.sh"


class CodexUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.log = self.dir / "mqtt.log"
        (self.dir / "mqtt-lib.sh").write_text(
            'KIOSK_ID=test_kiosk\nBASE_TOPIC=home/kiosk/test_kiosk\n'
            f'mqtt_pub() {{ printf "%s\\t%s\\n" "$1" "$2" >> "{self.log}"; }}\n')
        self.standalone = self.dir / "standalone"
        self.releases = self.standalone / "releases"
        for v in ("0.150.0", "0.153.4", "0.159.3"):
            (self.releases / f"{v}-x86_64-unknown-linux-musl" / "bin").mkdir(parents=True)
        (self.standalone / "current").symlink_to(self.releases / "0.159.3-x86_64-unknown-linux-musl")
        self.version = self.dir / "version"
        self.version.write_text("0.159.3")
        self.codex = self.dir / "codex"
        self.codex.write_text(
            "#!/usr/bin/env bash\n"
            f'if [[ "$1" == --version ]]; then echo "codex-cli $(cat {self.version})"; exit 0; fi\n'
            f'if [[ "$1" == update ]]; then [[ -f {self.dir}/fail ]] && {{ echo "network down"; exit 1; }}; '
            f'mkdir -p {self.releases}/0.172.0-x86_64-unknown-linux-musl; '
            f'ln -sfn {self.releases}/0.172.0-x86_64-unknown-linux-musl {self.standalone}/current; '
            f'echo 0.172.0 > {self.version}; echo updated; exit 0; fi\n'
            "exit 2\n")
        self.codex.chmod(0o755)
        self.tags = self.dir / "tags.json"
        self.tags.write_text(json.dumps({"latest": "0.172.0", "alpha": "0.174.0-alpha.2"}))
        self.env = dict(os.environ, HOME=str(self.dir / "home"), KIOSK_DIR=str(self.dir), CODEX_BIN=str(self.codex),
                        CODEX_STANDALONE=str(self.standalone), CODEX_DIST_TAGS_FILE=str(self.tags),
                        KIOSK_WARDEN_RUN_DIR=str(self.dir / "run"))

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

    def test_check_reads_installed_and_latest(self):
        state = json.loads(self.run_script("check").stdout)
        self.assertEqual((state["installed"], state["latest"], state["latest_known"]), ("0.159.3", "0.172.0", True))

    def test_publish_makes_an_update_entity_with_install(self):
        self.run_script("publish")
        t = self.topics()
        config = json.loads(t["homeassistant/update/test_kiosk/codex_cli/config"])
        self.assertEqual(config["command_topic"], "home/kiosk/test_kiosk/codex_cli/install")
        state = json.loads(t["home/kiosk/test_kiosk/codex_cli/state"])
        self.assertEqual((state["installed_version"], state["latest_version"], state["in_progress"]), ("0.159.3", "0.172.0", False))
        self.assertLessEqual(len(state["release_summary"]), 255)

    def test_install_updates_and_keeps_only_current_and_previous(self):
        self.run_script("install")
        state = json.loads(self.topics()["home/kiosk/test_kiosk/codex_cli/state"])
        self.assertEqual(state["installed_version"], "0.172.0")
        self.assertEqual(json.loads((self.dir / "codex-update.last").read_text())["state"], "done")
        left = sorted(p.name.split("-")[0] for p in self.releases.iterdir())
        self.assertEqual(left, ["0.159.3", "0.172.0"])

    def test_a_failed_install_is_shown_and_nothing_is_removed(self):
        (self.dir / "fail").write_text("")
        self.assertNotEqual(self.run_script("install", check=False).returncode, 0)
        state = json.loads(self.topics()["home/kiosk/test_kiosk/codex_cli/state"])
        self.assertTrue(state["release_summary"].startswith("Sidste opdatering fejlede: network down"))
        self.assertEqual(len(list(self.releases.iterdir())), 3)

    def test_without_codex_the_entity_is_removed(self):
        self.env["CODEX_BIN"] = str(self.dir / "missing")
        self.run_script("publish")
        self.assertEqual(self.topics()["homeassistant/update/test_kiosk/codex_cli/config"], "")


if __name__ == "__main__":
    unittest.main()
