#!/usr/bin/env python3
"""
RF Bias Calibration System
===========================

Handles real-world RF signal fluctuation and antenna positioning issues.

This script performs comprehensive calibration to compensate for:
- RF signal fluctuation and multipath effects
- Antenna positioning and orientation issues
- Scanner hardware differences (RSSI bias)
- Environmental interference

Workflow:
1. STATIC POSITION CALIBRATION (determines RSSI bias)
   - Center: Place beacon at door centerline → record baseline
   - Left: Place beacon near left scanner → record left bias
   - Right: Place beacon near right scanner → record right bias
   
2. DYNAMIC MOVEMENT CALIBRATION (determines timing and patterns)
   - Walk beacon through door multiple times (ENTER direction)
   - Walk beacon through door multiple times (LEAVE direction)
   - Record RSSI patterns, timing, and peak characteristics

3. BIAS COMPENSATION OUTPUT
   - Generates calibration.json with RSSI offsets for each scanner
   - Provides signal smoothing parameters
   - Sets optimal detection thresholds

Usage:
    source .venv/bin/activate
    export PYTHONPATH="$(pwd)"
    python3 calibration/rf_bias_calibration.py --mac AA:BB:CC:DD:EE:FF
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from statistics import median, mean, stdev
from typing import List, Dict, Tuple
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database_models import DatabaseManager


def signal_percent(rssi_dbm: float) -> int:
    """Convert RSSI to percentage (0-100%)"""
    if rssi_dbm is None:
        return 0
    return int(max(0, min(100, round((rssi_dbm + 100) * (100.0 / 60.0)))))


def fetch_recent_detections(db: DatabaseManager, mac: str, seconds: float = 1.0):
    """Fetch recent detections from database"""
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT d.scanner_id, d.rssi, d.timestamp
            FROM detections d
            JOIN beacons b ON b.id = d.beacon_id
            WHERE b.mac_address = ? AND d.timestamp > datetime('now', ?)
            ORDER BY d.timestamp DESC LIMIT 500
            """,
            (mac, f"-{int(max(1, seconds))} seconds"),
        )
        rows = c.fetchall()
    return rows


def collect_samples_with_smoothing(db: DatabaseManager, mac: str, duration_s: float, 
                                   position_name: str, use_smoothing: bool = True):
    """
    Collect samples with RF fluctuation smoothing
    
    Uses exponential moving average to smooth out rapid RF fluctuations
    """
    print(f"\n  Collecting samples for {duration_s:.0f}s at {position_name}...")
    print(f"  (RF smoothing: {'ENABLED' if use_smoothing else 'DISABLED'})")
    
    samples = []
    smoothed_left = None
    smoothed_right = None
    alpha = 0.3  # Smoothing factor (0-1, lower = more smoothing)
    
    t_start = time.time()
    
    while time.time() - t_start < duration_s:
        rows = fetch_recent_detections(db, mac, seconds=0.5)
        
        if rows:
            # Separate left and right
            left_vals = []
            right_vals = []
            
            for scanner_id, rssi, ts in rows:
                sid = (scanner_id or '').lower()
                rssi_val = float(rssi)
                
                if 'left' in sid or 'inner' in sid:
                    left_vals.append(rssi_val)
                elif 'right' in sid or 'outer' in sid:
                    right_vals.append(rssi_val)
            
            # Apply smoothing if enabled
            if use_smoothing:
                if left_vals:
                    current_left = median(left_vals)
                    if smoothed_left is None:
                        smoothed_left = current_left
                    else:
                        smoothed_left = alpha * current_left + (1 - alpha) * smoothed_left
                
                if right_vals:
                    current_right = median(right_vals)
                    if smoothed_right is None:
                        smoothed_right = current_right
                    else:
                        smoothed_right = alpha * current_right + (1 - alpha) * smoothed_right
            else:
                smoothed_left = median(left_vals) if left_vals else None
                smoothed_right = median(right_vals) if right_vals else None
            
            # Store all samples for later analysis
            samples.extend(rows)
            
            # Display live meter
            left_display = f"{signal_percent(smoothed_left):3d}%" if smoothed_left else "  N/A"
            right_display = f"{signal_percent(smoothed_right):3d}%" if smoothed_right else "  N/A"
            left_rssi = f"{smoothed_left:5.1f}" if smoothed_left else "  N/A"
            right_rssi = f"{smoothed_right:5.1f}" if smoothed_right else "  N/A"
            
            print(f"\r  LEFT: {left_display} ({left_rssi}dBm) | RIGHT: {right_display} ({right_rssi}dBm)   ", 
                  end="", flush=True)
        else:
            print(f"\r  Waiting for beacon signal...   ", end="", flush=True)
        
        time.sleep(0.3)
    
    print()  # New line
    return samples


