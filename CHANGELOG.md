# Changelog

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
