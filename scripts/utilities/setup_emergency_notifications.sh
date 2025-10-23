#!/bin/bash
# Emergency Notification System Setup Script
# Sets up emergency boat notifications with vibration and multi-channel alerts

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
pip3 install --user twilio==8.10.0
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
print_header "Creating Environment Configuration"

cat > .env.emergency << EOF
# Emergency Notification System Configuration

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

# Notification Channels
WEB_PUSH_ENABLED=true
SMS_ENABLED=false
EMAIL_ENABLED=false
PHONE_CALL_ENABLED=false

# SMS Configuration (Twilio) - Optional
TWILIO_SID=
TWILIO_TOKEN=
TWILIO_PHONE=

# Email Configuration - Optional
SMTP_SERVER=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=

# Dashboard URL
DASHBOARD_URL=http://localhost:5000

# Emergency Contacts (JSON format)
EMERGENCY_CONTACTS='[
    {
        "name": "Club Manager",
        "phone": "+1234567890",
        "email": "manager@rowingclub.com",
        "role": "admin",
        "notification_preferences": {
            "sms": true,
            "email": true,
            "phone_call": true
        }
    },
    {
        "name": "Safety Officer",
        "phone": "+1234567891",
        "email": "safety@rowingclub.com",
        "role": "admin",
        "notification_preferences": {
            "sms": true,
            "email": true,
            "phone_call": false
        }
    }
]'
EOF

print_status "Environment configuration created"

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
ExecStart=/usr/bin/python3 $(pwd)/app/emergency_integration.py
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

from emergency_integration import EmergencyNotificationIntegration

def test_emergency_system():
    """Test the emergency notification system"""
    print("Testing Emergency Boat Notification System...")
    
    try:
        # Initialize integration
        integration = EmergencyNotificationIntegration()
        
        # Print status
        status = integration.get_status()
        print("\nSystem Status:")
        print(json.dumps(status, indent=2))
        
        # Test different urgency levels
        for urgency in [1, 2, 3]:
            print(f"\nTesting urgency level {urgency}...")
            integration.test_emergency_notification(urgency=urgency)
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
    
    # Notification channels
    print("\nNotification Channels:")
    web_push = input("Enable web push notifications? (y/n) [y]: ").strip().lower()
    config['web_push_enabled'] = web_push != 'n'
    
    sms = input("Enable SMS notifications? (y/n) [n]: ").strip().lower()
    config['sms_enabled'] = sms == 'y'
    
    email = input("Enable email notifications? (y/n) [n]: ").strip().lower()
    config['email_enabled'] = email == 'y'
    
    phone_call = input("Enable phone call notifications? (y/n) [n]: ").strip().lower()
    config['phone_call_enabled'] = phone_call == 'y'
    
    # SMS configuration
    if config['sms_enabled']:
        print("\nSMS Configuration:")
        config['twilio_sid'] = input("Twilio SID: ").strip()
        config['twilio_token'] = input("Twilio Token: ").strip()
        config['twilio_phone'] = input("Twilio Phone Number: ").strip()
    
    # Email configuration
    if config['email_enabled']:
        print("\nEmail Configuration:")
        config['smtp_server'] = input("SMTP Server: ").strip()
        config['smtp_port'] = input("SMTP Port [587]: ").strip() or '587'
        config['smtp_username'] = input("SMTP Username: ").strip()
        config['smtp_password'] = input("SMTP Password: ").strip()
    
    # Emergency contacts
    print("\nEmergency Contacts:")
    contacts = []
    
    while True:
        name = input("Contact name (or 'done' to finish): ").strip()
        if name.lower() == 'done':
            break
        
        phone = input("Phone number: ").strip()
        email = input("Email address: ").strip()
        role = input("Role (admin/member) [member]: ").strip() or 'member'
        
        contact = {
            'name': name,
            'phone': phone,
            'email': email,
            'role': role,
            'notification_preferences': {
                'sms': config['sms_enabled'],
                'email': config['email_enabled'],
                'phone_call': config['phone_call_enabled']
            }
        }
        
        contacts.append(contact)
    
    config['emergency_contacts'] = contacts
    
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

# Create emergency notification documentation
print_header "Creating Documentation"

cat > EMERGENCY_NOTIFICATIONS_GUIDE.md << 'EOF'
# Emergency Boat Notification System

## Overview

The Emergency Boat Notification System provides critical alerts for boats left outside after hours. It uses multiple notification channels including web push notifications with vibration, SMS, email, and phone calls.

