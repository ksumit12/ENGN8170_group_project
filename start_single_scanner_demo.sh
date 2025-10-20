#!/bin/bash
# Single Scanner Demo Startup Script
# This script starts the boat tracking system in single-scanner fallback mode

cd "$(dirname "$0")"

echo "============================================"
echo "  Boat Tracking System - Single Scanner"
echo "============================================"
echo ""

# ========== CLEANUP ==========
echo "[1/5] Stopping existing processes..."
sudo pkill -9 -f boat_tracking 2>/dev/null || true
sudo pkill -9 -f "python3.*boat_tracking" 2>/dev/null || true
echo "      Done."

echo "[2/5] Freeing ports 5000 and 8000..."
sudo fuser -k 5000/tcp 2>/dev/null || true
sudo fuser -k 8000/tcp 2>/dev/null || true
echo "      Done."

# ========== BLE RESET ==========
echo "[3/5] Resetting BLE adapters..."
sudo timeout 2 bluetoothctl scan off 2>/dev/null || true
sudo systemctl restart bluetooth
sleep 2
sudo hciconfig hci0 down 2>/dev/null || true
sudo hciconfig hci1 down 2>/dev/null || true
sleep 1
sudo hciconfig hci0 up 2>/dev/null || true
sudo hciconfig hci1 up 2>/dev/null || true
sleep 2
echo "      Done."

# ========== CONFIGURATION ==========
echo "[4/5] Setting environment variables..."
export SINGLE_SCANNER=1
export SCANNER_ID=gate-outer
export PRESENCE_ACTIVE_WINDOW_S=12
echo "      SINGLE_SCANNER=1"
echo "      SCANNER_ID=gate-outer"
echo "      PRESENCE_ACTIVE_WINDOW_S=12"

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "      Virtual environment activated"
fi
echo "      Done."

# ========== START SYSTEM ==========
echo "[5/5] Starting system..."
echo ""
echo "============================================"
echo "  System Starting..."
echo "  API Server: http://172.20.10.12:8000"
echo "  Dashboard:  http://172.20.10.12:5000"
echo ""
echo "  Press Ctrl+C to stop"
echo "  Or run ./stop_scanner.sh from another terminal"
echo "============================================"
echo ""

sudo -E python3 boat_tracking_system.py --api-port 8000 --web-port 5000

