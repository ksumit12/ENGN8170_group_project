#!/bin/bash
# Start the boat tracking system with beacon simulator

echo "Starting Boat Tracking System with Beacon Simulator..."

# Optional flags:
#   --backfill-days N              # generate N days of synthetic history
#   --backfill-range FROM TO       # ISO range, e.g. 2025-09-20T00:00 2025-09-24T23:59
#   --sessions-per-day N           # sessions per day for backfill (default 2)

BACKFILL_DAYS=""
BACKFILL_FROM=""
BACKFILL_TO=""
SESSIONS_PER_DAY=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backfill-days)
      BACKFILL_DAYS="$2"; shift 2;;
    --backfill-range)
      BACKFILL_FROM="$2"; BACKFILL_TO="$3"; shift 3;;
    --sessions-per-day)
      SESSIONS_PER_DAY="$2"; shift 2;;
    *) shift;;
  esac
done

# Start the main system in the background
python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000 &
MAIN_PID=$!

# Wait a moment for the system to start
sleep 5

# Backfill historical data if requested
if [[ -n "$BACKFILL_DAYS" ]]; then
  echo "Backfilling last $BACKFILL_DAYS days (sessions/day=$SESSIONS_PER_DAY)..."
  python3 tools/backfill_history.py --days "$BACKFILL_DAYS" --sessions-per-day "$SESSIONS_PER_DAY"
fi

if [[ -n "$BACKFILL_FROM" && -n "$BACKFILL_TO" ]]; then
  echo "Backfilling range $BACKFILL_FROM to $BACKFILL_TO (sessions/day=$SESSIONS_PER_DAY)..."
  python3 tools/backfill_history.py --from "$BACKFILL_FROM" --to "$BACKFILL_TO" --sessions-per-day "$SESSIONS_PER_DAY"
fi

# Start the beacon simulator
python3 beacon_simulator.py --interval 30 &
SIMULATOR_PID=$!

echo "System started!"
echo "Main system PID: $MAIN_PID"
echo "Beacon simulator PID: $SIMULATOR_PID"
echo ""
echo "Web dashboard: http://localhost:5000"
echo "Reports: http://localhost:5000/reports"
echo ""
echo "Press Ctrl+C to stop both processes"

# Function to cleanup on exit
cleanup() {
    echo "Stopping processes..."
    kill $MAIN_PID 2>/dev/null
    kill $SIMULATOR_PID 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Wait for processes
wait
