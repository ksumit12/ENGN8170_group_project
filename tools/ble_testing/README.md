# BLE Testing Tools

This folder contains tools for testing BLE scanners and their range capabilities.

## Files

- **`identify_ble_dongles.py`** - Identifies available BLE dongles/adapters on the system
- **`scanner_range_test.py`** - Simple range testing tool for individual BLE dongles
- **`ble_scanner_tester.py`** - Comprehensive BLE scanner testing with multiple features
- **`BLE_TESTING_GUIDE.md`** - Complete guide for testing BLE scanner range

## Quick Start

1. **Identify your BLE dongles:**
   ```bash
   python3 identify_ble_dongles.py
   ```

2. **Test range of a specific dongle:**
   ```bash
   python3 scanner_range_test.py --adapter hci0 --duration 60
   ```

3. **Test all dongles:**
   ```bash
   python3 scanner_range_test.py --test-all --duration 30
   ```

## Usage

These tools help you:
- Find available BLE adapters on your Raspberry Pi
- Test the range of each BLE dongle individually
- Compare performance between different dongles
- Determine optimal placement for your boat tracking system

See `BLE_TESTING_GUIDE.md` for detailed instructions.
