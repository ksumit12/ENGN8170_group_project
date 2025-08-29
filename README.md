# Bluetooth Selfie Stick Button Logger

A robust Python script for logging button presses from Bluetooth selfie stick devices (like Q07/PICO) that automatically handles device sleep/wake cycles and disconnections.

## Features

- **Automatic Device Detection**: Finds and monitors Bluetooth HID devices with volume control buttons
- **Sleep/Wake Handling**: Automatically detects when devices go to sleep and wakes them up
- **Resilient Operation**: Survives device disconnections and reconnections
- **Real-time Logging**: Logs button presses with timestamps to CSV
- **Non-blocking I/O**: Uses efficient select() polling for multiple devices
- **No Device Grabbing**: Works alongside system volume controls

## Files

- `bt_trigger_logger.py` - Main working logger script
- `bt_triggers.csv` - Log file for button presses
- `README.md` - This documentation

## Prerequisites

1. **Python 3.6+** with the following packages:
   ```bash
   pip3 install evdev
   ```

2. **Root access** (required for reading input devices):
   ```bash
   sudo python3 bt_trigger_logger.py
   ```

3. **Bluetooth tools**:
   ```bash
   sudo apt-get install bluetooth bluez bluetoothctl
   ```

## Setup

### 1. Pair Your Device

First, make sure your Bluetooth selfie stick is paired:

```bash
bluetoothctl
> scan on
> pair FF:05:11:50:24:E0  # Replace with your device's MAC
> trust FF:05:11:50:24:E0
> connect FF:05:11:50:24:E0
```

### 2. Run the Logger

Start the main logger:

```bash
sudo python3 bt_trigger_logger.py
```

## How It Works

The script automatically:

1. **Scans for devices** that support `KEY_VOLUMEDOWN` (or other configurable keys)
2. **Monitors multiple devices** simultaneously using efficient I/O polling
3. **Handles sleep/wake cycles** - when a device goes to sleep, it's automatically removed from monitoring
4. **Reconnects automatically** - rescans for devices every 0.5 seconds
5. **Logs button presses** to CSV with timestamps and device information

## Configuration

You can modify these settings at the top of `bt_trigger_logger.py`:

```python
PREFERRED_NAMES = {"Q07", "PICO"}   # Device names to prefer
WATCH_CODE = ecodes.KEY_VOLUMEDOWN   # Button code to monitor
CSV_PATH = "bt_triggers.csv"         # Log file path
GRAB_DEVICE = False                  # Don't grab devices (let system work)
RESCAN_INTERVAL = 0.5                # Device rescan interval in seconds
```

## Usage

### Basic Usage

```bash
sudo python3 bt_trigger_logger.py
```

The script will:
- Automatically detect your Bluetooth device
- Start monitoring for button presses
- Log all presses to `bt_triggers.csv`
- Handle device sleep/wake cycles automatically

### Monitor Different Buttons

To monitor different buttons, change `WATCH_CODE`:

```python
# Monitor play/pause button
WATCH_CODE = ecodes.KEY_PLAYPAUSE

# Monitor next song button  
WATCH_CODE = ecodes.KEY_NEXTSONG

# Monitor power button
WATCH_CODE = ecodes.KEY_POWER
```

## Log Format

Button presses are logged to `bt_triggers.csv` with these columns:

- `iso_time_utc` - ISO 8601 timestamp in UTC
- `epoch_s` - Unix timestamp with microseconds
- `device_path` - Device path (e.g., /dev/input/event18)
- `device_name` - Device name (e.g., Q07)
- `value` - Event value (1 = press, 0 = release, 2 = repeat)
- `meaning` - Human-readable event description

## Troubleshooting

### Device Not Found

1. **Check Bluetooth connection**:
   ```bash
   bluetoothctl info FF:05:11:50:24:E0
   ```

2. **Verify device is paired**:
   ```bash
   bluetoothctl paired-devices
   ```

3. **Check input devices**:
   ```bash
   sudo cat /proc/bus/input/devices | grep -i q07
   ```

### Permission Denied

1. **Run with sudo**:
   ```bash
   sudo python3 bt_trigger_logger.py
   ```

2. **Add udev rule** (alternative to sudo):
   ```bash
   # Create file: /etc/udev/rules.d/99-input-permissions.rules
   KERNEL=="event*", SUBSYSTEM=="input", MODE="0666"
   ```

### Device Goes to Sleep

This is **normal behavior**! The script automatically handles:
- Device sleep detection
- Automatic removal from monitoring
- Re-scanning for when devices wake up
- Re-connection when devices become available again

## Systemd Service (Optional)

Create a systemd service to run the logger automatically:

```bash
# Create service file: /etc/systemd/system/bt-logger.service
[Unit]
Description=Bluetooth Selfie Stick Logger
After=bluetooth.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /path/to/bt_trigger_logger.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl enable bt-logger.service
sudo systemctl start bt-logger.service
```

## Technical Details

- **I/O Model**: Uses `select()` for efficient multi-device monitoring
- **Error Handling**: Gracefully handles `ENODEV` (device sleep) and `EIO` (disconnect) errors
- **Device Management**: Automatically opens/closes devices as they appear/disappear
- **Memory Efficient**: Only keeps active devices in memory

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is open source and available under the MIT License.
