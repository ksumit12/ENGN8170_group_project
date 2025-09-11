#!/usr/bin/env python3
"""
BLE Beacon Detector
Handles BLE beacon scanning and detection logic
"""

import asyncio
import time
import threading
from bleak import BleakScanner

# Configuration
BEACON_ADDRESS = "DC:0D:30:23:05:F8"
BEACON_NAME = "rowing_clu"
RSSI_THRESHOLD = -60
TIMEOUT_SECONDS = 15.0

class BLEBeaconDetector:
    def __init__(self, callback=None):
        self.callback = callback
        self.beacon_detected = False
        self.last_seen = 0
        self.current_rssi = None
        self.current_signal_percentage = 0
        self.current_signal_strength = "No Signal"
        self.lock = threading.Lock()
        self.running = False
        
    def rssi_to_percentage(self, rssi_dbm):
        """Convert RSSI to percentage (0-100%)."""
        rssi_dbm = max(-100, min(-30, rssi_dbm))
        percentage = ((rssi_dbm + 100) / 70) * 100
        return max(0, min(100, int(percentage)))
    
    def get_signal_strength_text(self, percentage):
        """Get human-readable signal strength text."""
        if percentage >= 80:
            return "Excellent"
        elif percentage >= 60:
            return "Good"
        elif percentage >= 40:
            return "Fair"
        elif percentage >= 20:
            return "Weak"
        elif percentage >= 5:
            return "Very Weak"
        else:
            return "No Signal"
    
    def detection_callback(self, device, advertisement_data):
        """Callback for BLE device detection."""
        if device.address == BEACON_ADDRESS:
            rssi = advertisement_data.rssi
            current_time = time.time()
            
            with self.lock:
                self.last_seen = current_time
                self.current_rssi = rssi
                self.current_signal_percentage = self.rssi_to_percentage(rssi)
                self.current_signal_strength = self.get_signal_strength_text(self.current_signal_percentage)
            
            print(f"Detected beacon {device.name} ({device.address}) - RSSI: {rssi} dBm")
            
            # Only trigger entry if signal is strong enough
            if rssi >= RSSI_THRESHOLD:
                if not self.beacon_detected:
                    self.beacon_detected = True
                    if self.callback:
                        self.callback('beacon_detected', {
                            'rssi': rssi,
                            'signal_percentage': self.current_signal_percentage,
                            'signal_strength': self.current_signal_strength
                        })
            else:
                # Update signal info but don't trigger entry
                if self.callback:
                    self.callback('signal_update', {
                        'rssi': rssi,
                        'signal_percentage': self.current_signal_percentage,
                        'signal_strength': self.current_signal_strength
                    })
    
    async def scan_for_beacon(self):
        """Scan for the target beacon using BLE."""
        print(f"Scanning for beacon {BEACON_ADDRESS} ({BEACON_NAME})...")
        print(f"RSSI threshold: {RSSI_THRESHOLD} dBm")
        
        scanner = BleakScanner(self.detection_callback)
        try:
            await scanner.start()
            print("BLE scanner started successfully")
            self.running = True
            
            # Start timeout checker
            async def check_timeout():
                while self.running:
                    await asyncio.sleep(1)  # Check every second
                    with self.lock:
                        current_time = time.time()
                        if (self.beacon_detected and 
                            self.last_seen > 0 and 
                            current_time - self.last_seen > TIMEOUT_SECONDS):
                            print(f"Beacon timeout after {TIMEOUT_SECONDS}s - considering lost")
                            self.beacon_detected = False
                            if self.callback:
                                self.callback('beacon_lost', {
                                    'rssi': self.current_rssi,
                                    'signal_percentage': self.current_signal_percentage,
                                    'signal_strength': self.current_signal_strength
                                })
            
            # Run scanner and timeout checker concurrently
            await asyncio.gather(
                asyncio.create_task(check_timeout()),
                asyncio.create_task(asyncio.sleep(float('inf')))  # Keep scanner running
            )
            
        except Exception as e:
            print(f"BLE scan error: {e}")
        finally:
            self.running = False
            await scanner.stop()
            print("BLE scanner stopped")
    
    def start_scanning(self):
        """Start BLE scanning in a separate thread."""
        def run_scanner():
            asyncio.run(self.scan_for_beacon())
        
        self.scanner_thread = threading.Thread(target=run_scanner, daemon=True)
        self.scanner_thread.start()
    
    def stop_scanning(self):
        """Stop BLE scanning."""
        self.running = False
        if hasattr(self, 'scanner_thread'):
            self.scanner_thread.join(timeout=5)
    
    def get_status(self):
        """Get current beacon status."""
        with self.lock:
            return {
                'beacon_detected': self.beacon_detected,
                'current_rssi': self.current_rssi,
                'signal_percentage': self.current_signal_percentage,
                'signal_strength': self.current_signal_strength,
                'last_seen': self.last_seen,
                'running': self.running
            }


