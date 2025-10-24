# Black Mountain Rowing Club - Boat Tracking System
## Comprehensive Documentation and Deployment Guide

**Version:** 2.0 (door-lr-v2)  
**Last Updated:** October 2025  
**Platform:** Raspberry Pi 4 with Dual BLE Scanners  
**License:** MIT

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Repository Structure and Branches](#repository-structure-and-branches)
3. [System Architecture](#system-architecture)
4. [Features and Capabilities](#features-and-capabilities)
5. [Hardware Requirements](#hardware-requirements)
6. [Software Installation Guide](#software-installation-guide)
7. [System Configuration](#system-configuration)
8. [Calibration Procedures](#calibration-procedures)
9. [Running the System](#running-the-system)
10. [System Diagnostics and Troubleshooting](#system-diagnostics-and-troubleshooting)
11. [API Reference](#api-reference)
12. [File Structure and Script Reference](#file-structure-and-script-reference)
13. [Maintenance and Monitoring](#maintenance-and-monitoring)
14. [Advanced Configuration](#advanced-configuration)
15. [Appendices](#appendices)

---

## 1. Project Overview

### 1.1 Purpose

The Black Mountain Rowing Club (BMRC) Boat Tracking System is an automated, privacy-preserving solution for monitoring boat movements in and out of the Red Shed. The system eliminates manual whiteboard tracking, provides real-time boat status visibility, maintains comprehensive usage logs, and supports operational safety by tracking which boats are currently on the water.

### 1.2 Key Capabilities

- **Automatic Detection**: No manual input required from club members
- **Direction Determination**: Accurately detects ENTER (water→shed) and LEAVE (shed→water) movements
- **Real-Time Dashboard**: Web-based and HDMI terminal display modes
- **Trip Tracking**: Automatic logging of boat departure and return times
- **Usage Analytics**: Comprehensive reporting on boat utilization
- **Privacy-Preserving**: Tracks boats, not people
- **Offline Operation**: Functions without internet connectivity
- **Low Maintenance**: Designed for volunteer operation

### 1.3 Technical Approach

The system uses a dual-scanner architecture positioned at the left and right sides of the shed doorway. BLE beacons attached to each boat are detected by both scanners, and sophisticated RSSI (Received Signal Strength Indicator) pattern analysis determines the direction of boat movement. The system includes:

- **RSSI Smoothing**: Reduces signal fluctuation noise
- **Bias Compensation**: Equalizes scanner sensitivity differences
- **Movement Pattern Analysis**: Validates direction through timing and signal progression
- **Robust Error Handling**: Automatic recovery from hardware and software failures
- **Comprehensive Calibration**: Adapts to specific environmental conditions

---

## 2. Repository Structure and Branches

### 2.1 Branch Overview

#### **door-lr-v2** (MAIN BRANCH - RECOMMENDED)
- **Status**: Production-ready with all fixes applied
- **Features**: Complete dual-scanner door left-right detection
- **Stability**: Improved robustness with error handling
- **Calibration**: Simplified calibration scripts
- **Use Case**: Primary deployment branch for Red Shed

#### **main**
- **Status**: Merged from door-lr-v2 (up-to-date)
- **Features**: Same as door-lr-v2
- **Use Case**: Default branch for repository

#### **working-single-scanner**
- **Status**: Legacy/deprecated
- **Features**: Single scanner with timeout-based detection
- **Limitations**: No directional detection capability
- **Use Case**: Reference implementation only

#### **feature branches**
Various feature branches exist for development purposes. Always use `door-lr-v2` for deployment.

### 2.2 Recommended Branch

**Always use `door-lr-v2` for deployment and testing.**

```bash
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project
git checkout door-lr-v2
```

---

## 3. System Architecture

### 3.1 Hardware Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    RED SHED INTERIOR                     │
│                                                          │
│  ┌──────────────┐              ┌──────────────┐        │
│  │ LEFT Scanner │              │ RIGHT Scanner│        │
│  │   (hci0)     │              │    (hci1)    │        │
│  │  2m USB Ext  │              │  2m USB Ext  │        │
│  └──────┬───────┘              └──────┬───────┘        │
│         │                              │                │
│         └──────────┬───────────────────┘                │
│                    │                                    │
│         ┌──────────▼──────────┐                        │
│         │  Raspberry Pi 4     │                        │
│         │  • BLE Processing   │                        │
│         │  • Direction FSM    │                        │
│         │  • SQLite DB        │                        │
│         │  • Web Server       │                        │
│         └──────────┬──────────┘                        │
│                    │                                    │
│         ┌──────────▼──────────┐                        │
│         │   HDMI Display      │  ◄───── Local View     │
│         └─────────────────────┘                        │
│                                                          │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
            ┌───────────────┐
            │  WiFi Network │
            └───────┬───────┘
                    │
         ┌──────────▼──────────┐
         │  Web Dashboard      │  ◄───── Remote Access
         │  (Any Browser)      │
         └─────────────────────┘
```

### 3.2 Software Architecture

```
┌────────────────────────────────────────────────────────┐
│                  BLE BEACONS (Boats)                    │
└───────────────┬───────────────┬────────────────────────┘
                │               │
         ┌──────▼──────┐ ┌─────▼──────┐
         │  Scanner L  │ │ Scanner R  │
         │ (hci0)      │ │ (hci1)     │
         └──────┬──────┘ └─────┬──────┘
                │               │
                └───────┬───────┘
                        │
                ┌───────▼────────┐
                │  BLE Scanner   │  ble_scanner.py
                │  • Filters     │  scanner_service.py
                │  • RSSI Smooth │
                └───────┬────────┘
                        │
                ┌───────▼────────┐
                │  API Server    │  api_server.py
                │  /api/v1/*     │
                └───────┬────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
   ┌─────▼─────┐  ┌────▼────┐  ┌─────▼──────┐
   │ DoorLR    │  │Database │  │   Web UI   │
   │ Engine    │  │ SQLite  │  │  Flask     │
   │ FSM       │  │         │  │  Dashboard │
   └───────────┘  └─────────┘  └────────────┘
   app/door_lr_engine.py
   app/direction_classifier.py
   app/rf_signal_filter.py
```

### 3.3 Data Flow

1. **Detection**: BLE scanners detect iBeacon advertisements
2. **Filtering**: RSSI threshold filtering and smoothing
3. **Processing**: Direction classifier analyzes RSSI patterns
4. **State Update**: FSM engine updates boat status
5. **Persistence**: Database stores events and state
6. **Display**: Web/HDMI dashboard shows real-time status

---

## 4. Features and Capabilities

### 4.1 Core Features

#### Automatic Boat Detection
- Zero-touch operation for club members
- Detects boats via BLE beacons attached to each hull
- Continuous monitoring with sub-second response time
- Works 24/7 without human intervention

#### Direction Detection
- Distinguishes ENTER (water→shed) from LEAVE (shed→water)
- Uses RSSI pattern analysis across dual scanners
- Validates direction through timing and signal progression
- Accuracy >85% after calibration (improved from 16.7%)

#### Real-Time Status Dashboard
- Web-based interface accessible from any device
- HDMI terminal mode for dedicated display
- Live updates every 1 second
- Color-coded status indicators (green=IN, blue=OUT)

#### Trip Tracking and Analytics
- Automatic trip start/end logging
- Duration calculation in minutes
- Daily water time totals per boat
- Historical trip records with timestamps

#### Usage Reporting
- Most-used boats ranking
- Total service hours per boat
- Daily/weekly/monthly summaries
- CSV export for external analysis

### 4.2 Advanced Features

#### Robust Error Handling
- Automatic recovery from scanner failures
- Database corruption protection with WAL mode
- Retry mechanisms with exponential backoff
- Graceful degradation on component failure

#### Calibration System
- Static position calibration (left/center/right)
- Movement pattern calibration (6-8 passes)
- RSSI bias compensation
- Automatic calibration data persistence

#### System Monitoring
- Health monitoring dashboard
- Resource usage tracking (CPU, memory, disk)
- Bluetooth adapter status checks
- Network connectivity verification
- Process monitoring for all services

#### Data Integrity
- Daily automatic database backups
- Append-only event logging
- Foreign key constraints
- Transaction-based updates

#### Flexible Configuration
- JSON-based configuration files
- Runtime parameter adjustment
- Multiple scanner configurations
- Threshold tuning without code changes

### 4.3 User Interface Features

#### Web Dashboard
- Boat status table with color coding
- Last seen timestamps (local timezone)
- Water time today calculations
- Trip history viewer
- Admin panel for boat/beacon management
- Beacon assignment interface
- Real-time beacon scanning

#### HDMI Terminal Display
- Full-screen boat status display
- Optimized for 1080p monitors
- Auto-refresh every second
- No browser required
- Perfect for dedicated shed display

### 4.4 Privacy and Security Features

- No personal data collection
- Tracks boats, not individuals
- Local data storage only
- Optional authentication for admin functions
- Audit logging for data changes

---

## 5. Hardware Requirements

### 5.1 Required Components

| Component | Specification | Quantity | Purpose |
|-----------|---------------|----------|---------|
| **Raspberry Pi 4** | 2GB+ RAM, quad-core | 1 | Main computing unit |
| **microSD Card** | 32GB+, Class 10/A1 | 1 | Operating system and data storage |
| **BLE USB Dongles** | TP-Link UB500 or equivalent | 2 | Left and right door scanners |
| **USB Extension Cables** | 2 meters, USB 2.0/3.0 | 2 | Position scanners at doorway |
| **Power Supply** | 5V 3A USB-C | 1 | Stable power for Pi |
| **BLE Beacons** | iBeacon compatible, waterproof | 3+ | Boat identification tags |

### 5.2 Optional Components

| Component | Purpose |
|-----------|---------|
| **HDMI Monitor** | Local dashboard display in shed |
| **HDMI Cable** | Connect Pi to monitor |
| **Ethernet Cable** | Wired network connection (recommended over WiFi) |
| **UPS/Battery Backup** | Power protection during outages |
| **Protective Case** | Weather protection for Raspberry Pi |
| **Buzzer** | Audible alerts for boat movements |
| **Mounting Hardware** | Secure scanner positioning |

### 5.3 Hardware Setup

#### Scanner Positioning
- **Left Scanner (hci0)**: Left side of door (viewed from inside shed)
- **Right Scanner (hci1)**: Right side of door (viewed from inside shed)
- **Height**: 1-2 meters (match beacon mounting height)
- **Distance from door**: 0.5-1 meter inside shed
- **Spacing**: 2-4 meters apart depending on door width
- **Line of sight**: Clear view through doorway

#### Beacon Configuration
- **Transmission Power**: Medium (not maximum) for ~1-1.5m range
- **Advertising Interval**: 100-200ms for frequent updates
- **Format**: iBeacon (UUID:Major:Minor)
- **Mounting**: Secure attachment to boat hull
- **Waterproofing**: IP67+ rating recommended

### 5.4 Network Requirements

- **Bandwidth**: Minimal (<1 Mbps)
- **Connectivity**: WiFi or Ethernet
- **Reliability**: Stable connection preferred
- **Ports**: 8000 (API), 5000 (Web Dashboard)
- **Internet**: Not required for core functionality

---

## 6. Software Installation Guide

### 6.1 Prerequisites

#### Operating System
- **Recommended**: Raspberry Pi OS (Bullseye or newer)
- **Architecture**: ARM64 (64-bit) or ARM32
- **Installation**: Use Raspberry Pi Imager

#### System Requirements
- **Python**: 3.8 or higher
- **BlueZ**: Latest version for BLE support
- **SQLite**: 3.x for database
- **Git**: For repository cloning

### 6.2 Fresh Installation (Recommended Method)

This is the complete step-by-step guide for installing on a fresh Raspberry Pi.

#### Step 1: Prepare Raspberry Pi OS

```bash
# Download Raspberry Pi OS Lite (64-bit recommended)
# Flash to microSD card using Raspberry Pi Imager
# Enable SSH before first boot (create empty 'ssh' file in boot partition)
# Configure WiFi if needed (wpa_supplicant.conf in boot partition)
```

#### Step 2: Initial System Update

```bash
# SSH into Raspberry Pi
ssh pi@<RPI_IP_ADDRESS>

# Update system packages
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

# Reboot
sudo reboot
```

#### Step 3: Clone Repository

```bash
# Clone the project repository
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project

# Switch to main branch (door-lr-v2 is merged here)
git checkout door-lr-v2

# Verify branch
git branch
```

#### Step 4: Automated WiFi Setup

```bash
# Make WiFi script executable
chmod +x wifi_auto.sh

# Run WiFi auto-configuration
./wifi_auto.sh

# Follow prompts to:
# 1. Select your WiFi network
# 2. Enter WiFi password
# 3. Configure network settings
# 4. Test connectivity

# The script will:
# - Scan for available networks
# - Configure wpa_supplicant
# - Set up static IP (optional)
# - Test connection
# - Save configuration
```

**Note**: If you're using Ethernet, you can skip this step.

#### Step 5: System Dependencies Installation

```bash
# Run comprehensive system setup
./scripts/setup/setup_system.sh --security --emergency

# This script will:
# - Install Python 3.8+ and pip
# - Install BlueZ and Bluetooth tools
# - Install system libraries (sqlite3, openssl, etc.)
# - Create Python virtual environment
# - Install Python packages from requirements.txt
# - Configure Bluetooth adapters
# - Set up database directory structure
# - Initialize logging system
# - Configure security features (if --security flag used)
# - Set up emergency notifications (if --emergency flag used)

# Expected duration: 10-15 minutes
```

#### Step 6: Verify Installation

```bash
# Check Python version
python3 --version
# Should show Python 3.8 or higher

# Check BlueZ installation
bluetoothctl --version

# Check Bluetooth adapters
hciconfig
# Should show hci0 and hci1 (or more)

# Verify Python packages
source .venv/bin/activate
pip list | grep -E "bleak|flask|requests"

# Check database setup
ls -la data/
# Should show boat_tracking.db and backups/ directory
```

### 6.3 Manual Installation (Alternative)

If the automated setup fails, use this manual process:

```bash
# Install system packages
sudo apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    bluez bluez-tools libbluetooth-dev \
    sqlite3 openssl curl git htop vim \
    iw wireless-tools

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt

# Initialize database
python3 -c "from app.database_models import DatabaseManager; DatabaseManager().init_database()"

# Create necessary directories
mkdir -p data/backups logs calibration/sessions/latest scripts/utilities
```

### 6.4 Bluetooth Adapter Configuration

```bash
# List USB Bluetooth adapters
lsusb | grep -i bluetooth

# Check HCI interfaces
hciconfig

# Enable adapters if DOWN
sudo hciconfig hci0 up
sudo hciconfig hci1 up

# Verify adapter status
hciconfig
# Both hci0 and hci1 should show "UP RUNNING"

# Test scanning on each adapter
sudo hcitool -i hci0 lescan &
sudo hcitool -i hci1 lescan &
# Should see BLE devices being detected
# Press Ctrl+C to stop

# Check adapter details
sudo hciconfig hci0 revision
sudo hciconfig hci1 revision
```

### 6.5 Permissions Configuration

```bash
# Add user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Configure Bluetooth permissions
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(which python3)

# Create udev rule for Bluetooth access
echo 'KERNEL=="hci[0-9]*", GROUP="bluetooth", MODE="0660"' | \
    sudo tee /etc/udev/rules.d/99-bluetooth.rules

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Reboot for permissions to take effect
sudo reboot
```

---

## 7. System Configuration

### 7.1 Scanner Configuration

The main configuration file is `system/json/scanner_config.json`:

```json
{
  "api_host": "localhost",
  "api_port": 8000,
  "gates": [
    {
      "id": "gate-1",
      "hysteresis": {
        "enter_dbm": -70,
        "exit_dbm": -75,
        "min_hold_ms": 2000
      },
      "scanners": [
        {
          "id": "gate-left",
          "adapter": "hci0",
          "rssi_bias_db": 0,
          "scan_interval": 1.0,
          "batch_size": 10,
          "api_key": "default-key"
        },
        {
          "id": "gate-right",
          "adapter": "hci1",
          "rssi_bias_db": 0,
          "scan_interval": 1.0,
          "batch_size": 10,
          "api_key": "default-key"
        }
      ]
    }
  ]
}
```

#### Configuration Parameters

| Parameter | Description | Default | Tuning Guide |
|-----------|-------------|---------|--------------|
| `enter_dbm` | RSSI threshold for entering shed | -70 | Lower = more sensitive |
| `exit_dbm` | RSSI threshold for exiting shed | -75 | Lower = more sensitive |
| `min_hold_ms` | Minimum detection time | 2000 | Increase for stability |
| `adapter` | HCI interface (hci0, hci1) | hci0/hci1 | Match physical position |
| `rssi_bias_db` | Scanner calibration offset | 0 | Set by calibration |
| `scan_interval` | Scanning frequency (seconds) | 1.0 | Lower = more frequent |
| `batch_size` | Detections per API call | 10 | Higher = less overhead |

### 7.2 Direction Classifier Parameters

Located in `app/door_lr_engine.py`:

```python
params = LRParams(
    active_dbm=-75,          # Detection threshold
    energy_dbm=-70,          # Strong signal threshold
    delta_db=5.0,            # Min RSSI difference for direction
    dwell_s=0.5,             # Min detection duration
    window_s=2.0,            # Analysis time window
    tau_min_s=0.2,           # Min time between peaks
    cooldown_s=3.0,          # Cooldown between events
    slope_min_db_per_s=5.0,  # Min RSSI change rate
    min_peak_sep_s=0.5       # Min peak separation time
)
```

#### Parameter Tuning Guidelines

- **Wider doors**: Increase `window_s` and `min_peak_sep_s`
- **Slower boats**: Increase `dwell_s` and `window_s`
- **Weaker beacons**: Decrease `active_dbm` and `energy_dbm`
- **False detections**: Increase `delta_db` and `slope_min_db_per_s`
- **Metal environment**: Use higher thresholds and longer windows

### 7.3 Database Configuration

The database is automatically configured in `app/database_models.py`:

- **Location**: `data/boat_tracking.db`
- **Mode**: WAL (Write-Ahead Logging) for concurrency
- **Backups**: Daily automatic backups in `data/backups/`
- **Timeout**: 30 seconds for lock acquisition
- **Cache**: 10,000 pages for performance

### 7.4 Network Configuration

#### Port Configuration
- **API Server**: 8000 (default)
- **Web Dashboard**: 5000 (default)
- **MQTT** (if enabled): 1883

#### Firewall Configuration (if needed)
```bash
# Allow API server
sudo ufw allow 8000/tcp

# Allow web dashboard
sudo ufw allow 5000/tcp

# Enable firewall
sudo ufw enable
```

---

## 8. Calibration Procedures

Calibration is **essential** for accurate direction detection. The system includes two calibration approaches.

### 8.1 Simplified Calibration (Recommended)

Use the new simplified calibration script for easier setup:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run simplified calibration
python3 scripts/utilities/simple_calibration.py \
    --beacon-mac "XX:XX:XX:XX:XX:XX" \
    --duration 30 \
    --runs 3

# Follow the interactive prompts:
# 1. Static calibration (left/center/right positions)
# 2. Movement calibration (walk through doorway)
# 3. Automatic analysis and bias calculation
# 4. Results saved to calibration/sessions/latest/

# Expected duration: 10-15 minutes
```

### 8.2 Advanced Calibration (Full Control)

For detailed calibration with more control:

#### Phase 1: RF Bias Calibration

```bash
# Static position calibration
python3 calibration/rf_bias_calibration.py \
    --mac YOUR_BEACON_MAC \
    --duration 30

# This will:
# 1. Collect RSSI samples at CENTER position (30s)
# 2. Collect RSSI samples at LEFT position (30s)
# 3. Collect RSSI samples at RIGHT position (30s)
# 4. Calculate bias compensation values
# 5. Save to calibration/sessions/latest/door_lr_calib.json

# Instructions during calibration:
# - CENTER: Hold beacon at exact doorway center
# - LEFT: Place beacon 10cm in front of left scanner
# - RIGHT: Place beacon 10cm in front of right scanner
# - Keep beacon steady during each 30s sample period
```

#### Phase 2: Movement Pattern Calibration

```bash
# Movement pattern analysis
python3 calibration/door_lr_calibration.py \
    --mac YOUR_BEACON_MAC \
    --runs 6

# For each direction (ENTER and LEAVE):
# 1. Walk beacon through doorway at normal pace
# 2. System records RSSI patterns and timing
# 3. Repeat 6 times per direction
# 4. System analyzes and validates patterns

# Tips for best results:
# - Walk at consistent, normal speed
# - Hold beacon at same height each time
# - Pass through center of doorway
# - Wait 5 seconds between passes
```

### 8.3 Calibration Validation

```bash
# Check calibration file was created
cat calibration/sessions/latest/door_lr_calib.json

# Expected output:
# {
#   "timestamp": "2025-10-24T...",
#   "rssi_offsets": {
#     "gate-left": -2.5,
#     "gate-right": 2.5
#   },
#   "thresholds": {
#     "active_dbm": -75,
#     "energy_dbm": -70
#   },
#   "movement_analysis": {
#     "enter_accuracy": 0.85,
#     "leave_accuracy": 0.90
#   }
# }

# Test calibration with live monitoring
python3 calibration/find_center_live.py --mac YOUR_BEACON_MAC

# This shows real-time RSSI values from both scanners
# Verify that at center position, both scanners show similar RSSI
```

### 8.4 Re-calibration Guidelines

Re-calibrate when:
- Scanner positions are changed
- Environmental conditions change significantly
- Detection accuracy drops below 80%
- New beacon types are introduced
- Seasonal temperature changes (>20°C difference)

---

## 9. Running the System

### 9.1 Quick Start

```bash
# Navigate to project directory
cd ~/ENGN8170_group_project

# Activate virtual environment
source .venv/bin/activate

# Start complete system
./start_system.sh --security --emergency --display-mode both

# This starts:
# - API server (port 8000)
# - Web dashboard (port 5000)
# - BLE scanners (hci0, hci1)
# - HDMI terminal display
# - Health monitoring
```

### 9.2 Display Modes

#### Web Dashboard Only
```bash
./start_system.sh --display-mode web
```
Access at: `http://<RPI_IP>:5000`

#### HDMI Terminal Only
```bash
./start_system.sh --display-mode terminal
```
Full-screen display on connected HDMI monitor

#### Both (Recommended)
```bash
./start_system.sh --display-mode both
```
Web + HDMI terminal simultaneously

### 9.3 Starting Individual Components

#### API Server Only
```bash
source .venv/bin/activate
python3 api_server.py
```

#### Scanner Service Only
```bash
source .venv/bin/activate
python3 scanner_service.py --config system/json/scanner_config.json
```

#### Web Dashboard Only
```bash
source .venv/bin/activate
python3 boat_tracking_system.py --api-port 8000 --web-port 5000 --display-mode web
```

### 9.4 System Management Scripts

```bash
# Comprehensive management
./scripts/management/manage_system.sh start     # Start all services
./scripts/management/manage_system.sh stop      # Stop all services
./scripts/management/manage_system.sh restart   # Restart all services
./scripts/management/manage_system.sh status    # Check status
./scripts/management/manage_system.sh logs      # View logs
./scripts/management/manage_system.sh test      # Run tests

# Quick scripts
./scripts/quick_start.sh                        # Fast startup
./scripts/stop_everything.sh                    # Emergency stop
./scripts/check_status.sh                       # Status check
```

### 9.5 Background Operation

To run the system as a service that starts on boot:

```bash
# Create systemd service file
sudo nano /etc/systemd/system/boat-tracking.service

# Add content:
[Unit]
Description=Boat Tracking System
After=network.target bluetooth.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/ENGN8170_group_project
ExecStart=/home/pi/ENGN8170_group_project/.venv/bin/python3 boat_tracking_system.py --display-mode both
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable boat-tracking
sudo systemctl start boat-tracking

# Check service status
sudo systemctl status boat-tracking

# View service logs
sudo journalctl -u boat-tracking -f
```

---

## 10. System Diagnostics and Troubleshooting

### 10.1 Comprehensive Health Check

```bash
# Run complete system health monitor
python3 scripts/utilities/system_health_monitor.py

# This checks:
# - Bluetooth adapter status
# - System resources (CPU, memory, disk)
# - Database health and activity
# - Network connectivity
# - Running processes
# - Recent events

# Save health report
python3 scripts/utilities/system_health_monitor.py --output logs/health.json

# Continuous monitoring (every 60 seconds)
python3 scripts/utilities/system_health_monitor.py --watch --interval 60
```

### 10.2 Bluetooth Diagnostics

#### Check Adapters
```bash
# List HCI interfaces
hciconfig

# Expected output:
# hci0:   Type: Primary  Bus: USB
#         BD Address: XX:XX:XX:XX:XX:XX  ACL MTU: 1021:8  SCO MTU: 64:1
#         UP RUNNING
# hci1:   Type: Primary  Bus: USB
#         BD Address: YY:YY:YY:YY:YY:YY  ACL MTU: 1021:8  SCO MTU: 64:1
#         UP RUNNING

# If adapters are DOWN:
sudo hciconfig hci0 up
sudo hciconfig hci1 up

# Check USB devices
lsusb | grep -i bluetooth
# Should show: TP-Link Bluetooth adapters

# Reset adapters if needed
sudo hciconfig hci0 reset
sudo hciconfig hci1 reset
```

#### Test BLE Scanning
```bash
# Scan with left scanner (hci0)
sudo hcitool -i hci0 lescan

# Scan with right scanner (hci1)
sudo hcitool -i hci1 lescan

# Should see BLE beacons:
# XX:XX:XX:XX:XX:XX Beacon_Name
# YY:YY:YY:YY:YY:YY (unknown)

# Advanced scanning with details
sudo btmon &  # Start Bluetooth monitor
sudo hcitool -i hci0 lescan --duplicates
# Press Ctrl+C to stop
# Check btmon output for detailed packet information
```

#### Scanner Range Test
```bash
# Test individual scanner range
python3 tools/ble_testing/scanner_range_test.py --adapter hci0 --duration 60
python3 tools/ble_testing/scanner_range_test.py --adapter hci1 --duration 60

# Test all scanners simultaneously
python3 tools/ble_testing/scanner_range_test.py --test-all --duration 30

# Identify dongles
python3 tools/ble_testing/identify_ble_dongles.py
```

### 10.3 API Diagnostics

#### Check API Server Status
```bash
# Test if API is running
curl http://localhost:8000/api/v1/health

# Expected response:
# {"status": "healthy", "timestamp": "2025-10-24T..."}

# Check boat presence
curl http://localhost:8000/api/v1/presence

# Expected response:
# [
#   {
#     "boat_id": "boat_001",
#     "boat_name": "Single Scull 1",
#     "status": "IN_HARBOR",
#     "last_seen": "2025-10-24T10:30:00Z",
#     ...
#   }
# ]

# Test detection endpoint (should return 400 without data)
curl -X POST http://localhost:8000/api/v1/detections

# Check all boats
curl http://localhost:8000/api/v1/boats

# Check all beacons
curl http://localhost:8000/api/v1/beacons
```

#### API Performance Test
```bash
# Install Apache Bench if needed
sudo apt-get install apache2-utils

# Test API response time
ab -n 100 -c 10 http://localhost:8000/api/v1/presence

# Expected results:
# Requests per second: >500
# Time per request: <20ms
# 50% of requests: <10ms
```

### 10.4 Database Diagnostics

#### Check Database Health
```bash
# Enter database
sqlite3 data/boat_tracking.db

# Check tables
.tables
# Expected: boats, beacons, boat_beacon_assignments, detection_states, 
#           shed_events, boat_trips

# Count records
SELECT COUNT(*) FROM boats;
SELECT COUNT(*) FROM beacons;
SELECT COUNT(*) FROM shed_events;

# Check recent events (last hour)
SELECT * FROM shed_events 
WHERE ts_utc > datetime('now', '-1 hour')
ORDER BY ts_utc DESC;

# Check database integrity
PRAGMA integrity_check;
# Expected: ok

# Check database size
.exit
ls -lh data/boat_tracking.db

# Check WAL mode
sqlite3 data/boat_tracking.db "PRAGMA journal_mode;"
# Expected: wal
```

#### Database Backup and Restore
```bash
# Manual backup
cp data/boat_tracking.db data/backups/boat_tracking_manual_$(date +%Y%m%d_%H%M%S).sqlite

# List backups
ls -lh data/backups/

# Restore from backup
cp data/backups/boat_tracking_20251024.sqlite data/boat_tracking.db

# Vacuum database (optimize)
sqlite3 data/boat_tracking.db "VACUUM;"
```

### 10.5 Network Diagnostics

```bash
# Check WiFi connection
iwconfig

# Check IP address
hostname -I

# Test internet connectivity
ping -c 4 8.8.8.8

# Check port availability
netstat -tuln | grep -E "8000|5000"

# Expected output:
# tcp  0  0.0.0.0:8000  0.0.0.0:*  LISTEN
# tcp  0  0.0.0.0:5000  0.0.0.0:*  LISTEN

# Test local API access
curl http://localhost:8000/api/v1/health

# Test remote API access (from another device)
curl http://<RPI_IP>:8000/api/v1/health
```

### 10.6 Process Diagnostics

```bash
# Check running Python processes
ps aux | grep python

# Expected processes:
# - api_server.py
# - boat_tracking_system.py
# - scanner_service.py (x2, one per adapter)

# Check process CPU/memory usage
top -p $(pgrep -d',' python)

# Check system resources
htop

# Check disk space
df -h

# Check memory usage
free -h
```

### 10.7 Log Analysis

```bash
# View system logs (last 100 lines)
tail -n 100 logs/system.log

# Follow logs in real-time
tail -f logs/system.log

# Search for errors
grep -i "error" logs/system.log

# Search for specific boat
grep "boat_001" logs/system.log

# Search for scanner issues
grep -i "scanner" logs/system.log | grep -i "error"

# View logs by timestamp
grep "2025-10-24 10:" logs/system.log

# Count events by type
grep "ENTER" logs/system.log | wc -l
grep "LEAVE" logs/system.log | wc -l
```

### 10.8 Common Issues and Solutions

#### Issue: No Bluetooth Adapters Found
```bash
# Check USB connection
lsusb | grep -i bluetooth

# Check if adapters are powered
sudo hciconfig hci0 up
sudo hciconfig hci1 up

# Reboot if needed
sudo reboot
```

#### Issue: Wrong Direction Detection
```bash
# Verify scanner placement (hci0=left, hci1=right)
hciconfig

# Check configuration
cat system/json/scanner_config.json

# Re-run calibration
python3 scripts/utilities/simple_calibration.py --beacon-mac YOUR_MAC

# Check calibration results
cat calibration/sessions/latest/door_lr_calib.json
```

#### Issue: Database Locked
```bash
# Check for multiple connections
lsof data/boat_tracking.db

# Kill processes accessing database
sudo pkill -f api_server.py
sudo pkill -f boat_tracking_system.py

# Restart system
./scripts/management/manage_system.sh restart
```

#### Issue: High CPU Usage
```bash
# Check process usage
top

# Reduce scanner frequency in config
# Edit system/json/scanner_config.json
# Increase scan_interval from 1.0 to 2.0

# Reduce batch processing
# Decrease batch_size from 10 to 5

# Restart services
./scripts/management/manage_system.sh restart
```

---

## 11. API Reference

### 11.1 Base URL

```
http://<RPI_IP>:8000/api/v1
```

### 11.2 Endpoints

#### GET /health
Check API server health

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-24T10:30:00Z"
}
```

#### GET /presence
Get current boat presence status

**Response:**
```json
[
  {
    "boat_id": "boat_001",
    "boat_name": "Single Scull 1",
    "boat_class": "1x",
    "status": "IN_HARBOR",
    "last_seen": "2025-10-24T10:30:00Z",
    "beacon_mac": "XX:XX:XX:XX:XX:XX",
    "water_time_today": 45
  }
]
```

#### GET /boats
List all boats

**Response:**
```json
[
  {
    "id": "boat_001",
    "name": "Single Scull 1",
    "class_type": "1x",
    "status": "IN_HARBOR",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-10-24T10:30:00Z"
  }
]
```

#### GET /beacons
List all beacons

**Response:**
```json
[
  {
    "id": "beacon_001",
    "mac_address": "XX:XX:XX:XX:XX:XX",
    "name": "Beacon 1",
    "status": "assigned",
    "last_seen": "2025-10-24T10:30:00Z",
    "last_rssi": -65
  }
]
```

#### POST /detections
Submit beacon detections (used by scanners)

**Request:**
```json
{
  "scanner_id": "gate-left",
  "gate_id": "gate-1",
  "observations": [
    {
      "mac": "XX:XX:XX:XX:XX:XX",
      "rssi": -65,
      "name": "Beacon 1",
      "beacon_id": "uuid:major:minor"
    }
  ]
}
```

**Response:**
```json
{
  "processed": 1,
  "state_changes": []
}
```

#### GET /trips
Get trip history

**Query Parameters:**
- `boat_id` (optional): Filter by boat
- `start_date` (optional): Start date filter
- `end_date` (optional): End date filter

**Response:**
```json
[
  {
    "id": "trip_001",
    "boat_id": "boat_001",
    "boat_name": "Single Scull 1",
    "start_time": "2025-10-24T09:00:00Z",
    "end_time": "2025-10-24T10:30:00Z",
    "duration_minutes": 90
  }
]
```

---

## 12. File Structure and Script Reference

### 12.1 Complete Directory Tree

```
ENGN8170_group_project/
├── api_server.py                    # Main API server (Flask)
├── boat_tracking_system.py          # Main system entry point
├── ble_scanner.py                   # BLE scanning module
├── scanner_service.py               # Scanner service manager
├── requirements.txt                 # Python dependencies
├── README.md                        # Original README
├── README_COMPREHENSIVE.md          # This comprehensive guide
├── FIXED_DEPLOYMENT_GUIDE.md        # Deployment guide with fixes
├── wifi_auto.sh                     # WiFi auto-configuration
│
├── app/                             # Core application modules
│   ├── __init__.py
│   ├── admin_service.py             # Admin functionality
│   ├── auth_system.py               # Authentication (optional)
│   ├── database_models.py           # Database ORM and models
│   ├── direction_classifier.py      # Direction detection algorithm
│   ├── door_lr_engine.py            # Door left-right FSM engine
│   ├── emergency_api.py             # Emergency notifications API
│   ├── emergency_system.py          # Emergency notification system
│   ├── entry_exit_fsm.py            # Legacy FSM engine
│   ├── fsm_engine.py                # FSM engine interface
│   ├── logging_config.py            # Logging configuration
│   ├── rf_signal_filter.py          # RSSI smoothing and filtering
│   ├── secure_database.py           # Encrypted database (optional)
│   └── single_scanner_engine.py     # Single scanner engine (legacy)
│
├── calibration/                     # Calibration tools and data
│   ├── README.md                    # Calibration documentation
│   ├── CALIBRATION_GUIDE.md         # Detailed calibration guide
│   ├── RF_CALIBRATION_GUIDE.md      # RF-specific calibration
│   ├── SCANNER_POSITIONING_GUIDE.md # Scanner placement guide
│   ├── USAGE.md                     # Usage instructions
│   ├── door_lr_calibration.py       # Movement calibration script
│   ├── rf_bias_calibration.py       # RSSI bias calibration script
│   ├── find_center_live.py          # Live center finding tool
│   ├── precheck_door_lr.py          # Pre-calibration check
│   └── sessions/                    # Calibration session data
│       ├── latest/                  # Latest calibration
│       │   └── door_lr_calib.json   # Active calibration file
│       └── backup/                  # Calibration backups
│
├── data/                            # Data directory
│   ├── boat_tracking.db             # Main SQLite database
│   └── backups/                     # Daily database backups
│       └── boat_tracking_YYYYMMDD.sqlite
│
├── docs/                            # Documentation
│   ├── architecture.mmd             # Architecture diagram (Mermaid)
│   ├── system_architecture.png      # System architecture image
│   ├── BLUETOOTH_DETECTION_EXPLAINED.md
│   ├── FSM_KNOWLEDGE_BASE.md        # FSM implementation details
│   ├── TWO_SCANNER_DOOR_SETUP.md    # Two-scanner setup guide
│   └── TWO_SCANNER_QUICK_REFERENCE.md
│
├── logs/                            # Log files
│   ├── system.log                   # Main system log
│   ├── scanner.log                  # Scanner activity log
│   ├── database.log                 # Database operations log
│   └── health.log                   # Health monitoring log
│
├── scripts/                         # Utility scripts
│   ├── management/                  # System management
│   │   └── manage_system.sh         # Comprehensive management script
│   ├── setup/                       # Setup scripts
│   │   └── setup_system.sh          # One-command system setup
│   ├── testing/                     # Testing scripts
│   │   └── test_system.sh           # Comprehensive testing
│   ├── utilities/                   # Utility scripts
│   │   ├── deploy_to_pi.sh          # Deployment script
│   │   ├── simple_calibration.py    # Simplified calibration
│   │   ├── system_health_monitor.py # Health monitoring
│   │   ├── run_calibration.sh       # Calibration runner
│   │   ├── start_two_scanner_system.sh
│   │   ├── stop_scanner.sh          # Stop scanner service
│   │   ├── generate_ssl_cert.sh     # SSL certificate generation
│   │   └── test_csv_logging.py      # CSV logging test
│   ├── quick_start.sh               # Quick system start
│   ├── stop_everything.sh           # Emergency stop all services
│   ├── check_status.sh              # Status check
│   ├── verify_setup.sh              # Verify installation
│   └── ibeacon_dual_monitor.py      # Dual scanner monitor
│
├── system/                          # System configuration
│   └── json/                        # JSON configuration files
│       ├── scanner_config.json      # Main scanner config
│       ├── scanner_config.door_left_right.json
│       ├── scanner_config.example.json
│       ├── scanner_config.inside_outside.json
│       └── settings.json            # System settings
│
├── test_plan/                       # Testing and validation
│   ├── README.md                    # Test plan documentation
│   ├── common.py                    # Common test utilities
│   ├── official_T1_demo.py          # Official T1 test
│   ├── official_T2_demo.py          # Official T2 test
│   ├── official_T3_demo.py          # Official T3 test
│   ├── physical_T1.py               # Physical T1 test
│   ├── physical_T2.py               # Physical T2 test
│   ├── physical_T3.py               # Physical T3 test
│   └── results/                     # Test results
│       ├── COMPREHENSIVE_TEST_REPORT.md
│       ├── T1/, T2/, T3/           # Test result directories
│       └── sim_*/                   # Simulation results
│
└── tools/                           # Testing and debugging tools
    ├── ble_testing/                 # BLE testing utilities
    │   ├── BLE_TESTING_GUIDE.md     # BLE testing guide
    │   ├── ble_scanner_tester.py    # Scanner testing tool
    │   ├── scanner_range_test.py    # Range testing
    │   ├── identify_ble_dongles.py  # Dongle identification
    │   ├── ibeacon_mac_scanner.py   # iBeacon MAC scanner
    │   └── ibeacon_mac_scanner.sh   # Shell script version
    ├── ble_watchdog.py              # BLE watchdog service
    ├── network/                     # Network utilities
    │   ├── get_ip.py                # IP address helper
    │   └── configure_firewall.sh    # Firewall configuration
    └── backfill_history.py          # Database backfill tool
```

### 12.2 Key Script Functions

#### System Management
- `scripts/management/manage_system.sh` - Start, stop, restart, status, logs
- `scripts/quick_start.sh` - Fast system startup
- `scripts/stop_everything.sh` - Emergency shutdown
- `scripts/check_status.sh` - Quick status check

#### Setup and Configuration
- `scripts/setup/setup_system.sh` - Complete system setup
- `wifi_auto.sh` - WiFi configuration
- `scripts/verify_setup.sh` - Installation verification

#### Calibration
- `scripts/utilities/simple_calibration.py` - User-friendly calibration
- `calibration/rf_bias_calibration.py` - Advanced RSSI bias calibration
- `calibration/door_lr_calibration.py` - Movement pattern calibration
- `calibration/find_center_live.py` - Live center finding

#### Monitoring and Diagnostics
- `scripts/utilities/system_health_monitor.py` - Comprehensive health check
- `tools/ble_testing/scanner_range_test.py` - Scanner range testing
- `tools/ble_testing/identify_ble_dongles.py` - Identify BLE adapters
- `scripts/ibeacon_dual_monitor.py` - Real-time dual scanner monitor

#### Testing
- `scripts/testing/test_system.sh` - Comprehensive system testing
- `test_plan/official_T1_demo.py` - T1 official test (location detection)
- `test_plan/official_T2_demo.py` - T2 official test (real-time updates)
- `test_plan/official_T3_demo.py` - T3 official test (timestamp accuracy)

---

## 13. Maintenance and Monitoring

### 13.1 Daily Maintenance

```bash
# Check system health
python3 scripts/utilities/system_health_monitor.py

# View recent logs
tail -n 50 logs/system.log

# Check disk space
df -h

# Verify adapters are up
hciconfig

# Test API responsiveness
curl http://localhost:8000/api/v1/health
```

### 13.2 Weekly Maintenance

```bash
# Review error logs
grep -i "error" logs/system.log | tail -n 50

# Check database size
ls -lh data/boat_tracking.db

# Verify backups exist
ls -lh data/backups/

# Test detection accuracy
# Manually pass beacon through door and verify correct direction

# Update system (if needed)
sudo apt-get update
sudo apt-get upgrade
```

### 13.3 Monthly Maintenance

```bash
# Full system test
./scripts/testing/test_system.sh all

# Re-run calibration check
python3 calibration/precheck_door_lr.py --mac YOUR_BEACON_MAC

# Database optimization
sqlite3 data/boat_tracking.db "VACUUM;"

# Review trip statistics
sqlite3 data/boat_tracking.db "
SELECT boat_id, COUNT(*) as trips, SUM(duration_minutes) as total_minutes
FROM boat_trips
WHERE start_time > datetime('now', '-30 days')
GROUP BY boat_id
ORDER BY total_minutes DESC;"

# Clean old logs (keep last 30 days)
find logs/ -name "*.log.*" -mtime +30 -delete

# Clean old backups (keep last 90 days)
find data/backups/ -name "*.sqlite" -mtime +90 -delete
```

### 13.4 Monitoring Metrics

#### System Health Metrics
- **CPU Usage**: Should be <50% average
- **Memory Usage**: Should be <70% of total RAM
- **Disk Space**: Keep >2GB free
- **Temperature**: Keep <70°C (check with `vcgencmd measure_temp`)

#### Detection Metrics
- **Detection Rate**: >90% of beacons should be detected
- **Direction Accuracy**: >85% correct direction (after calibration)
- **Response Time**: <2 seconds from detection to status update
- **False Positives**: <5% of total events

#### Database Metrics
- **Database Size**: Monitor growth, expect ~1MB per 1000 events
- **Query Performance**: API responses <500ms
- **Recent Events**: Should see events in last hour during active times
- **Backup Success**: Daily backups should be created

---

## 14. Advanced Configuration

### 14.1 Custom Threshold Tuning

For specific environments, you may need to tune detection thresholds:

```python
# Edit app/door_lr_engine.py
params = LRParams(
    active_dbm=-75,      # Decrease for weaker signals, increase for stronger
    energy_dbm=-70,      # Threshold for "strong" signal
    delta_db=5.0,        # Min RSSI difference between scanners
    dwell_s=0.5,         # Min time beacon must be present
    window_s=2.0,        # Time window for pattern analysis
    tau_min_s=0.2,       # Min time between left/right peaks
    cooldown_s=3.0,      # Prevent duplicate detections
    slope_min_db_per_s=5.0,  # Min RSSI change rate
    min_peak_sep_s=0.5   # Min separation between peaks
)
```

### 14.2 Multiple Gate Configuration

For installations with multiple doorways:

```json
{
  "api_host": "localhost",
  "api_port": 8000,
  "gates": [
    {
      "id": "gate-1",
      "hysteresis": { "enter_dbm": -70, "exit_dbm": -75, "min_hold_ms": 2000 },
      "scanners": [
        { "id": "gate1-left",  "adapter": "hci0", ... },
        { "id": "gate1-right", "adapter": "hci1", ... }
      ]
    },
    {
      "id": "gate-2",
      "hysteresis": { "enter_dbm": -70, "exit_dbm": -75, "min_hold_ms": 2000 },
      "scanners": [
        { "id": "gate2-left",  "adapter": "hci2", ... },
        { "id": "gate2-right", "adapter": "hci3", ... }
      ]
    }
  ]
}
```

### 14.3 Custom Logging Configuration

Edit `app/logging_config.py` to customize logging levels and formats:

```python
# Set global log level
LOG_LEVEL = logging.INFO  # Change to DEBUG for verbose output

# Configure file rotation
handler = RotatingFileHandler(
    'logs/system.log',
    maxBytes=10*1024*1024,  # 10MB per file
    backupCount=5            # Keep 5 backup files
)
```

---

## 15. Appendices

### 15.1 Troubleshooting Quick Reference

| Symptom | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| No detections | Adapters down | `sudo hciconfig hci0 up && sudo hciconfig hci1 up` |
| Wrong direction | Scanner swap or poor calibration | Verify hci0=left, hci1=right; re-calibrate |
| Database locked | Multiple processes | `sudo pkill -f api_server.py; restart services` |
| High CPU | Too frequent scanning | Increase scan_interval in config |
| No web access | Firewall or service down | Check `netstat -tuln \| grep 5000` |
| RSSI fluctuations | Metal interference | Run calibration with bias compensation |

### 15.2 Command Quick Reference

```bash
# System
sudo reboot                          # Reboot Raspberry Pi
sudo shutdown -h now                 # Shutdown
vcgencmd measure_temp                # Check temperature

# Bluetooth
hciconfig                            # List adapters
sudo hciconfig hci0 up               # Enable adapter
sudo hcitool -i hci0 lescan          # Scan for beacons
sudo hciconfig hci0 reset            # Reset adapter

# Services
./scripts/management/manage_system.sh start   # Start all
./scripts/management/manage_system.sh stop    # Stop all
./scripts/management/manage_system.sh status  # Check status

# Monitoring
python3 scripts/utilities/system_health_monitor.py   # Health check
tail -f logs/system.log                               # Follow logs
htop                                                  # System resources

# Database
sqlite3 data/boat_tracking.db                         # Open database
sqlite3 data/boat_tracking.db "SELECT * FROM boats;"  # Query boats

# Network
hostname -I                          # Get IP address
ping -c 4 8.8.8.8                   # Test internet
curl http://localhost:8000/api/v1/health  # Test API
```

### 15.3 Beacon MAC Address Reference

Keep a record of your beacons:

| Beacon MAC | Boat ID | Boat Name | Notes |
|------------|---------|-----------|-------|
| XX:XX:XX:XX:XX:XX | boat_001 | Single Scull 1 | Calibration beacon |
| YY:YY:YY:YY:YY:YY | boat_002 | Double Scull 1 |  |
| ZZ:ZZ:ZZ:ZZ:ZZ:ZZ | boat_003 | Quad 1 |  |

### 15.4 Contact and Support

- **Repository**: https://github.com/ksumit12/ENGN8170_group_project
- **Issues**: https://github.com/ksumit12/ENGN8170_group_project/issues
- **Branch**: door-lr-v2 (main deployment branch)

### 15.5 Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | Oct 2025 | door-lr-v2 with improved robustness |
| 1.5 | Oct 2025 | Added calibration system |
| 1.0 | Sep 2025 | Initial dual-scanner implementation |

---

## Quick Start Summary

For experienced users, here's the fastest path to deployment:

```bash
# 1. Clone and setup
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project
git checkout door-lr-v2

# 2. WiFi (if needed)
./wifi_auto.sh

# 3. Install
./scripts/setup/setup_system.sh --security --emergency

# 4. Calibrate
python3 scripts/utilities/simple_calibration.py --beacon-mac YOUR_MAC --duration 30 --runs 3

# 5. Run
./start_system.sh --display-mode both

# 6. Access
# Web: http://<RPI_IP>:5000
# API: http://<RPI_IP>:8000
```

---

**End of Comprehensive Documentation**

For additional help, consult the individual README files in each directory or refer to the inline code documentation.
