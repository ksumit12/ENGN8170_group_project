// Emergency Boat Notification Service Worker
// High-priority notifications with vibration for boats outside after hours

const VAPID_PUBLIC_KEY = 'YOUR_VAPID_PUBLIC_KEY_HERE';

// Emergency vibration patterns
const EMERGENCY_VIBRATION_PATTERNS = {
    NORMAL: [200, 100, 200],                    // Normal alert
    URGENT: [300, 100, 300, 100, 300],         // Urgent (1+ hours)
    EMERGENCY: [500, 200, 500, 200, 500, 200, 500], // Emergency (2+ hours)
    CRITICAL: [1000, 500, 1000, 500, 1000]    // Critical (3+ hours)
};

// Notification sounds
const NOTIFICATION_SOUNDS = {
    alert: '/sounds/alert.mp3',
    emergency: '/sounds/emergency.mp3',
    critical: '/sounds/critical.mp3'
};

// Service Worker Registration
self.addEventListener('push', function(event) {
    console.log('Push event received:', event);
    
    if (event.data) {
        const data = event.data.json();
        console.log('Push data:', data);
        
        // Handle emergency boat notifications
        if (data.title && data.title.includes('EMERGENCY')) {
            handleEmergencyBoatNotification(data);
        } else {
            handleNormalNotification(data);
        }
    }
});

// Handle emergency boat notifications
function handleEmergencyBoatNotification(data) {
    const urgency = data.urgency || 1;
    const vibrationPattern = data.vibration_pattern || EMERGENCY_VIBRATION_PATTERNS.NORMAL;
    
    // Determine notification options based on urgency
    const options = {
        body: data.body,
        icon: '/icons/emergency-192.png',
        badge: '/icons/emergency-badge-72.png',
        vibrate: vibrationPattern,
        data: {
            url: data.url || '/dashboard',
            timestamp: data.timestamp,
            urgency: urgency,
            boats: data.boats || []
        },
        requireInteraction: true, // Keep notification until user interacts
        silent: false,
        tag: 'boat-emergency',
        renotify: true, // Re-notify even if notification with same tag exists
        actions: [
            {
                action: 'acknowledge',
                title: 'Acknowledge',
                icon: '/icons/ack-icon.png'
            },
            {
                action: 'view',
                title: 'View Dashboard',
                icon: '/icons/view-icon.png'
            },
            {
                action: 'dismiss',
                title: 'Dismiss',
                icon: '/icons/dismiss-icon.png'
            }
        ],
        // Custom notification styling for emergency
        image: '/images/emergency-boat-alert.png',
        timestamp: Date.now()
    };
    
    // Add sound based on urgency
    if (data.sound && NOTIFICATION_SOUNDS[data.sound]) {
        options.sound = NOTIFICATION_SOUNDS[data.sound];
    }
    
    // Show notification
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
    
    // Play emergency sound if supported
    playEmergencySound(data.sound);
    
    // Send acknowledgment to server
    sendNotificationAcknowledgment(data, 'received');
}

// Handle normal notifications
function handleNormalNotification(data) {
    const options = {
        body: data.body,
        icon: '/icons/boat-192.png',
        badge: '/icons/boat-badge-72.png',
        vibrate: [100, 50, 100],
        data: {
            url: data.url || '/dashboard',
            timestamp: data.timestamp
        },
        requireInteraction: false,
        silent: false,
        tag: 'boat-notification'
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
}

// Handle notification clicks
self.addEventListener('notificationclick', function(event) {
    console.log('Notification clicked:', event);
    
    event.notification.close();
    
    const action = event.action;
    const data = event.notification.data;
    
    if (action === 'acknowledge') {
        // Send acknowledgment to server
        sendNotificationAcknowledgment(data, 'acknowledged');
        
        // Show acknowledgment confirmation
        self.registration.showNotification('Alert Acknowledged', {
            body: 'Thank you for acknowledging the boat alert.',
            icon: '/icons/ack-confirmed.png',
            vibrate: [100],
            silent: true,
            tag: 'acknowledgment'
        });
        
    } else if (action === 'view') {
        // Open dashboard
        event.waitUntil(
            clients.openWindow(data.url)
        );
        
    } else if (action === 'dismiss') {
        // Send dismissal to server
        sendNotificationAcknowledgment(data, 'dismissed');
        
    } else {
        // Default click - open dashboard
        event.waitUntil(
            clients.openWindow(data.url)
        );
    }
});

// Handle notification close
self.addEventListener('notificationclose', function(event) {
    console.log('Notification closed:', event);
    
    const data = event.notification.data;
    if (data && data.urgency >= 2) {
        // For high-urgency notifications, send close event to server
        sendNotificationAcknowledgment(data, 'closed');
    }
});

// Play emergency sound
function playEmergencySound(soundType) {
    if (soundType && NOTIFICATION_SOUNDS[soundType]) {
        // Note: Service Workers can't directly play audio
        // This would need to be handled by the main page
        // Send message to main page to play sound
        self.clients.matchAll().then(function(clients) {
            clients.forEach(function(client) {
                client.postMessage({
                    type: 'PLAY_EMERGENCY_SOUND',
                    sound: soundType
                });
            });
        });
    }
}

// Send acknowledgment to server
function sendNotificationAcknowledgment(data, status) {
    fetch('/api/notifications/acknowledge', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            notification_id: data.timestamp,
            status: status,
            urgency: data.urgency,
            boats: data.boats,
            timestamp: new Date().toISOString()
        })
    }).catch(function(error) {
        console.error('Failed to send acknowledgment:', error);
    });
}

