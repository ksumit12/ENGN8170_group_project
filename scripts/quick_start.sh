#!/bin/bash

# Quick Start Script for Boat Tracking System
# Provides easy options to start the system in different modes

echo " Boat Tracking System - Quick Start"
echo "======================================"
echo ""

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo " Virtual environment not activated!"
    echo "Please run: source .venv/bin/activate"
    echo "Then run this script again."
    exit 1
fi

echo " Virtual environment activated: $VIRTUAL_ENV"
echo ""

# Check if database exists
if [ ! -f "data/boat_tracking.db" ]; then
    echo " Database not found. Initializing..."
    python3 setup_new_system.py
    echo " Database initialized!"
    echo ""
fi

# Menu options
echo "Choose your startup mode:"
echo "1) Web Dashboard Only (http://localhost:5000)"
echo "2) HDMI Terminal Display Only"
echo "3) Both Web + Terminal Display"
echo "4) Public Access (ngrok tunnel)"
echo "5) Run Simulator for Testing"
echo "6) Exit"
echo ""

read -p "Enter your choice (1-6): " choice

case $choice in
    1)
        echo " Starting Web Dashboard..."
        python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000
        ;;
    2)
        echo " Starting Terminal Display..."
        python3 boat_tracking_system.py --display-mode terminal
        ;;
    3)
        echo " Starting Both Web + Terminal Display..."
        python3 boat_tracking_system.py --display-mode both --api-port 8000 --web-port 5000
        ;;
    4)
        echo " Starting Public Access..."
        ./scripts/start_public.sh
        ;;
    5)
        echo " Starting Simulator..."
        python3 sim_run_simulator.py
        ;;
    6)
        echo " Goodbye!"
        exit 0
        ;;
    *)
        echo " Invalid choice. Please run the script again."
        exit 1
        ;;
esac












