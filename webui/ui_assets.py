"""Kiosk Warden WebUI assets: Fleetdeck design system (CSS), UI script and icons.

The CSS is Fleetdeck's components 1:1 (fd-release/web: design/fleetdeck.css, design/skin.tsx,
mobile.css and Mantine 9.8 variables), shared with the other apps as fd-shared.css, followed by
the Kiosk Warden specific rules. Icons are Tabler Icons (MIT), the same set as Fleetdeck.
Inter Variable (latin subset, SIL OFL 1.1) is embedded so nothing is fetched from the internet.
"""
import base64

APP_CSS = r"""/* Fælles designsystem for Spamfilter, Kiosk Warden og Dantherm – Fleetdecks komponenter 1:1 i ren CSS.
   Kilder (fd-release/web):
   - src/design/fleetdeck.css   flader (--fd-*), sidemenu, nøgletal, flådekort, topmenu, fanebjælke
   - src/design/skin.tsx        tema: primærfarve fleet/indigo, primaryShade {light 6, dark 5}, radius, Inter,
                                Paper/Card withBorder, Button radius (command sm / aurora md), Badge radius sm
   - src/mobile.css             mobilregler (tabeller som kort, 36 px knapper, 16 px inputs)
   - node_modules/@mantine/core 9.8 styles/*.css + defaultCssVariablesResolver (udregnet med scripts/mantine-vars.js):
                                Button, Badge, Paper, Alert, SegmentedControl, Tabs, Table, Input, Switch, Checkbox,
                                Menu, ActionIcon, ThemeIcon, Kbd og farvevariablerne for lyst/mørkt tema.
   Ingen farvede venstrekanter: Fleetdeck har ingen. */
@font-face { font-family: "Inter Variable"; font-weight: 100 900; font-display: swap; src: url(/static/inter.woff2) format("woff2"); }

/* ---------- Tokens ---------- */
:root {
  --font: "Inter Variable", Inter, "Segoe UI Variable", "Segoe UI", system-ui, -apple-system, sans-serif;
  --mono: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
  /* fleetdeck.css */
  --fd-logo-a: #3b82f6; --fd-logo-b: #1d4ed8;
  --fd-ok: #16a34a; --fd-warn: #d97706; --fd-bad: #dc2626; --fd-off: #a1a1aa;
  /* skin.tsx: command-radius og Mantine-skyggen xs */
  --r-xs: 4px; --r-sm: 6px; --r-md: 8px; --r-lg: 12px; --r-xl: 16px;
  --r-default: var(--r-md); --r-btn: var(--r-sm); --r-badge: var(--r-sm);
  --shadow-xs: 0 1px 3px rgba(0,0,0,.05), 0 1px 2px rgba(0,0,0,.1);
  --shadow-md: 0 1px 3px rgba(0,0,0,.05), rgba(0,0,0,.05) 0 20px 25px -5px, rgba(0,0,0,.04) 0 10px 10px -5px;
}
[data-skin='aurora'] { --fd-logo-a: #22d3ee; --fd-logo-b: #6366f1;
  --r-xs: 6px; --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-xl: 22px; --r-default: var(--r-lg); --r-btn: var(--r-md); }

/* Mantine, lyst tema (defaultCssVariablesResolver) */
[data-theme='light'] { color-scheme: light;
  --text: #000; --bright: #000; --dimmed: #868e96; --placeholder: #adb5bd;
  --default: #fff; --default-hover: #f8f9fa; --default-color: #000; --default-border: #ced4da;
  --input: #fff; --input-bd: #ced4da; --table-hover: #f1f3f5; --tab-border: #dee2e6; --tab-hover: #f8f9fa;
  --sc-root: #f1f3f5; --sc-ind: #fff; --sc-ind-shadow: var(--shadow-xs); --sc-label: #495057; --sc-active: #000;
  --switch-off: #e9ecef; --switch-off-bd: #dee2e6; --menu-bd: #e9ecef; --menu-hover: #f1f3f5;
  --kbd-bg: #f8f9fa; --kbd-bd: #dee2e6; --kbd-c: #495057;
  /* light-varianter: baggrund = farve-1, tekst = farve-9 */
  --gray-l: #f1f3f5; --gray-lc: #212529; --red-l: #ffe3e3; --red-lc: #c92a2a; --orange-l: #ffe8cc; --orange-lc: #d9480f;
  --yellow-l: #fff3bf; --yellow-lc: #e67700; --green-l: #d3f9d8; --green-lc: #2b8a3e; --teal-l: #c3fae8; --teal-lc: #087f5b;
  --blue-l: #d0ebff; --blue-lc: #1864ab; --grape-l: #f3d9fa; --grape-lc: #862e9c;
  /* Text c="farve" = farve-6 */
  --red-t: #fa5252; --orange-t: #fd7e14; --yellow-t: #fab005; --green-t: #40c057; --teal-t: #12b886; --blue-t: #228be6; --grape-t: #be4bdb;
  --red-f: #fa5252; --red-fh: #f03e3e;
}
/* Mantine, mørkt tema */
[data-theme='dark'] { color-scheme: dark;
  --text: #c9c9c9; --bright: #fff; --dimmed: #828282; --placeholder: #696969;
  --default-hover: #3b3b3b; --default-color: #fff;
  --table-hover: #3b3b3b; --tab-hover: var(--default);
  --sc-root: #1f1f1f; --sc-ind: #3b3b3b; --sc-ind-shadow: none; --sc-label: #b8b8b8; --sc-active: #fff;
  --switch-off: #3b3b3b; --menu-hover: #3b3b3b;
  --kbd-c: #c9c9c9;
  --fd-ok: #22c55e; --fd-warn: #f59e0b; --fd-bad: #ef4444; --fd-off: #52525b;
  --gray-l: rgb(17,19,21); --gray-lc: #f8f9fa; --red-l: rgb(101,21,21); --red-lc: #fff5f5; --orange-l: rgb(109,36,8); --orange-lc: #fff4e6;
  --yellow-l: rgb(115,60,0); --yellow-lc: #fff9db; --green-l: rgb(22,69,31); --green-lc: #ebfbee; --teal-l: rgb(4,64,46); --teal-lc: #e6fcf5;
  --blue-l: rgb(12,50,86); --blue-lc: #e7f5ff; --grape-l: rgb(67,23,78); --grape-lc: #f8f0fc;
  /* Text c="farve" = farve-4 */
  --red-t: #ff8787; --orange-t: #ffa94d; --yellow-t: #ffd43b; --green-t: #69db7c; --teal-t: #38d9a9; --blue-t: #4dabf7; --grape-t: #da77f2;
  --red-f: #ff6b6b; --red-fh: #fa5252;
}
/* Command (fleetdeck.css + skin.tsx: primær fleet) */
[data-theme='light'][data-skin='command'] { --body: #f7f7f8; --fd-side: #fbfbfc; --fd-card: #ffffff; --fd-border: #e4e4e7; --fd-chip: #f4f4f5; --fd-shadow: 0 1px 2px rgba(0,0,0,.04);
  --primary: #2563eb; --primary-hover: #1854d1; --primary-light: #d2e0ff; --primary-light-hover: #a3bffa; --primary-lc: #003fa6; }
[data-theme='dark'][data-skin='command'] { --body: #0b0b0d; --fd-side: #0f0f12; --fd-card: #141417; --fd-border: #232328; --fd-chip: #1c1c21; --fd-shadow: none;
  --default: #1c1c21; --default-border: #2c2c33; --input: #1c1c21; --input-bd: #2c2c33; --tab-border: #2c2c33; --switch-off-bd: #2c2c33; --menu-bd: #2c2c33; --kbd-bg: #1c1c21; --kbd-bd: #2c2c33;
  --primary: #3270f0; --primary-hover: #2563eb; --primary-light: rgb(0,32,83); --primary-light-hover: rgb(0,44,116); --primary-lc: #e8f1ff; }
/* Aurora (fleetdeck.css + skin.tsx: primær indigo) */
[data-theme='light'][data-skin='aurora'] { --body: #f3f5fb; --fd-side: rgba(255,255,255,.72); --fd-card: rgba(255,255,255,.8); --fd-border: rgba(15,23,42,.08); --fd-chip: rgba(15,23,42,.05);
  --fd-shadow: 0 8px 30px rgba(30,41,99,.08);
  --primary: #5459ee; --primary-hover: #4549d4; --primary-light: #dde0ff; --primary-light-hover: #b9bdfb; --primary-lc: #3036a8; }
[data-theme='dark'][data-skin='aurora'] { --body: #070b16; --fd-side: rgba(15,20,36,.72); --fd-card: rgba(22,28,48,.74); --fd-border: rgba(255,255,255,.07); --fd-chip: rgba(255,255,255,.05);
  --fd-shadow: 0 10px 40px rgba(0,0,0,.35);
  --default: #182040; --default-border: #2a3358; --input: #182040; --input-bd: #2a3358; --tab-border: #2a3358; --switch-off-bd: #2a3358; --menu-bd: #2a3358; --kbd-bg: #182040; --kbd-bd: #2a3358;
  --primary: #5f63ee; --primary-hover: #5459ee; --primary-light: rgb(24,27,84); --primary-light-hover: rgb(34,38,118); --primary-lc: #eef0ff; }

* { box-sizing: border-box; }
html, body { margin: 0; -webkit-text-size-adjust: 100%; }
body { position: relative; min-height: 100vh; font-family: var(--font); font-size: 14px; line-height: 1.55; color: var(--text); background: var(--body); }
[data-skin='aurora'] { background: var(--body); }
[data-skin='aurora'] body {
  background: radial-gradient(900px 520px at 88% -8%, rgba(56,189,248,.16), transparent 60%),
              radial-gradient(820px 520px at 8% 108%, rgba(129,140,248,.18), transparent 60%), var(--body); }
a { color: var(--primary); text-decoration: none; }
svg.i { width: 16px; height: 16px; flex: none; stroke: currentColor; fill: none; stroke-width: 1.75; stroke-linecap: round; stroke-linejoin: round; }
.tabnum { font-variant-numeric: tabular-nums; }
.dim { color: var(--dimmed); }
.xs { font-size: 12px; } .sm { font-size: 14px; }

/* ---------- Skal (AppShell: header 60, navbar 236, padding lg) ---------- */
.fd-header { position: fixed; top: 0; left: 0; right: 0; height: 60px; z-index: 100; display: flex; align-items: center; gap: 12px; padding: 0 20px;
  background: color-mix(in srgb, var(--body) 82%, transparent); border-bottom: 1px solid var(--fd-border); backdrop-filter: blur(14px); }
.fd-navbar { position: absolute; top: 60px; bottom: 0; left: 0; width: 236px; z-index: 90; display: flex; flex-direction: column; padding: 12px;
  background: var(--fd-side); border-right: 1px solid var(--fd-border); backdrop-filter: blur(20px); }
.fd-navbar .grow { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 2px; }
.fd-main { padding: 80px 20px 32px 256px; min-height: 100vh; }
[data-nav='top'] .fd-navbar { display: none; }
[data-nav='top'] .fd-main { padding-left: 20px; }
.fd-brand { display: inline-flex; align-items: center; gap: 10px; font-weight: 800; letter-spacing: -.02em; color: var(--bright); }
.fd-logo { border-radius: 9px; display: grid; place-items: center; color: #fff; background: linear-gradient(135deg, var(--fd-logo-a), var(--fd-logo-b)); flex: none; }
.fd-logo svg { stroke: #fff; fill: none; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
/* Søgeknappen i topbjælken (App.tsx, inline-stil 1:1) */
.fd-search { flex: 0 1 380px; height: 36px; border: 1px solid var(--fd-border); background: var(--fd-card); border-radius: 9px; padding: 0 12px;
  display: flex; align-items: center; gap: 8px; color: var(--dimmed); font-size: 13px; }
/* Kbd size xs */
kbd, .fd-search kbd { margin-left: auto; font: 700 10px/1.55 var(--mono); border: 1px solid var(--kbd-bd); border-bottom-width: 3px; border-radius: var(--r-sm); padding: .12em .45em;
  background: var(--kbd-bg); color: var(--kbd-c); }
.spacer { flex: 1; }
/* ActionIcon variant default size lg (34 px) */
.fd-icon-btn { width: 34px; height: 34px; border-radius: var(--r-default); border: 1px solid var(--default-border); background: var(--default); color: var(--default-color);
  display: grid; place-items: center; flex: none; }
.fd-icon-btn svg.i { width: 17px; height: 17px; }
/* Avatar size 34, radius xl, color initials */
.fd-avatar { width: 34px; height: 34px; border-radius: 1000px; display: grid; place-items: center; font-weight: 700; font-size: 13px; flex: none;
  color: var(--teal-lc); background: var(--teal-l); }

/* Sidemenu (fleetdeck.css .fd-nav, .fd-count, .fd-group) */
.fd-nav { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; color: var(--dimmed); font-size: 13.5px; font-weight: 500; }
.fd-nav svg.i { width: 18px; height: 18px; stroke-width: 1.6; }
.fd-nav:hover { background: var(--fd-chip); color: var(--text); }
.fd-nav[data-active] { background: var(--primary-light); color: var(--text); font-weight: 600; }
[data-skin='aurora'] .fd-nav[data-active] { background: linear-gradient(90deg, var(--primary-light), transparent); }
.fd-nav[data-active] svg { color: var(--primary); }
.fd-count { margin-left: auto; font-size: 11px; padding: 1px 7px; border-radius: 10px; background: var(--fd-chip); font-weight: 600; color: var(--text); }
.fd-count[data-red] { background: var(--fd-bad); color: #fff; }
.fd-group { font-size: 11px; font-weight: 600; color: var(--dimmed); text-transform: uppercase; letter-spacing: .06em; padding: 14px 10px 6px; opacity: .8; }
.fd-foot { font-size: 12px; color: var(--dimmed); padding: 10px; }

/* Topmenu (fleetdeck.css .fd-top på Button variant subtle color gray size compact-md) */
.fd-topnav { display: flex; gap: 2px; align-items: center; }
.fd-top { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border-radius: var(--r-btn); font-weight: 500; font-size: 16px; color: var(--dimmed); white-space: nowrap; line-height: 1; }
.fd-top[data-active] { color: var(--text); background: var(--primary-light); font-weight: 600; }
.fd-top svg.i { width: 14px; height: 14px; }
/* Menu / Popover-dropdown */
.fd-drop { position: absolute; top: 40px; min-width: 220px; padding: 4px; border-radius: var(--r-default); background: var(--default); border: 1px solid var(--menu-bd);
  box-shadow: var(--shadow-md); z-index: 120; }
.fd-drop a { display: flex; align-items: center; gap: 10px; padding: 6.67px 12px; border-radius: var(--r-default); color: var(--text); font-size: 14px; }
.fd-drop a[data-active] { background: var(--menu-hover); }
.fd-drop .lbl { font-size: 12px; color: var(--dimmed); font-weight: 600; padding: 5px 12px; }

/* ---------- Byggeklodser ---------- */
/* Title order 2, fw 700, letter-spacing -0.02em; undertitel Text c=dimmed size=sm */
.fd-title { font-size: 26px; font-weight: 700; letter-spacing: -.02em; margin: 0; line-height: 1.35; color: var(--bright); }
.fd-sub { color: var(--dimmed); font-size: 14px; margin-top: 2px; }
.fd-head { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
.stack { display: flex; flex-direction: column; gap: 20px; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.grid { display: grid; gap: 16px; }
.g2 { grid-template-columns: repeat(2, minmax(0, 1fr)); } .g3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.g4 { grid-template-columns: repeat(4, minmax(0, 1fr)); } .g6 { grid-template-columns: repeat(6, minmax(0, 1fr)); }
.span-all { grid-column: 1 / -1; }
.fd-dash-main { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px; align-items: start; }

/* Paper withBorder p="md" (fleetdeck.css: --fd-card, --fd-border, --fd-shadow; radius = theme default) */
.paper { background: var(--fd-card); border: 1px solid var(--fd-border); border-radius: var(--r-default); box-shadow: var(--fd-shadow); padding: 16px; min-width: 0; }
[data-skin='aurora'] .paper { backdrop-filter: blur(16px); }
.paper.flush { padding: 0; overflow: hidden; }
/* Kortets hoved: Group justify=space-between mb=sm + Text fw=650 */
.paper-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.paper.flush .paper-head { padding: 16px 16px 0; }
.paper-head h3 { margin: 0; font-size: 16px; font-weight: 650; color: var(--bright); }
.paper-head .more { margin-left: auto; }

/* Nøgletal (Dashboard.tsx Kpi + .fd-kpi-hero) */
.kpi .lbl { font-size: 12px; font-weight: 600; color: var(--dimmed); display: flex; align-items: center; gap: 6px; }
.kpi .lbl svg.i { width: 14px; height: 14px; }
.kpi .val { font-size: 28px; font-weight: 700; line-height: 1.2; margin-top: 4px; font-variant-numeric: tabular-nums; color: var(--text); }
.kpi .val small { font-size: 14px; font-weight: 500; color: var(--dimmed); }
.kpi .sub { font-size: 12px; color: var(--dimmed); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.v-red { color: var(--red-t) !important; } .v-orange { color: var(--orange-t) !important; } .v-yellow { color: var(--yellow-t) !important; }
.v-teal { color: var(--teal-t) !important; } .v-blue { color: var(--blue-t) !important; } .v-grape { color: var(--grape-t) !important; } .v-green { color: var(--green-t) !important; }
.fd-kpi-hero { background: linear-gradient(135deg, var(--fd-logo-a), var(--fd-logo-b)) !important; color: #fff; border: 0 !important; }
.fd-kpi-hero .lbl, .fd-kpi-hero .sub, .fd-kpi-hero .val small { color: rgba(255,255,255,.88); }
.fd-kpi-hero .val { color: #fff; }
.fd-spark { display: flex; align-items: flex-end; gap: 3px; height: 26px; margin-top: 8px; }
.fd-spark b { flex: 1; border-radius: 2px; background: color-mix(in srgb, var(--primary) 35%, transparent); }
.fd-spark b:last-child { background: var(--primary); }
.fd-kpi-hero .fd-spark b { background: rgba(255,255,255,.35); } .fd-kpi-hero .fd-spark b:last-child { background: #fff; }

/* ThemeIcon variant light (size sm 22 / md 28), radius default */
.ticon { width: 28px; height: 28px; border-radius: var(--r-default); display: grid; place-items: center; flex: none; }
.ticon.sm { width: 22px; height: 22px; }
.ticon svg.i { width: 16px; height: 16px; }
.t-blue { color: var(--primary-lc); background: var(--primary-light); } .t-teal { color: var(--teal-lc); background: var(--teal-l); }
.t-orange { color: var(--orange-lc); background: var(--orange-l); } .t-red { color: var(--red-lc); background: var(--red-l); }
.t-grape { color: var(--grape-lc); background: var(--grape-l); } .t-yellow { color: var(--yellow-lc); background: var(--yellow-l); }

/* Flåden (fleetdeck.css .fd-dot, .fd-minibar, .fd-machine, .fd-chips) */
.fd-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: currentColor; box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 18%, transparent); }
.c-ok { color: var(--fd-ok); } .c-warn { color: var(--fd-warn); } .c-bad { color: var(--fd-bad); } .c-off { color: var(--fd-off); } .c-pri { color: var(--primary); }
.fd-minibar { height: 5px; border-radius: 3px; background: var(--fd-chip); overflow: hidden; margin-top: 8px; }
.fd-minibar i { display: block; height: 100%; border-radius: 3px; }
.fd-machine { border: 1px solid var(--fd-border); border-radius: var(--r-md); padding: 12px; display: flex; flex-direction: column; gap: 9px;
  background: color-mix(in srgb, var(--fd-card) 70%, var(--body)); color: inherit; }
.fd-chips { display: flex; flex-wrap: wrap; gap: 4px; font-size: 11px; color: var(--dimmed); }
.fd-chips span { display: inline-flex; align-items: center; gap: 3px; padding: 1px 6px; border-radius: 6px; border: 1px solid var(--fd-border);
  background: color-mix(in srgb, var(--text) 3%, transparent); font-variant-numeric: tabular-nums; }
.fd-chips svg.i { width: 12px; height: 12px; }

/* Badge variant light, radius sm; size sm (18 px) som standard, .xs = 16 px */
.badge { display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 18px; padding: 0 8px; border-radius: var(--r-badge);
  font-size: 10px; font-weight: 700; line-height: 16px; text-transform: uppercase; letter-spacing: .25px; white-space: nowrap; border: 1px solid transparent; }
.badge.xs { height: 16px; padding: 0 6px; font-size: 9px; line-height: 14px; }
.b-ok { color: var(--green-lc); background: var(--green-l); } .b-teal { color: var(--teal-lc); background: var(--teal-l); }
.b-warn { color: var(--orange-lc); background: var(--orange-l); } .b-bad { color: var(--red-lc); background: var(--red-l); }
.b-blue { color: var(--primary-lc); background: var(--primary-light); } .b-gray { color: var(--gray-lc); background: var(--gray-l); }
.b-grape { color: var(--grape-lc); background: var(--grape-l); } .b-yellow { color: var(--yellow-lc); background: var(--yellow-l); }

/* Button: size sm 36 px (standard), .s30 = xs, .sm = compact-sm 26 px, .xs = compact-xs 22 px. fw 600, line-height 1.
   Varianter: default (standard her, som i Fleetdeck), .pri = filled, .light, .subtle, .red = color red variant light */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 36px; padding: 0 18px; border-radius: var(--r-btn); font: 600 14px/1 var(--font);
  border: 1px solid var(--default-border); background: var(--default); color: var(--default-color); white-space: nowrap; cursor: pointer; }
.btn:has(svg.i:first-child) { padding-left: 12px; }
.btn:hover { background: var(--default-hover); }
.btn.s30 { height: 30px; padding: 0 14px; font-size: 12px; } .btn.s30:has(svg.i:first-child) { padding-left: 9.33px; }
.btn.sm { height: 26px; padding: 0 8px; font-size: 14px; gap: 6px; } .btn.sm:has(svg.i:first-child) { padding-left: 5.33px; }
.btn.xs { height: 22px; padding: 0 7px; font-size: 12px; gap: 5px; } .btn.xs:has(svg.i:first-child) { padding-left: 4.67px; }
.btn.sm svg.i, .btn.xs svg.i { width: 14px; height: 14px; }
.btn.pri { background: var(--primary); color: #fff; border-color: transparent; } .btn.pri:hover { background: var(--primary-hover); }
[data-skin='aurora'] .btn.pri { background-image: linear-gradient(135deg, var(--fd-logo-a), var(--fd-logo-b)); border: 0; }
.btn.light { background: var(--primary-light); color: var(--primary-lc); border-color: transparent; } .btn.light:hover { background: var(--primary-light-hover); }
.btn.subtle { background: transparent; border-color: transparent; color: var(--primary-lc); } .btn.subtle:hover { background: var(--primary-light); }
.btn.subtle.gray { color: var(--gray-lc); } .btn.subtle.gray:hover { background: var(--gray-l); }
.btn.red { background: var(--red-l); color: var(--red-lc); border-color: transparent; }

/* SegmentedControl size xs */
.seg { display: inline-flex; padding: 4px; gap: 0; border-radius: var(--r-default); background: var(--sc-root); }
.seg span { padding: 2px 6px; border-radius: calc(var(--r-default) - 4px); font-size: 12px; font-weight: 600; color: var(--sc-label); line-height: 1.55; }
.seg span[data-active] { background: var(--sc-ind); color: var(--sc-active); box-shadow: var(--sc-ind-shadow); }

/* Tabs variant default: 2 px linje, fane 10/16 px, fz sm */
.tabs { display: flex; box-shadow: inset 0 -2px 0 var(--tab-border); margin-bottom: 16px; overflow: hidden; }
.tabs span { padding: 10px 16px; font-size: 14px; line-height: 1; color: var(--text); border-bottom: 2px solid transparent; white-space: nowrap;
  display: inline-flex; gap: 8px; align-items: center; border-radius: var(--r-default) var(--r-default) 0 0; }
.tabs span[data-active] { border-color: var(--primary); }

/* Table highlightOnHover verticalSpacing xs: fz sm, celler 10 px, række-kant --fd-border (fleetdeck.css) */
table.fd-table { width: 100%; border-collapse: collapse; font-size: 14px; line-height: 1.55; }
.fd-table th { text-align: start; font-weight: 700; color: var(--text); padding: 10px; border-bottom: 1px solid var(--fd-border); white-space: nowrap; }
.fd-table td { padding: 10px; border-bottom: 1px solid var(--fd-border); vertical-align: middle; }
.fd-table th:first-child, .fd-table td:first-child { padding-left: 16px; } .fd-table th:last-child, .fd-table td:last-child { padding-right: 16px; }
.fd-table tr:last-child td { border-bottom: 0; }
.fd-table tbody tr:hover { background: var(--table-hover); }
.fd-table .main { font-weight: 600; color: var(--text); }
/* Checkbox size sm */
.cb { width: 20px; height: 20px; border-radius: var(--r-xs); border: 1px solid var(--input-bd); background: var(--input); display: inline-block; vertical-align: middle; }
.cb[data-on] { background: var(--primary); border-color: var(--primary); }

/* TextInput size sm + label (fz sm, fw medium = 600) */
.field { display: flex; flex-direction: column; gap: 4px; font-size: 14px; font-weight: 600; color: var(--text); }
.input { height: 36px; border: 1px solid var(--input-bd); border-radius: var(--r-default); background: var(--input); padding: 0 12px; display: flex; align-items: center;
  color: var(--text); font-size: 14px; font-weight: 400; }
.input .dim { color: var(--placeholder); }
/* Switch size sm: 38×20, knap 14 */
.switch { width: 38px; height: 20px; border-radius: 1000px; background: var(--switch-off); border: 1px solid var(--switch-off-bd); position: relative; flex: none; }
.switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 1000px; background: #fff; }
.switch[data-on] { background: var(--primary); border-color: var(--primary); } .switch[data-on]::after { left: 20px; }

.list-row { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-top: 1px solid var(--fd-border); }
.list-row:first-child { border-top: 0; }
/* Alert variant light: farve-baggrund, ingen kant, padding md, titel fw 700 i alert-farven, tekst sort/hvid */
.alert { display: flex; gap: 16px; align-items: flex-start; padding: 16px; border-radius: var(--r-default); font-size: 14px; border: 1px solid transparent;
  background: var(--primary-light); color: var(--primary-lc); }
.alert > svg.i { width: 20px; height: 20px; margin-top: 1px; }
.alert b { font-weight: 700; }
.alert > div > div { color: var(--bright); font-size: 14px; margin-top: 4px; }
.alert.warn { background: var(--orange-l); color: var(--orange-lc); } .alert.bad { background: var(--red-l); color: var(--red-lc); }
.alert.ok { background: var(--teal-l); color: var(--teal-lc); }
/* RingProgress size 52, thickness 6 */
.ring { --p: 70; --c: var(--teal-t); width: 52px; height: 52px; border-radius: 50%; flex: none; display: grid; place-items: center;
  background: conic-gradient(var(--c) calc(var(--p) * 1%), var(--fd-chip) 0); }
.ring::before { content: ""; width: 40px; height: 40px; border-radius: 50%; background: var(--fd-card); grid-area: 1/1; }
[data-skin='aurora'][data-theme='light'] .ring::before { background: #fff; }
/* Aktivitet (fleetdeck.css .fd-activity) */
.fd-activity { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 12px; border-radius: 999px; font-size: 13px; font-weight: 600;
  color: var(--primary); background: color-mix(in srgb, var(--primary) 12%, transparent); white-space: nowrap; }
.fd-activity.ok { color: var(--fd-ok); background: color-mix(in srgb, var(--fd-ok) 12%, transparent); }
.chart { width: 100%; height: 170px; display: block; }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--dimmed); flex-wrap: wrap; }
.legend i { display: inline-block; width: 10px; height: 3px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }

/* ---------- Mobil (fleetdeck.css .fd-tabbar + mobile.css) ---------- */
.fd-tabbar { display: none; }
.fd-sheet { display: none; }
.only-mobile { display: none !important; }
@media (max-width: 48em) {
  .fd-header { padding: 0 12px; }
  .fd-navbar, .only-desktop { display: none !important; }
  .only-mobile { display: initial !important; }
  .fd-main, [data-nav='top'] .fd-main { padding: 72px 12px calc(76px + env(safe-area-inset-bottom)); }
  .fd-tabbar { display: grid; grid-template-columns: repeat(5, 1fr); position: fixed; left: 0; right: 0; bottom: 0; z-index: 210;
    padding: 6px 4px calc(6px + env(safe-area-inset-bottom)); background: color-mix(in srgb, var(--body) 88%, transparent);
    backdrop-filter: blur(16px); border-top: 1px solid var(--fd-border); }
  .fd-tabbar a { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 10.5px; font-weight: 500; color: var(--dimmed); padding: 4px 0; }
  .fd-tabbar a span { position: relative; }
  .fd-tabbar svg.i { width: 22px; height: 22px; stroke-width: 1.7; }
  .fd-tabbar [data-active] { color: var(--primary); font-weight: 600; }
  .fd-tabbar b { position: absolute; top: -4px; right: -10px; min-width: 16px; height: 16px; border-radius: 8px; padding: 0 4px; font-size: 10px; line-height: 16px; text-align: center; background: var(--fd-warn); color: #fff; }
  .fd-tabbar b[data-red] { background: var(--fd-bad); }
  /* "Mere" åbner Fleetdecks navbar som fuldskærm (AppShell navbar på mobil) */
  .fd-sheet[data-open] { display: block; position: fixed; left: 0; right: 0; bottom: 0; top: 60px; z-index: 200; background: var(--fd-side); padding: 12px 12px 90px; backdrop-filter: blur(20px); overflow: auto; }
  [data-theme='light'][data-skin='aurora'] .fd-sheet[data-open] { background: rgba(255,255,255,.94); }
  .fd-sheet .fd-nav { font-size: 16px; min-height: 44px; }
  .fd-title { font-size: 22px; }
  .g2, .g3, .g4 { grid-template-columns: minmax(0, 1fr); }
  .g6, .m2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fd-dash-main { grid-template-columns: minmax(0, 1fr); }
  .stack { gap: 16px; } .grid { gap: 12px; }
  .kpi .val { font-size: 24px; }
  /* mobile.css: tryk-venlige knapper */
  .btn.xs, .btn.sm, .btn.s30 { min-height: 36px; padding-inline: 12px; font-size: 14px; }
  .fd-icon-btn { min-width: 36px; min-height: 36px; }
  .tabs span { min-height: 44px; font-size: 15px; }
  .seg span { min-height: 32px; display: flex; align-items: center; justify-content: center; }
  .input { font-size: 16px; }
  .badge.xs { font-size: 11px; height: 20px; padding-inline: 7px; }
  .badge { font-size: 12px; height: 22px; }
  /* mobile.css: tabeller som kort */
  .fd-table thead { display: none; }
  .fd-table, .fd-table tbody { display: block; }
  .fd-table tr { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: 12px 14px; border-bottom: 1px solid var(--fd-border); }
  .fd-table td, .fd-table td:first-child, .fd-table td:last-child { display: block; padding: 0; border: 0; font-size: 15px; line-height: 1.4; min-width: 0; }
  .fd-table td.main { flex: 1 1 100%; }
  .fd-table td[data-label]::before { content: attr(data-label); display: block; font-size: 12px; font-weight: 500; color: var(--dimmed); margin-bottom: 2px; }
  .fd-table td.hide-m { display: none; }
}

/* ---------- Kiosk Warden: shell details ---------- */
body:not(:has(.fd-header)) .fd-main { padding: 32px 16px; }
.fd-main > .narrow, .narrow { max-width: 720px; }
.fd-header .fd-brand { font-size: 15px; }
.fd-header .ctx { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 12px; border-radius: var(--r-btn);
  border: 1px solid var(--default-border); background: var(--default); color: var(--default-color); font-weight: 600; font-size: 13px; white-space: nowrap; max-width: 280px; overflow: hidden; }
.fd-header .ctx span { overflow: hidden; text-overflow: ellipsis; }
.fd-activity.warn { color: var(--fd-warn); background: color-mix(in srgb, var(--fd-warn) 12%, transparent); }
.fd-activity.bad { color: var(--fd-bad); background: color-mix(in srgb, var(--fd-bad) 12%, transparent); }
.fd-mtitle { font-weight: 700; font-size: 16px; letter-spacing: -.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.fd-navbar .fd-brandrow { padding: 4px 8px 14px; }
a.fd-nav, a.fd-top { cursor: pointer; }
.fd-top:hover { color: var(--text); }
.fd-top .fd-count { margin-left: 2px; }

/* Menus (Mantine Menu) */
.fd-menu { position: relative; display: inline-flex; }
.fd-menu > .fd-drop { display: none; }
.fd-menu[data-open] > .fd-drop { display: block; }
.fd-menu.end > .fd-drop { right: 0; }
.fd-drop { top: calc(100% + 6px); }
.fd-drop a, .fd-drop button { display: flex; width: 100%; align-items: center; gap: 10px; height: auto; padding: 6.67px 12px; border: 0; border-radius: var(--r-default);
  background: transparent; color: var(--text); font: 400 14px/1.55 var(--font); text-align: start; cursor: pointer; white-space: nowrap; }
.fd-drop a:hover, .fd-drop button:hover { background: var(--menu-hover); filter: none; }
.fd-drop svg.i { width: 14px; height: 14px; }
.fd-drop .chk { margin-left: auto; width: 14px; height: 14px; color: var(--primary); }
.fd-drop .chk.off { visibility: hidden; }
.fd-drop .note { color: var(--dimmed); font-size: 12px; }
.fd-drop hr { border: 0; border-top: 1px solid var(--menu-bd); margin: 4px 0; }
.fd-drop .who { padding: 8px 12px 6px; font-size: 13px; }
.fd-drop .who b { display: block; color: var(--bright); }
.fd-drop .danger { color: var(--red-t); }

/* Search (Spotlight) */
.fd-search { position: relative; cursor: text; }
.fd-search input { flex: 1; min-width: 0; height: 34px; padding: 0; border: 0; background: transparent; color: var(--text); font: 400 13px var(--font); outline: none; }
.fd-search input::placeholder { color: var(--dimmed); }
.fd-search .fd-drop { left: 0; right: 0; top: calc(100% + 6px); }
.fd-search .fd-drop[hidden] { display: none; }
.fd-search .fd-drop a[data-hit] { background: var(--menu-hover); }
.fd-search .fd-drop { max-height: min(70vh, 520px); overflow-y: auto; width: max(100%, 300px); right: auto; }
.fd-search .fd-drop small { margin-left: auto; padding-left: 12px; color: var(--dimmed); font-size: 12px; white-space: nowrap; }
.fd-search .fd-drop .lbl[hidden] { display: none; }
.fd-search input::-webkit-search-cancel-button { display: none; }
@media (min-width: 48.0625em) and (max-width: 1280px) { [data-nav='top'] .fd-header .ctx .dim { display: none; } [data-nav='top'] .fd-header .ctx { flex: none; } }
.fd-header .fd-brand { white-space: nowrap; }
/* The search also sits in the top bar with the menu at the top (Fleetdeck):
   right after the menu, a little narrower. With less room it folds to a
   search button that opens over the menu while typing. */
[data-nav='top'] .fd-search { flex: 0 1 300px; min-width: 180px; margin-left: 4px; }
@media (min-width: 48.0625em) and (max-width: 1440px) { [data-nav='top'] .fd-search kbd { display: none; } }
@media (min-width: 48.0625em) and (max-width: 1100px) {
  [data-nav='top'] .fd-search { flex: none; width: 36px; min-width: 36px; padding: 0; justify-content: center; color: var(--text); cursor: pointer; }
  [data-nav='top'] .fd-search > svg { pointer-events: none; }
  [data-nav='top'] .fd-search input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  [data-nav='top'] .fd-search:focus-within { width: 300px; margin-left: -260px; z-index: 5; padding: 0 12px; justify-content: flex-start; color: var(--dimmed);
    background: var(--default); box-shadow: var(--shadow-md); }
  [data-nav='top'] .fd-search:focus-within input { position: static; opacity: 1; cursor: text; }
  [data-nav='top'] .fd-search .fd-drop { left: auto; right: -1px; }
}
@media (min-width: 48.0625em) and (max-width: 900px) {
  [data-nav='top'] .fd-header .fd-brand > span:not(.fd-logo) { display: none; }
  [data-nav='top'] .fd-top { padding: 0 7px; }
}
/* Phone: a clear search button in the top bar opens the field as a row under it. */
.topbar-search-btn { width: 34px; height: 34px; display: inline-grid; place-items: center; flex: none; }
.topbar-search-btn[data-active] { color: var(--primary); }
@media (max-width: 48em) {
  .fd-search { display: none; }
  .search-open .fd-search { display: flex; position: fixed; left: 12px; right: 12px; top: 68px; height: 44px; z-index: 120; background: var(--default); box-shadow: var(--shadow-md); }
  .fd-search input { font-size: 16px; }
  .fd-search kbd { display: none; }
  .fd-search .fd-drop { left: -1px; right: -1px; width: auto; top: 50px; max-height: calc(100vh - 200px); }
  .fd-header .topbar-search-btn { display: inline-grid !important; }
}

/* Buttons that are not part of the generic form style */
button.fd-icon-btn { padding: 0; height: 34px; font: inherit; cursor: pointer; }
button.fd-icon-btn:hover { background: var(--default-hover); }
button.fd-avatar { border: 0; padding: 0; cursor: pointer; font: 700 13px var(--font); }
.fd-tabbar button { display: flex; flex-direction: column; align-items: center; gap: 2px; font: 500 10.5px var(--font); color: var(--dimmed); padding: 4px 0;
  background: transparent; border: 0; height: auto; border-radius: 0; cursor: pointer; }
.fd-tabbar button[data-active] { color: var(--primary); font-weight: 600; }
.fd-sheet a.fd-nav { cursor: pointer; }
.fd-sheet .fd-look { padding: 4px 10px 8px; display: flex; flex-direction: column; gap: 10px; }

/* ---------- Page head ---------- */
.fd-head .aside { margin-left: auto; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.fd-head .pill { align-self: center; }

/* ---------- Native form elements in Fleetdeck style ---------- */
fieldset { margin: 0 0 16px; padding: 16px; min-width: 0; background: var(--fd-card); border: 1px solid var(--fd-border); border-radius: var(--r-default); box-shadow: var(--fd-shadow); }
[data-skin='aurora'] fieldset { backdrop-filter: blur(16px); }
legend { float: left; width: 100%; padding: 0; margin: 0 0 12px; font-size: 16px; font-weight: 650; line-height: 1.35; color: var(--bright); }
legend + * { clear: both; }
legend + label, legend + .sub + label { margin-top: 0; }
fieldset fieldset { margin: 16px 0 0; padding: 12px; box-shadow: none; background: color-mix(in srgb, var(--fd-card) 70%, var(--body)); }
fieldset fieldset legend { font-size: 14px; }
form + form, fieldset + form, form + fieldset { margin-top: 0; }
.stack > fieldset, .stack > form > fieldset { margin-bottom: 0; }
label { display: block; margin: 12px 0 4px; font-size: 14px; font-weight: 600; color: var(--text); }
label:has(> input[type=checkbox]) { display: flex; align-items: center; gap: 10px; font-weight: 400; cursor: pointer; margin-top: 12px; }
input[type=text], input[type=password], input[type=number], input[type=url], select, textarea {
  display: block; width: 100%; height: 36px; margin: 0; padding: 0 12px; border: 1px solid var(--input-bd); border-radius: var(--r-default);
  background-color: var(--input); color: var(--text); font: 400 14px/1.55 var(--font); }
textarea { height: auto; min-height: 96px; padding: 8px 12px; font-family: var(--mono); font-size: 13px; resize: vertical; }
select { appearance: none; -webkit-appearance: none; padding-right: 34px; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23868e96' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center; background-size: 16px; }
input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); }
::placeholder { color: var(--placeholder); }
input:disabled, select:disabled, textarea:disabled { cursor: not-allowed; opacity: .6; background-color: var(--fd-chip); }
input[type=checkbox] { appearance: none; -webkit-appearance: none; width: 20px; height: 20px; margin: 0; flex: none; border: 1px solid var(--input-bd);
  border-radius: var(--r-xs); background: var(--input); cursor: pointer; }
input[type=checkbox]:checked { border-color: var(--primary); background: var(--primary) no-repeat center / 14px
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12l5 5l10 -10'/%3E%3C/svg%3E"); }
.choice-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0 12px; }
.choice-grid label { margin-top: 8px; }

/* Button (Mantine Button size sm, variant default / filled / light) */
button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 36px; padding: 0 18px; border-radius: var(--r-btn);
  font: 600 14px/1 var(--font); border: 1px solid var(--default-border); background: var(--default); color: var(--default-color); white-space: nowrap; cursor: pointer; }
button:has(svg.i:first-child) { padding-left: 12px; }
button:hover { background: var(--default-hover); }
button:active { transform: translateY(1px); }
button.primary, button.accent { background: var(--primary); color: #fff; border-color: transparent; }
button.primary:hover, button.accent:hover { background: var(--primary-hover); }
[data-skin='aurora'] button.primary, [data-skin='aurora'] button.accent { background-image: linear-gradient(135deg, var(--fd-logo-a), var(--fd-logo-b)); border: 0; }
button.danger { background: var(--red-l); color: var(--red-lc); border-color: transparent; }
button.danger:hover { background: color-mix(in srgb, var(--red-l) 80%, var(--red-t)); }
button.light { background: var(--primary-light); color: var(--primary-lc); border-color: transparent; }
button.light:hover { background: var(--primary-light-hover); }
button.subtle { background: transparent; border-color: transparent; color: var(--primary-lc); }
button.subtle:hover { background: var(--primary-light); }
button.icon-only { width: 36px; padding: 0; }
button:disabled, button:disabled:hover { cursor: not-allowed; transform: none; border-color: transparent; background: var(--fd-chip); background-image: none; color: var(--placeholder); box-shadow: none; }
.btn.red:hover { background: color-mix(in srgb, var(--red-l) 80%, var(--red-t)); }
.btn.subtle svg.i, button svg.i { width: 16px; height: 16px; }
.row { margin-top: 12px; }
.fd-head .row, .paper-head .row, .alert .row { margin-top: 0; }
.row > form { display: contents; }

/* Messages, pills, status text */
.msg { display: flex; gap: 12px; align-items: flex-start; padding: 12px 16px; border-radius: var(--r-default); margin-bottom: 16px; font-size: 14px; font-weight: 600; }
.msg svg.i { width: 18px; height: 18px; margin-top: 2px; }
.msg.error { background: var(--red-l); color: var(--red-lc); }
.msg.ok { background: var(--green-l); color: var(--green-lc); }
.pill { display: inline-flex; align-items: center; height: 22px; padding: 0 10px; border-radius: var(--r-badge); font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .25px; white-space: nowrap; color: var(--gray-lc); background: var(--gray-l); }
.pill.ok { color: var(--green-lc); background: var(--green-l); }
.pill.err { color: var(--red-lc); background: var(--red-l); }
.pill.warn { color: var(--orange-lc); background: var(--orange-l); }
.pill.info { color: var(--primary-lc); background: var(--primary-light); }
.status, .sub { color: var(--dimmed); font-size: 13px; margin: 8px 0 0; }
fieldset > .sub:first-of-type, legend + .sub, legend + p.status { margin: 0 0 4px; }
p.status { line-height: 1.55; }
img.shot { max-width: 100%; border-radius: var(--r-default); border: 1px solid var(--fd-border); display: block; }

/* Small value tiles (fd-machine) */
.grid { grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.grid.g2 { grid-template-columns: repeat(2, minmax(0, 1fr)); } .grid.g3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
fieldset .grid { margin: 0 0 4px; }
.tile { border: 1px solid var(--fd-border); border-radius: var(--r-md); padding: 10px 12px; min-width: 0; display: flex; flex-direction: column; gap: 2px;
  background: color-mix(in srgb, var(--fd-card) 70%, var(--body)); }
.tile > span { font-size: 12px; color: var(--dimmed); }
.tile > strong { font-weight: 600; color: var(--text); overflow-wrap: anywhere; }

/* Status page */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
.kpi { padding: 12px 14px; }
.kpi .val { font-size: 26px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi .val.err { color: var(--red-t); }
.kpi .val.warn { color: var(--orange-t); }
.bar-ok { background: var(--fd-ok); } .bar-warn { background: var(--fd-warn); } .bar-err { background: var(--fd-bad); } .bar-neutral { background: var(--primary); }
.kv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); margin: 0 -1px -1px 0; }
.kv-grid > div { padding: 12px 16px; border-right: 1px solid var(--fd-border); border-bottom: 1px solid var(--fd-border); min-width: 0; }
.kv-grid .k { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--dimmed); }
.kv-grid .k svg.i { width: 14px; height: 14px; }
.kv-grid .v { font-weight: 600; margin-top: 2px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; }
.chart-card { background: var(--fd-card); border: 1px solid var(--fd-border); border-radius: var(--r-default); box-shadow: var(--fd-shadow); padding: 16px; min-width: 0; }
[data-skin='aurora'] .chart-card { backdrop-filter: blur(16px); }
.chart-title { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; font-size: 16px; font-weight: 650; color: var(--bright); }
.chart-title small { margin-left: auto; font-size: 12px; font-weight: 400; color: var(--dimmed); white-space: nowrap; }
.chart-card .legend { margin: -2px 0 8px; }
canvas.telemetry-chart { display: block; width: 100%; height: 170px; }
.update-alert { color: inherit; }

/* Kiosk page tabs (Mantine Tabs) */
.tabs { overflow-x: auto; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tabs button { height: auto; padding: 10px 16px; font: 400 14px/1 var(--font); color: var(--text); background: transparent; border: 0; border-bottom: 2px solid transparent;
  border-radius: var(--r-default) var(--r-default) 0 0; white-space: nowrap; }
.tabs button:hover { background: var(--tab-hover); border-bottom-color: var(--tab-border); }
.tabs button[aria-selected='true'] { border-bottom-color: var(--primary); font-weight: 600; }
.tabs button svg.i { width: 16px; height: 16px; }
.tabs button:active { transform: none; }
.tab-panel[hidden] { display: none; }
.tab-cols { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
.tab-cols > div { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.tab-cols fieldset { margin: 0; }

/* SegmentedControl as real buttons */
.seg button { height: auto; padding: 2px 10px; border: 0; border-radius: calc(var(--r-default) - 4px); background: transparent; color: var(--sc-label); font: 600 12px/1.55 var(--font); }
.seg button:hover { background: transparent; color: var(--sc-active); }
.seg button[aria-pressed='true'] { background: var(--sc-ind); color: var(--sc-active); box-shadow: var(--sc-ind-shadow); }
.seg button:active { transform: none; }
.look-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.look-row > span { min-width: 64px; font-weight: 600; }

/* Updates page */
.version-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 16px; }
.version-card { background: var(--fd-card); border: 1px solid var(--fd-border); border-radius: var(--r-default); box-shadow: var(--fd-shadow); padding: 12px 14px; }
.version-card span { display: block; font-size: 12px; font-weight: 600; color: var(--dimmed); }
.version-card strong { display: block; font-size: 26px; font-weight: 700; line-height: 1.2; margin-top: 4px; color: var(--text); font-variant-numeric: tabular-nums; }
.release-notes { border: 1px solid var(--fd-border); border-radius: var(--r-md); padding: 12px 14px; margin: 16px 0 12px; background: color-mix(in srgb, var(--fd-card) 70%, var(--body)); }
.release-notes > strong { color: var(--bright); }
.changelog h2 { font-size: 15px; font-weight: 650; color: var(--bright); margin: 20px 0 4px; }
.changelog h2:first-child { margin-top: 0; }
.changelog ul { padding-left: 20px; margin: 4px 0 0; }
.changelog li { margin: 4px 0; }
.changelog p { color: var(--dimmed); font-size: 13px; margin: 2px 0 8px; }
.progress-shell { display: none; margin-top: 16px; }
.progress-track { height: 8px; overflow: hidden; border-radius: 999px; background: var(--fd-chip); }
.progress-fill { width: 0; height: 100%; border-radius: inherit; background: var(--primary); transition: width .35s ease; }
[data-skin='aurora'] .progress-fill { background: linear-gradient(90deg, var(--fd-logo-a), var(--fd-logo-b)); }
.progress-meta { display: flex; justify-content: space-between; gap: 16px; margin-top: 6px; font-size: 13px; color: var(--dimmed); }
.progress-meta strong { color: var(--text); }
.restart-choice { display: none; margin-top: 16px; padding: 16px; border-radius: var(--r-default); background: var(--teal-l); color: var(--text); }
.restart-choice strong { color: var(--teal-lc); }
.countdown { font-size: 15px; font-weight: 700; color: var(--orange-t); margin-top: 8px; }
.countdown:empty { display: none; }

/* Remote control */
.vnc-frame { margin-top: 16px; border-radius: var(--r-default); overflow: hidden; border: 1px solid var(--fd-border); background: #000; }
.vnc-frame iframe { width: 100%; height: calc(100vh - 250px); min-height: 420px; border: 0; display: block; background: #000; }
.vnc-empty { margin-top: 16px; min-height: 420px; display: grid; place-items: center; gap: 12px; text-align: center; border: 1px dashed var(--fd-border);
  border-radius: var(--r-default); background: var(--fd-card); color: var(--dimmed); }
.vnc-empty svg.i { width: 40px; height: 40px; stroke-width: 1.3; margin: 0 auto 8px; display: block; color: var(--fd-off); }

/* Login and first run */
.login-shell { min-height: calc(100vh - 64px); display: grid; place-items: center; }
.login-card { width: min(420px, 100%); padding: 32px; background: var(--fd-card); border: 1px solid var(--fd-border); border-radius: var(--r-lg); box-shadow: var(--shadow-md); }
[data-skin='aurora'] .login-card { backdrop-filter: blur(16px); }
.login-mark { width: 56px; height: 56px; margin: 0 auto 12px; border-radius: 14px; }
.login-product { text-align: center; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--dimmed); }
.login-card h1 { text-align: center; font-size: 26px; font-weight: 700; letter-spacing: -.02em; margin: 4px 0 2px; color: var(--bright); }
.login-card .sub { text-align: center; margin: 0 0 20px; font-size: 14px; }
.login-button { width: 100%; margin-top: 20px; }
.login-note { text-align: center; color: var(--dimmed); font-size: 12px; margin: 20px 0 0; }

@media (max-width: 48em) {
  .tab-cols { grid-template-columns: minmax(0, 1fr); }
  .charts { grid-template-columns: minmax(0, 1fr); }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .kpis > .fd-kpi-hero { grid-column: 1 / -1; }
  .kv-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .kv-grid > div { padding: 10px 12px; }
  .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fd-head .aside { margin-left: 0; }
  button { min-height: 36px; }
  .tabs button { min-height: 44px; font-size: 15px; }
  input[type=text], input[type=password], input[type=number], select, textarea { font-size: 16px; }
  .vnc-frame iframe { height: calc(100vh - 300px); }
  .login-card { padding: 24px 20px; }
}

/* Menu position: side menu (forslag A) shows the search, top menu (forslag B) shows the brand and menu in the bar */
[data-nav='side'] .top-only, [data-nav='side'] .fd-topnav, [data-nav='top'] .top-hide { display: none !important; }
label.fd-search { margin: 0; font-weight: 400; }
.fd-drop a[hidden] { display: none; }
.fd-sheet .fd-look { flex-direction: row; flex-wrap: wrap; gap: 8px; }
.fd-sheet .seg button { min-height: 32px; padding: 2px 10px; font-size: 13px; }
.fd-navbar { position: fixed; }
.fd-tabbar button:hover, .fd-tabbar button:active { background: transparent; transform: none; }
.alert .btn { flex: none; }
@media (max-width: 48em) {
  .alert { flex-wrap: wrap; gap: 8px 16px; }
  .alert > div { flex: 1 1 calc(100% - 40px) !important; }
  .alert > .btn { margin-left: 36px; }
}
"""

