#!/usr/bin/env python3
"""
Simplified WiFi Emergency Notification API
API routes for WiFi-based emergency boat notifications
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone
import json
import logging
from typing import Dict, List, Optional
import pywebpush

# Configure logging
logger = logging.getLogger(__name__)

# Create Blueprint
wifi_emergency_api = Blueprint('wifi_emergency_api', __name__)

# In-memory storage for WiFi device subscriptions
wifi_device_subscriptions = []

@wifi_emergency_api.route('/api/wifi-emergency/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """Get VAPID public key for WiFi push notifications"""
    try:
        public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        if not public_key:
            return jsonify({'error': 'VAPID public key not configured'}), 500
        
        return jsonify({'publicKey': public_key})
    except Exception as e:
        logger.error(f"Failed to get VAPID public key: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@wifi_emergency_api.route('/api/wifi-emergency/subscribe', methods=['POST'])
def subscribe_wifi_device():
    """Subscribe WiFi device to emergency notifications"""
    try:
        data = request.get_json()
        
        if not data or 'subscription' not in data:
            return jsonify({'error': 'Subscription data required'}), 400
        
        # Get device information
        device_info = {
            'subscription': data['subscription'],
            'user_agent': data.get('userAgent', ''),
            'wifi_network': data.get('wifiNetwork', {}),
            'device_info': data.get('deviceInfo', {}),
            'subscribed_at': datetime.now(timezone.utc).isoformat(),
            'active': True,
            'ip_address': request.remote_addr
        }
        
        # Store subscription
        wifi_device_subscriptions.append(device_info)
        
        logger.info(f"WiFi device subscribed: {len(wifi_device_subscriptions)} total devices")
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to WiFi emergency notifications',
            'device_count': len(wifi_device_subscriptions),
            'wifi_network': device_info['wifi_network']
        })
        
    except Exception as e:
        logger.error(f"Failed to subscribe WiFi device: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@wifi_emergency_api.route('/api/wifi-emergency/unsubscribe', methods=['POST'])
def unsubscribe_wifi_device():
    """Unsubscribe WiFi device from emergency notifications"""
    try:
        data = request.get_json()
        
        if not data or 'subscription' not in data:
            return jsonify({'error': 'Subscription data required'}), 400
        
        # Find and remove subscription
        global wifi_device_subscriptions
        wifi_device_subscriptions = [
            sub for sub in wifi_device_subscriptions 
            if sub['subscription'] != data['subscription']
        ]
        
        logger.info(f"WiFi device unsubscribed: {len(wifi_device_subscriptions)} remaining")
        
        return jsonify({
            'success': True,
            'message': 'Successfully unsubscribed from WiFi emergency notifications'
        })
        
    except Exception as e:
        logger.error(f"Failed to unsubscribe WiFi device: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@wifi_emergency_api.route('/api/wifi-emergency/test', methods=['POST'])
def test_wifi_emergency_notification():
    """Send test emergency notification to all WiFi devices"""
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
        
        # Send to all subscribed WiFi devices
        sent_count = send_wifi_push_notification(test_notification)
        
        return jsonify({
            'success': True,
            'message': f'Test WiFi emergency notification sent to {sent_count} devices',
            'notification': test_notification
        })
        
    except Exception as e:
        logger.error(f"Failed to send test WiFi emergency notification: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@wifi_emergency_api.route('/api/wifi-emergency/status', methods=['GET'])
def get_wifi_emergency_status():
    """Get WiFi emergency notification system status"""
    try:
        return jsonify({
            'success': True,
            'subscribed_devices': len(wifi_device_subscriptions),
            'devices': [
                {
                    'ip_address': device['ip_address'],
                    'user_agent': device['user_agent'],
                    'subscribed_at': device['subscribed_at'],
                    'wifi_network': device['wifi_network']
                } for device in wifi_device_subscriptions
            ],
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get WiFi emergency status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@wifi_emergency_api.route('/api/wifi-emergency/acknowledge', methods=['POST'])
def acknowledge_wifi_notification():
    """Acknowledge receipt of WiFi emergency notification"""
    try:
        data = request.get_json()
        
        notification_id = data.get('notification_id')
        status = data.get('status')  # 'received', 'acknowledged', 'dismissed'
        urgency = data.get('urgency', 1)
        boats = data.get('boats', [])
        timestamp = data.get('timestamp')
        
        # Log acknowledgment
        logger.info(f"WiFi emergency notification {status}: ID={notification_id}, Urgency={urgency}, Boats={len(boats)}")
        
        return jsonify({
            'success': True,
            'message': f'WiFi notification {status} successfully',
            'acknowledgment': {
                'notification_id': notification_id,
                'status': status,
                'urgency': urgency,
                'boats': boats,
                'timestamp': timestamp,
                'acknowledged_at': datetime.now(timezone.utc).isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to acknowledge WiFi notification: {e}")
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

def send_wifi_push_notification(notification: Dict) -> int:
    """Send WiFi push notification to all subscribed devices"""
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
                    "tag": "wifi-boat-emergency",
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
                    vapid_claims={"sub": "mailto:wifi-emergency@rowingclub.com"}
                )
                
                sent_count += 1
                logger.info(f"WiFi emergency notification sent to device at {device_info['ip_address']}")
                
            except Exception as e:
                logger.error(f"Failed to send notification to device at {device_info['ip_address']}: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Failed to send WiFi push notifications: {e}")
    
    return sent_count

# Register the blueprint
def register_wifi_emergency_api(app):
    """Register WiFi emergency API blueprint with Flask app"""
    app.register_blueprint(wifi_emergency_api)
    logger.info("WiFi emergency notification API registered")
