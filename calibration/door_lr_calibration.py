#!/usr/bin/env python3
"""
Door L/R Calibration Tool: guides operator through multiple dry runs and
derives parameters + consistency score. Stores raw samples and summary.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from statistics import mean
import math

import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='system/json/scanner_config.door_left_right.json')
    ap.add_argument('--samples', type=int, default=600)
    ap.add_argument('--max-lag', type=float, default=0.6)
    ap.add_argument('--runs', type=int, default=8, help='Total dry runs (half ENTER, half LEAVE)')
    ap.add_argument('--outdir', default='calibration/sessions')
    args = ap.parse_args()

    # Prepare session folder
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    session_dir = os.path.join(args.outdir, ts)
    os.makedirs(session_dir, exist_ok=True)

    print("Door L/R Calibration")
    print("- Perform dry runs with a single beacon.")
    print("- Half ENTER (outside->inside), half LEAVE (inside->outside).")
    print("- The script captures detection history from DB for the active beacon.")

    # Minimal interactive: operator provides the active beacon MAC and which direction for each run
    beacon_mac = input("Enter beacon MAC to calibrate (format AA:BB:...): ").strip()
    directions = []
    for i in range(args.runs):
        while True:
            d = input(f"Run {i+1}/{args.runs} direction [ENTER/LEAVE or R to redo previous]: ").strip().upper()
            if d == 'R' and directions:
                directions.pop()
                i -= 2  # redo previous iteration
                break
            if d in ('ENTER', 'LEAVE'):
                directions.append(d)
                break
            print("Please type ENTER or LEAVE")

    # Load detections for each run window by prompting operator to press Enter to start/stop
    from app.database_models import DatabaseManager
    db = DatabaseManager()

    run_summaries = []
    plots_dir = os.path.join(session_dir, 'plots')
    os.makedirs(plots_dir, exist_ok=True)
    for idx, d in enumerate(directions, start=1):
        input(f"Prepare for dry run {idx} ({d}). Press Enter to START...")
        t_start = datetime.now(timezone.utc)
        input("Walk through the door now with the beacon. Press Enter to STOP...")
        t_end = datetime.now(timezone.utc)

        # Query detections in window for this beacon
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT scanner_id, rssi, strftime('%s', timestamp) AS ts
                FROM detections d
                JOIN beacons b ON b.id = d.beacon_id
                WHERE b.mac_address = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
                """,
                (beacon_mac, t_start, t_end),
            )
            rows = c.fetchall()
        # Derive simple features: which side leads by first strong crossing and lags
        left_ts = []
        right_ts = []
        left_points = []  # (t, rssi)
        right_points = []
        for scanner_id, rssi, ts in rows:
            sid = (scanner_id or '').lower()
            tsec = float(ts)
            if sid.endswith('left') or sid.endswith('door-left') or sid.endswith('gate-left') or 'inner' in sid:
                left_ts.append(tsec)
                left_points.append((tsec, int(rssi)))
            if sid.endswith('right') or sid.endswith('door-right') or sid.endswith('gate-right') or 'outer' in sid:
                right_ts.append(tsec)
                right_points.append((tsec, int(rssi)))
        tL = left_ts[0] if left_ts else None
        tR = right_ts[0] if right_ts else None
        lag = (tR - tL) if (tL is not None and tR is not None) else None
        leader = None
        if lag is not None:
            if lag > 0:
                leader = 'LEFT'
            elif lag < 0:
                leader = 'RIGHT'
        score = 1.0 if lag is not None else 0.0
        run_summaries.append({
            'direction': d,
            't_start': t_start.isoformat(),
            't_end': t_end.isoformat(),
            'lag_s': lag,
            'leader': leader,
            'samples': len(rows),
            'score': score,
        })

        # Save raw for run
        with open(os.path.join(session_dir, f'run_{idx:02d}.json'), 'w') as f:
            json.dump({'direction': d, 'detections': rows}, f, indent=2)

        # Save CSV for run
        with open(os.path.join(session_dir, f'run_{idx:02d}.csv'), 'w') as f:
            f.write('scanner_id,rssi,timestamp_s\n')
            for scanner_id, rssi, ts in rows:
                f.write(f"{scanner_id},{rssi},{ts}\n")

        # Plot RSSI time series (relative to start)
        def _rel(points):
            if not points:
                return [], []
            base = min(p[0] for p in points)
            xs = [p[0] - t_start.timestamp() for p in points]
            ys = [p[1] for p in points]
            return xs, ys
        Lx, Ly = _rel(sorted(left_points))
        Rx, Ry = _rel(sorted(right_points))
        plt.figure(figsize=(8, 4))
        if Lx:
            plt.plot(Lx, Ly, label='Left/Inner', color='tab:blue')
        if Rx:
            plt.plot(Rx, Ry, label='Right/Outer', color='tab:orange')
        # Vertical lines at first detection times (relative)
        if tL is not None:
            plt.axvline(tL - t_start.timestamp(), color='tab:blue', linestyle='--', alpha=0.6)
        if tR is not None:
            plt.axvline(tR - t_start.timestamp(), color='tab:orange', linestyle='--', alpha=0.6)
        ttl = f"Run {idx} {d} | lag={round(lag,3) if lag is not None else 'na'} s | leader={leader or 'na'}"
        plt.title(ttl)
        plt.xlabel('Time since start (s)')
        plt.ylabel('RSSI (dBm)')
        plt.legend(loc='best')
        plt.grid(alpha=0.2)
        plt.tight_layout()
        plt.savefig(os.path.join(plots_dir, f'run_{idx:02d}_timeseries.png'), dpi=140)
        plt.close()

    # Aggregate calibration
    lags = [r['lag_s'] for r in run_summaries if r['lag_s'] is not None]
    pos = sum(1 for l in lags if l is not None and l > 0)
    neg = sum(1 for l in lags if l is not None and l < 0)
    lag_positive = 'LEAVE' if pos >= neg else 'ENTER'
    lag_negative = 'ENTER' if lag_positive == 'LEAVE' else 'LEAVE'
    tau_vals = [abs(l) for l in lags if l is not None]
    tau_min = round(min(tau_vals), 3) if tau_vals else 0.12
    consistency = round((pos + neg) / max(len(run_summaries), 1), 2)

    summary = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'beacon_mac': beacon_mac,
        'runs': len(run_summaries),
        'lag_positive': lag_positive,
        'lag_negative': lag_negative,
        'min_confidence_tau_s': tau_min,
        'consistency_score': consistency,
        'run_summaries': run_summaries,
    }

    # Aggregate plots: lag histogram & per-direction consistency
    if lags:
        plt.figure(figsize=(6, 4))
        plt.hist([l for l in lags if l is not None], bins=max(5, min(20, len(lags)//1)), color='tab:purple', alpha=0.8)
        plt.axvline(0.0, color='k', linestyle='--', linewidth=1)
        plt.title('Lag distribution (Right - Left) [s]')
        plt.xlabel('Lag (s)')
        plt.ylabel('Count')
        plt.tight_layout()
        plt.savefig(os.path.join(plots_dir, 'lag_histogram.png'), dpi=140)
        plt.close()

    # Direction success bars
    enter_runs = [r for r in run_summaries if r['direction'] == 'ENTER']
    leave_runs = [r for r in run_summaries if r['direction'] == 'LEAVE']
    enter_ok = sum(1 for r in enter_runs if r['lag_s'] is not None)
    leave_ok = sum(1 for r in leave_runs if r['lag_s'] is not None)
    plt.figure(figsize=(5, 4))
    labels = ['ENTER', 'LEAVE']
    vals = [enter_ok / max(len(enter_runs), 1), leave_ok / max(len(leave_runs), 1)]
    plt.bar(labels, vals, color=['tab:green', 'tab:red'])
    plt.ylim(0, 1)
    plt.ylabel('Fraction with valid lag')
    plt.title('Per-direction consistency')
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'consistency_bars.png'), dpi=140)
    plt.close()

    # Write session summary and update latest symlink/copy
    out_path = os.path.join(session_dir, 'door_lr_calib.json')
    with open(out_path, 'w') as f:
        json.dump(summary, f, indent=2)

    # CSV export of run summaries
    with open(os.path.join(session_dir, 'run_summaries.csv'), 'w') as f:
        f.write('idx,direction,t_start,t_end,lag_s,leader,samples,score\n')
        for i, r in enumerate(run_summaries, start=1):
            f.write(f"{i},{r['direction']},{r['t_start']},{r['t_end']},{'' if r['lag_s'] is None else r['lag_s']},{r['leader']},{r['samples']},{r['score']}\n")

    latest_dir = os.path.join(args.outdir, 'latest')
    os.makedirs(latest_dir, exist_ok=True)
    with open(os.path.join(latest_dir, 'door_lr_calib.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"Calibration written to {out_path}")


if __name__ == '__main__':
    main()


