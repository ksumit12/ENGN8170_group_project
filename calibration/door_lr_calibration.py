#!/usr/bin/env python3
"""
Door L/R Calibration Tool: 3-Step Bias Calibration
Teaches the system what CENTER, LEFT, and RIGHT positions look like.
Generates RSSI offsets for real-time signal equalization.

Workflow:
1. CENTER: Place beacon exactly in center → Learn zero bias point
2. LEFT: Place beacon near left scanner → Learn left characteristic  
3. RIGHT: Place beacon near right scanner → Learn right characteristic

Output: calibration/sessions/latest/door_lr_calib.json with RSSI offsets
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from statistics import median, mean, pstdev
import time

import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt

from app.database_models import DatabaseManager


def signal_percent(rssi_dbm: float) -> int:
    """Convert RSSI to percentage (0-100%)"""
    if rssi_dbm is None:
        return 0
    return int(max(0, min(100, round((rssi_dbm + 100) * (100.0 / 60.0)))))


def fetch_recent_detections(db: DatabaseManager, mac: str, seconds: float = 1.0):
    """Fetch recent detections for a beacon MAC from database"""
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT d.scanner_id, d.rssi, strftime('%s', d.timestamp) AS ts
            FROM detections d
            JOIN beacons b ON b.id = d.beacon_id
            WHERE b.mac_address = ? AND d.timestamp > datetime('now', ?)
            ORDER BY d.timestamp DESC LIMIT 200
            """,
            (mac, f"-{int(max(1, seconds))} seconds"),
        )
        rows = c.fetchall()
    return rows


def live_signal_meter(db: DatabaseManager, mac: str, duration_s: float = 10.0):
    """Show live signal strength and collect samples"""
    print(f"  Collecting for {duration_s:.0f}s... (watch the signal strength)")
    samples = []
    t_start = time.time()
    
    while time.time() - t_start < duration_s:
        rows = fetch_recent_detections(db, mac, seconds=1.0)
        samples.extend(rows)
        
        # Show live meter
        if rows:
            vals = [int(rssi) for _, rssi, _ in rows]
            avg = sum(vals) / len(vals) if vals else 0
            print(f"\r  Signal: {signal_percent(avg):3d}% (RSSI: {avg:5.1f} dBm)   ", end="", flush=True)
        else:
            print(f"\r  Signal:   0% (RSSI:   0.0 dBm)   ", end="", flush=True)
        
        time.sleep(0.5)
    
    print()  # New line after meter
    return samples


def analyze_samples(samples, position_name: str):
    """Analyze samples and compute statistics"""
    if not samples:
        print(f"   WARNING: No samples collected for {position_name}")
        return None
    
    # Separate left and right
    left_vals = []
    right_vals = []
    
    for scanner_id, rssi, ts in samples:
        sid = (scanner_id or '').lower()
        rssi_val = int(rssi)
        
        if 'left' in sid or 'inner' in sid:
            left_vals.append(rssi_val)
        elif 'right' in sid or 'outer' in sid:
            right_vals.append(rssi_val)
    
    if not left_vals or not right_vals:
        print(f"   WARNING: Missing data from one scanner for {position_name}")
        print(f"     Left samples: {len(left_vals)}, Right samples: {len(right_vals)}")
        return None
    
    # Compute statistics
    med_left = median(left_vals)
    med_right = median(right_vals)
    avg_left = mean(left_vals)
    avg_right = mean(right_vals)
    std_left = pstdev(left_vals) if len(left_vals) > 1 else 0.0
    std_right = pstdev(right_vals) if len(right_vals) > 1 else 0.0
    
    gap = abs(med_left - med_right)
    dominant = 'LEFT' if med_left > med_right else ('RIGHT' if med_right > med_left else 'EQUAL')
    
    result = {
        'position': position_name,
        'samples_left': len(left_vals),
        'samples_right': len(right_vals),
        'median_left': round(med_left, 2),
        'median_right': round(med_right, 2),
        'avg_left': round(avg_left, 2),
        'avg_right': round(avg_right, 2),
        'std_left': round(std_left, 2),
        'std_right': round(std_right, 2),
        'gap': round(gap, 2),
        'dominant': dominant,
        'raw_left': left_vals,
        'raw_right': right_vals
    }
    
    print(f"   {position_name} Analysis:")
    print(f"     Left:  median={med_left:5.1f} dBm, avg={avg_left:5.1f} dBm, std={std_left:4.1f} dB (n={len(left_vals)})")
    print(f"     Right: median={med_right:5.1f} dBm, avg={avg_right:5.1f} dBm, std={std_right:4.1f} dB (n={len(right_vals)})")
    print(f"     Gap: {gap:.1f} dB, Dominant: {dominant}")
    
    return result


