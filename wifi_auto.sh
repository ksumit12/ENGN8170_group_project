#!/usr/bin/env bash
# Wi-Fi bring-up & SSH hardening for Raspberry Pi OS (Bookworm Lite)
# Pref order: Red Shed Guest -> Sumit_iPhone -> ANU-Secure
# - Sets DNS per network (campus from DHCP lease; hotspot uses public DNS)
# - Ensures sshd is fast (UseDNS no, GSSAPIAuthentication no) and listens on 22 + 2222
# - Prints SSID, IP, DNS, and ping tests
# - Creates wpa_supplicant.conf with ANU-Secure EAP-TTLS configuration

set -euo pipefail

# ----------- SETTINGS -----------
IF="wlan0"
CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
HOTSPOT_SSID="Sumit_iPhone"            # change if needed
PREF_ORDER=("Red Shed Guest" "$HOTSPOT_SSID" "ANU-Secure")
DHCLIENT_LEASES="/var/lib/dhcp/dhclient.leases"
# Default to NetworkManager-managed flow unless explicitly disabled with --no-nm
USE_NETWORKMANAGER=1
# --------------------------------

say()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
err()  { echo -e "\033[1;31m[x]\033[0m $*" >&2; }

need() { command -v "$1" >/dev/null || { err "Missing: $1 (sudo apt install $1)"; exit 1; }; }
need wpa_cli; need wpa_supplicant; need ip; need iwgetid; need dhclient; need awk; need sed; need ss; need grep; need tee
# Arg parsing (only simple flag supported)
for arg in "$@"; do
  case "$arg" in
    --no-nm)
      USE_NETWORKMANAGER=0
      shift
      ;;
  esac
done


# Stop managers that fight with this script (best effort)
stop_conflicting_services() {
  if [ "$USE_NETWORKMANAGER" -eq 1 ]; then
    # NM-first mode: keep NM, stop raw managers that conflict
    sudo systemctl disable --now wpa_supplicant@wlan0 wpa_supplicant dhcpcd 2>/dev/null || true
    sudo nmcli radio wifi on 2>/dev/null || true
    # Ensure device is managed by NetworkManager (UI red-cross issue)
    if command -v nmcli >/dev/null 2>&1; then
      IFNM="$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')"
      [ -n "$IFNM" ] && nmcli dev set "$IFNM" managed yes 2>/dev/null || true
    fi
  else
    # Raw mode: stop NM and use wpa_supplicant directly
    if systemctl is-active --quiet NetworkManager 2>/dev/null; then
      warn "Stopping NetworkManager to avoid conflicts"
      sudo systemctl stop NetworkManager || true
      sudo systemctl disable NetworkManager || true
    fi
    if systemctl is-active --quiet dhcpcd 2>/dev/null; then
      warn "Stopping dhcpcd (using dhclient in this script)"
      sudo systemctl stop dhcpcd || true
    fi
  fi
}

# Ensure necessary packages exist (best effort, skips if already installed)
ensure_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo apt-get install -y --no-install-recommends \
      wpasupplicant wireless-tools dhcpcd5 resolvconf ufw >/dev/null 2>&1 || true
  fi
}

# Auto-detect wireless interface if the default is not present
detect_iface() {
  if ! ip link show "$IF" >/dev/null 2>&1; then
    local found
    found="$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')"
    if [ -n "$found" ]; then
      IF="$found"
      say "Detected wireless interface: $IF"
    else
      err "No wireless interface found (expected $IF)."
      exit 1
    fi
  fi
}

# Clear stale control sockets and PIDs, ensure control dir exists
prep_wpa_runtime() {
  sudo mkdir -p /var/run/wpa_supplicant
  sudo chgrp netdev /var/run/wpa_supplicant 2>/dev/null || true
  sudo chmod 0775 /var/run/wpa_supplicant 2>/dev/null || true
  # Kill any stuck wpa_supplicant for this IF
  sudo pkill -f "wpa_supplicant .* -i $IF" 2>/dev/null || true
  sudo rm -f "/var/run/wpa_supplicant/$IF" 2>/dev/null || true
}

