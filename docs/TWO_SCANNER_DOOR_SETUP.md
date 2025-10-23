# Two-Scanner Door Left/Right Setup Guide

## Overview

This system uses TWO BLE scanners positioned at the left and right sides of the shed door to accurately detect boat entry and exit direction using RSSI (signal strength) patterns.

## Architecture

```
                SHED INTERIOR (HARBOR)
                        |
        [Scanner LEFT]  |  [Scanner RIGHT]
          (hci0)        |      (hci1)
                    DOOR OPENING
                        |
                  OUTSIDE (WATER)
```

### How Direction Detection Works

1. **ENTER (Water → Shed):**
   - Boat approaches from outside
   - RIGHT scanner sees beacon first (strong signal)
   - LEFT scanner signal increases as boat passes through door
   - RIGHT signal decreases
   - Pattern: RIGHT peak → LEFT peak (negative lag)
   - Result: Boat marked IN_HARBOR, trip ended

2. **LEAVE (Shed → Water):**
   - Boat exits from shed
   - LEFT scanner sees beacon first (strong signal)
   - RIGHT scanner signal increases as boat passes through door
   - LEFT signal decreases
   - Pattern: LEFT peak → RIGHT peak (positive lag)
   - Result: Boat marked OUT, trip started

## Configuration

### 1. Scanner Configuration

File: `system/json/scanner_config.json`

```json
{
  "api_host": "localhost",
  "api_port": 8000,
  "gates": [
    {
      "id": "gate-1",
      "hysteresis": { 
        "enter_dbm": -58, 
        "exit_dbm": -64, 
        "min_hold_ms": 1200 
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

### 2. FSM Engine Configuration

File: `api_server.py`

The system is configured to use `DoorLREngine`:

```python
os.environ['FSM_ENGINE'] = 'app.door_lr_engine:DoorLREngine'
```

### 3. DirectionClassifier Parameters

File: `app/door_lr_engine.py`

Current parameters (tuned for testing):

```python
LRParams(
    active_dbm=-90,          # Threshold for active detection
    energy_dbm=-85,          # Threshold for strong signal
    delta_db=2.0,            # Min RSSI difference between scanners
    dwell_s=0.05,            # Min time beacon must be seen
    window_s=0.5,            # Time window for analysis
    tau_min_s=0.05,          # Min time between peaks
    cooldown_s=1.0,          # Cooldown after detection event
    slope_min_db_per_s=2.0,  # Min RSSI change rate
    min_peak_sep_s=0.05      # Min peak separation time
)
```

**Tuning Guidelines:**

- **Door Width:** Wider doors → increase `window_s` and `min_peak_sep_s`
- **Boat Speed:** Slower boats → increase `dwell_s` and `window_s`  
- **Signal Strength:** Weaker beacons → decrease `active_dbm` and `energy_dbm`
- **False Detections:** Too many → increase `delta_db` and `slope_min_db_per_s`

## Hardware Setup

### Physical Placement

1. **Left Scanner (hci0):**
   - Mount on left side of door (when looking from inside shed)
   - Height: Same as boat beacon height (typically 1-2m)
   - Distance from door: 0.5-1m inside shed
   - Clear line of sight through doorway

2. **Right Scanner (hci1):**
   - Mount on right side of door (when looking from inside shed)
   - Height: Same as left scanner
   - Distance from door: 0.5-1m inside shed  
   - Clear line of sight through doorway

### Scanner Identification

Verify your BLE adapters:

```bash
hciconfig
# Should show:
# hci0: ...
# hci1: ...
```

Test individual scanners:

```bash
# Left scanner (hci0)
sudo hcitool -i hci0 lescan

# Right scanner (hci1)
sudo hcitool -i hci1 lescan
```

## Running the System

### Start Everything

```bash
cd ~/grp_project
source .venv/bin/activate

# Start the main system
python3 boat_tracking_system.py \
  --api-port 8000 \
  --web-port 5000 \
  --display-mode web \
  --db-path data/boat_tracking.db
```

### Monitor Scanner Activity

```bash
# Real-time scanner monitoring
python3 scripts/ibeacon_dual_monitor.py

# Monitor detection sequences
python3 scripts/monitor_scanner_sequences.py
```

## Testing with Simulator

The simulator now always simulates two-scanner behavior:

```bash
# Test boat movements
python3 sim_run_simulator.py --boat boat_001 --direction exit
python3 sim_run_simulator.py --boat boat_001 --direction enter
```

Expected output:
```
EXIT boat_001 (AA:BB:CC:DD:EE:FF)
  Movement: Shed -> Left -> Right -> Water
  [Shows RSSI patterns from both scanners]
  -> Boat should be ON WATER

ENTER boat_001 (AA:BB:CC:DD:EE:FF)
  Movement: Water -> Right -> Left -> Shed
  [Shows RSSI patterns from both scanners]
  -> Boat should be IN SHED
