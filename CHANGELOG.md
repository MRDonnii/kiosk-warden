# Changelog

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
