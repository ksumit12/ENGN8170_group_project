#!/usr/bin/env python3
import os
import time
from datetime import datetime, timezone

from app.database_models import DatabaseManager, DetectionState


def clear():
    os.system('clear' if os.name == 'posix' else 'cls')


def render_ascii_state(state: DetectionState) -> str:
    mapping = {
        DetectionState.IDLE: 'IDLE   ',
        DetectionState.INSIDE: 'INSIDE ',
        DetectionState.OUTSIDE: 'OUTSIDE',
        DetectionState.OUT_PENDING: 'OUT_PND',
        DetectionState.IN_PENDING: 'IN_PND ',
    }
    return mapping.get(state, 'UNKN   ')


def main():
    db = DatabaseManager()
    assignments = db.get_active_assignments()
    if not assignments:
        print("No active assignments found. Run sim_seed_data.py first.")
        return

    # Pre-fetch boat and beacon labels
    labels = []
    for boat_id, beacon_id in assignments:
        boat = db.get_boat(boat_id)
        labels.append((boat_id, beacon_id, boat.name if boat else boat_id))

    try:
        while True:
            clear()
            print("Live FSM States (refreshing)...")
            print(datetime.now(timezone.utc).isoformat())
            print("")

            # Draw simple pseudo-diagram per boat
            for boat_id, beacon_id, name in labels:
                state = db.get_beacon_state(beacon_id)
                line = f"{name:24} | {render_ascii_state(state)} | beacon={beacon_id}"
                print(line)

            print("\nLegend: IDLE, ENTERED, EXITED, GO_OUT, GO_IN")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()


