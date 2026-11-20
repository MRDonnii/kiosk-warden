#!/bin/sh
# Kiosk Warden: kiosk-session på X11 (LightDM, autologin): Openbox som vindueshåndtering og kiosk-tjenesterne som brugertjenester.
# Ubuntu 26.04 har ingen X11-session i GNOME, så denne lille session holder xdotool, xset, skærmvagt, RustDesk og VNC i gang.
# Markøren er skjult af X selv (-nocursor i LightDM); touch virker via libinput.
export XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=Kiosk XDG_SESSION_DESKTOP=kiosk
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
# kun skærmvagten slukker skærmen: ingen pauseskærm eller automatisk DPMS fra X
xset s off; xset s noblank; xset +dpms; xset dpms 0 0 0
dbus-update-activation-environment --systemd DISPLAY XAUTHORITY XDG_SESSION_TYPE XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP 2>/dev/null \
  || systemctl --user import-environment DISPLAY XAUTHORITY XDG_SESSION_TYPE XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP
systemctl --user start kiosk-x11-session.target
# tjenesterne, der skal bruge skærmen, startes på ny mod denne X-server
( sleep 2; systemctl --user restart kiosk-chrome.service kiosk-input-guardian.service kiosk-watchdog.service kiosk-adaptive-brightness.service ) >/dev/null 2>&1 &
exec openbox --startup true
