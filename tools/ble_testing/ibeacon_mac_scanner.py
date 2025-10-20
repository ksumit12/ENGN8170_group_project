#!/usr/bin/env python3
"""
iBeacon MAC Scanner - Scan for specific MAC address and show iBeacon frames
"""

import argparse
import time
import struct
from bluepy.btle import Scanner, DefaultDelegate

class iBeaconDelegate(DefaultDelegate):
    def __init__(self, target_mac=None):
        DefaultDelegate.__init__(self)
        self.target_mac = target_mac.upper() if target_mac else None
        self.detection_count = 0
        
    def handleDiscovery(self, dev, isNewDev, isNewData):
        if self.target_mac and dev.addr.upper() != self.target_mac:
            return
            
        self.detection_count += 1
        print(f"\n[{self.detection_count}] Device: {dev.addr}")
        print(f"    RSSI: {dev.rssi} dBm")
        print(f"    Name: {dev.getValueText(9) if dev.getValueText(9) else 'N/A'}")
        
        # Check for iBeacon data in manufacturer data
        for (adtype, desc, value) in dev.getScanData():
            if adtype == 255:  # Manufacturer data
                if len(value) >= 25:  # iBeacon minimum length
                    try:
                        # Parse iBeacon data
                        uuid = value[2:18].hex()
                        major = struct.unpack('>H', value[18:20])[0]
                        minor = struct.unpack('>H', value[20:22])[0]
                        tx_power = struct.unpack('b', value[22:23])[0]
                        
                        print(f"    iBeacon UUID: {uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}")
                        print(f"    Major: {major}, Minor: {minor}")
                        print(f"    TX Power: {tx_power} dBm")
                        print(f"    Raw Data: {value.hex()}")
                    except Exception as e:
                        print(f"    Raw Manufacturer Data: {value.hex()}")
                        print(f"    Parse Error: {e}")
                else:
                    print(f"    Raw Manufacturer Data: {value.hex()}")
            else:
                print(f"    {desc}: {value}")

def main():
    parser = argparse.ArgumentParser(description='Scan for specific MAC address and show iBeacon frames')
    parser.add_argument('--mac', required=True, help='Target MAC address to scan for')
    parser.add_argument('--adapter', default='hci0', help='BLE adapter to use (default: hci0)')
    parser.add_argument('--duration', type=int, default=30, help='Scan duration in seconds (default: 30)')
    
    args = parser.parse_args()
    
    print(f"iBeacon MAC Scanner")
    print(f"==================")
    print(f"Target MAC: {args.mac}")
    print(f"Adapter: {args.adapter}")
    print(f"Duration: {args.duration} seconds")
    print(f"Press Ctrl+C to stop early\n")
    
    try:
        scanner = Scanner(args.adapter).withDelegate(iBeaconDelegate(args.mac))
        scanner.start()
        
        start_time = time.time()
        while time.time() - start_time < args.duration:
            scanner.process(1)
            
        scanner.stop()
        print(f"\nScan completed after {args.duration} seconds")
        
    except KeyboardInterrupt:
        scanner.stop()
        print(f"\nScan interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure:")
        print("1. The adapter exists: sudo hciconfig")
        print("2. The adapter is up: sudo hciconfig hci0 up")
        print("3. You have permissions: sudo python3 ...")

if __name__ == "__main__":
    main()
