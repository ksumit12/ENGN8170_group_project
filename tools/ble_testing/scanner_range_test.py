#!/usr/bin/env python3
"""
Simple BLE Scanner Range Test
Tests individual BLE dongles and their range with beacons
"""

import asyncio
import time
import sys
from datetime import datetime
from typing import Dict, List
import argparse

try:
    from bleak import BleakScanner
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    print("ERROR: bleak library not found. Install with: pip3 install bleak")
    sys.exit(1)

class ScannerRangeTester:
    def __init__(self):
        self.readings = []
        self.running = False
        self.target_beacon = None
        
    def estimate_distance(self, rssi: int) -> float:
        """Estimate distance based on RSSI"""
        if rssi == 0:
            return -1.0
        
        # Typical beacon TX power is around -59 dBm
        tx_power = -59
        n = 2.0  # Path loss exponent (free space = 2)
        
        ratio = (tx_power - rssi) / (10 * n)
        distance = 10 ** ratio
        
        return round(distance, 2)
    
    def is_beacon(self, device: BLEDevice, adv_data: AdvertisementData) -> bool:
        """Check if device is a beacon"""
        # Check for iBeacon (Apple manufacturer data)
        if adv_data.manufacturer_data:
            for manufacturer_id, data in adv_data.manufacturer_data.items():
                if manufacturer_id == 0x004C and len(data) >= 23:  # Apple iBeacon
                    return True
        
        # Check for Eddystone
        if adv_data.service_uuids:
            eddystone_uuid = "0000feaa-0000-1000-8000-00805f9b34fb"
            if eddystone_uuid in adv_data.service_uuids:
                return True
        
        # Check for named beacons
        if device.name and any(keyword in device.name.lower() for keyword in ['beacon', 'ibeacon', 'eddystone']):
            return True
        
        return False
    
    def get_adapter_info(self, adapter: str) -> str:
        """Get information about the adapter type"""
        adapter_info = {
            'hci0': 'System Bluetooth (Built-in)',
            'hci1': 'TP-Link BLE Scanner #2 (USB)',
            'hci2': 'TP-Link BLE Scanner #1 (USB)',
            'hci3': 'Additional BLE Adapter'
        }
        return adapter_info.get(adapter, f'Unknown Adapter ({adapter})')

    async def scan_with_adapter(self, adapter: str, duration: int = 30):
        """Scan using a specific BLE adapter"""
        adapter_type = self.get_adapter_info(adapter)
        print(f"\nSCANNING WITH ADAPTER: {adapter}")
        print(f"Adapter Type: {adapter_type}")
        print("=" * 50)
        
        found_beacons = set()
        start_time = time.time()
        
        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            if self.running and self.is_beacon(device, advertisement_data):
                beacon_name = device.name or f"Unknown-{device.address[:8]}"
                
                # Filter for target beacon if specified
                if self.target_beacon and self.target_beacon.lower() not in beacon_name.lower():
                    return
                
                distance = self.estimate_distance(advertisement_data.rssi)
                
                reading = {
                    'timestamp': datetime.now(),
                    'beacon_name': beacon_name,
                    'beacon_mac': device.address,
                    'rssi': advertisement_data.rssi,
                    'distance': distance,
                    'adapter': adapter,
                    'adapter_type': adapter_type
                }
                
                self.readings.append(reading)
                
                if device.address not in found_beacons:
                    found_beacons.add(device.address)
                    print(f"  {beacon_name} ({device.address}) - RSSI: {advertisement_data.rssi} dBm - Distance: {distance}m")
        
        try:
            # Create scanner with specific adapter
            scanner = BleakScanner(detection_callback, adapter=adapter)
            await scanner.start()
            
            self.running = True
            print(f"Scanning for {duration} seconds...")
            print("Walk around with your beacon to test range!")
            print("Press Ctrl+C to stop early")
            
            await asyncio.sleep(duration)
            
            await scanner.stop()
            self.running = False
            
            elapsed = time.time() - start_time
            print(f"\nScan completed in {elapsed:.1f} seconds")
            print(f"Found {len(found_beacons)} unique beacons")
            
        except Exception as e:
            print(f"Error scanning with adapter {adapter}: {e}")
            print(f"This might be because {adapter} is not available or not a BLE adapter")
            self.running = False
    
    def analyze_readings(self):
        """Analyze the collected readings"""
        if not self.readings:
            print("No readings to analyze")
            return
        
        print("\nRANGE TEST ANALYSIS")
        print("=" * 30)
        
        # Group by beacon
        beacon_groups = {}
        for reading in self.readings:
            mac = reading['beacon_mac']
            if mac not in beacon_groups:
                beacon_groups[mac] = []
            beacon_groups[mac].append(reading)
        
        for mac, readings in beacon_groups.items():
            if not readings:
                continue
            
            beacon_name = readings[0]['beacon_name']
            rssi_values = [r['rssi'] for r in readings]
            distances = [r['distance'] for r in readings if r['distance'] > 0]
            
            print(f"\nBeacon: {beacon_name}")
            print(f"  Total readings: {len(readings)}")
            print(f"  RSSI range: {min(rssi_values)} to {max(rssi_values)} dBm")
            print(f"  Average RSSI: {sum(rssi_values)/len(rssi_values):.1f} dBm")
            
            if distances:
                print(f"  Distance range: {min(distances):.1f}m to {max(distances):.1f}m")
                print(f"  Average distance: {sum(distances)/len(distances):.1f}m")
                print(f"  Max range detected: {max(distances):.1f}m")
            
            # Show strongest and weakest signals
            strongest = max(readings, key=lambda x: x['rssi'])
            weakest = min(readings, key=lambda x: x['rssi'])
            
            print(f"  Strongest signal: {strongest['rssi']} dBm at {strongest['distance']}m")
            print(f"  Weakest signal: {weakest['rssi']} dBm at {weakest['distance']}m")
    
    async def test_all_adapters(self, duration: int = 30):
        """Test all available BLE adapters"""
        print("TESTING ALL BLE ADAPTERS")
        print("=" * 30)
        print("Focusing on TP-Link BLE Scanners...")
        
        # Test TP-Link adapters first, then system adapter
        adapters_to_test = ['hci2', 'hci1', 'hci0']  # TP-Link #1, TP-Link #2, System
        
        for adapter in adapters_to_test:
            try:
                adapter_type = self.get_adapter_info(adapter)
                print(f"\nTesting adapter: {adapter} ({adapter_type})")
                self.readings.clear()  # Clear previous readings
                await self.scan_with_adapter(adapter, duration)
                self.analyze_readings()
                
                # Wait between tests
                if adapter != adapters_to_test[-1]:  # Not the last adapter
                    print(f"\nWaiting 5 seconds before testing next adapter...")
                    await asyncio.sleep(5)
                    
            except Exception as e:
                print(f"Could not test adapter {adapter}: {e}")
                continue
    
    async def interactive_range_test(self, beacon_name: str, duration: int = 60):
        """Interactive range test with instructions"""
        print(f"\nINTERACTIVE RANGE TEST")
        print("=" * 30)
        print(f"Target Beacon: {beacon_name}")
        print(f"Duration: {duration} seconds")
        print()
        print("INSTRUCTIONS:")
        print("1. Start at the scanner location (0m)")
        print("2. Walk away slowly while holding the beacon")
        print("3. Note the distance when beacon stops being detected")
        print("4. Return to scanner and repeat")
        print("5. Try different directions and obstacles")
        print()
        print("Starting in 5 seconds...")
        
        await asyncio.sleep(5)
        
        self.readings.clear()
        await self.scan_with_adapter('hci0', duration)  # Use default adapter
        self.analyze_readings()
        
        print("\nRANGE TEST COMPLETE!")
        print("Check the analysis above for maximum range detected.")

