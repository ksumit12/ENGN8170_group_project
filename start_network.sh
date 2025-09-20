#!/bin/bash

echo "STARTING BOAT TRACKING SYSTEM FOR NETWORK ACCESS"
echo "================================================"

# Get the IP address
echo "Getting Raspberry Pi IP address..."
python3 get_ip.py

echo ""
echo "Starting Boat Tracking System..."
echo "The system will be accessible from any device on your network"
echo "Press Ctrl+C to stop the system"
echo ""

# Start the boat tracking system
python3 boat_tracking_system.py --api-port 8000 --web-port 5000
