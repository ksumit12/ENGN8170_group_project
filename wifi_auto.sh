#!/usr/bin/env bash
# Wi-Fi bring-up & SSH hardening for Raspberry Pi OS (Bookworm Lite)
# Pref order: ANU-Secure -> Red Shed Guest -> Sumit_iPhone
# - Sets DNS per network (campus from DHCP lease; hotspot uses public DNS)
# - Ensures sshd is fast (UseDNS no, GSSAPIAuthentication no) and listens on 22 + 2222
# - Prints SSID, IP, DNS, and ping tests
# - Creates wpa_supplicant.conf with ANU-Secure EAP-TTLS configuration

set -euo pipefail

# ----------- SETTINGS -----------
IF="wlan0"
CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
HOTSPOT_SSID="Sumit_iPhone"            # change if needed
PREF_ORDER=("ANU-Secure" "Red Shed Guest" "$HOTSPOT_SSID")
DHCLIENT_LEASES="/var/lib/dhcp/dhclient.leases"
# --------------------------------

say()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
err()  { echo -e "\033[1;31m[x]\033[0m $*" >&2; }

need() { command -v "$1" >/dev/null || { err "Missing: $1 (sudo apt install $1)"; exit 1; }; }
need wpa_cli; need wpa_supplicant; need ip; need iwgetid; need dhclient; need awk; need sed; need ss; need grep; need tee

