#!/bin/bash
# Simple script to start everything on Raspberry Pi

echo "Starting Boat Tracking System..."

# Kill any existing processes
echo "Stopping any existing processes..."
pkill -f "boat_tracking_system.py" 2>/dev/null || true
pkill -f "ngrok" 2>/dev/null || true

# Wait a moment
sleep 2

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Start the boat tracking system in background
echo "Starting boat tracking system..."
python3 boat_tracking_system.py --api-port 8000 --web-port 5000 &
BOAT_PID=$!

# Wait for the system to start
echo "Waiting for system to start..."
sleep 5

# Check if the system is running
if ! kill -0 $BOAT_PID 2>/dev/null; then
    echo "ERROR: Boat tracking system failed to start!"
    exit 1
fi

# Start ngrok tunnel
echo "Starting ngrok tunnel..."
ngrok start boat-tracking --config ngrok.yml &
NGROK_PID=$!

# Wait for ngrok to start
sleep 3

echo ""
echo "=============================================="
echo "SYSTEM STARTED SUCCESSFULLY!"
echo "=============================================="
echo ""
echo "Local access: http://localhost:5000"
echo "ngrok dashboard: http://localhost:4040"
echo ""
echo "Your public URL will be shown in the ngrok dashboard"
echo "Check: https://dashboard.ngrok.com/tunnels"
echo ""
echo "Press Ctrl+C to stop everything"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Stopping system..."
    kill $BOAT_PID 2>/dev/null || true
    kill $NGROK_PID 2>/dev/null || true
    pkill -f "boat_tracking_system.py" 2>/dev/null || true
    pkill -f "ngrok" 2>/dev/null || true
    echo "System stopped."
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Wait for user to stop
wait
