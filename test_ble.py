#!/usr/bin/env python3
"""
Simple BLE Beacon Scanner - Terminal Display Only
Scans for iBeacon and Eddystone beacons and displays all metadata in terminal.
"""

import asyncio
import time
import logging
from datetime import datetime
from bleak import BleakScanner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Beacon protocol constants
APPLE_CID = 0x004C  # Apple Company ID for iBeacon
EDDYSTONE_UUID = "0000feaa-0000-1000-8000-00805f9b34fb"

# Eddystone frame types
EDDYSTONE_UID = 0x00
EDDYSTONE_URL = 0x10
EDDYSTONE_TLM = 0x20
EDDYSTONE_EID = 0x30

# Eddystone URL decoding
URL_SCHEMES = {
    0x00: "http://www.",
    0x01: "https://www.",
    0x02: "http://",
    0x03: "https://",
}

URL_ENCODINGS = {
    0x00: ".com/", 0x01: ".org/", 0x02: ".edu/", 0x03: ".net/",
    0x04: ".info/", 0x05: ".biz/", 0x06: ".gov/",
    0x07: ".com", 0x08: ".org", 0x09: ".edu", 0x0a: ".net",
    0x0b: ".info", 0x0c: ".biz", 0x0d: ".gov",
}

class BeaconScanner:
    def __init__(self, rssi_threshold=-80, debounce_seconds=2):
        self.rssi_threshold = rssi_threshold
        self.debounce_seconds = debounce_seconds
        self.last_seen = {}  # Track last seen time for each beacon
        self.running = False

    def format_uuid(self, uuid_bytes):
        """Format 16 bytes as UUID string."""
        hex_string = uuid_bytes.hex()
        return f"{hex_string[0:8]}-{hex_string[8:12]}-{hex_string[12:16]}-{hex_string[16:20]}-{hex_string[20:32]}"

    def parse_ibeacon(self, payload):
        """Parse iBeacon data from manufacturer data."""
        if len(payload) < 23:
            return None
        if payload[0] != 0x02 or payload[1] != 0x15:
            return None
        
        uuid_bytes = payload[2:18]
        major = int.from_bytes(payload[18:20], "big")
        minor = int.from_bytes(payload[20:22], "big")
        tx_power = int.from_bytes(payload[22:23], "big", signed=True)
        
        uuid_str = self.format_uuid(uuid_bytes)
        
        return {
            "type": "iBeacon",
            "uuid": uuid_str,
            "major": major,
            "minor": minor,
            "tx_power": tx_power,
            "identifier": f"{uuid_str}:{major}:{minor}"
        }

    def parse_eddystone_uid(self, service_data):
        """Parse Eddystone-UID frame."""
        if len(service_data) < 18 or service_data[0] != EDDYSTONE_UID:
            return None
        
        tx_power = int.from_bytes(service_data[1:2], "big", signed=True)
        namespace = service_data[2:12].hex()
        instance = service_data[12:18].hex()
        
        return {
            "type": "Eddystone-UID",
            "tx_power": tx_power,
            "namespace": namespace,
            "instance": instance,
            "identifier": f"eddystone-uid:{namespace}:{instance}"
        }

    def parse_eddystone_url(self, service_data):
        """Parse Eddystone-URL frame."""
        if len(service_data) < 3 or service_data[0] != EDDYSTONE_URL:
            return None
        
        tx_power = int.from_bytes(service_data[1:2], "big", signed=True)
        scheme_code = service_data[2]
        url = URL_SCHEMES.get(scheme_code, f"[unknown scheme {scheme_code}]")
        
        for byte in service_data[3:]:
            if byte in URL_ENCODINGS:
                url += URL_ENCODINGS[byte]
            else:
                url += chr(byte) if 32 <= byte <= 126 else f"[0x{byte:02x}]"
        
        return {
            "type": "Eddystone-URL",
            "tx_power": tx_power,
            "url": url,
            "identifier": f"eddystone-url:{url}"
        }

    def parse_eddystone_tlm(self, service_data):
        """Parse Eddystone-TLM (telemetry) frame."""
        if len(service_data) < 14 or service_data[0] != EDDYSTONE_TLM:
            return None
        
        version = service_data[1]
        battery_voltage = int.from_bytes(service_data[2:4], "big")
        beacon_temperature = int.from_bytes(service_data[4:6], "big", signed=True) / 256.0
        adv_count = int.from_bytes(service_data[6:10], "big")
        sec_count = int.from_bytes(service_data[10:14], "big")
        
        return {
            "type": "Eddystone-TLM",
            "version": version,
            "battery_voltage": battery_voltage,
            "temperature": beacon_temperature,
            "adv_count": adv_count,
            "uptime_seconds": sec_count,
            "identifier": "eddystone-tlm"
        }

    def parse_eddystone(self, advertisement_data):
        """Parse Eddystone beacon data."""
        # Check if Eddystone UUID is present
        service_uuids = advertisement_data.service_uuids or []
        if EDDYSTONE_UUID not in [uuid.lower() for uuid in service_uuids]:
            return None
        
        # Get service data
        service_data = advertisement_data.service_data or {}
        eddystone_data = None
        
        for uuid, data in service_data.items():
            if uuid.lower() == EDDYSTONE_UUID:
                eddystone_data = bytes(data)
                break
        
        if not eddystone_data or len(eddystone_data) < 1:
            return None
        
        frame_type = eddystone_data[0]
        
        if frame_type == EDDYSTONE_UID:
            return self.parse_eddystone_uid(eddystone_data)
        elif frame_type == EDDYSTONE_URL:
            return self.parse_eddystone_url(eddystone_data)
        elif frame_type == EDDYSTONE_TLM:
            return self.parse_eddystone_tlm(eddystone_data)
        elif frame_type == EDDYSTONE_EID:
            return {
                "type": "Eddystone-EID",
                "ephemeral_id": eddystone_data[2:10].hex(),
                "identifier": f"eddystone-eid:{eddystone_data[2:10].hex()}"
            }
        else:
            return {
                "type": "Eddystone-Unknown",
                "frame_type": f"0x{frame_type:02x}",
                "data": eddystone_data.hex(),
                "identifier": f"eddystone-unknown:{frame_type}"
            }

    def should_display(self, beacon_id):
        """Check if beacon should be displayed based on debounce time."""
        now = time.time()
        if beacon_id not in self.last_seen:
            self.last_seen[beacon_id] = now
            return True
        
        if now - self.last_seen[beacon_id] >= self.debounce_seconds:
            self.last_seen[beacon_id] = now
            return True
        
        return False

    def display_beacon(self, beacon_data, device, rssi, timestamp):
        """Display beacon information in terminal."""
        print("\n" + "="*80)
        print(f"🔵 BEACON DETECTED: {beacon_data['type']}")
        print("="*80)
        print(f"📍 MAC Address:     {device.address}")
        print(f"📶 RSSI:            {rssi} dBm")
        print(f"📱 Device Name:     {getattr(device, 'name', 'Unknown') or 'Unknown'}")
        print(f"🕐 Timestamp:       {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print(f"🔑 Identifier:      {beacon_data.get('identifier', 'N/A')}")
        
        if beacon_data['type'] == 'iBeacon':
            print(f"🆔 UUID:            {beacon_data['uuid']}")
            print(f"🔢 Major:           {beacon_data['major']}")
            print(f"🔢 Minor:           {beacon_data['minor']}")
            print(f"⚡ TX Power:        {beacon_data['tx_power']} dBm")
        
        elif 'Eddystone' in beacon_data['type']:
            if beacon_data['type'] == 'Eddystone-UID':
                print(f"🌐 Namespace:       {beacon_data['namespace']}")
                print(f"🆔 Instance:        {beacon_data['instance']}")
                print(f"⚡ TX Power:        {beacon_data['tx_power']} dBm")
            
            elif beacon_data['type'] == 'Eddystone-URL':
                print(f"🔗 URL:             {beacon_data['url']}")
                print(f"⚡ TX Power:        {beacon_data['tx_power']} dBm")
            
            elif beacon_data['type'] == 'Eddystone-TLM':
                print(f"🔋 Battery:         {beacon_data['battery_voltage']} mV")
                print(f"🌡️  Temperature:     {beacon_data['temperature']:.1f}°C")
                print(f"📊 Adv Count:       {beacon_data['adv_count']}")
                print(f"⏰ Uptime:          {beacon_data['uptime_seconds']} seconds")
                print(f"📋 TLM Version:     {beacon_data['version']}")
            
            elif beacon_data['type'] == 'Eddystone-EID':
                print(f"🔐 Ephemeral ID:    {beacon_data['ephemeral_id']}")
            
            else:
                print(f"❓ Frame Type:      {beacon_data.get('frame_type', 'Unknown')}")
                print(f"📊 Raw Data:        {beacon_data.get('data', 'N/A')}")

        print("="*80)

    def detection_callback(self, device, advertisement_data):
        """Handle BLE device detection."""
        rssi = advertisement_data.rssi
        timestamp = time.time()
        
        # Filter by RSSI threshold
        if rssi < self.rssi_threshold:
            return
        
        beacon_data = None
        
        # Check for iBeacon
        manufacturer_data = advertisement_data.manufacturer_data or {}
        if APPLE_CID in manufacturer_data:
            beacon_data = self.parse_ibeacon(bytes(manufacturer_data[APPLE_CID]))
        
        # Check for Eddystone if not iBeacon
        if not beacon_data:
            beacon_data = self.parse_eddystone(advertisement_data)
        
        # Display if beacon found and not recently shown
        if beacon_data and self.should_display(beacon_data.get('identifier', device.address)):
            self.display_beacon(beacon_data, device, rssi, timestamp)

    async def start_scanning(self):
        """Start continuous BLE scanning."""
        print("🚀 Starting BLE Beacon Scanner")
        print(f"📊 RSSI Threshold: {self.rssi_threshold} dBm")
        print(f"⏱️  Debounce Time: {self.debounce_seconds} seconds")
        print("🔍 Scanning for iBeacon and Eddystone beacons...")
        print("⏹️  Press Ctrl+C to stop\n")
        
        scanner = BleakScanner(self.detection_callback)
        
        try:
            await scanner.start()
            self.running = True
            
            while self.running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping scanner...")
        except Exception as e:
            print(f"❌ Scanner error: {e}")
        finally:
            self.running = False
            await scanner.stop()
            print("✅ Scanner stopped")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="BLE Beacon Scanner - Terminal Display")
    parser.add_argument("--rssi-threshold", type=int, default=-80, 
                       help="RSSI threshold in dBm (default: -80)")
    parser.add_argument("--debounce", type=int, default=2,
                       help="Debounce time in seconds (default: 2)")
    
    args = parser.parse_args()
    
    scanner = BeaconScanner(
        rssi_threshold=args.rssi_threshold,
        debounce_seconds=args.debounce
    )
    
    try:
        asyncio.run(scanner.start_scanning())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()