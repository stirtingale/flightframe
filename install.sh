#!/usr/bin/env bash
# Flight frame for Raspberry Pi: one-shot installer.
# Run on Raspberry Pi OS Bookworm (or later) Lite:
#   sudo ./install.sh                    # Pimoroni Inky Impression 7.3" (default)
#   sudo PANEL=waveshare ./install.sh    # Waveshare 7.3" e-Paper HAT (E)
set -euo pipefail

APP_DIR=/opt/flightframe
STATE_DIR=/var/lib/flightframe
VENV="$APP_DIR/venv"
PANEL="${PANEL:-inky}"
HOSTNAME_WANTED="${FRAME_HOSTNAME:-flightframe}"
NEEDS_REBOOT=0

if [[ $EUID -ne 0 ]]; then echo "Please run with sudo."; exit 1; fi
if [[ "$PANEL" != "inky" && "$PANEL" != "waveshare" ]]; then
  echo "PANEL must be inky or waveshare"; exit 1
fi
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "==> Packages"
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-dev build-essential \
  python3-pil python3-numpy python3-flask python3-requests python3-qrcode python3-waitress \
  python3-spidev python3-smbus2 python3-gpiozero python3-lgpio \
  fonts-inter fonts-dejavu-core git avahi-daemon network-manager

BOOT_CONFIG=/boot/firmware/config.txt
[[ -f "$BOOT_CONFIG" ]] || BOOT_CONFIG=/boot/config.txt

echo "==> SPI on (the panel talks over SPI)"
if command -v raspi-config >/dev/null; then raspi-config nonint do_spi 0; fi
[[ -e /dev/spidev0.0 ]] || NEEDS_REBOOT=1

if [[ "$PANEL" == "inky" ]]; then
  echo "==> I2C on (the Inky identifies itself over I2C)"
  if command -v raspi-config >/dev/null; then raspi-config nonint do_i2c 0; fi
  echo "==> Boot config: dtoverlay=spi0-0cs (required by Pimoroni for the Inky)"
  if ! grep -q "^dtoverlay=spi0-0cs" "$BOOT_CONFIG"; then
    echo "dtoverlay=spi0-0cs" >> "$BOOT_CONFIG"
    NEEDS_REBOOT=1
  fi
fi

echo "==> App"
mkdir -p "$APP_DIR" "$STATE_DIR"
rm -rf "$APP_DIR/flightframe"
cp -r "$SRC/flightframe" "$APP_DIR/"

echo "==> Python environment"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv --system-site-packages "$VENV"
fi
if [[ "$PANEL" == "inky" ]]; then
  "$VENV/bin/pip" install --upgrade "inky>=2.0"
fi

if [[ "$PANEL" == "waveshare" && ! -d "$APP_DIR/vendor/waveshare/lib/waveshare_epd" ]]; then
  echo "==> Waveshare E Ink driver"
  tmp="$(mktemp -d)"
  git clone --depth 1 --filter=blob:none --sparse https://github.com/waveshareteam/e-Paper.git "$tmp/e-Paper"
  git -C "$tmp/e-Paper" sparse-checkout set RaspberryPi_JetsonNano/python/lib
  mkdir -p "$APP_DIR/vendor/waveshare"
  cp -r "$tmp/e-Paper/RaspberryPi_JetsonNano/python/lib" "$APP_DIR/vendor/waveshare/"
  rm -rf "$tmp"
fi

echo "==> Remember which panel this is"
"$VENV/bin/python" - "$STATE_DIR/config.json" "$PANEL" <<'PY'
import json, sys
path, panel = sys.argv[1], sys.argv[2]
try:
    cfg = json.load(open(path))
except Exception:
    cfg = {}
cfg["display"] = panel
json.dump(cfg, open(path, "w"), indent=2)
PY

echo "==> Hotspot DNS: send every lookup to the frame so phones pop up the setup page"
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
echo "address=/#/10.42.0.1" > /etc/NetworkManager/dnsmasq-shared.d/flightframe.conf

echo "==> Hostname: ${HOSTNAME_WANTED}.local"
current="$(hostname)"
if [[ "$current" != "$HOSTNAME_WANTED" ]]; then
  hostnamectl set-hostname "$HOSTNAME_WANTED"
  sed -i "s/127.0.1.1.*/127.0.1.1\t${HOSTNAME_WANTED}/" /etc/hosts
fi

echo "==> Service"
install -m 644 "$SRC/systemd/flightframe.service" /etc/systemd/system/flightframe.service
systemctl daemon-reload
systemctl enable flightframe.service

echo
if [[ $NEEDS_REBOOT -eq 1 ]]; then
  echo "Done. Now run:  sudo reboot"
  echo "After the reboot the frame will show a Wi-Fi setup screen or a prompt to"
  echo "open http://${HOSTNAME_WANTED}.local and set your location."
else
  systemctl restart flightframe.service
  echo "Done. In a moment (allow about 30 seconds for the panel) the frame will show"
  echo "a Wi-Fi setup screen or a prompt to open http://${HOSTNAME_WANTED}.local."
fi
echo "Logs: journalctl -u flightframe -f"
