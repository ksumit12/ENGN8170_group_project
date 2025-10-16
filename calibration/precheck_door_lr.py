#!/usr/bin/env python3
"""
Door L/R Precheck: quick geometry readiness test before full calibration.

What it does
- Guides you through 3 short placements with one beacon:
  1) Center line
  2) Near LEFT/Inner side
  3) Near RIGHT/Outer side
- Shows live signal percent, samples ~5s per placement, and computes:
  - median_rssi_gap_db (|median(L) - median(R)|)
  - side dominance (which side is stronger)
  - variance (movement/noise proxy)
- Verdict: GO if center gap < 3 dB AND both side placements have gap ≥ 6 dB.

Usage
  source .venv/bin/activate
  export PYTHONPATH="$(pwd)"
  python3 calibration/precheck_door_lr.py --mac DC:0D:30:23:05:47
"""
from __future__ import annotations

import argparse
import time
from statistics import median, pstdev
import os, json
from datetime import datetime, timezone

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from typing import List, Tuple

from app.database_models import DatabaseManager

# Optional live scanning (Bleak)
try:
    from bleak import BleakScanner  # type: ignore
except Exception:
    BleakScanner = None  # noqa


def signal_percent(rssi_dbm: float) -> int:
    if rssi_dbm is None:
        return 0
    return int(max(0, min(100, round((rssi_dbm + 100) * (100.0 / 60.0)))))


