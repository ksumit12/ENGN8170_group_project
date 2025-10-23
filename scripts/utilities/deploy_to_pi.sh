#!/bin/bash
# Deploy wifi_auto.sh to Raspberry Pi
# Usage: ./deploy_to_pi.sh [PI_IP_ADDRESS]

set -euo pipefail

PI_IP="${1:-10.20.99.155}"
SCRIPT_NAME="wifi_auto.sh"
PI_USER="pi"

echo " Deploying wifi_auto.sh to Raspberry Pi at $PI_IP"
echo

# Check if script exists
if [ ! -f "$SCRIPT_NAME" ]; then
    echo " Error: $SCRIPT_NAME not found in current directory"
    exit 1
fi

# Test connectivity
echo " Testing connectivity to $PI_IP..."
if ! ping -c 3 -W 5 "$PI_IP" >/dev/null 2>&1; then
    echo " Error: Cannot reach $PI_IP"
    echo "   Make sure the Pi is powered on and connected to network"
    exit 1
fi
echo " Pi is reachable"

# Try SSH connection
echo " Testing SSH connection..."
if ssh -o ConnectTimeout=10 -o BatchMode=yes "$PI_USER@$PI_IP" exit 2>/dev/null; then
    echo " SSH connection successful"
else
    echo "  SSH connection failed - this is expected if SSH is not configured yet"
    echo "   The wifi_auto.sh script will configure SSH for you"
fi

# Copy script to Pi
echo " Copying $SCRIPT_NAME to Pi..."
if scp "$SCRIPT_NAME" "$PI_USER@$PI_IP:/home/$PI_USER/" 2>/dev/null; then
    echo " Script copied successfully"
else
    echo " Failed to copy script via SCP"
    echo "   You may need to copy it manually or configure SSH first"
    exit 1
fi

# Make script executable and run it
echo " Making script executable and running setup..."
ssh "$PI_USER@$PI_IP" << 'EOF'
chmod +x wifi_auto.sh
echo "Running wifi_auto.sh setup..."
sudo ./wifi_auto.sh
EOF

echo
echo " Deployment complete!"
echo
echo " Next steps:"
echo "  1. SSH to your Pi: ssh pi@$PI_IP"
echo "  2. If port 22 is blocked: ssh -p 2222 pi@$PI_IP"
echo "  3. Configure ANU password: sudo nano /etc/wpa_supplicant/wpa_supplicant.conf"
echo
echo " To check Pi IP after WiFi setup:"
echo "   ssh pi@$PI_IP 'ip addr show wlan0'"





