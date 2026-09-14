# Changelog

## v1.18.28 — 2026-09-14

- Fix System saves incorrectly requiring MQTT port and stats fields that live on the separate Connections page.
- Add a regression test proving System settings can be saved without any MQTT form fields.

## v1.18.27 — 2026-09-14

- Run the legacy screenshot cleanup from the freshly installed discovery script, so a kiosk upgrading with an older in-memory updater removes the old script and files on its first update.
- Includes the screenshot-free wake/self-test and exact wake-stage diagnostics from v1.18.26.

## v1.18.26 — 2026-09-14

- Remove screenshot capture, storage, WebUI controls and MQTT entities; remote control is the supported visual inspection path.
- Verify wake from Chrome's document, renderer and layout state while the physical panel remains off, avoiding false blank-screen failures on internal laptop displays.
- Record the exact failed wake stage in diagnostics instead of the generic `state/recovery failed` result.

## v1.18.25 — 2026-09-14

- Verify wake from Chrome's rendered surface while the physical panel remains off, avoiding false blank-screen failures on internal laptop displays.
- Record the exact failed wake stage in diagnostics instead of the generic `state/recovery failed` result.
- Keep the desktop screenshot as a compatibility fallback for older/non-CDP browser setups.

## v1.18.24 — 2026-09-14

- **Stops the Chrome restart storm found on Cinnamon kiosks.** GNOME's power
  daemon is touched only in a confirmed GNOME session, and both commands are
  bounded so they cannot hold Chrome startup indefinitely.
- **Watchdog and health recovery now allow a 45-second startup grace.** They
  no longer restart Chrome while its service has just started or Warden is in
  a legitimate transition, preventing overlapping recovery loops.
- Includes exact-tag recovery, non-destructive update acceptance, and the
  persistent signed-login fix from the preceding releases.

## v1.18.23 — 2026-09-14

- **Remote recovery can pin an exact immutable release.** A validated
  `KIOSK_WARDEN_FORCE_TAG` bypasses stale Beta API/Atom discovery, so a kiosk
  stuck on an older updater cannot accidentally reinstall the rollback-prone
  release while being repaired.
- Includes v1.18.22's non-destructive post-install acceptance and the
  persistent signed-login fix.

## v1.18.22 — 2026-09-14

- **Post-install checks can no longer downgrade a kiosk to an old snapshot.**
  Release acceptance is limited to the installed version, the WebUI service,
  and its installed server file. Hardware, MQTT, port, renderer, and display
  differences remain diagnostics instead of rollback conditions.
- **A failed post-check is explicit and non-destructive.** The update reaches
  100 percent, keeps the newly installed release, and records the exact failed
  essential check for troubleshooting. Rollback remains available manually.
- **The persistent 30-day signed login session remains included.** Installing
  this release directly also upgrades kiosks that were repeatedly returned to
  v1.18.12 before the login fix could remain installed.

## v1.18.21 — 2026-09-14

- **Updates no longer force the physical screen through OFF→ON at 95%.** The
  acceptance step verifies the installed version, six core services, Chrome,
  port ownership, and the already requested screen state without changing it.
- **An ON kiosk still gets strict dashboard verification.** An OFF kiosk is
  accepted only when Warden also reports OFF; neither path changes presence or
  power state. The disruptive full OFF→ON cycle remains available as a manual
  diagnostic test.
- **Faster and clearer completion.** Runtime acceptance retries for up to 60
  seconds and reports a runtime failure, rather than sitting at 95 percent in
  a nested physical wake test.

## v1.18.20 — 2026-09-14

- **Beta updates survive GitHub API rate limits.** When GitHub's anonymous API
  returns 403, Beta discovery now reads the newest immutable release tag from
  the public releases Atom feed instead of stopping at 5 percent.
- **Includes bounded wake verification from v1.18.19.** Slower hardware gets a
  short retry window while the same renderer, layout, screenshot, and display
  checks remain mandatory before an update is accepted.
