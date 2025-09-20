#!/usr/bin/env python3
"""
BLE Scanner Range Tester for Raspberry Pi
Tests multiple BLE dongles and their individual ranges
"""

import asyncio
import time
import json
import sys
from datetime import datetime
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, asdict
import argparse

try:
    from bleak import BleakScanner, BleakClient
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    print("ERROR: bleak library not found. Install with: pip3 install bleak")
    sys.exit(1)

@dataclass
class ScannerInfo:
    """Information about a BLE scanner/dongle"""
    name: str
    adapter: str
    address: str
    is_available: bool = False
    last_seen: Optional[datetime] = None

@dataclass
class BeaconReading:
    """Reading from a specific beacon"""
    beacon_name: str
    beacon_mac: str
    rssi: int
    scanner_name: str
    scanner_adapter: str
    timestamp: datetime
    distance_estimate: float = 0.0

class BLEScannerTester:
    def __init__(self):
        self.scanners: Dict[str, ScannerInfo] = {}
        self.beacon_readings: List[BeaconReading] = []
        self.running = False
        self.test_mode = False
        self.target_beacon = None
        
    async def discover_scanners(self) -> Dict[str, ScannerInfo]:
        """Discover available BLE adapters/scanners"""
        print("DISCOVERING BLE SCANNERS/ADAPTERS")
        print("=" * 40)
        
        try:
            # Get available adapters
            adapters = await BleakScanner.discover(return_adv=True)
            
            print(f"Found {len(adapters)} BLE devices...")
            
            # Look for potential BLE dongles/adapters
            for device, adv_data in adapters:
                # Check if it's a BLE adapter/dongle (usually has specific characteristics)
                if self._is_potential_scanner(device, adv_data):
                    scanner_info = ScannerInfo(
                        name=device.name or f"Unknown-{device.address[:8]}",
                        adapter=device.address,
                        address=device.address,
                        is_available=True,
                        last_seen=datetime.now()
                    )
                    self.scanners[device.address] = scanner_info
                    print(f"  Scanner: {scanner_info.name} ({scanner_info.address})")
            
            # Also try to get system adapters
            await self._check_system_adapters()
            
            print(f"\nTotal scanners found: {len(self.scanners)}")
            return self.scanners
            
        except Exception as e:
            print(f"Error discovering scanners: {e}")
            return {}
    
    def _is_potential_scanner(self, device: BLEDevice, adv_data: AdvertisementData) -> bool:
        """Check if a device is likely a BLE scanner/adapter"""
        # Look for common BLE adapter characteristics
        if not device.name:
            return False
            
        name_lower = device.name.lower()
        scanner_keywords = [
            'usb', 'bluetooth', 'ble', 'adapter', 'dongle', 
            'csr', 'broadcom', 'realtek', 'intel', 'qualcomm'
        ]
        
        return any(keyword in name_lower for keyword in scanner_keywords)
    
    async def _check_system_adapters(self):
        """Check for system BLE adapters"""
        try:
            # Try to scan with different adapters
            import subprocess
            result = subprocess.run(['hciconfig'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'hci' in line and 'UP' in line:
                        adapter_name = line.split(':')[0].strip()
                        if adapter_name not in self.scanners:
                            scanner_info = ScannerInfo(
                                name=f"System-{adapter_name}",
                                adapter=adapter_name,
                                address=adapter_name,
                                is_available=True,
                                last_seen=datetime.now()
                            )
                            self.scanners[adapter_name] = scanner_info
                            print(f"  System Adapter: {scanner_info.name}")
        except Exception as e:
            print(f"Could not check system adapters: {e}")
    
    async def scan_for_beacons(self, duration: int = 30, target_beacon: str = None):
        """Scan for beacons using all available scanners"""
        print(f"\nSCANNING FOR BEACONS ({duration} seconds)")
        print("=" * 40)
        
        if target_beacon:
            print(f"Looking for specific beacon: {target_beacon}")
        
        start_time = time.time()
        found_beacons = set()
        
        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            if self.running:
                # Check if it's a beacon (iBeacon, Eddystone, or named beacon)
                if self._is_beacon(device, advertisement_data):
                    beacon_name = device.name or f"Unknown-{device.address[:8]}"
                    
                    # If looking for specific beacon, filter others
                    if target_beacon and target_beacon.lower() not in beacon_name.lower():
                        return
                    
                    # Get scanner info (simplified - in real implementation you'd track which scanner)
                    scanner_name = "Primary-Scanner"  # This would be determined by which scanner found it
                    
                    reading = BeaconReading(
                        beacon_name=beacon_name,
                        beacon_mac=device.address,
                        rssi=advertisement_data.rssi,
                        scanner_name=scanner_name,
                        scanner_adapter="hci0",  # Default adapter
                        timestamp=datetime.now(),
                        distance_estimate=self._estimate_distance(advertisement_data.rssi)
                    )
                    
                    self.beacon_readings.append(reading)
                    
                    if device.address not in found_beacons:
                        found_beacons.add(device.address)
                        print(f"  Found: {beacon_name} ({device.address}) - RSSI: {advertisement_data.rssi} dBm")
        
        try:
            # Start scanning
            scanner = BleakScanner(detection_callback)
            await scanner.start()
            
            self.running = True
            print("Scanning started... Walk around with your beacon!")
            print("Press Ctrl+C to stop early")
            
            # Scan for specified duration
            try:
                await asyncio.sleep(duration)
            except KeyboardInterrupt:
                print("\nScanning stopped by user")
            
            await scanner.stop()
            self.running = False
            
            elapsed = time.time() - start_time
            print(f"\nScanning completed in {elapsed:.1f} seconds")
            print(f"Found {len(found_beacons)} unique beacons")
            
        except Exception as e:
            print(f"Error during scanning: {e}")
            self.running = False
    
    def _is_beacon(self, device: BLEDevice, adv_data: AdvertisementData) -> bool:
        """Check if device is a beacon"""
        # Check for iBeacon
        if adv_data.manufacturer_data:
            for manufacturer_id, data in adv_data.manufacturer_data.items():
                if manufacturer_id == 0x004C:  # Apple
                    if len(data) >= 23:
                        return True
        
        # Check for Eddystone
        if adv_data.service_uuids:
            eddystone_uuids = [
                "0000feaa-0000-1000-8000-00805f9b34fb",  # Eddystone
                "0000feaa-0000-1000-8000-00805f9b34fb"
            ]
            if any(uuid in adv_data.service_uuids for uuid in eddystone_uuids):
                return True
        
        # Check for named beacons
        if device.name and any(keyword in device.name.lower() for keyword in ['beacon', 'ibeacon', 'eddystone']):
            return True
        
        return False
    
    def _estimate_distance(self, rssi: int) -> float:
        """Estimate distance based on RSSI (rough approximation)"""
        if rssi == 0:
            return -1.0
        
        # Free space path loss model (very rough)
        # This is just an approximation - real distance depends on many factors
        tx_power = -59  # Typical beacon TX power
        n = 2.0  # Path loss exponent
        
        ratio = (tx_power - rssi) / (10 * n)
        distance = 10 ** ratio
        
        return round(distance, 2)
    
    def analyze_readings(self):
        """Analyze beacon readings and provide statistics"""
        if not self.beacon_readings:
            print("No beacon readings to analyze")
            return
        
        print("\nBEACON READING ANALYSIS")
        print("=" * 40)
        
        # Group by beacon
        beacon_groups = {}
        for reading in self.beacon_readings:
            if reading.beacon_mac not in beacon_groups:
                beacon_groups[reading.beacon_mac] = []
            beacon_groups[reading.beacon_mac].append(reading)
        
        for beacon_mac, readings in beacon_groups.items():
            if not readings:
                continue
                
            beacon_name = readings[0].beacon_name
            rssi_values = [r.reading.rssi for r in readings]
            distances = [r.reading.distance_estimate for r in readings if r.reading.distance_estimate > 0]
            
            print(f"\nBeacon: {beacon_name} ({beacon_mac})")
            print(f"  Total readings: {len(readings)}")
            print(f"  RSSI range: {min(rssi_values)} to {max(rssi_values)} dBm")
            print(f"  Average RSSI: {sum(rssi_values)/len(rssi_values):.1f} dBm")
            
            if distances:
                print(f"  Distance range: {min(distances):.1f}m to {max(distances):.1f}m")
                print(f"  Average distance: {sum(distances)/len(distances):.1f}m")
            
            # Show reading timeline
            print("  Recent readings:")
            for reading in readings[-5:]:  # Last 5 readings
                print(f"    {reading.timestamp.strftime('%H:%M:%S')} - RSSI: {reading.rssi} dBm")
    
    def save_results(self, filename: str = None):
        """Save test results to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ble_scanner_test_{timestamp}.json"
        
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "scanners": {addr: asdict(scanner) for addr, scanner in self.scanners.items()},
            "beacon_readings": [asdict(reading) for reading in self.beacon_readings],
            "summary": {
                "total_scanners": len(self.scanners),
                "total_readings": len(self.beacon_readings),
                "unique_beacons": len(set(r.beacon_mac for r in self.beacon_readings))
            }
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nResults saved to: {filename}")
        except Exception as e:
            print(f"Error saving results: {e}")
    
    async def range_test(self, beacon_name: str, test_duration: int = 60):
        """Perform a range test for a specific beacon"""
        print(f"\nRANGE TEST FOR: {beacon_name}")
        print("=" * 50)
        print("Instructions:")
        print("1. Start at the scanner location")
        print("2. Walk away slowly while holding the beacon")
        print("3. Note when the beacon stops being detected")
        print("4. Return to scanner and repeat")
        print("5. Press Ctrl+C when done testing")
        print("\nStarting in 5 seconds...")
        
        await asyncio.sleep(5)
        
        self.beacon_readings.clear()
        await self.scan_for_beacons(test_duration, beacon_name)
        self.analyze_readings()
        self.save_results(f"range_test_{beacon_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

async def main():
    parser = argparse.ArgumentParser(description="BLE Scanner Range Tester")
    parser.add_argument("--discover", action="store_true", help="Discover available BLE scanners")
    parser.add_argument("--scan", type=int, default=30, help="Scan duration in seconds")
    parser.add_argument("--beacon", type=str, help="Target specific beacon name")
    parser.add_argument("--range-test", type=str, help="Perform range test for specific beacon")
    parser.add_argument("--duration", type=int, default=60, help="Range test duration in seconds")
    
    args = parser.parse_args()
    
    tester = BLEScannerTester()
    
    try:
        if args.discover:
            await tester.discover_scanners()
        
        if args.range_test:
            await tester.range_test(args.range_test, args.duration)
        elif args.scan:
            await tester.scan_for_beacons(args.scan, args.beacon)
            tester.analyze_readings()
            tester.save_results()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        tester.running = False

if __name__ == "__main__":
    print("BLE SCANNER RANGE TESTER")
    print("========================")
    print("This script helps test BLE scanner range and performance")
    print()
    
    # Run the main function
    asyncio.run(main())