# ---------- Create wpa_supplicant.conf with ANU-Secure priority ----------
ensure_wpa_conf() {
  say "Creating/updating $CONF with ANU-Secure EAP-TTLS configuration…"
  sudo mkdir -p "$(dirname "$CONF")"
  sudo tee "$CONF" >/dev/null <<'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=AU

# ANU-Secure (priority 1) - EAP-TTLS with PAP
network={
    ssid="ANU-Secure"
    key_mgmt=WPA-EAP
    eap=TTLS
    identity="u7871775@anu.edu.au"
    password="YOUR_PASSWORD_HERE"
    phase2="auth=PAP"
    ca_cert="/etc/ssl/certs/ca-certificates.crt"
    priority=1
}

# Red Shed Guest (priority 2)
network={
    ssid="Red Shed Guest"
    priority=2
}

# Sumit_iPhone hotspot (priority 3)
network={
    ssid="Sumit_iPhone"
    priority=3
}
EOF
  say "Created $CONF with ANU-Secure → Red Shed Guest → Sumit_iPhone priority"
  say "⚠️  IMPORTANT: Update 'YOUR_PASSWORD_HERE' with your actual ANU password!"
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
configure_password() {
  if grep -q "YOUR_PASSWORD_HERE" "$CONF" 2>/dev/null; then
    warn "⚠️  ANU password not configured!"
    echo
    echo "To configure your ANU password, run:"
    echo "  sudo nano $CONF"
    echo "  # Replace 'YOUR_PASSWORD_HERE' with your actual ANU password"
    echo
    read -p "Do you want to configure the password now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      echo "Opening $CONF for editing..."
      sudo nano "$CONF"
      say "Password configuration complete!"
    else
      warn "Continuing without password configuration - ANU-Secure may fail to connect"
    fi
  fi
}

# ---------- Wi-Fi bring-up ----------
ensure_wpa_conf
configure_password
say "Resetting Wi-Fi ($IF)…"
sudo rfkill unblock wifi || true
sudo ip link set "$IF" down || true
sudo killall wpa_supplicant 2>/dev/null || true
sudo ip link set "$IF" up

# Start wpa_supplicant (service if present, else direct)
if systemctl list-unit-files | grep -q '^wpa_supplicant\.service'; then
  say "Starting wpa_supplicant service…"
  sudo systemctl enable wpa_supplicant >/dev/null 2>&1 || true
  sudo systemctl restart wpa_supplicant
else
  say "Starting wpa_supplicant (direct)…"
  sudo wpa_supplicant -B -i "$IF" -c "$CONF" -D nl80211
fi

# Scan & choose preferred SSID
wpa_cli -i "$IF" reconfigure >/dev/null 2>&1 || true
say "Scanning for known SSIDs…"
wpa_cli -i "$IF" scan >/dev/null
sleep 3
VISIBLE="$(wpa_cli -i "$IF" scan_results | awk '{print $5}' | tail -n +3)"

TARGET=""; NETID=""
for ssid in "${PREF_ORDER[@]}"; do
  if echo "$VISIBLE" | grep -Fxq "$ssid"; then
    NETID="$(wpa_cli -i "$IF" list_networks | awk -v s="$ssid" '$2==s {print $1; exit}')"
    if [ -n "$NETID" ]; then TARGET="$ssid"; break; fi
  fi
done
[ -n "$TARGET" ] || { err "None of the preferred SSIDs are visible: ${PREF_ORDER[*]}"; exit 1; }

say "Connecting to '$TARGET' (network id $NETID)…"
wpa_cli -i "$IF" select_network "$NETID" >/dev/null
wpa_cli -i "$IF" enable_network "$NETID"  >/dev/null
wpa_cli -i "$IF" reassociate             >/dev/null

# Wait up to 15s for association
for _ in {1..15}; do
  SSID="$(iwgetid -r || true)"
  STATE="$(wpa_cli -i "$IF" status 2>/dev/null | awk -F= '$1=="wpa_state"{print $2}')"
  [ "$SSID" = "$TARGET" ] && [ "$STATE" = "COMPLETED" ] && break
  sleep 1
done
SSID="$(iwgetid -r || true)"
[ "$SSID" = "$TARGET" ] || { err "Failed to associate to '$TARGET'"; exit 1; }
say "Associated with: $SSID"

# DHCP with small retry loop
say "Requesting IP (DHCP)…"
sudo pkill -f "dhclient $IF" 2>/dev/null || true
sudo dhclient -r "$IF" 2>/dev/null || true
IPV4=""; tries=0
while [ $tries -lt 3 ]; do
  tries=$((tries+1))
  sudo dhclient -v "$IF" | sed 's/^/[dhclient] /' || true
  IPV4="$(ip -4 -o addr show dev "$IF" | awk '{print $4}' | cut -d/ -f1)"
  [ -n "$IPV4" ] && break
  warn "No IPv4 yet… retry $tries/3"
  sleep 2
done
[ -n "$IPV4" ] || { err "No IPv4 lease on $IF after retries"; exit 1; }

# DNS per network
set_dns_for_ssid "$SSID"

echo
say "Connected ✅"
echo "  SSID : $SSID"
echo "  IPv4 : $IPV4"
echo "  DNS  :"
sed 's/^/    /' /etc/resolv.conf
echo

# Quick reachability tests
say "Pinging 8.8.8.8…"
ping -c 3 -W 2 8.8.8.8 || warn "8.8.8.8 ping failed"

say "Pinging google.com…"
if ! ping -c 3 -W 3 google.com; then
  warn "DNS ping failed. Current /etc/resolv.conf:"
  sed 's/^/    /' /etc/resolv.conf
fi

# SSH fixes (fast handshake + dual ports)
say "Applying SSH fixes (UseDNS no, GSSAPIAuthentication no; Ports 22 & 2222)…"
fix_sshd

echo
say "🎉 Setup Complete!"
echo
say "📡 WiFi Status:"
echo "  SSID : $SSID"
echo "  IPv4 : $IPV4"
echo "  DNS  :"
sed 's/^/    /' /etc/resolv.conf
echo
say "🔐 SSH Access:"
echo "  Port 22  : ssh pi@$IPV4"
echo "  Port 2222: ssh -p 2222 pi@$IPV4"
echo
say "📋 Next Steps:"
echo "  1. Test SSH: ssh pi@$IPV4"
echo "  2. If port 22 blocked: ssh -p 2222 pi@$IPV4"
echo "  3. Configure ANU password if not done: sudo nano $CONF"
echo

say "Done."
