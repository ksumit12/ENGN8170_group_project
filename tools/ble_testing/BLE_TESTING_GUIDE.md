# BLE Scanner Range Testing Guide

This guide helps you test your two BLE dongles on the Raspberry Pi and determine their individual ranges with beacons.

## Quick Start

### 1. Identify Your BLE Dongles
```bash
python3 identify_ble_dongles.py
```
This will show you all available Bluetooth adapters and USB devices.

### 2. Test Individual Scanner Range
```bash
# Test first dongle (usually hci0)
python3 scanner_range_test.py --adapter hci0 --duration 60

# Test second dongle (usually hci1)
python3 scanner_range_test.py --adapter hci1 --duration 60
```

### 3. Test All Dongles at Once
```bash
python3 scanner_range_test.py --test-all --duration 30
```

### 4. Interactive Range Test
```bash
# Test with a specific beacon
python3 scanner_range_test.py --interactive "beacon_1" --duration 120
```

## Detailed Testing Process

### Step 1: Identify Your Dongles
Run the identification script to see what BLE adapters are available:
```bash
python3 identify_ble_dongles.py
```

Expected output:
```
IDENTIFYING BLE DONGLES/ADAPTERS
========================================

1. BLUETOOTH ADAPTERS (hciconfig):
-----------------------------------
  Adapter 1: hci0
    MAC: AA:BB:CC:DD:EE:FF
    Status: UP

  Adapter 2: hci1
    MAC: 11:22:33:44:55:66
    Status: UP
```

### Step 2: Test Each Dongle Individually

#### Test Dongle 1 (hci0):
```bash
python3 scanner_range_test.py --adapter hci0 --duration 60
```

**Instructions:**
1. Start at the scanner location (0m)
2. Walk away slowly while holding your beacon
3. Note when the beacon stops being detected
4. Return and repeat in different directions
5. Try with obstacles (walls, doors, etc.)

#### Test Dongle 2 (hci1):
```bash
python3 scanner_range_test.py --adapter hci1 --duration 60
```

Repeat the same process as above.

### Step 3: Compare Results

The script will show you:
- **RSSI range**: Signal strength range (higher = closer)
- **Distance estimates**: Approximate distance in meters
- **Maximum range**: Farthest distance where beacon was detected
- **Signal quality**: How consistent the signal is

### Step 4: Test with Specific Beacons

If you have multiple beacons, test each one:
```bash
# Test with beacon named "beacon_1"
python3 scanner_range_test.py --adapter hci0 --beacon "beacon_1" --duration 60

# Test with beacon named "beacon_2"
python3 scanner_range_test.py --adapter hci1 --beacon "beacon_2" --duration 60
```

## Understanding the Results

### RSSI Values
- **-30 to -50 dBm**: Very close (0-2 meters)
- **-50 to -70 dBm**: Close (2-10 meters)
- **-70 to -90 dBm**: Medium range (10-30 meters)
- **-90 to -100 dBm**: Far (30+ meters)

### Distance Estimates
The script provides distance estimates based on RSSI, but these are approximate. Real range depends on:
- Beacon transmission power
- Environmental obstacles
- Interference from other devices
- Antenna orientation

### Range Testing Tips

1. **Start Close**: Begin at the scanner location
2. **Walk Slowly**: Move gradually to find the exact cutoff point
3. **Test Multiple Directions**: Range may vary by direction
4. **Test with Obstacles**: Walls, doors, and metal objects affect range
5. **Test Multiple Times**: Range can vary due to interference
6. **Note Environmental Factors**: Other devices, WiFi, etc.

## Troubleshooting

### No Beacons Found
- Make sure your beacon is powered on
- Check if beacon is in pairing/discoverable mode
- Try different beacon names or MAC addresses
- Increase scan duration

### Adapter Not Found
- Check if dongle is properly connected
- Try different adapter names (hci0, hci1, hci2, etc.)
- Check USB connection
- Restart Bluetooth service: `sudo systemctl restart bluetooth`

### Permission Issues
- Run with sudo if needed: `sudo python3 scanner_range_test.py`
- Check if user is in bluetooth group: `sudo usermod -a -G bluetooth $USER`

## Advanced Testing

### Test All Adapters
```bash
python3 scanner_range_test.py --test-all --duration 30
```

### Comprehensive Testing
```bash
python3 ble_scanner_tester.py --discover
python3 ble_scanner_tester.py --scan 60
python3 ble_scanner_tester.py --range-test "beacon_1" --duration 120
```

## Expected Results

After testing, you should know:
1. **Which dongle has better range**
2. **Maximum detection distance for each dongle**
3. **Best placement for each dongle**
4. **Environmental factors that affect range**
5. **Optimal beacon placement for your use case**

## Next Steps

Once you know the range of each dongle:
1. Place them strategically in your boat tracking area
2. Configure your boat tracking system to use both dongles
3. Set up proper entry/exit zones based on range data
4. Test with actual boats and beacons
