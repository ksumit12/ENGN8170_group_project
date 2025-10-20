#!/bin/bash
# Stop all boat tracking processes

echo "Stopping boat tracking system..."

# Kill all related processes
sudo pkill -9 -f boat_tracking 2>/dev/null
sudo pkill -9 -f "python3.*boat_tracking" 2>/dev/null
sudo pkill -9 -f ble_scanner 2>/dev/null

# Free up ports
sudo fuser -k 5000/tcp 2>/dev/null
sudo fuser -k 8000/tcp 2>/dev/null

# Wait a moment
sleep 1

# Check if anything is still running
REMAINING=$(ps aux | grep -E "(boat_tracking|python3.*boat_tracking)" | grep -v grep | wc -l)

if [ $REMAINING -eq 0 ]; then
    echo "All processes stopped successfully!"
else
    echo "Warning: Some processes may still be running"
    ps aux | grep -E "(boat_tracking|python3.*boat_tracking)" | grep -v grep
fi

