#!/bin/bash
# Stop Script - Cleanly stops all boat tracking processes

echo "============================================"
echo "  Stopping Boat Tracking System"
echo "============================================"
echo ""

# Kill all boat tracking processes
echo "[1/4] Stopping boat tracking processes..."
sudo pkill -9 -f boat_tracking 2>/dev/null || true
sudo pkill -9 -f "python3.*boat_tracking" 2>/dev/null || true
echo "      Done."

# Free up ports
echo "[2/4] Freeing ports 5000 and 8000..."
sudo fuser -k 5000/tcp 2>/dev/null || true
sudo fuser -k 8000/tcp 2>/dev/null || true
echo "      Done."

# Stop any BLE scans
echo "[3/4] Stopping BLE scans..."
sudo timeout 2 bluetoothctl scan off 2>/dev/null || true
echo "      Done."

# Wait for cleanup
echo "[4/4] Waiting for cleanup..."
sleep 2
echo "      Done."

echo ""
echo "============================================"
echo "  All processes stopped!"
echo "============================================"
echo ""

# Check if anything is still running
REMAINING=$(ps aux | grep -E "(boat_tracking|python3.*boat_tracking)" | grep -v grep | wc -l)
if [ $REMAINING -gt 0 ]; then
    echo "WARNING: Some processes may still be running:"
    ps aux | grep -E "(boat_tracking|python3.*boat_tracking)" | grep -v grep
else
    echo "System fully stopped and ready for restart."
fi

