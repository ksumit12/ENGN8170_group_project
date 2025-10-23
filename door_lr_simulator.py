#!/usr/bin/env python3
"""
Highly Realistic Door-LR Simulator
Based on calibration data and real-world Bluetooth behavior patterns.
"""

import random
import time
import requests
import json
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import math

from app.database_models import DatabaseManager, DetectionState


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def send_detection_to_api(scanner_id: str, beacon_mac: str, rssi: int, server_url: str = "http://127.0.0.1:8000", log=None, db=None, boat_id=None, expected_state=None):
    """Send a detection to the API server like a real BLE scanner would."""
    payload = {
        "scanner_id": scanner_id,
        "gate_id": "main_gate", 
        "adapter": "hci0",
        "observations": [{
            "protocol": "ibeacon",
            "beacon_stable_id": f"uuid:major:minor:{beacon_mac.replace(':', '')}",
            "mac": beacon_mac,
            "name": f"Beacon-{beacon_mac[-5:]}",
            "rssi": rssi,
            "ts": time.time(),
            "ibeacon_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "ibeacon_major": 1,
            "ibeacon_minor": int(beacon_mac.split(':')[-1], 16),
            "ibeacon_tx_power": -20,
            "eddystone_namespace": None,
            "eddystone_instance": None,
            "eddystone_url": None,
            "eddystone_tx_power": None,
        }]
    }
    
    # Get current state before sending
    current_state_before = "unknown"
    if db and boat_id:
        try:
            beacon = db.get_beacon_by_boat(boat_id)
            if beacon:
                state = db.get_beacon_state(beacon.id)
                current_state_before = state.value if state else "idle"
        except:
            pass
    
    if log:
        log("detection_send", 
            scanner_id=scanner_id, 
            beacon_mac=beacon_mac, 
            rssi=rssi,
            boat_id=boat_id,
            current_state=current_state_before,
            expected_state=expected_state,
            timestamp=time.time())
    
    try:
        response = requests.post(
            f"{server_url}/api/v1/detections",
            json=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer default-key"},
            timeout=2
        )
        
        # Get current state after sending
        current_state_after = "unknown"
        if db and boat_id:
            try:
                beacon = db.get_beacon_by_boat(boat_id)
                if beacon:
                    state = db.get_beacon_state(beacon.id)
                    current_state_after = state.value if state else "idle"
            except:
                pass
        
        if response.status_code == 200:
            state_change = "→" if current_state_before != current_state_after else "="
            print(f" SENT [{scanner_id:12}] {beacon_mac} @ {rssi:4d} dBm | State: {current_state_before:8} {state_change} {current_state_after:8} | Expect: {expected_state or 'N/A'}")
            if log:
                log("detection_success", 
                    scanner_id=scanner_id, 
                    beacon_mac=beacon_mac, 
                    rssi=rssi,
                    boat_id=boat_id,
                    state_before=current_state_before,
                    state_after=current_state_after,
                    state_changed=(current_state_before != current_state_after),
                    expected_state=expected_state,
                    status=response.status_code,
                    timestamp=time.time())
            return True
        else:
            print(f" ERROR {response.status_code}: {response.text[:100]}")
            if log:
                log("detection_error", 
                    scanner_id=scanner_id, 
                    beacon_mac=beacon_mac, 
                    rssi=rssi, 
                    boat_id=boat_id,
                    current_state=current_state_after,
                    status=response.status_code, 
                    error=response.text[:500])
            return False
    except Exception as e:
        print(f" FAILED: {e}")
        if log:
            log("detection_fail", 
                scanner_id=scanner_id, 
                beacon_mac=beacon_mac, 
                rssi=rssi,
                boat_id=boat_id, 
                error=str(e))
        return False


