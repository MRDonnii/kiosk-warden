#!/usr/bin/env bash
# Display backend abstraction for Kiosk Warden. Source this file.

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

screen_backend_detect() {
  if [[ -n "${KIOSK_SCREEN_BACKEND:-}" && "${KIOSK_SCREEN_BACKEND}" != auto ]]; then
    printf '%s\n' "$KIOSK_SCREEN_BACKEND"
  elif [[ "${XDG_SESSION_TYPE:-}" == wayland ]] && command -v wlopm >/dev/null 2>&1; then
    printf 'wayland-wlopm\n'
  elif [[ "${XDG_SESSION_TYPE:-}" == wayland ]] && command -v kscreen-doctor >/dev/null 2>&1; then
    printf 'wayland-kde\n'
  elif [[ -r /proc/device-tree/model ]] && tr -d '\0' </proc/device-tree/model | grep -qi 'raspberry pi'; then
    printf 'raspberry-pi\n'
  elif [[ "${XDG_CURRENT_DESKTOP:-}" == *Cinnamon* ]]; then
    printf 'cinnamon-x11\n'
  elif [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]]; then
    printf 'gnome-x11\n'
  else
    printf 'x11\n'
  fi
}

screen_output() { xrandr --query 2>/dev/null | awk '/ connected/ {print $1; exit}'; }

screen_geometry() {
  local geometry width height output refresh
  geometry="$(xdotool getdisplaygeometry 2>/dev/null || true)"
  read -r width height <<<"$geometry"
  if [[ "${width:-0}" -eq 0 ]] && command -v wlr-randr >/dev/null 2>&1; then
    geometry="$(wlr-randr --json 2>/dev/null | jq -r '[.[]|select(.enabled)][0].modes[]|select(.current)|"\(.width) \(.height)"' | head -n1)"
    read -r width height <<<"$geometry"
  fi
  output="$(screen_output)"
  refresh="$(xrandr --query 2>/dev/null | awk -v out="$output" '$1==out{seen=1;next} seen && /\*/{gsub("[*+]", "", $2); print $2; exit}')"
  jq -cn --arg backend "$(screen_backend_detect)" --arg output "$output" \
    --argjson width "${width:-0}" --argjson height "${height:-0}" --arg refresh "${refresh:-unknown}" \
    '{backend:$backend,output:$output,width:$width,height:$height,refresh_hz:$refresh}'
}

screen_prepare_on() {
  local backend output
  backend="$(screen_backend_detect)"; output="$(screen_output)"
  case "$backend" in
    gnome-x11|cinnamon-x11|x11)
      [[ -n "$output" ]] && timeout 3s xrandr --output "$output" --auto >/dev/null 2>&1 || true ;;
    raspberry-pi)
      [[ -n "$output" ]] && timeout 3s xrandr --output "$output" --auto >/dev/null 2>&1 || true
      command -v vcgencmd >/dev/null && vcgencmd display_power 1 >/dev/null 2>&1 || true ;;
    wayland-wlopm) timeout 5s wlopm --on '*' >/dev/null 2>&1 || return 1 ;;
    wayland-kde) timeout 5s kscreen-doctor --dpms on >/dev/null 2>&1 || return 1 ;;
    ddc)
      command -v ddcutil >/dev/null && timeout 5s ddcutil setvcp D6 01 ${KIOSK_DDC_ARGS:-} >/dev/null 2>&1 || return 1 ;;
    cec)
      command -v cec-client >/dev/null && printf 'on %s\n' "${KIOSK_CEC_DEVICE:-0}" | timeout 5s cec-client -s -d 1 >/dev/null 2>&1 || return 1 ;;
    *) echo "Unsupported screen backend: $backend" >&2; return 1 ;;
  esac
}

screen_show() {
  xset +dpms >/dev/null 2>&1 || true
  timeout 3s xset dpms force on >/dev/null 2>&1 || true
  xset s off >/dev/null 2>&1 || true
  xset s noblank >/dev/null 2>&1 || true
  xset dpms 0 0 0 >/dev/null 2>&1 || true
}

screen_hide() {
  local backend
  backend="$(screen_backend_detect)"
  case "$backend" in
    gnome-x11|cinnamon-x11|x11)
      xset +dpms >/dev/null 2>&1 || true
      xset dpms 0 0 1 >/dev/null 2>&1 || true
      timeout 3s xset dpms force off >/dev/null 2>&1 ;;
    raspberry-pi)
      command -v vcgencmd >/dev/null && vcgencmd display_power 0 >/dev/null 2>&1 || {
        xset +dpms >/dev/null 2>&1; timeout 3s xset dpms force off >/dev/null 2>&1;
      } ;;
    wayland-wlopm) timeout 5s wlopm --off '*' >/dev/null 2>&1 ;;
    wayland-kde) timeout 5s kscreen-doctor --dpms off >/dev/null 2>&1 ;;
    ddc) timeout 5s ddcutil setvcp D6 04 ${KIOSK_DDC_ARGS:-} >/dev/null 2>&1 ;;
    cec) printf 'standby %s\n' "${KIOSK_CEC_DEVICE:-0}" | timeout 5s cec-client -s -d 1 >/dev/null 2>&1 ;;
  esac
}

screen_power_state() {
  local state
  state="$(xset q 2>/dev/null | awk '/Monitor is/{print $3; exit}')"
  [[ -n "$state" ]] && printf '%s\n' "$state" || printf 'Unknown\n'
}
