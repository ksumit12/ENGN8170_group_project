#!/bin/bash
# Simplified WiFi Emergency Notification Setup Script
# Sets up WiFi-based emergency boat notifications with vibration

set -e

echo "Setting up WiFi Emergency Boat Notification System..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root"
   exit 1
fi

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    print_error "Python 3.8 or higher is required. Found: $python_version"
    exit 1
fi

print_status "Python version check passed: $python_version"

# Install required Python packages
print_header "Installing Python Dependencies"

pip3 install --user pywebpush==1.14.0
pip3 install --user cryptography==41.0.7
pip3 install --user python-dotenv==1.0.0

print_status "Python dependencies installed"

# Create necessary directories
print_header "Creating Directory Structure"

mkdir -p static/sounds
mkdir -p static/icons
mkdir -p static/images
mkdir -p logs/wifi-emergency
mkdir -p data/wifi-emergency

print_status "Directory structure created"

# Generate VAPID keys for web push notifications
print_header "Generating VAPID Keys"

if ! command -v openssl &> /dev/null; then
    print_warning "OpenSSL not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y openssl
fi

# Generate VAPID key pair
vapid_private_key=$(openssl ecparam -name prime256v1 -genkey -noout | openssl ec -outform der | openssl base64 -A)
vapid_public_key=$(openssl ec -in <(echo "$vapid_private_key" | openssl base64 -d -A) -pubout -outform der | openssl base64 -A)

print_status "VAPID keys generated"

# Create environment file
print_header "Creating WiFi Emergency Configuration"

cat > .env.wifi-emergency << EOF
# WiFi Emergency Notification System Configuration

# VAPID Keys for Web Push Notifications
VAPID_PRIVATE_KEY="$vapid_private_key"
VAPID_PUBLIC_KEY="$vapid_public_key"

# Database Configuration
DB_PATH=data/boat_tracking.db
DB_ENCRYPTION_KEY=$(openssl rand -base64 32)

# WiFi Emergency Notification Settings
WIFI_EMERGENCY_CLOSING_TIME=18:00
WIFI_EMERGENCY_CHECK_INTERVAL=60
WIFI_EMERGENCY_ESCALATION_ENABLED=true

# Dashboard URL
DASHBOARD_URL=http://localhost:5000

# WiFi Network Settings
WIFI_NETWORK_SSID=Red Shed WiFi
WIFI_NETWORK_RANGE=192.168.1.0/24
EOF

print_status "WiFi emergency configuration created"

# Create emergency notification sounds
print_header "Creating Emergency Notification Sounds"

# Create placeholder sound files (in production, use real sound files)
cat > static/sounds/alert.mp3 << 'EOF'
# Placeholder for alert sound
# Replace with actual MP3 file
EOF

cat > static/sounds/emergency.mp3 << 'EOF'
# Placeholder for emergency sound
# Replace with actual MP3 file
EOF

cat > static/sounds/critical.mp3 << 'EOF'
# Placeholder for critical sound
# Replace with actual MP3 file
EOF

print_status "Sound files created (placeholders)"

# Create emergency notification icons
print_header "Creating Emergency Notification Icons"

# Create simple SVG icons
cat > static/icons/emergency-192.png << 'EOF'
# Placeholder for emergency icon
# Replace with actual PNG file (192x192)
EOF

cat > static/icons/emergency-badge-72.png << 'EOF'
# Placeholder for emergency badge
# Replace with actual PNG file (72x72)
EOF

cat > static/icons/ack-icon.png << 'EOF'
# Placeholder for acknowledge icon
# Replace with actual PNG file
EOF

cat > static/icons/view-icon.png << 'EOF'
# Placeholder for view icon
# Replace with actual PNG file
EOF

cat > static/icons/dismiss-icon.png << 'EOF'
# Placeholder for dismiss icon
# Replace with actual PNG file
EOF

print_status "Icon files created (placeholders)"

# Create emergency notification images
print_header "Creating Emergency Notification Images"

cat > static/images/emergency-boat-alert.png << 'EOF'
# Placeholder for emergency boat alert image
# Replace with actual PNG file
EOF

print_status "Image files created (placeholders)"

# Create systemd service for WiFi emergency monitoring
print_header "Creating System Service"

sudo tee /etc/systemd/system/wifi-emergency-boat-notifications.service > /dev/null << EOF
[Unit]
Description=WiFi Emergency Boat Notification Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=/usr/bin:/usr/local/bin
EnvironmentFile=$(pwd)/.env.wifi-emergency
ExecStart=/usr/bin/python3 $(pwd)/app/wifi_emergency_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

