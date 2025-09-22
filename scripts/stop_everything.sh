#!/bin/bash
# Simple script to stop everything

echo "Stopping Boat Tracking System..."

# Kill all related processes
pkill -f "boat_tracking_system.py" 2>/dev/null || true
pkill -f "ngrok" 2>/dev/null || true

# Wait a moment
sleep 2

echo "All processes stopped."
