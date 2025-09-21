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

## 🚀 ONE COMMAND SETUP (Fresh RPi)

```bash
# 1. Clone and setup everything
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project
chmod +x setup_rpi.sh
./setup_rpi.sh

# 2. Start the system
./start_system.sh
```

**Your static URL**: `https://boat-tracking-ksumit12.ngrok.io` (NEVER CHANGES!)

## Quick Start (Already Setup)

### Local Development
```bash
python3 boat_tracking_system.py --api-port 8000 --web-port 5000
```

### Public Access
```bash
./start_system.sh
```

## Initial Setup

Initialize the database and sample data:

```bash
python3 setup_new_system.py
```

This creates `boat_tracking.db` with sample boats and beacons for testing.

## Running

### Full system (orchestrator)

Starts API server, two scanners (inner/outer), and the web dashboard.

```bash
python3 boat_tracking_system.py
```

Defaults:
- API Server: http://localhost:8000
- Web Dashboard: http://localhost:5000

You can also override ports:

```bash
python3 boat_tracking_system.py --api-port 8001 --web-port 5001
```

### Components separately

API server only:

```bash
python3 api_server.py --port 8000
```

Scanner (run one per scanner location):

```bash
python3 ble_scanner.py --scanner-id gate-outer --server-url http://localhost:8000
python3 ble_scanner.py --scanner-id gate-inner --server-url http://localhost:8000
```

## Registering a New Beacon

1. Open the web dashboard at http://localhost:5000
2. Click “Register New Beacon”
3. Click “Start Scanning” – only iBeacon devices are listed
4. Select your beacon (name and MAC are shown), complete boat details, save

The beacon is assigned to the boat and appears on the dashboard and in the API.

## Features

- iBeacon-only filtering at the scanner level (Apple manufacturer data 0x004C, subtype 0x02 0x15)
- Beacon discovery and registration workflow
- One active beacon per boat enforced by the database
- Presence summary and recent detections

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
├── database_models.py         # SQLite models and CRUD
├── entry_exit_fsm.py          # Entry/exit finite state machine
├── admin_service.py           # Admin operations service
├── logging_config.py          # Centralized logging configuration
├── requirements.txt           # Python dependencies
├── data/                      # Database and logs directory
│   ├── boat_tracking.db      # SQLite database
│   └── logs/                 # System logs
├── tools/                     # Utility tools and scripts
│   ├── ble_testing/          # BLE scanner testing tools
│   │   ├── identify_ble_dongles.py
│   │   ├── scanner_range_test.py
│   │   ├── ble_scanner_tester.py
│   │   └── BLE_TESTING_GUIDE.md
│   ├── network/              # Network access tools
│   │   ├── get_ip.py
│   │   ├── start_network.sh
│   │   └── configure_firewall.sh
│   ├── scripts/              # Utility scripts
│   │   ├── kill_all_servers.sh
│   │   └── kill_boat_servers.sh
│   └── logs/                 # Log analysis tools (future)
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

## Development Notes

- The scanner captures device local name and MAC and forwards them to the server.
- The web dashboard lists only beacons not yet assigned during registration.

---

For migration details from the old single-beacon scripts, see `MIGRATION_GUIDE.md`.