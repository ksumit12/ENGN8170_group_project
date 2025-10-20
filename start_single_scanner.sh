#!/bin/bash
# Ultra-simple single scanner startup
# Just detect beacons - no complex FSM

cd "$(dirname "$0")"

echo "Cleaning up..."
sudo pkill -9 -f boat_tracking 2>/dev/null || true
sudo pkill -9 -f "python3.*boat_tracking" 2>/dev/null || true
sudo fuser -k 5000/tcp 2>/dev/null || true
sudo fuser -k 8000/tcp 2>/dev/null || true

# Restart Bluetooth to clear any BLE adapter locks
echo "Restarting Bluetooth service..."
sudo systemctl restart bluetooth
sleep 3

echo " Starting simple single-scanner mode..."

# Ultra-simple config
export SINGLE_SCANNER=1
export SCANNER_ID=gate-outer
export PRESENCE_ACTIVE_WINDOW_S=10  # 10 seconds timeout

# Force single scanner config
export SCANNER_CONFIG=system/json/scanner_config.single.json

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Start the system - it will auto-start the scanner
# Press Ctrl+C to stop, or use ./stop_scanner.sh from another terminal
echo ""
echo "Starting system... Press Ctrl+C to stop"
echo "Or run ./stop_scanner.sh from another terminal"
echo ""

sudo -E python3 boat_tracking_system.py --api-port 8000 --web-port 5000

