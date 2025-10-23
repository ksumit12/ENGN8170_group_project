# Emergency Boat Notification System

## Overview

The Emergency Boat Notification System is a **critical safety feature** that provides immediate alerts when boats are left outside after closing hours. It uses multiple notification channels including web push notifications with vibration, SMS, email, and phone calls to ensure that responsible parties are immediately notified.

## Key Features

### 🚨 **High-Priority Emergency Alerts**
- **Multi-Channel Notifications**: Web push, SMS, email, phone calls
- **Vibration Patterns**: Different vibration patterns based on urgency level
- **Escalation System**: Automatic escalation with increasing urgency over time
- **WiFi-Based Targeting**: Notifications sent to devices on the same WiFi network
- **Real-Time Monitoring**: Continuous monitoring for boats outside after hours

### 📱 **Web Push Notifications with Vibration**
- **Service Worker**: Background notification handling
- **Vibration API**: Device vibration for urgent alerts
- **Notification Actions**: Acknowledge, View Dashboard, Dismiss
- **Offline Support**: Notifications queued when offline
- **Permission Management**: User-friendly permission requests

### 🔄 **Escalation Levels**
- **Level 1**: Normal alert (boats outside < 1 hour)
- **Level 2**: Urgent (boats outside 1-2 hours) 
- **Level 3**: Emergency (boats outside 2-3 hours)
- **Level 4**: Critical (boats outside > 3 hours)

## How It Works

### 1. **Continuous Monitoring**
The system continuously monitors boat status and checks if any boats are outside after the configured closing time.

### 2. **Multi-Channel Notification**
When boats are detected outside after hours, the system sends notifications via:
- **Web Push**: Browser notifications with vibration to dashboard users
- **SMS**: Text messages to emergency contacts
- **Email**: Detailed email alerts with boat information
- **Phone Calls**: Automated voice calls for critical alerts

### 3. **Escalation System**
The system automatically escalates notifications based on how long boats have been outside:
- **Immediate**: Web push notifications to all subscribed users
- **15 minutes**: SMS and email to emergency contacts
- **30 minutes**: Phone calls added to emergency contacts
- **60 minutes**: Network broadcast and external alerts

### 4. **Vibration Patterns**
Different vibration patterns indicate urgency levels:
- **Normal**: `[200, 100, 200]` - Short, gentle pattern
- **Urgent**: `[300, 100, 300, 100, 300]` - Medium pattern with pauses
- **Emergency**: `[500, 200, 500, 200, 500, 200, 500]` - Long, strong pattern
- **Critical**: `[1000, 500, 1000, 500, 1000]` - Very long, intense pattern

## Setup and Installation

### 1. **Run Setup Script**
```bash
./setup_emergency_notifications.sh
```

This script will:
- Install required Python packages (`pywebpush`, `twilio`, `cryptography`)
- Generate VAPID keys for web push notifications
- Create necessary directories and files
- Set up systemd service
- Create test and management scripts

### 2. **Configure Settings**
```bash
./configure_emergency_notifications.py
```

Interactive configuration for:
- Closing time
- Check interval
- Notification channels (SMS, email, phone calls)
- Emergency contacts
- Escalation settings

### 3. **Start Service**
```bash
./manage_emergency_notifications.sh start
```

### 4. **Test System**
```bash
./manage_emergency_notifications.sh test
```

## Configuration

### Environment Variables
```bash
# VAPID Keys for Web Push
VAPID_PRIVATE_KEY="your_private_key"
VAPID_PUBLIC_KEY="your_public_key"

# Emergency Settings
EMERGENCY_CLOSING_TIME="18:00"
EMERGENCY_CHECK_INTERVAL=60
EMERGENCY_ESCALATION_ENABLED=true

# Notification Channels
WEB_PUSH_ENABLED=true
SMS_ENABLED=false
EMAIL_ENABLED=false
PHONE_CALL_ENABLED=false

# SMS Configuration (Twilio)
TWILIO_SID="your_twilio_sid"
TWILIO_TOKEN="your_twilio_token"
TWILIO_PHONE="+1234567890"

# Email Configuration
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT=587
SMTP_USERNAME="your_email@gmail.com"
SMTP_PASSWORD="your_app_password"
```

### System Configuration
```json
{
  "emergency_notifications": {
    "enabled": true,
    "closing_time": "18:00",
    "check_interval": 60,
    "escalation_enabled": true,
    "web_push_enabled": true,
    "sms_enabled": false,
    "email_enabled": false,
    "phone_call_enabled": false
  }
}
```

## Usage

### For Users (Web Dashboard)

