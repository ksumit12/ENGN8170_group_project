#!/usr/bin/env python3
"""
Emergency Boat Notification Service
Critical alerts for boats left outside after hours
"""

import json
import smtplib
import requests
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BoatAlert:
    boat_name: str
    beacon_id: str
    last_seen: datetime
    location: str
    urgency_level: int  # 1-5 (5 = most urgent)

@dataclass
class EmergencyContact:
    name: str
    phone: str
    email: str
    role: str  # "admin", "manager", "member"
    notification_preferences: Dict[str, bool]
    wifi_network: Optional[str] = None

class EmergencyNotificationService:
    """High-priority emergency notification system for boats outside after hours"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.contacts = []
        self.web_push_subscriptions = []
        self.escalation_levels = [
            {"delay_minutes": 0, "channels": ["web_push", "sms", "email"]},
            {"delay_minutes": 15, "channels": ["sms", "email", "phone_call"]},
            {"delay_minutes": 30, "channels": ["sms", "email", "phone_call", "network_broadcast"]},
            {"delay_minutes": 60, "channels": ["sms", "email", "phone_call", "network_broadcast", "external_alert"]}
        ]
        
        # Initialize notification channels
        self.sms_client = None
        self.email_server = None
        self.init_notification_channels()
    
    def init_notification_channels(self):
        """Initialize all notification channels"""
        try:
            # SMS (Twilio)
            if self.config.get('twilio_sid') and self.config.get('twilio_token'):
                from twilio.rest import Client
                self.sms_client = Client(
                    self.config['twilio_sid'], 
                    self.config['twilio_token']
                )
                logger.info("SMS notifications enabled")
            
            # Email
            if self.config.get('smtp_server'):
                self.email_server = smtplib.SMTP(
                    self.config['smtp_server'], 
                    self.config.get('smtp_port', 587)
                )
                self.email_server.starttls()
                self.email_server.login(
                    self.config['smtp_username'], 
                    self.config['smtp_password']
                )
                logger.info("Email notifications enabled")
                
        except Exception as e:
            logger.error(f"Failed to initialize notification channels: {e}")
    
    def add_emergency_contact(self, contact: EmergencyContact):
        """Add emergency contact for notifications"""
        self.contacts.append(contact)
        logger.info(f"Added emergency contact: {contact.name}")
    
    def add_web_push_subscription(self, subscription_data: Dict):
        """Add web push subscription"""
        self.web_push_subscriptions.append(subscription_data)
        logger.info("Added web push subscription")
    
    def send_emergency_boat_alert(self, boats_outside: List[BoatAlert], 
                                 closing_time: str, escalation_level: int = 0):
        """Send emergency alert about boats outside after hours"""
        
        if not boats_outside:
            return
        
        # Create emergency message
        boat_list = ", ".join([boat.boat_name for boat in boats_outside])
        urgency_emoji = "🚨" if escalation_level >= 2 else "⚠️"
        
        message = {
            "title": f"{urgency_emoji} EMERGENCY: Boats Outside After Hours",
            "body": f"{len(boats_outside)} boat(s) still outside after {closing_time}: {boat_list}",
            "urgency": escalation_level + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "boats": [
                {
                    "name": boat.boat_name,
                    "beacon_id": boat.beacon_id,
                    "last_seen": boat.last_seen.isoformat(),
                    "location": boat.location
                } for boat in boats_outside
            ],
            "vibration_pattern": self.get_vibration_pattern(escalation_level),
            "sound": "emergency" if escalation_level >= 2 else "alert"
        }
        
        # Send via all configured channels
        channels = self.escalation_levels[escalation_level]["channels"]
        
        for channel in channels:
            try:
                if channel == "web_push":
                    self.send_web_push_emergency(message)
                elif channel == "sms":
                    self.send_sms_emergency(message)
                elif channel == "email":
                    self.send_email_emergency(message)
                elif channel == "phone_call":
                    self.send_phone_call_emergency(message)
                elif channel == "network_broadcast":
                    self.send_network_broadcast(message)
                elif channel == "external_alert":
                    self.send_external_alert(message)
                    
            except Exception as e:
                logger.error(f"Failed to send {channel} notification: {e}")
    
    def get_vibration_pattern(self, escalation_level: int) -> List[int]:
        """Get vibration pattern based on escalation level"""
        patterns = {
            0: [200, 100, 200],                    # Normal alert
            1: [300, 100, 300, 100, 300],         # Urgent
            2: [500, 200, 500, 200, 500, 200, 500], # Emergency
            3: [1000, 500, 1000, 500, 1000]       # Critical
        }
        return patterns.get(escalation_level, [200, 100, 200])
    
    def send_web_push_emergency(self, message: Dict):
        """Send high-priority web push notification"""
        import pywebpush
        
        for subscription in self.web_push_subscriptions:
            try:
                # Enhanced notification options for emergency
                notification_data = {
                    **message,
                    "requireInteraction": True,
                    "silent": False,
                    "tag": "boat-emergency",
                    "renotify": True,
                    "actions": [
                        {
                            "action": "acknowledge",
                            "title": "Acknowledge",
                            "icon": "/ack-icon.png"
                        },
                        {
                            "action": "view",
                            "title": "View Dashboard",
                            "icon": "/view-icon.png"
                        }
                    ]
                }
                
                pywebpush.webpush(
                    subscription_info=subscription,
                    data=json.dumps(notification_data),
                    vapid_private_key=self.config['vapid_private_key'],
                    vapid_public_key=self.config['vapid_public_key'],
                    vapid_claims={"sub": "mailto:emergency@rowingclub.com"}
                )
                
                logger.info("Emergency web push notification sent")
                
            except Exception as e:
                logger.error(f"Web push emergency notification failed: {e}")
    
    def send_sms_emergency(self, message: Dict):
        """Send SMS emergency notification"""
        if not self.sms_client:
            logger.warning("SMS client not configured")
            return
        
        sms_body = f"🚨 EMERGENCY ALERT 🚨\n\n{message['body']}\n\nTime: {message['timestamp']}\n\nReply STOP to unsubscribe"
        
        for contact in self.contacts:
            if contact.notification_preferences.get('sms', True) and contact.phone:
                try:
                    self.sms_client.messages.create(
                        body=sms_body,
                        from_=self.config['twilio_phone'],
                        to=contact.phone
                    )
                    logger.info(f"Emergency SMS sent to {contact.name}")
                except Exception as e:
                    logger.error(f"SMS to {contact.name} failed: {e}")
    
    def send_email_emergency(self, message: Dict):
        """Send email emergency notification"""
        if not self.email_server:
            logger.warning("Email server not configured")
            return
        
        # Create HTML email
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #ff4444; color: white; padding: 20px; text-align: center;">
                <h1>🚨 EMERGENCY ALERT 🚨</h1>
            </div>
            <div style="padding: 20px;">
                <h2>Boats Outside After Hours</h2>
                <p><strong>Alert Time:</strong> {message['timestamp']}</p>
                <p><strong>Boats Outside:</strong> {message['body']}</p>
                
                <h3>Boat Details:</h3>
                <ul>
                    {"".join([f"<li><strong>{boat['name']}</strong> - Last seen: {boat['last_seen']} at {boat['location']}</li>" for boat in message['boats']])}
                </ul>
                
                <div style="background-color: #fff3cd; padding: 15px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <p><strong>Action Required:</strong> Please check the shed and ensure boats are properly secured.</p>
                </div>
                
                <p><a href="{self.config.get('dashboard_url', 'http://localhost:5000')}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">View Dashboard</a></p>
            </div>
        </body>
        </html>
        """
        
        for contact in self.contacts:
            if contact.notification_preferences.get('email', True) and contact.email:
                try:
                    msg = MimeMultipart('alternative')
                    msg['Subject'] = f"🚨 EMERGENCY: {len(message['boats'])} Boats Outside After Hours"
                    msg['From'] = self.config['smtp_username']
                    msg['To'] = contact.email
                    
                    msg.attach(MimeText(html_body, 'html'))
                    
                    self.email_server.send_message(msg)
                    logger.info(f"Emergency email sent to {contact.name}")
                    
                except Exception as e:
                    logger.error(f"Email to {contact.name} failed: {e}")
    
    def send_phone_call_emergency(self, message: Dict):
        """Send automated phone call (if Twilio is configured)"""
        if not self.sms_client:
            return
        
        # Create TwiML for phone call
        twiml = f"""
        <Response>
            <Say voice="alice">Emergency alert. {len(message['boats'])} boats are still outside after hours. 
            Please check the boat shed immediately. This is an automated emergency notification.</Say>
            <Pause length="2"/>
            <Say voice="alice">Repeat. {len(message['boats'])} boats are still outside after hours. 
            Please check the boat shed immediately.</Say>
        </Response>
        """
        
        for contact in self.contacts:
            if contact.notification_preferences.get('phone_call', False) and contact.phone:
                try:
                    self.sms_client.calls.create(
                        twiml=twiml,
                        to=contact.phone,
                        from_=self.config['twilio_phone']
                    )
                    logger.info(f"Emergency phone call initiated to {contact.name}")
                except Exception as e:
                    logger.error(f"Phone call to {contact.name} failed: {e}")
    
    def send_network_broadcast(self, message: Dict):
        """Broadcast emergency alert on local network"""
        try:
            # Try to discover and notify devices on the network
            network_devices = self.discover_network_devices()
            
            for device_ip in network_devices:
                self.try_notify_device(device_ip, message)
                
        except Exception as e:
            logger.error(f"Network broadcast failed: {e}")
    
    def discover_network_devices(self) -> List[str]:
        """Discover devices on the local network"""
        import subprocess
        import ipaddress
        
        devices = []
        try:
            # Get local network range
            result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                  capture_output=True, text=True)
            
            # Parse network range (simplified)
            network_range = "192.168.1.0/24"  # Default assumption
            
            # Scan common IPs
            for i in range(1, 255):
                ip = f"192.168.1.{i}"
                if self.ping_device(ip):
                    devices.append(ip)
                    
        except Exception as e:
            logger.error(f"Network discovery failed: {e}")
        
        return devices
    
    def ping_device(self, ip: str) -> bool:
        """Ping a device to check if it's reachable"""
        import subprocess
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', '1', ip], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    def try_notify_device(self, device_ip: str, message: Dict):
        """Try to send notification to a specific device"""
        # Try common notification endpoints
        endpoints = [
            f"http://{device_ip}:8080/api/emergency-notify",
            f"http://{device_ip}:3000/emergency-notify",
            f"http://{device_ip}:5000/api/emergency-notify"
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.post(
                    endpoint, 
                    json=message, 
                    timeout=2,
                    headers={'Content-Type': 'application/json'}
                )
                if response.status_code == 200:
                    logger.info(f"Emergency notification sent to {device_ip}")
                    return True
            except:
                continue
        
        return False
    
    def send_external_alert(self, message: Dict):
        """Send alert to external systems (slack, discord, etc.)"""
        # Implement external integrations
        pass
    
    def start_emergency_monitoring(self, db_manager):
        """Start monitoring for boats outside after hours"""
        import threading
        
        def monitor_loop():
            while True:
                try:
                    self.check_boats_outside_after_hours(db_manager)
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Emergency monitoring error: {e}")
                    time.sleep(60)
        
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        logger.info("Emergency monitoring started")
    
    def check_boats_outside_after_hours(self, db_manager):
        """Check for boats outside after closing time"""
        closing_time = self.get_closing_time()
        current_time = datetime.now(timezone.utc).time()
        
        if current_time > closing_time:
            boats_outside = self.get_boats_outside(db_manager)
            
            if boats_outside:
                # Determine escalation level based on how long boats have been outside
                escalation_level = self.calculate_escalation_level(boats_outside, closing_time)
                
                self.send_emergency_boat_alert(
                    boats_outside=boats_outside,
                    closing_time=closing_time.strftime("%H:%M"),
                    escalation_level=escalation_level
                )
    
    def get_closing_time(self) -> datetime.time:
        """Get configured closing time"""
        # This should come from your configuration
        return datetime.strptime("18:00", "%H:%M").time()
    
    def get_boats_outside(self, db_manager) -> List[BoatAlert]:
        """Get list of boats currently outside"""
        # This should query your database for boats with status OUT
        boats = []
        # Implementation depends on your database structure
        return boats
    
    def calculate_escalation_level(self, boats: List[BoatAlert], closing_time: datetime.time) -> int:
        """Calculate escalation level based on how long boats have been outside"""
        current_time = datetime.now(timezone.utc).time()
        hours_outside = (datetime.combine(datetime.today(), current_time) - 
                        datetime.combine(datetime.today(), closing_time)).seconds / 3600
        
        if hours_outside >= 3:
            return 3  # Critical
        elif hours_outside >= 2:
            return 2  # Emergency
        elif hours_outside >= 1:
            return 1  # Urgent
        else:
            return 0  # Normal alert


# Example usage
if __name__ == "__main__":
    config = {
        'twilio_sid': 'your_twilio_sid',
        'twilio_token': 'your_twilio_token',
        'twilio_phone': '+1234567890',
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'smtp_username': 'your_email@gmail.com',
        'smtp_password': 'your_app_password',
        'vapid_private_key': 'your_vapid_private_key',
        'vapid_public_key': 'your_vapid_public_key',
        'dashboard_url': 'https://your-dashboard.com'
    }
    
    # Initialize emergency notification service
    emergency_service = EmergencyNotificationService(config)
    
    # Add emergency contacts
    emergency_service.add_emergency_contact(EmergencyContact(
        name="Club Manager",
        phone="+1234567890",
        email="manager@rowingclub.com",
        role="admin",
        notification_preferences={
            "sms": True,
            "email": True,
            "phone_call": True
        }
    ))
    
    print("Emergency Boat Notification Service initialized")
