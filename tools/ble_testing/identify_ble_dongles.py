#!/usr/bin/env python3
"""
Identify BLE Dongles/Adapters on Raspberry Pi
"""

import subprocess
import sys
import re
from typing import List, Dict

def get_bluetooth_adapters() -> List[Dict[str, str]]:
    """Get list of Bluetooth adapters using hciconfig"""
    adapters = []
    
    try:
        result = subprocess.run(['hciconfig'], capture_output=True, text=True, check=True)
        lines = result.stdout.split('\n')
        
        current_adapter = None
        for line in lines:
            # Look for adapter names (hci0, hci1, etc.)
            adapter_match = re.match(r'^(\w+):', line)
            if adapter_match:
                current_adapter = adapter_match.group(1)
                continue
            
            # Look for status information
            if current_adapter and 'UP' in line:
                # Extract MAC address if present
                mac_match = re.search(r'([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})', line)
                mac_address = mac_match.group(1) if mac_match else "Unknown"
                
                adapters.append({
                    'name': current_adapter,
                    'mac': mac_address,
                    'status': 'UP' if 'UP' in line else 'DOWN'
                })
    
    except subprocess.CalledProcessError as e:
        print(f"Error running hciconfig: {e}")
    except FileNotFoundError:
        print("hciconfig not found. Trying alternative method...")
        return get_bluetooth_adapters_alternative()
    
    return adapters

def get_bluetooth_adapters_alternative() -> List[Dict[str, str]]:
    """Alternative method to get Bluetooth adapters"""
    adapters = []
    
    try:
        # Try using lsusb to find Bluetooth dongles
        result = subprocess.run(['lsusb'], capture_output=True, text=True, check=True)
        lines = result.stdout.split('\n')
        
        bluetooth_keywords = ['bluetooth', 'ble', 'csr', 'broadcom', 'realtek', 'intel']
        
        for line in lines:
            if any(keyword in line.lower() for keyword in bluetooth_keywords):
                # Extract device info
                parts = line.split()
                if len(parts) >= 6:
                    bus = parts[1]
                    device = parts[3].rstrip(':')
                    description = ' '.join(parts[6:])
                    
                    adapters.append({
                        'name': f"USB-{bus}-{device}",
                        'mac': "USB Device",
                        'status': 'Connected',
                        'description': description
                    })
    
    except subprocess.CalledProcessError as e:
        print(f"Error running lsusb: {e}")
    except FileNotFoundError:
        print("lsusb not found")
    
    return adapters

def get_usb_bluetooth_devices() -> List[Dict[str, str]]:
    """Get USB Bluetooth devices"""
    devices = []
    
    try:
        result = subprocess.run(['lsusb', '-v'], capture_output=True, text=True, check=True)
        lines = result.stdout.split('\n')
        
        current_device = {}
        for line in lines:
            if line.startswith('Bus '):
                # New device
                if current_device:
                    devices.append(current_device)
                current_device = {'bus': line.strip()}
            elif 'idVendor' in line:
                current_device['vendor_id'] = line.split()[1]
            elif 'idProduct' in line:
                current_device['product_id'] = line.split()[1]
            elif 'iProduct' in line:
                current_device['product'] = line.split(' ', 1)[1].strip('"')
            elif 'iManufacturer' in line:
                current_device['manufacturer'] = line.split(' ', 1)[1].strip('"')
    
    except subprocess.CalledProcessError as e:
        print(f"Error running lsusb -v: {e}")
    except FileNotFoundError:
        print("lsusb not found")
    
    return devices

def main():
    print("IDENTIFYING BLE DONGLES/ADAPTERS")
    print("=" * 40)
    
    # Get Bluetooth adapters
    print("\n1. BLUETOOTH ADAPTERS (hciconfig):")
    print("-" * 35)
    adapters = get_bluetooth_adapters()
    
    if adapters:
        for i, adapter in enumerate(adapters, 1):
            print(f"  Adapter {i}: {adapter['name']}")
            print(f"    MAC: {adapter['mac']}")
            print(f"    Status: {adapter['status']}")
            if 'description' in adapter:
                print(f"    Description: {adapter['description']}")
            print()
    else:
        print("  No Bluetooth adapters found")
    
    # Get USB Bluetooth devices
    print("\n2. USB BLUETOOTH DEVICES (lsusb):")
    print("-" * 35)
    usb_devices = get_usb_bluetooth_devices()
    
    if usb_devices:
        for i, device in enumerate(usb_devices, 1):
            print(f"  Device {i}: {device.get('bus', 'Unknown')}")
            if 'manufacturer' in device:
                print(f"    Manufacturer: {device['manufacturer']}")
            if 'product' in device:
                print(f"    Product: {device['product']}")
            if 'vendor_id' in device:
                print(f"    Vendor ID: {device['vendor_id']}")
            if 'product_id' in device:
                print(f"    Product ID: {device['product_id']}")
            print()
    else:
        print("  No USB Bluetooth devices found")
    
    # Summary
    print("\nSUMMARY:")
    print("-" * 10)
    print(f"Total Bluetooth adapters: {len(adapters)}")
    print(f"Total USB Bluetooth devices: {len(usb_devices)}")
    
    if adapters:
        print("\nTo test these adapters, use:")
        for adapter in adapters:
            if adapter['status'] == 'UP':
                print(f"  python3 scanner_range_test.py --adapter {adapter['name']} --duration 30")
    
    print("\nTo test all adapters at once:")
    print("  python3 scanner_range_test.py --test-all --duration 30")

if __name__ == "__main__":
    main()
