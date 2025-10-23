// Consolidated Emergency Boat Notification System
// WiFi-based emergency notifications with vibration

class EmergencyNotificationManager {
    constructor() {
        this.isSupported = this.checkSupport();
        this.isRegistered = false;
        this.subscription = null;
        this.vibrationSupported = 'vibrate' in navigator;
        this.wifiNetwork = null;
        
        if (this.isSupported) {
            this.init();
        }
    }
    
    checkSupport() {
        return 'serviceWorker' in navigator && 
               'PushManager' in window && 
               'Notification' in window;
    }
    
    async init() {
        try {
            // Get WiFi network information
            this.wifiNetwork = await this.getWifiNetworkInfo();
            
            // Register service worker
            await this.registerServiceWorker();
            
            // Request notification permission
            const permission = await this.requestPermission();
            
            if (permission === 'granted') {
                // Subscribe to emergency push notifications
                await this.subscribeToPush();
                
                console.log('Emergency notifications initialized successfully');
                console.log(`Connected to WiFi network: ${this.wifiNetwork.ssid}`);
            } else {
                console.warn('Notification permission denied');
            }
        } catch (error) {
            console.error('Failed to initialize emergency notifications:', error);
        }
    }
    
    async getWifiNetworkInfo() {
        // Try to get WiFi network information
        if ('connection' in navigator) {
            const connection = navigator.connection;
            return {
                ssid: 'Current WiFi Network', // Browser doesn't expose SSID for security
                effectiveType: connection.effectiveType,
                type: connection.type,
                downlink: connection.downlink,
                isLocal: this.isLocalNetwork()
            };
        }
        
        // Fallback: check if on local network
        return {
            ssid: 'Local Network',
            isLocal: this.isLocalNetwork(),
            hostname: window.location.hostname
        };
    }
    
    isLocalNetwork() {
        const hostname = window.location.hostname;
        return hostname.includes('192.168') || 
               hostname.includes('10.0') ||
               hostname.includes('172.16') ||
               hostname === 'localhost' ||
               hostname === '127.0.0.1';
    }
    
    async registerServiceWorker() {
        const registration = await navigator.serviceWorker.register('/sw-emergency.js');
        console.log('Emergency service worker registered:', registration);
        return registration;
    }
    
    async requestPermission() {
        if (Notification.permission === 'granted') {
            return 'granted';
        } else if (Notification.permission !== 'denied') {
            return await Notification.requestPermission();
        }
        return 'denied';
    }
    
