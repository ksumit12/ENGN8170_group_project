# Rowing Boat Tracking System

Multi-beacon BLE system for tracking boat presence and managing beacon-to-boat assignments. The system supports 30–40 boats with unique BLE beacons and provides a web dashboard and REST API.

## Overview

- Multi-scanner BLE ingestion (filtering to iBeacon frames)
- Database-backed boats, beacons, assignments, and detection history (SQLite by default)
- Web dashboard for presence and management
- REST API for integrations

## Prerequisites

- Python 3.10+
- Linux with BLE support (BlueZ). Ensure your user can access the BLE adapter.

## Installation

```bash
pip install -r requirements.txt
```

##  ONE COMMAND SETUP (Fresh RPi)

```bash
# 1. Activate virtual environment (FIRST STEP after SSH)
source .venv/bin/activate

# 2. Clone and setup everything
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project
chmod +x setup_rpi.sh
./setup_rpi.sh

# 3. Start the system
./start_system.sh
```

**Your static URL**: `https://boat-tracking-ksumit12.ngrok.io` (NEVER CHANGES!)

## Quick Start (Already Setup)

### Local Development
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run the system (web dashboard)
python3 boat_tracking_system.py --api-port 8000 --web-port 5000

# 2. Run with terminal display (HDMI monitor)
python3 boat_tracking_system.py --display-mode terminal

# 2. Run with both web and terminal display
python3 boat_tracking_system.py --display-mode both --api-port 8000 --web-port 5000
```

### Public Access
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Start the system
./start_system.sh
```

## Initial Setup

Initialize the database and sample data:

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Initialize database
python3 setup_new_system.py
```

This creates `boat_tracking.db` with sample boats and beacons for testing.

## Running

### Full system (orchestrator)

Starts API server, two scanners (inner/outer), and the web dashboard.

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run the system (web dashboard)
python3 boat_tracking_system.py

# 2. Run with terminal display (HDMI monitor)
python3 boat_tracking_system.py --display-mode terminal

# 2. Run with both web and terminal display
python3 boat_tracking_system.py --display-mode both
```

Defaults:
- API Server: http://localhost:8000
- Web Dashboard: http://localhost:5000 (when display-mode is 'web' or 'both')
- Terminal Display: Active on HDMI output (when display-mode is 'terminal' or 'both')

You can also override ports:

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run with custom ports
python3 boat_tracking_system.py --api-port 8001 --web-port 5001
```

### Components separately

API server only:

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run API server
python3 api_server.py --port 8000
```

Scanner (run one per scanner location):

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run scanners
python3 ble_scanner.py --scanner-id gate-outer --server-url http://localhost:8000
python3 ble_scanner.py --scanner-id gate-inner --server-url http://localhost:8000
```

## Registering a New Beacon

1. Open the web dashboard at http://localhost:5000
2. Click “Register New Beacon”
3. Click “Start Scanning” – only iBeacon devices are listed
4. Select your beacon (name and MAC are shown), complete boat details, save

The beacon is assigned to the boat and appears on the dashboard and in the API.

## Display Modes

The system supports multiple display options for different use cases:

### Web Dashboard (Default)
- **Mode**: `--display-mode web` (default)
- **Access**: Browser at http://localhost:5000
- **Features**: Full interactive dashboard with boat management, beacon registration, logs
- **Best for**: Remote access, management tasks, detailed monitoring

### Terminal Display (HDMI Monitor)
- **Mode**: `--display-mode terminal`
- **Access**: Direct HDMI output on Raspberry Pi
- **Features**: 
  - Real-time boat status board with color-coded status indicators
  - Automatic updates every 3 seconds
  - Boat name, class, status, last seen time, signal strength
  - Currently in shed summary
  - System status information
  - Clean, readable format optimized for monitors
- **Best for**: Headless RPi with HDMI monitor, simple status display, kiosk mode

### Both Modes
- **Mode**: `--display-mode both`
- **Access**: Web dashboard + HDMI terminal display simultaneously
- **Features**: Full web functionality + live terminal display
- **Best for**: RPi with monitor + remote access, comprehensive monitoring

### Usage Examples

```bash
# Web dashboard only (default)
python3 boat_tracking_system.py

# Terminal display only (HDMI monitor)
python3 boat_tracking_system.py --display-mode terminal

