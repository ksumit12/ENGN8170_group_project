#!/usr/bin/env python3
"""
Dual-adapter iBeacon monitor for field testing.

What it does
 - Scans two BLE adapters (e.g., hci1=inner, hci0=outer) concurrently
 - Filters strictly for iBeacon frames (Apple company ID 0x004C, type 0x02/0x15)
 - Tracks one or more target beacons (by MAC or auto-detect strongest)
 - Prints continuous, compact console updates with per-adapter RSSI and distance
 - Optional CSV logging and optional POST to API /api/v1/detections

Usage examples
  python scripts/ibeacon_dual_monitor.py \
      --inner hci1 --outer hci0 --duration 0 \
      --target DC:0D:30:23:05:CF --interval 0.5

  # Auto-pick strongest iBeacon seen in the first few seconds
  python scripts/ibeacon_dual_monitor.py --inner hci1 --outer hci0 --autopick 3

  # Log to CSV
  python scripts/ibeacon_dual_monitor.py --inner hci1 --outer hci0 --csv /tmp/ibeacon_log.csv

  # Also post to API detections (if your server expects it)
  python scripts/ibeacon_dual_monitor.py --post http://127.0.0.1:8000 --api-key default-key

Notes
 - Requires bleak (already used in project). If missing: pip install bleak
 - Distance is a heuristic using measured_power (default -59 dBm) and path-loss model n≈2.0
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple, List

try:
    from bleak import BleakScanner
except Exception as e:  # pragma: no cover
    print("This tool needs 'bleak'. Install with: pip install bleak", file=sys.stderr)
    raise

try:
    import requests
except Exception:
    requests = None  # optional


APPLE_COMPANY_ID = 0x004C


@dataclass
class Reading:
    ts: float
    rssi: int
    distance_m: float


def is_ibeacon(advertisement_data) -> Tuple[bool, Optional[int]]:
    """Return (is_ibeacon, measured_power). bleak gives manufacturer_data {company_id: bytes}.
    iBeacon payload format (after company id):
      0x02 0x15 | 16B UUID | 2B major | 2B minor | 1B tx_power (signed)
    """
    m = advertisement_data.manufacturer_data or {}
    if APPLE_COMPANY_ID not in m:
        return False, None
    payload: bytes = m[APPLE_COMPANY_ID]
    if len(payload) < 23:
        return False, None
    if payload[0] != 0x02 or payload[1] != 0x15:
        return False, None
    tx_power = int.from_bytes(payload[-1:].ljust(1, b"\x00"), byteorder="big", signed=True)
    return True, tx_power


def estimate_distance(rssi: int, measured_power: int = -59, n: float = 2.0) -> float:
    """Simple path-loss model distance estimate in meters.
    distance = 10 ^ ((measured_power - rssi) / (10 * n))
    """
    try:
        return round(pow(10.0, (measured_power - rssi) / (10.0 * n)), 2)
    except Exception:
        return 0.0


class DualMonitor:
    def __init__(self, inner_adapter: str, outer_adapter: str, targets: List[str], autopick_s: float,
                 interval_s: float, csv_path: Optional[str], post_url: Optional[str], api_key: Optional[str]):
        self.inner_adapter = inner_adapter
        self.outer_adapter = outer_adapter
        self.targets = [t.strip().lower() for t in targets if t]
        self.autopick_s = max(0.0, autopick_s)
        self.interval_s = max(0.2, interval_s)
        self.csv_path = csv_path
        self.post_url = post_url.rstrip("/") if post_url else None
        self.api_key = api_key or "default-key"

        self._inner_readings: Dict[str, Reading] = {}
        self._outer_readings: Dict[str, Reading] = {}
        self._measured_power_by_mac: Dict[str, int] = {}
        self._stop = asyncio.Event()
        self._csv = None
        self._csv_writer = None

    async def start(self):
        if self.csv_path:
            self._csv = open(self.csv_path, "a", newline="")
            self._csv_writer = csv.writer(self._csv)
            if self._csv.tell() == 0:
                self._csv_writer.writerow(["ts", "mac", "adapter", "rssi", "distance_m"])  # header

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)

        inner_task = asyncio.create_task(self._scan_adapter(self.inner_adapter, is_inner=True))
        outer_task = asyncio.create_task(self._scan_adapter(self.outer_adapter, is_inner=False))
        printer = asyncio.create_task(self._printer())

        # optional autopick of a strong beacon in first few seconds
        if not self.targets and self.autopick_s > 0:
            await asyncio.sleep(self.autopick_s)
            pick = self._pick_strongest()
            if pick:
                self.targets = [pick]
                print(f"[autopick] Tracking strongest iBeacon: {pick}")

        await self._stop.wait()
        inner_task.cancel(); outer_task.cancel(); printer.cancel()
        for t in (inner_task, outer_task, printer):
            with contextlib.suppress(Exception):
                await t
        if self._csv:
            self._csv.close()

    def _pick_strongest(self) -> Optional[str]:
        best_mac = None
        best_rssi = -999
        for d in (self._inner_readings, self._outer_readings):
            for mac, r in d.items():
                if r.rssi > best_rssi:
                    best_rssi = r.rssi
                    best_mac = mac
        return best_mac

    async def _scan_adapter(self, adapter: str, is_inner: bool):
        scanner = BleakScanner(adapter=adapter)

        def _cb(device, advertisement_data):
            ok, txp = is_ibeacon(advertisement_data)
            if not ok:
                return
            mac = (device.address or "").lower()
            if self.targets and mac not in self.targets:
                return
            rssi = int(device.rssi or -100)
            if txp is not None:
                self._measured_power_by_mac[mac] = txp
            mp = self._measured_power_by_mac.get(mac, -59)
            dist = estimate_distance(rssi, measured_power=mp)
            store = self._inner_readings if is_inner else self._outer_readings
            store[mac] = Reading(ts=time.time(), rssi=rssi, distance_m=dist)
            if self._csv_writer:
                self._csv_writer.writerow([datetime.utcnow().isoformat(), mac, 'inner' if is_inner else 'outer', rssi, dist])
            if self.post_url and requests:
                # best-effort post to API detections (expected by backend)
                try:
                    payload = {
                        "scanner_id": "gate-inner" if is_inner else "gate-outer",
                        "observations": [
                            {"protocol": "ibeacon", "mac": mac, "name": device.name or mac, "rssi": rssi}
                        ],
                        "api_key": self.api_key,
                    }
                    requests.post(f"{self.post_url}/api/v1/detections", json=payload, timeout=1.5)
                except Exception:
                    pass

        scanner.register_detection_callback(_cb)

        while not self._stop.is_set():
            try:
                await scanner.start()
                # keep scanner running; bleak handles callbacks
                await asyncio.sleep(0.5)
            except Exception as e:
                # transient adapter not ready; wait and retry
                await asyncio.sleep(0.8)
            finally:
                with contextlib.suppress(Exception):
                    await scanner.stop()

    async def _printer(self):
        # continuously print current status of tracked beacons
        while not self._stop.is_set():
            await asyncio.sleep(self.interval_s)
            tracked = self.targets or list({*self._inner_readings.keys(), *self._outer_readings.keys()})
            if not tracked:
                print("No iBeacon tracked yet. Bring a beacon close or use --autopick/--target.")
                continue
            lines = []
            ts = datetime.now().strftime('%H:%M:%S')
            for mac in tracked:
                ir = self._inner_readings.get(mac)
                orr = self._outer_readings.get(mac)
                if not ir and not orr:
                    lines.append(f"{mac} | inner: --    | outer: --")
                    continue
                def fmt(r: Optional[Reading]) -> str:
                    if not r:
                        return "--"
                    age = time.time() - r.ts
                    return f"rssi={r.rssi:>3} dBm, d≈{r.distance_m:>4} m, age={age:>3.1f}s"
                lines.append(f"{mac} | inner: {fmt(ir)} | outer: {fmt(orr)}")
            print(f"[{ts}]\n" + "\n".join(lines))


import contextlib


def main() -> None:
    ap = argparse.ArgumentParser(description="Dual iBeacon monitor (two adapters)")
    ap.add_argument("--inner", default="hci1", help="Inner adapter (e.g., hci1)")
    ap.add_argument("--outer", default="hci0", help="Outer adapter (e.g., hci0)")
    ap.add_argument("--target", action="append", default=[], help="Target beacon MAC to track (repeatable)")
    ap.add_argument("--autopick", type=float, default=2.0, help="Seconds to auto-pick strongest beacon (0=disabled)")
    ap.add_argument("--interval", type=float, default=0.7, help="Console refresh interval seconds")
    ap.add_argument("--duration", type=float, default=0.0, help="Optional max seconds to run (0=infinite)")
    ap.add_argument("--csv", default=None, help="Optional CSV log path")
    ap.add_argument("--post", default=None, help="Optional API base URL to POST detections (e.g., http://127.0.0.1:8000)")
    ap.add_argument("--api-key", default="default-key", help="API key for posting detections")
    args = ap.parse_args()

    mon = DualMonitor(
        inner_adapter=args.inner,
        outer_adapter=args.outer,
        targets=args.target,
        autopick_s=args.autopick,
        interval_s=args.interval,
        csv_path=args.csv,
        post_url=args.post,
        api_key=args.api_key,
    )

    async def runner():
        t = asyncio.create_task(mon.start())
        if args.duration and args.duration > 0:
            try:
                await asyncio.wait_for(mon._stop.wait(), timeout=args.duration)
            except asyncio.TimeoutError:
                mon._stop.set()
        await t

    asyncio.run(runner())


if __name__ == "__main__":
    main()


