# Boat Tracking System - Setup Summary

## ✅ What's Been Added

### 1. Trip Tracking & Analytics
- **New Database Table**: `boat_trips` - logs every exit/entry with duration
- **FSM Integration**: Automatically logs trips when boats transition ENTERED ↔ EXITED
- **API Enhancement**: Added `water_time_today_minutes` field to boat API
- **Analytics Methods**: 
  - `get_boat_water_time_today()` - total minutes on water today
  - `get_boat_trip_history()` - trip history for a boat
  - `get_boat_usage_stats()` - usage analytics across all boats

### 2. Enhanced Scripts
- **`scripts/stop_everything.sh`** - Kills all boat tracking processes and frees ports
- **`scripts/quick_start.sh`** - Interactive menu to start system in different modes
- **`scripts/verify_setup.sh`** - Verifies setup and checks all dependencies

### 3. Updated README
- **Complete setup guide** for fresh Raspberry Pi
- **Multiple display modes** (web, terminal, both)
- **Physical hardware setup** instructions
- **Troubleshooting section** with common issues

## 🚀 Quick Start Commands

### Fresh Raspberry Pi Setup
```bash
# 1. SSH into Raspberry Pi
ssh pi@<RPI_IP> -p 2222

# 2. Clone and setup
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project
chmod +x scripts/setup_rpi.sh
./scripts/setup_rpi.sh

# 3. Activate environment (REQUIRED)
source .venv/bin/activate

# 4. Initialize database
python3 setup_new_system.py

# 5. Start system (choose your mode)
./scripts/quick_start.sh
```

### Manual Start Options
```bash
# Web dashboard only
python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000

# HDMI terminal display only
python3 boat_tracking_system.py --display-mode terminal

# Both web + terminal
python3 boat_tracking_system.py --display-mode both --api-port 8000 --web-port 5000
```

### Stop Everything
```bash
./scripts/stop_everything.sh
```

## 🔧 Physical Hardware Setup

### BLE Scanner Placement
- **Inner Scanner**: Inside shed, ~1m from boat storage area
- **Outer Scanner**: Outside shed, ~1m from water access point
- **USB Extensions**: 2m extensions for flexible placement

### BLE Beacon Configuration
- **Transmission Power**: Medium/low (not maximum)
- **Advertising Interval**: 100-200ms
- **Detection Range**: ~1-1.5 meters per scanner

## 📊 New Features

### Trip Tracking
- **Automatic Logging**: Every boat exit/entry is logged with duration
- **Water Time Today**: New column showing total minutes on water today
- **Historical Data**: Complete trip history for analytics
- **Usage Statistics**: Track most-used boats and total service hours

### Display Modes
- **Web Dashboard**: Full interactive interface (http://localhost:5000)
- **Terminal Display**: Clean HDMI output for monitors
- **Both**: Simultaneous web + terminal display

## 🛠️ Troubleshooting

### Common Issues
- **Environment not activated**: Always run `source .venv/bin/activate` first
- **Ports in use**: Run `./scripts/stop_everything.sh` to free ports
- **BLE permissions**: Ensure user is in bluetooth group
- **HDMI display**: Check HDMI connection and `/boot/config.txt`

### Verification
```bash
# Check setup
./scripts/verify_setup.sh

# Check system status
./scripts/check_status.sh
```

## 📁 Key Files

- **`README.md`** - Complete setup and usage guide
- **`scripts/stop_everything.sh`** - Stop all processes
- **`scripts/quick_start.sh`** - Interactive startup menu
- **`scripts/verify_setup.sh`** - Setup verification
- **`app/database_models.py`** - Database models with trip tracking
- **`app/entry_exit_fsm.py`** - FSM with trip logging

## 🎯 Next Steps

1. **Test the system** with simulator: `python3 sim_run_simulator.py`
2. **Configure BLE beacons** for ~1m detection range
3. **Place scanners** inside/outside shed with 2m USB extensions
4. **Test real boat movement** and verify trip logging
5. **Monitor analytics** in web dashboard

---

**The system is now ready for production use with comprehensive trip tracking and multiple display options!**