def analyze_position_bias(samples, position_name: str):
    """
    Analyze samples to determine RSSI bias for a position
    
    Returns statistics and recommended bias values
    """
    if not samples:
        print(f"   WARNING: No samples for {position_name}")
        return None
    
    left_vals = []
    right_vals = []
    
    for scanner_id, rssi, ts in samples:
        sid = (scanner_id or '').lower()
        rssi_val = float(rssi)
        
        if 'left' in sid or 'inner' in sid:
            left_vals.append(rssi_val)
        elif 'right' in sid or 'outer' in sid:
            right_vals.append(rssi_val)
    
    if not left_vals or not right_vals:
        print(f"   WARNING: Missing scanner data for {position_name}")
        return None
    
    # Calculate statistics
    left_median = median(left_vals)
    right_median = median(right_vals)
    left_mean = mean(left_vals)
    right_mean = mean(right_vals)
    left_std = stdev(left_vals) if len(left_vals) > 1 else 0
    right_std = stdev(right_vals) if len(right_vals) > 1 else 0
    
    # RSSI difference (bias)
    median_diff = left_median - right_median
    mean_diff = left_mean - right_mean
    
    # Determine which scanner is stronger (closer)
    stronger_scanner = "LEFT" if left_median > right_median else "RIGHT"
    weaker_scanner = "RIGHT" if stronger_scanner == "LEFT" else "LEFT"
    strength_diff = abs(median_diff)
    
    stats = {
        'position': position_name,
        'left': {
            'median': left_median,
            'mean': left_mean,
            'std': left_std,
            'samples': len(left_vals)
        },
        'right': {
            'median': right_median,
            'mean': right_mean,
            'std': right_std,
            'samples': len(right_vals)
        },
        'bias': {
            'median_diff': median_diff,
            'mean_diff': mean_diff,
            'magnitude': abs(median_diff)
        },
        'positioning': {
            'stronger_scanner': stronger_scanner,
            'weaker_scanner': weaker_scanner,
            'strength_difference': strength_diff,
            'is_centered': strength_diff < 3.0  # Within 3 dB = roughly centered
        }
    }
    
    # Print detailed results
    print(f"\n   {position_name} Analysis:")
    print(f"   Left Scanner:  {left_median:5.1f} dBm (std: {left_std:4.1f}, n={len(left_vals)})")
    print(f"   Right Scanner: {right_median:5.1f} dBm (std: {right_std:4.1f}, n={len(right_vals)})")
    print(f"   Bias:          {median_diff:+5.1f} dB (L-R)")
    print(f"   Positioning:   {stronger_scanner} scanner is {strength_diff:.1f} dB stronger")
    
    if stats['positioning']['is_centered']:
        print(f"   Status:        ✓ Beacon is well-centered (difference < 3 dB)")
    else:
        print(f"   Status:        ⚠ Beacon favors {stronger_scanner} scanner (difference ≥ 3 dB)")
    
    return stats


