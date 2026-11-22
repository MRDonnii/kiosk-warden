import importlib.util
import pathlib
import re
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webui"))
SPEC = importlib.util.spec_from_file_location("warden_server_collapse", ROOT / "webui" / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)
ASSETS = SERVER.ui_assets


def _side(nav_html):
    start = nav_html.index('<nav class="fd-navbar"')
    return nav_html[start:nav_html.index("</nav>", start) + len("</nav>")]


class CollapsibleSideMenuTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        (root / "version").write_text("1.26.0\n")
        self._saved = (SERVER.KIOSK_DIR, SERVER.VERSION_PATH, dict(SERVER._update_cache))
        SERVER.KIOSK_DIR = str(root)
        SERVER.VERSION_PATH = str(root / "version")
        SERVER._update_cache["latest"] = {"latest_version": "1.27.0", "release_url": "", "release_summary": "", "prerelease": False}

    def tearDown(self):
        SERVER.KIOSK_DIR, SERVER.VERSION_PATH, cache = self._saved
        SERVER._update_cache.clear()
        SERVER._update_cache.update(cache)
        self.tmp.cleanup()

    def render(self, active="/control"):
        return SERVER.render_nav(active, {"KIOSK_NAME": "Test", "WEBUI_USERNAME": "admin"})

    def test_head_script_applies_saved_state_before_first_paint(self):
        head = SERVER.PAGE_HEAD.format(title_suffix="")
        script = head[head.index("<script>"):head.index("</script>")]
        self.assertIn("kioskwarden.nav.collapsed", script)
        self.assertIn("classList.add('nav-collapsed')", script)
        # Inline and before the stylesheet, so the rail is drawn right on the first paint.
        self.assertLess(head.index("kioskwarden.nav.collapsed"), head.index('rel="stylesheet"'))

    def test_toggle_button_sits_at_the_bottom_of_the_side_menu(self):
        side = _side(self.render())
        self.assertIn('id="fdSideNav"', side)
        button = re.search(r"<button[^>]*data-nav-collapse[^>]*>", side).group(0)
        self.assertIn('aria-expanded="true"', button)
        self.assertIn('aria-controls="fdSideNav"', button)
        self.assertIn('aria-label="Klap menuen sammen"', button)
        self.assertIn('data-tip-closed="Fold menuen ud"', button)
        self.assertIn('type="button"', button)
        # After the menu entries, above the version footer.
        self.assertGreater(side.index("data-nav-collapse"), side.index('href="/settings"'))
        self.assertLess(side.index("data-nav-collapse"), side.index('class="fd-foot"'))
        self.assertIn(">Klap menuen sammen</span>", side)

    def test_every_side_entry_has_a_name_for_the_icon_rail(self):
        side = _side(self.render())
        links = re.findall(r'<a class="fd-nav"[^>]*>', side)
        self.assertEqual(len(links), len(SERVER._nav_items()))
        for link in links:
            self.assertRegex(link, r'aria-label="[^"]+"')
            self.assertRegex(link, r'data-tip="[^"]+"')
        self.assertIn('aria-label="Opdateringer, 1 ny opdatering"', side)
        self.assertIn('aria-current="page"', re.search(r'<a class="fd-nav" href="/control"[^>]*>', side).group(0))
        # The logo keeps its name too, and the group label can be hidden on its own.
        self.assertIn('data-tip="Kiosk Warden"', side)
        self.assertIn('<div class="fd-group"><span>Opsætning</span></div>', side)
        # The count stays inside the entry so it can become a dot/number on the icon.
        self.assertRegex(side, r'href="/updates"[^>]*>.*?<span class="fd-count">1</span></a>')

    def test_mobile_sheet_and_tab_bar_are_unchanged(self):
        nav = self.render()
        sheet = nav[nav.index('<div class="fd-sheet">'):nav.index('<nav class="fd-tabbar"')]
        self.assertNotIn("data-tip", sheet)
        self.assertNotIn("data-nav-collapse", sheet)
        self.assertNotIn("data-nav-collapse", nav[nav.index('<nav class="fd-tabbar"'):])

    def test_css_rail_is_desktop_only_with_short_motion(self):
        css = ASSETS.APP_CSS
        block = css[css.index("Sammenklappelig sidemenu"):]
        desktop = block[block.index("@media (min-width: 48.0625em)"):block.index("@media (max-width: 48em)")]
        self.assertIn(".nav-collapsed[data-nav='side'] .fd-navbar { width: 64px;", desktop)
        self.assertIn(".nav-collapsed[data-nav='side'] .fd-main { padding-left: 84px; }", desktop)
        self.assertIn(".fd-group > span", desktop)
        self.assertIn(".fd-brand > span:not(.fd-logo) { display: none; }", desktop)
        self.assertIn("position: absolute", desktop[desktop.index(".fd-count"):])
        self.assertRegex(desktop, r"transition: width \.18s")
        self.assertIn("@media (prefers-reduced-motion: reduce)", block)
        self.assertIn("transition: none", block[block.index("prefers-reduced-motion"):])
        self.assertIn("@media (max-width: 48em) { .fd-collapse { display: none !important; } }", block)
        # Every collapsed rule is scoped to the desktop media query, so mobile is untouched.
        outside = block.replace(desktop, "")
        self.assertNotIn(".nav-collapsed", outside.split("*/", 1)[1])

    def test_js_toggle_shortcut_and_storage(self):
        js = ASSETS.APP_JS
        self.assertIn("'kioskwarden.nav.collapsed'", js)
        self.assertIn("event.ctrlKey || event.metaKey", js)
        self.assertIn("toLowerCase() !== 'b'", js)
        self.assertIn("/^(INPUT|TEXTAREA|SELECT)$/", js)
        self.assertIn("isContentEditable", js)
        self.assertIn("setAttribute('aria-expanded'", js)
        self.assertIn("data-tip-closed", js)

    def test_icon_and_english_labels_exist(self):
        self.assertIn("chevron-left", ASSETS.ICONS)
        english = SERVER.localize_html(_side(self.render()), "en")
        self.assertIn('aria-label="Collapse menu"', english)
        self.assertIn('data-tip-closed="Expand menu"', english)
        self.assertIn('aria-label="Updates, 1 new update"', english)

    def test_csp_is_unchanged(self):
        source = (ROOT / "webui" / "server.py").read_text()
        self.assertIn(
            "\"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; frame-src http: https:; connect-src 'self'\"",
            source,
        )


if __name__ == "__main__":
    unittest.main()
