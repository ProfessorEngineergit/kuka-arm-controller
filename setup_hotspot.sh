#!/bin/bash
# Raspberry Pi WiFi Hotspot Setup (NetworkManager / nmcli)
# Debian Trixie does not use dhcpcd – NetworkManager handles everything.
set -e

REAL_USER="${SUDO_USER:-pi}"
APP_DIR="/home/${REAL_USER}/kuka-arm"

# Load .env
if [ -f "$APP_DIR/.env" ]; then
  export $(grep -v '^#' "$APP_DIR/.env" | xargs)
fi

SSID="${WIFI_SSID:-KUKA-ARM}"
PASS="${WIFI_PASSWORD:-kuka1234}"
IFACE="wlan0"
IP="192.168.4.1"
CON="kuka-hotspot"

echo "=== KUKA-ARM Hotspot Setup (NetworkManager) ==="
echo "SSID: $SSID | IP: $IP"

rfkill unblock wlan 2>/dev/null || true

# Remove existing connection if present (idempotent re-run)
nmcli con delete "$CON" 2>/dev/null || true

# Create WiFi AP connection
nmcli con add type wifi ifname "$IFACE" con-name "$CON" autoconnect yes ssid "$SSID"
nmcli con modify "$CON" \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "$PASS" \
  ipv4.method shared \
  ipv4.addresses "${IP}/24"

# Bring it up
nmcli con up "$CON"

echo ""
echo "=== Hotspot aktiv ==="
echo "  SSID:     $SSID"
echo "  Passwort: $PASS"
echo "  IP:       http://$IP"
echo "  Alias:    http://kuka.local"
