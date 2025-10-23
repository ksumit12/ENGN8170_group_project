#!/bin/bash
# Consolidated Emergency Boat Notification Setup Script
# Sets up WiFi-based emergency boat notifications with vibration

set -e

echo "Setting up Emergency Boat Notification System..."

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
mkdir -p logs/emergency
mkdir -p data/emergency

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
print_header "Creating Emergency Configuration"

cat > .env.emergency << EOF
# Emergency Boat Notification System Configuration

# VAPID Keys for Web Push Notifications
VAPID_PRIVATE_KEY="$vapid_private_key"
VAPID_PUBLIC_KEY="$vapid_public_key"

# Database Configuration
DB_PATH=data/boat_tracking.db
DB_ENCRYPTION_KEY=$(openssl rand -base64 32)

# Emergency Notification Settings
EMERGENCY_CLOSING_TIME=18:00
EMERGENCY_CHECK_INTERVAL=60
EMERGENCY_ESCALATION_ENABLED=true

# Dashboard URL
DASHBOARD_URL=http://localhost:5000

# WiFi Network Settings
WIFI_NETWORK_SSID=Red Shed WiFi
WIFI_NETWORK_RANGE=192.168.1.0/24
EOF

print_status "Emergency configuration created"

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

# Create systemd service for emergency monitoring
print_header "Creating System Service"

sudo tee /etc/systemd/system/emergency-boat-notifications.service > /dev/null << EOF
[Unit]
Description=Emergency Boat Notification Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=/usr/bin:/usr/local/bin
EnvironmentFile=$(pwd)/.env.emergency
ExecStart=/usr/bin/python3 $(pwd)/app/emergency_system.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

print_status "System service created"

# Create emergency notification test script
print_header "Creating Test Scripts"

cat > test_emergency_notifications.py << 'EOF'
#!/usr/bin/env python3
"""
Test script for emergency boat notifications
"""

import sys
import os
import time
import json
from datetime import datetime, timezone, timedelta

# Add app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from emergency_system import EmergencyNotificationSystem

def test_emergency_system():
    """Test the emergency notification system"""
    print("Testing Emergency Boat Notification System...")
    
    try:
        # Initialize emergency system
        config = {
            'closing_time': '18:00',
            'check_interval': 60,
            'vapid_private_key': 'test_private_key',
            'vapid_public_key': 'test_public_key'
        }
        
        emergency_system = EmergencyNotificationSystem(config)
        
        # Print status
        status = emergency_system.get_status()
        print("\nEmergency System Status:")
        print(json.dumps(status, indent=2))
        
        # Test different urgency levels
        for urgency in [1, 2, 3]:
            print(f"\nTesting urgency level {urgency}...")
            emergency_system.test_emergency_notification(urgency=urgency)
            time.sleep(2)
        
        print("\nEmergency notification tests completed successfully!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_emergency_system()
    sys.exit(0 if success else 1)
EOF

chmod +x test_emergency_notifications.py

print_status "Test script created"

# Create emergency notification management script
cat > manage_emergency_notifications.sh << 'EOF'
#!/bin/bash
# Emergency Notification Management Script

case "$1" in
    start)
        echo "Starting emergency notification service..."
        sudo systemctl start emergency-boat-notifications
        sudo systemctl enable emergency-boat-notifications
        echo "Service started and enabled"
        ;;
    stop)
        echo "Stopping emergency notification service..."
        sudo systemctl stop emergency-boat-notifications
        echo "Service stopped"
        ;;
    restart)
        echo "Restarting emergency notification service..."
        sudo systemctl restart emergency-boat-notifications
        echo "Service restarted"
        ;;
    status)
        echo "Emergency notification service status:"
        sudo systemctl status emergency-boat-notifications
        ;;
    logs)
        echo "Emergency notification service logs:"
        sudo journalctl -u emergency-boat-notifications -f
        ;;
    test)
        echo "Running emergency notification tests..."
        python3 test_emergency_notifications.py
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the emergency notification service"
        echo "  stop    - Stop the emergency notification service"
        echo "  restart - Restart the emergency notification service"
        echo "  status  - Show service status"
        echo "  logs    - Show service logs"
        echo "  test    - Run emergency notification tests"
        exit 1
        ;;
esac
EOF

chmod +x manage_emergency_notifications.sh

print_status "Management script created"

# Create emergency notification configuration script
cat > configure_emergency_notifications.py << 'EOF'
#!/usr/bin/env python3
"""
Configure emergency notification settings
"""

import json
import os
from datetime import datetime

def configure_emergency_settings():
    """Interactive configuration of emergency notification settings"""
    print("Emergency Boat Notification Configuration")
    print("=" * 40)
    
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
    config_file = 'emergency_config.json'
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nConfiguration saved to {config_file}")
    print("\nConfiguration Summary:")
    print(json.dumps(config, indent=2))

if __name__ == "__main__":
    configure_emergency_settings()
EOF

chmod +x configure_emergency_notifications.py

print_status "Configuration script created"

# Final setup steps
print_header "Final Setup Steps"

# Reload systemd
sudo systemctl daemon-reload

# Set permissions
chmod 644 .env.emergency
chmod 755 test_emergency_notifications.py
chmod 755 configure_emergency_notifications.py
chmod 755 manage_emergency_notifications.sh

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

echo "Emergency Boat Notification System Setup Complete!"
echo ""
echo "Next Steps:"
echo "1. Configure settings: ./configure_emergency_notifications.py"
echo "2. Start service: ./manage_emergency_notifications.sh start"
echo "3. Test system: ./manage_emergency_notifications.sh test"
echo "4. View logs: ./manage_emergency_notifications.sh logs"
echo ""
echo "Files Created:"
echo "- .env.emergency (environment configuration)"
echo "- test_emergency_notifications.py (test script)"
echo "- configure_emergency_notifications.py (configuration script)"
echo "- manage_emergency_notifications.sh (management script)"
echo ""
echo "Service: emergency-boat-notifications.service"
echo "Status: Ready to configure and start"

print_status "Emergency notification system setup completed successfully!"