class RealisticBluetoothSimulator:
    """Highly realistic Bluetooth simulator based on calibration data."""
    
    def __init__(self):
        # Calibration-based parameters from real-world data
        self.base_rssi_left = -45  # Strong signal when close to left scanner
        self.base_rssi_right = -45  # Strong signal when close to right scanner
        self.noise_level = 3  # dB noise variation
        self.reflection_delay = 0.1  # Reflection delay in seconds
        self.multipath_factor = 0.3  # Multipath interference factor
        
        # Distance-based attenuation (realistic for BLE)
        self.attenuation_rate = 2.0  # dB per meter (approximate)
        
        # Movement parameters
        self.walking_speed = 1.2  # m/s average walking speed
        self.gate_width = 2.0  # meters - width of the gate area
        
    def calculate_rssi(self, distance: float, base_rssi: int, noise: bool = True) -> int:
        """Calculate realistic RSSI based on distance and environmental factors."""
        # Free space path loss approximation
        path_loss = 20 * math.log10(distance) if distance > 0 else 0
        
        # Add multipath effects
        multipath_loss = random.uniform(0, self.multipath_factor * path_loss)
        
        # Calculate final RSSI
        rssi = base_rssi - path_loss - multipath_loss
        
        # Add realistic noise
        if noise:
            rssi += random.gauss(0, self.noise_level)
        
        # Clamp to realistic BLE range
        return int(max(-100, min(-20, rssi)))
    
    def simulate_movement(self, direction: str, beacon_mac: str, server_url: str, log=None, db=None, boat_id=None) -> bool:
        """Simulate realistic boat movement through the gate."""
        
        expected_final = "exited" if direction == "exit" else "entered"
        print(f"\n{'='*80}")
        print(f"{direction.upper()} Movement: {beacon_mac} (Boat: {boat_id})")
        print(f"Expected Final State: {expected_final}")
        print(f"{'='*80}")
        
        if direction == "exit":
            return self._simulate_exit(beacon_mac, server_url, log, db, boat_id, expected_final)
        else:
            return self._simulate_enter(beacon_mac, server_url, log, db, boat_id, expected_final)
    
    def _simulate_exit(self, beacon_mac: str, server_url: str, log=None, db=None, boat_id=None, expected_state=None) -> bool:
        """Simulate boat exiting shed (left -> right movement) - Door-LR Logic."""
        
        # Phase 1: Boat starts in shed (strong left signal)
        print("\n   Phase 1: Boat in shed (strong LEFT signal)")
        print("     Goal: Establish baseline - boat is INSIDE")
        for i in range(3):
            rssi = self.calculate_rssi(0.5, self.base_rssi_left)
            send_detection_to_api("gate-left", beacon_mac, rssi, server_url, log, db, boat_id, expected_state)
            time.sleep(random.uniform(0.4, 0.6))
        
        # Phase 2: Boat begins moving toward gate - LEFT weakens, RIGHT strengthens
        print("\n   Phase 2: Moving through gate (LEFT → RIGHT)")
        print("     Goal: LEFT weakens, RIGHT strengthens - classifier should detect EXIT")
        steps = 10
        for i in range(steps):
            # Distance from left scanner increases, from right scanner decreases
            progress = i / steps
            dist_left = 0.5 + progress * 2.5  # 0.5m to 3.0m
            dist_right = 3.0 - progress * 2.5  # 3.0m to 0.5m
            
            rssi_left = self.calculate_rssi(dist_left, self.base_rssi_left)
            rssi_right = self.calculate_rssi(dist_right, self.base_rssi_right)
            
            print(f"     Step {i+1}/{steps}: dist_L={dist_left:.1f}m dist_R={dist_right:.1f}m")
            
            # Both scanners see the boat during transition - critical for door-lr
            send_detection_to_api("gate-left", beacon_mac, rssi_left, server_url, log, db, boat_id, expected_state)
            time.sleep(0.1)  # Small delay between scanners
            send_detection_to_api("gate-right", beacon_mac, rssi_right, server_url, log, db, boat_id, expected_state)
            
            time.sleep(random.uniform(0.2, 0.4))
        
        # Phase 3: Boat exits to water (strong right signal, weak left)
        print("\n   Phase 3: Boat on water (strong RIGHT signal)")
        print("     Goal: Strong RIGHT, weak LEFT - confirm OUTSIDE state")
        for i in range(4):
            rssi = self.calculate_rssi(0.5, self.base_rssi_right)
            send_detection_to_api("gate-right", beacon_mac, rssi, server_url, log, db, boat_id, expected_state)
            # Occasional weak left signal (reflection)
            if random.random() < 0.4:
                weak_rssi = self.calculate_rssi(4.0, self.base_rssi_left)
                send_detection_to_api("gate-left", beacon_mac, weak_rssi, server_url, log, db, boat_id, expected_state)
            time.sleep(random.uniform(0.4, 0.6))
        
        print("\n   Exit movement completed (LEFT → RIGHT)")
        return True
    
    def _simulate_enter(self, beacon_mac: str, server_url: str, log=None, db=None, boat_id=None, expected_state=None) -> bool:
        """Simulate boat entering shed (right -> left movement) - Door-LR Logic."""
        
        # Phase 1: Boat approaches from water (strong right signal)
        print("\n   Phase 1: Boat approaching from water (strong RIGHT signal)")
        print("     Goal: Establish baseline - boat is OUTSIDE")
        for i in range(3):
            rssi = self.calculate_rssi(0.5, self.base_rssi_right)
            send_detection_to_api("gate-right", beacon_mac, rssi, server_url, log, db, boat_id, expected_state)
            time.sleep(random.uniform(0.4, 0.6))
        
        # Phase 2: Boat moves through gate - RIGHT weakens, LEFT strengthens
        print("\n   Phase 2: Moving through gate (RIGHT → LEFT)")
        print("     Goal: RIGHT weakens, LEFT strengthens - classifier should detect ENTER")
        steps = 10
        for i in range(steps):
            # Distance from right scanner increases, from left scanner decreases
            progress = i / steps
            dist_right = 0.5 + progress * 2.5  # 0.5m to 3.0m
            dist_left = 3.0 - progress * 2.5  # 3.0m to 0.5m
            
            rssi_right = self.calculate_rssi(dist_right, self.base_rssi_right)
            rssi_left = self.calculate_rssi(dist_left, self.base_rssi_left)
            
            print(f"     Step {i+1}/{steps}: dist_R={dist_right:.1f}m dist_L={dist_left:.1f}m")
            
            # Both scanners see the boat during transition - critical for door-lr
            send_detection_to_api("gate-right", beacon_mac, rssi_right, server_url, log, db, boat_id, expected_state)
            time.sleep(0.1)  # Small delay between scanners
            send_detection_to_api("gate-left", beacon_mac, rssi_left, server_url, log, db, boat_id, expected_state)
            
            time.sleep(random.uniform(0.2, 0.4))
        
        # Phase 3: Boat enters shed (strong left signal, weak right)
        print("\n   Phase 3: Boat in shed (strong LEFT signal)")
        print("     Goal: Strong LEFT, weak RIGHT - confirm INSIDE state")
        for i in range(4):
            rssi = self.calculate_rssi(0.5, self.base_rssi_left)
            send_detection_to_api("gate-left", beacon_mac, rssi, server_url, log, db, boat_id, expected_state)
            # Occasional weak right signal (reflection)
            if random.random() < 0.4:
                weak_rssi = self.calculate_rssi(4.0, self.base_rssi_right)
                send_detection_to_api("gate-right", beacon_mac, weak_rssi, server_url, log, db, boat_id, expected_state)
            time.sleep(random.uniform(0.4, 0.6))
        
        print("\n   Enter movement completed (RIGHT → LEFT)")
        return True


