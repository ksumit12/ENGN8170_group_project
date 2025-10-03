# Rowing Boat Tracking System

Multi-beacon BLE system for tracking boat presence and managing beacon-to-boat assignments. The system supports 30–40 boats with unique BLE beacons and provides a web dashboard and REST API.

## Overview

- Multi-scanner BLE ingestion (filtering to iBeacon frames)
- Database-backed boats, beacons, assignments, and detection history (SQLite by default)
- Web dashboard for presence and management
- REST API for integrations
- **NEW**: Trip tracking and water time analytics
- **NEW**: Multiple display modes (web dashboard + HDMI terminal display)

## Prerequisites

- Python 3.10+
- Linux with BLE support (BlueZ). Ensure your user can access the BLE adapter.
- Raspberry Pi (recommended) with HDMI output for terminal display

## Fresh Raspberry Pi Setup (Complete Guide)

### Step 1: SSH into Raspberry Pi
```bash
ssh pi@<RPI_IP> -p 2222
```

### Step 2: One-Command Setup
```bash
# Clone the repository
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project

# Make setup script executable and run it
chmod +x scripts/setup_rpi.sh
./scripts/setup_rpi.sh
```

### Step 3: Activate Environment and Start System
```bash
# Activate virtual environment (REQUIRED before any commands)
source .venv/bin/activate

# Initialize database with sample data
python3 setup_new_system.py

# Start the system (choose your preferred mode)
```

## Running the System

### Option 1: Web Dashboard Only (Default)
```bash
# Activate environment first
source .venv/bin/activate

# Start web dashboard
python3 boat_tracking_system.py --api-port 8000 --web-port 5000
```
- **Access**: http://localhost:5000 (or http://<RPI_IP>:5000 from other devices)
- **Features**: Full interactive dashboard, boat management, beacon registration, trip analytics

### Option 2: HDMI Terminal Display Only
```bash
# Activate environment first
source .venv/bin/activate

# Start terminal display (HDMI monitor)
python3 boat_tracking_system.py --display-mode terminal
```
- **Access**: Direct HDMI output on Raspberry Pi
- **Features**: Real-time boat status board, color-coded status indicators, automatic updates

### Option 3: Both Web + Terminal Display
```bash
# Activate environment first
source .venv/bin/activate

# Start both web and terminal display
python3 boat_tracking_system.py --display-mode both --api-port 8000 --web-port 5000
```
- **Access**: Web dashboard + HDMI terminal display simultaneously
- **Features**: Full web functionality + live terminal display

### Option 4: Public Access (ngrok tunnel)
```bash
# Activate environment first
source .venv/bin/activate

# Start with public tunnel
./scripts/start_public.sh
```
- **Access**: Public URL via ngrok tunnel
- **Static URL**: `https://boat-tracking-ksumit12.ngrok.io` (NEVER CHANGES!)

## Stopping the System

### Quick Stop (All Processes)
```bash
# Stop all boat tracking processes
./scripts/stop_everything.sh
```

### Manual Stop
```bash
# Kill specific processes
pkill -f boat_tracking_system.py
pkill -f scanner_service.py
pkill -f sim_run_simulator.py
```

## Physical Hardware Setup

### BLE Scanner Placement
You need **two BLE scanners** with 2m USB extensions:

1. **Inner Scanner (gate-inner)**:
   - Place **inside the shed**
   - Mount on wall/post inside, ~1m from boat storage area
   - Should detect boats when fully inside

2. **Outer Scanner (gate-outer)**:
   - Place **outside the shed**
   - Mount on external wall/post, ~1m from water access point
   - Should detect boats when on water side

### BLE Beacon Configuration
Configure your beacons for **~1-1.5 meter detection radius**:
- **Transmission Power**: Medium/low (not maximum)
- **Advertising Interval**: 100-200ms (faster = more frequent detections)
- **Range**: ~1m detection radius per scanner

### Testing Setup
1. **Test Range**: Place beacon at different distances from each scanner
2. **Verify Sequence**: Walk beacon from inside → outside and confirm detection sequence
3. **Check FSM**: Verify state transitions in web dashboard

## New Features

### Trip Tracking & Analytics
- **Water Time Today**: New column showing total minutes each boat spent on water today
- **Trip History**: Complete log of all boat trips with duration
- **Usage Analytics**: Track most-used boats and total service hours
- **Admin Logs**: Trip data saved in admin page logs