print_status "System service created"

# Create WiFi emergency notification test script
print_header "Creating Test Scripts"

cat > test_wifi_emergency_notifications.py << 'EOF'
#!/usr/bin/env python3
"""
Test script for WiFi emergency boat notifications
"""

import sys
import os
import time
import json
from datetime import datetime, timezone, timedelta

# Add app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from wifi_emergency_service import WiFiEmergencyNotificationService

def test_wifi_emergency_system():
    """Test the WiFi emergency notification system"""
    print("Testing WiFi Emergency Boat Notification System...")
    
    try:
        # Initialize WiFi emergency service
        config = {
            'closing_time': '18:00',
            'check_interval': 60,
            'vapid_private_key': 'test_private_key',
            'vapid_public_key': 'test_public_key'
        }
        
        wifi_emergency_service = WiFiEmergencyNotificationService(config)
        
        # Print status
        status = wifi_emergency_service.get_status()
        print("\nWiFi Emergency System Status:")
        print(json.dumps(status, indent=2))
        
        # Test different urgency levels
        for urgency in [1, 2, 3]:
            print(f"\nTesting urgency level {urgency}...")
            wifi_emergency_service.test_wifi_emergency_notification(urgency=urgency)
            time.sleep(2)
        
        print("\nWiFi emergency notification tests completed successfully!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_wifi_emergency_system()
    sys.exit(0 if success else 1)
EOF

chmod +x test_wifi_emergency_notifications.py

print_status "Test script created"

# Create WiFi emergency notification management script
cat > manage_wifi_emergency_notifications.sh << 'EOF'
#!/bin/bash
# WiFi Emergency Notification Management Script

case "$1" in
    start)
        echo "Starting WiFi emergency notification service..."
        sudo systemctl start wifi-emergency-boat-notifications
        sudo systemctl enable wifi-emergency-boat-notifications
        echo "Service started and enabled"
        ;;
    stop)
        echo "Stopping WiFi emergency notification service..."
        sudo systemctl stop wifi-emergency-boat-notifications
        echo "Service stopped"
        ;;
    restart)
        echo "Restarting WiFi emergency notification service..."
        sudo systemctl restart wifi-emergency-boat-notifications
        echo "Service restarted"
        ;;
    status)
        echo "WiFi emergency notification service status:"
        sudo systemctl status wifi-emergency-boat-notifications
        ;;
    logs)
        echo "WiFi emergency notification service logs:"
        sudo journalctl -u wifi-emergency-boat-notifications -f
        ;;
    test)
        echo "Running WiFi emergency notification tests..."
        python3 test_wifi_emergency_notifications.py
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the WiFi emergency notification service"
        echo "  stop    - Stop the WiFi emergency notification service"
        echo "  restart - Restart the WiFi emergency notification service"
        echo "  status  - Show service status"
        echo "  logs    - Show service logs"
        echo "  test    - Run WiFi emergency notification tests"
        exit 1
        ;;
esac
EOF

chmod +x manage_wifi_emergency_notifications.sh

print_status "Management script created"

# Create WiFi emergency notification configuration script
cat > configure_wifi_emergency_notifications.py << 'EOF'
#!/usr/bin/env python3
"""
Configure WiFi emergency notification settings
"""

import json
import os
from datetime import datetime

def configure_wifi_emergency_settings():
    """Interactive configuration of WiFi emergency notification settings"""
    print("WiFi Emergency Boat Notification Configuration")
    print("=" * 50)
    
    config = {}
    
    # Closing time
    closing_time = input("Enter closing time (HH:MM) [18:00]: ").strip()
    config['closing_time'] = closing_time if closing_time else '18:00'
    
    # Check interval
    check_interval = input("Enter check interval in seconds [60]: ").strip()
    config['check_interval'] = int(check_interval) if check_interval.isdigit() else 60
    
    # Escalation
    escalation = input("Enable escalation? (y/n) [y]: ").strip().lower()
    config['escalation_enabled'] = escalation != 'n'
    
    # WiFi network settings
    print("\nWiFi Network Settings:")
    wifi_ssid = input("WiFi Network SSID [Red Shed WiFi]: ").strip()
    config['wifi_ssid'] = wifi_ssid if wifi_ssid else 'Red Shed WiFi'
    
    wifi_range = input("Network range [192.168.1.0/24]: ").strip()
    config['wifi_range'] = wifi_range if wifi_range else '192.168.1.0/24'
    
    # Dashboard URL
    dashboard_url = input("Dashboard URL [http://localhost:5000]: ").strip()
    config['dashboard_url'] = dashboard_url if dashboard_url else 'http://localhost:5000'
    
    # Save configuration
    config_file = 'wifi_emergency_config.json'
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nConfiguration saved to {config_file}")
    print("\nConfiguration Summary:")
    print(json.dumps(config, indent=2))