// Background sync for offline notifications
self.addEventListener('sync', function(event) {
    if (event.tag === 'emergency-notification-sync') {
        event.waitUntil(syncEmergencyNotifications());
    }
});

// Sync emergency notifications when back online
function syncEmergencyNotifications() {
    return fetch('/api/notifications/sync', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    }).then(function(response) {
        if (response.ok) {
            return response.json();
        }
        throw new Error('Sync failed');
    }).then(function(data) {
        // Process any missed emergency notifications
        if (data.missed_notifications) {
            data.missed_notifications.forEach(function(notification) {
                handleEmergencyBoatNotification(notification);
            });
        }
    }).catch(function(error) {
        console.error('Emergency notification sync failed:', error);
    });
}

// Handle push subscription updates
self.addEventListener('pushsubscriptionchange', function(event) {
    console.log('Push subscription changed:', event);
    
    event.waitUntil(
        fetch('/api/notifications/resubscribe', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                old_subscription: event.oldSubscription,
                new_subscription: event.newSubscription
            })
        })
    );
});

// Periodic background sync for emergency monitoring
self.addEventListener('periodicsync', function(event) {
    if (event.tag === 'emergency-monitor') {
        event.waitUntil(checkEmergencyStatus());
    }
});

// Check emergency status periodically
function checkEmergencyStatus() {
    return fetch('/api/emergency/status', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    }).then(function(response) {
        if (response.ok) {
            return response.json();
        }
        throw new Error('Status check failed');
    }).then(function(data) {
        if (data.boats_outside && data.boats_outside.length > 0) {
            // Show emergency notification if boats are still outside
            handleEmergencyBoatNotification({
                title: '🚨 EMERGENCY: Boats Still Outside',
                body: `${data.boats_outside.length} boat(s) still outside after hours`,
                urgency: data.urgency || 2,
                boats: data.boats_outside,
                timestamp: new Date().toISOString()
            });
        }
    }).catch(function(error) {
        console.error('Emergency status check failed:', error);
    });
}

// Install event
self.addEventListener('install', function(event) {
    console.log('Emergency notification service worker installed');
    self.skipWaiting();
});

// Activate event
self.addEventListener('activate', function(event) {
    console.log('Emergency notification service worker activated');
    event.waitUntil(self.clients.claim());
});

// Message handling from main page
self.addEventListener('message', function(event) {
    console.log('Message received in service worker:', event.data);
    
    if (event.data.type === 'REGISTER_EMERGENCY_MONITORING') {
        // Register for emergency monitoring
        registerEmergencyMonitoring();
    } else if (event.data.type === 'UNREGISTER_EMERGENCY_MONITORING') {
        // Unregister from emergency monitoring
        unregisterEmergencyMonitoring();
    }
});

// Register for emergency monitoring
function registerEmergencyMonitoring() {
    // Request periodic background sync
    if ('serviceWorker' in navigator && 'periodicSync' in window.ServiceWorkerRegistration.prototype) {
        navigator.serviceWorker.ready.then(function(registration) {
            return registration.periodicSync.register('emergency-monitor', {
                minInterval: 300000 // 5 minutes
            });
        }).then(function() {
            console.log('Emergency monitoring registered');
        }).catch(function(error) {
            console.error('Emergency monitoring registration failed:', error);
        });
    }
}

// Unregister from emergency monitoring
function unregisterEmergencyMonitoring() {
    if ('serviceWorker' in navigator && 'periodicSync' in window.ServiceWorkerRegistration.prototype) {
        navigator.serviceWorker.ready.then(function(registration) {
            return registration.periodicSync.unregister('emergency-monitor');
        }).then(function() {
            console.log('Emergency monitoring unregistered');
        }).catch(function(error) {
            console.error('Emergency monitoring unregistration failed:', error);
        });
    }
}