def calculate_offsets(center_stats, left_stats, right_stats):
    """Calculate RSSI offsets to equalize signals"""
    
    if not center_stats:
        print("\n WARNING: Cannot calculate offsets without center calibration")
        return None
    
    # Center bias: difference between left and right at center
    center_bias = center_stats['median_left'] - center_stats['median_right']
    
    # Apply symmetric offsets to equalize at center
    # offset_left = -center_bias/2, offset_right = +center_bias/2
    # This makes: (L - offset_L) ≈ (R - offset_R) at center
    offset_left = -center_bias / 2.0
    offset_right = +center_bias / 2.0
    
    print("\n OFFSET CALCULATION:")
    print(f"  Center bias (L-R): {center_bias:+.2f} dB")
    print(f"  Offset for LEFT:   {offset_left:+.2f} dB")
    print(f"  Offset for RIGHT:  {offset_right:+.2f} dB")
    print(f"  Effect: Equalized center at ~{(center_stats['median_left'] + offset_left):.1f} dBm")
    
    # Characteristic thresholds from left/right calibration
    thresholds = {}
    
    if left_stats:
        # When near LEFT: expect strong left, weak right
        thresholds['strong_left'] = round(left_stats['median_left'] + offset_left, 2)
        thresholds['weak_right_at_left'] = round(left_stats['median_right'] + offset_right, 2)
        thresholds['left_dominance'] = round(
            (left_stats['median_left'] + offset_left) - (left_stats['median_right'] + offset_right), 
            2
        )
    
    if right_stats:
        # When near RIGHT: expect strong right, weak left
        thresholds['strong_right'] = round(right_stats['median_right'] + offset_right, 2)
        thresholds['weak_left_at_right'] = round(right_stats['median_left'] + offset_left, 2)
        thresholds['right_dominance'] = round(
            (right_stats['median_right'] + offset_right) - (right_stats['median_left'] + offset_left),
            2
        )
    
    return {
        'rssi_offsets': {
            'gate-left': round(offset_left, 2),
            'gate-right': round(offset_right, 2),
            'door-left': round(offset_left, 2),  # Alias
            'door-right': round(offset_right, 2)  # Alias
        },
        'center_bias_db': round(center_bias, 2),
        'thresholds': thresholds
    }