APP_JS = r"""// Kiosk Warden UI: appearance (Fleetdeck Command/Aurora), menus, "More" sheet, page search and tabs.
(function () {
  'use strict';
  var root = document.documentElement;
  var KEYS = { skin: 'kw-skin', theme: 'kw-theme', nav: 'kw-nav' };
  var DEFAULTS = { skin: 'command', theme: 'dark', nav: 'side' };
  var PRESETS = { a: { skin: 'command', theme: 'dark', nav: 'side' }, b: { skin: 'aurora', theme: 'light', nav: 'top' } };

  function get(key) { try { return localStorage.getItem(KEYS[key]) || DEFAULTS[key]; } catch (_) { return DEFAULTS[key]; } }
  function put(key, value) { try { localStorage.setItem(KEYS[key], value); } catch (_) {} }
  var media = window.matchMedia ? matchMedia('(prefers-color-scheme: dark)') : null;
  function computedTheme() { var t = get('theme'); return t === 'auto' ? (media && media.matches ? 'dark' : 'light') : t; }

  function applyLook() {
    root.dataset.skin = get('skin');
    root.dataset.theme = computedTheme();
    root.dataset.nav = get('nav');
    var preset = '';
    Object.keys(PRESETS).forEach(function (name) {
      var p = PRESETS[name];
      if (p.skin === get('skin') && p.theme === get('theme') && p.nav === get('nav')) preset = name;
    });
    document.querySelectorAll('[data-look]').forEach(function (el) {
      var key = el.getAttribute('data-look'), val = el.getAttribute('data-value');
      var on = key === 'preset' ? val === preset : get(key) === val;
      el.setAttribute('aria-pressed', on ? 'true' : 'false');
      var chk = el.querySelector('.chk');
      if (chk) chk.classList.toggle('off', !on);
    });
    document.querySelectorAll('[data-theme-icon]').forEach(function (el) {
      el.hidden = el.getAttribute('data-theme-icon') !== root.dataset.theme;
    });
    window.dispatchEvent(new Event('kw-look'));
  }

  document.addEventListener('click', function (event) {
    var look = event.target.closest('[data-look]');
    if (look) {
      var key = look.getAttribute('data-look'), val = look.getAttribute('data-value');
      if (key === 'preset') { var p = PRESETS[val]; Object.keys(p).forEach(function (k) { put(k, p[k]); }); }
      else put(key, val);
      applyLook();
      var openMenu = look.closest('.fd-menu');
      if (openMenu) openMenu.removeAttribute('data-open');
      return;
    }
    var toggle = event.target.closest('[data-menu-toggle]');
    var menus = document.querySelectorAll('.fd-menu[data-open]');
    menus.forEach(function (m) { if (!toggle || m !== toggle.closest('.fd-menu')) m.removeAttribute('data-open'); });
    if (toggle) {
      var menu = toggle.closest('.fd-menu');
      if (menu.hasAttribute('data-open')) menu.removeAttribute('data-open'); else menu.setAttribute('data-open', '');
      toggle.setAttribute('aria-expanded', menu.hasAttribute('data-open') ? 'true' : 'false');
      return;
    }
    var sheetToggle = event.target.closest('[data-sheet-toggle]');
    var sheet = document.querySelector('.fd-sheet');
    if (sheetToggle && sheet) {
      var open = !sheet.hasAttribute('data-open');
      if (open) sheet.setAttribute('data-open', ''); else sheet.removeAttribute('data-open');
      sheetToggle.toggleAttribute('data-active', open);
      document.querySelectorAll('.fd-tabbar a[data-current]').forEach(function (a) { a.toggleAttribute('data-active', !open); });
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      document.querySelectorAll('.fd-menu[data-open]').forEach(function (m) { m.removeAttribute('data-open'); });
      var sheet = document.querySelector('.fd-sheet[data-open]');
      if (sheet) sheet.removeAttribute('data-open');
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      var input = document.getElementById('fdSearch');
      if (input && input.offsetParent) { event.preventDefault(); input.focus(); input.select(); }
    }
  });
  if (media && media.addEventListener) media.addEventListener('change', function () { if (get('theme') === 'auto') applyLook(); });

  // Page search (like Fleetdeck's Spotlight), in both menu placements: matches
  // page names, menu groups and keywords (every word must match). Arrow keys
  // choose, Enter opens. On the phone the search button opens the field.
  var search = document.getElementById('fdSearch');
  if (search) {
    var root = document.documentElement;
    var drop = document.getElementById('fdSearchResults');
    var none = drop.querySelector('.fd-search-none');
    var links = Array.prototype.slice.call(drop.querySelectorAll('a'));
    var hits = [], cur = 0;
    var mark = function (i) {
      cur = hits.length ? (i + hits.length) % hits.length : 0;
      links.forEach(function (a) { a.removeAttribute('data-hit'); a.setAttribute('aria-selected', 'false'); });
      if (hits[cur]) { hits[cur].setAttribute('data-hit', ''); hits[cur].setAttribute('aria-selected', 'true'); if (hits[cur].scrollIntoView) hits[cur].scrollIntoView({ block: 'nearest' }); }
    };
    var refresh = function () {
      var words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      hits = links.filter(function (a) {
        var hay = (a.textContent + ' ' + (a.getAttribute('data-keywords') || '')).toLowerCase();
        return words.every(function (w) { return hay.indexOf(w) !== -1; });
      });
      links.forEach(function (a) { a.hidden = hits.indexOf(a) === -1; });
      if (none) none.hidden = hits.length > 0;
      drop.hidden = false;  // an empty field lists every page (like Spotlight)
      search.setAttribute('aria-expanded', 'true');
      mark(0);
    };
    var closeSearch = function () {
      drop.hidden = true;
      search.setAttribute('aria-expanded', 'false');
      root.classList.toggle('search-open', false);
      document.querySelectorAll('[data-search-open]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); b.removeAttribute('data-active'); });
    };
    search.addEventListener('focus', refresh);
    search.addEventListener('input', refresh);
    search.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); mark(cur + 1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); mark(cur - 1); }
      else if (event.key === 'Enter' && hits[cur]) { event.preventDefault(); location.href = hits[cur].href; }
      else if (event.key === 'Escape') { closeSearch(); search.blur(); }
    });
    search.addEventListener('blur', function () { setTimeout(closeSearch, 150); });
    document.querySelectorAll('[data-search-open]').forEach(function (b) {
      // mousedown: keep the field open (its blur would close it before the click).
      b.addEventListener('mousedown', function (event) { if (root.classList.contains('search-open')) event.preventDefault(); });
      b.addEventListener('click', function () {
        if (root.classList.contains('search-open')) { closeSearch(); search.blur(); return; }
        root.classList.toggle('search-open', true);
        b.setAttribute('aria-expanded', 'true'); b.setAttribute('data-active', '');
        search.focus();
      });
    });
  }

  // Tabs (Mantine Tabs) – the last chosen tab is remembered while the browser tab is open.
  document.querySelectorAll('[data-tabs]').forEach(function (bar) {
    var name = 'kw-tab:' + bar.getAttribute('data-tabs');
    var buttons = Array.prototype.slice.call(bar.querySelectorAll('[role=tab]'));
    var select = function (id, remember) {
      buttons.forEach(function (b) {
        var on = b.getAttribute('aria-controls') === id;
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        var panel = document.getElementById(b.getAttribute('aria-controls'));
        if (panel) panel.hidden = !on;
      });
      if (remember) { try { sessionStorage.setItem(name, id); } catch (_) {} }
    };
    buttons.forEach(function (b) { b.addEventListener('click', function () { select(b.getAttribute('aria-controls'), true); }); });
    var start = (location.hash || '').slice(1);
    if (!document.getElementById(start) || !bar.querySelector('[aria-controls="' + start + '"]')) {
      try { start = sessionStorage.getItem(name) || ''; } catch (_) { start = ''; }
    }
    if (!bar.querySelector('[aria-controls="' + start + '"]')) start = buttons[0].getAttribute('aria-controls');
    select(start, false);
  });

  applyLook();
})();
"""