- **Includes isolated VNC close from v1.18.18.** Viewer expiry stops only VNC
  services and preserves Warden, Chrome, renderer, and screen state.

## v1.18.19 — 2026-09-14

- **Do not reject a slow but healthy wake.** Dashboard, renderer, and screenshot
  verification now retry for a bounded period before staged recovery or
  rollback. This accommodates slower monitors and kiosk hardware without
  weakening the final acceptance criteria.
- **Includes the isolated VNC close from v1.18.18.** Closing a remote viewer
  stops only VNC/noVNC after its heartbeat lease expires and never issues a
  kiosk, Chrome, renderer, or screen-state command.

## v1.18.18 — 2026-09-14

- **Closing VNC cannot trigger kiosk lifecycle actions.** Browser unload no
  longer sends duplicate stop requests. The existing heartbeat lease expires
  after five seconds and then stops only `kiosk-novnc.service` and
  `kiosk-vnc.service`.
- **Preserve the kiosk and screen state.** Regression coverage proves the VNC
  stop path contains no Warden state, Chrome, renderer, or screen command, so
  an ON kiosk remains ON and an OFF kiosk remains OFF.
- **Remove the VNC startup race.** The heartbeat lease is established before
  systemd starts VNC, and a normal stop clears stale failure markers belonging
  only to the VNC units.

## v1.18.17 — 2026-09-14

- **VNC has no separate password workflow.** Fresh installs no longer ask for,
  generate, or describe a second VNC password, and the obsolete WebUI handler
  for changing it has been removed. VNC continues to derive its credential
  automatically from the Kiosk Warden administrator login before each start.
- **Readable touch calibration.** The normal 3×3 identity matrix is displayed
  as Standard and a transformed matrix as Custom; raw matrix data remains
  available through diagnostics instead of overflowing the status tile.
- **Explain missing input timing.** If `xprintidle` is absent, Latest input now
  says so explicitly rather than showing the ambiguous Unknown state.

## v1.18.16 — 2026-09-14

- **Test Connections without guessing.** Connections now has dedicated MQTT
  and Home Assistant test actions. MQTT performs a real authenticated publish;
  HA uses the saved URL and token and reports when it is not configured.
- **Protect every authenticated write.** Forms, background actions, VNC
  heartbeats, and close beacons carry an HMAC-bound CSRF token. Missing or
  altered tokens are rejected without running the requested action.
- **Harden the local WebUI.** HTML and JSON responses include restrictive
  browser security headers, and request bodies larger than 1 MiB are rejected
  before parsing.

## v1.18.15 — 2026-09-14

- **Complete the primary English WebUI.** Operational labels, explanations,
  profile actions, remote-control states, connection details, and System
  controls no longer fall back to Danish when English is selected.
- **Explain why touch-to-wake is unavailable.** Capability detection now
  distinguishes a disconnected touch device, a missing event device, missing
  `evtest`, insufficient permissions, and a ready input guardian instead of
  showing the same generic unavailable state for every cause.
- **Align setup guidance with the new navigation.** Installer messages now
  direct users to System and Connections rather than the retired Settings tab.

## v1.18.14 — 2026-09-14

- **Clearer WebUI navigation in Danish and English.** The six areas are now
  Status, Kiosk, Remote Control, Connections, Updates, and System, and every
  page starts with a short description plus the active kiosk name.
- **Connections are grouped together.** The optional Home Assistant setup now
  lives beside MQTT under Connections instead of being mixed into System.
- **Profile zoom selector fixed.** An existing template typo no longer inserts
  visible apostrophes between zoom choices.

## v1.18.13 — 2026-09-14

- **Remembered login now survives WebUI restarts and updates.** Session cookies
  are self-contained and HMAC-signed with the persisted administrator password
  hash instead of depending on an in-memory token table that disappeared every
  time `kiosk-webui.service` restarted.
- **The 30-day option is submitted correctly.** The **Remember me** checkbox is
  now inside the login form and enabled by default. Disabling automatic logout
  also gives the session the remembered duration. Changing the administrator
  password invalidates every previously signed cookie.