```

## Calibration

### Pre-calibration Check

```bash
python3 calibration/precheck_door_lr.py
```

This verifies:
- Both scanners are detecting beacons
- RSSI levels are appropriate
- Signal patterns show clear left/right peaks

### Full Calibration

```bash
python3 calibration/door_lr_calibration.py
```

Follow the prompts:
1. Walk beacon from shed → water (EXIT)
2. Walk beacon from water → shed (ENTER)
3. Repeat 5-10 times
4. Review calibration results

The calibration will suggest optimal parameter values for your specific setup.

### Finding Center Point

```bash
python3 calibration/find_center_live.py
```

This helps determine the exact door centerline based on RSSI patterns.

## Troubleshooting

### Boats Not Detected

**Check:**
1. Are both scanners running? `hciconfig`
2. Are beacons broadcasting? `scripts/ibeacon_dual_monitor.py`
3. Is RSSI above threshold? Check logs for "RSSI below threshold"
4. Are scanner IDs correct? Should end with `-left` or `-right`

### Wrong Direction Detected

**Check:**
1. Scanner placement - left should be on left, right on right
2. Calibration map in `door_lr_engine.py`:
   ```python
   calib_map = {"lag_positive": "LEAVE", "lag_negative": "ENTER"}
   ```
3. If reversed, swap to:
   ```python
   calib_map = {"lag_positive": "ENTER", "lag_negative": "LEAVE"}
   ```

### No Direction Events Generated

**Check:**
1. RSSI patterns in logs - are both scanners seeing the beacon?
2. Parameters might be too strict - try decreasing `delta_db` and `slope_min_db_per_s`
3. Window might be too short - try increasing `window_s`
4. Check logs for: "DoorLREngine: ... events=0"

### Too Many False Detections

**Tune:**
1. Increase `delta_db` (require larger signal difference)
2. Increase `slope_min_db_per_s` (require faster RSSI changes)
3. Increase `min_peak_sep_s` (require more time between peaks)
4. Increase `cooldown_s` (prevent rapid re-triggering)

## System Components

### Key Files

| File | Purpose |
|------|---------|
| `app/door_lr_engine.py` | Main FSM engine for two-scanner logic |
| `app/direction_classifier.py` | RSSI pattern analysis and direction determination |
| `ble_scanner.py` | BLE beacon detection (one instance per scanner) |
| `scanner_service.py` | Multi-scanner management |
| `api_server.py` | API and FSM orchestration |
| `system/json/scanner_config.json` | Scanner configuration |

### Database Events

The system logs to `shed_events` table:
- `OUT_SHED` - Boat detected leaving (LEAVE direction)
- `IN_SHED` - Boat detected entering (ENTER direction)

Each event includes:
- Timestamp
- Boat ID
- Beacon ID
- Event type

## Advanced: Parameter Optimization

### Empirical Tuning Process

1. **Collect Data:**
   ```bash
   python3 calibration/door_lr_calibration.py
   ```

2. **Analyze Patterns:**
   - Review lag histograms
   - Note average lag times
   - Check RSSI peak characteristics

3. **Adjust Parameters:**
   - Set `window_s` = 2× average lag time
   - Set `min_peak_sep_s` = 0.5× average lag time
   - Set `delta_db` = 50% of observed peak RSSI difference
   - Set `active_dbm` = -10dB below weakest reliable detection

4. **Test and Iterate:**
   ```bash
   python3 sim_run_simulator.py --boat test_boat --direction exit
   python3 sim_run_simulator.py --boat test_boat --direction enter
   ```

### Physical Setup Optimization

For best results:
- **Scanner spacing:** 2-3 meters apart
- **Door width:** 1-2 meters (wider doors need more separation)
- **Mounting height:** Match beacon height (1-2m typically)
- **Environment:** Minimize metal reflections, keep scanners stationary

## Status Indicators

### Dashboard View

Navigate to `http://localhost:5000` to see:
- Current boat status (IN HARBOR / ON WATER)
- Recent trips with entry/exit times
- Scanner status (both left and right)
- Detection events in real-time

### Logs

```bash
# Main system log
tail -f logs/boat_tracking.log | grep "DoorLREngine"

# Direction events
tail -f logs/boat_tracking.log | grep "direction"

# Scanner detections  
tail -f logs/boat_tracking.log | grep "SCANNER"
```

## Summary

The two-scanner door left/right system provides accurate directional tracking by:

1. Using TWO BLE scanners (left and right of door)
2. Analyzing RSSI patterns to determine movement direction
3. Detecting which scanner sees the beacon first (time lag)
4. Comparing signal strength patterns between scanners
5. Automatically logging entry/exit events with timestamps

This enables precise boat tracking without manual input, supporting automatic trip logging and real-time harbor/water status.

---

**Last Updated:** October 22, 2025  
**System Version:** Boat Tracking System v2.1 with Two-Scanner Door Detection