def run_static_calibration(db: DatabaseManager, mac: str):
    """
    Step 1: Static position calibration
    Records RSSI at center, left, and right positions
    """
    print("\n" + "="*70)
    print("STEP 1: STATIC POSITION CALIBRATION")
    print("="*70)
    print("\nThis measures RF signal characteristics at three key positions.")
    print("We'll use this to compensate for antenna angle and scanner differences.\n")
    
    positions = []
    
    # Position 1: CENTER
    print("\n[1/3] CENTER POSITION")
    print("-" * 50)
    print("Place the beacon at the EXACT CENTER of the doorway.")
    print("This should be equidistant from both scanners.")
    input("Press ENTER when beacon is in position...")
    
    center_samples = collect_samples_with_smoothing(db, mac, duration_s=15.0, 
                                                     position_name="CENTER", 
                                                     use_smoothing=True)
    center_stats = analyze_position_bias(center_samples, "CENTER")
    if center_stats:
        positions.append(center_stats)
    
    # Position 2: LEFT
    print("\n[2/3] LEFT POSITION")
    print("-" * 50)
    print("Move the beacon CLOSE to the LEFT scanner (hci0).")
    print("About 0.5-1 meter away, clearly favoring left side.")
    input("Press ENTER when beacon is in position...")
    
    left_samples = collect_samples_with_smoothing(db, mac, duration_s=15.0, 
                                                   position_name="LEFT", 
                                                   use_smoothing=True)
    left_stats = analyze_position_bias(left_samples, "LEFT")
    if left_stats:
        positions.append(left_stats)
    
    # Position 3: RIGHT
    print("\n[3/3] RIGHT POSITION")
    print("-" * 50)
    print("Move the beacon CLOSE to the RIGHT scanner (hci1).")
    print("About 0.5-1 meter away, clearly favoring right side.")
    input("Press ENTER when beacon is in position...")
    
    right_samples = collect_samples_with_smoothing(db, mac, duration_s=15.0, 
                                                    position_name="RIGHT", 
                                                    use_smoothing=True)
    right_stats = analyze_position_bias(right_samples, "RIGHT")
    if right_stats:
        positions.append(right_stats)
    
    return positions


def calculate_bias_compensation(positions):
    """
    Calculate RSSI bias compensation values
    
    Goal: Make center position show equal RSSI from both scanners
    """
    print("\n" + "="*70)
    print("BIAS COMPENSATION CALCULATION")
    print("="*70)
    
    center_stats = next((p for p in positions if p['position'] == 'CENTER'), None)
    left_stats = next((p for p in positions if p['position'] == 'LEFT'), None)
    right_stats = next((p for p in positions if p['position'] == 'RIGHT'), None)
    
    if not center_stats:
        print("\nERROR: No center position data. Cannot calculate bias.")
        return None
    
    # Calculate bias to equalize center position
    center_bias = center_stats['bias']['median_diff']
    
    # Bias values to add to each scanner's RSSI
    # Positive bias makes scanner "stronger"
    # Negative bias makes scanner "weaker"
    left_bias = -center_bias / 2.0  # Adjust left
    right_bias = center_bias / 2.0  # Adjust right
    
    compensation = {
        'center_measured_bias': center_bias,
        'left_bias_db': left_bias,
        'right_bias_db': right_bias,
        'bias_explanation': {
            'left': f"Add {left_bias:+.1f} dB to left scanner RSSI",
            'right': f"Add {right_bias:+.1f} dB to right scanner RSSI",
            'center': f"Measured center bias was {center_bias:+.1f} dB (L-R)",
            'result': f"After compensation, center should show ~0 dB difference"
        }
    }
    
    print(f"\nMeasured Center Bias: {center_bias:+.1f} dB (Left - Right)")
    print(f"\nRecommended Compensation:")
    print(f"  Left Scanner (gate-left):  {left_bias:+.1f} dB bias")
    print(f"  Right Scanner (gate-right): {right_bias:+.1f} dB bias")
    print(f"\nThis will equalize signals at the center position.")
    
    return compensation


