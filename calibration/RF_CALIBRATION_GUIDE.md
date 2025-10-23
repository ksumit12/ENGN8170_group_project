# RF Bias Calibration Guide

## The RF Problem

Indoor RF signals are unpredictable due to:
- **Multipath**: Signals bounce off walls, ceiling, water
- **Antenna angle**: Small changes in orientation dramatically affect RSSI
- **Hardware variance**: Different BLE adapters have different sensitivities
- **Environmental interference**: Other devices, people moving, humidity

This makes it **impossible** to get identical RSSI from two scanners at the center position without calibration.

## Solution: Bias Calibration + Signal Filtering

Our system compensates for RF issues using two approaches:

1. **Static Bias Calibration**: Measure actual RSSI at known positions, calculate offsets
2. **Dynamic Signal Filtering**: Smooth out fluctuations in real-time

## Calibration Process

### Step 1: Run RF Bias Calibration

```bash
cd ~/grp_project
source .venv/bin/activate

# Replace with your beacon's MAC address
python3 calibration/rf_bias_calibration.py --mac AA:BB:CC:DD:EE:FF
```

### Step 2: Follow the Interactive Steps

The script will guide you through:

**STATIC POSITION CALIBRATION:**

1. **CENTER Position** (15 seconds)
   - Place beacon at EXACT center of doorway
   - Equidistant from both scanners
   - System measures RSSI from both scanners
   - Calculates the "bias" (difference)

2. **LEFT Position** (15 seconds)
   - Move beacon close to LEFT scanner (hci0)
   - About 0.5-1 meter away
   - Clearly favoring left side
   - System records left-side characteristics

3. **RIGHT Position** (15 seconds)
   - Move beacon close to RIGHT scanner (hci1)
   - About 0.5-1 meter away
   - Clearly favoring right side
   - System records right-side characteristics

**MOVEMENT CALIBRATION:**

4. **ENTER Movements** (3 runs)
   - Walk beacon from OUTSIDE → INSIDE
   - Simulates boat entering shed
   - Walk at normal speed
   - Each run captures RSSI patterns

5. **LEAVE Movements** (3 runs)
   - Walk beacon from INSIDE → OUTSIDE
   - Simulates boat leaving shed
   - Walk at normal speed
   - Each run captures RSSI patterns

### Step 3: Apply Calibration Values

The script will output something like:

```
Recommended Compensation:
  Left Scanner (gate-left):  +2.5 dB bias
  Right Scanner (gate-right): -2.5 dB bias
```

**Apply these values to `system/json/scanner_config.json`:**

```json
{
  "scanners": [
    {
      "id": "gate-left",
      "adapter": "hci0",
      "rssi_bias_db": 2.5
    },
    {
      "id": "gate-right",
      "adapter": "hci1",
      "rssi_bias_db": -2.5
    }
  ]
}
```

### Step 4: Restart System

```bash
# Restart to apply new bias values
python3 boat_tracking_system.py --api-port 8000 --web-port 5000
```

## Understanding the Results

### What is RSSI Bias?

If at the CENTER position:
- Left scanner reads: -60 dBm
- Right scanner reads: -65 dBm
- Bias = -60 - (-65) = +5 dB (left is stronger)

**Bias compensation:**
- Add -2.5 dB to left scanner → -60 + (-2.5) = -62.5 dBm
- Add +2.5 dB to right scanner → -65 + 2.5 = -62.5 dBm
- Result: Both show -62.5 dBm at center (equalized!)

### Why This Matters

Without calibration:
- Center position shows 5 dB difference
- System thinks beacon is closer to left scanner
- Direction detection gets confused
- False ENTER/LEAVE events

With calibration:
- Center position shows ~0 dB difference
- Clear left vs right discrimination
- Accurate direction detection
- Reliable ENTER/LEAVE events

## Signal Filtering (Automatic)

The system also applies real-time signal filtering:

### Exponential Moving Average (EMA)
- Smooths rapid RSSI fluctuations
- Alpha = 0.3 (30% new, 70% old)
- Fast response with stability

### Median Filter
- Removes outlier spikes
- Window size = 5 samples
- Resistant to interference bursts

### Combined Filter
- Median filter removes spikes first
- Then EMA smooths the cleaned signal
- Best of both worlds

Example of filtering effect:

```
Raw RSSI:    -65, -58, -67, -64, -72, -63, -66
Median:      -64, -64, -65, -64, -67, -66, -66
EMA:         -64, -64, -64, -64, -65, -65, -65
```

Notice how the filtered signal is much more stable!

## Calibration Files

After calibration, files are saved to:

```
calibration/sessions/
├── session_20251022_143500/
│   └── calibration.json
└── latest/
    └── calibration.json  ← Used by system
```

### Calibration Data Structure

