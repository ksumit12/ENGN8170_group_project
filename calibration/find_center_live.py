#!/usr/bin/env python3
"""
Find Center (Live Helper)

Purpose
- Continuously compute the LEFT/RIGHT median RSSI and the gap for a target beacon
  so you can physically move the beacon until the gap is near zero.
- Announces when the gap stays within a tolerance for a stability window to
  indicate a good "center" measurement. Optionally writes suggested RSSI offsets
  into calibration/door_lr_calib.json.

Data source
- Uses recent detections from the local database (posted by your scanners).

Usage
  source .venv/bin/activate
  python3 calibration/find_center_live.py --mac AA:BB:CC:DD:EE:FF \
      [--tol-db 2.0] [--window-s 2.0] [--stable-s 5.0] [--save-offsets]

Notes
- "Center" is when |median(L) - median(R)| <= tol_db and both sides have
  enough samples.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from statistics import median, pstdev
from typing import List, Tuple, Optional

from app.database_models import DatabaseManager
import sqlite3

# Optional direct scanning (Bleak)
try:
    from bleak import BleakScanner  # type: ignore
except Exception:
    BleakScanner = None  # noqa


def fetch_recent(db: DatabaseManager, mac: str, seconds: float = 2.0) -> List[Tuple[str, int]]:
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT d.scanner_id, d.rssi
                FROM detections d
                JOIN beacons b ON b.id = d.beacon_id
                WHERE b.mac_address = ? AND d.timestamp > datetime('now', ?)
                ORDER BY d.timestamp DESC LIMIT 400
                """,
                (mac, f"-{int(max(1, seconds))} seconds"),
            )
            rows = c.fetchall()
        return [(str(sid or ''), int(rssi)) for sid, rssi in rows]
    except sqlite3.Error as e:
        print(f"[DB unavailable] {e}. Tip: start scanners or use --scan for direct BLE.")
        return []


def compute_stats(readings: List[Tuple[str, int]], min_samples: int = 4, *, offsets: Optional[dict] = None):
    L = [r for sid, r in readings if 'left' in (sid or '').lower() or 'inner' in (sid or '').lower()]
    R = [r for sid, r in readings if 'right' in (sid or '').lower() or 'outer' in (sid or '').lower()]
    # Apply symmetric offsets if provided to emulate runtime equalization
    offL = 0.0
    offR = 0.0
    if offsets and isinstance(offsets.get('rssi_offsets'), dict):
        offL = float(offsets['rssi_offsets'].get('door-left', 0.0) or 0.0)
        offR = float(offsets['rssi_offsets'].get('door-right', 0.0) or 0.0)
    if L:
        L = [r - offL for r in L]
    if R:
        R = [r - offR for r in R]
    if len(L) < min_samples or len(R) < min_samples:
        return {
            'medL': float(median(L)) if L else None,
            'medR': float(median(R)) if R else None,
            'gap': None,
            'var': None,
            'dom': None,
            'nL': len(L),
            'nR': len(R),
        }
    medL = median(L)
    medR = median(R)
    gap = abs(medL - medR)
    var = (pstdev(L) + pstdev(R)) / 2.0 if len(L) > 1 and len(R) > 1 else 0.0
    dom = 'LEFT' if medL > medR else ('RIGHT' if medR > medL else 'NONE')
    return {
        'medL': float(medL),
        'medR': float(medR),
        'gap': float(gap),
        'var': float(var),
        'dom': dom,
        'nL': len(L),
        'nR': len(R),
    }


def scan_once(inner_adapter: str, outer_adapter: str, mac: str, duration_s: float = 2.0) -> List[Tuple[str, int]]:
    """Direct BLE scan for a short window; returns [(scanner_id, rssi)]."""
    if BleakScanner is None:
        return []

    readings: List[Tuple[str, int]] = []

    def make_cb(store_scanner_id: str):
        def _cb(device, advertisement_data):
            if (device.address or '').lower() != mac.lower():
                return
            try:
                rssi_val = getattr(advertisement_data, 'rssi', None)
                if rssi_val is None:
                    rssi_val = getattr(device, 'rssi', None)
                if rssi_val is None:
                    return
                readings.append((store_scanner_id, int(rssi_val)))
            except Exception:
                pass
        return _cb

    inner = BleakScanner(detection_callback=make_cb('door-left'), adapter=inner_adapter)
    outer = BleakScanner(detection_callback=make_cb('door-right'), adapter=outer_adapter)

    import asyncio
    async def run_once():
        await inner.start(); await outer.start()
        try:
            await asyncio.sleep(max(0.2, duration_s))
        finally:
            await inner.stop(); await outer.stop()

    try:
        import contextlib
        asyncio.run(run_once())
    except Exception:
        pass
    return readings