1. **Visit Dashboard**: Open the boat tracking dashboard in your browser
2. **Allow Notifications**: Click "Allow" when prompted for notification permission
3. **Receive Alerts**: Get notifications with vibration when boats are outside after hours
4. **Acknowledge**: Click "Acknowledge" to confirm receipt of the alert

### For Administrators

1. **Add Emergency Contacts**:
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

2. **Test Notifications**:
   ```bash
   ./manage_emergency_notifications.sh test
   ```

3. **Monitor Status**:
   ```bash
   ./manage_emergency_notifications.sh status
   ```

4. **View Logs**:
   ```bash
   ./manage_emergency_notifications.sh logs
   ```

## API Endpoints

### Web Push Notifications
- `GET /api/notifications/vapid-public-key` - Get VAPID public key
- `POST /api/notifications/subscribe` - Subscribe to notifications
- `POST /api/notifications/unsubscribe` - Unsubscribe from notifications
- `POST /api/notifications/test-emergency` - Send test notification
- `POST /api/notifications/acknowledge` - Acknowledge notification

### Emergency Management
- `GET /api/emergency/status` - Get emergency status
- `POST /api/emergency/contacts` - Add emergency contact
- `GET /api/emergency/contacts` - Get emergency contacts

## Integration with Main System

The emergency notification system integrates seamlessly with the main boat tracking system:

1. **Automatic Detection**: Monitors boat status from the main database
2. **Real-Time Alerts**: Sends notifications immediately when boats are detected outside
3. **Dashboard Integration**: Emergency notification controls available in the web dashboard
4. **Service Integration**: Runs as part of the main system service

## Security Considerations

- **VAPID Keys**: Securely generated for web push authentication
- **Database Encryption**: Emergency contact data encrypted at rest
- **HTTPS Support**: Notifications sent over encrypted connections
- **Permission-Based**: Users must explicitly grant notification permission
- **Audit Logging**: All emergency notifications logged for security

## Troubleshooting

### Common Issues

1. **Notifications Not Working**
   - Check browser notification permissions
   - Verify VAPID keys are configured
   - Check service status: `./manage_emergency_notifications.sh status`

2. **Vibration Not Working**
   - Ensure device supports vibration API
   - Check browser compatibility
   - Test vibration: `./manage_emergency_notifications.sh test`

3. **SMS Not Sending**
   - Verify Twilio credentials
   - Check phone number format
   - Ensure SMS is enabled in configuration

4. **Email Not Sending**
   - Verify SMTP settings
   - Check email credentials
   - Ensure email is enabled in configuration

### Debugging

1. **Check Service Logs**:
   ```bash
   ./manage_emergency_notifications.sh logs
   ```

2. **Test Individual Components**:
   ```bash
   python3 test_emergency_notifications.py
   ```

3. **Verify Configuration**:
   ```bash
   ./configure_emergency_notifications.py
   ```

## File Structure

```
app/
├── emergency_notification_service.py    # Core emergency notification service
├── emergency_integration.py             # Integration with main system
├── emergency_api.py                     # API endpoints
└── ...

static/
├── sw-emergency.js                      # Service worker for web push
├── js/emergency-notifications.js        # Client-side JavaScript
├── sounds/                              # Emergency notification sounds
├── icons/                               # Notification icons
└── images/                              # Notification images

setup_emergency_notifications.sh         # Setup script
configure_emergency_notifications.py     # Configuration script
manage_emergency_notifications.sh        # Management script
test_emergency_notifications.py          # Test script
EMERGENCY_NOTIFICATIONS_GUIDE.md        # This documentation
```

## Support and Maintenance

### Regular Maintenance
- **Monitor Logs**: Check for failed notifications
- **Update Contacts**: Keep emergency contacts current
- **Test System**: Run monthly tests to ensure functionality
- **Review Configuration**: Update settings as needed

### Emergency Procedures
1. **Immediate Response**: Check boat shed when emergency notification received
2. **Acknowledge Alert**: Use dashboard to acknowledge receipt
3. **Investigate**: Determine why boats were left outside
4. **Follow Up**: Address any security or procedural issues

## Future Enhancements

- **Weather Integration**: Consider weather conditions in escalation
- **GPS Tracking**: Add location-based notifications
- **Mobile App**: Dedicated mobile app for better reliability
- **Integration**: Connect with club management systems
- **Analytics**: Track notification effectiveness and response times

---

**Important**: This is a critical safety system. Ensure it is properly configured, tested regularly, and that emergency contacts are kept up to date. The system should be monitored continuously to ensure it functions correctly when needed.