ICONS = {
    "layout-dashboard": "<path d=\"M5 4h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1\"/><path d=\"M5 16h4a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-2a1 1 0 0 1 1 -1\"/><path d=\"M15 12h4a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-6a1 1 0 0 1 1 -1\"/><path d=\"M15 4h4a1 1 0 0 1 1 1v2a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1v-2a1 1 0 0 1 1 -1\"/>",
    "device-tv": "<path d=\"M3 9a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2l0 -9\"/><path d=\"M16 3l-4 4l-4 -4\"/>",
    "pointer": "<path d=\"M7.904 17.563a1.2 1.2 0 0 0 2.228 .308l2.09 -3.093l4.907 4.907a1.067 1.067 0 0 0 1.509 0l1.047 -1.047a1.067 1.067 0 0 0 0 -1.509l-4.907 -4.907l3.113 -2.09a1.2 1.2 0 0 0 -.309 -2.228l-13.582 -3.904l3.904 13.563\"/>",
    "plug": "<path d=\"M9.785 6l8.215 8.215l-2.054 2.054a5.81 5.81 0 1 1 -8.215 -8.215l2.054 -2.054\"/><path d=\"M4 20l3.5 -3.5\"/><path d=\"M15 4l-3.5 3.5\"/><path d=\"M20 9l-3.5 3.5\"/>",
    "download": "<path d=\"M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2\"/><path d=\"M7 11l5 5l5 -5\"/><path d=\"M12 4l0 12\"/>",
    "settings": "<path d=\"M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065\"/><path d=\"M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0\"/>",
    "logout": "<path d=\"M14 8v-2a2 2 0 0 0 -2 -2h-7a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h7a2 2 0 0 0 2 -2v-2\"/><path d=\"M9 12h12l-3 -3\"/><path d=\"M18 15l3 -3\"/>",
    "user": "<path d=\"M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0\"/><path d=\"M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2\"/>",
    "palette": "<path d=\"M12 21a9 9 0 0 1 0 -18c4.97 0 9 3.582 9 8c0 1.06 -.474 2.078 -1.318 2.828c-.844 .75 -1.989 1.172 -3.182 1.172h-2.5a2 2 0 0 0 -1 3.75a1.3 1.3 0 0 1 -1 2.25\"/><path d=\"M7.5 10.5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/><path d=\"M11.5 7.5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/><path d=\"M15.5 10.5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/>",
    "sun": "<path d=\"M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0\"/><path d=\"M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7\"/>",
    "moon": "<path d=\"M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454l0 .008\"/>",
    "sun-moon": "<path d=\"M9.173 14.83a4 4 0 1 1 5.657 -5.657\"/><path d=\"M11.294 12.707l.174 .247a7.5 7.5 0 0 0 8.845 2.492a9 9 0 0 1 -14.671 2.914\"/><path d=\"M3 12h1\"/><path d=\"M12 3v1\"/><path d=\"M5.6 5.6l.7 .7\"/><path d=\"M3 21l18 -18\"/>",
    "check": "<path d=\"M5 12l5 5l10 -10\"/>",
    "search": "<path d=\"M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0\"/><path d=\"M21 21l-6 -6\"/>",
    "chevron-down": "<path d=\"M6 9l6 6l6 -6\"/>",
    "dots": "<path d=\"M4 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/><path d=\"M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/><path d=\"M18 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/>",
    "x": "<path d=\"M18 6l-12 12\"/><path d=\"M6 6l12 12\"/>",
    "bell": "<path d=\"M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6\"/><path d=\"M9 17v1a3 3 0 0 0 6 0v-1\"/>",
    "world": "<path d=\"M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0\"/><path d=\"M3.6 9h16.8\"/><path d=\"M3.6 15h16.8\"/><path d=\"M11.5 3a17 17 0 0 0 0 18\"/><path d=\"M12.5 3a17 17 0 0 1 0 18\"/>",
    "clock": "<path d=\"M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0\"/><path d=\"M12 7v5l3 3\"/>",
    "cpu": "<path d=\"M5 6a1 1 0 0 1 1 -1h12a1 1 0 0 1 1 1v12a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1l0 -12\"/><path d=\"M9 9h6v6h-6l0 -6\"/><path d=\"M3 10h2\"/><path d=\"M3 14h2\"/><path d=\"M10 3v2\"/><path d=\"M14 3v2\"/><path d=\"M21 10h-2\"/><path d=\"M21 14h-2\"/><path d=\"M14 21v-2\"/><path d=\"M10 21v-2\"/>",
    "box": "<path d=\"M12 3l8 4.5l0 9l-8 4.5l-8 -4.5l0 -9l8 -4.5\"/><path d=\"M12 12l8 -4.5\"/><path d=\"M12 12l0 9\"/><path d=\"M12 12l-8 -4.5\"/>",
    "package": "<path d=\"M12 3l8 4.5l0 9l-8 4.5l-8 -4.5l0 -9l8 -4.5\"/><path d=\"M12 12l8 -4.5\"/><path d=\"M12 12l0 9\"/><path d=\"M12 12l-8 -4.5\"/><path d=\"M16 5.25l-8 4.5\"/>",
    "temperature": "<path d=\"M10 13.5a4 4 0 1 0 4 0v-8.5a2 2 0 0 0 -4 0v8.5\"/><path d=\"M10 9l4 0\"/>",
    "bolt": "<path d=\"M13 3l0 7l6 0l-8 11l0 -7l-6 0l8 -11\"/>",
    "activity": "<path d=\"M3 12h4l3 8l4 -16l3 8h4\"/>",
    "gauge": "<path d=\"M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0\"/><path d=\"M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0\"/><path d=\"M13.41 10.59l2.59 -2.59\"/><path d=\"M7 12a5 5 0 0 1 5 -5\"/>",
    "wifi": "<path d=\"M12 18l.01 0\"/><path d=\"M9.172 15.172a4 4 0 0 1 5.656 0\"/><path d=\"M6.343 12.343a8 8 0 0 1 11.314 0\"/><path d=\"M3.515 9.515c4.686 -4.687 12.284 -4.687 17 0\"/>",
    "device-desktop": "<path d=\"M3 5a1 1 0 0 1 1 -1h16a1 1 0 0 1 1 1v10a1 1 0 0 1 -1 1h-16a1 1 0 0 1 -1 -1v-10\"/><path d=\"M7 20h10\"/><path d=\"M9 16v4\"/><path d=\"M15 16v4\"/>",
    "info-circle": "<path d=\"M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0\"/><path d=\"M12 9h.01\"/><path d=\"M11 12h1v4h1\"/>",
    "shield-check": "<path d=\"M11.46 20.846a12 12 0 0 1 -7.96 -14.846a12 12 0 0 0 8.5 -3a12 12 0 0 0 8.5 3a12 12 0 0 1 -.09 7.06\"/><path d=\"M15 19l2 2l4 -4\"/>",
    "refresh": "<path d=\"M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4\"/><path d=\"M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4\"/>",
    "player-play": "<path d=\"M7 4v16l13 -8l-13 -8\"/>",
    "tool": "<path d=\"M7 10h3v-3l-3.5 -3.5a6 6 0 0 1 8 8l6 6a2 2 0 0 1 -3 3l-6 -6a6 6 0 0 1 -8 -8l3.5 3.5\"/>",
    "trash": "<path d=\"M4 7l16 0\"/><path d=\"M10 11l0 6\"/><path d=\"M14 11l0 6\"/><path d=\"M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12\"/><path d=\"M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3\"/>",
    "plus": "<path d=\"M12 5l0 14\"/><path d=\"M5 12l14 0\"/>",
    "power": "<path d=\"M7 6a7.75 7.75 0 1 0 10 0\"/><path d=\"M12 4l0 8\"/>",
    "layout-sidebar": "<path d=\"M4 6a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2l0 -12\"/><path d=\"M9 4l0 16\"/>",
    "layout-navbar": "<path d=\"M4 6a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2l0 -12\"/><path d=\"M4 9l16 0\"/>",
    "maximize": "<path d=\"M4 8v-2a2 2 0 0 1 2 -2h2\"/><path d=\"M4 16v2a2 2 0 0 0 2 2h2\"/><path d=\"M16 4h2a2 2 0 0 1 2 2v2\"/><path d=\"M16 20h2a2 2 0 0 0 2 -2v-2\"/>",
    "player-stop": "<path d=\"M5 7a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2l0 -10\"/>",
    "external-link": "<path d=\"M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6\"/><path d=\"M11 13l9 -9\"/><path d=\"M15 4h5v5\"/>",
    "first-aid-kit": "<path d=\"M8 8v-2a2 2 0 0 1 2 -2h4a2 2 0 0 1 2 2v2\"/><path d=\"M4 10a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2l0 -8\"/><path d=\"M10 14h4\"/><path d=\"M12 12v4\"/>",
    "flask": "<path d=\"M9 3l6 0\"/><path d=\"M10 9l4 0\"/><path d=\"M10 3v6l-4 11a.7 .7 0 0 0 .5 1h11a.7 .7 0 0 0 .5 -1l-4 -11v-6\"/>",
    "zoom-scan": "<path d=\"M8 11a3 3 0 1 0 6 0a3 3 0 0 0 -6 0\"/><path d=\"M16 16l-2.5 -2.5\"/><path d=\"M3 7v-2a2 2 0 0 1 2 -2h2\"/><path d=\"M3 17v2a2 2 0 0 0 2 2h2\"/><path d=\"M17 3h2a2 2 0 0 1 2 2v2\"/><path d=\"M17 21h2a2 2 0 0 0 2 -2v-2\"/>",
    "device-floppy": "<path d=\"M6 4h10l4 4v10a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2\"/><path d=\"M10 14a2 2 0 1 0 4 0a2 2 0 1 0 -4 0\"/><path d=\"M14 4l0 4l-6 0l0 -4\"/>",
    "archive": "<path d=\"M3 6a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2\"/><path d=\"M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-10\"/><path d=\"M10 12l4 0\"/>",
    "rotate-clockwise": "<path d=\"M4.05 11a8 8 0 1 1 .5 4m-.5 5v-5h5\"/>",
    "arrow-back-up": "<path d=\"M9 14l-4 -4l4 -4\"/><path d=\"M5 10h11a4 4 0 1 1 0 8h-1\"/>",
    "history": "<path d=\"M12 8l0 4l2 2\"/><path d=\"M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5\"/>",
    "key": "<path d=\"M16.555 3.843l3.602 3.602a2.877 2.877 0 0 1 0 4.069l-2.643 2.643a2.877 2.877 0 0 1 -4.069 0l-.301 -.301l-6.558 6.558a2 2 0 0 1 -1.239 .578l-.175 .008h-1.172a1 1 0 0 1 -.993 -.883l-.007 -.117v-1.172a2 2 0 0 1 .467 -1.284l.119 -.13l.414 -.414h2v-2h2v-2l2.144 -2.144l-.301 -.301a2.877 2.877 0 0 1 0 -4.069l2.643 -2.643a2.877 2.877 0 0 1 4.069 0\"/><path d=\"M15 9h.01\"/>",
    "lock": "<path d=\"M5 13a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v6a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2v-6\"/><path d=\"M11 16a1 1 0 1 0 2 0a1 1 0 0 0 -2 0\"/><path d=\"M8 11v-4a4 4 0 1 1 8 0v4\"/>",
    "alert-triangle": "<path d=\"M12 9v4\"/><path d=\"M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0\"/><path d=\"M12 16h.01\"/>",
    "circle-check": "<path d=\"M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0\"/><path d=\"M9 12l2 2l4 -4\"/>"
}