async def main():
    parser = argparse.ArgumentParser(description="BLE Scanner Range Test for TP-Link Adapters")
    parser.add_argument("--adapter", type=str, default="hci2", help="BLE adapter to use (hci2=TP-Link #1, hci1=TP-Link #2, hci0=System)")
    parser.add_argument("--duration", type=int, default=30, help="Scan duration in seconds")
    parser.add_argument("--beacon", type=str, help="Target specific beacon name")
    parser.add_argument("--test-all", action="store_true", help="Test all available adapters")
    parser.add_argument("--interactive", type=str, help="Interactive range test for specific beacon")
    
    args = parser.parse_args()
    
    tester = ScannerRangeTester()
    
    # Show adapter mapping
    print("TP-LINK BLE ADAPTER MAPPING:")
    print("hci2 = TP-Link BLE Scanner #1 (Primary)")
    print("hci1 = TP-Link BLE Scanner #2 (Secondary)")
    print("hci0 = System Bluetooth (Built-in)")
    print()
    
    try:
        if args.interactive:
            tester.target_beacon = args.interactive
            await tester.interactive_range_test(args.interactive, args.duration)
        elif args.test_all:
            await tester.test_all_adapters(args.duration)
        else:
            tester.target_beacon = args.beacon
            await tester.scan_with_adapter(args.adapter, args.duration)
            tester.analyze_readings()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        tester.running = False

if __name__ == "__main__":
    print("BLE SCANNER RANGE TESTER")
    print("========================")
    print("Test your BLE dongles and their range with beacons")
    print()
    
    asyncio.run(main())
