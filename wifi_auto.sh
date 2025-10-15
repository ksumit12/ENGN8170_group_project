#!/usr/bin/env bash
# Raspberry Pi (Bookworm+) Wi-Fi + SSH auto-setup
# Pref order: Red Shed Guest > Sumit_iPhone > ANU-Secure
# - Detects active stack (NetworkManager vs none) and uses it
# - Falls back to wpa_supplicant if NM not usable
# - Enables SSH on port 22 and verifies it's listening

set -euo pipefail

# ========= USER SETTINGS (edit if needed) =========
IF="${IF:-wlan0}"

SSID_RED="Red Shed Guest"
PSK_RED="RowingisGreat2025!"

SSID_IPHONE="Sumit_iPhone"
PSK_IPHONE="123451234"

SSID_ANU="ANU-Secure"
ANU_IDENTITY="u7871775@anu.edu.au"
ANU_PASSWORD="R0b0@2025Fly!"
ANU_CA="/etc/ssl/certs/ca-certificates.crt"   # leave as-is on Debian-like systems
# ==================================================

LOG="/var/log/wifi_ssh_autosetup.log"
say()  { echo -e "\033[1;32m[+]\033[0m $*" | tee -a "$LOG"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*" | tee -a "$LOG"; }
err()  { echo -e "\033[1;31m[x]\033[0m $*" | tee -a "$LOG" >&2; }

# ---------- helpers ----------
svc_active() { systemctl is-active --quiet "$1"; }
have()       { command -v "$1" >/dev/null 2>&1; }

# ---------- BLE setup helpers ----------
stop_ble_conflicts() {
  say "Stopping any competing BLE scans (bluetoothctl/hcitool)"
  pkill -f "bluetoothctl.*scan" 2>/dev/null || true
  pkill -f "hcitool.*lescan" 2>/dev/null || true
}

reset_ble_adapters() {
  say "Restarting bluetooth service and resetting adapters"
  sudo systemctl restart bluetooth || true
  sleep 1
  if have hciconfig; then
    for dev in hci0 hci1 hci2; do
      sudo hciconfig "$dev" reset 2>/dev/null || true
    done
  fi
}

disable_onboard_bt_if_usb_present() {
  # If TP-Link (Realtek USB) adapters are present, optionally disable onboard BT
  # to avoid contention. This is safe and reversible (requires reboot to take effect).
  if lsusb | grep -qiE 'tp-link|realtek'; then
    say "USB BLE adapters detected. Ensuring onboard BT is disabled (optional)."
    # Mask hciuart so onboard UART BT is not brought up
    sudo systemctl mask hciuart 2>/dev/null || true
    # Add overlay to firmware config if not present
    local BOOTCFG
    BOOTCFG="/boot/firmware/config.txt"
    [ -f /boot/config.txt ] && BOOTCFG="/boot/config.txt"
    if ! grep -q '^dtoverlay=disable-bt' "$BOOTCFG" 2>/dev/null; then
      echo 'dtoverlay=disable-bt' | sudo tee -a "$BOOTCFG" >/dev/null
      warn "Onboard Bluetooth disabled in $BOOTCFG (reboot required to fully apply)"
    fi
  else
    warn "No USB BLE adapter detected via lsusb; skipping onboard-BT disable"
  fi
}

ensure_ble_packages() {
  say "Installing BLE prerequisites (bluez, rfkill, tools, venv)"
  sudo apt-get update -qq || true
  sudo apt-get install -y bluez bluez-tools rfkill python3-venv python3-pip >/dev/null
}

setup_ble_venv() {
  say "Preparing Python venv for BLE scanning (Bleak)"
  mkdir -p "$HOME/venvs"
  if [ ! -d "$HOME/venvs/ibeacon" ]; then
    python3 -m venv "$HOME/venvs/ibeacon"
  fi
  # shellcheck disable=SC1091
  . "$HOME/venvs/ibeacon/bin/activate"
  python -m pip install --upgrade pip >/dev/null
  # Use a known-good Bleak range compatible with our script
  python -m pip install 'bleak>=0.22.2,<0.23' >/dev/null
}

ble_quick_test() {
  say "Running quick dual-adapter test (Apple iBeacon frames)"
  # shellcheck disable=SC1091
  . "$HOME/venvs/ibeacon/bin/activate"
  python - "$@" <<'PY' || warn "BLE quick test encountered an error"
import asyncio, sys
from bleak import BleakScanner

APPLE = 0x004C

async def scan(adapter: str):
    hits = 0
    def cb(device, advertisement_data):
        md = getattr(advertisement_data, 'manufacturer_data', {}) or {}
        if APPLE in md:
            nonlocal hits
            hits += 1
    s = BleakScanner(detection_callback=cb, adapter=adapter)
    await s.start()
    try:
        await asyncio.sleep(8.0)
    finally:
        await s.stop()
    print(f"{adapter} apple_frames={hits}")

async def main():
    for a in ("hci0", "hci1"):
        try:
            await scan(a)
        except Exception as e:
            print(f"{a} error={e}")

asyncio.run(main())
PY
}

preflight() {
  say "Snapshotting current state → $LOG"
  {
    echo "=== DATE ==="; date -Is
    echo "=== OS ===";  cat /etc/os-release 2>/dev/null || true
    echo "=== KERNEL ==="; uname -a
    echo "=== SERVICES ==="
    systemctl is-active NetworkManager || true
    systemctl is-active wpa_supplicant || true
    systemctl is-active "wpa_supplicant@$IF" || true
    echo "=== RFKILL ==="; rfkill list || true
    echo "=== IFACES ==="; iw dev || true
    echo "=== IPs ==="; ip -4 addr show dev "$IF" || true
  } >>"$LOG" 2>&1
}

enable_ssh_22() {
  say "Ensuring OpenSSH server is installed & enabled on port 22…"
  sudo apt-get update -qq || true
  sudo apt-get install -y openssh-server > /dev/null
  sudo systemctl enable --now ssh

  # Make sure Port 22 is present and unique
  sudo sed -i '/^[#[:space:]]*Port[[:space:]]\+22\b/!{s/^#\?Port .*/Port 22/}' /etc/ssh/sshd_config || true
  if ! grep -qE '^[#[:space:]]*Port[[:space:]]+22\b' /etc/ssh/sshd_config; then
    echo "Port 22" | sudo tee -a /etc/ssh/sshd_config >/dev/null
  fi
  sudo systemctl restart ssh

  # Open firewall if ufw present
  if have ufw; then
    sudo ufw allow 22/tcp || true
  fi

  say "SSH status:"
  ss -lntp 2>/dev/null | awk '/:22 /' || warn "ss didn't show port 22 yet"
  if svc_active ssh; then say "SSH: ACTIVE"; else warn "SSH not active"; fi
}

bring_up_nm() {
  # Ensure NM exists & usable
  have nmcli || return 1
  sudo systemctl enable --now NetworkManager
  sudo rfkill unblock all || true
  sudo ip link set "$IF" up || true
  nmcli dev set "$IF" managed yes || true
  nmcli radio wifi on || true

  say "Provisioning NetworkManager connections (with priorities)…"
  # Red Shed Guest (priority 100)
  nmcli -t -f NAME con show | grep -Fxq "$SSID_RED" || \
    nmcli con add type wifi ifname "$IF" con-name "$SSID_RED" ssid "$SSID_RED"
  nmcli con mod "$SSID_RED" \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.psk "$PSK_RED" \
    connection.autoconnect yes connection.autoconnect-priority 100

  # Sumit_iPhone (priority 90)
  nmcli -t -f NAME con show | grep -Fxq "$SSID_IPHONE" || \
    nmcli con add type wifi ifname "$IF" con-name "$SSID_IPHONE" ssid "$SSID_IPHONE"
  nmcli con mod "$SSID_IPHONE" \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.psk "$PSK_IPHONE" \
    connection.autoconnect yes connection.autoconnect-priority 90

  # ANU-Secure (priority 80) — EAP-TTLS (PAP)
  nmcli -t -f NAME con show | grep -Fxq "$SSID_ANU" || \
    nmcli con add type wifi ifname "$IF" con-name "$SSID_ANU" ssid "$SSID_ANU"
  nmcli con mod "$SSID_ANU" \
    802-11-wireless-security.key-mgmt wpa-eap \
    802-1x.eap ttls 802-1x.phase2-auth pap \
    802-1x.identity "$ANU_IDENTITY" 802-1x.password "$ANU_PASSWORD" \
    802-1x.ca-cert "$ANU_CA" \
    connection.autoconnect yes connection.autoconnect-priority 80

  nmcli dev wifi rescan || true
  sleep 2
  for SSID in "$SSID_RED" "$SSID_IPHONE" "$SSID_ANU"; do
    if nmcli -t -f SSID dev wifi list | grep -Fxq "$SSID"; then
      say "Bringing up preferred visible SSID via NM: $SSID"
      nmcli con up "$SSID" ifname "$IF" && return 0
    fi
  done
  warn "No preferred SSIDs visible to NM yet"
  return 1
}

bring_up_wpas() {
  say "Falling back to wpa_supplicant path…"
  sudo apt-get update -qq || true
  sudo apt-get install -y wpasupplicant wireless-tools dhclient > /dev/null

  local CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
  sudo mkdir -p /etc/wpa_supplicant
  sudo tee "$CONF" >/dev/null <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=AU

# 1) Red Shed Guest (highest)
network={
    ssid="$SSID_RED"
    key_mgmt=WPA-PSK
    psk="$PSK_RED"
    priority=3
}

# 2) Sumit_iPhone
network={
    ssid="$SSID_IPHONE"
    key_mgmt=WPA-PSK
    psk="$PSK_IPHONE"
    priority=2
}

# 3) ANU-Secure (EAP-TTLS/PAP)
network={
    ssid="$SSID_ANU"
    key_mgmt=WPA-EAP
    eap=TTLS
    identity="$ANU_IDENTITY"
    password="$ANU_PASSWORD"
    phase2="auth=PAP"
    ca_cert="$ANU_CA"
    priority=1
}
EOF

  # Make sure NM is out of the way if it exists
  if svc_active NetworkManager; then
    warn "Stopping NetworkManager to avoid conflicts with wpa_supplicant"
    sudo systemctl disable --now NetworkManager || true
  fi

  # Clean interface and start wpa_supplicant service
  sudo rfkill unblock wifi || true
  sudo ip link set "$IF" down || true
  sudo ip addr flush dev "$IF" || true
  sudo ip link set "$IF" up || true

  if systemctl list-unit-files | grep -q '^wpa_supplicant@\.service'; then
    sudo systemctl enable --now "wpa_supplicant@$IF"
  else
    sudo systemctl enable --now wpa_supplicant
  fi

  # DHCP (IPv4)
  sudo pkill -f "dhclient $IF" 2>/dev/null || true
  sudo dhclient -r "$IF" 2>/dev/null || true
  sudo dhclient "$IF" || true

  # Verify association
  sleep 3
  local SSID_ACT
  SSID_ACT="$(iwgetid -r || true)"
  if [ -z "$SSID_ACT" ]; then
    warn "wpa_supplicant up, but not yet associated; will continue"
  else
    say "Associated with: $SSID_ACT"
  fi
}

diagnose_net() {
  say "Network summary:"
  echo "  Host IPs : $(hostname -I 2>/dev/null || true)"
  echo "  SSID     : $(iwgetid -r 2>/dev/null || echo 'n/a')"
  echo "  Route    : $(ip route get 8.8.8.8 2>/dev/null | awk '/via/ {print $0}' || echo 'n/a')"
  say "Pinging 8.8.8.8…"
  ping -c 3 -W 2 8.8.8.8 || warn "ICMP to 8.8.8.8 failed"
  say "Pinging google.com…"
  ping -c 3 -W 3 google.com || warn "DNS or connectivity issue"
}

# ========== MAIN ==========
preflight

# Try NetworkManager first IF it’s present & can manage Wi-Fi
USED_STACK="none"
if have nmcli; then
  if bring_up_nm; then
    USED_STACK="networkmanager"
  else
    warn "NetworkManager path didn’t associate; trying wpa_supplicant fallback…"
  fi
fi

if [ "$USED_STACK" = "none" ]; then
  bring_up_wpas
  USED_STACK="wpa_supplicant"
fi

say "Using stack: $USED_STACK"
enable_ssh_22
diagnose_net

# ---------- BLE Setup & Sanity Test ----------
ensure_ble_packages
stop_ble_conflicts
reset_ble_adapters
disable_onboard_bt_if_usb_present
setup_ble_venv
ble_quick_test || true

say "Done. You can SSH with:  ssh pi@$(hostname -I | awk '{print $1}')"
warn "If onboard BT was disabled, reboot to fully apply (sudo reboot)."

# ---------- BLE Watchdog Service (systemd) ----------
install_ble_watchdog_service() {
  say "Installing BLE watchdog systemd service (auto-recovers BLE adapters)"

  # Determine project directory (assumes this script is run from repo root or within it)
  local PROJ_DIR
  if [ -d "$PWD/.git" ] && [ -f "$PWD/tools/ble_watchdog.py" ]; then
    PROJ_DIR="$PWD"
  elif [ -f "$(dirname "$0")/tools/ble_watchdog.py" ]; then
    PROJ_DIR="$(cd "$(dirname "$0")/.." && pwd)"
  else
    # Fallback to common location on Pi
    PROJ_DIR="$HOME/ENGN8170_group_project"
  fi

  if [ ! -f "$PROJ_DIR/tools/ble_watchdog.py" ]; then
    warn "ble_watchdog.py not found in $PROJ_DIR/tools — skipping service install"
    return 0
  fi

  # Ensure executable bit
  chmod +x "$PROJ_DIR/tools/ble_watchdog.py" || true

  # Create systemd unit with absolute paths; use system python (no extra deps required)
  local UNIT=/etc/systemd/system/ble_watchdog.service
  sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=BLE Watchdog (monitor hci0/hci1 and auto-recover)
After=bluetooth.service network-online.target
Wants=bluetooth.service network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJ_DIR
ExecStart=/usr/bin/python3 $PROJ_DIR/tools/ble_watchdog.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ble-watchdog

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now ble_watchdog.service

  # Show quick status summary
  if svc_active ble_watchdog; then
    say "BLE watchdog: ACTIVE"
  else
    warn "BLE watchdog not active yet; check: sudo journalctl -u ble_watchdog -b"
  fi
}

# Install and start the BLE watchdog automatically
install_ble_watchdog_service
