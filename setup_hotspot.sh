#!/bin/bash
# Raspberry Pi WiFi Hotspot Setup
# Reads WIFI_SSID and WIFI_PASSWORD from .env
set -e

# Load .env
if [ -f /home/pi/kuka-arm/.env ]; then
  export $(grep -v '^#' /home/pi/kuka-arm/.env | xargs)
fi

SSID="${WIFI_SSID:-KUKA-ARM}"
PASS="${WIFI_PASSWORD:-kuka1234}"
IFACE="wlan0"
IP="192.168.4.1"

echo "=== KUKA-ARM Hotspot Setup ==="
echo "SSID: $SSID | IP: $IP"

# Install dependencies
apt-get update -q
apt-get install -y hostapd dnsmasq

# Stop services during config
systemctl stop hostapd dnsmasq || true
rfkill unblock wlan || true

# Static IP for wlan0
cat > /etc/dhcpcd.conf.d/kuka-hotspot.conf <<EOF
interface ${IFACE}
    static ip_address=${IP}/24
    nohook wpa_supplicant
EOF

# Append to dhcpcd.conf if not already there
if ! grep -q "kuka-hotspot" /etc/dhcpcd.conf; then
  echo "" >> /etc/dhcpcd.conf
  echo "# KUKA hotspot" >> /etc/dhcpcd.conf
  echo "interface ${IFACE}" >> /etc/dhcpcd.conf
  echo "    static ip_address=${IP}/24" >> /etc/dhcpcd.conf
  echo "    nohook wpa_supplicant" >> /etc/dhcpcd.conf
fi

# dnsmasq – DHCP server
cat > /etc/dnsmasq.d/kuka.conf <<EOF
interface=${IFACE}
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=local
address=/kuka.local/${IP}
EOF

# hostapd – Access Point
cat > /etc/hostapd/hostapd.conf <<EOF
interface=${IFACE}
driver=nl80211
ssid=${SSID}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
wpa=2
wpa_passphrase=${PASS}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# Point hostapd to config
sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

# Enable IP forwarding (optional, for internet sharing)
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/kuka.conf

# Enable and start
systemctl unmask hostapd
systemctl enable hostapd dnsmasq
systemctl restart dhcpcd || true
systemctl start hostapd dnsmasq

echo ""
echo "=== Hotspot aktiv ==="
echo "  SSID:     $SSID"
echo "  Passwort: $PASS"
echo "  IP:       http://$IP"
echo "  Alias:    http://kuka.local"
