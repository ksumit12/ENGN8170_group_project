# Calibration Tools - Quick Reference

## The Problem This Solves

**RF signals indoors are a mess:**
- Multipath interference (reflections)
- Antenna positioning issues
- Hardware RSSI differences between scanners
- Signal fluctuation and noise

**Result:** Two scanners at the center don't show the same RSSI!

## The Solution

### 1. RF Bias Calibration (NEW - Recommended)

**Purpose:** Comprehensive calibration with bias compensation and signal smoothing

**When to use:** Setting up system at any new location, or when signals are unreliable

```bash
python3 calibration/rf_bias_calibration.py --mac AA:BB:CC:DD:EE:FF
```

**What it does:**
1. Records RSSI at CENTER, LEFT, RIGHT positions (static)
2. Calculates bias to equalize scanners
3. Records ENTER and LEAVE movement patterns (dynamic)
4. Generates calibration.json with recommended settings
5. Provides bias values to add to scanner_config.json

**Output:**
- `calibration/sessions/latest/calibration.json`
- RSSI bias values for each scanner
- Signal smoothing parameters

**Next step:** Apply bias values to `system/json/scanner_config.json`

---

### 2. Pre-Check Tool

**Purpose:** Quick validation before full calibration

```bash
python3 calibration/precheck_door_lr.py --mac AA:BB:CC:DD:EE:FF
```

**What it does:**
- Quick 5-second test at CENTER, LEFT, RIGHT
- Shows RSSI gap at each position
- Gives GO/NO-GO verdict
- Identifies antenna positioning issues

**Use this first** to verify scanners are working and positioned reasonably before doing full calibration.

---

### 3. Find Center Live

**Purpose:** Locate exact centerline of doorway

```bash
python3 calibration/find_center_live.py --mac AA:BB:CC:DD:EE:FF
```

**What it does:**
- Shows live RSSI from both scanners
- Helps you find where signals are equal
- Useful for marking physical center

---

### 4. Door LR Calibration (Legacy)

**Purpose:** Original calibration tool

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF
```

**Note:** Use `rf_bias_calibration.py` instead for better RF handling.

---

## Recommended Workflow

### First Time Setup

1. **Verify scanner operation:**
   ```bash
   hciconfig  # Both hci0 and hci1 should be UP
   ```

2. **Quick pre-check:**
   ```bash
   python3 calibration/precheck_door_lr.py --mac YOUR_BEACON_MAC
   ```
   
3. **Full RF bias calibration:**
   ```bash
   python3 calibration/rf_bias_calibration.py --mac YOUR_BEACON_MAC
   ```
   
4. **Apply bias values:**
   - Edit `system/json/scanner_config.json`
   - Add `rssi_bias_db` values from calibration output
   
5. **Restart system:**
   ```bash
   python3 boat_tracking_system.py --api-port 8000 --web-port 5000
   ```

6. **Test with physical walks:**
   - Walk beacon through door (ENTER and LEAVE)
   - Verify direction detection in dashboard
   - Check logs for direction events

### Regular Maintenance

Re-calibrate when:
- Moving scanners to new location
- Changing antenna orientation
- Direction detection becomes unreliable
- Every few months for accuracy

---

## Files

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `rf_bias_calibration.py` | **Full calibration with bias** | New setup, RF issues |
| `precheck_door_lr.py` | Quick validation | Before full calibration |
| `find_center_live.py` | Find centerline | Physical setup |
| `door_lr_calibration.py` | Legacy calibration | Old method |

---

## Output Files

### Calibration Data

```
calibration/sessions/
├── session_20251022_143500/
│   └── calibration.json        # Timestamped session
└── latest/
    └── calibration.json        # Symlink to latest (auto-loaded by system)
```

### Calibration JSON Structure

```json
{
  "timestamp": "20251022_143500",
  "static_positions": [...],
  "bias_compensation": {
    "left_bias_db": 2.5,
    "right_bias_db": -2.5
  },
  "movement_calibration": [...],
  "recommended_config": {
    "scanner_config": {...},
    "signal_smoothing": {...}
  }
}
```

System automatically loads `latest/calibration.json` on startup.

---

## Troubleshooting

### "No samples collected"

**Fix:**
- Verify beacon is broadcasting
- Check both scanners are running: `hciconfig`
- Move beacon closer to scanners
- Ensure system is running and logging detections

### "Missing scanner data"

**Fix:**
- One scanner not working
- Check: `sudo hcitool -i hci0 lescan`
- Check: `sudo hcitool -i hci1 lescan`
- Verify scanner IDs in config match actual hardware

### "Bias too large (>10 dB)"

**Fix:**
- Beacon not truly centered
- Re-measure center position
- Check antenna orientations
- Consider this may be normal for your setup (still use bias compensation)

### "Direction detection still wrong after calibration"

**Fix:**
- Did you restart system after applying bias?
- Check logs for: "Loaded RSSI bias compensation"
- Verify bias values in scanner_config.json
- Try swapping calibration map in door_lr_engine.py

---

## Understanding RF Signal Smoothing

The system uses **automatic signal filtering** to handle RF noise:

### Processing Pipeline

```
Raw RSSI → Bias Compensation → Median Filter → EMA Smoother → Direction Classifier
  -65 dBm      -65 + 2.5         -62.4 dBm       -62.7 dBm        ENTER/LEAVE
```

### Filters Applied

1. **Median Filter** (window=5)
   - Removes outlier spikes
   - Resistant to brief interference
   
2. **Exponential Moving Average** (alpha=0.3)
   - Smooths rapid fluctuations
   - Fast response with stability

### Effect on Signal

```
Time:   0    1    2    3    4    5    6    7
Raw:   -65  -58  -67  -64  -72  -63  -66  -65
Filt:  -65  -62  -64  -64  -66  -65  -65  -65
```

Notice how filtered signal is much more stable!

---

## Quick Commands

```bash
# Navigate to calibration
cd ~/grp_project/calibration

# Pre-check (quick test)
python3 precheck_door_lr.py --mac AA:BB:CC:DD:EE:FF

# Full calibration (recommended)
python3 rf_bias_calibration.py --mac AA:BB:CC:DD:EE:FF

# Find center
python3 find_center_live.py --mac AA:BB:CC:DD:EE:FF

# View latest calibration
cat sessions/latest/calibration.json

# Test RF filter
python3 ../app/rf_signal_filter.py
```

---

## For More Information

- **Full RF Calibration Guide:** `RF_CALIBRATION_GUIDE.md`
- **Two-Scanner Setup:** `../docs/TWO_SCANNER_DOOR_SETUP.md`
- **Quick Reference:** `../docs/TWO_SCANNER_QUICK_REFERENCE.md`
- **Tool Usage:** `USAGE.md`

---

**Last Updated:** October 22, 2025  
**Calibration System Version:** 2.0 with RF Bias Compensation