### Display Modes
- **Web Dashboard**: Full interactive interface with all features
- **Terminal Display**: Clean HDMI output optimized for monitors
- **Both**: Simultaneous web + terminal display

## Initial Setup Commands

```bash
# 1. SSH into Raspberry Pi
ssh pi@<RPI_IP> -p 2222

# 2. Clone and setup
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project
chmod +x scripts/setup_rpi.sh
./scripts/setup_rpi.sh

# 3. Activate environment (REQUIRED for all operations)
source .venv/bin/activate

# 4. Initialize database
python3 setup_new_system.py

# 5. Start system (choose your mode)
python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000
# OR
python3 boat_tracking_system.py --display-mode terminal
# OR
python3 boat_tracking_system.py --display-mode both --api-port 8000 --web-port 5000
```

## Registering a New Beacon

1. Open web dashboard at http://localhost:5000
2. Click "Register New Beacon"
3. Click "Start Scanning" – only iBeacon devices are listed
4. Select your beacon, complete boat details, save
5. Beacon appears on dashboard and in API

## Testing with Simulator

```bash
# Activate environment first
source .venv/bin/activate

# Run simulator for testing
python3 sim_run_simulator.py

# Seed database with test data
python3 sim_seed_data.py --boats 10 --days 10 --reset
```

## Project Structure

```
grp_project/
├── boat_tracking_system.py     # Web Dashboard + API Orchestrator [Web/API Server + Displays]
├── api_server.py               # REST API server for detections and status [Web/API Server]
├── ble_scanner.py              # Single BLE receiver at a gate [Receivers at Chokepoint]
├── scanner_service.py          # Runs both receivers together [BLE Ingest]
├── beacon_simulator.py         # Test signal generator [Simulation & Testing]
├── sim_run_simulator.py        # Movement simulator end-to-end [Simulation & Testing]
├── sim_fsm_viewer.py           # Visualizes state changes [Displays]
├── sim_seed_data.py            # Creates demo boats/beacons/trips [State Store]
├── scanner_service.py          # Service to run both scanners together [BLE Ingest]
├── app/                        # Core application modules
│   ├── database_models.py      # Database tables and access [State Store]
│   ├── entry_exit_fsm.py       # Boat entry/exit logic (rules) [Event Engine]
│   ├── fsm_engine.py           # Wires FSM into the app [Event Engine]
│   ├── admin_service.py        # Admin actions (assign beacons, etc.) [Web/API Server]
│   └── logging_config.py       # Unified logs [All blocks]
├── requirements.txt            # Python dependencies
├── data/                       # Database and logs directory
│   ├── boat_tracking.db        # SQLite database (runtime) [State Store]
│   └── logs/                   # System logs [Observability]
├── scripts/                    # Operational & diagnostic scripts
│   ├── setup_rpi.sh            # One-command Pi setup [Deployment]
│   ├── start_everything.sh     # Start full system [Operations]
│   ├── stop_everything.sh      # Stop all processes [Operations]
│   ├── check_status.sh         # Health/status snapshot [Operations]
│   ├── start_public.sh         # Public tunnel start [Operations]
│   ├── monitor_scanner_sequences.py # Shows inner→outer / outer→inner in real time [Diagnostics]
│   └── ibeacon_dual_monitor.py # Live signal strength & distance per adapter [Receivers Diagnostics]
├── system/
│   └── json/                   # Runtime JSON configuration
│       ├── scanner_config.json # Which USB adapter is inner/outer, thresholds [Receivers + Ingest]
│       └── settings.json       # General app settings [Operations]
├── tools/                      # Developer utilities
│   ├── backfill_history.py     # Rebuild trip/history data [State Store]
│   ├── ble_testing/            # BLE range tests & helpers [Receivers Diagnostics]
│   └── network/                # Network helpers (e.g., get_ip) [Operations]
└── README.md                   # This file
```

> System diagram: see `~/Documents/system_architecture.png` (not tracked in repo).

## System Architecture → Code Map

This maps each block in the architecture diagram to the scripts/modules that implement it, so teammates can find the relevant code quickly.