    async subscribeToPush() {
        const registration = await navigator.serviceWorker.ready;
        
        // Get VAPID public key
        const vapidPublicKey = await this.getVapidPublicKey();
        
        // Subscribe to push notifications
        this.subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: this.urlBase64ToUint8Array(vapidPublicKey)
        });
        
        // Send subscription to server with WiFi network info
        await this.sendSubscriptionToServer(this.subscription);
        
        this.isRegistered = true;
        console.log('Emergency push subscription created:', this.subscription);
    }
    
    async getVapidPublicKey() {
        try {
            const response = await fetch('/api/emergency/vapid-public-key');
            const data = await response.json();
            return data.publicKey;
        } catch (error) {
            console.error('Failed to get VAPID public key:', error);
            throw error;
        }
    }
    
    async sendSubscriptionToServer(subscription) {
        try {
            const response = await fetch('/api/emergency/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription,
                    userAgent: navigator.userAgent,
                    wifiNetwork: this.wifiNetwork,
                    deviceInfo: {
                        platform: navigator.platform,
                        language: navigator.language,
                        cookieEnabled: navigator.cookieEnabled,
                        onLine: navigator.onLine
                    }
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log('Subscription sent to server successfully');
                console.log(`Connected to ${data.wifi_network.ssid || 'WiFi network'}`);
            } else {
                throw new Error('Failed to send subscription to server');
            }
        } catch (error) {
            console.error('Failed to send subscription to server:', error);
            throw error;
        }
    }
    
    // Test emergency notification
    async testEmergencyNotification() {
        if (!this.isRegistered) {
            console.error('Emergency notifications not registered');
            return;
        }
        
        try {
            const response = await fetch('/api/emergency/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    urgency: 2,
                    boats: ['Test Boat 1', 'Test Boat 2']
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log('Test emergency notification sent');
                console.log(`Sent to ${data.message}`);
            } else {
                throw new Error('Failed to send test notification');
            }
        } catch (error) {
            console.error('Failed to send test emergency notification:', error);
        }
    }
    
    // Manual vibration test
    testVibration() {
        if (this.vibrationSupported) {
            navigator.vibrate([200, 100, 200, 100, 200]);
            console.log('Emergency vibration test executed');
        } else {
            console.warn('Vibration not supported on this device');
        }
    }
    
    // Play emergency sound
    playEmergencySound(soundType = 'emergency') {
        const audio = new Audio(`/sounds/${soundType}.mp3`);
        audio.volume = 0.8;
        audio.play().catch(error => {
            console.error('Failed to play emergency sound:', error);
        });
    }
    
    // Handle emergency sound messages from service worker
    handleServiceWorkerMessage(event) {
        if (event.data.type === 'PLAY_EMERGENCY_SOUND') {
            this.playEmergencySound(event.data.sound);
        }
    }
    
    // Unsubscribe from notifications
    async unsubscribe() {
        if (this.subscription) {
            try {
                await this.subscription.unsubscribe();
                
                // Notify server
                await fetch('/api/emergency/unsubscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        subscription: this.subscription
                    })
                });
                
                this.subscription = null;
                this.isRegistered = false;
                console.log('Unsubscribed from emergency notifications');
            } catch (error) {
                console.error('Failed to unsubscribe:', error);
            }
        }
    }
    
    // Utility function to convert VAPID key
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
    
    // Get notification status
    getStatus() {
        return {
            isSupported: this.isSupported,
            isRegistered: this.isRegistered,
            permission: Notification.permission,
            vibrationSupported: this.vibrationSupported,
            subscription: this.subscription ? 'active' : 'none',
            wifiNetwork: this.wifiNetwork,
            isLocalNetwork: this.isLocalNetwork()
        };
    }
}

// Emergency notification UI components
class EmergencyNotificationUI {
    constructor(notificationManager) {
        this.manager = notificationManager;
        this.createUI();
        this.bindEvents();
    }
    
    createUI() {
        // Create emergency notification control panel
        const panel = document.createElement('div');
        panel.id = 'emergency-notification-panel';
        panel.innerHTML = `
            <div class="emergency-panel">
                <h3>🚨 Emergency Boat Notifications</h3>
                <div class="status-indicator">
                    <span id="notification-status">Checking...</span>
                </div>
                <div class="wifi-info">
                    <p><strong>WiFi Network:</strong> <span id="wifi-network-name">Loading...</span></p>
                    <p><strong>Local Network:</strong> <span id="local-network-status">Checking...</span></p>
                </div>
                <div class="controls">
                    <button id="test-notification" class="btn btn-warning">Test Emergency Alert</button>
                    <button id="test-vibration" class="btn btn-info">Test Vibration</button>
                    <button id="test-sound" class="btn btn-success">Test Sound</button>
                    <button id="unsubscribe-btn" class="btn btn-danger">Unsubscribe</button>
                </div>
                <div class="info">
                    <p><strong>Status:</strong> <span id="status-details">Loading...</span></p>
                    <p><strong>Permission:</strong> <span id="permission-status">Unknown</span></p>
                    <p><strong>Vibration:</strong> <span id="vibration-status">Unknown</span></p>
                </div>
            </div>
        `;
        
        // Add styles
        const styles = `
            <style>
                .emergency-panel {
                    background: #fff3cd;
                    border: 2px solid #ffc107;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    font-family: Arial, sans-serif;
                }
                
                .emergency-panel h3 {
                    color: #856404;
                    margin-top: 0;
                }
                
                .wifi-info {
                    background: #e9ecef;
                    padding: 10px;
                    border-radius: 4px;
                    margin: 10px 0;
                }
                
                .wifi-info p {
                    margin: 5px 0;
                    font-size: 0.9rem;
                }
                
                .status-indicator {
                    margin: 10px 0;
                }
                
                .controls {
                    margin: 15px 0;
                }
                
                .controls button {
                    margin: 5px;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                
                .btn-warning { background-color: #ffc107; color: #212529; }
                .btn-info { background-color: #17a2b8; color: white; }
                .btn-success { background-color: #28a745; color: white; }
                .btn-danger { background-color: #dc3545; color: white; }
                
                .info {
                    background: #f8f9fa;
                    padding: 10px;
                    border-radius: 4px;
                    margin-top: 15px;
                }
                
                .info p {
                    margin: 5px 0;
                }
            </style>
        `;
        
        document.head.insertAdjacentHTML('beforeend', styles);
        
        // Add to dashboard
        const dashboard = document.querySelector('.dashboard-content') || document.body;
        dashboard.insertAdjacentElement('beforeend', panel);
    }
    
