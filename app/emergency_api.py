#!/usr/bin/env python3
"""
Emergency Notification API Endpoints
API routes for emergency boat notifications
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
emergency_api = Blueprint('emergency_api', __name__)

# In-memory storage for subscriptions (in production, use database)
web_push_subscriptions = []
emergency_contacts = []

@emergency_api.route('/api/notifications/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """Get VAPID public key for push notifications"""
    try:
        public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        if not public_key:
            return jsonify({'error': 'VAPID public key not configured'}), 500
        
        return jsonify({'publicKey': public_key})
    except Exception as e:
        logger.error(f"Failed to get VAPID public key: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/notifications/subscribe', methods=['POST'])
def subscribe_to_notifications():
    """Subscribe to emergency push notifications"""
    try:
        data = request.get_json()
        
        if not data or 'subscription' not in data:
            return jsonify({'error': 'Subscription data required'}), 400
        
        subscription_info = {
            'subscription': data['subscription'],
            'user_agent': data.get('userAgent', ''),
            'wifi_network': data.get('wifiNetwork', {}),
            'notification_preferences': data.get('notificationPreferences', {}),
            'subscribed_at': datetime.now(timezone.utc).isoformat(),
            'active': True
        }
        
        # Store subscription
        web_push_subscriptions.append(subscription_info)
        
        logger.info(f"New emergency notification subscription: {len(web_push_subscriptions)} total")
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to emergency notifications',
            'subscription_count': len(web_push_subscriptions)
        })
        
    except Exception as e:
        logger.error(f"Failed to subscribe to notifications: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/notifications/unsubscribe', methods=['POST'])
def unsubscribe_from_notifications():
    """Unsubscribe from emergency push notifications"""
    try:
        data = request.get_json()
        
        if not data or 'subscription' not in data:
            return jsonify({'error': 'Subscription data required'}), 400
        
        # Find and remove subscription
        global web_push_subscriptions
        web_push_subscriptions = [
            sub for sub in web_push_subscriptions 
            if sub['subscription'] != data['subscription']
        ]
        
        logger.info(f"Emergency notification unsubscribed: {len(web_push_subscriptions)} remaining")
        
        return jsonify({
            'success': True,
            'message': 'Successfully unsubscribed from emergency notifications'
        })
        
    except Exception as e:
        logger.error(f"Failed to unsubscribe from notifications: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/notifications/test-emergency', methods=['POST'])
def test_emergency_notification():
    """Send test emergency notification"""
    try:
        data = request.get_json()
        urgency = data.get('urgency', 1)
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
            'url': '/dashboard'
        }
        
        # Send to all subscribers
        sent_count = send_emergency_push_notification(test_notification)
        
        return jsonify({
            'success': True,
            'message': f'Test emergency notification sent to {sent_count} subscribers',
            'notification': test_notification
        })
        
    except Exception as e:
        logger.error(f"Failed to send test emergency notification: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/notifications/acknowledge', methods=['POST'])
def acknowledge_notification():
    """Acknowledge receipt of emergency notification"""
    try:
        data = request.get_json()
        
        notification_id = data.get('notification_id')
        status = data.get('status')  # 'received', 'acknowledged', 'dismissed', 'closed'
        urgency = data.get('urgency', 1)
        boats = data.get('boats', [])
        timestamp = data.get('timestamp')
        
        # Log acknowledgment
        logger.info(f"Emergency notification {status}: ID={notification_id}, Urgency={urgency}, Boats={len(boats)}")
        
        # Store acknowledgment in database (implement as needed)
        acknowledgment = {
            'notification_id': notification_id,
            'status': status,
            'urgency': urgency,
            'boats': boats,
            'timestamp': timestamp,
            'acknowledged_at': datetime.now(timezone.utc).isoformat()
        }
        
        # In production, save to database
        # db.save_notification_acknowledgment(acknowledgment)
        
        return jsonify({
            'success': True,
            'message': f'Notification {status} successfully',
            'acknowledgment': acknowledgment
        })
        
    except Exception as e:
        logger.error(f"Failed to acknowledge notification: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/notifications/sync', methods=['POST'])
def sync_notifications():
    """Sync missed notifications when back online"""
    try:
        # Get missed notifications since last sync
        # This would typically query the database for notifications sent while offline
        missed_notifications = get_missed_notifications()
        
        return jsonify({
            'success': True,
            'missed_notifications': missed_notifications,
            'sync_timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to sync notifications: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/notifications/resubscribe', methods=['POST'])
def resubscribe():
    """Handle push subscription changes"""
    try:
        data = request.get_json()
        old_subscription = data.get('old_subscription')
        new_subscription = data.get('new_subscription')
        
        # Update subscription in storage
        global web_push_subscriptions
        for i, sub in enumerate(web_push_subscriptions):
            if sub['subscription'] == old_subscription:
                web_push_subscriptions[i]['subscription'] = new_subscription
                web_push_subscriptions[i]['updated_at'] = datetime.now(timezone.utc).isoformat()
                break
        
        logger.info("Push subscription updated successfully")
        
        return jsonify({
            'success': True,
            'message': 'Subscription updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to resubscribe: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/emergency/status', methods=['GET'])
def get_emergency_status():
    """Get current emergency status"""
    try:
        # This would typically query the database for boats currently outside
        boats_outside = get_boats_outside_after_hours()
        
        urgency = 0
        if boats_outside:
            # Calculate urgency based on how long boats have been outside
            urgency = calculate_urgency_level(boats_outside)
        
        return jsonify({
            'boats_outside': boats_outside,
            'urgency': urgency,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'active_subscriptions': len(web_push_subscriptions)
        })
        
    except Exception as e:
        logger.error(f"Failed to get emergency status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/emergency/contacts', methods=['POST'])
def add_emergency_contact():
    """Add emergency contact for notifications"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'phone', 'email', 'role']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        contact = {
            'name': data['name'],
            'phone': data['phone'],
            'email': data['email'],
            'role': data['role'],
            'notification_preferences': data.get('notification_preferences', {
                'sms': True,
                'email': True,
                'phone_call': False
            }),
            'wifi_network': data.get('wifi_network'),
            'added_at': datetime.now(timezone.utc).isoformat(),
            'active': True
        }
        
        emergency_contacts.append(contact)
        
        logger.info(f"Added emergency contact: {contact['name']}")
        
        return jsonify({
            'success': True,
            'message': f'Emergency contact {contact["name"]} added successfully',
            'contact': contact
        })
        
    except Exception as e:
        logger.error(f"Failed to add emergency contact: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@emergency_api.route('/api/emergency/contacts', methods=['GET'])
def get_emergency_contacts():
    """Get all emergency contacts"""
    try:
        return jsonify({
            'success': True,
            'contacts': emergency_contacts,
            'count': len(emergency_contacts)
        })
        
    except Exception as e:
        logger.error(f"Failed to get emergency contacts: {e}")
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
    """Send emergency push notification to all subscribers"""
    sent_count = 0
    
    try:
        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        
        if not vapid_private_key or not vapid_public_key:
            logger.error("VAPID keys not configured")
            return 0
        
        for subscription_info in web_push_subscriptions:
            if not subscription_info.get('active', True):
                continue
                
            try:
                subscription = subscription_info['subscription']
                
                # Enhanced notification options for emergency
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
                logger.info(f"Emergency notification sent to subscriber")
                
            except Exception as e:
                logger.error(f"Failed to send notification to subscriber: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Failed to send emergency push notifications: {e}")
    
    return sent_count

def get_missed_notifications() -> List[Dict]:
    """Get notifications that were sent while user was offline"""
    # This would typically query the database for notifications sent in the last 24 hours
    # that the user hasn't acknowledged
    return []

def get_boats_outside_after_hours() -> List[Dict]:
    """Get boats currently outside after hours"""
    # This would typically query the database for boats with status OUT
    # and check if current time is after closing time
    return []

def calculate_urgency_level(boats: List[Dict]) -> int:
    """Calculate urgency level based on boats outside"""
    # This would typically calculate based on:
    # - How long boats have been outside
    # - Weather conditions
    # - Number of boats
    # - Time of day
    return 1

# Register the blueprint
def register_emergency_api(app):
    """Register emergency API blueprint with Flask app"""
    app.register_blueprint(emergency_api)
    logger.info("Emergency notification API registered")
