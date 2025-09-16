#!/usr/bin/env python3
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
import requests


BASE = "http://localhost:9000"


def main():
    boats = [
        {"boat_id": "jack_sparrow", "display_name": "Jack_sparrow (4x)", "assigned_beacon_ids": ["DC:0D:30:23:05:F8"]},
        {"boat_id": "iron_man", "display_name": "iron_man (8+)", "assigned_beacon_ids": ["DC:0D:30:23:05:CF"]},
        {"boat_id": "oliver_queen", "display_name": "oliver_queen (2+)", "assigned_beacon_ids": ["DC:0D:30:23:05:47"]},
    ]

    for b in boats:
        requests.post(f"{BASE}/api/boats", json=b, timeout=5)

    now = datetime.now(timezone.utc)
    evts = [
        {"beacon_id": "B1", "boat_id": "jack_sparrow", "new_state": "ON_WATER", "event_time": (now - timedelta(minutes=30)).isoformat()},
        {"beacon_id": "B2", "boat_id": "iron_man", "new_state": "ON_WATER", "event_time": (now - timedelta(minutes=20)).isoformat()},
        {"beacon_id": "B3", "boat_id": "oliver_queen", "new_state": "IN_SHED", "event_time": (now - timedelta(minutes=10)).isoformat()},
    ]
    for e in evts:
        requests.post(f"{BASE}/api/events/ingest", json=e, timeout=5)

    print("Seeded boats and events.")


if __name__ == "__main__":
    main()