    bindEvents() {
        // Test notification button
        document.getElementById('test-notification').addEventListener('click', () => {
            this.manager.testEmergencyNotification();
        });
        
        // Test vibration button
        document.getElementById('test-vibration').addEventListener('click', () => {
            this.manager.testVibration();
        });
        
        // Test sound button
        document.getElementById('test-sound').addEventListener('click', () => {
            this.manager.playEmergencySound();
        });
        
        // Unsubscribe button
        document.getElementById('unsubscribe-btn').addEventListener('click', () => {
            if (confirm('Are you sure you want to unsubscribe from emergency notifications?')) {
                this.manager.unsubscribe();
                this.updateStatus();
            }
        });
        
        // Listen for service worker messages
        navigator.serviceWorker.addEventListener('message', (event) => {
            this.manager.handleServiceWorkerMessage(event);
        });
    }
    
    updateStatus() {
        const status = this.manager.getStatus();
        
        document.getElementById('notification-status').textContent = 
            status.isRegistered ? '✅ Active' : '❌ Inactive';
        
        document.getElementById('wifi-network-name').textContent = 
            status.wifiNetwork?.ssid || 'Unknown';
        
        document.getElementById('local-network-status').textContent = 
            status.isLocalNetwork ? '✅ Yes' : '❌ No';
        
        document.getElementById('status-details').textContent = 
            status.isSupported ? 'Supported' : 'Not Supported';
        
        document.getElementById('permission-status').textContent = 
            status.permission.charAt(0).toUpperCase() + status.permission.slice(1);
        
        document.getElementById('vibration-status').textContent = 
            status.vibrationSupported ? 'Supported' : 'Not Supported';
    }
}

// Service Worker for Emergency Notifications
const EMERGENCY_VIBRATION_PATTERNS = {
    NORMAL: [200, 100, 200],                    // Normal alert
    URGENT: [300, 100, 300, 100, 300],         // Urgent (1+ hours)
    EMERGENCY: [500, 200, 500, 200, 500, 200, 500], // Emergency (2+ hours)
    CRITICAL: [1000, 500, 1000, 500, 1000]    // Critical (3+ hours)
};

// Service Worker Registration
self.addEventListener('push', function(event) {
    console.log('Emergency Push event received:', event);
    
    if (event.data) {
        const data = event.data.json();
        console.log('Emergency Push data:', data);
        
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
            boats: data.boats || [],
            wifi_network: data.wifi_network || 'WiFi Network'
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
    
    // Show notification
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
    
    // Play emergency sound if supported
    playEmergencySound(data.sound);
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
    console.log('Emergency Notification clicked:', event);
    
    event.notification.close();
    
    const action = event.action;
    const data = event.notification.data;
    
    if (action === 'acknowledge') {
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
        // Notification dismissed
        console.log('Emergency notification dismissed');
        
    } else {
        // Default click - open dashboard
        event.waitUntil(
            clients.openWindow(data.url)
        );
    }
});

// Play emergency sound
function playEmergencySound(soundType) {
    if (soundType) {
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

// Initialize emergency notifications when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Initialize emergency notification manager
    const emergencyManager = new EmergencyNotificationManager();
    
    // Create UI if on dashboard
    if (window.location.pathname.includes('dashboard') || window.location.pathname === '/') {
        const emergencyUI = new EmergencyNotificationUI(emergencyManager);
        
        // Update status every 5 seconds
        setInterval(() => {
            emergencyUI.updateStatus();
        }, 5000);
    }
    
    // Make manager globally available
    window.emergencyNotificationManager = emergencyManager;
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { EmergencyNotificationManager, EmergencyNotificationUI };
}
