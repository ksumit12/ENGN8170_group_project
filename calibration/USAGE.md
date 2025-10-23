# Door L/R Calibration - Quick Usage Guide

##  Two Modes

### 1. Calibration Mode (Default)
Teaches the system what CENTER, LEFT, and RIGHT look like at different heights.

### 2. Live Testing Mode (`--test-live`)
Tests real-time movement detection using saved calibration.

---

##  Calibration Mode

### Full Calibration with Height Testing (Recommended)

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --duration 8
```

**What it does:**
- Tests 3 positions: CENTER, LEFT, RIGHT
- At each position, tests 3 heights:
  - **GROUND**: Lowest surface (floor/ground)
  - **CHEST**: Normal carrying height
  - **OVERHEAD**: Arms fully extended up
- **Total time**: ~2-3 minutes (9 positions × 8 seconds + prompts)

**Why height testing?**
- Beacons are carried at different heights in real use
- RF signal strength varies with height
- Aggregating across heights makes calibration more robust
- Handles the case when someone walks vs. carries beacon high

### Quick Calibration (Single Height)

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --no-heights --duration 10
```

Faster but less robust to height variations.

---

##  Live Testing Mode

### After Calibration - Test Real Movement

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --test-live
```

**Interactive testing:**
1. Choose EXIT or ENTER
2. Walk through gate at normal pace
3. System shows:
   - Raw RSSI values
   - Corrected RSSI (with offsets applied)
   - First detection (lag analysis)
   - Signal dominance
   - / Detection result

**Example session:**
```
Test 1 - Which direction? [EXIT/ENTER/Q to quit]: EXIT
Press Enter to START monitoring...

 Monitoring for 15 seconds...

  LEFT  | Raw:  -45 dBm | Corrected:  -47.5 dBm
  RIGHT | Raw:  -52 dBm | Corrected:  -49.5 dBm
  ...

 Captured 245 samples

Analyzing movement pattern...
  First detection: LEFT (lag: 0.34s)
  Left avg:  -48.2 dBm (corrected)
  Right avg: -45.1 dBm (corrected)
  Dominance: RIGHT by 3.1 dB

  Expected: EXIT
  Detection:  CORRECT
```

---

##  Typical Workflow

### Day 1: Initial Calibration

```bash
# 1. Start API server (terminal 1)
python3 boat_tracking_system.py --api-port 8000 --web-port 5000

# 2. Run full calibration (terminal 2)
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF

# Follow prompts for 3 positions × 3 heights (9 measurements)
```

**Output:**
- `calibration/sessions/latest/door_lr_calib.json` ← System uses this
- `calibration/sessions/TIMESTAMP/door_lr_calib.json` ← Archived
- Plots in `calibration/sessions/TIMESTAMP/plots/`

### Day 1: Verify Calibration

```bash
# Test live movement
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --test-live

# Try multiple EXIT and ENTER movements
# Check if detection is correct
```

### Day 2+: Quick Re-Calibration If Needed

If scanners moved or environment changed:

```bash
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF
```

---

##  Understanding Output

### RSSI Offsets

```
RSSI Offsets (to be applied by DirectionClassifier):
  Left/Inner:  -2.5 dB
  Right/Outer: +2.5 dB
```

**Meaning:**
- Left scanner is 2.5 dB stronger at center
- System subtracts 2.5 dB from left readings
- System adds 2.5 dB to right readings
- After correction, center reads as equal on both sides

### Learned Thresholds

```
Strong LEFT signal:  -42.3 dBm
Strong RIGHT signal: -44.1 dBm
LEFT dominance:      12.8 dB
RIGHT dominance:     11.5 dB
```

**Meaning:**
- When near LEFT, expect ~-42 dBm signal
- When near RIGHT, expect ~-44 dBm signal
- Dominance = gap between near/far scanner

### Quality Checks

 **GOOD Calibration:**
- Center gap: <3 dB
- Left gap: ≥6 dB
- Right gap: ≥6 dB
- Sample counts: >20 per position

 **Issues:**
- Center gap >3 dB → Reposition beacon
- Side gaps <6 dB → Move closer to scanner
- Low samples → Check scanner connectivity

---

##  Troubleshooting

### No samples collected

**Cause:** Scanners not posting to API

**Fix:**
```bash
# Check if scanners are running
ps aux | grep scanner

# Check API server
curl http://127.0.0.1:8000/api/presence
```

### High center gap (>3 dB)

**Causes:**
- Beacon not at true center
- Physical obstacles
- Scanner power imbalance

**Fixes:**
- Use measuring tape for exact center
- Remove metal objects
- Check scanner antenna positions

### Live testing shows wrong direction

**Causes:**
- Calibration quality issues
- Walking too fast/slow
- Beacon orientation changed

**Fixes:**
- Re-run calibration
- Walk at consistent pace
- Keep beacon orientation same as calibration

---

##  Tips

### For Best Results

1. **Use same beacon** for calibration and testing
2. **Keep orientation consistent** (don't rotate beacon)
3. **Normal walking speed** during movement tests
4. **Avoid metal objects** near scanners during calibration
5. **Test at multiple times of day** (RF can vary)

### Height Testing Strategy

- **Ground**: Place directly on floor at each position
- **Chest**: Hold at sternum height (natural carrying)
- **Overhead**: Fully extend arms up (maximum height)

### When to Re-Calibrate

- Scanner positions changed
- New installation location
- Seasonal/environmental changes
- Detection accuracy drops below 80%
- Adding new type of beacon

---

##  Integration

Once calibrated, the system automatically:
1. Loads offsets from `calibration/sessions/latest/door_lr_calib.json`
2. Applies corrections to all RSSI readings
3. Uses learned thresholds for decisions
4. Updates in real-time as boats move

No manual steps needed - just restart `boat_tracking_system.py`!

---

##  Advanced

### Custom Duration Per Height

```bash
# Longer sampling for noisy environments
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --duration 12
```

### Skip Heights (Faster)

```bash
# Single height measurement
python3 calibration/door_lr_calibration.py --mac AA:BB:CC:DD:EE:FF --no-heights
```

### View Calibration History

```bash
ls -lt calibration/sessions/
cat calibration/sessions/latest/door_lr_calib.json | python3 -m json.tool
```

---

**Need Help?** See `CALIBRATION_GUIDE.md` for detailed explanations.









