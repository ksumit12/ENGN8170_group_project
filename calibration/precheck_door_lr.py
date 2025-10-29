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
import sqlite3

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
    try:
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
    except sqlite3.Error as e:
        # Gracefully degrade when DB or table isn't ready
        print(f"[DB unavailable] {e}. Tip: start scanners or use --scan for direct BLE.")
        return []


def stats(readings: List[Tuple[str, int]], *, min_samples: int = 3) -> Tuple[float, float, float, int, int, float, float]:
    """Return (gap_db, variance_db, dominance, n_left, n_right, medL, medR).

    dominance: +1 for LEFT>RIGHT, -1 for RIGHT>LEFT, 0 for no data or tie.
    When either side has < min_samples, treat dominance as NONE (0) and gap=0.
    """
    L = [r for sid, r in readings if 'left' in (sid or '').lower() or 'inner' in (sid or '').lower()]
    R = [r for sid, r in readings if 'right' in (sid or '').lower() or 'outer' in (sid or '').lower()]
    if len(L) < min_samples or len(R) < min_samples:
        # medians may be undefined; return 0 with counts
        medL = median(L) if L else 0.0
        medR = median(R) if R else 0.0
        return 0.0, 0.0, 0.0, len(L), len(R), float(medL), float(medR)
    try:
        medL = median(L)
        medR = median(R)
        gap = abs(medL - medR)
        v = (pstdev(L) + pstdev(R)) / 2.0
        dom = 1.0 if medL > medR else (-1.0 if medR > medL else 0.0)
        return gap, v, dom, len(L), len(R), float(medL), float(medR)
    except Exception:
        medL = median(L) if L else 0.0
        medR = median(R) if R else 0.0
        return 0.0, 0.0, 0.0, len(L), len(R), float(medL), float(medR)


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
                # Prefer AdvertisementData.rssi; fall back to device.rssi when missing
                rssi_val = getattr(advertisement_data, 'rssi', None)
                if rssi_val is None:
                    rssi_val = getattr(device, 'rssi', None)
                if rssi_val is None:
                    return  # skip no-signal samples to avoid bias
                rssi = int(rssi_val)
            except Exception:
                return
            readings.append((store_scanner_id, rssi))
        return _cb

    # Use modern BleakScanner API with detection_callback to avoid deprecation warnings
    inner = BleakScanner(detection_callback=make_cb('door-left'), adapter=inner_adapter)
    outer = BleakScanner(detection_callback=make_cb('door-right'), adapter=outer_adapter)

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
    ap.add_argument('--precision-tol-db', type=float, default=1.0, help='Precision tolerance window around median gap (±dB)')
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
        gap_c, var_c, dom_c, nL_c, nR_c, medL_c, medR_c = stats(center)
        dom_c_lbl = 'LEFT' if dom_c>0 else ('RIGHT' if dom_c<0 else 'NONE')
        center_gaps.append(gap_c); center_dom.append(dom_c_lbl)
        print(f"Center: gap={gap_c:.1f} dB, var≈{var_c:.1f} dB, dominant={dom_c_lbl} (nL={nL_c}, nR={nR_c})  medL={medL_c:.1f} medR={medR_c:.1f}")

        print("Step 2 – LEFT side: hold closer to LEFT/Inner, press Enter to start…")
        input()
        leftp = scan_window(args.inner, args.outer, args.mac, args.hold) if (args.scan and BleakScanner) else live_meter(db, args.mac, duration_s=args.hold)
        gap_l, var_l, dom_l, nL_l, nR_l, medL_l, medR_l = stats(leftp)
        left_gaps.append(gap_l)
        dom_l_lbl = 'LEFT' if dom_l>0 else ('RIGHT' if dom_l<0 else 'NONE')
        print(f"Left bias: gap={gap_l:.1f} dB, var≈{var_l:.1f} dB, dominant={dom_l_lbl} (nL={nL_l}, nR={nR_l})  medL={medL_l:.1f} medR={medR_l:.1f}")

        print("Step 3 – RIGHT side: hold closer to RIGHT/Outer, press Enter to start…")
        input()
        rightp = scan_window(args.inner, args.outer, args.mac, args.hold) if (args.scan and BleakScanner) else live_meter(db, args.mac, duration_s=args.hold)
        gap_r, var_r, dom_r, nL_r, nR_r, medL_r, medR_r = stats(rightp)
        right_gaps.append(gap_r)
        dom_r_lbl = 'LEFT' if dom_r>0 else ('RIGHT' if dom_r<0 else 'NONE')
        print(f"Right bias: gap={gap_r:.1f} dB, var≈{var_r:.1f} dB, dominant={dom_r_lbl} (nL={nL_r}, nR={nR_r})  medL={medL_r:.1f} medR={medR_r:.1f}")

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

    # Precision metrics: fraction within ±tol of the median gap per placement
    tol = max(0.0, float(args.precision_tol_db))
    def precision_fraction(vals: list[float]) -> float:
        if not vals:
            return 0.0
        import statistics as _st
        m = _st.median(vals)
        hits = sum(1 for v in vals if abs(v - m) <= tol)
        return hits / max(1, len(vals))
    prec_center = precision_fraction(center_gaps)
    prec_left = precision_fraction(left_gaps)
    prec_right = precision_fraction(right_gaps)

    # Dominance precision (how consistently the same side dominates at center)
    dom_mode = None
    if center_dom:
        from collections import Counter as _Counter
        cnt = _Counter(center_dom)
        dom_mode, mode_n = max(cnt.items(), key=lambda kv: kv[1])
        dom_prec = mode_n / max(1, len(center_dom))
    else:
        dom_prec = 0.0
    print("\nPrecision (repeatability):")
    print(f"  Center precision (±{tol:.1f} dB of median): {prec_center*100:.1f}%")
    print(f"  Left precision   (±{tol:.1f} dB of median): {prec_left*100:.1f}%")
    print(f"  Right precision  (±{tol:.1f} dB of median): {prec_right*100:.1f}%")
    if dom_mode:
        print(f"  Center dominance consistency: {dom_prec*100:.1f}% (mode={dom_mode})")

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
            'ready': all_ok,
            'precision_tol_db': tol,
            'precision_center': prec_center,
            'precision_left': prec_left,
            'precision_right': prec_right,
            'dominance_mode': dom_mode,
            'dominance_precision': dom_prec
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

    # Precision bars plot
    plt.figure(figsize=(5,4))
    labels=['Center','Left','Right']
    vals=[prec_center, prec_left, prec_right]
    plt.bar(labels, vals, color=['tab:blue','tab:green','tab:red'])
    plt.ylim(0,1); plt.ylabel('Precision (fraction within ±%.1f dB)' % tol); plt.title('Repeatability precision')
    plt.tight_layout(); plt.savefig(os.path.join(out_dir, 'precision_bars.png'), dpi=140); plt.close()


if __name__ == '__main__':
    main()