if __name__ == "__main__":
    configure_wifi_emergency_settings()
EOF

chmod +x configure_wifi_emergency_notifications.py

print_status "Configuration script created"

# Create WiFi emergency notification documentation
print_header "Creating Documentation"

cat > WiFi_EMERGENCY_NOTIFICATIONS_GUIDE.md << 'EOF'
# WiFi Emergency Boat Notification System

## Overview

The WiFi Emergency Boat Notification System provides **critical alerts** for boats left outside after hours. It focuses on **WiFi-based notifications** to notify everyone connected to the same WiFi network when boats are outside after closing time.

## Key Features

- **WiFi-Based Notifications**: Targets all devices connected to the same WiFi network
- **Web Push with Vibration**: Browser notifications with vibration patterns
- **Real-Time Monitoring**: Continuous monitoring for boats outside after hours
- **Escalation System**: Automatic escalation with increasing urgency over time
- **Network Discovery**: Automatically discovers devices on the WiFi network

## How It Works

### 1. **WiFi Network Detection**
The system automatically detects the current WiFi network and scans for connected devices.

### 2. **Device Subscription**
When users visit the dashboard and allow notifications, their devices are subscribed to receive emergency alerts.

### 3. **Continuous Monitoring**
The system monitors boat status and checks if any boats are outside after the configured closing time.

### 4. **Emergency Notifications**
When boats are detected outside after hours:
- **Web Push**: Browser notifications with vibration to all subscribed devices
- **Network Broadcast**: Attempts to notify other devices on the WiFi network
- **Escalation**: Automatically escalates based on how long boats have been outside

## Setup and Installation

### 1. **Run Setup Script**
```bash
./setup_wifi_emergency_notifications.sh
```

### 2. **Configure Settings**
```bash
./configure_wifi_emergency_notifications.py
```

### 3. **Start Service**
```bash
./manage_wifi_emergency_notifications.sh start
```

### 4. **Test System**
```bash
./manage_wifi_emergency_notifications.sh test
```

## Configuration

### Environment Variables
```bash
# VAPID Keys for Web Push
VAPID_PRIVATE_KEY="your_private_key"
VAPID_PUBLIC_KEY="your_public_key"

# WiFi Emergency Settings
WIFI_EMERGENCY_CLOSING_TIME="18:00"
WIFI_EMERGENCY_CHECK_INTERVAL=60
WIFI_EMERGENCY_ESCALATION_ENABLED=true

# WiFi Network Settings
WIFI_NETWORK_SSID="Red Shed WiFi"
WIFI_NETWORK_RANGE="192.168.1.0/24"
```

## Usage

### For Users (WiFi-Connected Devices)

1. **Connect to WiFi**: Ensure your device is connected to the club's WiFi network
2. **Visit Dashboard**: Open the boat tracking dashboard in your browser
3. **Allow Notifications**: Click "Allow" when prompted for notification permission
4. **Receive Alerts**: Get notifications with vibration when boats are outside after hours
5. **Acknowledge**: Click "Acknowledge" to confirm receipt of the alert

### For Administrators

1. **Monitor Status**:
   ```bash
   ./manage_wifi_emergency_notifications.sh status
   ```

2. **View Logs**:
   ```bash
   ./manage_wifi_emergency_notifications.sh logs
   ```

3. **Test Notifications**:
   ```bash
   ./manage_wifi_emergency_notifications.sh test
   ```

## Urgency Levels

- **Level 1**: Normal alert (boats outside < 1 hour)
- **Level 2**: Urgent (boats outside 1-2 hours)
- **Level 3**: Emergency (boats outside 2-3 hours)
- **Level 4**: Critical (boats outside > 3 hours)

## Vibration Patterns

- **Normal**: [200, 100, 200] - Short, gentle
- **Urgent**: [300, 100, 300, 100, 300] - Medium with pauses
- **Emergency**: [500, 200, 500, 200, 500, 200, 500] - Long, strong
- **Critical**: [1000, 500, 1000, 500, 1000] - Very long, intense