## v1.18.12 — 2026-09-14

- **Avoid the white screen on the first VNC start.** The page now waits for the
  VNC and noVNC ports to answer before it points the iframe at the viewer, so
  the first click no longer needs a manual refresh.

## v1.18.11 — 2026-09-14

- **On-demand VNC sessions.** VNC and noVNC are now disabled by default and
  only start when you press **Start VNC**. The same button becomes **Stop VNC**
  while the session is active.
- **VNC closes with the page.** The active page sends a close beacon on
  `pagehide`/`beforeunload` and a short heartbeat timeout stops the services
  if the close beacon is missed.

## v1.18.10 — 2026-09-14

- **Fix black, unresponsive VNC iframe on Remote Control.** The page's inline
  script was a plain (non-f) string, so the embedded VNC password and noVNC
  port were sent to the browser as literal, unevaluated Python placeholder
  text instead of real values. The invalid `port` placeholder was a
  JavaScript syntax error, so the whole script silently failed and the
  iframe's `src` was never set — showing a black, unresponsive box. Direct
  noVNC access (bypassing the iframe) was unaffected, which is why this was
  hard to spot. Fixed by making the block an f-string with the JS braces
  escaped.

## v1.18.9 — 2026-09-14

- **Fix 404 after Start VNC.** The Start VNC action now redirects back to
  Remote Control after restarting the VNC and browser bridge services,
  instead of rendering the page directly as the POST response. Refreshing
  the page after pressing Start VNC previously landed on a 404 because the
  browser replayed the POST-only `/vnc/start` URL.

## v1.18.8 — 2026-09-14

- **Editable MQTT identity.** Kiosk ID and Base topic can now both be changed
  later from Settings. Custom Base topics are preserved, while changing the
  Kiosk ID keeps the optional Codex remote topic aligned with the new ID.

## v1.18.7 — 2026-09-14

- **VNC works with the screen OFF.** x11vnc keeps the X11 framebuffer pollable
  while the monitor is powered down, so remote control no longer requires the
  kiosk display to wake first.
- **Start VNC no longer changes kiosk state.** The explicit Start VNC action
  only restarts the VNC and browser bridge services; it leaves the kiosk's
  current screen state untouched.

## v1.18.6 — 2026-09-14

- **Automatic VNC authentication.** noVNC now derives its access password from
  the Kiosk Warden WebUI login, so remote control no longer asks for a separate
  password. The old VNC password field has been removed.
- **Profile-owned kiosk URL.** The URL/zoom shown by the kiosk is now managed
  only by Kiosk Profiles. Settings shows the active URL read-only, ignores any
  direct URL submission, and MQTT URL changes only take effect when they match
  an existing profile.
- **MQTT profile editing.** Home Assistant can now update the active profile's
  URL and zoom with dedicated entities, and the kiosk navigates to the correct
  URL even when the browser is idle.
- **VNC start button.** Remote Control now has an explicit Start VNC action that
  restarts the VNC and noVNC services before reconnecting.
- **Login keyboard submit.** Pressing Enter on the login page submits the form
  after username and password are entered.
- **Configurable WebUI sessions.** Login can remember the user for 30 days, and
  Settings can turn automatic sign-out after 12 hours on or off.
- **Profiles are the only display source.** The remaining URL field is removed
  from Settings. Control now shows the active profile's URL, and every profile
  has an editable URL and zoom.
- **Dedicated MQTT page.** Broker address, credentials, discovery and stats
  timing now live on a separate MQTT tab instead of the general Settings page.

## v1.18.0 — 2026-09-14

- **Session-based WebUI login.** The Basic Auth prompt is replaced by a real
  first-run administrator setup and an expiring `HttpOnly` session cookie.
  Existing installations keep their password and migrate to the `admin`
  username automatically.
- **Platform capability probing.** Warden detects usable X11/Wayland, sysfs/
  DDC/CEC display control, touch-event access, ambient-light sensors, battery
  telemetry, audio input/output, and capture tools without changing hardware.
  MQTT entities are published only for proven capabilities.
