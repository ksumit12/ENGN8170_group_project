#!/usr/bin/env python3
"""
Simple script to get the Raspberry Pi's IP address for network access
"""
import socket
import subprocess
import sys

def get_local_ip():
    """Get the local IP address of this machine"""
    try:
        # Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception as e:
        print(f"Error getting IP: {e}")
        return None

def get_network_info():
    """Get network information using ip command"""
    try:
        result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], 
                              capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if 'src' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'src':
                        return parts[i + 1]
    except Exception as e:
        print(f"Error getting network info: {e}")
    return None

def main():
    print("RASPBERRY PI NETWORK CONFIGURATION")
    print("=" * 40)
    
    # Try multiple methods to get IP
    ip = get_local_ip()
    if not ip:
        ip = get_network_info()
    
    if ip:
        print(f"Raspberry Pi IP Address: {ip}")
        print()
        print("WEB ACCESS URLs:")
        print(f"  Main Dashboard: http://{ip}:5000")
        print(f"  API Server:     http://{ip}:8000")
        print()
        print("INSTRUCTIONS:")
        print("1. Run: python3 boat_tracking_system.py --api-port 8000 --web-port 5000")
        print("2. Access from any device on the same network using the URLs above")
        print("3. Make sure your firewall allows connections on ports 5000 and 8000")
    else:
        print("Could not determine IP address automatically")
        print("Try running: ip addr show | grep inet")

if __name__ == "__main__":
    main()