# Unblock rfkill and bring interface cleanly up
reset_radio() {
  sudo rfkill unblock wifi || true
  sudo ip link set "$IF" down || true
  sudo ip addr flush dev "$IF" || true
  sudo ip link set "$IF" up || true
}

# DHCP using dhclient first, fallback to dhcpcd
do_dhcp() {
  local tries=0
  sudo pkill -f "dhclient $IF" 2>/dev/null || true
  sudo dhclient -r "$IF" 2>/dev/null || true
  IPV4=""
  while [ $tries -lt 3 ]; do
    tries=$((tries+1))
    sudo dhclient -v "$IF" | sed 's/^/[dhclient] /' || true
    IPV4="$(ip -4 -o addr show dev "$IF" | awk '{print $4}' | cut -d/ -f1)"
    [ -n "$IPV4" ] && break
    warn "No IPv4 yet... retry $tries/3"
    sleep 2
  done
  if [ -z "$IPV4" ] && command -v dhcpcd >/dev/null 2>&1; then
    warn "Falling back to dhcpcd"
    sudo pkill -f "dhcpcd .* $IF" 2>/dev/null || true
    sudo dhcpcd -k "$IF" 2>/dev/null || true
    sudo dhcpcd "$IF" || true
    IPV4="$(ip -4 -o addr show dev "$IF" | awk '{print $4}' | cut -d/ -f1)"
  fi
}

# Allow SSH ports through common firewalls (best effort)
open_firewall_ports() {
  if command -v ufw >/dev/null 2>&1; then
    sudo ufw allow 22/tcp >/dev/null 2>&1 || true
    sudo ufw allow 2222/tcp >/dev/null 2>&1 || true
  fi
  # nftables/iptables best-effort allowance
  if command -v iptables >/dev/null 2>&1; then
    sudo iptables -C INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null || sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT || true
    sudo iptables -C INPUT -p tcp --dport 2222 -j ACCEPT 2>/dev/null || sudo iptables -A INPUT -p tcp --dport 2222 -j ACCEPT || true
  fi
}

# ---------- Create wpa_supplicant.conf with site priorities ----------
ensure_wpa_conf() {
  say "Creating/updating $CONF with saved Wi-Fi configuration..."
  sudo mkdir -p "$(dirname "$CONF")"
  sudo tee "$CONF" >/dev/null <<'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=AU

# Red Shed Guest (priority 1)
network={
    ssid="Red Shed Guest"
    key_mgmt=WPA-PSK
    psk="RowingisGreat2025!"
    priority=1
}

# Sumit_iPhone hotspot (priority 2)
network={
    ssid="Sumit_iPhone"
    key_mgmt=WPA-PSK
    psk="123451234"
    priority=2
}

# ANU-Secure (priority 3) - EAP-TTLS with PAP
network={
    ssid="ANU-Secure"
    key_mgmt=WPA-EAP
    eap=TTLS
    identity="u7871775@anu.edu.au"
    password="R0b0@2025Fly!"
    phase2="auth=PAP"
    ca_cert="/etc/ssl/certs/ca-certificates.crt"
    priority=3
}
EOF
  say "Created $CONF with priority: Red Shed Guest -> Sumit_iPhone -> ANU-Secure"
}

# ---------- NetworkManager connection provisioning ----------
nm_provision_connections() {
  say "Provisioning NetworkManager connections..."
  local ifnm
  ifnm="$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')"
  [ -z "$ifnm" ] && ifnm="$IF"
  # Red Shed Guest
  nmcli -t -f NAME con show | grep -Fxq "Red Shed Guest" || \
    nmcli con add type wifi ifname "$ifnm" con-name "Red Shed Guest" ssid "Red Shed Guest" || true
  nmcli con mod "Red Shed Guest" 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk "RowingisGreat2025!" connection.autoconnect yes connection.autoconnect-priority 100 || true
  # Sumit_iPhone
  nmcli -t -f NAME con show | grep -Fxq "$HOTSPOT_SSID" || \
    nmcli con add type wifi ifname "$ifnm" con-name "$HOTSPOT_SSID" ssid "$HOTSPOT_SSID" || true
  nmcli con mod "$HOTSPOT_SSID" 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk "123451234" connection.autoconnect yes connection.autoconnect-priority 90 || true
  # ANU-Secure (EAP-TTLS/PAP)
  nmcli -t -f NAME con show | grep -Fxq "ANU-Secure" || \
    nmcli con add type wifi ifname "$ifnm" con-name "ANU-Secure" ssid "ANU-Secure" || true
  nmcli con mod "ANU-Secure" 802-11-wireless-security.key-mgmt wpa-eap 802-1x.eap ttls 802-1x.identity "u7871775@anu.edu.au" 802-1x.password "R0b0@2025Fly!" 802-1x.phase2-auth pap 802-1x.ca-cert "/etc/ssl/certs/ca-certificates.crt" connection.autoconnect yes connection.autoconnect-priority 80 || true
}

