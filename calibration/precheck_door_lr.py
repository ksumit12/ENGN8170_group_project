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
from typing import List, Tuple

from app.database_models import DatabaseManager


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Door L/R geometry precheck")
    ap.add_argument('--mac', required=True, help='Beacon MAC (AA:BB:...)')
    ap.add_argument('--hold', type=float, default=5.0, help='Seconds per placement')
    args = ap.parse_args()

    db = DatabaseManager()

    print("Precheck – Make sure dual monitor/scanners are posting to the API.")
    print("Step 1 – CENTER: place beacon on the line, press Enter to start…")
    input()
    center = live_meter(db, args.mac, duration_s=args.hold)
    gap_c, var_c, dom_c = stats(center)
    print(f"Center: gap={gap_c:.1f} dB, var≈{var_c:.1f} dB")

    print("Step 2 – LEFT side: hold closer to LEFT/Inner, press Enter to start…")
    input()
    leftp = live_meter(db, args.mac, duration_s=args.hold)
    gap_l, var_l, dom_l = stats(leftp)
    print(f"Left bias: gap={gap_l:.1f} dB, var≈{var_l:.1f} dB, dominant={'LEFT' if dom_l>0 else 'RIGHT'}")

    print("Step 3 – RIGHT side: hold closer to RIGHT/Outer, press Enter to start…")
    input()
    rightp = live_meter(db, args.mac, duration_s=args.hold)
    gap_r, var_r, dom_r = stats(rightp)
    print(f"Right bias: gap={gap_r:.1f} dB, var≈{var_r:.1f} dB, dominant={'LEFT' if dom_r>0 else 'RIGHT'}")

    # Verdict rules
    ok_center = gap_c < 3.0
    ok_left = gap_l >= 6.0 and dom_l > 0
    ok_right = gap_r >= 6.0 and dom_r < 0
    all_ok = ok_center and ok_left and ok_right

    print("\nVerdict:")
    print(f"  Center gap < 3 dB …… {'OK' if ok_center else 'NO'} (got {gap_c:.1f} dB)")
    print(f"  Left bias gap ≥ 6 dB …… {'OK' if ok_left else 'NO'} (got {gap_l:.1f} dB)")
    print(f"  Right bias gap ≥ 6 dB … {'OK' if ok_right else 'NO'} (got {gap_r:.1f} dB)")
    print(f"\nReady for calibration: {'YES' if all_ok else 'NO'}")


if __name__ == '__main__':
    main()


