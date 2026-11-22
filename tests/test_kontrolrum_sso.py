"""Sign-in from Kontrolrum: the handshake, the session binding and the command line."""
import hashlib
import hmac
import http.client
import importlib.util
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webui"))
SPEC = importlib.util.spec_from_file_location("warden_server_sso", ROOT / "webui" / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)

# Linux answers on all of 127/8, so a second source address is a real other peer.
KONTROLRUM_IP = "127.0.0.1"
OTHER_IP = "127.0.0.2"


def assertion(key, sub="kontrolrum", aud="kioskwarden", iat=None, lifetime=60, nonce=None, v=1):
    iat = int(time.time()) if iat is None else iat
    a = {"v": v, "aud": aud, "sub": sub, "iat": iat, "exp": iat + lifetime, "nonce": nonce or secrets.token_hex(16)}
    text = "\n".join(["kontrolrum-sso", str(a["v"]), a["aud"], a["sub"], str(a["iat"]), str(a["exp"]), a["nonce"]])
    a["sig"] = hmac.new(key.encode(), text.encode(), hashlib.sha256).hexdigest()
    return a


class KontrolrumSsoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.files = pathlib.Path(tmp.name)
        self.saved = (SERVER.CONF_PATH, SERVER.KIOSK_DIR, SERVER.SSO)
        self.addCleanup(self.restore)
        SERVER.KIOSK_DIR = str(self.files)
        SERVER.CONF_PATH = str(self.files / "kiosk.conf")
        conf = dict(SERVER.DEFAULTS)
        conf.update(WEBUI_USERNAME="kontrolrum", WEBUI_PASSWORD_HASH=SERVER.hash_password("long-test-password"), UI_LANGUAGE="da")
        with open(SERVER.CONF_PATH, "w", encoding="utf-8") as handle:
            for field, value in conf.items():
                handle.write(f'{field}="{value}"\n')
        self.sso = SERVER.kontrolrum_sso.KontrolrumSso(self.files / "kontrolrum-sso.json", "kioskwarden")
        SERVER.SSO = self.sso
        self.key = self.sso.create_key("test")
        self.sso.set_peers([KONTROLRUM_IP])
        self.sso.set_user("kontrolrum", True)
        self.httpd = SERVER.ThreadingHTTPServer(("127.0.0.1", 0), SERVER.Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def restore(self):
        SERVER.CONF_PATH, SERVER.KIOSK_DIR, SERVER.SSO = self.saved

    def call(self, method, path, body=None, cookie="", source=KONTROLRUM_IP, form=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10, source_address=(source, 0))
        try:
            headers = {"Cookie": cookie} if cookie else {}
            data = None
            if form is not None:
                data = urllib.parse.urlencode(form).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            elif body is not None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            reply = conn.getresponse()
            raw = reply.read().decode("utf-8", "replace")
            return reply.status, raw, reply.getheader("Set-Cookie") or "", reply.getheader("Location") or ""
        finally:
            conn.close()

    def login(self, a=None, source=KONTROLRUM_IP):
        status, raw, cookie, _ = self.call("POST", "/login/kontrolrum", assertion(self.key) if a is None else a, source=source)
        try:
            return status, json.loads(raw), cookie
        except ValueError:
            return status, {}, cookie

    def cookie(self):
        status, body, header = self.login()
        self.assertEqual(status, 200, body)
        return header.split(";", 1)[0]

    def logged_in(self, cookie, source=KONTROLRUM_IP):
        return self.call("GET", "/settings", cookie=cookie, source=source)[0] == 200

    def error(self, a):
        status, body, _ = self.login(a)
        return status, body.get("error")

    def test_valid_login_gives_a_working_session_with_a_csrf_token(self):
        cookie = self.cookie()
        status, page, _, _ = self.call("GET", "/", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertRegex(page, r'<meta name="warden-csrf" content="[0-9a-f]{64}"')
        self.assertEqual(self.sso.status()["last_used"]["user"], "kontrolrum")

    def test_bad_signature(self):
        a = assertion(self.key)
        a["sig"] = "0" * 64
        self.assertEqual(self.error(a), (401, "bad_signature"))

    def test_wrong_audience(self):
        self.assertEqual(self.error(assertion(self.key, aud="dantherm")), (401, "bad_audience"))

    def test_expired(self):
        self.assertEqual(self.error(assertion(self.key, iat=int(time.time()) - 600)), (401, "expired"))

    def test_from_the_future(self):
        self.assertEqual(self.error(assertion(self.key, iat=int(time.time()) + 600)), (401, "expired"))

    def test_too_long_lifetime(self):
        self.assertEqual(self.error(assertion(self.key, lifetime=121)), (401, "expired"))

    def test_replay_is_refused_also_after_a_restart(self):
        a = assertion(self.key)
        self.assertEqual(self.login(a)[0], 200)
        self.assertEqual(self.error(a), (401, "replay"))
        SERVER.SSO = SERVER.kontrolrum_sso.KontrolrumSso(self.files / "kontrolrum-sso.json", "kioskwarden")
        self.assertEqual(self.error(a), (401, "replay"))

    def test_disabled(self):
        self.sso.disable()
        self.assertEqual(self.error(assertion(self.key)), (403, "sso_disabled"))

    def test_user_not_opted_in(self):
        self.sso.set_user("kontrolrum", False)
        self.assertEqual(self.error(assertion(self.key)), (401, "unknown_user"))

    def test_another_user_name_is_refused_even_when_ticked(self):
        self.sso.set_user("anna", True)
        self.assertEqual(self.error(assertion(self.key, sub="anna")), (401, "unknown_user"))

    def test_wrong_source_ip_is_404_and_shows_the_address(self):
        self.assertEqual(self.login(source=OTHER_IP)[0], 404)
        info = self.sso.status()
        self.assertEqual((info["rejected_ip"], info["rejected_reason"]), (OTHER_IP, "wrong_peer"))

    def test_copied_cookie_does_not_work_from_another_address(self):
        cookie = self.cookie()
        self.sso.set_peers([KONTROLRUM_IP, OTHER_IP])
        self.assertFalse(self.logged_in(cookie, OTHER_IP))
        self.assertTrue(self.logged_in(cookie))

    def test_new_key_off_and_removed_tick_end_the_session(self):
        for end in (lambda: self.sso.create_key("test"), self.sso.disable,
                    lambda: self.sso.set_user("kontrolrum", False)):
            self.key = self.sso.key() or self.sso.create_key("test")
            self.sso.set_user("kontrolrum", True)
            cookie = self.cookie()
            self.assertTrue(self.logged_in(cookie))
            end()
            self.assertFalse(self.logged_in(cookie))

    def test_a_tampered_session_is_refused(self):
        cookie = self.cookie()
        name, token = cookie.split("=", 1)
        encoded, signature = token.split(".", 1)
        self.assertFalse(self.logged_in(f"{name}={encoded[:-2]}xx.{signature}"))
        forged = ("A" if signature[0] != "A" else "B") + signature[1:]
        self.assertFalse(self.logged_in(f"{name}={encoded}.{forged}"), "right content, wrong signature")

    def test_the_session_is_not_an_ordinary_session(self):
        token = self.cookie().split("=", 1)[1]
        conf = SERVER.read_conf()
        self.assertFalse(SERVER.valid_session(token, conf), "no address: refused")
        self.assertTrue(SERVER.valid_session(token, conf, KONTROLRUM_IP))

    def test_ordinary_password_login_still_works(self):
        status, _, cookie, _ = self.call("POST", "/login", form={"username": "kontrolrum", "password": "long-test-password"})
        self.assertEqual(status, 303)
        self.assertTrue(self.logged_in(cookie.split(";", 1)[0], OTHER_IP))

    def test_rate_limit(self):
        for _ in range(SERVER.kontrolrum_sso.RATE_LIMIT):
            self.assertEqual(self.login(assertion("b" * 64))[0], 401)
        self.assertEqual(self.error(assertion(self.key)), (429, "rate_limited"))

    def test_rubbish_is_a_clean_refusal(self):
        for body in (b"{", b"[1]", b"\xff\xfe", b"x" * 5000):
            self.sso._hits.clear()
            self.assertEqual(self.login(body)[0], 400, body[:20])

    def test_a_fault_in_the_sign_in_code_only_refuses_this_request(self):
        def broken(*args):
            raise RuntimeError("boom")
        self.sso.login = broken
        self.assertEqual(self.error(assertion(self.key)), (503, "unavailable"))

    def test_without_the_module_the_endpoint_is_404(self):
        SERVER.SSO = None
        self.assertEqual(self.login()[0], 404)

    def test_settings_card_needs_a_login_and_never_shows_the_key(self):
        status, _, _, location = self.call("POST", "/kontrolrum/key", form={})
        self.assertEqual(status, 303)
        self.assertIn("/login", location)
        _, _, header, _ = self.call("POST", "/login", form={"username": "kontrolrum", "password": "long-test-password"})
        cookie = header.split(";", 1)[0]
        page = self.call("GET", "/settings", cookie=cookie)[1]
        self.assertIn("Login fra Kontrolrum", page)
        self.assertNotIn(self.key, page)
        self.assertEqual(self.call("POST", "/kontrolrum/key", form={}, cookie=cookie)[0], 403, "no CSRF token")
        csrf = re.search(r'name="warden-csrf" content="([^"]+)"', page).group(1)
        reply = self.call("POST", "/kontrolrum/key", form={"csrf_token": csrf}, cookie=cookie)
        self.assertEqual(reply[0], 200)
        self.assertNotEqual(self.sso.key(), self.key)
        self.assertIn(self.sso.key(), reply[1], "the new key is shown once")

    def test_the_files_are_private(self):
        self.login()
        for name in ("kontrolrum-sso.json", "kontrolrum-sso-nonces.json", "kontrolrum-sso-status.json"):
            self.assertEqual((self.files / name).stat().st_mode & 0o777, 0o600, name)


class CommandLineTests(unittest.TestCase):
    def run_cli(self, home, *args):
        return subprocess.run([sys.executable, str(ROOT / "webui/kontrolrum_sso.py"), *args], capture_output=True,
                              text=True, env=dict(os.environ, HOME=str(home)), timeout=30, check=False)

    def home(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        kiosk = pathlib.Path(tmp.name) / "kiosk"
        kiosk.mkdir()
        (kiosk / "kiosk.conf").write_text('WEBUI_USERNAME="kontrolrum"\n')
        return pathlib.Path(tmp.name)

    def test_pairing_prints_only_the_key_and_ticks_the_user(self):
        home = self.home()
        done = self.run_cli(home, "kontrolrum-sso", "kontrolrum", "--peer", "192.168.1.28")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"\A[0-9a-f]{64}\Z")
        self.assertNotIn(done.stdout, done.stderr)
        sso = SERVER.kontrolrum_sso.KontrolrumSso(home / "kiosk/kontrolrum-sso.json", "kioskwarden")
        self.assertEqual((sso.key(), sso.users(), sso.peers()), (done.stdout, ["kontrolrum"], ["192.168.1.28"]))
        status = self.run_cli(home, "status")
        self.assertNotIn(done.stdout, status.stdout + status.stderr)

    def test_unknown_user_makes_no_key(self):
        home = self.home()
        done = self.run_cli(home, "kontrolrum-sso", "nobody")
        self.assertEqual((done.returncode, done.stdout), (1, ""))
        self.assertFalse((home / "kiosk/kontrolrum-sso.json").exists())


if __name__ == "__main__":
    unittest.main()
