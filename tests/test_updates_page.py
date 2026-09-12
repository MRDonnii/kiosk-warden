import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("warden_server", ROOT / "webui" / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class UpdatesPageTest(unittest.TestCase):
    def test_updates_are_on_a_dedicated_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "version").write_text("1.8.0\n")
            (root / "update_channel").write_text("stable\n")
            (root / "CHANGELOG.md").write_text("# Changelog\n\n## v1.8.0\n\n- Update progress\n")
            SERVER.KIOSK_DIR = str(root)
            SERVER.VERSION_PATH = str(root / "version")
            SERVER.UPDATE_CHANNEL_PATH = str(root / "update_channel")
            SERVER.CHANGELOG_PATH = str(root / "CHANGELOG.md")
            SERVER._update_cache["latest"] = {
                "latest_version": "1.8.0",
                "release_url": "https://example.test/v1.8.0",
                "release_summary": "## Highlights\n\n- Dedicated update page",
                "prerelease": False,
            }
            conf = {"KIOSK_NAME": "Test kiosk"}
            updates = SERVER.render_updates(conf)
            settings = SERVER.render_settings(conf)
            self.assertIn("⬇️ Opdateringer", updates)
            self.assertIn("Seneste på Stable", updates)
            self.assertIn('value="beta"', updates)
            self.assertIn("Dedicated update page", updates)
            self.assertIn("Gendan tidligere version", updates)
            self.assertIn("Komplet changelog", updates)
            self.assertIn("Tjek for updates", updates)
            self.assertIn("updateProgressFill", updates)
            self.assertIn("Genstart Kiosk Warden", updates)
            self.assertIn("Genstart maskinen", updates)
            self.assertIn("restart_warden", updates)
            self.assertIn("Genstarter om ${seconds} sekunder", updates)
            self.assertNotIn("Release-kanal og installation", settings)
            self.assertNotIn("Gendan tidligere version", settings)

    def test_control_page_owns_operations_and_power_profile(self):
        conf = {"KIOSK_NAME": "Test kiosk", "KIOSK_ID": "test"}
        original = SERVER.current_power_profile
        SERVER.current_power_profile = lambda: "power-saver"
        try:
            control = SERVER.render_control(conf)
            dashboard = SERVER.render_dashboard(conf)
        finally:
            SERVER.current_power_profile = original
        self.assertIn("🎛️ Styring", control)
        self.assertIn("Strømbesparelse", control)
        self.assertIn('id="restartWardenManual"', control)
        self.assertIn("Genstart Kiosk Warden", control)
        self.assertIn("Genstart maskine", control)
        self.assertNotIn("Hurtige handlinger", dashboard)

    def test_mqtt_exposes_power_profile_and_warden_restart(self):
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        control = (ROOT / "scripts" / "mqtt-control.sh").read_text()
        self.assertIn('select_entity power_profile', discovery)
        self.assertIn('button restart_warden', discovery)
        self.assertIn('listen_topic "$BASE_TOPIC/set_power_profile"', control)
        self.assertIn('restart_warden) restart_warden', control)

    def test_updater_uses_independent_webui_restart_timer(self):
        updater = (ROOT / "scripts" / "self-update.sh").read_text()
        self.assertIn("systemd-run --user --collect --on-active=2s", updater)
        self.assertNotIn("sleep 2 && systemctl --user restart kiosk-webui.service", updater)
        self.assertIn('er installeret og genstartet.', updater)
        self.assertIn('complete false', updater)


if __name__ == "__main__":
    unittest.main()
