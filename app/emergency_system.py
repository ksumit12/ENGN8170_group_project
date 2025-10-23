#!/usr/bin/env python3
"""
Consolidated Emergency Boat Notification System
WiFi-based emergency notifications for boats outside after hours
"""

import json
import time
import threading
import logging
import requests
import subprocess
import socket
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import pywebpush
from flask import Blueprint, request, jsonify, current_app

# Configure logging
logger = logging.getLogger(__name__)

# Create Blueprint for API endpoints
emergency_api = Blueprint('emergency_api', __name__)

# In-memory storage for WiFi device subscriptions
wifi_device_subscriptions = []

class EmergencyNotificationSystem:
    """Consolidated emergency notification system for WiFi-based boat alerts"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # WiFi network settings
        self.wifi_network = self.get_wifi_network_info()
        self.network_devices = []
        
        # Notification settings
        self.closing_time = config.get('closing_time', '18:00')
        self.check_interval = config.get('check_interval', 60)
        
        logger.info(f"Emergency Notification System initialized for network: {self.wifi_network['ssid']}")
    
    def get_wifi_network_info(self) -> Dict:
        """Get current WiFi network information"""
        try:
            # Get network interface information
            result = subprocess.run(['iwgetid'], capture_output=True, text=True)
            if result.returncode == 0:
                ssid = result.stdout.strip().split('"')[1] if '"' in result.stdout else 'Unknown'
            else:
                ssid = 'Unknown'
            
            # Get local IP and network range
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            network_base = '.'.join(local_ip.split('.')[:-1]) + '.'
            
            return {
                'ssid': ssid,
                'local_ip': local_ip,
                'network_base': network_base,
                'network_range': f"{network_base}0/24"
            }
        except Exception as e:
            logger.error(f"Failed to get WiFi network info: {e}")
            return {
                'ssid': 'Unknown',
                'local_ip': '192.168.1.100',
                'network_base': '192.168.1.',
                'network_range': '192.168.1.0/24'
            }
    
    def add_device_subscription(self, subscription_data: Dict):
        """Add device subscription from a WiFi-connected device"""
        subscription_info = {
            'subscription': subscription_data['subscription'],
            'user_agent': subscription_data.get('userAgent', ''),
            'wifi_network': subscription_data.get('wifiNetwork', {}),
            'device_info': subscription_data.get('deviceInfo', {}),
            'subscribed_at': datetime.now(timezone.utc).isoformat(),
            'active': True,
            'ip_address': subscription_data.get('ip_address', 'unknown')
        }
        
        wifi_device_subscriptions.append(subscription_info)
        logger.info(f"New WiFi device subscribed: {len(wifi_device_subscriptions)} total devices")
    
    def discover_wifi_devices(self) -> List[str]:
        """Discover devices connected to the WiFi network"""
        devices = []
        network_base = self.wifi_network['network_base']
        
        try:
            # Scan common IP addresses on the network
            for i in range(1, 255):
                ip = f"{network_base}{i}"
                if self.ping_device(ip):
                    devices.append(ip)
                    logger.debug(f"Found device at {ip}")
            
            self.network_devices = devices
            logger.info(f"Discovered {len(devices)} devices on WiFi network")
            
        except Exception as e:
            logger.error(f"Failed to discover WiFi devices: {e}")
        
        return devices
    
    def ping_device(self, ip: str) -> bool:
        """Ping a device to check if it's reachable"""
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', '1', ip], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    def send_emergency_alert(self, boats_outside: List[Dict], urgency_level: int = 1):
        """Send emergency alert to all WiFi-connected devices"""
        
        if not boats_outside:
            return
        
        boat_list = ", ".join([boat['name'] for boat in boats_outside])
        urgency_emoji = "🚨" if urgency_level >= 2 else "⚠️"
        
        # Create emergency message
        message = {
            "title": f"{urgency_emoji} EMERGENCY: Boats Outside After Hours",
            "body": f"{len(boats_outside)} boat(s) still outside after {self.closing_time}: {boat_list}",
            "urgency": urgency_level,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "boats": boats_outside,
            "vibration_pattern": self.get_vibration_pattern(urgency_level),
            "sound": "emergency" if urgency_level >= 2 else "alert",
            "wifi_network": self.wifi_network['ssid'],
            "url": "/dashboard"
        }
        
        # Send web push notifications to subscribed devices
        web_push_sent = self.send_web_push_notifications(message)
        
        # Try to notify other devices on the network
        network_notifications_sent = self.send_network_broadcast(message)
        
        logger.warning(f"EMERGENCY ALERT SENT: {len(boats_outside)} boats outside")
        logger.info(f"Web push notifications sent: {web_push_sent}")
        logger.info(f"Network broadcast notifications sent: {network_notifications_sent}")
    
    def get_vibration_pattern(self, urgency_level: int) -> List[int]:
        """Get vibration pattern based on urgency level"""
        patterns = {
            1: [200, 100, 200],                    # Normal alert
            2: [300, 100, 300, 100, 300],         # Urgent
            3: [500, 200, 500, 200, 500, 200, 500], # Emergency
            4: [1000, 500, 1000, 500, 1000]       # Critical
        }
        return patterns.get(urgency_level, [200, 100, 200])
    
    def send_web_push_notifications(self, message: Dict) -> int:
        """Send web push notifications to all subscribed devices"""
        sent_count = 0
        
        try:
            vapid_private_key = self.config.get('vapid_private_key')
            vapid_public_key = self.config.get('vapid_public_key')
            
            if not vapid_private_key or not vapid_public_key:
                logger.error("VAPID keys not configured")
                return 0
            
            for subscription_info in wifi_device_subscriptions:
                if not subscription_info.get('active', True):
                    continue
                
                try:
                    subscription = subscription_info['subscription']
                    
                    # Enhanced notification for emergency
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
                        vapid_private_key=vapid_private_key,
                        vapid_public_key=vapid_public_key,
                        vapid_claims={"sub": "mailto:emergency@rowingclub.com"}
                    )
                    
                    sent_count += 1
                    logger.info(f"Emergency notification sent to WiFi device")
                    
                except Exception as e:
                    logger.error(f"Failed to send notification to WiFi device: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Failed to send web push notifications: {e}")
        
        return sent_count
    
    def send_network_broadcast(self, message: Dict) -> int:
        """Try to send notifications to other devices on the WiFi network"""
        sent_count = 0
        
        try:
            # Discover devices on the network
            devices = self.discover_wifi_devices()
            
            for device_ip in devices:
                if self.try_notify_device(device_ip, message):
                    sent_count += 1
                    
        except Exception as e:
            logger.error(f"Network broadcast failed: {e}")
        
        return sent_count
    
    def try_notify_device(self, device_ip: str, message: Dict) -> bool:
        """Try to send notification to a specific device on the network"""
        # Try common notification endpoints
        endpoints = [
            f"http://{device_ip}:8080/api/emergency-notify",
            f"http://{device_ip}:3000/emergency-notify",
            f"http://{device_ip}:5000/api/emergency-notify",
            f"http://{device_ip}:8080/emergency",
            f"http://{device_ip}:3000/emergency"
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
    
    def start_monitoring(self, db_manager):
        """Start monitoring for boats outside after hours on WiFi network"""
        def monitor_loop():
            while self.monitoring_active:
                try:
                    self.check_boats_outside_after_hours(db_manager)
                    time.sleep(self.check_interval)
                except Exception as e:
                    logger.error(f"Emergency monitoring error: {e}")
                    time.sleep(60)
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("Emergency monitoring started")
    
    def stop_monitoring(self):
        """Stop emergency monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("Emergency monitoring stopped")
    
    def check_boats_outside_after_hours(self, db_manager):
        """Check for boats outside after closing time"""
        try:
            closing_time = datetime.strptime(self.closing_time, "%H:%M").time()
            current_time = datetime.now(timezone.utc).time()
            
            if current_time > closing_time:
                boats_outside = self.get_boats_outside(db_manager)
                
                if boats_outside:
                    urgency_level = self.calculate_urgency_level(boats_outside, closing_time)
                    
                    logger.warning(f"EMERGENCY: {len(boats_outside)} boats outside after hours (urgency level {urgency_level})")
                    
                    # Send emergency alert to all WiFi devices
                    self.send_emergency_alert(
                        boats_outside=boats_outside,
                        urgency_level=urgency_level
                    )
                else:
                    logger.debug("No boats outside after hours")
            else:
                logger.debug(f"Before closing time ({closing_time.strftime('%H:%M')})")
                
        except Exception as e:
            logger.error(f"Failed to check boats outside after hours: {e}")
    
    def get_boats_outside(self, db_manager) -> List[Dict]:
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
            
            results = db_manager.execute_query(query)
            
            for row in results:
                boat_info = {
                    'name': row[0],
                    'beacon_id': row[1],
                    'last_seen': row[2],
                    'location': row[3]
                }
                boats_outside.append(boat_info)
            
            logger.debug(f"Found {len(boats_outside)} boats outside")
            
        except Exception as e:
            logger.error(f"Failed to get boats outside: {e}")
        
        return boats_outside
    
    def calculate_urgency_level(self, boats: List[Dict], closing_time: datetime.time) -> int:
        """Calculate urgency level based on how long boats have been outside"""
        if not boats:
            return 0
        
        # Find the oldest boat outside
        oldest_boat = min(boats, key=lambda b: b['last_seen'])
        
        # Calculate hours outside
        closing_datetime = datetime.combine(datetime.today(), closing_time)
        current_datetime = datetime.now(timezone.utc)
        
        # Handle timezone conversion
        if isinstance(oldest_boat['last_seen'], str):
            oldest_boat['last_seen'] = datetime.fromisoformat(oldest_boat['last_seen'].replace('Z', '+00:00'))
        
        hours_outside = (current_datetime - oldest_boat['last_seen']).total_seconds() / 3600
        
        # Determine urgency level
        if hours_outside >= 3:
            return 4  # Critical
        elif hours_outside >= 2:
            return 3  # Emergency
        elif hours_outside >= 1:
            return 2  # Urgent
        else:
            return 1  # Normal alert
    
    def test_emergency_notification(self, urgency: int = 2):
        """Send test emergency notification to all WiFi devices"""
        try:
            test_boats = [
                {
                    'name': 'Test Boat 1',
                    'beacon_id': 'test_beacon_1',
                    'last_seen': datetime.now(timezone.utc) - timedelta(hours=2),
                    'location': 'Outside Shed'
                },
                {
                    'name': 'Test Boat 2',
                    'beacon_id': 'test_beacon_2',
                    'last_seen': datetime.now(timezone.utc) - timedelta(hours=1),
                    'location': 'Outside Shed'
                }
            ]
            
            self.send_emergency_alert(
                boats_outside=test_boats,
                urgency_level=urgency
            )
            
            logger.info(f"Test emergency notification sent (urgency level {urgency})")
            
        except Exception as e:
            logger.error(f"Failed to send test emergency notification: {e}")
            raise
    
    def get_status(self) -> Dict:
        """Get emergency notification system status"""
        return {
            'monitoring_active': self.monitoring_active,
            'closing_time': self.closing_time,
            'check_interval': self.check_interval,
            'wifi_network': self.wifi_network,
            'subscribed_devices': len(wifi_device_subscriptions),
            'discovered_devices': len(self.network_devices),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

# API Endpoints
@emergency_api.route('/api/emergency/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """Get VAPID public key for emergency push notifications"""
    try:
        public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        if not public_key:
            return jsonify({'error': 'VAPID public key not configured'}), 500
        
        return jsonify({'publicKey': public_key})
    except Exception as e:
        logger.error(f"Failed to get VAPID public key: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/emergency/subscribe', methods=['POST'])
def subscribe_device():
    """Subscribe device to emergency notifications"""
    try:
        data = request.get_json()
        
        if not data or 'subscription' not in data:
            return jsonify({'error': 'Subscription data required'}), 400
        
        # Get device information
        device_info = {
            'subscription': data['subscription'],
            'userAgent': data.get('userAgent', ''),
            'wifiNetwork': data.get('wifiNetwork', {}),
            'deviceInfo': data.get('deviceInfo', {}),
            'ip_address': request.remote_addr
        }
        
        # Store subscription
        wifi_device_subscriptions.append(device_info)
        
        logger.info(f"Device subscribed: {len(wifi_device_subscriptions)} total devices")
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to emergency notifications',
            'device_count': len(wifi_device_subscriptions),
            'wifi_network': device_info['wifiNetwork']
        })
        
    except Exception as e:
        logger.error(f"Failed to subscribe device: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/emergency/test', methods=['POST'])
def test_emergency_notification():
    """Send test emergency notification"""
    try:
        data = request.get_json()
        urgency = data.get('urgency', 2)
        boats = data.get('boats', ['Test Boat'])
        
        # Create test notification
        test_notification = {
            'title': '🚨 TEST: Emergency Boat Alert',
            'body': f'Test alert for {len(boats)} boat(s): {", ".join(boats)}',
            'urgency': urgency,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'boats': [{'name': boat, 'beacon_id': f'test_{i}', 'last_seen': datetime.now(timezone.utc).isoformat(), 'location': 'Test Location'} for i, boat in enumerate(boats)],
            'vibration_pattern': get_vibration_pattern(urgency),
            'sound': 'emergency' if urgency >= 2 else 'alert',
            'url': '/dashboard',
            'wifi_network': 'Test Network'
        }
        
        # Send to all subscribed devices
        sent_count = send_emergency_push_notification(test_notification)
        
        return jsonify({
            'success': True,
            'message': f'Test emergency notification sent to {sent_count} devices',
            'notification': test_notification
        })
        
    except Exception as e:
        logger.error(f"Failed to send test emergency notification: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/emergency/status', methods=['GET'])
def get_emergency_status():
    """Get emergency notification system status"""
    try:
        return jsonify({
            'success': True,
            'subscribed_devices': len(wifi_device_subscriptions),
            'devices': [
                {
                    'ip_address': device['ip_address'],
                    'user_agent': device['userAgent'],
                    'wifi_network': device['wifiNetwork']
                } for device in wifi_device_subscriptions
            ],
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get emergency status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Helper functions
def get_vibration_pattern(urgency: int) -> List[int]:
    """Get vibration pattern based on urgency level"""
    patterns = {
        1: [200, 100, 200],                    # Normal alert
        2: [300, 100, 300, 100, 300],         # Urgent
        3: [500, 200, 500, 200, 500, 200, 500], # Emergency
        4: [1000, 500, 1000, 500, 1000]       # Critical
    }
    return patterns.get(urgency, [200, 100, 200])

def send_emergency_push_notification(notification: Dict) -> int:
    """Send emergency push notification to all subscribed devices"""
    sent_count = 0
    
    try:
        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        
        if not vapid_private_key or not vapid_public_key:
            logger.error("VAPID keys not configured")
            return 0
        
        for device_info in wifi_device_subscriptions:
            if not device_info.get('active', True):
                continue
                
            try:
                subscription = device_info['subscription']
                
                # Enhanced notification for emergency
                notification_data = {
                    **notification,
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
                    vapid_private_key=vapid_private_key,
                    vapid_public_key=vapid_public_key,
                    vapid_claims={"sub": "mailto:emergency@rowingclub.com"}
                )
                
                sent_count += 1
                logger.info(f"Emergency notification sent to device at {device_info['ip_address']}")
                
            except Exception as e:
                logger.error(f"Failed to send notification to device at {device_info['ip_address']}: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Failed to send emergency push notifications: {e}")
    
    return sent_count

# Register the blueprint
def register_emergency_api(app):
    """Register emergency API blueprint with Flask app"""
    app.register_blueprint(emergency_api)
    logger.info("Emergency notification API registered")

# Main function for testing
def main():
    """Test the emergency notification system"""
    try:
        config = {
            'closing_time': '18:00',
            'check_interval': 60,
            'vapid_private_key': 'test_private_key',
            'vapid_public_key': 'test_public_key'
        }
        
        # Initialize emergency notification system
        emergency_system = EmergencyNotificationSystem(config)
        
        print("Emergency Notification System initialized")
        print(f"Network: {emergency_system.wifi_network['ssid']}")
        print(f"Local IP: {emergency_system.wifi_network['local_ip']}")
        
        # Test emergency notification
        emergency_system.test_emergency_notification(urgency=2)
        
    except Exception as e:
        logger.error(f"Failed to run emergency notification system: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