# ---------- DNS helpers ----------
_resolv_replace() {
  # replace /etc/resolv.conf whether it's a file or broken symlink
  sudo rm -f /etc/resolv.conf 2>/dev/null || true
  # "$@" already contains "nameserver X" lines
  printf '%s\n' "$@" | sudo tee /etc/resolv.conf >/dev/null
}

write_dns_list() {
  # args may be raw IPs or "nameserver X" lines; normalize to "nameserver X"
  local out=()
  for d in "$@"; do
    [[ "$d" =~ ^nameserver[[:space:]] ]] && out+=("$d") || out+=("nameserver $d")
  done
  _resolv_replace "${out[@]}"
}

get_dns_from_leases() {
  # prints one DNS per line from last lease
  [ -r "$DHCLIENT_LEASES" ] || return 1
  awk '/domain-name-servers/ {last=$0} END{print last}' "$DHCLIENT_LEASES" \
    | sed -E 's/.*domain-name-servers *([^;]+);.*/\1/' \
    | tr -d ' ' | tr ',' '\n'
}

set_dns_for_ssid() {
  local ssid="$1"
  if [ "$ssid" = "$HOTSPOT_SSID" ]; then
    say "Hotspot detected → using public DNS (8.8.8.8, 1.1.1.1)"
    write_dns_list 8.8.8.8 1.1.1.1
  else
    say "Campus Wi-Fi detected → deriving DNS from DHCP lease"
    mapfile -t DNS_IPS < <(get_dns_from_leases || true)
    if [ "${#DNS_IPS[@]}" -eq 0 ]; then
      warn "Could not read campus DNS from leases; fallback to 8.8.8.8, 1.1.1.1"
      write_dns_list 8.8.8.8 1.1.1.1
    else
      write_dns_list "${DNS_IPS[@]}"
    fi
  fi
}

# ---------- SSH hardening and port configuration ----------
fix_sshd() {
  local cfg="/etc/ssh/sshd_config"

  say "Configuring SSH for fast connections and dual ports..."
  sudo touch "$cfg"

  # Backup original config
  sudo cp "$cfg" "${cfg}.backup.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

  # Ensure SSH service is installed and enabled
  sudo apt-get update -qq
  sudo apt-get install -y openssh-server

  # Configure SSH for fast handshake
  sudo sed -i 's/^[#[:space:]]*UseDNS.*/UseDNS no/g' "$cfg" || true
  sudo sed -i 's/^[#[:space:]]*GSSAPIAuthentication.*/GSSAPIAuthentication no/g' "$cfg" || true
  sudo sed -i 's/^[#[:space:]]*PubkeyAuthentication.*/PubkeyAuthentication yes/g' "$cfg" || true
  sudo sed -i 's/^[#[:space:]]*PasswordAuthentication.*/PasswordAuthentication yes/g' "$cfg" || true

  # Add missing lines if they don't exist
  grep -qE '^[#[:space:]]*UseDNS' "$cfg" || echo "UseDNS no" | sudo tee -a "$cfg" >/dev/null
  grep -qE '^[#[:space:]]*GSSAPIAuthentication' "$cfg" || echo "GSSAPIAuthentication no" | sudo tee -a "$cfg" >/dev/null
  grep -qE '^[#[:space:]]*PubkeyAuthentication' "$cfg" || echo "PubkeyAuthentication yes" | sudo tee -a "$cfg" >/dev/null
  grep -qE '^[#[:space:]]*PasswordAuthentication' "$cfg" || echo "PasswordAuthentication yes" | sudo tee -a "$cfg" >/dev/null

  # Configure dual ports (22 and 2222)
  # Remove any existing Port lines
  sudo sed -i '/^[#[:space:]]*Port[[:space:]]/d' "$cfg"
  
  # Add both ports
  echo "Port 22" | sudo tee -a "$cfg" >/dev/null
  echo "Port 2222" | sudo tee -a "$cfg" >/dev/null

  # Enable and start SSH service
  sudo systemctl enable ssh >/dev/null 2>&1 || true
  sudo systemctl enable sshd >/dev/null 2>&1 || true
  sudo systemctl restart ssh >/dev/null 2>&1 || true
  sudo systemctl restart sshd >/dev/null 2>&1 || true

  # Wait a moment for SSH to start
  sleep 2

  say "SSH configuration complete. Listening on:"
  ss -lntp | awk '/:22 |:2222 /' || warn "SSH ports not visible yet (may need a moment)"
  
  # Show SSH status
  if systemctl is-active --quiet ssh; then
    say "SSH service: ACTIVE"
  elif systemctl is-active --quiet sshd; then
    say "SSHD service: ACTIVE"
  else
    warn "SSH service status unclear - checking manually..."
    sudo systemctl status ssh sshd | head -10
  fi
}

