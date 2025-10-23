// Emergency Boat Notification Manager
// Client-side JavaScript for emergency notifications with vibration

class EmergencyNotificationManager {
    constructor() {
        this.isSupported = this.checkSupport();
        this.isRegistered = false;
        this.subscription = null;
        this.vibrationSupported = 'vibrate' in navigator;
        
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
            // Register service worker
            await this.registerServiceWorker();
            
            // Request notification permission
            const permission = await this.requestPermission();
            
            if (permission === 'granted') {
                // Subscribe to push notifications
                await this.subscribeToPush();
                
                // Register for emergency monitoring
                await this.registerEmergencyMonitoring();
                
                console.log('Emergency notifications initialized successfully');
            } else {
                console.warn('Notification permission denied');
            }
        } catch (error) {
            console.error('Failed to initialize emergency notifications:', error);
        }
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
        
        // Send subscription to server
        await this.sendSubscriptionToServer(this.subscription);
        
        this.isRegistered = true;
        console.log('Push subscription created:', this.subscription);
    }
    
    async getVapidPublicKey() {
        try {
            const response = await fetch('/api/notifications/vapid-public-key');
            const data = await response.json();
            return data.publicKey;
        } catch (error) {
            console.error('Failed to get VAPID public key:', error);
            throw error;
        }
    }
    
    async sendSubscriptionToServer(subscription) {
        try {
            const response = await fetch('/api/notifications/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription,
                    userAgent: navigator.userAgent,
                    wifiNetwork: await this.getWifiNetworkInfo(),
                    notificationPreferences: {
                        emergency: true,
                        vibration: this.vibrationSupported,
                        sound: true
                    }
                })
            });
            
            if (response.ok) {
                console.log('Subscription sent to server successfully');
            } else {
                throw new Error('Failed to send subscription to server');
            }
        } catch (error) {
            console.error('Failed to send subscription to server:', error);
            throw error;
        }
    }
    
    async getWifiNetworkInfo() {
        // Try to get WiFi network information
        if ('connection' in navigator) {
            const connection = navigator.connection;
            return {
                effectiveType: connection.effectiveType,
                type: connection.type,
                downlink: connection.downlink
            };
        }
        
        // Fallback: check if on local network
        const isLocal = window.location.hostname.includes('192.168') || 
                       window.location.hostname.includes('10.0') ||
                       window.location.hostname === 'localhost';
        
        return {
            isLocal: isLocal,
            hostname: window.location.hostname
        };
    }
    
    async registerEmergencyMonitoring() {
        // Send message to service worker to register for emergency monitoring
        if ('serviceWorker' in navigator) {
            const registration = await navigator.serviceWorker.ready;
            if (registration.active) {
                registration.active.postMessage({
                    type: 'REGISTER_EMERGENCY_MONITORING'
                });
            }
        }
    }
    
    // Test emergency notification
    async testEmergencyNotification() {
        if (!this.isRegistered) {
            console.error('Emergency notifications not registered');
            return;
        }
        
        try {
            const response = await fetch('/api/notifications/test-emergency', {
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
                console.log('Test emergency notification sent');
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
            console.log('Vibration test executed');
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
                await fetch('/api/notifications/unsubscribe', {
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
            subscription: this.subscription ? 'active' : 'none'
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
                <h3>🚨 Emergency Notifications</h3>
                <div class="status-indicator">
                    <span id="notification-status">Checking...</span>
                </div>
                <div class="controls">
                    <button id="test-notification" class="btn btn-warning">Test Notification</button>
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
        
        document.getElementById('status-details').textContent = 
            status.isSupported ? 'Supported' : 'Not Supported';
        
        document.getElementById('permission-status').textContent = 
            status.permission.charAt(0).toUpperCase() + status.permission.slice(1);
        
        document.getElementById('vibration-status').textContent = 
            status.vibrationSupported ? 'Supported' : 'Not Supported';
    }
}

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
