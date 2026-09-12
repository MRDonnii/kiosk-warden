# Changelog

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

- **Fix: onboard-tastatur der forsvandt uden at komme frem igen**: v1.1.0's docking-indstillinger (`org.onboard.window docking-enabled`/`docking-edge`) viste sig at bringe onboard i en ødelagt tilstand på visse versioner — man kunne se ikonet, men et klik på det fik det til at forsvinde uden at vise tastaturet. Erstattet med at flytte/resize selve vinduet via `wmctrl`/`xdotool` (samme værktøjer kiosk-warden allerede bruger til Chrome-styring) i stedet for at stole på onboard's interne (versions-afhængige) indstillinger.

## v1.1.0 — 2026-09-05

- **Touch-tastatur dokket i bunden automatisk**: når `onboard` slås til (ved install eller via MQTT/HA/web-UI), sættes den nu automatisk til at docke i bunden af skærmen og vise sig selv når man trykker i et tekstfelt (`docking-edge bottom` + `auto-show`) — ingen manuel indstilling nødvendig.
- **Cross-distro support**: `install.sh` registrerer nu OS og display manager (GDM3 vs LightDM) og bruger den rigtige autologin-metode for hver — Ubuntu (GDM) virkede allerede, Linux Mint og andre LightDM-baserede distroer sættes nu også korrekt op.
- **Touch-tastatur virker på alle desktops**: `onboard` installeres nu altid via apt og bruges som det primære skærmtastatur (virker på GNOME, Cinnamon, MATE, Xfce...); GNOME's indbyggede on-screen keyboard bruges kun som fallback når GNOME faktisk er det aktive skrivebordsmiljø. Tidligere brugte installeren kun GNOME's variant, som ikke virker på fx Linux Mint/Cinnamon.
- **VNC password skiftes fra web-UI'et**: en ny "Fjernstyring (VNC) password"-formular under Indstillinger sætter `x11vnc -storepasswd` og genstarter `kiosk-vnc.service` — ingen terminal nødvendig.
- **Valg ved installation**: `install.sh` spørger nu om du vil konfigurere kiosk/MQTT/VNC i terminalen med det samme, eller installere med standardværdier og gøre det bagefter via web-UI'et (`CONFIGURE_NOW=no` for at styre det uden interaktion).
- `git` er nu en eksplicit del af apt-pakkelisten (var tidligere kun sikret i curl-bootstrap-stien), da selvopdatering kræver den ved kørsel.

## v1.0.0 — 2026-08-30

Første officielle release.

- **Selvopdatering fra GitHub**: en "Tjek og opdater"-knap under Indstillinger henter nyeste version, opdaterer alle scripts/web-UI/systemd-units, og genstarter de nødvendige services — uden SSH.
- **Home Assistant-integration af opdateringer**: en `update`-entity i HA viser når en ny version er klar, og "Install"-knappen i HA trigger opdateringen direkte via MQTT.
- **Nyheder-fane**: denne changelog vises nu direkte i web-UI'et.
- **Notifikation på forsiden**: en banner viser besked når en ny version er tilgængelig, baseret på et periodisk baggrundstjek mod GitHub.
- Ensartet sidebredde på alle sider — ingen layout-hop når man skifter mellem Oversigt, Fjernstyring, Nyheder og Indstillinger.

## Tidligere ændringer (samlet under udvikling)

- Delt web-UI op i separate sider: **Oversigt** (status + hurtige handlinger), **Fjernstyring** (VNC) og **Indstillinger** (kiosk/MQTT-konfiguration + password), med en fælles navigationsmenu.
- Tilføjet et brugerdefineret logo/favicon (shield + skærm-ikon) brugt i browserfanen og på begge skrivebordsgenveje.
- Farvekodede status-felter (grøn/gul/rød) baseret på tærskelværdier for RAM, disk og CPU-temperatur, samt et generelt visuelt løft af web-UI'et.
- Live maskindata i web-UI'et: IP, oppetid, RAM/disk/temperatur, CPU-load, Chrome-status og model — hentet direkte fra systemet.
- Bygget browser-baseret **VNC-fjernstyring** ind i pakken (x11vnc + noVNC + websockify), så man kan klikke direkte på kiosk-skærmen fra en browser, inklusiv fuldskærmsvisning.
- Tilføjet et lille indbygget **web-UI** (ren Python, ingen eksterne afhængigheder) til opsætning og lokal kontrol, tilgængeligt på port 8080.
- Første udgivelse: et selvhelende Ubuntu Chrome-kiosk-setup bygget på bash og systemd, med fuld Home Assistant MQTT-integration (status, styring, screenshots, backups, health-check/watchdog).