# ---------- Password configuration helper ----------
# No interactive password prompt; ANU-Secure uses EAP-TTLS without stored password.
configure_password() { true; }

# ---------- Wi-Fi bring-up ----------
stop_conflicting_services
detect_iface
ensure_wpa_conf
configure_password
say "Resetting Wi-Fi ($IF)..."
sudo rfkill unblock wifi || true
sudo ip link set "$IF" down || true
sudo ip addr flush dev "$IF" || true
sudo ip link set "$IF" up
sudo killall wpa_supplicant 2>/dev/null || true

if [ "$USE_NETWORKMANAGER" -eq 1 ]; then
  say "Using NetworkManager to manage Wi-Fi..."
  sudo systemctl enable --now NetworkManager 2>/dev/null || true
  nm_provision_connections
  sudo nmcli radio wifi on || true
  # Prefer highest priority that is visible
  nmcli dev wifi rescan || true
  sleep 2
  for ssid in "${PREF_ORDER[@]}"; do
    if nmcli -t -f SSID dev wifi list | grep -Fxq "$ssid"; then
      case "$ssid" in
        "Red Shed Guest") nmcli con up "Red Shed Guest" ifname "$IF" || true ;;
        "$HOTSPOT_SSID") nmcli con up "$HOTSPOT_SSID" ifname "$IF" || true ;;
        "ANU-Secure") nmcli con up "ANU-Secure" ifname "$IF" || true ;;
      esac
      break
    fi
  done
else
  ### Start wpa_supplicant using per-interface service to ensure control socket
  if systemctl list-unit-files | grep -q '^wpa_supplicant@\.service'; then
    say "Starting wpa_supplicant@${IF}.service..."
    sudo systemctl enable "wpa_supplicant@${IF}.service" >/dev/null 2>&1 || true
    sudo systemctl restart "wpa_supplicant@${IF}.service"
  elif systemctl list-unit-files | grep -q '^wpa_supplicant\.service'; then
    say "Starting wpa_supplicant service..."
    sudo systemctl enable wpa_supplicant >/dev/null 2>&1 || true
    sudo systemctl restart wpa_supplicant
  else
    say "Starting wpa_supplicant (direct)..."
    sudo wpa_supplicant -B -i "$IF" -c "$CONF" -D nl80211
  fi
fi

