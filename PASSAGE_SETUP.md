# Boat Tracking Passage Setup Guide

## Scanner Configuration

### Physical Setup:
- **hci0 (Left Scanner)**: Position on the LEFT side of the passage
- **hci1 (Right Scanner)**: Position on the RIGHT side of the passage
- **Distance between scanners**: 2-3 meters apart (adjust based on your passage width)

### Detection Zones:
- **Left Scanner (hci0)**: 
  - RSSI threshold: -60 dBm
  - Detection range: ~1 meter
  - Triggers when beacon approaches from left side

- **Right Scanner (hci1)**:
  - RSSI threshold: -55 dBm  
  - Detection range: ~0.5 meters
  - Triggers when beacon approaches from right side

## Passage Flow:

```
[Left Scanner hci0]     [Right Scanner hci1]
      |                        |
      |    Passage Area        |
      |                        |
      |                        |
```

## Entry/Exit Detection Logic:

### Entry (Boat entering harbor):
1. **Left scanner detects first** → Boat approaching from left
2. **Right scanner detects** → Boat has passed through passage
3. **System logs**: "Boat entered harbor"

### Exit (Boat leaving harbor):
1. **Right scanner detects first** → Boat approaching from right
2. **Left scanner detects** → Boat has passed through passage  
3. **System logs**: "Boat left harbor"

## Testing Your Setup:

1. **Position scanners** 2-3 meters apart
2. **Test left scanner**: Walk with beacon near hci0 - should detect at ~1m
3. **Test right scanner**: Walk with beacon near hci1 - should detect at ~0.5m
4. **Test passage flow**: Walk through the passage with beacon
5. **Check logs**: Verify entry/exit detection is working

## Troubleshooting:

- **Both scanners detect simultaneously**: Move scanners further apart
- **No detection**: Lower RSSI threshold (e.g., -70 dBm)
- **False detections**: Raise RSSI threshold (e.g., -50 dBm)
- **Wrong direction detection**: Swap scanner positions

## Current Configuration:
- Left Scanner: hci0, RSSI threshold -60 dBm
- Right Scanner: hci1, RSSI threshold -55 dBm
- Both using TP-Link BLE adapters only
