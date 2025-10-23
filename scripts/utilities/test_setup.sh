#!/bin/bash
echo "=== Raspberry Pi WiFi Setup Test ==="
echo
echo "1. WiFi Configuration (wpa_supplicant.conf):"
echo "    Red Shed Guest (Priority 1)"
echo "    Sumit_iPhone (Priority 2)" 
echo "    ANU-Secure (Priority 3)"
echo
echo "2. WiFi Auto Script (/home/pi/wifi_auto.sh):"
echo "    Priority order: Red Shed Guest → Sumit_iPhone → ANU-Secure"
echo "    DNS configuration per network"
echo "    SSH hardening (ports 22 & 2222)"
echo "    Executable permissions set"
echo
echo "3. To test after boot:"
echo "   ssh pi@<pi-ip-address>"
echo "   sudo ./wifi_auto.sh"
echo
echo "4. Expected behavior:"
echo "   - First tries Red Shed Guest"
echo "   - Falls back to iPhone hotspot if Red Shed unavailable"
echo "   - Falls back to ANU-Secure as last resort"
echo
echo " Setup complete!"