- BLE Receivers at Chokepoint (Left/Right/Overhead)
  - Primary: `ble_scanner.py` (single scanner), `scanner_service.py` (multi-scanner)
  - Config: `system/json/scanner_config.json` (adapters `hci0/hci1`, thresholds)
  - Diagnostics: `scripts/ibeacon_dual_monitor.py`, `tools/ble_testing/*`

- BLE Ingest (BlueZ scanner service)
  - `ble_scanner.py`, `scanner_service.py`
  - Uses BlueZ via `bleak` to filter iBeacon frames, batches observations

- Event Engine (RSSI filter • thresholds • direction)
  - `app/entry_exit_fsm.py` (5-state FSM with pair windows, dominance, hysteresis)
  - `app/fsm_engine.py` (engine interface/wiring)

- State Store (SQLite)
  - `app/database_models.py` (tables: `beacons`, `boats`, `detections`, `beacon_states`, assignments)
  - Runtime DB file: `data/boat_tracking.db`

- Web/API Server (Flask)
  - Dashboard + API orchestrator: `boat_tracking_system.py` (web on port 5000, API proxy)
  - Standalone API service: `api_server.py` (port 8000)

- Notifier (entry/exit sounds + webhooks)
  - Hook points live in `boat_tracking_system.py` (web UI) and `api_server.py` (extendable). Addons can subscribe to state changes.

- Displays (HDMI kiosk / Web dashboard)
  - Web: `boat_tracking_system.py` → routes `/`, `/fsm`, `/api/fsm-states`, etc.
  - Terminal: `boat_tracking_system.py --display-mode terminal`

- Users / Network
  - LAN/Wi‑Fi access via ports 5000 (web) and 8000 (API)
  - Utilities: `tools/network/get_ip.py`, scripts under `scripts/`

- Simulation & Testing
  - Movement simulator: `sim_run_simulator.py`
  - Beacon simulator: `beacon_simulator.py`
  - FSM visualizer: `sim_fsm_viewer.py`
  - Live sequence monitor: `scripts/monitor_scanner_sequences.py`

Physical mapping tips
- Inner scanner = `gate-inner` (typically `hci1`); outer scanner = `gate-outer` (typically `hci0`), configured in `system/json/scanner_config.json`.
- Dashboard: `http://<pi-ip>:5000/` • API: `http://<pi-ip>:8000/`.

## REST API Endpoints

```
POST /api/v1/detections              # Scanner → server observations
GET  /api/v1/boats                   # List boats (includes water_time_today_minutes)
POST /api/v1/boats                   # Create boat
POST /api/v1/boats/{id}/assign-beacon
GET  /api/v1/beacons                 # List beacons
GET  /api/v1/presence                # Presence summary
GET  /api/v1/trips/{boat_id}         # Get trip history for boat
GET  /api/v1/usage-stats             # Get usage analytics
GET  /health                         # Health check
```

## Troubleshooting

### Common Issues
- **Port in use (8000/5000)**: Run `./scripts/stop_everything.sh` to stop previous runs
- **BLE permissions**: Ensure user can access BLE adapter (Bluetooth group)
- **No beacons listed**: Ensure device is broadcasting iBeacon frames
- **Environment not activated**: Always run `source .venv/bin/activate` first
- **HDMI display issues**: Check HDMI connection and `/boot/config.txt` settings

### Useful Commands
```bash
# Check system status
./scripts/check_status.sh

# Stop all processes
./scripts/stop_everything.sh

# Get Raspberry Pi IP
python3 tools/network/get_ip.py

# Test BLE scanner range
python3 tools/ble_testing/scanner_range_test.py
```

## Development Notes

- Scanner captures device local name and MAC, forwards to server
- Web dashboard lists only unassigned beacons during registration
- FSM supports maintenance-aware operations (ignores detections for boats in maintenance)
- Trip tracking automatically logs entry/exit events with duration
- Multi-gate architecture supports hardware isolation and independent scanner tuning

---

**Quick Start Summary:**
1. SSH: `ssh pi@<RPI_IP> -p 2222`
2. Clone: `git clone https://github.com/ksumit12/ENGN8170_group_project.git`
3. Setup: `cd ENGN8170_group_project && chmod +x scripts/setup_rpi.sh && ./scripts/setup_rpi.sh`
4. Activate: `source .venv/bin/activate`
5. Initialize: `python3 setup_new_system.py`
6. Run: `python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000`
7. Access: http://localhost:5000