#!/bin/bash
# Single Scanner Demo Startup Script
# This script starts the boat tracking system in single-scanner fallback mode

cd "$(dirname "$0")"

# Stop any existing instances
echo "Stopping existing processes..."
sudo pkill -9 -f boat_tracking 2>/dev/null || true
sudo pkill -9 -f "python3.*boat_tracking" 2>/dev/null || true
sudo fuser -k 5000/tcp 2>/dev/null || true
sudo fuser -k 8000/tcp 2>/dev/null || true

# Stop any active BLE scans and reset adapters
echo "Resetting BLE adapters..."
sudo timeout 2 bluetoothctl scan off 2>/dev/null || true
sudo systemctl restart bluetooth
sleep 3
sudo hciconfig hci0 down 2>/dev/null || true
sudo hciconfig hci1 down 2>/dev/null || true
sleep 1
sudo hciconfig hci0 up 2>/dev/null || true
sudo hciconfig hci1 up 2>/dev/null || true
sleep 2

# Set environment variables for single-scanner mode
export SINGLE_SCANNER=1
export SCANNER_ID=gate-outer  # or gate-inner, depending on which scanner you want to use
# Short window so boats flip to OUT quickly when beacon powers off
export PRESENCE_ACTIVE_WINDOW_S=12

# Activate virtual environment
source .venv/bin/activate

# Start the system
sudo -E python3 boat_tracking_system.py --api-port 8000 --web-port 5000

