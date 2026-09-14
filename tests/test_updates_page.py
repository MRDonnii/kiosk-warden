import importlib.util
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webui"))
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
        self.assertIn("Skærmbillede", control)
        self.assertIn("/screenshot.jpg", control)
        self.assertNotIn("Hurtige handlinger", dashboard)
        self.assertNotIn("/screenshot.jpg", dashboard)
        self.assertIn('id="usageChart"', dashboard)
        self.assertIn('id="temperatureChart"', dashboard)
        self.assertIn('id="frequencyChart"', dashboard)
        self.assertIn('id="networkChart"', dashboard)
        self.assertIn("/api/telemetry", dashboard)
        self.assertIn("Smartdash-forbindelse", control)
        self.assertIn("refreshSmartdash", control)
        self.assertIn("animationer, livekameraer og rendering virker kun", control)

    def test_mqtt_exposes_power_profile_and_warden_restart(self):
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        control = (ROOT / "scripts" / "mqtt-control.sh").read_text()
        self.assertIn('select_entity power_profile', discovery)
        self.assertIn('button restart_warden', discovery)
        self.assertIn('listen_topic "$BASE_TOPIC/set_power_profile"', control)
        self.assertIn('smartdash_connection_entity', discovery)
        self.assertIn('smartdash_rendering_switch', discovery)
        self.assertIn('$BASE_TOPIC/set_smartdash_rendering', discovery)
        self.assertIn('listen_topic "$BASE_TOPIC/set_smartdash_rendering" set_smartdash_rendering', control)
        self.assertIn('mqtt_pub "$BASE_TOPIC/smartdash/status" "$payload" -r', control)
        self.assertIn('mqtt_pub "$BASE_TOPIC/smartdash/availability" "online" -r', control)
        self.assertIn('smartdash_status_loop &', control)
        self.assertIn('restart_warden) restart_warden', control)

    def test_vnc_services_stop_cleanly_during_warden_restart(self):
        vnc = (ROOT / "systemd" / "kiosk-vnc.service").read_text()
        novnc = (ROOT / "systemd" / "kiosk-novnc.service").read_text()
        self.assertIn("SuccessExitStatus=2", vnc)
        self.assertIn("SuccessExitStatus=143", novnc)

    def test_installer_supports_arm_and_raspberry_pi_os(self):
        installer = (ROOT / "install.sh").read_text()
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        vnc = (ROOT / "systemd" / "kiosk-vnc.service").read_text()
        self.assertIn('ARCH="$(dpkg --print-architecture)"', installer)
        self.assertIn('raspi-config nonint do_wayland W1', installer)
        self.assertIn('sudo apt-get install -y chromium', installer)
        self.assertIn('required_packages=', installer)
        self.assertIn('power-profiles-daemon', installer)
        self.assertIn('-auth guess', vnc)
        self.assertIn('/proc/device-tree/model', discovery)

    def test_english_is_default_and_danish_is_selectable(self):
        conf = dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test")
        settings = SERVER.localize_html(SERVER.render_settings(conf), "en")
        control = SERVER.localize_html(SERVER.render_control(conf), "en")
        self.assertEqual("en", SERVER.DEFAULTS["UI_LANGUAGE"])
        self.assertIn("Interface language", settings)
        self.assertIn('value="da"', settings)
        self.assertIn("Power profile", control)
        self.assertIn("Restart Kiosk Warden", control)
        self.assertNotIn("Strømprofil", control)
        self.assertIn('lang="da"', SERVER.localize_html(settings, "da"))

    def test_screen_wake_is_idempotent_and_screen_off_does_not_freeze(self):
        control = (ROOT / "scripts" / "mqtt-control.sh").read_text()
        start = control.index("screen_on() {")
        end = control.index("\nscreen_off() {", start)
        screen_on = control[start:end]
        off_end = control.index("\ndock_onboard_bottom()", end)
        screen_off = control[end:off_end]
        self.assertIn('CHROME_LIFECYCLE" active', screen_on)
        self.assertIn('startswith("http")', screen_on)
        self.assertIn("return 0", screen_on)
        self.assertIn("restart_kiosk", screen_on)
        self.assertNotIn('CHROME_LIFECYCLE" frozen', screen_off)
        self.assertIn('CHROME_LIFECYCLE" idle', screen_off)
        self.assertNotIn('xrandr --output "$output" --off', screen_off)
        self.assertIn('xdotool getdisplaygeometry', screen_on)
        self.assertLess(screen_on.index('xrandr --output "$output" --auto'), screen_on.index('CHROME_LIFECYCLE" active'))
        lifecycle = (ROOT / "scripts" / "chrome-lifecycle.py").read_text()
        self.assertIn('"method": "Runtime.evaluate"', lifecycle)
        self.assertIn("kiosk-warden-power", lifecycle)
        self.assertNotIn("Page.setWebLifecycleState", lifecycle)
        self.assertIn('"active", "idle", "status"', lifecycle)
        self.assertIn('window.BeastPower.setState', lifecycle)
        self.assertIn("animationer, livekameraer og rendering virker kun", SERVER.render_control({"KIOSK_NAME": "Test kiosk"}))

    def test_health_check_recovers_a_solid_grey_surface(self):
        health = (ROOT / "scripts" / "health-check.sh").read_text()
        self.assertIn("grey_surface()", health)
        self.assertIn("colors <= 8", health)
        self.assertIn("Blank or solid-grey Chrome surface", health)
        self.assertIn('screen_state', health)
        self.assertLess(health.index('command -v import'), health.index('command -v gnome-screenshot'))
        self.assertNotIn("trap 'rm -f", health)
        self.assertIn('local shot colors result=1', health)

    def test_mint_dpms_wake_order_keeps_dpms_enabled(self):
        control = (ROOT / "scripts" / "mqtt-control.sh").read_text()
        startup = (ROOT / "scripts" / "start-kiosk.sh").read_text()
        on = control[control.index("screen_on() {"):control.index("\nscreen_off() {")]
        self.assertLess(on.index("xset +dpms"), on.index("xset dpms force on"))
        self.assertLess(on.index("xset dpms force on"), on.index("xset dpms 0 0 0"))
        self.assertNotIn("xset -dpms", on)
        self.assertIn("xset dpms 0 0 0", startup)

    def test_updater_uses_independent_webui_restart_timer(self):
        updater = (ROOT / "scripts" / "self-update.sh").read_text()
        self.assertIn("systemd-run --user --collect --on-active=2s", updater)
        self.assertNotIn("sleep 2 && systemctl --user restart kiosk-webui.service", updater)
        self.assertIn('er installeret og genstartet.', updater)
        self.assertIn('complete false', updater)

    def test_installer_supports_a_conflict_checked_webui_port(self):
        installer = (ROOT / "install.sh").read_text()
        service = (ROOT / "systemd" / "kiosk-webui.service").read_text()
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn("select_webui_port", installer)
        self.assertIn("webui_port_in_use", installer)
        self.assertIn('existing_webui_port=', installer)
        self.assertIn("KIOSK_WEBUI_PORT=$KIOSK_WEBUI_PORT", installer)
        self.assertIn('ufw allow "$KIOSK_WEBUI_PORT/tcp"', installer)
        self.assertIn("http://localhost:$KIOSK_WEBUI_PORT", installer)
        self.assertIn("EnvironmentFile=-%h/kiosk/kiosk.conf", service)
        self.assertIn('"KIOSK_WEBUI_PORT": "8080"', server)

    def test_redirected_updates_page_resumes_progress_polling(self):
        page = SERVER.render_updates({"KIOSK_NAME": "Test kiosk"})
        self.assertIn("function ensureStatusPolling()", page)
        self.assertIn("if (!pollTimer) pollTimer = setInterval(pollStatus, 800);", page)
        self.assertIn("if (status.result === 'running') { ensureStatusPolling(); return; }", page)
        self.assertNotIn("pollTimer = setInterval(pollStatus, 800); setTimeout", page)

    def test_stale_release_metadata_never_offers_a_downgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "version").write_text("1.12.5\n")
            (root / "update_channel").write_text("stable\n")
            (root / "CHANGELOG.md").write_text("# Changelog\n")
            SERVER.KIOSK_DIR = str(root)
            SERVER.VERSION_PATH = str(root / "version")
            SERVER.UPDATE_CHANNEL_PATH = str(root / "update_channel")
            SERVER.CHANGELOG_PATH = str(root / "CHANGELOG.md")
            SERVER._update_cache["latest"] = {"latest_version": "1.12.2"}
            page = SERVER.render_updates({"KIOSK_NAME": "Test kiosk"})
            self.assertFalse(SERVER.version_newer("1.12.2", "1.12.5"))
            self.assertTrue(SERVER.version_newer("1.12.6", "1.12.5"))
            self.assertIn('id="installUpdate" disabled', page)
            self.assertNotIn("Ny version klar", page)
            self.assertIn("button:disabled", page)

    def test_completed_status_from_an_old_version_is_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "version").write_text("1.12.7\n")
            (root / "update_status.json").write_text(
                '{"stage":"complete","percent":100,"message":"Kiosk Warden 1.12.0 er installeret og genstartet.","result":"complete"}'
            )
            SERVER.VERSION_PATH = str(root / "version")
            SERVER.UPDATE_STATUS_PATH = str(root / "update_status.json")
            self.assertEqual("idle", SERVER.update_status()["result"])


if __name__ == "__main__":
    unittest.main()