INTER_WOFF2 = base64.b64decode(
    "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"
    "uGdN/5f//SfeeMpfT/X3Uw09TcNzLj9vZOd05hWevDL5TdRvc+gdit6j7H0aPnT240o/rehLcr4u7XsyfiLrp/J+KvlnKn+m/udy"
    "fyH9d1q3ZBVmB8xNmF/AG+CeAM8eoHpf+G0DFgID6ElbuK5J61T1pV1ZfUVf27tGv8gIgzO+/PBoKDAWnShMvhHJTGdmyEPqw+nD"
    "hSOKuP5o5xh3fChZPDmZmW4/vx38cva3p/786e9/8Ieb27/8x8/86eaOz/7tt/+AbI3din+BMxP/+e3/7jj4r5sPHf7erbd2XX/k"
    "jiP3HDtwfNfx60/sObH35N2n95zZc/bA+V88evaxW67e2P33Z3t7f/18foT9W/uPD/ztxb+/lIntsWIKE29qJABQTPCfnaXqGTNG"
    "Z+UfQ9myDsd2LM6tbRfiH30dsQLg0Q+JFSGmjz3ufsmqjbnjof3Q7kgqLvxNH94/PfCDz/NbL8YCq3P23YFXqQOMr6ceVg9r8r0L"
    "ejO4L/AAF+/YLW5psOEK2Frywa0Btv98vRr0+oD5LochsAGHL6386O1PDJwKfuh3lbYEFnjsfVNVyRLA+/8UyUngEbnSKUVbZSk/"
    "HkJsVHgI0swAAUHQBVvbQ9/5G9d33vql79zVpJ5jGCYaSNI0u/SdxTN8Zh3Ye0arDglG0yLoMs1J3wPu/vXHx14uDPi2ryefv5ns"
    "WJZOlmozXo8HlcofpbVrkT7h/cE8Q5HNTmLsZHPWidW+0IVtMoqmxppHjV4A5iZwk7hZOC3HcibOxuVxUa7C+uRKk/Gplc+skueY"
    "hgQswJGbEpUxyer9YoD9gKIo7qdm5miOWXqIKwIDv1PYc+jBxn9DX+SHex2PX9hJI2kgzwE+/unjabbuxy4vpC8cH82dIz6a/9G8"
    "D9fI1vjqDVd//C7aDS3vdWyi0GseOJy9XtHF/fZ1/RIw+tXPFVrxQsWoGofd4noe60sheqcfyVuLRIgc5LkmCubRN5BZavfDBt+N"
    "U02sqeRDPreE4s7o7OY+/Ij0YGyRCl2jaCjAW8aYsUuz5yh8qlKZNi84Tk+nsde96pDzXlfhMyelZBR94einn8KlzwRNQ0vHw8vH"
    "VW8eqvjwNdusVHlZYaVV/pDgP0/tkiJVhp3Sqe1ToNB++U446ZRjfqp3i1ajm270rxq0eeOtl7rt1WWxOwPg3V089IywVELPhhdF"
    "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"
)


def icon(name, cls=""):
    """Inline Tabler icon as SVG (16 px by default, styled by svg.i)."""
    extra = f" {cls}" if cls else ""
    return f'<svg class="i{extra}" viewBox="0 0 24 24" aria-hidden="true">{ICONS.get(name, "")}</svg>'