## Features

- **Multi-Channel Notifications**: Web push, SMS, email, phone calls
- **Vibration Patterns**: Different vibration patterns based on urgency level
- **Escalation System**: Automatic escalation with increasing urgency
- **WiFi-Based**: Targets devices connected to the same WiFi network
- **Real-Time Monitoring**: Continuous monitoring for boats outside after hours

## Setup

1. **Run Setup Script**:
   ```bash
   ./setup_emergency_notifications.sh
   ```

2. **Configure Settings**:
   ```bash
   ./configure_emergency_notifications.py
   ```

3. **Start Service**:
   ```bash
   ./manage_emergency_notifications.sh start
   ```

## Configuration

### Environment Variables

- `VAPID_PRIVATE_KEY`: Private key for web push notifications
- `VAPID_PUBLIC_KEY`: Public key for web push notifications
- `EMERGENCY_CLOSING_TIME`: Closing time (HH:MM format)
- `EMERGENCY_CHECK_INTERVAL`: Check interval in seconds
- `EMERGENCY_ESCALATION_ENABLED`: Enable escalation system

### Notification Channels

- **Web Push**: Browser notifications with vibration
- **SMS**: Text messages via Twilio
- **Email**: Email notifications via SMTP
- **Phone Calls**: Automated calls via Twilio

## Usage

### Web Push Notifications

1. **Subscribe**: Visit the dashboard and allow notifications
2. **Receive Alerts**: Get notifications with vibration when boats are outside
3. **Acknowledge**: Click "Acknowledge" to confirm receipt

### Emergency Contacts

Add emergency contacts who will receive notifications:

```python
from app.emergency_integration import EmergencyNotificationIntegration

integration = EmergencyNotificationIntegration()
integration.add_emergency_contact({
    'name': 'Club Manager',
    'phone': '+1234567890',
    'email': 'manager@rowingclub.com',
    'role': 'admin',
    'notification_preferences': {
        'sms': True,
        'email': True,
        'phone_call': True
    }
})
```

### Testing

Run the test script to verify the system:

```bash
./manage_emergency_notifications.sh test
```

## Urgency Levels

- **Level 1**: Normal alert (boats outside < 1 hour)
- **Level 2**: Urgent (boats outside 1-2 hours)
- **Level 3**: Emergency (boats outside 2-3 hours)
- **Level 4**: Critical (boats outside > 3 hours)

## Vibration Patterns

- **Normal**: [200, 100, 200]
- **Urgent**: [300, 100, 300, 100, 300]
- **Emergency**: [500, 200, 500, 200, 500, 200, 500]
- **Critical**: [1000, 500, 1000, 500, 1000]

## Troubleshooting

### Common Issues

1. **Notifications not working**: Check browser permissions
2. **Vibration not working**: Ensure device supports vibration API
3. **SMS not sending**: Verify Twilio credentials
4. **Email not sending**: Check SMTP settings

### Logs

View service logs:

```bash
./manage_emergency_notifications.sh logs
```

### Status

Check service status:

```bash
./manage_emergency_notifications.sh status
```

## Security Considerations

- VAPID keys are generated securely
- Database encryption is enabled
- Emergency contacts are stored securely
- Notification data is encrypted in transit

## API Endpoints

- `POST /api/notifications/subscribe`: Subscribe to notifications
- `POST /api/notifications/unsubscribe`: Unsubscribe from notifications
- `POST /api/notifications/test-emergency`: Send test notification
- `POST /api/notifications/acknowledge`: Acknowledge notification
- `GET /api/emergency/status`: Get emergency status
- `POST /api/emergency/contacts`: Add emergency contact

## Integration

The emergency notification system integrates with:

- Main boat tracking system
- Database for boat status
- Web dashboard for user interface
- Service worker for background notifications

## Support

For issues or questions:

1. Check the logs: `./manage_emergency_notifications.sh logs`
2. Run tests: `./manage_emergency_notifications.sh test`
3. Check configuration: `./configure_emergency_notifications.py`
EOF

print_status "Documentation created"

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

if python3 -c "import pywebpush, twilio, cryptography" 2>/dev/null; then
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
echo "- EMERGENCY_NOTIFICATIONS_GUIDE.md (documentation)"
echo ""
echo "Service: emergency-boat-notifications.service"
echo "Status: Ready to configure and start"

print_status "Emergency notification system setup completed successfully!"
