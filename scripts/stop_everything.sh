#!/bin/bash

# Stop Everything Script for Boat Tracking System
# Kills all boat tracking related processes and frees up ports

echo " Stopping Boat Tracking System..."

# Function to kill process by name
kill_process() {
    local process_name="$1"
    local pids=$(pgrep -f "$process_name")
    
    if [ -n "$pids" ]; then
        echo "  Killing $process_name (PIDs: $pids)"
        kill $pids 2>/dev/null
        sleep 2
        
        # Force kill if still running
        pids=$(pgrep -f "$process_name")
        if [ -n "$pids" ]; then
            echo "  Force killing $process_name (PIDs: $pids)"
            
            kill -9 $pids 2>/dev/null
        fi
    else
        echo "  $process_name not running"
    fi
}

# Kill main system processes
echo " Stopping main system processes..."
kill_process "boat_tracking_system.py"
kill_process "api_server.py"
kill_process "scanner_service.py"
kill_process "ble_scanner.py"

# Kill simulator processes
echo " Stopping simulator processes..."
kill_process "sim_run_simulator.py"
kill_process "sim_seed_data.py"
kill_process "beacon_simulator.py"

# Kill ngrok if running
echo " Stopping ngrok tunnel..."
kill_process "ngrok"

# Kill any Python processes that might be related
echo " Stopping related Python processes..."
kill_process "python3.*boat"
kill_process "python3.*scanner"
kill_process "python3.*sim"

# Free up common ports
echo " Freeing up ports..."
for port in 5000 8000 8001 5001; do
    pid=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pid" ]; then
        echo "  Killing process on port $port (PID: $pid)"
        kill $pid 2>/dev/null
    fi
done

# Wait a moment for cleanup
sleep 2

# Check if any processes are still running
echo " Checking for remaining processes..."
remaining=$(pgrep -f "boat_tracking_system\|api_server\|scanner_service\|ble_scanner\|sim_run_simulator\|ngrok" | wc -l)

if [ "$remaining" -eq 0 ]; then
    echo " All processes stopped successfully!"
else
    echo "  Some processes may still be running:"
    pgrep -f "boat_tracking_system\|api_server\|scanner_service\|ble_scanner\|sim_run_simulator\|ngrok" | xargs ps -p
    echo " You may need to run: sudo pkill -f 'boat_tracking_system|api_server|scanner_service|ble_scanner|sim_run_simulator|ngrok'"
fi

echo " Stop script completed!"
echo ""
echo "To restart the system:"
echo "  source .venv/bin/activate"
echo "  python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000"