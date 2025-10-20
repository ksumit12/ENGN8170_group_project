#!/usr/bin/env python3
"""
SingleScannerEngine: minimal FSM engine for single-scanner deployments.

On each detection, mark the beacon state as INSIDE (entered). OUT state is
inferred by the API server background updater using recency-of-last-seen.
"""

from __future__ import annotations

from typing import Optional, Tuple, Any
from datetime import datetime, timezone

from .fsm_engine import IFSMEngine
from .database_models import DatabaseManager, DetectionState, BoatStatus
from .logging_config import get_logger


logger = get_logger()


class SingleScannerEngine(IFSMEngine):
    def __init__(self, db_manager: DatabaseManager, outer_scanner_id: str, inner_scanner_id: str, **kwargs):
        self.db = db_manager
        # Retain fields for compatibility; values are not used for decisions
        self.outer_scanner_id = (outer_scanner_id or '').lower()
        self.inner_scanner_id = (inner_scanner_id or '').lower()

    def process_detection(self, scanner_id: str, beacon_id: str, rssi: int) -> Optional[Tuple[Any, Any]]:
        """On detection, set state to INSIDE and update boat status to IN_HARBOR.

        OUT transitions are handled by the API server's recency logic.
        Returns a tuple shaped like (old_state, new_state) where each has a .value.
        """
        old_state = self.db.get_beacon_state(beacon_id) or DetectionState.IDLE
        now = datetime.now(timezone.utc)

        # Commit INSIDE on any detection (debounce handled by upstream batch/post rate)
        self.db.update_beacon_state(
            beacon_id=beacon_id,
            state=DetectionState.INSIDE,
            entry_timestamp=now
        )

        # Reflect on boat status for dashboard immediacy
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT boat_id FROM boat_beacon_assignments WHERE beacon_id = ?", (beacon_id,))
                row = cur.fetchone()
                if row:
                    boat_id = row[0]
                    self.db.update_boat_status(boat_id, BoatStatus.IN_HARBOR)
        except Exception:
            pass

        new_state = DetectionState.INSIDE
        return (old_state, new_state)

    def get_beacon_state(self, beacon_id: str):
        return self.db.get_beacon_state(beacon_id) or DetectionState.IDLE