def maybe_write_offsets(calib_path: str, medL: float, medR: float) -> None:
    # We define offsets such that L' = L - offL and R' = R - offR make medL' ~= medR'.
    # Choose symmetric offsets: offL = +delta/2, offR = -delta/2 where delta = medL - medR
    delta = medL - medR
    offL = +delta / 2.0
    offR = -delta / 2.0
    try:
        data = {}
        if os.path.exists(calib_path):
            with open(calib_path, 'r') as f:
                data = json.load(f)
        data.setdefault('rssi_offsets', {})
        data['rssi_offsets']['door-left'] = round(data['rssi_offsets'].get('door-left', 0.0) + offL, 2)
        data['rssi_offsets']['door-right'] = round(data['rssi_offsets'].get('door-right', 0.0) + offR, 2)
        os.makedirs(os.path.dirname(calib_path), exist_ok=True)
        with open(calib_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved suggested offsets to {calib_path}: L={data['rssi_offsets']['door-left']} dB, R={data['rssi_offsets']['door-right']} dB")
    except Exception as e:
        print(f"Failed to write calibration file: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description='Live center finder (DB or direct BLE)')
    ap.add_argument('--mac', required=True, help='Beacon MAC (AA:BB:...)')
    ap.add_argument('--window-s', type=float, default=2.0, help='Seconds of recent data for medians')
    ap.add_argument('--tol-db', type=float, default=2.0, help='Target |L-R| tolerance for center')
    ap.add_argument('--stable-s', type=float, default=5.0, help='Seconds gap must remain within tolerance')
    ap.add_argument('--min-samples', type=int, default=3, help='Minimum samples per side to compute gap (lower if signals are sparse)')
    ap.add_argument('--save-offsets', action='store_true', default=False, help='Write suggested RSSI offsets to calibration/door_lr_calib.json when stable')
    ap.add_argument('--apply-offsets', action='store_true', default=False, help='Apply saved rssi_offsets from calibration/door_lr_calib.json while computing gap')
    ap.add_argument('--scan', action='store_true', default=False, help='Use direct BLE scan instead of DB')
    ap.add_argument('--inner', default='hci1', help='Inner adapter (when --scan)')
    ap.add_argument('--outer', default='hci0', help='Outer adapter (when --scan)')
    args = ap.parse_args()

    db = DatabaseManager()

    stable_since = None
    last_announce = 0.0
    print("Move the beacon slowly; aim to keep gap near 0 dB. Press Ctrl+C to exit.")

    if args.scan and BleakScanner is None:
        print("--scan requested but bleak not available. Install with: pip install bleak")
        return

    try:
        while True:
            if args.scan:
                rs = scan_once(args.inner, args.outer, args.mac, duration_s=args.window_s)
            else:
                rs = fetch_recent(db, args.mac, seconds=args.window_s)
            # Load offsets once per loop if requested
            offs = None
            if args.apply_offsets:
                try:
                    with open(os.path.join('calibration','door_lr_calib.json'),'r') as f:
                        offs = json.load(f)
                except Exception:
                    offs = None
            st = compute_stats(rs, min_samples=max(1, int(args.min_samples)), offsets=offs)
            now = time.time()
            if not st or st.get('gap') is None:
                nL = st.get('nL', 0) if st else 0
                nR = st.get('nR', 0) if st else 0
                msg = f"waiting… need both sides | nL={nL} nR={nR}"
                if args.scan:
                    msg += " (direct scan)"
                else:
                    msg += " (from DB)"
                print("\r" + msg + " " * 20, end='', flush=True)
                time.sleep(0.25)
                continue

            gap = st['gap']
            medL = st['medL']
            medR = st['medR']
            dom = st['dom']
            nL = st['nL']
            nR = st['nR']
            msg = f"gap={gap:>4.1f} dB | L={medL:>5.1f} dB  R={medR:>5.1f} dB | dom={dom:>5s} (nL={nL}, nR={nR})"

            within = gap <= args.tol_db
            if within:
                stable_since = stable_since or now
            else:
                stable_since = None

            if stable_since and (now - stable_since) >= args.stable_s:
                if now - last_announce > 1.0:
                    print("\r" + msg + f"   -> CENTER LOCKED (≥{args.stable_s:.0f}s within ±{args.tol_db:.1f} dB)           ", end='', flush=True)
                    last_announce = now
                    if args.save_offsets:
                        calib_path = os.path.join('calibration', 'door_lr_calib.json')
                        maybe_write_offsets(calib_path, medL, medR)
            else:
                print("\r" + msg + " " * 20, end='', flush=True)

            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nDone.")


if __name__ == '__main__':
    main()


