#!/bin/bash

echo "KILLING ALL BOAT TRACKING SERVERS AND PROCESSES"
echo "==============================================="

# Function to kill processes by name pattern
kill_processes() {
    local pattern="$1"
    local description="$2"
    
    echo "Looking for $description..."
    
    # Find PIDs
    local pids=$(pgrep -f "$pattern" 2>/dev/null)
    
    if [ -n "$pids" ]; then
        echo "  Found PIDs: $pids"
        echo "  Killing $description..."
        
        # Try graceful kill first
        kill -TERM $pids 2>/dev/null
        sleep 2
        
        # Force kill if still running
        local remaining=$(pgrep -f "$pattern" 2>/dev/null)
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

# Kill all boat tracking related processes
echo ""
echo "KILLING BOAT TRACKING PROCESSES"
echo "-------------------------------"

kill_processes "boat_tracking_system.py" "Boat Tracking System"
kill_processes "api_server.py" "API Server"
kill_processes "ble_scanner.py" "BLE Scanner"
kill_processes "simple_boat_tracker.py" "Simple Boat Tracker"
kill_processes "ble_beacon_detector.py" "BLE Beacon Detector"
kill_processes "boat_tracker.py" "Boat Tracker"

# Kill only boat tracking Flask processes
echo ""
echo "KILLING BOAT TRACKING FLASK PROCESSES"
echo "-------------------------------------"

# Only kill Flask processes that are specifically boat tracking related
kill_processes "python.*flask.*boat" "Boat tracking Flask apps"
kill_processes "python.*app.*boat" "Boat tracking apps"

# Kill processes by port
echo ""
echo "KILLING PROCESSES BY PORT"
echo "-------------------------"

kill_port "5000" "Web Dashboard"
kill_port "8000" "API Server"
kill_port "8001" "API Server (Alt)"
kill_port "8002" "API Server (Alt2)"

# Kill any remaining Python processes that might be related
echo ""
echo "KILLING REMAINING BOAT TRACKING PYTHON PROCESSES"
echo "------------------------------------------------"

# Be very specific - only kill if they contain exact boat tracking script names
local boat_python_pids=$(pgrep -f "python.*\(boat_tracking_system\|simple_boat_tracker\|ble_beacon_detector\|boat_tracker\|api_server\|ble_scanner\)" 2>/dev/null)
if [ -n "$boat_python_pids" ]; then
    echo "  Found boat tracking Python processes: $boat_python_pids"
    kill -TERM $boat_python_pids 2>/dev/null
    sleep 2
    kill -KILL $boat_python_pids 2>/dev/null
    echo "  Boat tracking Python processes killed"
else
    echo "  No boat tracking Python processes found"
fi

# Kill any processes using BLE or beacon keywords (but be specific)
echo ""
echo "KILLING BLE/BEACON PROCESSES"
echo "----------------------------"

# Only kill if they're specifically related to our boat tracking
kill_processes "python.*bleak" "Bleak BLE library in boat tracking"
kill_processes "python.*beacon" "Beacon processes in boat tracking"

# Final cleanup - kill any remaining processes that might be hanging
echo ""
echo "FINAL CLEANUP"
echo "-------------"

# Kill any zombie processes (but be very specific to avoid killing system processes)
echo "  Cleaning up zombie boat tracking processes..."
ps aux | grep -E "(boat_tracking_system|simple_boat_tracker|ble_beacon_detector|boat_tracker|api_server|ble_scanner)" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null

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

# Show remaining processes
echo ""
echo "REMAINING PROCESSES"
echo "-------------------"

echo "  Python processes:"
ps aux | grep python | grep -v grep | head -5

echo ""
echo "  Flask processes:"
ps aux | grep flask | grep -v grep

echo ""
echo "  Processes using common ports:"
netstat -tulpn | grep -E ":(5000|8000|8001|8002)" 2>/dev/null || echo "  No processes found on common ports"

echo ""
echo "CLEANUP COMPLETE!"
echo "================="
echo ""
echo "You can now start your preferred system:"
echo "  Old System:  python3 simple_boat_tracker.py"
echo "  New System:  python3 boat_tracking_system.py --api-port 8000 --web-port 5000"
echo ""

