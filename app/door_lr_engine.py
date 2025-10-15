#!/usr/bin/env python3
"""
DoorLREngine: FSM engine that uses DirectionClassifier for door left/right logic.
"""
from __future__ import annotations

from typing import Optional, Tuple, Any, Dict
from datetime import datetime, timezone

from .fsm_engine import IFSMEngine
from .database_models import DatabaseManager, DetectionState
from .logging_config import get_logger
from .direction_classifier import DirectionClassifier, LRParams


logger = get_logger()


class DoorLREngine(IFSMEngine):
    def __init__(self, db_manager: DatabaseManager, outer_scanner_id: str, inner_scanner_id: str,
                 rssi_threshold: int = -80, hysteresis: int = 10, **kwargs):
        self.db = db_manager
        self.outer_scanner_id = (outer_scanner_id or '').lower()
        self.inner_scanner_id = (inner_scanner_id or '').lower()
        self.rssi_threshold = rssi_threshold
        self.hysteresis = hysteresis

        # Default params; may be overridden by calibration loader by API layer
        params = LRParams(
            active_dbm=-70,
            energy_dbm=-65,
            delta_db=8,
            dwell_s=0.20,
            window_s=1.20,
            tau_min_s=0.12,
            cooldown_s=3.0,
            slope_min_db_per_s=10.0,
            min_peak_sep_s=0.12,
        )
        calib_map = {"lag_positive": "LEAVE", "lag_negative": "ENTER"}
        self.classifier = DirectionClassifier(params, calib_map, logger)

    def process_detection(self, scanner_id: str, beacon_id: str, rssi: int) -> Optional[Tuple[Any, Any]]:
        # Map scanner IDs to left/right by suffix
        sid = (scanner_id or '').lower()
        leftish = sid.endswith('left') or sid.endswith('door-left') or sid.endswith('gate-left')
        rightish = sid.endswith('right') or sid.endswith('door-right') or sid.endswith('gate-right')
        if not (leftish or rightish):
            # Fallback mapping based on inner/outer: treat inner as left, outer as right for door-LR
            leftish = sid == self.inner_scanner_id
            rightish = sid == self.outer_scanner_id

        # Provide a monotonic-like timestamp (seconds)
        t = datetime.now(timezone.utc).timestamp()
        logical_scanner = f"gate-left" if leftish else ("gate-right" if rightish else sid)

        events = self.classifier.update(beacon_id, logical_scanner, float(rssi), t)
        if not events:
            return None

        # Commit first event as state change for compatibility
        ev = events[0]
        old_state = self.db.get_beacon_state(beacon_id)
        if ev.direction == 'ENTER':
            new_state = DetectionState.ENTERED
        else:
            new_state = DetectionState.EXITED

        # Save state for dashboard compatibility
        self.db.update_beacon_state(
            beacon_id=beacon_id,
            state=new_state,
        )
        return (new_state, new_state)  # keep signature compatible; UI uses .value

    def get_beacon_state(self, beacon_id: str):
        return self.db.get_beacon_state(beacon_id)


