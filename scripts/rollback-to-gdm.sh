#!/bin/sh
# Kiosk Warden: tilbage fra X11-kiosksessionen (LightDM) til GDM/GNOME. Kør som root: sudo sh ~/kiosk/rollback-to-gdm.sh
set -e
echo /usr/sbin/gdm3 > /etc/X11/default-display-manager
systemctl disable lightdm >/dev/null 2>&1 || true
systemctl enable gdm3 >/dev/null 2>&1 || true
systemctl stop lightdm || true
systemctl start gdm3