```json
{
  "timestamp": "20251022_143500",
  "static_positions": [
    {
      "position": "CENTER",
      "left": {"median": -60.0, "std": 2.3},
      "right": {"median": -65.0, "std": 2.1},
      "bias": {"median_diff": 5.0}
    }
  ],
  "bias_compensation": {
    "left_bias_db": -2.5,
    "right_bias_db": 2.5
  },
  "movement_calibration": [...]
}
```

## Troubleshooting

### Problem: High variance at CENTER

```
Center Analysis:
  Left:  -60.0 dBm (std: 8.5, n=150)
  Right: -65.0 dBm (std: 7.2, n=145)
```

**Cause:** Beacon moving, RF interference, poor placement

**Solution:**
- Keep beacon completely still
- Use a stand/holder
- Avoid holding beacon (hand absorbs signal)
- Run calibration when no one else in room

### Problem: Not enough samples

```
WARNING: Missing scanner data for CENTER
  Left samples: 5, Right samples: 142
```

**Cause:** One scanner not detecting beacon

**Solution:**
- Check scanner is running: `hciconfig`
- Verify beacon is broadcasting
- Move beacon slightly closer
- Check antenna orientation

### Problem: Bias too large (>10 dB)

```
Measured Center Bias: +12.5 dB (Left - Right)
```

**Cause:** Scanners too different, or bad placement

**Solution:**
- Verify beacon is truly centered
- Check both scanners working: `sudo hcitool -i hci0 lescan`
- Try adjusting antenna angles
- Consider using RSSI bias up to ±10 dB max

### Problem: Direction detection still wrong after calibration

**Check:**
1. Did you restart system after applying bias values?
2. Is calibration file being loaded? Check logs for:
   ```
   Loaded RSSI bias compensation: {'gate-left': 2.5, 'gate-right': -2.5}
   ```
3. Are bias values in scanner_config.json correct?
4. Run calibration again in actual operating conditions

## Best Practices

### Before Calibration

1. System must be running (scanners active, database logging)
2. Use a single beacon for calibration
3. Room should be quiet (no movement, no people)
4. Beacon battery should be fresh (weak battery = weak signal)

### During Calibration

1. Keep beacon completely still at each position
2. Use a stand/holder, don't hold beacon by hand
3. Wait full collection time (15 seconds)
4. For movement runs, walk at consistent speed
5. Try to simulate actual boat movement speed

### After Calibration

1. Apply bias values to scanner_config.json
2. Restart boat tracking system
3. Verify in logs that bias is loaded
4. Test with physical beacon walks
5. Monitor direction detection accuracy

### When to Re-Calibrate

- When moving scanners to new location
- After changing antenna orientation
- If direction detection becomes unreliable
- When environmental conditions change significantly
- Every few months for maintenance

## Signal Processing Pipeline

Here's what happens to each RSSI reading:

```
1. Raw RSSI from BLE adapter
   ↓
2. Apply bias compensation (from calibration)
   ↓
3. Median filter (remove spikes)
   ↓
4. Exponential moving average (smooth)
   ↓
5. Direction classifier (detect ENTER/LEAVE)
   ↓
6. FSM state update (IN_HARBOR / OUT)
```

This pipeline handles RF issues at multiple stages for robust detection.

## Advanced: Understanding RSSI

RSSI (Received Signal Strength Indicator) is measured in dBm:

- **-30 to -50 dBm:** Excellent signal (very close)
- **-50 to -70 dBm:** Good signal (typical detection range)
- **-70 to -85 dBm:** Weak signal (far, or obstacles)
- **-85 to -100 dBm:** Very weak (at edge of range)
- **Below -100 dBm:** Too weak to use

### Path Loss

Signal decreases with distance:
- **1 meter:** ~-50 dBm
- **2 meters:** ~-56 dBm (6 dB loss)
- **4 meters:** ~-62 dBm (6 dB loss again)
- **8 meters:** ~-68 dBm

Every doubling of distance = ~6 dB loss (free space).
Indoors with obstacles: 10-15 dB loss per doubling.

### Why We Need Calibration

Two scanners at same distance might show:
- Scanner A: -60 dBm
- Scanner B: -65 dBm

Could be due to:
- Different antenna gain (hardware)
- Different antenna angle (orientation)
- Different receiver sensitivity
- One has obstruction, other doesn't

Calibration measures and compensates for these real-world differences.

## Summary

RF calibration is **essential** for reliable direction detection because:

1. **RF is unpredictable** - multipath, reflections, interference
2. **Hardware varies** - no two scanners are identical
3. **Antenna matters** - small angle changes = big RSSI changes
4. **Environment affects** - walls, water, people all impact signal

Our solution:
- **Calibrate once** - measure actual bias at your location
- **Filter continuously** - smooth out fluctuations in real-time
- **Compensate automatically** - system applies corrections

Result: **Reliable direction detection despite RF challenges**

---

**Related Documents:**
- `docs/TWO_SCANNER_DOOR_SETUP.md` - Overall setup guide
- `calibration/USAGE.md` - Calibration tools usage
- `docs/BLUETOOTH_DETECTION_EXPLAINED.md` - Technical details




