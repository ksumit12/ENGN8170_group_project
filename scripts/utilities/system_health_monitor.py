#!/usr/bin/env python3
"""
System Health Monitor for Boat Tracking System
Monitors system health and provides diagnostics for troubleshooting deployment issues.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database_models import DatabaseManager
from app.logging_config import get_logger

logger = get_logger()

class SystemHealthMonitor:
    def __init__(self, db_path: str = "data/boat_tracking.db"):
        self.db = DatabaseManager(db_path)
        self.health_data = {}
        
    def check_bluetooth_adapters(self) -> Dict:
        """Check BLE adapter status and availability."""
        print("Checking Bluetooth adapters...")
        
        adapters = {}
        
        try:
            # Check hciconfig output
            result = subprocess.run(['hciconfig'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                current_adapter = None
                
                for line in lines:
                    if 'hci' in line and ':' in line:
                        # Extract adapter name
                        adapter_name = line.split(':')[0].strip()
                        current_adapter = adapter_name
                        adapters[adapter_name] = {
                            'name': adapter_name,
                            'status': 'UNKNOWN',
                            'mac': 'UNKNOWN',
                            'features': []
                        }
                    elif current_adapter and 'UP' in line:
                        adapters[current_adapter]['status'] = 'UP'
                    elif current_adapter and 'DOWN' in line:
                        adapters[current_adapter]['status'] = 'DOWN'
                    elif current_adapter and 'BD Address:' in line:
                        mac = line.split('BD Address:')[1].strip().split()[0]
                        adapters[current_adapter]['mac'] = mac
                        
        except subprocess.TimeoutExpired:
            print("  Warning: hciconfig command timed out")
        except FileNotFoundError:
            print("  Warning: hciconfig command not found")
        except Exception as e:
            print(f"  Error checking adapters: {e}")
            
        # Check USB devices
        try:
            result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'TP-Link' in line or 'Bluetooth' in line:
                        print(f"  Found USB device: {line.strip()}")
                        
        except Exception as e:
            print(f"  Error checking USB devices: {e}")
            
        return adapters
    
    def check_system_resources(self) -> Dict:
        """Check system resource usage."""
        print("Checking system resources...")
        
        resources = {}
        
        try:
            # Check CPU usage
            result = subprocess.run(['top', '-bn1'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'load average:' in line:
                        load_avg = line.split('load average:')[1].strip().split(',')[0].strip()
                        resources['load_average'] = load_avg
                        
        except Exception as e:
            print(f"  Error checking CPU: {e}")
            
        try:
            # Check memory usage
            result = subprocess.run(['free', '-m'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if line.startswith('Mem:'):
                        parts = line.split()
                        total = int(parts[1])
                        used = int(parts[2])
                        available = int(parts[6]) if len(parts) > 6 else total - used
                        resources['memory'] = {
                            'total_mb': total,
                            'used_mb': used,
                            'available_mb': available,
                            'usage_percent': (used / total) * 100
                        }
                        
        except Exception as e:
            print(f"  Error checking memory: {e}")
            
        try:
            # Check disk usage
            result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if line.startswith('/dev/'):
                        parts = line.split()
                        if len(parts) >= 5:
                            resources['disk'] = {
                                'total': parts[1],
                                'used': parts[2],
                                'available': parts[3],
                                'usage_percent': parts[4]
                            }
                            
        except Exception as e:
            print(f"  Error checking disk: {e}")
            
        return resources
    
    def check_database_health(self) -> Dict:
        """Check database health and performance."""
        print("Checking database health...")
        
        db_health = {}
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check table sizes
                tables = ['boats', 'beacons', 'boat_beacon_assignments', 'detection_states', 'shed_events', 'boat_trips']
                table_sizes = {}
                
                for table in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        table_sizes[table] = count
                    except Exception as e:
                        table_sizes[table] = f"Error: {e}"
                        
                db_health['table_sizes'] = table_sizes
                
                # Check recent activity
                try:
                    cursor.execute("SELECT COUNT(*) FROM shed_events WHERE ts_utc > datetime('now', '-1 hour')")
                    recent_events = cursor.fetchone()[0]
                    db_health['recent_events_1h'] = recent_events
                except Exception:
                    db_health['recent_events_1h'] = 0
                    
                # Check database file size
                if os.path.exists(self.db.db_path):
                    db_size = os.path.getsize(self.db.db_path)
                    db_health['file_size_mb'] = db_size / (1024 * 1024)
                    
        except Exception as e:
            db_health['error'] = str(e)
            
        return db_health
    
    def check_network_connectivity(self) -> Dict:
        """Check network connectivity and performance."""
        print("Checking network connectivity...")
        
        network = {}
        
        try:
            # Check WiFi connection
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'IEEE 802.11' in line:
                        if 'ESSID:' in line:
                            essid = line.split('ESSID:')[1].strip().strip('"')
                            network['wifi_essid'] = essid
                        if 'Signal level=' in line:
                            signal = line.split('Signal level=')[1].split()[0]
                            network['wifi_signal'] = signal
                            
        except Exception as e:
            print(f"  Error checking WiFi: {e}")
            
        try:
            # Check internet connectivity
            result = subprocess.run(['ping', '-c', '3', '8.8.8.8'], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'packet loss' in line:
                        network['internet_connectivity'] = 'OK'
                        break
            else:
                network['internet_connectivity'] = 'FAILED'
                
        except Exception as e:
            network['internet_connectivity'] = f"Error: {e}"
            
        return network
    
    def check_process_status(self) -> Dict:
        """Check if system processes are running."""
        print("Checking process status...")
        
        processes = {}
        
        # Check for Python processes
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                
                # Look for boat tracking processes
                boat_processes = []
                scanner_processes = []
                
                for line in lines:
                    if 'python' in line.lower():
                        if 'boat_tracking_system.py' in line:
                            boat_processes.append(line.strip())
                        elif 'ble_scanner.py' in line or 'scanner_service.py' in line:
                            scanner_processes.append(line.strip())
                            
                processes['boat_tracking'] = boat_processes
                processes['scanners'] = scanner_processes
                
        except Exception as e:
            processes['error'] = str(e)
            
        return processes
    
    def generate_health_report(self) -> Dict:
        """Generate comprehensive health report."""
        print("=== SYSTEM HEALTH MONITOR ===")
        print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print()
        
        health_report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'bluetooth_adapters': self.check_bluetooth_adapters(),
            'system_resources': self.check_system_resources(),
            'database_health': self.check_database_health(),
            'network_connectivity': self.check_network_connectivity(),
            'process_status': self.check_process_status()
        }
        
        # Generate summary
        issues = []
        warnings = []
        
        # Check for issues
        if not health_report['bluetooth_adapters']:
            issues.append("No Bluetooth adapters found")
            
        if health_report['system_resources'].get('memory', {}).get('usage_percent', 0) > 90:
            warnings.append("High memory usage")
            
        if health_report['database_health'].get('recent_events_1h', 0) == 0:
            warnings.append("No recent events in database")
            
        if health_report['network_connectivity'].get('internet_connectivity') != 'OK':
            warnings.append("Internet connectivity issues")
            
        if not health_report['process_status'].get('boat_tracking'):
            issues.append("Boat tracking system not running")
            
        if not health_report['process_status'].get('scanners'):
            issues.append("BLE scanners not running")
            
        health_report['summary'] = {
            'status': 'HEALTHY' if not issues else 'ISSUES_FOUND',
            'issues': issues,
            'warnings': warnings
        }
        
        return health_report
    
    def print_health_report(self, report: Dict):
        """Print formatted health report."""
        print("\n=== HEALTH REPORT SUMMARY ===")
        print(f"Status: {report['summary']['status']}")
        
        if report['summary']['issues']:
            print("\nISSUES:")
            for issue in report['summary']['issues']:
                print(f"  ❌ {issue}")
                
        if report['summary']['warnings']:
            print("\nWARNINGS:")
            for warning in report['summary']['warnings']:
                print(f"  ⚠️  {warning}")
                
        if not report['summary']['issues'] and not report['summary']['warnings']:
            print("  ✅ All systems healthy")
            
        print(f"\nBluetooth Adapters: {len(report['bluetooth_adapters'])} found")
        print(f"Database Events (1h): {report['database_health'].get('recent_events_1h', 0)}")
        print(f"Boat Tracking Processes: {len(report['process_status'].get('boat_tracking', []))}")
        print(f"Scanner Processes: {len(report['process_status'].get('scanners', []))}")
        
    def save_health_report(self, report: Dict, output_path: str = None):
        """Save health report to file."""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"logs/health_report_{timestamp}.json"
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
            
        print(f"\nHealth report saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="System Health Monitor for Boat Tracking System")
    parser.add_argument("--db-path", default="data/boat_tracking.db", help="Database file path")
    parser.add_argument("--output", help="Output file for health report")
    parser.add_argument("--watch", action="store_true", help="Continuously monitor system health")
    parser.add_argument("--interval", type=int, default=60, help="Monitoring interval in seconds")
    
    args = parser.parse_args()
    
    monitor = SystemHealthMonitor(args.db_path)
    
    if args.watch:
        print(f"Starting continuous monitoring (interval: {args.interval}s)")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                report = monitor.generate_health_report()
                monitor.print_health_report(report)
                
                if args.output:
                    monitor.save_health_report(report, args.output)
                    
                print(f"\nNext check in {args.interval} seconds...")
                time.sleep(args.interval)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
    else:
        report = monitor.generate_health_report()
        monitor.print_health_report(report)
        
        if args.output:
            monitor.save_health_report(report, args.output)

if __name__ == "__main__":
    main()