## API Endpoints

- `GET /api/wifi-emergency/vapid-public-key` - Get VAPID public key
- `POST /api/wifi-emergency/subscribe` - Subscribe WiFi device
- `POST /api/wifi-emergency/unsubscribe` - Unsubscribe WiFi device
- `POST /api/wifi-emergency/test` - Send test notification
- `POST /api/wifi-emergency/acknowledge` - Acknowledge notification
- `GET /api/wifi-emergency/status` - Get WiFi emergency status

## Integration

The WiFi emergency notification system integrates with:

- Main boat tracking system
- Database for boat status
- Web dashboard for user interface
- Service worker for background notifications
- WiFi network discovery

## Troubleshooting

### Common Issues

1. **Notifications not working**: Check browser permissions and WiFi connection
2. **Vibration not working**: Ensure device supports vibration API
3. **Devices not discovered**: Check WiFi network range configuration

### Debugging

1. **Check Service Logs**:
   ```bash
   ./manage_wifi_emergency_notifications.sh logs
   ```

2. **Test Individual Components**:
   ```bash
   python3 test_wifi_emergency_notifications.py
   ```

3. **Verify Configuration**:
   ```bash
   ./configure_wifi_emergency_notifications.py
   ```

## File Structure

```
app/
├── wifi_emergency_service.py           # Core WiFi emergency service
├── wifi_emergency_api.py               # API endpoints
└── ...

static/
├── sw-wifi-emergency.js                # Service worker for WiFi push
├── js/wifi-emergency-notifications.js  # Client-side JavaScript
├── sounds/                             # Emergency notification sounds
├── icons/                              # Notification icons
└── images/                             # Notification images

setup_wifi_emergency_notifications.sh   # Setup script
configure_wifi_emergency_notifications.py # Configuration script
manage_wifi_emergency_notifications.sh  # Management script
test_wifi_emergency_notifications.py    # Test script
WiFi_EMERGENCY_NOTIFICATIONS_GUIDE.md  # This documentation
```

## Support and Maintenance

### Regular Maintenance
- **Monitor Logs**: Check for failed notifications
- **Test System**: Run monthly tests to ensure functionality
- **Review Configuration**: Update WiFi network settings as needed

### Emergency Procedures
1. **Immediate Response**: Check boat shed when emergency notification received
2. **Acknowledge Alert**: Use dashboard to acknowledge receipt
3. **Investigate**: Determine why boats were left outside
4. **Follow Up**: Address any security or procedural issues

---

**Important**: This is a critical safety system focused on WiFi-based notifications. Ensure it is properly configured, tested regularly, and that all devices on the WiFi network can receive notifications when needed.
EOF

print_status "Documentation created"

# Final setup steps
print_header "Final Setup Steps"

# Reload systemd
sudo systemctl daemon-reload

# Set permissions
chmod 644 .env.wifi-emergency
chmod 755 test_wifi_emergency_notifications.py
chmod 755 configure_wifi_emergency_notifications.py
chmod 755 manage_wifi_emergency_notifications.sh

print_status "Permissions set"

# Test the setup
print_header "Testing Setup"

if python3 -c "import pywebpush, cryptography" 2>/dev/null; then
    print_status "All dependencies installed successfully"
else
    print_error "Some dependencies are missing"
    exit 1
fi

# Create summary
print_header "Setup Complete"

echo "WiFi Emergency Boat Notification System Setup Complete!"
echo ""
echo "Next Steps:"
echo "1. Configure settings: ./configure_wifi_emergency_notifications.py"
echo "2. Start service: ./manage_wifi_emergency_notifications.sh start"
echo "3. Test system: ./manage_wifi_emergency_notifications.sh test"
echo "4. View logs: ./manage_wifi_emergency_notifications.sh logs"
echo ""
echo "Files Created:"
echo "- .env.wifi-emergency (environment configuration)"
echo "- test_wifi_emergency_notifications.py (test script)"
echo "- configure_wifi_emergency_notifications.py (configuration script)"
echo "- manage_wifi_emergency_notifications.sh (management script)"
echo "- WiFi_EMERGENCY_NOTIFICATIONS_GUIDE.md (documentation)"
echo ""
echo "Service: wifi-emergency-boat-notifications.service"
echo "Status: Ready to configure and start"

print_status "WiFi emergency notification system setup completed successfully!"
