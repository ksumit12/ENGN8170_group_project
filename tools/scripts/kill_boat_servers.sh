#!/bin/bash

echo "KILLING BOAT TRACKING SERVERS ONLY"
echo "==================================="

# Function to kill processes by exact name
kill_exact_process() {
    local script_name="$1"
    local description="$2"
    
    echo "Looking for $description..."
    
    # Find PIDs for exact script name
    local pids=$(pgrep -f "$script_name" 2>/dev/null)
    
    if [ -n "$pids" ]; then
        echo "  Found PIDs: $pids"
        echo "  Killing $description..."
        
        # Try graceful kill first
        kill -TERM $pids 2>/dev/null
        sleep 2
        
        # Force kill if still running
        local remaining=$(pgrep -f "$script_name" 2>/dev/null)
        if [ -n "$remaining" ]; then
            echo "  Force killing remaining processes..."
            kill -KILL $remaining 2>/dev/null
        fi
        
        echo "  $description killed"
    else
        echo "  No $description processes found"
    fi
}

# Function to kill processes by port
kill_port() {
    local port="$1"
    local description="$2"
    
    echo "Looking for processes on port $port ($description)..."
    
    # Find PIDs using the port
    local pids=$(lsof -ti:$port 2>/dev/null)
    
    if [ -n "$pids" ]; then
        echo "  Found PIDs using port $port: $pids"
        echo "  Killing processes on port $port..."
        
        # Try graceful kill first
        kill -TERM $pids 2>/dev/null
        sleep 2
        
        # Force kill if still running
        local remaining=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$remaining" ]; then
            echo "  Force killing remaining processes on port $port..."
            kill -KILL $remaining 2>/dev/null
        fi
        
        echo "  Port $port cleared"
    else
        echo "  No processes found on port $port"
    fi
}

# Kill specific boat tracking scripts
echo ""
echo "KILLING BOAT TRACKING SCRIPTS"
echo "-----------------------------"

kill_exact_process "boat_tracking_system.py" "Boat Tracking System"
kill_exact_process "api_server.py" "API Server"
kill_exact_process "ble_scanner.py" "BLE Scanner"
kill_exact_process "simple_boat_tracker.py" "Simple Boat Tracker"
kill_exact_process "ble_beacon_detector.py" "BLE Beacon Detector"
kill_exact_process "boat_tracker.py" "Boat Tracker"

# Kill processes by port (these are the ports we know our systems use)
echo ""
echo "KILLING PROCESSES BY PORT"
echo "-------------------------"

kill_port "5000" "Web Dashboard"
kill_port "8000" "API Server"
kill_port "8001" "API Server (Alt)"
kill_port "8002" "API Server (Alt2)"

# Check if ports are still in use
echo ""
echo "CHECKING PORTS"
echo "--------------"

check_port() {
    local port="$1"
    local status=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$status" ]; then
        echo "  Port $port is still in use by PID: $status"
    else
        echo "  Port $port is free"
    fi
}

check_port "5000"
check_port "8000"
check_port "8001"
check_port "8002"

echo ""
echo "CLEANUP COMPLETE!"
echo "================="
echo ""
echo "You can now start your preferred system:"
echo "  Old System:  python3 simple_boat_tracker.py"
echo "  New System:  python3 boat_tracking_system.py --api-port 8000 --web-port 5000"
echo ""

