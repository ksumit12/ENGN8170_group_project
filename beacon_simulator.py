#!/usr/bin/env python3
"""
Beacon Simulator - Simulates real beacon activity by periodically updating timestamps.
This is useful for testing and development when physical beacons are not available.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database_models import DatabaseManager
from datetime import datetime, timezone
import time
import random
import threading
import signal

class BeaconSimulator:
    def __init__(self, update_interval=30):
        """Initialize the beacon simulator.
        
        Args:
            update_interval: How often to update beacon timestamps (in seconds)
        """
        self.db = DatabaseManager('data/boat_tracking.db')
        self.update_interval = update_interval
        self.running = False
        self.thread = None
        
    def start(self):
        """Start the beacon simulator."""
        if self.running:
            print("Beacon simulator is already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.thread.start()
        print(f"Beacon simulator started (updating every {self.update_interval} seconds)")
        
    def stop(self):
        """Stop the beacon simulator."""
        self.running = False
        if self.thread:
            self.thread.join()
        print("Beacon simulator stopped")
        
    def _simulation_loop(self):
        """Main simulation loop."""
        while self.running:
            try:
                self._update_beacon_activity()
                time.sleep(self.update_interval)
            except Exception as e:
                print(f"Error in beacon simulation: {e}")
                time.sleep(5)  # Wait before retrying
                
    def _update_beacon_activity(self):
        """Update beacon activity for assigned beacons."""
        boats = self.db.get_all_boats()
        updated_count = 0
        
        for boat in boats:
            beacon = self.db.get_beacon_by_boat(boat.id)
            if beacon:
                # Simulate beacon detection with some randomness
                now = datetime.now(timezone.utc)
                
                # Add some randomness to make it more realistic
                # Sometimes skip updates to simulate intermittent detection
                if random.random() < 0.8:  # 80% chance of detection
                    rssi = random.randint(-80, -30)  # Random RSSI
                    
                    # Update beacon in database
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE beacons 
                            SET last_seen = ?, last_rssi = ?, updated_at = ?
                            WHERE id = ?
                        """, (now, rssi, now, beacon.id))
                        conn.commit()
                    
                    print(f"[{now.strftime('%H:%M:%S')}] Updated {boat.name}: RSSI = {rssi} dBm")
                    updated_count += 1
                    
        if updated_count > 0:
            print(f"Updated {updated_count} beacons")
            
    def simulate_outing(self, boat_name, duration_minutes=30):
        """Simulate a boat outing by updating timestamps over time."""
        boat = None
        for b in self.db.get_all_boats():
            if b.name.lower() == boat_name.lower():
                boat = b
                break
                
        if not boat:
            print(f"Boat '{boat_name}' not found")
            return
            
        beacon = self.db.get_beacon_by_boat(boat.id)
        if not beacon:
            print(f"No beacon assigned to boat '{boat_name}'")
            return
            
        print(f"Simulating outing for {boat.name} ({duration_minutes} minutes)...")
        
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Simulate going out (exit)
        print(f"[{start_time.strftime('%H:%M:%S')}] {boat.name} EXITED")
        
        # Simulate being out for the duration
        current_time = start_time
        while current_time < end_time and self.running:
            # Update beacon with decreasing signal strength (going away)
            rssi = random.randint(-90, -70)  # Weak signal when out
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE beacons 
                    SET last_seen = ?, last_rssi = ?, updated_at = ?
                    WHERE id = ?
                """, (current_time, rssi, current_time, beacon.id))
                conn.commit()
            
            time.sleep(10)  # Update every 10 seconds
            current_time = datetime.now(timezone.utc)
            
        # Simulate returning (enter)
        print(f"[{end_time.strftime('%H:%M:%S')}] {boat.name} ENTERED")
        
        # Update with strong signal (back in range)
        rssi = random.randint(-50, -30)  # Strong signal when back
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE beacons 
                SET last_seen = ?, last_rssi = ?, updated_at = ?
                WHERE id = ?
            """, (end_time, rssi, end_time, beacon.id))
            conn.commit()
            
        print(f"Outing simulation complete for {boat.name}")

def main():
    """Main function for command-line usage."""
    import argparse
    from datetime import timedelta
    
    parser = argparse.ArgumentParser(description='Beacon Simulator')
    parser.add_argument('--interval', type=int, default=30, 
                       help='Update interval in seconds (default: 30)')
    parser.add_argument('--simulate-outing', type=str, 
                       help='Simulate an outing for a specific boat')
    parser.add_argument('--duration', type=int, default=30,
                       help='Duration of simulated outing in minutes (default: 30)')
    
    args = parser.parse_args()
    
    simulator = BeaconSimulator(update_interval=args.interval)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nStopping beacon simulator...")
        simulator.stop()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    
    if args.simulate_outing:
        # Simulate a specific outing
        simulator.simulate_outing(args.simulate_outing, args.duration)
    else:
        # Start continuous simulation
        simulator.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            simulator.stop()

if __name__ == "__main__":
    main()

