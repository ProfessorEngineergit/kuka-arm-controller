#!/bin/bash
# Full installation script for KUKA-ARM on Raspberry Pi
# Run as root: sudo bash setup.sh
set -e

APP_DIR="/home/pi/kuka-arm"
echo "=== KUKA-ARM Setup ==="
echo "Installationsverzeichnis: $APP_DIR"

# ── 1. System-Pakete ────────────────────────────────────────
echo "[1/6] System-Pakete installieren..."
apt-get update -q
apt-get install -y python3 python3-pip python3-venv git i2c-tools

# ── 2. I²C aktivieren ────────────────────────────────────────
echo "[2/6] I²C aktivieren..."
if ! grep -q "dtparam=i2c_arm=on" /boot/config.txt; then
  echo "dtparam=i2c_arm=on" >> /boot/config.txt
fi
# Raspberry Pi 5 uses /boot/firmware/config.txt
if [ -f /boot/firmware/config.txt ] && ! grep -q "dtparam=i2c_arm=on" /boot/firmware/config.txt; then
  echo "dtparam=i2c_arm=on" >> /boot/firmware/config.txt
fi
modprobe i2c-dev 2>/dev/null || true
if ! id -nG pi | grep -qw i2c; then
  usermod -aG i2c pi
fi

# ── 3. Python Virtual Environment ────────────────────────────
echo "[3/6] Python-Umgebung einrichten..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate

# ── 4. Verzeichnisse & Berechtigungen ────────────────────────
echo "[4/6] Berechtigungen setzen..."
mkdir -p "$APP_DIR/config/programs"
chown -R pi:pi "$APP_DIR"
chmod +x "$APP_DIR/start.sh"
chmod +x "$APP_DIR/setup_hotspot.sh"

# ── 5. WiFi Hotspot ───────────────────────────────────────────
echo "[5/6] WiFi-Hotspot konfigurieren..."
bash "$APP_DIR/setup_hotspot.sh"

# ── 6. Systemd Service ────────────────────────────────────────
echo "[6/6] Systemd-Service einrichten..."
cp "$APP_DIR/kuka-arm.service" /etc/systemd/system/kuka-arm.service
systemctl daemon-reload
systemctl enable kuka-arm.service

echo ""
echo "=== Installation abgeschlossen ==="
echo "Starte den Service: sudo systemctl start kuka-arm"
echo "Status prüfen:      sudo systemctl status kuka-arm"
echo "Logs:               sudo journalctl -u kuka-arm -f"
echo ""
echo "Verbinde dich mit WLAN '$(grep WIFI_SSID .env | cut -d= -f2)'"
echo "und öffne: http://192.168.4.1"
echo ""
echo "HINWEIS: Neustart empfohlen damit I²C und WLAN aktiv werden."
echo "         sudo reboot"