def main():
    ap = argparse.ArgumentParser(description="Door L/R 3-Step Calibration")
    ap.add_argument('--mac', required=True, help='Beacon MAC address (AA:BB:CC:DD:EE:FF)')
    ap.add_argument('--duration', type=float, default=8.0, help='Seconds to sample each height')
    ap.add_argument('--outdir', default='calibration/sessions')
    ap.add_argument('--test-live', action='store_true', help='Test live movement with saved calibration')
    ap.add_argument('--heights', action='store_true', default=True, help='Test at multiple heights (ground, chest, overhead)')
    args = ap.parse_args()

    db = DatabaseManager()
    
    # ===== LIVE TESTING MODE =====
    if args.test_live:
        print("="*70)
        print("LIVE MOVEMENT TESTING MODE")
        print("="*70)
        print("Testing real-time detection with saved calibration\n")
        
        # Load saved calibration
        calib_file = os.path.join(args.outdir, 'latest', 'door_lr_calib.json')
        if not os.path.exists(calib_file):
            print(f" No saved calibration found at: {calib_file}")
            print("Run calibration first without --test-live flag")
            return
        
        with open(calib_file, 'r') as f:
            calib = json.load(f)
        
        print(" Loaded calibration:")
        print(f"  Created: {calib.get('created_at', 'unknown')}")
        print(f"  Offsets: L={calib['rssi_offsets']['gate-left']:+.2f} dB, R={calib['rssi_offsets']['gate-right']:+.2f} dB")
        print(f"  Center bias: {calib.get('center_bias_db', 0):+.2f} dB")
        
        print("\n" + "="*70)
        print("LIVE MOVEMENT TEST")
        print("="*70)
        print("Instructions:")
        print("  1. EXIT test: Walk from INSIDE → OUTSIDE (left to right)")
        print("  2. ENTER test: Walk from OUTSIDE → INSIDE (right to left)")
        print("\nPress Ctrl+C to stop\n")
        
        try:
            offsets = calib['rssi_offsets']
            test_count = 0
            
            while True:
                test_count += 1
                direction = input(f"\nTest {test_count} - Which direction? [EXIT/ENTER/Q to quit]: ").strip().upper()
                
                if direction == 'Q':
                    break
                
                if direction not in ['EXIT', 'ENTER']:
                    print("Please enter EXIT or ENTER")
                    continue
                
                print(f"\n{'='*70}")
                print(f"Testing {direction} movement")
                print(f"{'='*70}")
                print("When ready, walk through at normal pace...")
                input("Press Enter to START monitoring...")
                
                # Monitor for 15 seconds
                print("\n Monitoring for 15 seconds...\n")
                samples = []
                t_start = time.time()
                
                while time.time() - t_start < 15.0:
                    rows = fetch_recent_detections(db, args.mac, seconds=0.5)
                    
                    for scanner_id, rssi, ts in rows:
                        sid = (scanner_id or '').lower()
                        rssi_val = int(rssi)
                        
                        # Apply calibration offsets
                        if 'left' in sid or 'inner' in sid:
                            corrected = rssi_val - offsets.get('gate-left', 0)
                            scanner = 'LEFT'
                        elif 'right' in sid or 'outer' in sid:
                            corrected = rssi_val - offsets.get('gate-right', 0)
                            scanner = 'RIGHT'
                        else:
                            continue
                        
                        samples.append((time.time(), scanner, rssi_val, corrected))
                        
                        # Live display
                        print(f"\r  {scanner:5} | Raw: {rssi_val:4d} dBm | Corrected: {corrected:6.1f} dBm   ", end="", flush=True)
                    
                    time.sleep(0.1)
                
                print(f"\n\n Captured {len(samples)} samples")
                
                # Analyze pattern
                if samples:
                    print("\nAnalyzing movement pattern...")
                    
                    left_samples = [(t, raw, cor) for t, s, raw, cor in samples if s == 'LEFT']
                    right_samples = [(t, raw, cor) for t, s, raw, cor in samples if s == 'RIGHT']
                    
                    if left_samples and right_samples:
                        # First detection times
                        t_left_first = left_samples[0][0]
                        t_right_first = right_samples[0][0]
                        lag = t_right_first - t_left_first
                        
                        # Signal strengths over time
                        left_corrected = [cor for _, _, cor in left_samples]
                        right_corrected = [cor for _, _, cor in right_samples]
                        
                        left_avg = sum(left_corrected) / len(left_corrected)
                        right_avg = sum(right_corrected) / len(right_corrected)
                        
                        print(f"  First detection: {'LEFT' if lag > 0 else 'RIGHT'} (lag: {abs(lag):.2f}s)")
                        print(f"  Left avg:  {left_avg:5.1f} dBm (corrected)")
                        print(f"  Right avg: {right_avg:5.1f} dBm (corrected)")
                        print(f"  Dominance: {'LEFT' if left_avg > right_avg else 'RIGHT'} by {abs(left_avg - right_avg):.1f} dB")
                        
                        # Determine detected direction based on pattern
                        if direction == 'EXIT':
                            # Expected: LEFT first, then RIGHT stronger
                            correct = (lag > 0 and right_avg > left_avg) or (lag < 0 and lag > -1.0 and right_avg > left_avg)
                        else:  # ENTER
                            # Expected: RIGHT first, then LEFT stronger
                            correct = (lag < 0 and left_avg > right_avg) or (lag > 0 and lag < 1.0 and left_avg > right_avg)
                        
                        result = " CORRECT" if correct else " INCORRECT"
                        print(f"\n  Expected: {direction}")
                        print(f"  Detection: {result}")
                    else:
                        print("   Incomplete data - both scanners needed")
                
        except KeyboardInterrupt:
            print("\n\nLive testing stopped.")
        
        print("\n" + "="*70)
        print("Testing complete!")
        print("="*70)
        return
    
    # ===== CALIBRATION MODE =====
    print("="*70)
    print("DOOR L/R CALIBRATION - 3-Step Bias Learning")
    print("="*70)
    print(f"Beacon MAC: {args.mac}")
    print(f"Sample duration: {args.duration:.1f}s per height")
    print(f"Height testing: {'Enabled (ground, chest, overhead)' if args.heights else 'Disabled'}")
    print("\nThis calibration teaches the system:")
    print("  1. CENTER: What zero-bias looks like")
    print("  2. LEFT: What strong-left signal looks like")
    print("  3. RIGHT: What strong-right signal looks like")
    
    if args.heights:
        print("\nAt each position, test at 3 heights:")
        print("  - Ground level (lowest surface)")
        print("  - Chest height (normal carrying)")
        print("  - Overhead (arms fully extended up)")
    
    print("\nMake sure both scanners are running and posting to API!\n")

    # Prepare session folder
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    session_dir = os.path.join(args.outdir, ts)
    os.makedirs(session_dir, exist_ok=True)

    # Prepare latest folder (symlink target)
    latest_dir = os.path.join(args.outdir, 'latest')
    if os.path.isdir(latest_dir):
        try:
            import shutil
            shutil.rmtree(latest_dir)
        except Exception:
            pass
    os.makedirs(latest_dir, exist_ok=True)

    # ===== STEP 1: CENTER CALIBRATION =====
    print("\n" + "="*70)
    print("STEP 1: CENTER CALIBRATION")
    print("="*70)
    print("Place the beacon EXACTLY in the CENTER between scanners.")
    print("This teaches the system what zero-bias looks like.\n")
    
    center_all_heights = []
    
    if args.heights:
        heights = [
            ("GROUND", "ground level (lowest surface available)"),
            ("CHEST", "chest height (normal carrying position)"),
            ("OVERHEAD", "overhead (arms fully extended up)")
        ]
        
        for height_name, height_desc in heights:
            print(f"\n HEIGHT: {height_name}")
            print(f"Place beacon at CENTER at {height_desc}")
            input("Press Enter to start sampling...")
            
            samples = live_signal_meter(db, args.mac, args.duration)
            stats = analyze_samples(samples, f"CENTER-{height_name}")
            
            if stats:
                stats['height'] = height_name
                center_all_heights.append(stats)
        
        # Aggregate center stats from all heights
        if center_all_heights:
            # Use median values across all heights
            all_left = [s['median_left'] for s in center_all_heights]
            all_right = [s['median_right'] for s in center_all_heights]
            
            center_stats = {
                'position': 'CENTER',
                'median_left': round(median(all_left), 2),
                'median_right': round(median(all_right), 2),
                'avg_left': round(mean(all_left), 2),
                'avg_right': round(mean(all_right), 2),
                'gap': round(median([s['gap'] for s in center_all_heights]), 2),
                'dominant': center_all_heights[0]['dominant'],
                'heights': center_all_heights,
                'samples_left': sum(s['samples_left'] for s in center_all_heights),
                'samples_right': sum(s['samples_right'] for s in center_all_heights),
            }
            
            print(f"\n CENTER (aggregated across {len(center_all_heights)} heights):")
            print(f"   Median Left: {center_stats['median_left']:.1f} dBm")
            print(f"   Median Right: {center_stats['median_right']:.1f} dBm")
            print(f"   Gap: {center_stats['gap']:.1f} dB")
        else:
            center_stats = None
    else:
        input("Press Enter when beacon is positioned at CENTER...")
        center_samples = live_signal_meter(db, args.mac, args.duration)
        center_stats = analyze_samples(center_samples, "CENTER")
    
    if not center_stats:
        print("\n CENTER calibration failed! Cannot proceed without center data.")
        return
    
    # ===== STEP 2: LEFT CALIBRATION =====
    print("\n" + "="*70)
    print("STEP 2: LEFT CALIBRATION")
    print("="*70)
    print("Place the beacon close to the LEFT/INNER scanner.")
    print("This teaches the system what strong-left looks like.\n")
    
    left_all_heights = []
    
    if args.heights:
        for height_name, height_desc in heights:
            print(f"\n HEIGHT: {height_name}")
            print(f"Place beacon at LEFT at {height_desc}")
            input("Press Enter to start sampling...")
            
            samples = live_signal_meter(db, args.mac, args.duration)
            stats = analyze_samples(samples, f"LEFT-{height_name}")
            
            if stats:
                stats['height'] = height_name
                left_all_heights.append(stats)
        
        if left_all_heights:
            all_left = [s['median_left'] for s in left_all_heights]
            all_right = [s['median_right'] for s in left_all_heights]
            
            left_stats = {
                'position': 'LEFT',
                'median_left': round(median(all_left), 2),
                'median_right': round(median(all_right), 2),
                'avg_left': round(mean(all_left), 2),
                'avg_right': round(mean(all_right), 2),
                'gap': round(median([s['gap'] for s in left_all_heights]), 2),
                'dominant': left_all_heights[0]['dominant'],
                'heights': left_all_heights,
                'samples_left': sum(s['samples_left'] for s in left_all_heights),
                'samples_right': sum(s['samples_right'] for s in left_all_heights),
            }
            
            print(f"\n LEFT (aggregated across {len(left_all_heights)} heights):")
            print(f"   Median Left: {left_stats['median_left']:.1f} dBm")
            print(f"   Median Right: {left_stats['median_right']:.1f} dBm")
            print(f"   Gap: {left_stats['gap']:.1f} dB")
        else:
            left_stats = None
    else:
        input("Press Enter when beacon is positioned at LEFT...")
        left_samples = live_signal_meter(db, args.mac, args.duration)
        left_stats = analyze_samples(left_samples, "LEFT")
    
    # ===== STEP 3: RIGHT CALIBRATION =====
    print("\n" + "="*70)
    print("STEP 3: RIGHT CALIBRATION")
    print("="*70)
    print("Place the beacon close to the RIGHT/OUTER scanner.")
    print("This teaches the system what strong-right looks like.\n")
    
    right_all_heights = []
    
    if args.heights:
        for height_name, height_desc in heights:
            print(f"\n HEIGHT: {height_name}")
            print(f"Place beacon at RIGHT at {height_desc}")
            input("Press Enter to start sampling...")
            
            samples = live_signal_meter(db, args.mac, args.duration)
            stats = analyze_samples(samples, f"RIGHT-{height_name}")
            
            if stats:
                stats['height'] = height_name
                right_all_heights.append(stats)
        
        if right_all_heights:
            all_left = [s['median_left'] for s in right_all_heights]
            all_right = [s['median_right'] for s in right_all_heights]
            
            right_stats = {
                'position': 'RIGHT',
                'median_left': round(median(all_left), 2),
                'median_right': round(median(all_right), 2),
                'avg_left': round(mean(all_left), 2),
                'avg_right': round(mean(all_right), 2),
                'gap': round(median([s['gap'] for s in right_all_heights]), 2),
                'dominant': right_all_heights[0]['dominant'],
                'heights': right_all_heights,
                'samples_left': sum(s['samples_left'] for s in right_all_heights),
                'samples_right': sum(s['samples_right'] for s in right_all_heights),
            }
            
            print(f"\n RIGHT (aggregated across {len(right_all_heights)} heights):")
            print(f"   Median Left: {right_stats['median_left']:.1f} dBm")
            print(f"   Median Right: {right_stats['median_right']:.1f} dBm")
            print(f"   Gap: {right_stats['gap']:.1f} dB")
        else:
            right_stats = None
    else:
        input("Press Enter when beacon is positioned at RIGHT...")
        right_samples = live_signal_meter(db, args.mac, args.duration)
        right_stats = analyze_samples(right_samples, "RIGHT")
    
    # ===== CALCULATE OFFSETS =====
    print("\n" + "="*70)
    print("CALCULATING RSSI OFFSETS")
    print("="*70)
    
    offsets_data = calculate_offsets(center_stats, left_stats, right_stats)
    
    if not offsets_data:
        print("\n Failed to calculate offsets!")
        return
    
    # ===== SAVE CALIBRATION =====
    calib_data = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'beacon_mac': args.mac,
        'duration_per_position_s': args.duration,
        'center': center_stats,
        'left': left_stats,
        'right': right_stats,
        **offsets_data
    }
    
    # Save to session directory
    calib_file = os.path.join(session_dir, 'door_lr_calib.json')
    with open(calib_file, 'w') as f:
        json.dump(calib_data, f, indent=2)
    
    # Save to latest directory (this is what the system will load)
    latest_file = os.path.join(latest_dir, 'door_lr_calib.json')
    with open(latest_file, 'w') as f:
        json.dump(calib_data, f, indent=2)
    
    print(f"\n Calibration saved to:")
    print(f"   Session: {calib_file}")
    print(f"   Latest:  {latest_file}")
    
    # ===== GENERATE PLOTS =====
    plots_dir = os.path.join(session_dir, 'plots')
    os.makedirs(plots_dir, exist_ok=True)
    
    # Plot 1: RSSI comparison across positions
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    positions = ['CENTER', 'LEFT', 'RIGHT']
    stats_list = [center_stats, left_stats, right_stats]
    
    for ax, pos, stats in zip(axes, positions, stats_list):
        if stats:
            labels = ['Left Scanner', 'Right Scanner']
            medians = [stats['median_left'], stats['median_right']]
            colors = ['tab:blue', 'tab:orange']
            
            bars = ax.bar(labels, medians, color=colors, alpha=0.7)
            ax.set_ylabel('RSSI (dBm)')
            ax.set_title(f'{pos} Position')
            ax.axhline(y=0, color='k', linestyle='-', linewidth=0.5)
            ax.grid(axis='y', alpha=0.3)
            
            # Add value labels on bars
            for bar, val in zip(bars, medians):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                       f'{val:.1f}', ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'rssi_by_position.png'), dpi=140)
    plt.close()

    # Plot 2: Gap comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    gaps = [center_stats['gap'], left_stats['gap'] if left_stats else 0, right_stats['gap'] if right_stats else 0]
    colors_gap = ['green' if g < 3 else 'orange' if g < 6 else 'red' for g in gaps]
    
    bars = ax.bar(positions, gaps, color=colors_gap, alpha=0.7)
    ax.set_ylabel('Gap |L-R| (dB)')
    ax.set_title('RSSI Gap by Position')
    ax.axhline(y=3, color='orange', linestyle='--', linewidth=1, label='Target: <3 dB at center')
    ax.axhline(y=6, color='red', linestyle='--', linewidth=1, label='Expected: ≥6 dB at sides')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    for bar, val in zip(bars, gaps):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.3,
               f'{val:.1f} dB', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'gap_comparison.png'), dpi=140)
    plt.close()

    # Plot 3: Raw RSSI distribution
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    for ax, pos, stats in zip(axes, positions, stats_list):
        if stats and 'raw_left' in stats and 'raw_right' in stats:
            ax.hist(stats['raw_left'], bins=20, alpha=0.6, label='Left', color='tab:blue')
            ax.hist(stats['raw_right'], bins=20, alpha=0.6, label='Right', color='tab:orange')
            ax.set_xlabel('RSSI (dBm)')
            ax.set_ylabel('Frequency')
            ax.set_title(f'{pos} - Raw RSSI Distribution')
            ax.legend()
            ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'rssi_distributions.png'), dpi=140)
    plt.close()

    print(f"\n Plots saved to: {plots_dir}/")
    
    # ===== VALIDATION & RECOMMENDATIONS =====
    print("\n" + "="*70)
    print("CALIBRATION QUALITY ASSESSMENT")
    print("="*70)
    
    issues = []
    recommendations = []
    
    # Check center calibration quality
    if center_stats['gap'] > 3.0:
        issues.append(f" Center gap is {center_stats['gap']:.1f} dB (should be <3 dB)")
        recommendations.append("   → Reposition beacon closer to true center")
        recommendations.append("   → Check for physical obstacles or reflections")
    else:
        print(f" Center gap: {center_stats['gap']:.1f} dB (Good)")
    
    # Check left/right separation
    if left_stats and left_stats['gap'] < 6.0:
        issues.append(f" Left position gap is {left_stats['gap']:.1f} dB (should be ≥6 dB)")
        recommendations.append("   → Move beacon closer to left scanner")
    elif left_stats:
        print(f" Left separation: {left_stats['gap']:.1f} dB (Good)")
    
    if right_stats and right_stats['gap'] < 6.0:
        issues.append(f" Right position gap is {right_stats['gap']:.1f} dB (should be ≥6 dB)")
        recommendations.append("   → Move beacon closer to right scanner")
    elif right_stats:
        print(f" Right separation: {right_stats['gap']:.1f} dB (Good)")
    
    # Check sample counts
    min_samples = 20
    if center_stats['samples_left'] < min_samples or center_stats['samples_right'] < min_samples:
        issues.append(f" Low sample count at center (L:{center_stats['samples_left']}, R:{center_stats['samples_right']})")
        recommendations.append("   → Increase --duration or check scanner connectivity")
    
    if issues:
        print("\n ISSUES DETECTED:")
        for issue in issues:
            print(issue)
        print("\nRECOMMENDATIONS:")
        for rec in recommendations:
            print(rec)
        print("\nConsider re-running calibration with adjustments.")
    else:
        print("\n Calibration quality is GOOD!")
    
    # ===== SUMMARY =====
    print("\n" + "="*70)
    print("CALIBRATION SUMMARY")
    print("="*70)
    print(f"\nRSSI Offsets (to be applied by DirectionClassifier):")
    print(f"  Left/Inner:  {offsets_data['rssi_offsets']['gate-left']:+.2f} dB")
    print(f"  Right/Outer: {offsets_data['rssi_offsets']['gate-right']:+.2f} dB")
    
    if 'thresholds' in offsets_data and offsets_data['thresholds']:
        print(f"\nLearned Thresholds (after offset correction):")
        t = offsets_data['thresholds']
        if 'strong_left' in t:
            print(f"  Strong LEFT signal:  {t['strong_left']:.1f} dBm")
        if 'strong_right' in t:
            print(f"  Strong RIGHT signal: {t['strong_right']:.1f} dBm")
        if 'left_dominance' in t:
            print(f"  LEFT dominance:      {t['left_dominance']:.1f} dB")
        if 'right_dominance' in t:
            print(f"  RIGHT dominance:     {t['right_dominance']:.1f} dB")
    
    print(f"\n Calibration files:")
    print(f"   {latest_file}")
    print(f"   {calib_file}")
    
    print("\n" + "="*70)
    print(" CALIBRATION COMPLETE!")
    print("="*70)
    print("\nNext steps:")
    print("1. Review plots in: " + plots_dir + "/")
    print("2. Restart boat_tracking_system.py to apply new calibration")
    print("3. Test with simulator: python3 door_lr_simulator.py --test-movements 3")
    print("\nThe system will now use these offsets for real-time signal equalization.")


if __name__ == '__main__':
    main()