if [ "$USE_NETWORKMANAGER" -eq 0 ]; then
  # Wait for control interface socket so wpa_cli does not fail
  for _ in {1..10}; do
    if wpa_cli -i "$IF" status >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if [ "$USE_NETWORKMANAGER" -eq 0 ]; then
  # Scan & choose preferred SSID (if hidden, include configured SSIDs)
  wpa_cli -i "$IF" reconfigure >/dev/null 2>&1 || true
  say "Scanning for known SSIDs..."
  wpa_cli -i "$IF" scan >/dev/null
  sleep 3
  VISIBLE="$(wpa_cli -i "$IF" scan_results | awk '{print $5}' | tail -n +3)"
  if ! echo "$VISIBLE" | grep -Fxq "ANU-Secure"; then
    # trigger a directed scan for ANU-Secure (hidden APs)
    wpa_cli -i "$IF" add_network >/dev/null 2>&1 || true
    wpa_cli -i "$IF" set_network 0 ssid '"ANU-Secure"' >/dev/null 2>&1 || true
    wpa_cli -i "$IF" set_network 0 scan_ssid 1 >/dev/null 2>&1 || true
    wpa_cli -i "$IF" scan >/dev/null 2>&1 || true
    sleep 2
    VISIBLE="$(wpa_cli -i "$IF" scan_results | awk '{print $5}' | tail -n +3)"
  fi
fi

TARGET=""; NETID=""
if [ "$USE_NETWORKMANAGER" -eq 0 ]; then
  for ssid in "${PREF_ORDER[@]}"; do
    if echo "$VISIBLE" | grep -Fxq "$ssid"; then
      NETID="$(wpa_cli -i "$IF" list_networks | awk -v s="$ssid" '$2==s {print $1; exit}')"
      if [ -n "$NETID" ]; then TARGET="$ssid"; break; fi
    fi
  done
fi
[ -n "$TARGET" ] || { err "None of the preferred SSIDs are visible: ${PREF_ORDER[*]}"; exit 1; }

if [ "$USE_NETWORKMANAGER" -eq 1 ]; then
  : # already brought up preferred connection via nmcli above
else
  say "Connecting to '$TARGET' (network id $NETID)..."
  wpa_cli -i "$IF" select_network "$NETID" >/dev/null
  wpa_cli -i "$IF" enable_network "$NETID"  >/dev/null
  wpa_cli -i "$IF" reassociate             >/dev/null
fi

# For enterprise/roaming, allow longer association window
for _ in {1..25}; do
  SSID="$(iwgetid -r || true)"
  STATE="$(wpa_cli -i "$IF" status 2>/dev/null | awk -F= '$1=="wpa_state"{print $2}')"
  [ "$SSID" = "$TARGET" ] && [ "$STATE" = "COMPLETED" ] && break
  sleep 1
done
SSID="$(iwgetid -r || true)"
[ "$SSID" = "$TARGET" ] || { err "Failed to associate to '$TARGET'"; exit 1; }
say "Associated with: $SSID"

say "Requesting IP (DHCP)..."
do_dhcp
[ -n "$IPV4" ] || { err "No IPv4 lease on $IF after retries"; exit 1; }

# DNS per network
set_dns_for_ssid "$SSID"

echo
say "Connected"
echo "  SSID : $SSID"
echo "  IPv4 : $IPV4"
echo "  DNS  :"
sed 's/^/    /' /etc/resolv.conf
echo

# Quick reachability tests
say "Pinging 8.8.8.8..."
ping -c 3 -W 2 8.8.8.8 || warn "8.8.8.8 ping failed"

say "Pinging google.com..."
if ! ping -c 3 -W 3 google.com; then
  warn "DNS ping failed. Current /etc/resolv.conf:"
  sed 's/^/    /' /etc/resolv.conf
fi

# SSH fixes (fast handshake + dual ports)
say "Applying SSH fixes (UseDNS no, GSSAPIAuthentication no; Ports 22 & 2222)..."
fix_sshd
open_firewall_ports

echo
say "Setup Complete"
echo
say "WiFi Status:"
echo "  SSID : $SSID"
echo "  IPv4 : $IPV4"
echo "  DNS  :"
sed 's/^/    /' /etc/resolv.conf
echo
say "SSH Access:"
echo "  Port 22  : ssh pi@$IPV4"
echo "  Port 2222: ssh -p 2222 pi@$IPV4"
echo
say "Next Steps:"
echo "  1. Test SSH: ssh pi@$IPV4"
echo "  2. If port 22 blocked: ssh -p 2222 pi@$IPV4"
echo "  3. Configure ANU password if not done: sudo nano $CONF"
echo

say "Done."