def simulate_realistic_movement(db: DatabaseManager, boat_id: str, beacon_mac: str,
                              direction: str, server_url: str = "http://127.0.0.1:8000", log=None):
    """Simulate one realistic movement using calibration-based parameters."""
    
    expected_final = "exited" if direction == "exit" else "entered"
    
    if log:
        log("movement_begin", boat_id=boat_id, beacon_mac=beacon_mac, direction=direction, expected_final_state=expected_final)
    
    simulator = RealisticBluetoothSimulator()
    success = simulator.simulate_movement(direction, beacon_mac, server_url, log, db, boat_id)
    
    if log:
        log("movement_complete", boat_id=boat_id, beacon_mac=beacon_mac, direction=direction, expected_final_state=expected_final, success=success)
    
    return direction


def _state_str(s: DetectionState) -> str:
    try:
        return s.value
    except Exception:
        return str(s)


def _expected_final_state(direction: str) -> DetectionState:
    return DetectionState.OUTSIDE if direction == "exit" else DetectionState.INSIDE


def _get_current_state_for_boat(db: DatabaseManager, boat_id: str) -> DetectionState:
    beacon = db.get_beacon_by_boat(boat_id)
    if not beacon:
        return DetectionState.IDLE
    return db.get_beacon_state(beacon.id) or DetectionState.IDLE


