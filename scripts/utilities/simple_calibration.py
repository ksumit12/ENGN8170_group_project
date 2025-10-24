#!/usr/bin/env python3
"""
Simplified Calibration Script for Door Left-Right System
This script provides a streamlined calibration process that's easier to use in real-world deployment.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database_models import DatabaseManager
from app.logging_config import get_logger

logger = get_logger()

class SimpleCalibrator:
    def __init__(self, db_path: str = "data/boat_tracking.db"):
        self.db = DatabaseManager(db_path)
        self.samples = []
        self.calibration_data = {}
        
    def collect_static_samples(self, beacon_mac: str, duration: int = 30) -> Dict[str, List[float]]:
        """Collect static RSSI samples at different positions."""
        print(f"\n=== STATIC CALIBRATION ===")
        print(f"Beacon MAC: {beacon_mac}")
        print(f"Duration: {duration} seconds per position")
        
        positions = {
            "center": "Place beacon at doorway center",
            "left": "Place beacon near LEFT scanner (hci0)",
            "right": "Place beacon near RIGHT scanner (hci1)"
        }
        
        results = {}
        
        for pos_name, instruction in positions.items():
            print(f"\n--- {pos_name.upper()} POSITION ---")
            print(f"Instruction: {instruction}")
            input("Press Enter when ready to start sampling...")
            
            print(f"Collecting samples for {duration} seconds...")
            samples = self._collect_samples_for_position(beacon_mac, duration)
            
            if samples:
                left_rssi = [s[1] for s in samples if 'left' in s[0].lower()]
                right_rssi = [s[1] for s in samples if 'right' in s[0].lower()]
                
                results[pos_name] = {
                    "left_rssi": left_rssi,
                    "right_rssi": right_rssi,
                    "left_avg": sum(left_rssi) / len(left_rssi) if left_rssi else 0,
                    "right_avg": sum(right_rssi) / len(right_rssi) if right_rssi else 0,
                    "sample_count": len(samples)
                }
                
                print(f"Collected {len(samples)} samples")
                print(f"Left scanner avg: {results[pos_name]['left_avg']:.1f} dBm")
                print(f"Right scanner avg: {results[pos_name]['right_avg']:.1f} dBm")
            else:
                print("No samples collected!")
                
        return results
    
    def collect_movement_samples(self, beacon_mac: str, runs: int = 3) -> Dict[str, List[Dict]]:
        """Collect movement samples for ENTER and LEAVE directions."""
        print(f"\n=== MOVEMENT CALIBRATION ===")
        print(f"Beacon MAC: {beacon_mac}")
        print(f"Runs per direction: {runs}")
        
        results = {"enter": [], "leave": []}
        
        for direction in ["enter", "leave"]:
            print(f"\n--- {direction.upper()} MOVEMENT ---")
            
            if direction == "enter":
                print("Walk from WATER side to SHED side")
                print("Expected pattern: RIGHT scanner sees beacon first, then LEFT scanner")
            else:
                print("Walk from SHED side to WATER side")
                print("Expected pattern: LEFT scanner sees beacon first, then RIGHT scanner")
            
            for run in range(runs):
                print(f"\nRun {run + 1}/{runs}")
                input("Press Enter when ready to start movement...")
                
                print("Moving... (walk at normal pace)")
                samples = self._collect_samples_for_position(beacon_mac, 10)
                
                if samples:
                    # Analyze movement pattern
                    analysis = self._analyze_movement(samples, direction)
                    results[direction].append(analysis)
                    print(f"Pattern detected: {analysis.get('pattern', 'UNKNOWN')}")
                else:
                    print("No samples collected!")
                    
        return results
    
    def _collect_samples_for_position(self, beacon_mac: str, duration: int) -> List[Tuple[str, float, str]]:
        """Collect RSSI samples from the database."""
        samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    # Get recent detections for this beacon
                    cursor.execute("""
                        SELECT scanner_id, rssi, timestamp 
                        FROM detections 
                        WHERE beacon_id = ? 
                        AND timestamp > datetime('now', '-5 seconds')
                        ORDER BY timestamp DESC
                        LIMIT 10
                    """, (beacon_mac,))
                    
                    rows = cursor.fetchall()
                    for row in rows:
                        scanner_id, rssi, timestamp = row
                        samples.append((scanner_id, rssi, timestamp))
                        
            except Exception as e:
                logger.error(f"Error collecting samples: {e}")
                
            time.sleep(0.5)
            
        return samples
    
    def _analyze_movement(self, samples: List[Tuple[str, float, str]], expected_direction: str) -> Dict:
        """Analyze movement samples to determine pattern."""
        if not samples:
            return {"pattern": "NO_DATA"}
            
        # Separate by scanner
        left_samples = [s for s in samples if 'left' in s[0].lower()]
        right_samples = [s for s in samples if 'right' in s[0].lower()]
        
        if not left_samples or not right_samples:
            return {"pattern": "INCOMPLETE"}
            
        # Find first detection from each scanner
        left_first = min(left_samples, key=lambda x: x[2])[2]
        right_first = min(right_samples, key=lambda x: x[2])[2]
        
        # Determine pattern
        if left_first < right_first:
            pattern = "LEFT_FIRST"
        else:
            pattern = "RIGHT_FIRST"
            
        # Check if pattern matches expected direction
        correct = False
        if expected_direction == "enter" and pattern == "RIGHT_FIRST":
            correct = True
        elif expected_direction == "leave" and pattern == "LEFT_FIRST":
            correct = True
            
        return {
            "pattern": pattern,
            "expected": expected_direction,
            "correct": correct,
            "left_samples": len(left_samples),
            "right_samples": len(right_samples)
        }
    
    def calculate_calibration(self, static_data: Dict, movement_data: Dict) -> Dict:
        """Calculate calibration parameters from collected data."""
        print(f"\n=== CALCULATING CALIBRATION ===")
        
        calibration = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rssi_offsets": {},
            "thresholds": {},
            "recommendations": []
        }
        
        # Calculate RSSI offsets
        if "center" in static_data:
            center_data = static_data["center"]
            left_center = center_data["left_avg"]
            right_center = center_data["right_avg"]
            
            # Calculate bias to equalize scanners at center
            bias = (left_center - right_center) / 2
            calibration["rssi_offsets"]["gate-left"] = -bias
            calibration["rssi_offsets"]["gate-right"] = bias
            
            print(f"Center bias calculated: {bias:.2f} dB")
            print(f"Left scanner offset: {calibration['rssi_offsets']['gate-left']:.2f} dB")
            print(f"Right scanner offset: {calibration['rssi_offsets']['gate-right']:.2f} dB")
        
        # Calculate thresholds
        if "left" in static_data and "right" in static_data:
            left_data = static_data["left"]
            right_data = static_data["right"]
            
            # Use stronger signal as threshold
            left_threshold = left_data["left_avg"] - 10  # 10 dB below peak
            right_threshold = right_data["right_avg"] - 10
            
            calibration["thresholds"] = {
                "strong_left": left_threshold,
                "strong_right": right_threshold,
                "active_dbm": min(left_threshold, right_threshold),
                "energy_dbm": min(left_threshold, right_threshold) + 5
            }
            
            print(f"Thresholds calculated:")
            print(f"  Active threshold: {calibration['thresholds']['active_dbm']:.1f} dBm")
            print(f"  Energy threshold: {calibration['thresholds']['energy_dbm']:.1f} dBm")
        
        # Analyze movement patterns
        enter_correct = sum(1 for run in movement_data.get("enter", []) if run.get("correct", False))
        leave_correct = sum(1 for run in movement_data.get("leave", []) if run.get("correct", False))
        
        total_enter = len(movement_data.get("enter", []))
        total_leave = len(movement_data.get("leave", []))
        
        calibration["movement_analysis"] = {
            "enter_accuracy": enter_correct / total_enter if total_enter > 0 else 0,
            "leave_accuracy": leave_correct / total_leave if total_leave > 0 else 0,
            "total_runs": total_enter + total_leave
        }
        
        print(f"Movement analysis:")
        print(f"  ENTER accuracy: {calibration['movement_analysis']['enter_accuracy']:.1%}")
        print(f"  LEAVE accuracy: {calibration['movement_analysis']['leave_accuracy']:.1%}")
        
        # Generate recommendations
        if calibration["movement_analysis"]["enter_accuracy"] < 0.8:
            calibration["recommendations"].append("ENTER pattern needs improvement - check RIGHT scanner positioning")
        if calibration["movement_analysis"]["leave_accuracy"] < 0.8:
            calibration["recommendations"].append("LEAVE pattern needs improvement - check LEFT scanner positioning")
            
        return calibration
    
    def save_calibration(self, calibration: Dict, output_path: str = None):
        """Save calibration data to file."""
        if not output_path:
            output_path = "calibration/sessions/latest/door_lr_calib.json"
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(calibration, f, indent=2)
            
        print(f"\nCalibration saved to: {output_path}")
        
        # Also save a backup with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"calibration/sessions/backup/door_lr_calib_{timestamp}.json"
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        with open(backup_path, 'w') as f:
            json.dump(calibration, f, indent=2)
            
        print(f"Backup saved to: {backup_path}")

def main():
    parser = argparse.ArgumentParser(description="Simple Calibration for Door Left-Right System")
    parser.add_argument("--beacon-mac", required=True, help="MAC address of beacon to calibrate")
    parser.add_argument("--duration", type=int, default=30, help="Duration for static sampling (seconds)")
    parser.add_argument("--runs", type=int, default=3, help="Number of movement runs per direction")
    parser.add_argument("--output", help="Output file path for calibration data")
    
    args = parser.parse_args()
    
    calibrator = SimpleCalibrator()
    
    print("=== SIMPLE CALIBRATION FOR DOOR LEFT-RIGHT SYSTEM ===")
    print("This script will help you calibrate the system for reliable direction detection.")
    print("\nRequirements:")
    print("- Two BLE scanners connected (hci0 = left, hci1 = right)")
    print("- Beacon with MAC address:", args.beacon_mac)
    print("- Clear path through doorway")
    print("- About 10-15 minutes of time")
    
    input("\nPress Enter to start calibration...")
    
    try:
        # Step 1: Static calibration
        static_data = calibrator.collect_static_samples(args.beacon_mac, args.duration)
        
        # Step 2: Movement calibration
        movement_data = calibrator.collect_movement_samples(args.beacon_mac, args.runs)
        
        # Step 3: Calculate calibration
        calibration = calibrator.calculate_calibration(static_data, movement_data)
        
        # Step 4: Save calibration
        calibrator.save_calibration(calibration, args.output)
        
        print("\n=== CALIBRATION COMPLETE ===")
        print("The system will now use these calibration parameters for improved detection.")
        print("Restart the boat tracking system to apply the new calibration.")
        
    except KeyboardInterrupt:
        print("\nCalibration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nCalibration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
