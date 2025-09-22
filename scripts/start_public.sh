#!/bin/bash
# Boat Tracking System - Public Access Startup Script

echo " Starting Boat Tracking System with Public Access..."

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo " ngrok not found. Please install ngrok first."
    echo "   Run: curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null"
    echo "   Then: echo 'deb https://ngrok-agent.s3.amazonaws.com buster main' | sudo tee /etc/apt/sources.list.d/ngrok.list"
    echo "   Then: sudo apt update && sudo apt install ngrok"
    exit 1
fi

# Check if auth token is set
if [ ! -f "ngrok.yml" ] || grep -q "YOUR_NGROK_AUTH_TOKEN_HERE" ngrok.yml; then
    echo "  Please set your ngrok auth token in ngrok.yml"
    echo "   Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken"
    echo "   Then edit ngrok.yml and replace YOUR_NGROK_AUTH_TOKEN_HERE with your token"
    exit 1
fi

# Start the boat tracking system in background
echo " Starting boat tracking system..."
python3 boat_tracking_system.py --api-port 8000 --web-port 5000 &
BOAT_PID=$!

# Wait a moment for the system to start
sleep 3

# Start ngrok tunnel
echo " Starting ngrok tunnel..."
ngrok start boat-tracking --config ngrok.yml

# Cleanup function
cleanup() {
    echo " Shutting down..."
    kill $BOAT_PID 2>/dev/null
    pkill -f ngrok 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Wait for user to stop
echo " System running! Press Ctrl+C to stop."
wait
