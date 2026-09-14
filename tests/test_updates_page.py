import importlib.util
import http.client
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.parse
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
        self.assertIn("🎛️ Kiosk", control)
        self.assertIn("Strømbesparelse", control)
        self.assertIn('id="restartWardenManual"', control)
        self.assertIn("Genstart Kiosk Warden", control)
        self.assertIn("Genstart maskine", control)
        self.assertNotIn("Skærmbillede", control)
        self.assertNotIn("/screenshot.jpg", control)
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

    def test_navigation_is_structured_and_bilingual(self):
        conf = dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test")
        nav = SERVER.render_nav("/mqtt")
        expected = ["🏠 Status", "🎛️ Kiosk", "🖱️ Fjernstyring", "📡 Forbindelser", "⬇️ Opdateringer", "⚙️ System"]
        self.assertEqual(sorted(nav.index(label) for label in expected), [nav.index(label) for label in expected])

        connections_da = SERVER.render_mqtt(conf)
        system_da = SERVER.render_settings(conf)
        self.assertIn("Opsæt MQTT og den valgfrie forbindelse til Home Assistant.", connections_da)
        self.assertIn('action="/save-ha"', connections_da)
        self.assertNotIn('action="/save-ha"', system_da)
        self.assertIn("Tilpas identitet, lokale porte, skærm, login og strømfunktioner.", system_da)

        connections_en = SERVER.localize_html(connections_da, "en")
        system_en = SERVER.localize_html(system_da, "en")
        self.assertIn("📡 Connections", connections_en)
        self.assertIn("Configure MQTT and the optional Home Assistant connection.", connections_en)
        self.assertIn("Configure identity, local ports, display, login, and power features.", system_en)

    def test_profile_zoom_options_have_no_literal_separators(self):
        options = SERVER.render_zoom_options(100)
        self.assertNotIn("</option>'<option", options)
        self.assertIn('<option value="90">90%</option><option value="100" selected>100%</option>', options)

    def test_touch_guardian_reports_the_actual_unavailable_reason(self):
        self.assertEqual(SERVER.touch_guardian_label({"touch": {"guardian": True, "guardian_reason": "ready"}}), "Klar")
        self.assertEqual(SERVER.touch_guardian_label({"touch": {"guardian_reason": "permission_denied"}}), "Mangler adgang til touch-enheden")
        self.assertEqual(SERVER.touch_guardian_label({"touch": {"guardian_reason": "event_device_missing"}}), "Touch-enheden er frakoblet")
        probe = (ROOT / "scripts" / "capability-probe.py").read_text()
        for reason in ("touch_not_detected", "event_device_missing", "evtest_missing", "permission_denied", "ready"):
            self.assertIn(reason, probe)

    def test_primary_page_actions_are_translated_to_english(self):
        samples = {
            "Aktiv visning:": "Active view:",
            "Kiosktilstand og diagnostik": "Kiosk state and diagnostics",
            "Kør OFF→ON-test": "Run OFF→ON test",
            "Skærm og touch": "Display and touch",
            "Kontroller hardware igen": "Check hardware again",
            "Opdatér profil": "Update profile",
            "VNC er slukket. Tryk på Start VNC for at forbinde.": "VNC is off. Press Start VNC to connect.",
            "Alle tre lokale serviceporte konfliktkontrolleres før de gemmes.": "All three local service ports are checked for conflicts before saving.",
            "Skift administrator-login": "Change administrator login",
        }
        for danish, english in samples.items():
            self.assertEqual(SERVER.localize_html(danish, "en"), english)

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
        state = (ROOT / "scripts" / "warden-state.sh").read_text()
        backend = (ROOT / "scripts" / "screen-backend.sh").read_text()
        start = control.index("screen_on() {")
        end = control.index("\nscreen_off() {", start)
        screen_on = control[start:end]
        off_end = control.index("\ndock_onboard_bottom()", end)
        screen_off = control[end:off_end]
        self.assertIn('warden-state.sh" on', screen_on)
        self.assertIn('write_state WAKING', state)
        self.assertIn('verify_wake', state)
        self.assertIn('recover_staged', state)
        self.assertNotIn('CHROME_LIFECYCLE" frozen', screen_off)
        self.assertIn('warden-state.sh" off', screen_off)
        self.assertNotIn('xrandr --output "$output" --off', screen_off)
        self.assertNotIn('xrandr --output "$output" --off', backend)
        self.assertIn('xdotool getdisplaygeometry', state)
        self.assertLess(state.index('screen_prepare_on'), state.index('CHROME_LIFECYCLE" active'))
        lifecycle = (ROOT / "scripts" / "chrome-lifecycle.py").read_text()
        self.assertIn('"method": "Runtime.evaluate"', lifecycle)
        self.assertIn("kiosk-warden-power", lifecycle)
        self.assertNotIn("Page.setWebLifecycleState", lifecycle)
        self.assertIn('"active", "idle", "status"', lifecycle)
        self.assertIn('window.BeastPower.setState', lifecycle)
        self.assertIn("animationer, livekameraer og rendering virker kun", SERVER.render_control({"KIOSK_NAME": "Test kiosk"}))

    def test_health_check_does_not_capture_or_store_screenshots(self):
        health = (ROOT / "scripts" / "health-check.sh").read_text()
        self.assertNotIn("grey_surface()", health)
        self.assertNotIn("screenshot", health.lower())

    def test_mint_dpms_wake_order_keeps_dpms_enabled(self):
        control = (ROOT / "scripts" / "mqtt-control.sh").read_text()
        backend = (ROOT / "scripts" / "screen-backend.sh").read_text()
        startup = (ROOT / "scripts" / "start-kiosk.sh").read_text()
        on = control[control.index("screen_on() {"):control.index("\nscreen_off() {")]
        show = backend[backend.index("screen_show() {"):backend.index("\nscreen_hide() {")]
        self.assertIn('warden-state.sh" on', on)
        self.assertLess(show.index("xset +dpms"), show.index("xset dpms force on"))
        self.assertLess(show.index("xset dpms force on"), show.index("xset dpms 0 0 0"))
        self.assertNotIn("xset -dpms", on)
        self.assertIn("xset dpms 0 0 0", startup)

    def test_updater_uses_independent_webui_restart_timer(self):
        updater = (ROOT / "scripts" / "self-update.sh").read_text()
        self.assertIn("systemd-run --user --collect --on-active=2s", updater)
        self.assertNotIn("sleep 2 && systemctl --user restart kiosk-webui.service", updater)
        self.assertIn('er installeret og genstartet.', updater)
        self.assertIn('complete false', updater)
        self.assertIn("releases.atom", updater)
        self.assertIn("API returns 403", updater)
        self.assertIn("KIOSK_WARDEN_FORCE_TAG", updater)
        self.assertIn("ERROR invalid forced release tag", updater)
        verify = updater[updater.index("runtime_release_healthy()") : updater.index("install_release()")]
        self.assertNotIn("kiosk-self-test.sh", verify)
        self.assertIn("kiosk-webui.service", verify)
        self.assertNotIn("restore_snapshot", verify)
        self.assertIn("UPDATED_WITH_WARNING", verify)
        self.assertIn('RUNTIME_FAILURE="version"', verify)
        self.assertIn('RUNTIME_FAILURE="webui"', verify)

    def test_chrome_startup_has_platform_guard_and_recovery_grace(self):
        startup = (ROOT / "scripts" / "start-kiosk.sh").read_text()
        watchdog = (ROOT / "scripts" / "watchdog.sh").read_text()
        health = (ROOT / "scripts" / "health-check.sh").read_text()
        self.assertIn('XDG_CURRENT_DESKTOP', startup)
        self.assertIn('grep -q', startup)
        self.assertIn('timeout 3s systemctl --user kill', startup)
        self.assertIn('chrome_service_starting', watchdog)
        self.assertIn('45000000', watchdog)
        self.assertIn('chrome_service_starting', health)
        self.assertIn('Chrome is starting', health)
        self.assertIn('WAKING', health)

    def test_wake_verifies_renderer_without_screenshot_capture(self):
        lifecycle = (ROOT / "scripts" / "chrome-lifecycle.py").read_text()
        state = (ROOT / "scripts" / "warden-state.sh").read_text()
        self_test = (ROOT / "scripts" / "kiosk-self-test.sh").read_text()
        self.assertNotIn('Page.captureScreenshot', lifecycle)
        self.assertNotIn('verify_screenshot', state)
        self.assertNotIn('take-screenshot.sh', self_test)
        self.assertIn('wake_verification.json', state)
        self.assertIn('wake_verification.json', self_test)
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        updater = (ROOT / "scripts" / "self-update.sh").read_text()
        self.assertIn('publish_config image screenshot_image ""', discovery)
        self.assertIn('rm -f "$HOME/kiosk/take-screenshot.sh"', discovery)
        self.assertIn('rm -f "$KIOSK_DIR/take-screenshot.sh"', updater)

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

    def test_webui_port_can_be_changed_later_from_settings(self):
        conf = dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test")
        settings = SERVER.render_settings(conf)
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn('name="KIOSK_WEBUI_PORT"', settings)
        self.assertIn('min="1024" max="65535"', settings)
        self.assertIn('"KIOSK_WEBUI_PORT", "KIOSK_VNC_PORT", "KIOSK_NOVNC_PORT"', server)
        self.assertIn('systemd-run", "--user", "--collect", "--on-active=2s"', server)
        self.assertIn('if non_port_changed:', server)
        self.assertIn("location.replace(target)", SERVER.render_port_change(conf, 18081))
        self.assertIn(":18081/settings", SERVER.render_port_change(conf, 18081))

    def test_state_machine_recovery_self_test_and_safe_cleanup_are_shipped(self):
        state = (ROOT / "scripts" / "warden-state.sh").read_text()
        self_test = (ROOT / "scripts" / "kiosk-self-test.sh").read_text()
        cleanup = (ROOT / "scripts" / "cleanup-owned-browsers.sh").read_text()
        updater = (ROOT / "scripts" / "self-update.sh").read_text()
        for machine_state in ("OFF", "WAKING", "ON", "SLEEPING", "RECOVERING"):
            self.assertIn(machine_state, state)
        for step in ("resize", "resume", "reload", "restart"):
            self.assertIn(step, state)
        self.assertIn("dpms_off", self_test)
        self.assertIn("renderer_layout", self_test)
        self.assertIn("--user-data-dir=$PROFILE", cleanup)
        self.assertIn("is_descendant", cleanup)
        self.assertIn("verify_or_rollback", updater)
        self.assertIn("restore_snapshot", updater)
        self.assertIn("wait_verify_wake", state)
        self.assertIn("KIOSK_WAKE_VERIFY_TRIES:-8", state)

    def test_diagnostics_redacts_secrets_and_ports_are_configurable(self):
        diagnostics = (ROOT / "scripts" / "create-diagnostics.sh").read_text()
        port_check = (ROOT / "scripts" / "port-check.sh").read_text()
        vnc = (ROOT / "systemd" / "kiosk-vnc.service").read_text()
        novnc = (ROOT / "systemd" / "kiosk-novnc.service").read_text()
        self.assertIn("[REDACTED]", diagnostics)
        self.assertNotIn("kiosk.conf\" \"$work", diagnostics)
        self.assertIn("KIOSK_VNC_PORT", port_check)
        self.assertIn("KIOSK_NOVNC_PORT", port_check)
        self.assertIn("KIOSK_VNC_PORT", vnc)
        self.assertIn("KIOSK_NOVNC_PORT", novnc)

    def test_capabilities_gate_optional_hardware_entities(self):
        probe = (ROOT / "scripts" / "capability-probe.py").read_text()
        hardware = (ROOT / "scripts" / "hardware-control.py").read_text()
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        for capability in ("brightness", "illuminance", "battery", "microphone", "guardian"):
            self.assertIn(capability, probe)
        self.assertIn('brightness_backend', hardware)
        self.assertIn(".display.brightness // false", discovery)
        self.assertIn(".audio.microphone == true", discovery)
        self.assertIn(".sensors.illuminance == true", discovery)
        self.assertIn(".sensors.battery == true", discovery)

    def test_touch_guardian_consumes_wake_gesture_and_has_bounded_grab(self):
        guardian = (ROOT / "scripts" / "input-guardian.sh").read_text()
        service = (ROOT / "systemd" / "kiosk-input-guardian.service").read_text()
        self.assertIn("evtest --grab", guardian)
        self.assertIn("timeout 2s", guardian)
        self.assertIn("warden-state.sh\" on touch", guardian)
        self.assertIn("KIOSK_TOUCH_RELEASE_DELAY", guardian)
        self.assertIn("input-guardian.sh", service)

    def test_vnc_uses_the_webui_login_without_a_separate_password(self):
        service = (ROOT / "systemd" / "kiosk-vnc.service").read_text()
        sync_script = (ROOT / "scripts" / "sync-vnc-password.sh").read_text()
        conf = {"WEBUI_PASSWORD_HASH": "salt:abcdef1234567890"}
        vnc_page = SERVER.render_vnc(conf, active=True)
        vnc_off = SERVER.render_vnc(conf, active=False)
        self.assertIn("ExecStartPre=%h/kiosk/sync-vnc-password.sh", service)
        self.assertIn("x11vnc -storepasswd", sync_script)
        self.assertEqual("abcdef12", SERVER.vnc_password_from_conf(conf))
        self.assertIn("#password=", vnc_page)
        self.assertIn("VNC er aktiv og lukker automatisk", vnc_page)
        self.assertIn("Stop VNC", vnc_page)
        self.assertIn('action="/vnc/stop"', vnc_page)
        self.assertIn("Start VNC", vnc_off)
        self.assertIn('action="/vnc/start"', vnc_off)
        self.assertIn("/vnc/heartbeat", vnc_page)
        self.assertIn("/vnc/status", vnc_page)
        self.assertNotIn("sendBeacon", vnc_page)
        self.assertNotIn("beforeunload", vnc_page)
        self.assertNotIn("pagehide", vnc_page)
        self.assertIn("VNC er slukket", vnc_off)
        self.assertNotIn("#password=", vnc_off)
        installer = (ROOT / "install.sh").read_text()
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertNotIn("ask VNC_PASSWORD", installer)
        self.assertNotIn('parsed.path == "/vnc-password"', server)
        self.assertNotIn("def set_vnc_password", server)

    def test_vnc_stop_is_isolated_from_kiosk_and_screen_state(self):
        calls = []
        original_run = SERVER.run
        SERVER.run = lambda *args, **kwargs: calls.append(args)
        try:
            SERVER.stop_vnc_services()
        finally:
            SERVER.run = original_run
        self.assertEqual([
            ("systemctl", "--user", "stop", "kiosk-novnc.service", "kiosk-vnc.service"),
            ("systemctl", "--user", "reset-failed", "kiosk-novnc.service", "kiosk-vnc.service"),
        ], calls)
        source = (ROOT / "webui" / "server.py").read_text()
        stop_body = source[source.index("def stop_vnc_services") : source.index("def vnc_page_watchdog")]
        self.assertNotIn("warden-state", stop_body)
        self.assertNotIn("kiosk-chrome", stop_body)
        self.assertNotIn("screen", stop_body)
        self.assertIn("VNC_PAGE_IDLE_STOP = 5.0", source)
        start_body = source[source.index('if parsed.path == "/vnc/start"') : source.index('if parsed.path == "/vnc/stop"')]
        self.assertLess(start_body.index("mark_vnc_activity()"), start_body.index('run("systemctl"'))

    def test_touch_calibration_is_presented_as_a_readable_state(self):
        identity = "1.000000, 0.000000, 0.000000, 0.000000, 1.000000, 0.000000, 0.000000, 0.000000, 1.000000"
        custom = "0.000000, -1.000000, 1.000000, 1.000000, 0.000000, 0.000000, 0.000000, 0.000000, 1.000000"
        self.assertEqual("Standard", SERVER.calibration_label(identity))
        self.assertEqual("Tilpasset", SERVER.calibration_label(custom))
        self.assertEqual("Standard/ukendt", SERVER.calibration_label("not a matrix"))

    def test_login_submits_with_enter_and_vnc_has_start_action(self):
        login = SERVER.render_login({"KIOSK_NAME": "Test kiosk"})
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn("event.key === 'Enter'", login)
        self.assertIn("this.requestSubmit()", login)
        self.assertIn('parsed.path == "/vnc/start"', server)
        self.assertIn('"kiosk-vnc.service", "kiosk-novnc.service"', server)
        self.assertNotIn('warden-state.sh"), "on"', server)

    def test_profiles_offline_fallback_and_wayland_backends_are_shipped(self):
        profiles = (ROOT / "scripts" / "profile-manager.py").read_text()
        health = (ROOT / "scripts" / "health-check.sh").read_text()
        lifecycle = (ROOT / "scripts" / "chrome-lifecycle.py").read_text()
        backend = (ROOT / "scripts" / "screen-backend.sh").read_text()
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn("profiles.json", profiles)
        self.assertIn("active_profile", profiles)
        self.assertIn("fallback_active", health)
        self.assertLess(health.index('chrome_running" != "on"'), health.index('[[ -f "$FALLBACK_FILE" ]]'))
        self.assertIn('navigate_url', lifecycle)
        self.assertIn('parsed.path == "/offline"', server)
        self.assertIn("wayland-wlopm", backend)
        self.assertIn("wayland-kde", backend)

    def test_adaptive_brightness_is_opt_in_and_bounded(self):
        adaptive = (ROOT / "scripts" / "adaptive-brightness.sh").read_text()
        example = (ROOT / "kiosk.conf.example").read_text()
        self.assertIn('KIOSK_AUTO_BRIGHTNESS:-false', adaptive)
        self.assertIn('KIOSK_BRIGHTNESS_MIN', adaptive)
        self.assertIn('KIOSK_BRIGHTNESS_MAX', adaptive)
        self.assertIn('KIOSK_AUTO_BRIGHTNESS=false', example)

    def test_profile_manager_persists_valid_profiles_and_rejects_unsafe_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            kiosk = pathlib.Path(tmp) / "kiosk"
            kiosk.mkdir()
            script = ROOT / "scripts" / "profile-manager.py"
            (kiosk / "kiosk.conf").write_text('KIOSK_URL="http://example.test/default"\n')
            env = dict(os.environ, HOME=tmp)
            initial = subprocess.run([script, "list"], env=env, capture_output=True, text=True, check=True)
            self.assertEqual("Default", json.loads(initial.stdout)["profiles"][0]["name"])
            subprocess.run([script, "add", "Night", "http://example.test/night", "75"], env=env, check=True)
            profiles = json.loads(subprocess.run([script, "list"], env=env, capture_output=True, text=True, check=True).stdout)
            self.assertEqual(["Default", "Night"], [item["name"] for item in profiles["profiles"]])
            unsafe = subprocess.run([script, "add", "Bad", "javascript:alert(1)", "100"], env=env)
            self.assertEqual(2, unsafe.returncode)

    def test_profiles_support_cycle_and_daily_schedule_automation(self):
        manager = (ROOT / "scripts" / "profile-manager.py").read_text()
        scheduler = (ROOT / "scripts" / "profile-scheduler.py").read_text()
        service = (ROOT / "systemd" / "kiosk-profile-scheduler.service").read_text()
        control = SERVER.render_control(dict(SERVER.DEFAULTS, KIOSK_NAME="Test", KIOSK_ID="test"))
        self.assertIn('action="/profile-automation"', control)
        self.assertIn("Cycle mode", control)
        self.assertIn("Bestemte tidspunkter", control)
        self.assertIn('name="cycle_profile"', control)
        self.assertIn("Vælg mindst to profiler", control)
        self.assertIn("Automatic profile switching", SERVER.localize_html(control, "en"))
        self.assertIn('action=="automation"', manager)
        self.assertIn('"cycle_profiles"', manager)
        self.assertIn('action=="switch"', manager)
        self.assertIn('ZOOM_FILE=KIOSK/"page_zoom"', manager)
        self.assertIn('mode=="cycle"', scheduler)
        self.assertIn('automation.get("cycle_profiles",[])', scheduler)
        self.assertIn('mode=="schedule"', scheduler)
        self.assertIn("profile-manager.py\"),\"switch\"", scheduler)
        self.assertIn("profile-scheduler.py", service)
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        self.assertIn("enable --now kiosk-profile-scheduler.service", discovery)

    def test_mqtt_updates_the_active_kiosk_profile(self):
        control = (ROOT / "scripts" / "mqtt-control.sh").read_text()
        discovery = (ROOT / "scripts" / "mqtt-discovery.sh").read_text()
        manager = (ROOT / "scripts" / "profile-manager.py").read_text()
        lifecycle = (ROOT / "scripts" / "chrome-lifecycle.py").read_text()
        self.assertIn('"set-active-url"', manager)
        self.assertIn('"set-active-zoom"', manager)
        self.assertIn('set-active-url "$1"', control)
        self.assertIn('set-active-zoom "${1%%%}"', control)
        self.assertIn("Profile URL", discovery)
        self.assertIn("Profile Zoom", discovery)
        self.assertIn('const destination = {destination} || location.href;', lifecycle)

    def test_capability_probe_stdout_is_valid_and_non_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp)
            result = subprocess.run([ROOT / "scripts" / "capability-probe.py", "--stdout"], env=env, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            self.assertEqual(1, data["schema"])
            self.assertIn("platform", data)
            self.assertIn("display", data)
            self.assertFalse((pathlib.Path(tmp) / "kiosk" / "capabilities.json").exists())

    def test_webui_port_validation_rejects_invalid_and_occupied_ports(self):
        fields = {
            "KIOSK_ID": ["test"], "BASE_TOPIC": ["home/kiosk/test"],
            "MQTT_PORT": ["1883"], "STATS_INTERVAL": ["10"],
        }
        fields["KIOSK_WEBUI_PORT"] = ["80"]
        self.assertIn("1024", SERVER.validate_settings(fields))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            original_host = SERVER.BIND_HOST
            SERVER.BIND_HOST = "127.0.0.1"
            try:
                fields["KIOSK_WEBUI_PORT"] = [str(port)]
                self.assertIn("allerede i brug", SERVER.validate_settings(fields))
            finally:
                SERVER.BIND_HOST = original_host

    def test_system_save_does_not_require_fields_from_connections_page(self):
        fields = {
            "KIOSK_ID": ["test"], "BASE_TOPIC": ["home/kiosk/test"],
            "KIOSK_WEBUI_PORT": ["8080"], "KIOSK_VNC_PORT": ["5900"],
            "KIOSK_NOVNC_PORT": ["6080"], "KIOSK_SCREEN_BACKEND": ["auto"],
            "KIOSK_BRIGHTNESS_MIN": ["15"], "KIOSK_BRIGHTNESS_MAX": ["100"],
        }
        self.assertIsNone(SERVER.validate_settings(fields))
        self.assertNotIn('name="MQTT_PORT"', SERVER.render_settings(dict(SERVER.DEFAULTS)))

    def test_kiosk_url_is_owned_only_by_profiles(self):
        control = SERVER.render_control(dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test"))
        settings = SERVER.render_settings(dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test"))
        self.assertIn("Aktiv visning", control)
        self.assertNotIn('name="KIOSK_URL"', settings)
        self.assertNotIn("value=\"http://homeassistant.local:8123\" readonly", settings)
        fields = {
            "KIOSK_ID": ["test"], "BASE_TOPIC": ["home/kiosk/test"],
            "KIOSK_URL": ["http://example.test/ignored"],
            "MQTT_PORT": ["1883"], "STATS_INTERVAL": ["10"],
        }
        self.assertIsNone(SERVER.validate_settings(fields))

    def test_kiosk_id_and_base_topic_are_editable(self):
        settings = SERVER.render_settings(dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test"))
        self.assertIn('name="KIOSK_ID"', settings)
        self.assertIn('name="BASE_TOPIC"', settings)
        fields = {
            "KIOSK_ID": ["test"], "BASE_TOPIC": ["custom/kiosk"],
            "MQTT_PORT": ["1883"], "STATS_INTERVAL": ["10"],
        }
        self.assertIsNone(SERVER.validate_settings(fields))
        fields["BASE_TOPIC"] = ["bad topic"]
        self.assertIn("Base topic", SERVER.validate_settings(fields))

    def test_base_topic_save_keeps_custom_value(self):
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn('"BASE_TOPIC", "MQTT_HOST"', server)
        self.assertIn("if not conf.get(\"BASE_TOPIC\"):", server)

    def test_redirected_updates_page_resumes_progress_polling(self):
        page = SERVER.render_updates({"KIOSK_NAME": "Test kiosk"})
        self.assertIn("function ensureStatusPolling()", page)
        self.assertIn("if (!pollTimer) pollTimer = setInterval(pollStatus, 800);", page)
        self.assertIn("if (status.result === 'running') { ensureStatusPolling(); return; }", page)
        self.assertNotIn("pollTimer = setInterval(pollStatus, 800); setTimeout", page)

    def test_real_login_page_replaces_basic_auth_and_uses_session_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_dir, original_path = SERVER.KIOSK_DIR, SERVER.CONF_PATH
            SERVER.KIOSK_DIR = tmp
            SERVER.CONF_PATH = str(pathlib.Path(tmp) / "kiosk.conf")
            conf = dict(SERVER.DEFAULTS, WEBUI_USERNAME="warden", WEBUI_PASSWORD_HASH=SERVER.hash_password("correct-horse"))
            SERVER.write_conf(conf)
            SERVER._login_failures.clear()
            server = SERVER.ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request("GET", "/settings")
                response = conn.getresponse()
                self.assertEqual(303, response.status)
                self.assertTrue(response.getheader("Location").startswith("/login?"))
                self.assertIsNone(response.getheader("WWW-Authenticate"))
                response.read()

                body = urllib.parse.urlencode({"username": "warden", "password": "correct-horse", "next": "/settings"})
                conn.request("POST", "/login", body, {"Content-Type": "application/x-www-form-urlencoded"})
                response = conn.getresponse()
                self.assertEqual(303, response.status)
                cookie = response.getheader("Set-Cookie")
                self.assertIn("warden_session=", cookie)
                self.assertIn("HttpOnly", cookie)
                self.assertIn("SameSite=Strict", cookie)
                response.read()

                conn.request("GET", "/settings", headers={"Cookie": cookie.split(";", 1)[0]})
                response = conn.getresponse()
                self.assertEqual(200, response.status)
                self.assertEqual("nosniff", response.getheader("X-Content-Type-Options"))
                self.assertEqual("SAMEORIGIN", response.getheader("X-Frame-Options"))
                settings_html = response.read().decode()
                self.assertIn("Sign out", settings_html)
                csrf = __import__("re").search(r'<meta name="warden-csrf" content="([a-f0-9]+)">', settings_html).group(1)
                self.assertIn('name="csrf_token"', settings_html)

                session_cookie = cookie.split(";", 1)[0]
                conn.request("POST", "/vnc/heartbeat", "", {"Cookie": session_cookie})
                response = conn.getresponse()
                self.assertEqual(403, response.status)
                response.read()

                conn.request("POST", "/vnc/heartbeat", "", {"Cookie": session_cookie, "X-Warden-CSRF": csrf})
                response = conn.getresponse()
                self.assertEqual(200, response.status)
                response.read()
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                SERVER.KIOSK_DIR, SERVER.CONF_PATH = original_dir, original_path

    def test_connection_checks_and_post_security_are_shipped(self):
        connections = SERVER.render_mqtt(dict(SERVER.DEFAULTS, KIOSK_NAME="Test", KIOSK_ID="test"))
        source = (ROOT / "webui" / "server.py").read_text()
        self.assertIn('action="/test-mqtt"', connections)
        self.assertIn('action="/test-ha"', connections)
        self.assertIn('parsed.path == "/test-mqtt"', source)
        self.assertIn('parsed.path == "/test-ha"', source)
        self.assertIn("MAX_POST_BYTES", source)
        self.assertIn("Content-Security-Policy", source)

    def test_first_run_creates_username_and_password(self):
        page = SERVER.render_first_run()
        self.assertIn('name="username"', page)
        self.assertIn('autocomplete="new-password"', page)
        self.assertIn("Opret login", page)

    def test_login_remember_and_auto_logout_are_configurable(self):
        login = SERVER.render_login({"KIOSK_NAME": "Test kiosk"})
        settings = SERVER.render_settings(dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk"))
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn('name="remember"', login)
        self.assertIn('name="remember" value="true" checked', login)
        self.assertIn('name="WEBUI_AUTO_LOGOUT"', settings)
        self.assertIn("REMEMBER_TTL", server)
        self.assertIn('conf["WEBUI_AUTO_LOGOUT"]', server)

    def test_signed_login_survives_webui_restart_and_password_change_revokes_it(self):
        conf = dict(SERVER.DEFAULTS, WEBUI_PASSWORD_HASH=SERVER.hash_password("correct-horse"))
        token = SERVER.create_session(conf, SERVER.REMEMBER_TTL)
        self.assertTrue(SERVER.valid_session(token, conf))
        # Validation uses only the signed cookie and persisted password hash,
        # so there is no process-local session table to lose on restart.
        self.assertNotIn("_sessions", SERVER.__dict__)
        changed = dict(conf, WEBUI_PASSWORD_HASH=SERVER.hash_password("new-password"))
        self.assertFalse(SERVER.valid_session(token, changed))
        self.assertFalse(SERVER.valid_session(token + "tampered", conf))

    def test_mqtt_has_a_dedicated_page(self):
        conf = dict(SERVER.DEFAULTS, KIOSK_NAME="Test kiosk", KIOSK_ID="test")
        settings = SERVER.render_settings(conf)
        mqtt = SERVER.render_mqtt(conf)
        nav = SERVER.render_nav("/mqtt")
        server = (ROOT / "webui" / "server.py").read_text()
        self.assertIn('href="/mqtt"', nav)
        self.assertIn("/mqtt", mqtt)
        self.assertIn('name="MQTT_HOST"', mqtt)
        self.assertIn('name="MQTT_PORT"', mqtt)
        self.assertIn('name="MQTT_USER"', mqtt)
        self.assertIn('name="MQTT_PASS"', mqtt)
        self.assertIn('name="STATS_INTERVAL"', mqtt)
        self.assertIn('action="/save-mqtt"', mqtt)
        self.assertNotIn('name="MQTT_HOST"', settings)
        self.assertNotIn('name="MQTT_PORT"', settings)
        self.assertIn('parsed.path == "/mqtt"', server)
        self.assertIn('parsed.path == "/save-mqtt"', server)

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