def fetch_recent(db: DatabaseManager, mac: str, seconds: float = 1.0) -> List[Tuple[str, int]]:
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT d.scanner_id, d.rssi
            FROM detections d
            JOIN beacons b ON b.id = d.beacon_id
            WHERE b.mac_address = ? AND d.timestamp > datetime('now', ?)
            ORDER BY d.timestamp DESC LIMIT 200
            """,
            (mac, f"-{int(max(1, seconds))} seconds"),
        )
        rows = c.fetchall()
    return [(str(sid or ''), int(rssi)) for sid, rssi in rows]


def stats(readings: List[Tuple[str, int]]) -> Tuple[float, float, float]:
    L = [r for sid, r in readings if 'left' in sid.lower() or 'inner' in sid.lower()]
    R = [r for sid, r in readings if 'right' in sid.lower() or 'outer' in sid.lower()]
    if not L or not R:
        return 0.0, 0.0, 0.0
    try:
        gap = abs(median(L) - median(R))
        v = (pstdev(L) + pstdev(R)) / 2.0
        dom = 1.0 if median(L) > median(R) else -1.0
        return gap, v, dom
    except Exception:
        return 0.0, 0.0, 0.0


def live_meter(db: DatabaseManager, mac: str, duration_s: float = 5.0) -> List[Tuple[str, int]]:
    buf: List[Tuple[str, int]] = []
    t0 = time.time()
    while time.time() - t0 < duration_s:
        rs = fetch_recent(db, mac, seconds=1)
        buf.extend(rs)
        # print single-line meter
        if rs:
            vals = [rssi for _, rssi in rs]
            avg = sum(vals) / max(1, len(vals))
            print(f"\rSignal: {signal_percent(avg)}%   ", end="", flush=True)
        else:
            print("\rSignal: 0%   ", end="", flush=True)
        time.sleep(0.5)
    print()
    return buf


def scan_window(inner_adapter: str, outer_adapter: str, mac: str, duration_s: float = 5.0) -> List[Tuple[str, int]]:
    """Scan directly from two adapters for a short window and return readings list.
    readings format: [(scanner_id, rssi), ...] with scanner_id in {'door-left','door-right'} semantics.
    """
    if BleakScanner is None:
        return []

    readings: List[Tuple[str, int]] = []
    stop_time = time.time() + duration_s

    def make_cb(store_scanner_id: str):
        def _cb(device, advertisement_data):
            if (device.address or '').lower() != mac.lower():
                return
            try:
                rssi = int(device.rssi or -100)
            except Exception:
                rssi = -100
            readings.append((store_scanner_id, rssi))
        return _cb

    inner = BleakScanner(adapter=inner_adapter)
    outer = BleakScanner(adapter=outer_adapter)
    inner.register_detection_callback(make_cb('door-left'))
    outer.register_detection_callback(make_cb('door-right'))

    import asyncio
    async def run_once():
        await inner.start(); await outer.start()
        try:
            while time.time() < stop_time:
                # Show single-line meter from last second of samples
                recent = readings[-40:]
                vals = [r for _, r in recent]
                if vals:
                    avg = sum(vals)/len(vals)
                    print(f"\rSignal: {signal_percent(avg)}%   ", end="", flush=True)
                else:
                    print(f"\rSignal: 0%   ", end="", flush=True)
                await asyncio.sleep(0.5)
        finally:
            await inner.stop(); await outer.stop()

    try:
        asyncio.run(run_once())
    except Exception:
        pass
    print()
    return readings


def main() -> None:
    ap = argparse.ArgumentParser(description="Door L/R geometry precheck")
    ap.add_argument('--mac', required=True, help='Beacon MAC (AA:BB:...)')
    ap.add_argument('--hold', type=float, default=5.0, help='Seconds per placement')
    ap.add_argument('--reps', type=int, default=1, help='Repeat center/left/right reps times and summarize')
    ap.add_argument('--scan', action='store_true', default=False, help='Scan directly (no DB)')
    ap.add_argument('--inner', default='hci1', help='Inner adapter for direct scan (requires --scan)')
    ap.add_argument('--outer', default='hci0', help='Outer adapter for direct scan (requires --scan)')
    args = ap.parse_args()

    db = DatabaseManager()

    if args.scan and BleakScanner is None:
        print("--scan requested but bleak not available. Install with: pip install bleak")
        return

    print("Precheck – " + ("scanning directly" if args.scan else "Make sure dual monitor/scanners are posting to the API."))

    # Session folder
    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join('calibration', 'sessions', f'precheck_{ts}')
    os.makedirs(out_dir, exist_ok=True)

    center_gaps: list[float] = []
    center_dom: list[str] = []
    left_gaps: list[float] = []
    right_gaps: list[float] = []

    for i in range(1, max(1, args.reps) + 1):
        print(f"\n[Rep {i}/{args.reps}] Step 1 – CENTER: place beacon on the line, press Enter to start…")
        input()
        center = scan_window(args.inner, args.outer, args.mac, args.hold) if (args.scan and BleakScanner) else live_meter(db, args.mac, duration_s=args.hold)
        gap_c, var_c, dom_c = stats(center)
        dom_c_lbl = 'LEFT' if dom_c>0 else ('RIGHT' if dom_c<0 else 'NONE')
        center_gaps.append(gap_c); center_dom.append(dom_c_lbl)
        print(f"Center: gap={gap_c:.1f} dB, var≈{var_c:.1f} dB, dominant={dom_c_lbl}")

        print("Step 2 – LEFT side: hold closer to LEFT/Inner, press Enter to start…")
        input()
        leftp = scan_window(args.inner, args.outer, args.mac, args.hold) if (args.scan and BleakScanner) else live_meter(db, args.mac, duration_s=args.hold)
        gap_l, var_l, dom_l = stats(leftp)
        left_gaps.append(gap_l)
        print(f"Left bias: gap={gap_l:.1f} dB, var≈{var_l:.1f} dB, dominant={'LEFT' if dom_l>0 else 'RIGHT'}")

        print("Step 3 – RIGHT side: hold closer to RIGHT/Outer, press Enter to start…")
        input()
        rightp = scan_window(args.inner, args.outer, args.mac, args.hold) if (args.scan and BleakScanner) else live_meter(db, args.mac, duration_s=args.hold)
        gap_r, var_r, dom_r = stats(rightp)
        right_gaps.append(gap_r)
        print(f"Right bias: gap={gap_r:.1f} dB, var≈{var_r:.1f} dB, dominant={'LEFT' if dom_r>0 else 'RIGHT'}")

    # Summary
    total = max(1, args.reps)
    ok_center = sum(1 for g in center_gaps if g < 3.0)
    ok_left = sum(1 for g in left_gaps if g >= 6.0)
    ok_right = sum(1 for g in right_gaps if g >= 6.0)
    all_ok = (ok_center==total and ok_left==total and ok_right==total)

    print("\nSummary across reps:")
    print(f"  Center OK (<3 dB): {ok_center}/{total}")
    print(f"  Left OK (≥6 dB):   {ok_left}/{total}")
    print(f"  Right OK (≥6 dB):  {ok_right}/{total}")
    print(f"\nReady for calibration: {'YES' if all_ok else 'NO'}")

    # Save JSON
    with open(os.path.join(out_dir, 'summary.json'), 'w') as f:
        json.dump({
            'created_at': datetime.now(timezone.utc).isoformat(),
            'mac': args.mac,
            'reps': total,
            'center_gaps_db': center_gaps,
            'center_dominant': center_dom,
            'left_gaps_db': left_gaps,
            'right_gaps_db': right_gaps,
            'ok_center': ok_center,
            'ok_left': ok_left,
            'ok_right': ok_right,
            'ready': all_ok
        }, f, indent=2)

    # Plots
    plt.figure(figsize=(5,4))
    labels=['Center<3','Left≥6','Right≥6']
    vals=[ok_center/total, ok_left/total, ok_right/total]
    plt.bar(labels, vals, color=['tab:blue','tab:green','tab:red'])
    plt.ylim(0,1); plt.ylabel('Fraction OK'); plt.title('Precheck consistency')
    plt.tight_layout(); plt.savefig(os.path.join(out_dir, 'consistency_bars.png'), dpi=140); plt.close()

    plt.figure(figsize=(6,4)); plt.hist(center_gaps, bins=min(10,total), alpha=0.8); plt.axvline(3.0, color='k', ls='--');
    plt.xlabel('Center gap (dB)'); plt.ylabel('Count'); plt.tight_layout(); plt.savefig(os.path.join(out_dir,'center_gap_hist.png'), dpi=140); plt.close()
    plt.figure(figsize=(6,4)); plt.hist(left_gaps, bins=min(10,total), alpha=0.8, color='tab:green'); plt.axvline(6.0, color='k', ls='--');
    plt.xlabel('Left gap (dB)'); plt.ylabel('Count'); plt.tight_layout(); plt.savefig(os.path.join(out_dir,'left_gap_hist.png'), dpi=140); plt.close()
    plt.figure(figsize=(6,4)); plt.hist(right_gaps, bins=min(10,total), alpha=0.8, color='tab:red'); plt.axvline(6.0, color='k', ls='--');
    plt.xlabel('Right gap (dB)'); plt.ylabel('Count'); plt.tight_layout(); plt.savefig(os.path.join(out_dir,'right_gap_hist.png'), dpi=140); plt.close()


if __name__ == '__main__':
    main()


