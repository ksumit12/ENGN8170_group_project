# Scanner Positioning Guide for Asymmetric Door Setup

## Understanding Asymmetric Positioning

Your door setup is **asymmetric** - one scanner is positioned slightly ahead/closer than the other. This is **normal and expected** for real-world installations.

## Expected Scanner Layout

```
                SHED INTERIOR (HARBOR)
                        |
        [LEFT Scanner]  |  [RIGHT Scanner]
          (hci0)        |      (hci1)
          CLOSER        |      FURTHER
                    DOOR OPENING
                        |
                  OUTSIDE (WATER)
```

## Detection Patterns

### ENTER Movement (Water → Shed)
```
Boat approaches from water side
↓
RIGHT scanner sees beacon first (stronger signal)
↓
LEFT scanner signal increases as boat passes through
↓
Pattern: RIGHT peak → LEFT peak
Result: ENTER detected, boat IN_HARBOR
```

### LEAVE Movement (Shed → Water)
```
Boat exits from shed side
↓
LEFT scanner sees beacon first (stronger signal)
↓
RIGHT scanner signal increases as boat passes through
↓
Pattern: LEFT peak → RIGHT peak
Result: LEAVE detected, boat OUT
```

## Calibration Analysis

The enhanced calibration system now tracks:

### Static Positioning Analysis
- **CENTER position**: Which scanner is stronger at doorway center
- **LEFT position**: Signal strength when beacon near left scanner
- **RIGHT position**: Signal strength when beacon near right scanner
- **Bias calculation**: Compensation needed to equalize scanners

### Movement Pattern Analysis
- **First detection**: Which scanner sees beacon first during movement
- **Detection timing**: How much earlier one scanner detects vs the other
- **Peak analysis**: RSSI peaks and timing between scanners
- **Pattern validation**: Whether movement follows expected ENTER/LEAVE pattern

## Calibration Output Example

```
CENTER Analysis:
  Left Scanner:  -60.0 dBm (std: 2.3, n=150)
  Right Scanner: -65.0 dBm (std: 2.1, n=145)
  Bias:          +5.0 dB (L-R)
  Positioning:   LEFT scanner is 5.0 dB stronger
  Status:        ⚠ Beacon favors LEFT scanner (difference ≥ 3 dB)

ENTER Run 1 Analysis:
  First Detection: RIGHT scanner (0.15s ahead)
  Expected Pattern: RIGHT→LEFT
  Actual Pattern:   RIGHT→LEFT
  Pattern Correct:  ✓ YES
  Left Peak:        -58.0 dBm
  Right Peak:       -55.0 dBm
  Peak Lag:         -0.12s

MOVEMENT PATTERN SUMMARY
ENTER Movements: 3/3 correct patterns
LEAVE Movements: 3/3 correct patterns

Average Detection Lag:
  ENTER: 0.18s
  LEAVE: 0.22s

SCANNER POSITIONING ANALYSIS
Static Positioning (CENTER):
  LEFT scanner is 5.0 dB stronger
  ⚠ Beacon favors LEFT scanner - may need repositioning

Movement Pattern Analysis:
  ENTER: 3/3 correct patterns
  LEAVE: 3/3 correct patterns

Scanner Positioning Recommendations:
  LEFT Scanner (hci0): Should be on SHED/INSIDE side
  RIGHT Scanner (hci1): Should be on WATER/OUTSIDE side
  Expected ENTER pattern: RIGHT scanner sees beacon first
  Expected LEAVE pattern: LEFT scanner sees beacon first

Timing Analysis:
  Average ENTER lag: 0.18s
  Average LEAVE lag: 0.22s
  ✓ Symmetric timing - scanners appear well-positioned
```

## What This Tells You

### ✓ Good Signs
- **Correct patterns**: ENTER shows RIGHT→LEFT, LEAVE shows LEFT→RIGHT
- **Consistent timing**: Similar lag times for both directions
- **Clear detection**: Strong signal differences between scanners

### ⚠ Warning Signs
- **Wrong patterns**: ENTER shows LEFT→RIGHT (scanners swapped)
- **Inconsistent timing**: Very different lag times
- **Weak signals**: Both scanners show similar weak RSSI
- **High variance**: Large standard deviation in RSSI readings

## Troubleshooting Positioning Issues

### Problem: Wrong ENTER Pattern
**Symptom**: ENTER shows LEFT→RIGHT instead of RIGHT→LEFT
**Cause**: Scanners are swapped
**Fix**: 
1. Check physical scanner placement
2. Verify hci0 is on left side, hci1 on right side
3. Update scanner_config.json if needed

### Problem: Inconsistent Timing
**Symptom**: Very different lag times for ENTER vs LEAVE
**Cause**: Scanners not equidistant from center
**Fix**:
1. Measure distance from each scanner to doorway center
2. Adjust scanner positions to be more symmetric
3. Re-run calibration

### Problem: Weak Signal Differences
**Symptom**: Small RSSI differences between scanners
**Cause**: Scanners too close together or too far apart
**Fix**:
1. Move scanners further apart (minimum 1 meter)
2. Ensure clear line of sight to doorway
3. Check for obstructions

## Optimal Scanner Positioning

### Distance Guidelines
- **Scanner separation**: 1.5-3 meters apart
- **Distance to center**: 0.5-1 meter from doorway centerline
- **Height**: 1-2 meters above ground
- **Angle**: Point toward doorway center

### Signal Strength Targets
- **At center**: Both scanners within 3 dB of each other
- **At scanner**: Target scanner 10+ dB stronger than other
- **Peak difference**: 5-15 dB between scanners during movement

## Calibration Commands

```bash
# Run enhanced calibration with positioning analysis
python3 calibration/rf_bias_calibration.py --mac YOUR_BEACON_MAC

# Check scanner positioning live
python3 calibration/find_center_live.py --mac YOUR_BEACON_MAC

# Quick pre-check before full calibration
python3 calibration/precheck_door_lr.py --mac YOUR_BEACON_MAC
```

## Key Takeaways

1. **Asymmetric positioning is normal** - don't worry if scanners aren't perfectly symmetric
2. **Pattern matters more than symmetry** - focus on getting correct ENTER/LEAVE patterns
3. **Timing consistency is important** - similar lag times indicate good positioning
4. **Calibration compensates for differences** - bias values handle asymmetric positioning
5. **Test both directions** - verify ENTER and LEAVE patterns work correctly

The enhanced calibration system will guide you through proper positioning and provide detailed analysis of your scanner setup.