- **Capability-gated hardware control.** Brightness and microphone controls
  exist only when their backend and current permissions work. Optional
  adaptive brightness is opt-in and bounded by configured minimum/maximum
  values.
- **Safe touch-to-wake.** While the screen is OFF, a supported touch input is
  briefly grabbed so the wake gesture cannot pass through to the dashboard.
  Input is released after a configured delay and only after a verified wake.
- **Named kiosk profiles.** Control pages and MQTT can switch between named
  URL/zoom profiles. If the primary dashboard is unreachable, Warden shows a
  local offline page and returns automatically when the primary URL recovers.
- **Portable display and low-resolution support.** `wlopm` and KDE Wayland
  DPMS backends are available alongside X11, and Raspberry Pi wake geometry
  thresholds are configurable.
- **Update and diagnostics integration.** New services, capabilities, and
  scripts are installed, enabled, restarted, validated, and included in
  diagnostics. The offline fallback no longer blocks recovery when Chrome is
  dead.

## v1.17.0 — 2026-09-14

- **Deterministic kiosk state machine.** Screen and renderer transitions move
  through `OFF`, `WAKING`, `ON`, `SLEEPING`, and `RECOVERING` under one lock.
- **Verified wake and staged recovery.** Warden verifies display geometry, the
  expected page, renderer/layout, and a non-blank screenshot before exposing
  the monitor. Recovery escalates from resize and renderer resume to reload,
  and only then restarts Chrome.
- **Portable display backends.** GNOME/X11, Cinnamon/X11, generic X11,
  Raspberry Pi, DDC/CI, and HDMI-CEC are isolated behind a backend interface.
- **OFF→ON acceptance and automatic rollback.** Updates must pass a timed test
  of DPMS, resolution, renderer, screenshot, ports, and wake time or the
  pre-update snapshot is restored.
- **Safe browser cleanup and diagnostics.** Only orphaned processes with the
  dedicated Warden Chrome profile are closed. The WebUI creates a sanitized
  diagnostics ZIP with services, logs, display, touch/input, Chrome, renderer,
  ports and version data, without including `kiosk.conf`.
- **All local ports conflict-checked.** WebUI, VNC, and noVNC ports are
  configurable, range-checked, unique, and tested for active listeners.

## v1.16.4 — 2026-09-14

- **Change the WebUI port later from Settings.** The port is validated against
  the allowed range and active listeners before it is saved. Warden completes
  the current response, restarts only the WebUI through a delayed independent
  systemd scope and automatically redirects the browser to the new address.
- **Safe failure handling.** If the delayed restart cannot be scheduled, the
  previous port is restored in `kiosk.conf` and the WebUI remains reachable.

## v1.16.3 — 2026-09-14

- **Conflict-safe WebUI port during installation.** Installations now validate
  the configured WebUI port, detect an existing TCP listener and ask for an
  alternative instead of silently starting a failed service on port 8080.
  Non-interactive installs can set `KIOSK_WEBUI_PORT`; occupied or invalid
  values stop with an actionable error.
- **The selected port is used everywhere.** It is persisted in `kiosk.conf`,
  loaded by the WebUI systemd service and used for the firewall rule, desktop
  shortcut and final access URLs.

## v1.16.2 — 2026-09-14

- **Stable Smartdash geometry across presence sleep.** Screen-off no longer
  disables the X11 output with `xrandr --off`, which collapsed the logical
  desktop from 1920x1080 to 320x200 and could leave responsive dashboard cards
  measured for the tiny fallback viewport after wake. DPMS still powers down
  the physical monitor while Smartdash pauses cameras and animations.
- **Safe recovery from v1.16.1 OFF state.** Screen-on restores the configured
  output mode and waits for a full kiosk-sized viewport before resuming
  Smartdash rendering and exposing the monitor.

## v1.16.1 — 2026-09-13