def _poll_actual_state(db: DatabaseManager, boat_id: str, expect: DetectionState, timeout_s: float = 30.0, interval_s: float = 0.5, log=None):
    """Poll current FSM state and return the final observed state."""
    deadline = time.time() + timeout_s
    last_print = 0.0
    
    print(f"    Monitoring state changes for {boat_id}...")
    
    while time.time() < deadline:
        cur = _get_current_state_for_boat(db, boat_id)
        
        # Print progress every 2 seconds
        if time.time() - last_print > 2.0:
            print(f"    Current state: {_state_str(cur)} (waiting for {_state_str(expect)})")
            if log:
                log("observe_tick", boat_id=boat_id, observed=_state_str(cur), expect=_state_str(expect))
            last_print = time.time()
        
        if cur == expect:
            print(f"    State change detected: {_state_str(cur)}")
            return cur
        
        time.sleep(interval_s)
    
    final_state = _get_current_state_for_boat(db, boat_id)
    print(f"    Timeout reached. Final state: {_state_str(final_state)}")
    return final_state


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Realistic Door-LR BLE Simulator")
    parser.add_argument("--cooldown-after-exit-seconds", type=int, default=60,
                        help="Seconds to wait before changing state again for a boat after an EXIT")
    parser.add_argument("--min-wait", type=float, default=1.0,
                        help="Minimum seconds between movements")
    parser.add_argument("--max-wait", type=float, default=3.0,
                        help="Maximum seconds between movements")
    parser.add_argument("--max-parallel-exited", type=int, default=2,
                        help="Target at most this many boats in exited state concurrently")
    parser.add_argument("--enter_settle_delay", type=float, default=30.0,
                        help="Average seconds to wait after ENTERED before considering exit again")
    parser.add_argument("--log-file", type=str, default="realistic_sim.log",
                        help="Path to write JSONL log")
    parser.add_argument("--test-movements", type=int, default=6,
                        help="Number of test movements to perform")
    args = parser.parse_args()

    # Truncate existing log
    try:
        with open(args.log_file, "w", encoding="utf-8") as _f:
            _f.write("")
    except Exception:
        pass

    # Structured JSON logger
    def log(event: str, **fields):
        rec = {"ts": iso_now(), "event": event}
        rec.update(fields)
        try:
            with open(args.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    db = DatabaseManager()
    
    # Get boat-beacon assignments
    assignments = db.get_active_assignments()
    if not assignments:
        print("ERROR: No active boat-beacon assignments found. Run sim_seed_data.py first.")
        return
    
    # Convert beacon IDs to MAC addresses
    boat_beacons = []
    for boat_id, beacon_id in assignments:
        beacon = db.get_beacon_by_boat(boat_id)
        if beacon and beacon.mac_address:
            boat_beacons.append((boat_id, beacon.mac_address))
    
    if not boat_beacons:
        print("ERROR: No beacon MAC addresses found for assigned boats.")
        return

    print(f"Starting Realistic Door-LR Simulation")
    print(f"Boats: {len(boat_beacons)}")
    print(f"Test movements: {args.test_movements}")
    print(f"Log file: {args.log_file}")
    print("=" * 60)
    
    log("sim_start", boats=len(boat_beacons), test_movements=args.test_movements)
    
    # Track movement results
    movement_results = []
    
    try:
        for movement_num in range(1, args.test_movements + 1):
            print(f"\nMovement {movement_num}/{args.test_movements}")
            
            # Choose random boat
            boat_id, beacon_mac = random.choice(boat_beacons)
            
            # Alternate directions for testing
            direction = "exit" if movement_num % 2 == 1 else "enter"
            
            print(f"Testing {boat_id} ({beacon_mac}) - {direction.upper()}")
            
            # Get initial state
            initial_state = _get_current_state_for_boat(db, boat_id)
            print(f"Initial state: {_state_str(initial_state)}")
            
            # Perform movement
            start_time = time.time()
            simulate_realistic_movement(
                db, boat_id, beacon_mac,
                direction=direction,
                server_url="http://127.0.0.1:8000",
                log=log
            )
            
            # Wait for state change
            expected_state = _expected_final_state(direction)
            observed_state = _poll_actual_state(db, boat_id, expected_state, timeout_s=30.0, log=log)
            
            # Record result
            duration = time.time() - start_time
            success = observed_state == expected_state
            
            result = {
                "movement_num": movement_num,
                "boat_id": boat_id,
                "beacon_mac": beacon_mac,
                "direction": direction,
                "expected": _state_str(expected_state),
                "observed": _state_str(observed_state),
                "success": success,
                "duration": duration,
                "timestamp": iso_now()
            }
            
            movement_results.append(result)
            
            print(f"Result: {'PASS' if success else 'FAIL'}")
            print(f"Duration: {duration:.1f}s")
            
            log("movement_result", **result)
            
            # Wait between movements
            if movement_num < args.test_movements:
                wait_time = random.uniform(args.min_wait, args.max_wait)
                print(f"Waiting {wait_time:.1f}s before next movement...")
                time.sleep(wait_time)
    
    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")
        log("sim_stop", reason="user_interrupt")
    
    # Summary
    print("\n" + "=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    
    total_movements = len(movement_results)
    successful_movements = sum(1 for r in movement_results if r["success"])
    success_rate = (successful_movements / total_movements * 100) if total_movements > 0 else 0
    
    print(f"Total movements: {total_movements}")
    print(f"Successful: {successful_movements}")
    print(f"Failed: {total_movements - successful_movements}")
    print(f"Success rate: {success_rate:.1f}%")
    
    # Detailed results
    print("\nDetailed Results:")
    for result in movement_results:
        status = "PASS" if result["success"] else "FAIL"
        print(f"  {result['movement_num']}. {result['boat_id']} - {result['direction'].upper()}: {status} ({result['duration']:.1f}s)")
    
    log("sim_summary", 
        total_movements=total_movements,
        successful_movements=successful_movements,
        success_rate=success_rate,
        results=movement_results)
    
    print(f"\nFull log saved to: {args.log_file}")


if __name__ == "__main__":
    main()