def analyze_movement_pattern(samples, direction: str, run: int):
    """
    Analyze movement samples to determine scanner detection order and timing
    """
    if not samples:
        return None
    
    # Separate samples by scanner
    left_samples = []
    right_samples = []
    
    for scanner_id, rssi, ts in samples:
        sid = (scanner_id or '').lower()
        rssi_val = float(rssi)
        timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
        
        if 'left' in sid or 'inner' in sid:
            left_samples.append((timestamp, rssi_val))
        elif 'right' in sid or 'outer' in sid:
            right_samples.append((timestamp, rssi_val))
    
    if not left_samples or not right_samples:
        return None
    
    # Sort by timestamp
    left_samples.sort(key=lambda x: x[0])
    right_samples.sort(key=lambda x: x[0])
    
    # Find first detection from each scanner
    left_first_time = left_samples[0][0]
    right_first_time = right_samples[0][0]
    
    # Determine which scanner sees beacon first
    if left_first_time < right_first_time:
        first_scanner = "LEFT"
        time_diff = right_first_time - left_first_time
    else:
        first_scanner = "RIGHT"
        time_diff = left_first_time - right_first_time
    
    # Find peak RSSI from each scanner
    left_peak = max(left_samples, key=lambda x: x[1])[1]
    right_peak = max(right_samples, key=lambda x: x[1])[1]
    
    # Calculate movement characteristics
    left_peak_time = next(ts for ts, rssi in left_samples if rssi == left_peak)
    right_peak_time = next(ts for ts, rssi in right_samples if rssi == right_peak)
    
    peak_lag = left_peak_time - right_peak_time
    
    analysis = {
        'direction': direction,
        'run': run,
        'first_scanner': first_scanner,
        'first_detection_lag': time_diff,
        'left_peak_rssi': left_peak,
        'right_peak_rssi': right_peak,
        'peak_lag': peak_lag,
        'expected_pattern': "RIGHT→LEFT" if direction == "ENTER" else "LEFT→RIGHT",
        'actual_pattern': f"{first_scanner}→{'RIGHT' if first_scanner == 'LEFT' else 'LEFT'}",
        'pattern_correct': (first_scanner == "RIGHT" and direction == "ENTER") or 
                          (first_scanner == "LEFT" and direction == "LEAVE")
    }
    
    return analysis


