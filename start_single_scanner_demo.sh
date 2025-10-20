#!/bin/bash
# Single Scanner Demo Startup Script
# This script starts the boat tracking system in single-scanner fallback mode

cd "$(dirname "$0")"

# Stop any existing instances
pkill -f boat_tracking

# Wait for processes to stop
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

