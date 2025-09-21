#!/bin/bash
# Check if everything is running

echo "Boat Tracking System Status"
echo "============================"

# Check boat tracking system
if pgrep -f "boat_tracking_system.py" > /dev/null; then
    echo "Boat tracking system: RUNNING"
else
    echo "Boat tracking system: NOT RUNNING"
fi

# Check ngrok
if pgrep -f "ngrok" > /dev/null; then
    echo "ngrok tunnel: RUNNING"
else
    echo "ngrok tunnel: NOT RUNNING"
fi

# Check if local server is responding
if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo "Local website: ACCESSIBLE (http://localhost:5000)"
else
    echo "Local website: NOT ACCESSIBLE"
fi

# Check ngrok dashboard
if curl -s http://localhost:4040 > /dev/null 2>&1; then
    echo "ngrok dashboard: ACCESSIBLE (http://localhost:4040)"
else
    echo "ngrok dashboard: NOT ACCESSIBLE"
fi

echo ""
echo "To start everything: ./start_everything.sh"
echo "To stop everything: ./stop_everything.sh"
