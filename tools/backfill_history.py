#!/usr/bin/env python3
"""
Backfill historical synthetic data for testing reports.
- Generates detections per beacon across selected days
- Optionally writes session start/end (ENTERED/EXITED) state rows to beacon_states history via detections

Usage examples:
  python3 tools/backfill_history.py --days 7 --sessions-per-day 2
  python3 tools/backfill_history.py --from 2025-09-20T00:00 --to 2025-09-24T23:59 --sessions-per-day 3

Notes:
- This writes to data/boat_tracking.db
- It simulates iBeacon observations by inserting into detections and nudging states via simple ordering
"""

import argparse
from datetime import datetime, timedelta, timezone
import random
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from app.database_models import DatabaseManager  # type: ignore


def iso_to_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def choose_times(day_start: datetime, sessions_per_day: int) -> list[tuple[datetime, datetime]]:
    """Produce session (exit→enter) windows during the day."""
    spans: list[tuple[datetime, datetime]] = []
    for _ in range(sessions_per_day):
        start_min = random.randint(6 * 60, 16 * 60)  # between 06:00 and 16:00
        dur_min = random.randint(20, 120)  # 20-120 minutes outing
        start = day_start + timedelta(minutes=start_min)
        end = start + timedelta(minutes=dur_min)
        spans.append((start, end))
    spans.sort(key=lambda x: x[0])
    return spans


def insert_detection_rows(db: DatabaseManager, beacon_id: str, when: datetime, state: str, rssi: int) -> None:
    """Insert a detection row at time with state label for analytics.
    We write to detections table consistent with schema.
    """
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO detections (id, scanner_id, beacon_id, rssi, timestamp, state)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"DET{int(when.timestamp()*1000)}{random.randint(100,999)}",
                "sim-scanner",
                beacon_id,
                rssi,
                when,
                state,
            ),
        )
        conn.commit()


def backfill(db: DatabaseManager, start: datetime, end: datetime, sessions_per_day: int, rssi_base: int) -> None:
    boats = db.get_all_boats()
    beacons = []
    for b in boats:
        bc = db.get_beacon_by_boat(b.id)
        if bc:
            beacons.append((b, bc))
    if not beacons:
        print("No assigned beacons found; nothing to backfill.")
        return

    current = start
    total_sessions = 0
    while current.date() <= end.date():
        day_start = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
        spans = choose_times(day_start, sessions_per_day)
        for boat, beacon in beacons:
            for s, e in spans:
                # Exit (on-water) event sequence
                insert_detection_rows(db, beacon.id, s - timedelta(seconds=5), 'exited', rssi_base - 5)
                insert_detection_rows(db, beacon.id, s, 'exited', rssi_base - 10)
                # Enter (in-shed) sequence at end
                insert_detection_rows(db, beacon.id, e - timedelta(seconds=5), 'entered', rssi_base - 3)
                insert_detection_rows(db, beacon.id, e, 'entered', rssi_base)
                total_sessions += 1
        current += timedelta(days=1)

    print(f"Backfill complete: {total_sessions} sessions inserted across {len(beacons)} boats.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical detections")
    parser.add_argument('--days', type=int, default=3, help='How many days back from now')
    parser.add_argument('--from', dest='from_iso', type=str, help='ISO start (e.g., 2025-09-20T00:00)')
    parser.add_argument('--to', dest='to_iso', type=str, help='ISO end (e.g., 2025-09-24T23:59)')
    parser.add_argument('--sessions-per-day', type=int, default=2)
    parser.add_argument('--rssi', type=int, default=-45, help='Base RSSI value around in-shed events')

    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    if args.from_iso and args.to_iso:
        start = iso_to_dt(args.from_iso) or now - timedelta(days=3)
        end = iso_to_dt(args.to_iso) or now
    else:
        end = now
        start = now - timedelta(days=args.days)

    if start > end:
        start, end = end, start

    db = DatabaseManager('data/boat_tracking.db')
    backfill(db, start, end, args.sessions_per_day, args.rssi)


if __name__ == '__main__':
    main()

