#!/bin/bash
# iBeacon MAC Scanner using hcitool
# Usage: ./ibeacon_mac_scanner.sh <MAC_ADDRESS> [adapter] [duration]

MAC=${1:-"DC:0D:30:23:05:47"}
ADAPTER=${2:-"hci0"}
DURATION=${3:-30}

echo "iBeacon MAC Scanner"
echo "=================="
echo "Target MAC: $MAC"
echo "Adapter: $ADAPTER"
echo "Duration: $DURATION seconds"
echo "Press Ctrl+C to stop early"
echo ""

# Check if adapter exists and is up
if ! hciconfig $ADAPTER >/dev/null 2>&1; then
    echo "Error: Adapter $ADAPTER not found"
    echo "Available adapters:"
    hciconfig
    exit 1
fi

# Bring adapter up
sudo hciconfig $ADAPTER up

echo "Starting scan for $MAC..."
echo "Time: $(date)"
echo ""

# Start scanning
timeout $DURATION sudo hcitool -i $ADAPTER lescan --duplicates | while read line; do
    if echo "$line" | grep -qi "$MAC"; then
        echo "[$(date '+%H:%M:%S')] FOUND: $line"
    fi
done

echo ""
echo "Scan completed after $DURATION seconds"