def run_movement_calibration(db: DatabaseManager, mac: str):
    """
    Step 2: Movement calibration
    Record walking patterns through doorway
    """
    print("\n" + "="*70)
    print("STEP 2: MOVEMENT CALIBRATION")
    print("="*70)
    print("\nThis records how RSSI changes as beacon moves through doorway.")
    print("We'll analyze which scanner sees the beacon first and timing patterns.")
    print("\nREAL-WORLD SCENARIOS:")
    print("- Boats may pass closer to one scanner than the other")
    print("- Hand-to-hand beacon passing (simulating boat movement)")
    print("- Off-center paths through the doorway")
    print("- Asymmetric scanner positioning\n")
    
    movements = []
    movement_analyses = []
    
    # ENTER movements (Water → Shed)
    print("\n[ENTER] Water → Shed Movement")
    print("-" * 50)
    print("Expected pattern: RIGHT scanner should see beacon first, then LEFT scanner")
    print("This indicates boat approaching from outside (water side)")
    print("\nREALISTIC MOVEMENT OPTIONS:")
    print("1. Walk through center (if distance allows)")
    print("2. Hand-to-hand passing (start near RIGHT, pass to LEFT)")
    print("3. Off-center path (closer to one scanner)")
    print("Choose the method that best simulates your boat movement:\n")
    
    for i in range(3):
        print(f"\nRun {i+1}/3: ENTER (Water → Shed)")
        print("Walk beacon from OUTSIDE (right/water side) to INSIDE (left/shed side)")
        print("Walk at normal boat-passing speed.")
        print("\nMOVEMENT OPTIONS:")
        print("A) Walk through center (if 4m distance allows)")
        print("B) Hand-to-hand passing (start near RIGHT scanner, pass to LEFT)")
        print("C) Off-center path (closer to one scanner)")
        
        choice = input("Choose movement method (A/B/C) or press ENTER for default (A): ").strip().upper()
        if not choice:
            choice = "A"
        
        print(f"Using method {choice}: ", end="")
        if choice == "A":
            print("Walking through center")
        elif choice == "B":
            print("Hand-to-hand passing")
        elif choice == "C":
            print("Off-center path")
        else:
            print("Default center walk")
        
        input("Press ENTER when ready to start...")
        
        print("Recording... walk through NOW!")
        time.sleep(0.5)  # Brief delay
        
        # Collect during movement (longer duration)
        samples = collect_samples_with_smoothing(db, mac, duration_s=8.0, 
                                                position_name=f"ENTER_run{i+1}", 
                                                use_smoothing=False)  # No smoothing for movement
        
        if samples:
            movements.append({
                'direction': 'ENTER',
                'run': i+1,
                'movement_method': choice,
                'samples': len(samples),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Analyze movement pattern
            analysis = analyze_movement_pattern(samples, 'ENTER', i+1)
            if analysis:
                analysis['movement_method'] = choice
                movement_analyses.append(analysis)
                
                print(f"\n   ENTER Run {i+1} Analysis ({choice}):")
                print(f"   First Detection: {analysis['first_scanner']} scanner ({analysis['first_detection_lag']:.2f}s ahead)")
                print(f"   Expected Pattern: {analysis['expected_pattern']}")
                print(f"   Actual Pattern:   {analysis['actual_pattern']}")
                print(f"   Pattern Correct:  {'✓ YES' if analysis['pattern_correct'] else '✗ NO'}")
                print(f"   Left Peak:        {analysis['left_peak_rssi']:.1f} dBm")
                print(f"   Right Peak:       {analysis['right_peak_rssi']:.1f} dBm")
                print(f"   Peak Lag:         {analysis['peak_lag']:.2f}s")
            
            print(f"Captured {len(samples)} samples")
        
        if i < 2:
            print("Return beacon to starting position for next run...")
            time.sleep(3)
    
    # LEAVE movements (Shed → Water)
    print("\n[LEAVE] Shed → Water Movement")
    print("-" * 50)
    print("Expected pattern: LEFT scanner should see beacon first, then RIGHT scanner")
    print("This indicates boat exiting from inside (shed side)")
    print("\nREALISTIC MOVEMENT OPTIONS:")
    print("1. Walk through center (if distance allows)")
    print("2. Hand-to-hand passing (start near LEFT, pass to RIGHT)")
    print("3. Off-center path (closer to one scanner)")
    print("Choose the method that best simulates your boat movement:\n")
    
    for i in range(3):
        print(f"\nRun {i+1}/3: LEAVE (Shed → Water)")
        print("Walk beacon from INSIDE (left/shed side) to OUTSIDE (right/water side)")
        print("Walk at normal boat-passing speed.")
        print("\nMOVEMENT OPTIONS:")
        print("A) Walk through center (if 4m distance allows)")
        print("B) Hand-to-hand passing (start near LEFT scanner, pass to RIGHT)")
        print("C) Off-center path (closer to one scanner)")
        
        choice = input("Choose movement method (A/B/C) or press ENTER for default (A): ").strip().upper()
        if not choice:
            choice = "A"
        
        print(f"Using method {choice}: ", end="")
        if choice == "A":
            print("Walking through center")
        elif choice == "B":
            print("Hand-to-hand passing")
        elif choice == "C":
            print("Off-center path")
        else:
            print("Default center walk")
        
        input("Press ENTER when ready to start...")
        
        print("Recording... walk through NOW!")
        time.sleep(0.5)
        
        samples = collect_samples_with_smoothing(db, mac, duration_s=8.0, 
                                                position_name=f"LEAVE_run{i+1}", 
                                                use_smoothing=False)
        
        if samples:
            movements.append({
                'direction': 'LEAVE',
                'run': i+1,
                'movement_method': choice,
                'samples': len(samples),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Analyze movement pattern
            analysis = analyze_movement_pattern(samples, 'LEAVE', i+1)
            if analysis:
                analysis['movement_method'] = choice
                movement_analyses.append(analysis)
                
                print(f"\n   LEAVE Run {i+1} Analysis ({choice}):")
                print(f"   First Detection: {analysis['first_scanner']} scanner ({analysis['first_detection_lag']:.2f}s ahead)")
                print(f"   Expected Pattern: {analysis['expected_pattern']}")
                print(f"   Actual Pattern:   {analysis['actual_pattern']}")
                print(f"   Pattern Correct:   {'✓ YES' if analysis['pattern_correct'] else '✗ NO'}")
                print(f"   Left Peak:        {analysis['left_peak_rssi']:.1f} dBm")
                print(f"   Right Peak:       {analysis['right_peak_rssi']:.1f} dBm")
                print(f"   Peak Lag:         {analysis['peak_lag']:.2f}s")
            
            print(f"Captured {len(samples)} samples")
        
        if i < 2:
            print("Return beacon to starting position for next run...")
            time.sleep(3)
    
    # Summary analysis
    if movement_analyses:
        print("\n" + "="*70)
        print("MOVEMENT PATTERN SUMMARY")
        print("="*70)
        
        enter_analyses = [a for a in movement_analyses if a['direction'] == 'ENTER']
        leave_analyses = [a for a in movement_analyses if a['direction'] == 'LEAVE']
        
        # Analyze by movement method
        print(f"\nMovement Method Analysis:")
        methods = set(a.get('movement_method', 'A') for a in movement_analyses)
        for method in sorted(methods):
            method_analyses = [a for a in movement_analyses if a.get('movement_method', 'A') == method]
            method_name = {'A': 'Center Walk', 'B': 'Hand-to-Hand', 'C': 'Off-Center'}.get(method, f'Method {method}')
            
            correct_count = sum(1 for a in method_analyses if a['pattern_correct'])
            print(f"  {method_name} ({method}): {correct_count}/{len(method_analyses)} correct patterns")
            
            if method_analyses:
                avg_lag = sum(a['first_detection_lag'] for a in method_analyses) / len(method_analyses)
                print(f"    Average lag: {avg_lag:.2f}s")
        
        if enter_analyses:
            enter_correct = sum(1 for a in enter_analyses if a['pattern_correct'])
            print(f"\nENTER Movements: {enter_correct}/{len(enter_analyses)} correct patterns")
            if enter_correct < len(enter_analyses):
                print("⚠️  Some ENTER movements show wrong pattern - check scanner positioning")
        
        if leave_analyses:
            leave_correct = sum(1 for a in leave_analyses if a['pattern_correct'])
            print(f"LEAVE Movements: {leave_correct}/{len(leave_analyses)} correct patterns")
            if leave_correct < len(leave_analyses):
                print("⚠️  Some LEAVE movements show wrong pattern - check scanner positioning")
        
        # Calculate average timing
        avg_enter_lag = sum(a['first_detection_lag'] for a in enter_analyses) / len(enter_analyses) if enter_analyses else 0
        avg_leave_lag = sum(a['first_detection_lag'] for a in leave_analyses) / len(leave_analyses) if leave_analyses else 0
        
        print(f"\nOverall Timing Analysis:")
        print(f"  ENTER: {avg_enter_lag:.2f}s")
        print(f"  LEAVE: {avg_leave_lag:.2f}s")
        
        # Real-world scenario analysis
        print(f"\nReal-World Scenario Analysis:")
        hand_to_hand_analyses = [a for a in movement_analyses if a.get('movement_method') == 'B']
        off_center_analyses = [a for a in movement_analyses if a.get('movement_method') == 'C']
        
        if hand_to_hand_analyses:
            hth_correct = sum(1 for a in hand_to_hand_analyses if a['pattern_correct'])
            print(f"  Hand-to-Hand Passing: {hth_correct}/{len(hand_to_hand_analyses)} correct")
            if hth_correct == len(hand_to_hand_analyses):
                print(f"    ✓ Hand-to-hand passing works well - suitable for 4m distance")
            else:
                print(f"    ⚠ Hand-to-hand passing has issues - may need adjustment")
        
        if off_center_analyses:
            oc_correct = sum(1 for a in off_center_analyses if a['pattern_correct'])
            print(f"  Off-Center Paths: {oc_correct}/{len(off_center_analyses)} correct")
            if oc_correct == len(off_center_analyses):
                print(f"    ✓ Off-center paths work well - boats can pass closer to one scanner")
            else:
                print(f"    ⚠ Off-center paths have issues - may need scanner adjustment")
    
    return movements, movement_analyses


def save_calibration(positions, compensation, movements, movement_analyses=None, output_dir="calibration/sessions"):
    """Save calibration data to JSON file"""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join(output_dir, f"session_{timestamp}")
    os.makedirs(session_dir, exist_ok=True)
    
    calibration_data = {
        'timestamp': timestamp,
        'version': '2.0',
        'static_positions': positions,
        'bias_compensation': compensation,
        'movement_calibration': movements,
        'movement_analyses': movement_analyses or [],
        'recommended_config': {
            'scanner_config': {
                'gate-left': {
                    'rssi_bias_db': compensation['left_bias_db'] if compensation else 0,
                    'adapter': 'hci0'
                },
                'gate-right': {
                    'rssi_bias_db': compensation['right_bias_db'] if compensation else 0,
                    'adapter': 'hci1'
                }
            },
            'signal_smoothing': {
                'enabled': True,
                'alpha': 0.3,
                'window_size': 3
            },
            'detection_params': {
                'active_dbm': -90,
                'energy_dbm': -85,
                'delta_db': 2.0,
                'window_s': 0.5,
                'cooldown_s': 1.0
            }
        }
    }
    
    # Save full calibration
    calib_file = os.path.join(session_dir, "calibration.json")
    with open(calib_file, 'w') as f:
        json.dump(calibration_data, f, indent=2)
    
    # Save as 'latest' for easy access
    latest_dir = os.path.join(output_dir, "latest")
    os.makedirs(latest_dir, exist_ok=True)
    latest_file = os.path.join(latest_dir, "calibration.json")
    with open(latest_file, 'w') as f:
        json.dump(calibration_data, f, indent=2)
    
    print(f"\nCalibration saved to:")
    print(f"  {calib_file}")
    print(f"  {latest_file}")
    
    return calib_file


def main():
    parser = argparse.ArgumentParser(description="RF Bias Calibration System")
    parser.add_argument('--mac', required=True, help="Beacon MAC address (AA:BB:CC:DD:EE:FF)")
    parser.add_argument('--db-path', default='data/boat_tracking.db', help="Database path")
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("RF BIAS CALIBRATION SYSTEM")
    print("="*70)
    print(f"\nBeacon MAC: {args.mac}")
    print(f"Database:   {args.db_path}")
    print("\nThis calibration compensates for:")
    print("  - RF signal fluctuation and multipath")
    print("  - Antenna positioning and angle issues")
    print("  - Scanner hardware RSSI differences")
    print("  - Environmental interference")
    
    # Initialize database
    db = DatabaseManager(args.db_path)
    
    # Step 1: Static position calibration
    positions = run_static_calibration(db, args.mac)
    
    # Calculate bias compensation
    compensation = calculate_bias_compensation(positions)
    
    # Step 2: Movement calibration
    movements, movement_analyses = run_movement_calibration(db, args.mac)
    
    # Save results
    if compensation:
        calib_file = save_calibration(positions, compensation, movements, movement_analyses)
        
        print("\n" + "="*70)
        print("CALIBRATION COMPLETE")
        print("="*70)
        print("\nNext steps:")
        print("1. Copy calibration values to system/json/scanner_config.json:")
        print(f"   gate-left:  rssi_bias_db: {compensation['left_bias_db']:.1f}")
        print(f"   gate-right: rssi_bias_db: {compensation['right_bias_db']:.1f}")
        print("\n2. Restart the boat tracking system to apply new bias values")
        print("\n3. Test direction detection with physical beacon walks")
        
        # Print positioning analysis
        if movement_analyses:
            print("\n" + "="*70)
            print("SCANNER POSITIONING ANALYSIS")
            print("="*70)
            
            # Analyze static positioning
            center_stats = next((p for p in positions if p['position'] == 'CENTER'), None)
            if center_stats:
                print(f"\nStatic Positioning (CENTER):")
                print(f"  {center_stats['positioning']['stronger_scanner']} scanner is {center_stats['positioning']['strength_difference']:.1f} dB stronger")
                if center_stats['positioning']['is_centered']:
                    print(f"  ✓ Beacon is well-centered at doorway")
                else:
                    print(f"  ⚠ Beacon favors {center_stats['positioning']['stronger_scanner']} scanner - may need repositioning")
            
            # Analyze movement patterns
            enter_analyses = [a for a in movement_analyses if a['direction'] == 'ENTER']
            leave_analyses = [a for a in movement_analyses if a['direction'] == 'LEAVE']
            
            print(f"\nMovement Pattern Analysis:")
            if enter_analyses:
                enter_correct = sum(1 for a in enter_analyses if a['pattern_correct'])
                print(f"  ENTER: {enter_correct}/{len(enter_analyses)} correct patterns")
                if enter_correct < len(enter_analyses):
                    print(f"  ⚠ ENTER pattern issues - check if RIGHT scanner is truly on water side")
            
            if leave_analyses:
                leave_correct = sum(1 for a in leave_analyses if a['pattern_correct'])
                print(f"  LEAVE: {leave_correct}/{len(leave_analyses)} correct patterns")
                if leave_correct < len(leave_analyses):
                    print(f"  ⚠ LEAVE pattern issues - check if LEFT scanner is truly on shed side")
            
            # Scanner positioning recommendations
            print(f"\nScanner Positioning Recommendations:")
            print(f"  LEFT Scanner (hci0): Should be on SHED/INSIDE side")
            print(f"  RIGHT Scanner (hci1): Should be on WATER/OUTSIDE side")
            print(f"  Expected ENTER pattern: RIGHT scanner sees beacon first")
            print(f"  Expected LEAVE pattern: LEFT scanner sees beacon first")
            
            # Check for asymmetric positioning
            if enter_analyses and leave_analyses:
                avg_enter_lag = sum(a['first_detection_lag'] for a in enter_analyses) / len(enter_analyses)
                avg_leave_lag = sum(a['first_detection_lag'] for a in leave_analyses) / len(leave_analyses)
                
                print(f"\nTiming Analysis:")
                print(f"  Average ENTER lag: {avg_enter_lag:.2f}s")
                print(f"  Average LEAVE lag: {avg_leave_lag:.2f}s")
                
                if abs(avg_enter_lag - avg_leave_lag) > 0.5:
                    print(f"  ⚠ Asymmetric timing detected - scanners may not be equidistant from center")
                else:
                    print(f"  ✓ Symmetric timing - scanners appear well-positioned")
            
            # 4m distance constraint analysis
            print(f"\n4m Distance Constraint Analysis:")
            print(f"  Scanner separation: ~4 meters")
            print(f"  Wire tension: May block center path")
            print(f"  Recommended movement methods:")
            
            hand_to_hand_analyses = [a for a in movement_analyses if a.get('movement_method') == 'B']
            off_center_analyses = [a for a in movement_analyses if a.get('movement_method') == 'C']
            
            if hand_to_hand_analyses:
                hth_correct = sum(1 for a in hand_to_hand_analyses if a['pattern_correct'])
                print(f"  Hand-to-Hand Passing: {hth_correct}/{len(hand_to_hand_analyses)} correct")
                if hth_correct == len(hand_to_hand_analyses):
                    print(f"    ✓ RECOMMENDED for 4m setup - avoids wire obstruction")
                else:
                    print(f"    ⚠ May need adjustment for reliable detection")
            
            if off_center_analyses:
                oc_correct = sum(1 for a in off_center_analyses if a['pattern_correct'])
                print(f"  Off-Center Paths: {oc_correct}/{len(off_center_analyses)} correct")
                if oc_correct == len(off_center_analyses):
                    print(f"    ✓ RECOMMENDED for boats passing closer to one scanner")
                else:
                    print(f"    ⚠ May need scanner repositioning")
            
            print(f"\nReal-World Boat Movement Considerations:")
            print(f"  - Boats may not pass through exact center")
            print(f"  - Hand-to-hand passing simulates boat movement well")
            print(f"  - Off-center paths are normal and expected")
            print(f"  - System should handle all movement patterns reliably")
        
    else:
        print("\nCalibration failed. Please try again with better beacon placement.")


if __name__ == '__main__':
    main()