# Both web and terminal display
python3 boat_tracking_system.py --display-mode both --api-port 8000 --web-port 5000
```

## Features

- iBeacon-only filtering at the scanner level (Apple manufacturer data 0x004C, subtype 0x02 0x15)
- Beacon discovery and registration workflow
- One active beacon per boat enforced by the database
- Presence summary and recent detections
- Multiple display modes (web, terminal, both)

## REST API (selected)

```
POST /api/v1/detections              # Scanner → server observations
GET  /api/v1/boats                   # List boats
POST /api/v1/boats                   # Create boat
POST /api/v1/boats/{id}/assign-beacon
GET  /api/v1/beacons                 # List beacons
GET  /api/v1/presence                # Presence summary
GET  /health                         # Health check
```

## Project Structure

```
grp_project/
├── boat_tracking_system.py    # Main orchestrator (API + scanners + dashboard)
├── api_server.py              # REST API (Flask) and presence endpoints
├── ble_scanner.py             # BLE scanner (filters iBeacon) and posts detections
├── app/                       # Core application modules
│   ├── database_models.py     # SQLite models and CRUD
│   ├── entry_exit_fsm.py      # Entry/exit finite state machine
│   ├── admin_service.py       # Admin operations service
│   └── logging_config.py      # Centralized logging configuration
├── requirements.txt           # Python dependencies
├── data/                      # Database and logs directory
│   ├── boat_tracking.db      # SQLite database
│   └── logs/                 # System logs
├── scripts/                   # Operational scripts (start/stop/status/setup)
│   ├── start_everything.sh    # Start API, dashboard, and ngrok
│   ├── stop_everything.sh     # Stop processes
│   ├── check_status.sh        # Health/status snapshot
│   ├── start_public.sh        # Start with public tunnel
│   ├── setup_rpi.sh           # One-command setup on fresh RPi
│   └── reserve_domain.sh      # Helper to reserve ngrok domain
├── system/
│   └── json/                  # Runtime JSON configuration
│       ├── scanner_config.json
│       ├── scanner_config.example.json
│       └── settings.json
├── tools/                     # Developer utilities
│   ├── ble_testing/          # BLE scanner testing tools
│   │   ├── identify_ble_dongles.py
│   │   ├── scanner_range_test.py
│   │   ├── ble_scanner_tester.py
│   │   └── BLE_TESTING_GUIDE.md
│   └── network/              # Network helpers
│       ├── get_ip.py
│       ├── start_network.sh
│       └── configure_firewall.sh
└── README.md                  # This file
```

## Tools and Utilities

### BLE Testing Tools (`tools/ble_testing/`)
- Test BLE dongle range and performance
- Identify available BLE adapters
- Compare multiple scanners

### Network Access Tools (`tools/network/`)
- Make system accessible from other devices
- Configure firewall for network access
- Get Raspberry Pi IP address

### Utility Scripts (`tools/scripts/`)
- Kill system processes and free ports
- Clean up running services

## Troubleshooting

- **Port in use (8000/5000)**: use `./tools/scripts/kill_boat_servers.sh` to stop previous runs
- **BLE permissions**: ensure your user can access the BLE adapter (Bluetooth group or run with appropriate permissions)
- **No beacons listed**: ensure your device is broadcasting iBeacon frames
- **Network access issues**: use `./tools/network/get_ip.py` to get RPi IP and `./tools/network/configure_firewall.sh` to configure firewall
- **BLE range testing**: use `./tools/ble_testing/scanner_range_test.py` to test dongle range
- **Terminal display issues**: 
  - Ensure HDMI monitor is connected and powered on
  - Check that display mode is set correctly: `--display-mode terminal`
  - For headless RPi, ensure HDMI output is enabled in `/boot/config.txt`
  - Terminal display updates every 3 seconds - be patient if data appears delayed

## Development Notes

- The scanner captures device local name and MAC and forwards them to the server.
- The web dashboard lists only beacons not yet assigned during registration.

---

For migration details from the old single-beacon scripts, see `MIGRATION_GUIDE.md`.

## Multi-Gate Architecture (Hardware Isolation)

This system now separates hardware scanning from the API/FSM/dashboard so you can scale to multiple gates and tune each scanner independently.

- Hardware daemon: `scanner_service.py`
  - Talks to BLE adapters only (hci0/hci1/...).
  - Posts observations to the API at `/api/v1/detections`.
  - Supports multi-gate config and per-scanner tuning via `rssi_threshold` and `rssi_bias_db`.
- API + FSM + Dashboard: `boat_tracking_system.py` (or `api_server.py` for API only)
  - Consumes observations, runs entry/exit FSM, updates DB, serves UI.

### Config for multi-gate scanning
Create a file `scanner_config.json`:

```json
{
  "api_host": "localhost",
  "api_port": 8000,
  "gates": [
    {
      "id": "gate-1",
      "hysteresis": { "enter_dbm": -58, "exit_dbm": -64, "min_hold_ms": 1200 },
      "scanners": [
        { "id": "gate-1-left",  "adapter": "hci0", "rssi_threshold": -60, "rssi_bias_db": 0 },
        { "id": "gate-1-right", "adapter": "hci1", "rssi_threshold": -55, "rssi_bias_db": 0 }
      ]
    }
  ]
}
```

- `rssi_threshold`: base cutoff per scanner (dBm)
- `rssi_bias_db`: software bias to emulate scan power tuning (negative expands zone, positive tightens)

### Run
- Start API/UI (on RPi):
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Start API/UI
python3 boat_tracking_system.py --api-port 8000 --web-port 5000
```
- Start hardware daemon (same host):
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Start scanner service
python3 scanner_service.py --config system/json/scanner_config.json
```

### Logs
- Scanner posts include `gate_id`, `scanner_id`, `adapter` and are logged as detections.
- State changes include `gate_id` in the API response `state_changes`.

### Notes on FSM and gates
- Current FSM supports a single gate by `outer_scanner_id`/`inner_scanner_id` naming.
- Maintenance-aware FSM: when a boat's `op_status` is `MAINTENANCE`, detections are ignored.
- Beacon replacement safety: FSM context resets automatically if a beacon is re-mapped to a different boat.
- Multi-gate isolation: scanners tag `gate_id` and API logs it; per-gate persistence can be added without schema breaks.

### Passage setup quick tips
- Place scanners ~2–4 m apart (USB extension okay). Start with thresholds:
  - Left: `rssi_threshold: -60`
  - Right: `rssi_threshold: -55`
- Adjust `rssi_bias_db` by ±2–5 dB to reduce overlap.
- Verify with logs that each side primarily detects when the tag is closest.