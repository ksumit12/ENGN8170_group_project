#!/usr/bin/env python3
"""
Monitor inner/outer scanner detections and validate expected FSM sequences.

Purpose
 - Show whether both scanners are detecting any registered beacon
 - Track live per-scanner detection order per beacon
 - Validate inner→outer (EXIT) and outer→inner (ENTRY) sequences against FSM

Usage
  python3 scripts/monitor_scanner_sequences.py \
      --server http://127.0.0.1:5000 \
      --inner gate-inner --outer gate-outer \
      --window-s 20 --duration-s 300 --interval-s 1.0

Notes
 - This script polls the dashboard/API server that `boat_tracking_system.py` runs.
 - It uses these endpoints if available:
     GET /api/active-beacons     → current live detections from running scanners
     GET /api/fsm-states         → current FSM state per beacon
     GET /api/beacons            → registered beacons (to filter known IDs)
 - If /api/active-beacons lacks per-scanner detail, the script still reports
   FSM states and overall visibility, but sequence validation may be limited.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

try:
    import requests
except Exception as e:  # pragma: no cover
    print("This script requires the 'requests' package. Install with: pip install requests", file=sys.stderr)
    raise


FSM_ENTERED = {"entered", "ENTERED"}
FSM_EXITED = {"exited", "EXITED"}
FSM_INSIDE = {"entered", "ENTERED", "inside", "INSIDE"}
FSM_OUTSIDE = {"exited", "EXITED", "outside", "OUTSIDE"}


@dataclass
class BeaconLive:
    beacon_id: str
    mac: Optional[str]
    boat_id: Optional[str]
    boat_name: Optional[str]
    # present_by_scanner[scanner_id] = True if seen in this poll
    present_by_scanner: Dict[str, bool]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_json(session: requests.Session, url: str, timeout: float = 4.0) -> Any:
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_registered_beacons(session: requests.Session, base: str) -> Dict[str, Dict[str, Any]]:
    try:
        data = get_json(session, f"{base}/api/beacons")
        by_id: Dict[str, Dict[str, Any]] = {}
        for b in data:
            # expected keys: id, mac_address, assigned_boat_id, assigned_boat_name, last_seen, etc.
            bid = str(b.get("id") or b.get("beacon_id") or "")
            if bid:
                by_id[bid] = b
        return by_id
    except Exception:
        return {}


def fetch_active_beacons(session: requests.Session, base: str) -> List[Dict[str, Any]]:
    try:
        return get_json(session, f"{base}/api/active-beacons")
    except Exception:
        return []


def fetch_fsm_states(session: requests.Session, base: str) -> Dict[str, str]:
    try:
        data = get_json(session, f"{base}/api/fsm-states")
        # Expect: list of { beacon_id, state, boat_id, ... }
        states: Dict[str, str] = {}
        if isinstance(data, list):
            for row in data:
                bid = str(row.get("beacon_id") or row.get("id") or "")
                state = str(row.get("state") or "").lower()
                if bid:
                    states[bid] = state
        elif isinstance(data, dict) and "items" in data:
            for row in data.get("items", []):
                bid = str(row.get("beacon_id") or row.get("id") or "")
                state = str(row.get("state") or "").lower()
                if bid:
                    states[bid] = state
        return states
    except Exception:
        return {}


def parse_present_by_scanner(item: Dict[str, Any]) -> Dict[str, bool]:
    """Best-effort extraction of which scanners see this beacon right now.
    We support multiple shapes to be robust to API variations.
    """
    present: Dict[str, bool] = {}
    # shape 1: item["scanners"] = [{"id": "gate-inner", "present": true}, ...]
    scanners = item.get("scanners")
    if isinstance(scanners, list):
        for s in scanners:
            sid = str(s.get("id") or s.get("scanner_id") or "").strip()
            if sid:
                present[sid] = bool(s.get("present", True))
    # shape 2: item["by_scanner"] = { scanner_id: { present: true } }
    if not present and isinstance(item.get("by_scanner"), dict):
        for sid, info in item["by_scanner"].items():
            present[str(sid)] = bool((info or {}).get("present", True))
    # shape 3: flags: item["seen_inner"], item["seen_outer"] with ids
    for key in ("seen_inner", "seen_outer"):
        if key in item and isinstance(item[key], bool):
            # fall back names if provided
            sid = "gate-inner" if key == "seen_inner" else "gate-outer"
            present[sid] = bool(item[key])
    return present


def main() -> None:
    p = argparse.ArgumentParser(description="Monitor inner/outer scanner sequences vs FSM")
    p.add_argument("--server", default="http://127.0.0.1:5000", help="Base URL of server")
    p.add_argument("--inner", default="gate-inner", help="Inner scanner id")
    p.add_argument("--outer", default="gate-outer", help="Outer scanner id")
    p.add_argument("--window-s", type=float, default=20.0, help="Max seconds between pair for sequence validation")
    p.add_argument("--duration-s", type=float, default=300.0, help="Total time to run")
    p.add_argument("--interval-s", type=float, default=1.0, help="Polling interval seconds")
    p.add_argument("--only-registered", action="store_true", help="Only consider beacons registered in DB")
    args = p.parse_args()

    base = args.server.rstrip("/")
    inner_id = args.inner.strip().lower()
    outer_id = args.outer.strip().lower()
    pair_window = timedelta(seconds=max(1.0, args.window_s))

    session = requests.Session()

    registered = fetch_registered_beacons(session, base)
    registered_set = set(registered.keys())

    print(f"Monitoring server={base} inner={inner_id} outer={outer_id} window={pair_window.total_seconds():.0f}s")
    if args.only_registered:
        print(f"Registered beacons in DB: {len(registered_set)}")

    # Track last-seen timestamp per scanner per beacon
    last_seen: Dict[str, Dict[str, datetime]] = defaultdict(dict)
    # Track detected sequences with small deques for recent events
    recent_events: deque[Tuple[datetime, str, str]] = deque(maxlen=200)  # (ts, beacon_id, event)

    stop_at = time.time() + args.duration_s
    tick = 0
    try:
        while time.time() < stop_at:
            tick += 1
            tnow = now_utc()

            # Fetch data
            fsm_states = fetch_fsm_states(session, base)
            active = fetch_active_beacons(session, base)

            # Build live presence index
            live_rows: List[BeaconLive] = []
            for item in active:
                beacon_id = str(item.get("beacon_id") or item.get("id") or "").strip()
                if not beacon_id:
                    continue
                if args.only_registered and beacon_id not in registered_set:
                    continue
                mac = item.get("mac") or item.get("mac_address")
                boat_id = item.get("boat_id") or item.get("assigned_boat_id")
                boat_name = item.get("boat_name") or item.get("assigned_boat_name")
                present_by_scanner = parse_present_by_scanner(item)
                # normalize keys
                present_by_scanner = {str(k).strip().lower(): bool(v) for k, v in present_by_scanner.items()}
                live_rows.append(BeaconLive(
                    beacon_id=beacon_id,
                    mac=str(mac) if mac else None,
                    boat_id=str(boat_id) if boat_id else None,
                    boat_name=str(boat_name) if boat_name else None,
                    present_by_scanner=present_by_scanner,
                ))

            # Update last seen per scanner and detect sequences
            for row in live_rows:
                pid = row.beacon_id
                pres = row.present_by_scanner
                if inner_id in pres and pres.get(inner_id):
                    last_seen[pid][inner_id] = tnow
                if outer_id in pres and pres.get(outer_id):
                    last_seen[pid][outer_id] = tnow

                # Validate sequences within window
                li = last_seen[pid].get(inner_id)
                lo = last_seen[pid].get(outer_id)
                if li and lo:
                    # exit: inner then outer
                    if li <= lo and (lo - li) <= pair_window:
                        recent_events.append((tnow, pid, "SEQ_EXIT(inner→outer)"))
                    # entry: outer then inner
                    if lo <= li and (li - lo) <= pair_window:
                        recent_events.append((tnow, pid, "SEQ_ENTRY(outer→inner)"))

            # Print compact status every few ticks
            if tick % int(max(1, round(5.0 / max(0.1, args.interval_s)))) == 0:
                print("\n=== Live Scanner Status ===")
                if not live_rows:
                    print("No active detections from scanners right now.")
                else:
                    for row in live_rows:
                        st = fsm_states.get(row.beacon_id, "unknown")
                        inner_flag = row.present_by_scanner.get(inner_id, False)
                        outer_flag = row.present_by_scanner.get(outer_id, False)
                        name = row.boat_name or row.boat_id or row.beacon_id
                        print(f"- {name:>12} | inner={str(inner_flag):5} outer={str(outer_flag):5} | FSM={st}")

                # Show recent sequence detections and compare with FSM
                if recent_events:
                    print("\nRecent sequences (within window):")
                    for ts, bid, ev in list(recent_events)[-10:]:
                        st = fsm_states.get(bid, "unknown")
                        ok = False
                        if ev.startswith("SEQ_EXIT") and (st in FSM_OUTSIDE):
                            ok = True
                        if ev.startswith("SEQ_ENTRY") and (st in FSM_INSIDE):
                            ok = True
                        verdict = "" if ok else "?"
                        label = registered.get(bid, {}).get("assigned_boat_name") or bid
                        print(f"  {ts.isoformat()} {ev} -> FSM={st} [{verdict}] ({label})")

            time.sleep(args.interval_s)

    except KeyboardInterrupt:
        print("\nInterrupted.")

    # Final summary
    print("\n=== Summary ===")
    print(f"Tracked beacons: {len(last_seen)}")
    if recent_events:
        exit_ok = entry_ok = 0
        exit_total = entry_total = 0
        for _, bid, ev in recent_events:
            st = (fsm_states.get(bid, "unknown") if 'fsm_states' in locals() else "unknown")
            if ev.startswith("SEQ_EXIT"):
                exit_total += 1
                if st in FSM_OUTSIDE:
                    exit_ok += 1
            if ev.startswith("SEQ_ENTRY"):
                entry_total += 1
                if st in FSM_INSIDE:
                    entry_ok += 1
        if exit_total:
            print(f"Exit sequences: {exit_ok}/{exit_total} aligned with FSM")
        if entry_total:
            print(f"Entry sequences: {entry_ok}/{entry_total} aligned with FSM")
    else:
        print("No sequences observed within the configured window.")


if __name__ == "__main__":
    main()
















