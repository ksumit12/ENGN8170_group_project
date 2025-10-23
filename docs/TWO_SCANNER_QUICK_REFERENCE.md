# Two-Scanner Door Setup - Quick Reference

## System Configuration

**Branch:** `working-single-scanner` (now configured for two scanners)  
**FSM Engine:** `DoorLREngine`  
**Scanners:** 2 (gate-left on hci0, gate-right on hci1)

## Quick Start

```bash
# 1. Start system
cd ~/grp_project
source .venv/bin/activate
python3 boat_tracking_system.py --api-port 8000 --web-port 5000 --display-mode web

# 2. Monitor scanners
python3 scripts/ibeacon_dual_monitor.py

# 3. Test with simulator
python3 sim_run_simulator.py --boat boat_001 --direction exit
python3 sim_run_simulator.py --boat boat_001 --direction enter
```

## Scanner Setup

| Scanner | Adapter | Position | Scanner ID |
|---------|---------|----------|------------|
| Left    | hci0    | Left side of door (inside view) | gate-left |
| Right   | hci1    | Right side of door (inside view) | gate-right |

## Detection Logic

### ENTER (Water to Shed)
```
Boat movement: Water → RIGHT scanner → LEFT scanner → Shed
RSSI pattern: RIGHT peak first, then LEFT peak
Time lag: Negative (RIGHT leads LEFT)
Result: Boat IN_HARBOR, trip ends
```

### LEAVE (Shed to Water)
```
Boat movement: Shed → LEFT scanner → RIGHT scanner → Water
RSSI pattern: LEFT peak first, then RIGHT peak  
Time lag: Positive (LEFT leads RIGHT)
Result: Boat OUT, trip starts
```

## Key Files

- **Configuration:** `system/json/scanner_config.json`
- **FSM Engine:** `app/door_lr_engine.py`
- **Direction Logic:** `app/direction_classifier.py`
- **API Server:** `api_server.py` (line 34: FSM_ENGINE setting)

## Parameters (Current Settings)

```python
active_dbm = -90       # Detection threshold
energy_dbm = -85       # Strong signal threshold
delta_db = 2.0         # Min RSSI difference
dwell_s = 0.05         # Min dwell time
window_s = 0.5         # Analysis window
tau_min_s = 0.05       # Min lag time
cooldown_s = 1.0       # Event cooldown
slope_min_db_per_s = 2.0  # Min RSSI change rate
min_peak_sep_s = 0.05     # Min peak separation
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No detections | Check `hciconfig`, verify both scanners running |
| Wrong direction | Verify scanner placement (left/right), check calib_map |
| False detections | Increase delta_db, slope_min_db_per_s, cooldown_s |
| Missed detections | Decrease delta_db, increase window_s |

## Calibration Commands

```bash
# Pre-check
python3 calibration/precheck_door_lr.py

# Full calibration
python3 calibration/door_lr_calibration.py

# Find center point
python3 calibration/find_center_live.py
```

## Dashboard Access

- **Local:** `http://localhost:5000`
- **Status:** Shows IN HARBOR / ON WATER
- **Events:** Real-time entry/exit logging

## Logs

```bash
# Direction events
tail -f logs/boat_tracking.log | grep "DoorLREngine"

# All detections
tail -f logs/boat_tracking.log | grep "SCANNER"
```

## Parameter Tuning Quick Guide

- **Wider door:** Increase `window_s`, `min_peak_sep_s`
- **Slower boats:** Increase `dwell_s`, `window_s`
- **Weaker signal:** Decrease `active_dbm`, `energy_dbm`
- **More strict:** Increase `delta_db`, `slope_min_db_per_s`

## Next Steps

1. Test with physical beacons
2. Calibrate for your specific door/scanner setup
3. Tune parameters based on real-world performance
4. Monitor and log several entry/exit cycles
5. Adjust as needed

For complete details, see: `docs/TWO_SCANNER_DOOR_SETUP.md`