- **Fix: screen_off did not actually power down GNOME kiosks.** On GNOME
  desktops, gsd-power (GNOME's own power daemon) was resetting DPMS state
  back to on within about a minute of a manual force-off, so the screen
  visually looked idle (Smartdash paused/blanked its own content) but the
  physical monitor never powered down - a real burn-in risk overnight.
  start-kiosk.sh now masks and stops gsd-power on GNOME kiosks at startup
  (no-op elsewhere). screen_off()/screen_on() also now disable/restore the
  X output directly via xrandr as a second, independent layer, in case DPMS
  alone still gets overridden by some other desktop component in the future.

## v1.16.0 — 2026-09-13

- **Clear HA Smartdash-only scope.** Control now states that Warden can pause
  animations, live cameras and rendering only when the kiosk shows HA
  Smartdash. Physical DPMS screen control still works with other dashboards,
  but their internal visual work cannot be paused by this bridge.
- **Home Assistant MQTT control.** MQTT discovery adds `Smartdash Connection`
  as a diagnostic connectivity entity with retained capability/build/state
  attributes, plus an available-only `Smartdash Rendering` switch. Turning it
  on sends `active`; turning it off sends `idle` through the same local Chrome
  bridge used by automatic screen control.
- **Live retained state.** Warden republishes Smartdash support, state, build,
  release, URL and errors every 15 seconds and after automatic or HA-requested
  state changes. Unsupported dashboards make the switch unavailable.
- **Discovery after self-update.** New MQTT entities are registered during the
  update without requiring a reinstall or shell access.

## v1.15.2 — 2026-09-13

- **Update progress no longer freezes at 20%.** Submitting an update redirects
  to a fresh Updates page. That navigation discarded the polling timer from
  the submitting page, while the fresh page only read status once — commonly
  during the 20% download stage — even though the isolated updater continued
  through validation, backup, installation and restart. A page that initially
  reads a running update now resumes polling every 800 ms until it receives a
  completed or failed status.
- **No duplicate polling timer.** The submit path and redirected-page recovery
  share one guarded polling starter, so a single page cannot accidentally run
  multiple progress loops.

## v1.15.1 — 2026-09-13

- **Fix: Smartdash auto-detection silently missing python3-websocket.**
  `self-update.sh` only ever replaced script/webui files - it never re-ran
  the apt package list from `install.sh`, so kiosks provisioned before
  `python3-websocket` was added there (needed for Smartdash's local Chrome
  debug-port check) could self-update forever without ever getting it,
  always showing "Not detected" with no explanation. `self-update.sh` now
  best-effort installs it during every update if missing (never blocks the
  release install if apt/sudo isn't available non-interactively).
- **Better Smartdash error reporting.** `chrome-lifecycle.py` now writes a
  specific `error`/`error_message` to `smartdash_status.json` when it can't
  run at all - missing `python3-websocket`, Chrome's debug port (9222) not
  responding, or no visible page found - instead of leaving the status file
  untouched. Styring's Smartdash-forbindelse panel and its "Kontroller igen"
  button now show that specific reason instead of a generic "Ikke
  registreret" for all three cases.
- **Clarified: Smartdash-forbindelse is HA Smartdash-specific.** The panel
  now states plainly that this only applies to kiosks running HA Smartdash -
  other dashboards will naturally always show "Ikke registreret" here, which
  is expected, not a bug.

## v1.15.0 — 2026-09-13

- **Optional Home Assistant connection**: a new "Home Assistant" section under
  Indstillinger lets Warden read a sensor's state back from HA using a
  Long-Lived Access Token, with a guided link straight to HA's token screen
  and a live "Test forbindelse" check. The sensor to track is chosen from a
  real dropdown of HA's own power/energy entities — never a free-text
  entity_id to guess.
- **Power on the Overview page**: when a Home Assistant connection and sensor
  are configured, Oversigt gains an "Effekt" tile and a fifth telemetry chart
  alongside CPU/RAM/GPU, temperature, frequency and network — reusing the
  same 6-hour rolling telemetry buffer, no new dependency.
- **Relayed back into Home Assistant**: the same reading is also published as
  a `PC Power` sensor under this Kiosk Warden device via MQTT discovery, so
  it groups with the machine's other diagnostics in HA. Entirely inert for
  installs that never configure the connection - no extra network calls, no
  empty entity left behind.

## v1.14.0 — 2026-09-13

- **Visible automatic Smartdash link**: Control now shows whether HA Smartdash was detected, its active/idle state and build, with an on-demand refresh action.
- **Capability handshake**: Warden queries the active page and applies power state directly when Smartdash exposes its power API; no MQTT credentials, extra IP or manual pairing is required.

## v1.13.0 — 2026-09-13

- **Smartdash-aware idle mode**: screen-off sends a lightweight `idle` event to the current web page, allowing compatible dashboards to pause animations and close live camera sessions without stopping or freezing Chrome.
- **Immediate wake response**: screen-on sends `active` before waking HDMI, so Smartdash can reconnect visible cameras while the monitor warms up.
- **Safe compatibility**: ordinary web pages ignore the event, repeated screen commands preserve the Chrome process, and a kiosk restarted while OFF receives the idle state as soon as its page is ready.

## v1.12.10 — 2026-09-13

- **Mint/Cinnamon HDMI wake**: DPMS is enabled before `force on`, then automatic timeouts are set to zero without `xset -dpms`, preventing Cinnamon from leaving an external HDMI monitor physically off.
- **Invisible visual health checks**: ImageMagick `import -window root` is preferred over the flashing `gnome-screenshot` capture path.
- **Crash-free temporary cleanup**: grey-surface checks explicitly remove their temporary image and no longer retain a `RETURN` trap that can reference an out-of-scope local variable under `set -u`.

## v1.12.9 — 2026-09-13

- **Visual grey-screen watchdog**: while the display is logically ON, health checks inspect the actual X11 surface and detect a blank or solid-grey frame even when Chrome's process, title and URL look healthy.
- **Automatic visual recovery**: the existing staged recovery first reloads and then restarts Chrome if the unusable surface persists.

## v1.12.8 — 2026-09-13

- **Stable presence wake**: repeated `screen_on` commands are idempotent and preserve the Chrome PID whenever Chrome and its HTTP page are healthy.
- **No renderer freezing by default**: screen-off now uses monitor DPMS only and keeps Smartdash paintable, preventing grey screens after physical or automated wake.
- **Targeted recovery only**: `screen_on` restarts Chrome only when the process or dashboard page is genuinely missing or unhealthy.

## v1.12.7 — 2026-09-13

- **Truthful completed status**: stale success messages from an older installed version are automatically hidden instead of remaining at 100% indefinitely.
- **Clearly disabled update action**: when installed and latest versions match, the install button is both functionally disabled and visually muted.

## v1.12.6 — 2026-09-13

- **Faster timed presence wake**: Warden holds DPMS off against Chrome's own X11 window activity, then starts monitor warm-up as soon as the dashboard HTTP page exists, overlapping the final rendering phase without exposing the desktop.
- **Fresh fallback discovery**: rate-limit fallback checks bypass GitHub's short-lived latest-release redirect cache, so a newly published Stable version appears immediately.

## v1.12.5 — 2026-09-13

- **Rate-limit-safe Stable checks**: when GitHub's unauthenticated API quota is exhausted, Warden discovers the current stable tag through GitHub's public latest-release redirect instead of showing a 403 error.
- **No downgrade offers**: the Web UI and overview banner now require a semantically newer version before offering an installation, so stale cached metadata can never present an older release as an update.

## v1.12.4 — 2026-09-13

- **No desktop flash on presence wake**: the monitor now remains physically off while the fresh Chrome renderer starts and is exposed only after the dashboard page is ready.
- **Race-safe hidden startup**: a dedicated wake marker prevents startup recovery and newer screen-off commands from fighting over DPMS state.

## v1.12.3 — 2026-09-13

- **Full low-power presence sleep**: presence-off freezes Chrome rendering and media before DPMS powers down the monitor, avoiding unnecessary background dashboard work.
- **Fresh renderer before wake**: presence-on starts Chrome cleanly behind the powered-off monitor, waits for the dashboard page and only then exposes the display, preventing the former grey wake screen.
- **Bounded DPMS commands**: screen state is published before power-down and X11 power calls cannot block the MQTT control path indefinitely, keeping later presence wake commands responsive.

## v1.12.2 — 2026-09-13

- **Race-free wake during restart**: a delayed OFF-state restore now rechecks the latest requested screen state before touching DPMS, so a simultaneous `screen_on` command always wins.

## v1.12.1 — 2026-09-13

- **Reliable screen wake**: screen power saving now uses DPMS without freezing Chrome's renderer, preventing the kiosk from waking to a solid grey page.
- **Safe OFF-state restore**: restarting Chrome while the screen is off still restores the physical DPMS state without suspending dashboard painting.

## v1.12.0 — 2026-09-13

- **English by default**: every Web UI page, navigation item, control, status, validation message and countdown now uses English on fresh installations.
- **Danish language option**: Settings includes a persistent Interface language selector for switching the complete interface between English and Danish.

## v1.11.0 — 2026-09-13

- **Cross-architecture browser install**: amd64 systems use Google Chrome while ARM systems, including Raspberry Pi OS, install Chromium.
- **Portable dependency handling**: core runtime packages are mandatory while distro-specific desktop and telemetry helpers install opportunistically without breaking the whole installation.
- **Raspberry Pi OS desktop support**: Raspberry Pi installs select the X11/Openbox backend required by Warden's DPMS, xdotool and x11vnc controls; a reboot activates it.
- **Portable VNC and HA identity**: x11vnc discovers the active X authority instead of assuming GDM, and MQTT discovery reports the real hardware model and operating system.

## v1.10.0 — 2026-09-13

- **Telemetry overview**: Overview now shows live CPU, RAM, Intel GPU activity, CPU frequency, CPU/NVMe temperatures and network throughput.
- **Live history graphs**: four lightweight canvas charts retain up to six hours in memory and display the latest hour without page or DOM rebuilds.
- **Low-overhead updates**: telemetry samples every ten seconds, GPU residency every thirty seconds, and redraws existing canvases in place.

## v1.9.2 — 2026-09-13

- **Screenshot on Styring**: the latest kiosk screenshot now appears beside its capture action on the Styring page, while Overview remains a focused status dashboard.

## v1.9.1 — 2026-09-13

- **Clean service restarts**: x11vnc and noVNC now treat their normal termination exit codes as successful, so a deliberate Warden restart no longer leaves transient failed-unit records.

## v1.9.0 — 2026-09-13

- **Dedicated control page**: operational actions have moved from Overview to a new Styring tab, keeping Overview focused on status and diagnostics.
- **Power-profile control**: switch between Strømbesparelse, Balanceret and Ydelse from the web UI or the new Home Assistant MQTT select entity.
- **Warden restart everywhere it belongs**: restart Kiosk Warden from Styring or the new Home Assistant MQTT button, with a five-second web countdown and an independent systemd restart job.

## v1.8.2 — 2026-09-13

- **Visible Warden restart action**: the manual Restart Kiosk Warden button now sits directly below the update controls instead of below rollback and release content where it could be outside the viewport.
- **Accurate post-update state**: a completed update now explicitly reports that Kiosk Warden has already been restarted and no longer presents a misleading second restart requirement.

## v1.8.1 — 2026-09-13

- **Reliable web UI activation after updates**: the updater now schedules the web UI restart as an independent systemd timer unit, preventing the delayed restart from being killed with the completed update scope. New navigation and pages become active immediately after every update.
- **Restart Kiosk Warden control**: the Updates page can restart all Warden and kiosk Chrome services without rebooting the machine. Both Warden restart and full machine restart show a five-second countdown, and the post-update prompt still supports Later.

## v1.8.0 — 2026-09-13

- **Manual update check**: the Updates page now has a dedicated check button that refreshes GitHub release information without installing anything.
- **Live installation progress**: download, validation, backup, file installation and service restart stages are shown in a persistent progress bar that survives the web UI service restart.
- **Controlled reboot**: after a successful update, choose to restart the machine now or later. Restart Now displays a visible five-second countdown before reboot.
- **Web UI address in Home Assistant**: MQTT discovery now adds a Web UI sensor containing the kiosk's complete `http://IP:port` address.

## v1.7.0 — 2026-09-13

- **Dedicated Updates page**: Kiosk Warden now has a separate Updates navigation tab with installed/latest versions, Stable/Beta selection, release notes, installation controls, local snapshots, rollback and the complete changelog.
- **Cleaner Settings page**: software update controls have moved out of general kiosk and MQTT settings.
- **Compatible news link**: the former `/changelog` URL continues to work and opens the new Updates page.

## v1.6.3 — 2026-09-13

- **Reliable failed-update reporting**: if release download, validation, backup or file replacement fails after installation starts, Home Assistant now receives a final `in_progress: false` state instead of leaving the update entity spinning.

## v1.6.2 — 2026-09-13

- **Strict MQTT schema compliance**: optional update fields with no value are omitted rather than published as `null`, allowing Home Assistant to accept every periodic update-state refresh.

## v1.6.1 — 2026-09-13

- **Home Assistant update state compatibility**: internal channel and release metadata is now filtered out before MQTT publication, so Home Assistant accepts and displays the semantic versions, release notes, URL and installation progress.

## v1.6.0 — 2026-09-13

- **Automatic low-power screen state**: `screen_off` now freezes the Chrome page before DPMS powers down the monitor, while `screen_on` resumes it before the display returns. The persisted OFF state is restored after Chrome restarts.
- **Stable and Beta update channels**: choose a channel in Home Assistant or Kiosk Warden. Stable follows GitHub's latest stable release; Beta follows the newest release including prereleases.
- **Release-based updates**: update discovery now reports semantic versions, release notes and the GitHub release URL instead of raw commit hashes.
- **Safe rollback**: every install creates a local snapshot first, and the web UI can restore a previously installed version.
- **Complete update packaging**: Python helpers and the semantic `VERSION` file are now installed and updated with the shell scripts.

## v1.1.1 — 2026-09-05

- **Onboard keyboard visibility fix**: replaced version-dependent internal docking settings with direct `wmctrl`/`xdotool` positioning so the keyboard reliably opens and remains visible.

## v1.1.0 — 2026-09-05

- **Automatic touch keyboard docking**: Onboard is positioned along the bottom edge and automatically shown for text input.
- **Cross-distro support**: the installer detects GDM and LightDM and configures the appropriate automatic login method.
- **Portable touch keyboard**: Onboard works across GNOME, Cinnamon, MATE and Xfce, with GNOME's keyboard used only as a fallback.
- **VNC password management**: Settings can update the x11vnc password and restart its service.
- **Flexible installation**: configure kiosk, MQTT and VNC interactively or defer configuration to the Web UI.
- `git` became an explicit installation dependency for self-updates.

## v1.0.0 — 2026-08-30

First official release.

- **Self-update from GitHub**: fetch and install scripts, Web UI and systemd units without SSH.
- **Home Assistant updates**: an MQTT update entity reports and installs new releases.
- **Built-in changelog**: release history is available directly in the Web UI.
- **Overview notifications**: the dashboard reports newly available releases.
- Consistent page width across every section.

## Earlier development changes

- Split the Web UI into shared navigation pages for status, VNC and configuration.
- Added the custom shield/monitor logo and desktop shortcuts.
- Added colour-coded RAM, disk and CPU temperature health thresholds.
- Added live IP, uptime, resource, Chrome and hardware information.
- Added browser-based VNC remote control through x11vnc, noVNC and websockify.
- Added the dependency-free Python Web UI on port 8080.
- Established the self-healing Chrome kiosk and complete Home Assistant MQTT integration.
