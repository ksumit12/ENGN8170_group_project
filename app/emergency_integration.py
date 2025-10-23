#!/usr/bin/env python3
"""
Emergency Notification Integration
Integrates emergency notifications with the main boat tracking system
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import json

# Add app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from emergency_notification_service import EmergencyNotificationService, EmergencyContact, BoatAlert
from database_models import Boat, Beacon, Passage
from secure_database import SecureDatabase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmergencyNotificationIntegration:
    """Integrates emergency notifications with boat tracking system"""
    
    def __init__(self, config_file: str = None):
        self.config = self.load_config(config_file)
        self.emergency_service = None
        self.db_manager = None
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Initialize components
        self.init_database()
        self.init_emergency_service()
        
    def load_config(self, config_file: str = None) -> Dict:
        """Load configuration from file or environment"""
        config = {
            # Emergency notification settings
            'closing_time': '18:00',
            'emergency_check_interval': 60,  # seconds
            'escalation_enabled': True,
            
            # Notification channels
            'web_push_enabled': True,
            'sms_enabled': False,
            'email_enabled': False,
            'phone_call_enabled': False,
            
            # Database settings
            'db_path': os.getenv('DB_PATH', 'data/boat_tracking.db'),
            'db_encryption_key': os.getenv('DB_ENCRYPTION_KEY'),
            
            # VAPID keys for web push
            'vapid_private_key': os.getenv('VAPID_PRIVATE_KEY'),
            'vapid_public_key': os.getenv('VAPID_PUBLIC_KEY'),
            
            # SMS settings (Twilio)
            'twilio_sid': os.getenv('TWILIO_SID'),
            'twilio_token': os.getenv('TWILIO_TOKEN'),
            'twilio_phone': os.getenv('TWILIO_PHONE'),
            
            # Email settings
            'smtp_server': os.getenv('SMTP_SERVER'),
            'smtp_port': int(os.getenv('SMTP_PORT', '587')),
            'smtp_username': os.getenv('SMTP_USERNAME'),
            'smtp_password': os.getenv('SMTP_PASSWORD'),
            
            # Dashboard URL
            'dashboard_url': os.getenv('DASHBOARD_URL', 'http://localhost:5000')
        }
        
        # Load from config file if provided
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    file_config = json.load(f)
                    config.update(file_config)
            except Exception as e:
                logger.error(f"Failed to load config file {config_file}: {e}")
        
        return config
    
    def init_database(self):
        """Initialize database connection"""
        try:
            self.db_manager = SecureDatabase(
                db_path=self.config['db_path'],
                encryption_key=self.config['db_encryption_key'],
                enable_backups=True
            )
            logger.info("Database connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def init_emergency_service(self):
        """Initialize emergency notification service"""
        try:
            self.emergency_service = EmergencyNotificationService(self.config)
            
            # Add default emergency contacts if configured
            self.load_emergency_contacts()
            
            logger.info("Emergency notification service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize emergency service: {e}")
            raise
    
    def load_emergency_contacts(self):
        """Load emergency contacts from database or config"""
        try:
            # Try to load from database first
            contacts = self.get_emergency_contacts_from_db()
            
            if not contacts:
                # Load from config file
                contacts = self.get_emergency_contacts_from_config()
            
            # Add contacts to emergency service
            for contact_data in contacts:
                contact = EmergencyContact(
                    name=contact_data['name'],
                    phone=contact_data.get('phone', ''),
                    email=contact_data.get('email', ''),
                    role=contact_data.get('role', 'member'),
                    notification_preferences=contact_data.get('notification_preferences', {
                        'sms': True,
                        'email': True,
                        'phone_call': False
                    }),
                    wifi_network=contact_data.get('wifi_network')
                )
                self.emergency_service.add_emergency_contact(contact)
            
            logger.info(f"Loaded {len(contacts)} emergency contacts")
            
        except Exception as e:
            logger.error(f"Failed to load emergency contacts: {e}")
    
    def get_emergency_contacts_from_db(self) -> List[Dict]:
        """Get emergency contacts from database"""
        try:
            # This would query your database for emergency contacts
            # For now, return empty list
            return []
        except Exception as e:
            logger.error(f"Failed to get emergency contacts from database: {e}")
            return []
    
    def get_emergency_contacts_from_config(self) -> List[Dict]:
        """Get emergency contacts from configuration"""
        # Default emergency contacts
        return [
            {
                'name': 'Club Manager',
                'phone': '+1234567890',
                'email': 'manager@rowingclub.com',
                'role': 'admin',
                'notification_preferences': {
                    'sms': True,
                    'email': True,
                    'phone_call': True
                }
            },
            {
                'name': 'Safety Officer',
                'phone': '+1234567891',
                'email': 'safety@rowingclub.com',
                'role': 'admin',
                'notification_preferences': {
                    'sms': True,
                    'email': True,
                    'phone_call': False
                }
            }
        ]
    
    def start_emergency_monitoring(self):
        """Start monitoring for boats outside after hours"""
        if self.monitoring_active:
            logger.warning("Emergency monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        
        logger.info("Emergency monitoring started")
    
    def stop_emergency_monitoring(self):
        """Stop emergency monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logger.info("Emergency monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                self.check_boats_outside_after_hours()
                time.sleep(self.config['emergency_check_interval'])
            except Exception as e:
                logger.error(f"Error in emergency monitoring loop: {e}")
                time.sleep(60)  # Wait before retrying
    
    def check_boats_outside_after_hours(self):
        """Check for boats outside after closing time"""
        try:
            closing_time = self.parse_closing_time()
            current_time = datetime.now(timezone.utc).time()
            
            # Check if current time is after closing time
            if current_time > closing_time:
                boats_outside = self.get_boats_outside()
                
                if boats_outside:
                    escalation_level = self.calculate_escalation_level(boats_outside, closing_time)
                    
                    logger.warning(f"EMERGENCY: {len(boats_outside)} boats outside after hours (escalation level {escalation_level})")
                    
                    # Send emergency alert
                    self.emergency_service.send_emergency_boat_alert(
                        boats_outside=boats_outside,
                        closing_time=closing_time.strftime("%H:%M"),
                        escalation_level=escalation_level
                    )
                else:
                    logger.debug("No boats outside after hours")
            else:
                logger.debug(f"Before closing time ({closing_time.strftime('%H:%M')})")
                
        except Exception as e:
            logger.error(f"Failed to check boats outside after hours: {e}")
    
    def parse_closing_time(self) -> datetime.time:
        """Parse closing time from config"""
        try:
            return datetime.strptime(self.config['closing_time'], "%H:%M").time()
        except ValueError:
            logger.error(f"Invalid closing time format: {self.config['closing_time']}")
            return datetime.strptime("18:00", "%H:%M").time()
    
    def get_boats_outside(self) -> List[BoatAlert]:
        """Get boats currently outside"""
        boats_outside = []
        
        try:
            # Query database for boats with status OUT
            query = """
                SELECT b.name, b.beacon_id, p.timestamp, p.location
                FROM boats b
                JOIN passages p ON b.beacon_id = p.beacon_id
                WHERE b.status = 'OUT'
                AND p.timestamp = (
                    SELECT MAX(timestamp) 
                    FROM passages p2 
                    WHERE p2.beacon_id = b.beacon_id
                )
                ORDER BY p.timestamp DESC
            """
            
            results = self.db_manager.execute_query(query)
            
            for row in results:
                boat_alert = BoatAlert(
                    boat_name=row[0],
                    beacon_id=row[1],
                    last_seen=datetime.fromisoformat(row[2].replace('Z', '+00:00')),
                    location=row[3],
                    urgency_level=1
                )
                boats_outside.append(boat_alert)
            
            logger.debug(f"Found {len(boats_outside)} boats outside")
            
        except Exception as e:
            logger.error(f"Failed to get boats outside: {e}")
        
        return boats_outside
    
    def calculate_escalation_level(self, boats: List[BoatAlert], closing_time: datetime.time) -> int:
        """Calculate escalation level based on how long boats have been outside"""
        if not boats:
            return 0
        
        # Find the oldest boat outside
        oldest_boat = min(boats, key=lambda b: b.last_seen)
        
        # Calculate hours outside
        closing_datetime = datetime.combine(datetime.today(), closing_time)
        current_datetime = datetime.now(timezone.utc)
        
        # Handle timezone conversion
        if oldest_boat.last_seen.tzinfo is None:
            oldest_boat.last_seen = oldest_boat.last_seen.replace(tzinfo=timezone.utc)
        
        hours_outside = (current_datetime - oldest_boat.last_seen).total_seconds() / 3600
        
        # Determine escalation level
        if hours_outside >= 3:
            return 3  # Critical
        elif hours_outside >= 2:
            return 2  # Emergency
        elif hours_outside >= 1:
            return 1  # Urgent
        else:
            return 0  # Normal alert
    
    def add_emergency_contact(self, contact_data: Dict):
        """Add emergency contact"""
        try:
            contact = EmergencyContact(
                name=contact_data['name'],
                phone=contact_data.get('phone', ''),
                email=contact_data.get('email', ''),
                role=contact_data.get('role', 'member'),
                notification_preferences=contact_data.get('notification_preferences', {
                    'sms': True,
                    'email': True,
                    'phone_call': False
                }),
                wifi_network=contact_data.get('wifi_network')
            )
            
            self.emergency_service.add_emergency_contact(contact)
            
            # Save to database
            self.save_emergency_contact_to_db(contact_data)
            
            logger.info(f"Added emergency contact: {contact.name}")
            
        except Exception as e:
            logger.error(f"Failed to add emergency contact: {e}")
            raise
    
    def save_emergency_contact_to_db(self, contact_data: Dict):
        """Save emergency contact to database"""
        try:
            # This would save to your database
            # For now, just log
            logger.debug(f"Saving emergency contact to database: {contact_data['name']}")
        except Exception as e:
            logger.error(f"Failed to save emergency contact to database: {e}")
    
    def test_emergency_notification(self, urgency: int = 2):
        """Send test emergency notification"""
        try:
            test_boats = [
                BoatAlert(
                    boat_name="Test Boat 1",
                    beacon_id="test_beacon_1",
                    last_seen=datetime.now(timezone.utc) - timedelta(hours=2),
                    location="Outside Shed",
                    urgency_level=urgency
                ),
                BoatAlert(
                    boat_name="Test Boat 2",
                    beacon_id="test_beacon_2",
                    last_seen=datetime.now(timezone.utc) - timedelta(hours=1),
                    location="Outside Shed",
                    urgency_level=urgency
                )
            ]
            
            self.emergency_service.send_emergency_boat_alert(
                boats_outside=test_boats,
                closing_time="18:00",
                escalation_level=urgency
            )
            
            logger.info(f"Test emergency notification sent (urgency level {urgency})")
            
        except Exception as e:
            logger.error(f"Failed to send test emergency notification: {e}")
            raise
    
    def get_status(self) -> Dict:
        """Get emergency notification system status"""
        return {
            'monitoring_active': self.monitoring_active,
            'closing_time': self.config['closing_time'],
            'check_interval': self.config['emergency_check_interval'],
            'escalation_enabled': self.config['escalation_enabled'],
            'web_push_enabled': self.config['web_push_enabled'],
            'sms_enabled': self.config['sms_enabled'],
            'email_enabled': self.config['email_enabled'],
            'phone_call_enabled': self.config['phone_call_enabled'],
            'emergency_contacts_count': len(self.emergency_service.contacts),
            'web_push_subscriptions_count': len(self.emergency_service.web_push_subscriptions),
            'database_connected': self.db_manager is not None,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

# Main function for testing
def main():
    """Test the emergency notification integration"""
    try:
        # Initialize integration
        integration = EmergencyNotificationIntegration()
        
        # Print status
        status = integration.get_status()
        print("Emergency Notification Integration Status:")
        print(json.dumps(status, indent=2))
        
        # Test emergency notification
        print("\nSending test emergency notification...")
        integration.test_emergency_notification(urgency=2)
        
        # Start monitoring
        print("\nStarting emergency monitoring...")
        integration.start_emergency_monitoring()
        
        # Keep running
        try:
            while True:
                time.sleep(60)
                print(f"Emergency monitoring active at {datetime.now().strftime('%H:%M:%S')}")
        except KeyboardInterrupt:
            print("\nStopping emergency monitoring...")
            integration.stop_emergency_monitoring()
            print("Emergency monitoring stopped")
        
    except Exception as e:
        logger.error(f"Failed to run emergency notification integration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
