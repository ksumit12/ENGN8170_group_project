# Door L/R Calibration Guide

## Overview

The Door L/R system uses a **3-step bias calibration** to teach it what different beacon positions look like. This calibration generates RSSI offsets that equalize the signals in real-time, solving RF variability issues.

## Calibration Workflow

### Prerequisites
1. Both scanners (gate-left and gate-right) must be running
2. API server must be running (`python3 boat_tracking_system.py`)
3. One test beacon available

### Step 1: Geometry Check (Optional but Recommended)

First, verify your scanner geometry is good:

```bash
python3 calibration/precheck_door_lr.py --mac AA:BB:CC:DD:EE:FF
```

**Expected results:**
- Center gap: <3 dB
- Left gap: ≥6 dB  
- Right gap: ≥6 dB

If geometry check fails, adjust scanner positions before proceeding.

### Step 2: Run 3-Step Calibration

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --duration 10
```

The script will guide you through three positions:

**Position 1: CENTER**
- Place beacon exactly in the middle between scanners
- System learns the zero-bias point
- Target: Both scanners see similar RSSI (gap <3 dB)

**Position 2: LEFT**
- Place beacon close to LEFT/INNER scanner
- System learns what "strong left" looks like
- Target: Left scanner much stronger (gap ≥6 dB)

**Position 3: RIGHT**  
- Place beacon close to RIGHT/OUTER scanner
- System learns what "strong right" looks like
- Target: Right scanner much stronger (gap ≥6 dB)

### Step 3: Review Results

The calibration generates:
- **RSSI Offsets**: Applied to equalize signals
- **Thresholds**: Learned characteristics for left/right dominance
- **Plots**: Visual validation of calibration quality

Files saved to:
- `calibration/sessions/latest/door_lr_calib.json` ← **System loads this**
- `calibration/sessions/TIMESTAMP/door_lr_calib.json` ← Archived session

### Step 4: Apply Calibration

Restart the boat tracking system to load new calibration:

```bash
# Stop current system
pkill -f boat_tracking_system

# Start with new calibration
python3 boat_tracking_system.py --api-port 8000 --web-port 5000
```

### Step 5: Test

Run simulator to verify improved detection:

```bash
python3 door_lr_simulator.py --test-movements 6 --log-file test_after_calib.jsonl
```

## Understanding the Calibration Output

### RSSI Offsets

The calibration calculates offsets to equalize signals:

```json
{
  "rssi_offsets": {
    "gate-left": -2.5,   // Subtract 2.5 dB from left readings
    "gate-right": +2.5   // Add 2.5 dB to right readings
  }
}
```

**Effect**: After applying offsets, a beacon at CENTER will have equal L/R signals.

### Learned Thresholds

```json
{
  "thresholds": {
    "strong_left": -45.0,         // Expected RSSI near left scanner
    "strong_right": -47.0,        // Expected RSSI near right scanner
    "left_dominance": 12.5,       // Gap when near left
    "right_dominance": 11.8       // Gap when near right
  }
}
```

These guide the DirectionClassifier's decision-making.

## Troubleshooting

### Issue: Center gap >3 dB

**Causes:**
- Beacon not at true center
- Physical obstacles/reflections
- Scanner power imbalance

**Solutions:**
- Use a measuring tape to find exact center
- Remove metal objects near scanners
- Check scanner antenna orientation

### Issue: Side gaps <6 dB

**Causes:**
- Scanners too close together
- Beacon not close enough to scanner
- Poor scanner separation

**Solutions:**
- Move beacon closer to scanner (within 30cm)
- Increase scanner separation
- Run `precheck_door_lr.py` to verify geometry

### Issue: Low sample counts

**Causes:**
- Scanner not posting to API
- Beacon battery low
- Duration too short

**Solutions:**
- Check scanner logs
- Replace beacon battery
- Increase `--duration` parameter

## Maintenance

### When to Re-Calibrate

Re-run calibration if:
- Scanner positions change
- Detection accuracy drops
- New beacons with different characteristics
- Environmental changes (new walls/reflections)

### Calibration History

All calibrations are archived in `calibration/sessions/TIMESTAMP/`:
- `door_lr_calib.json` - Calibration data
- `plots/` - Visual diagnostics

## Advanced Options

### Custom Duration

Collect more samples for noisy environments:

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --duration 20
```

### Direct Scanning (No DB)

For offline calibration:

```bash
python3 calibration/find_center_live.py --mac AA:BB:CC:DD:EE:FF --scan --save-offsets
```

## Integration with System

The DirectionClassifier automatically loads calibration from:
```
calibration/sessions/latest/door_lr_calib.json
```

On startup, it:
1. Loads RSSI offsets
2. Applies offsets to all readings
3. Uses learned thresholds for decision-making

This makes the system robust to RF variability and scanner asymmetries.

## See Also

- `precheck_door_lr.py` - Geometry validation
- `find_center_live.py` - Live center-finding tool  
- `door_lr_simulator.py` - Testing tool
- `FSM_KNOWLEDGE_BASE.md` - System architecture

---

**Pro Tip**: Keep your beacon at the exact same height for all three positions to maintain consistent measurements!





