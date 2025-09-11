#!/usr/bin/env python3
"""
Entry/Exit FSM for BLE Beacon Detection
Implements hysteresis-based state machine for reliable entry/exit detection
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

from database_models import DetectionState, DatabaseManager

class FSMState(Enum):
    IDLE = "idle"
    SEEN_OUTER = "seen_outer"
    SEEN_INNER = "seen_inner"
    ENTERED = "entered"
    EXITED = "exited"

@dataclass
class BeaconFSM:
    beacon_id: str
    current_state: FSMState
    last_outer_seen: Optional[datetime]
    last_inner_seen: Optional[datetime]
    entry_timestamp: Optional[datetime]
    exit_timestamp: Optional[datetime]
    last_update: datetime

class EntryExitFSM:
    def __init__(self, db_manager: DatabaseManager, 
                 outer_scanner_id: str, inner_scanner_id: str,
                 rssi_threshold: int = -70, hysteresis: int = 5):
        self.db = db_manager
        self.outer_scanner_id = outer_scanner_id
        self.inner_scanner_id = inner_scanner_id
        self.rssi_threshold = rssi_threshold
        self.hysteresis = hysteresis  # dBm hysteresis to prevent flicker
        
        # State cache for performance
        self.beacon_states: Dict[str, BeaconFSM] = {}
        self.load_beacon_states()
    
    def load_beacon_states(self):
        """Load all beacon states from database."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT beacon_id, current_state, last_outer_seen, last_inner_seen,
                       entry_timestamp, exit_timestamp, updated_at
                FROM beacon_states
            """)
            
            for row in cursor.fetchall():
                beacon_id = row[0]
                self.beacon_states[beacon_id] = BeaconFSM(
                    beacon_id=beacon_id,
                    current_state=FSMState(row[1]),
                    last_outer_seen=row[2],
                    last_inner_seen=row[3],
                    entry_timestamp=row[4],
                    exit_timestamp=row[5],
                    last_update=row[6]
                )
    
    def process_detection(self, scanner_id: str, beacon_id: str, rssi: int) -> Optional[Tuple[FSMState, FSMState]]:
        """
        Process a detection and return (old_state, new_state) if state changed.
        Returns None if no state change occurred.
        """
        now = datetime.now(timezone.utc)
        
        # Get or create beacon state
        if beacon_id not in self.beacon_states:
            self.beacon_states[beacon_id] = BeaconFSM(
                beacon_id=beacon_id,
                current_state=FSMState.IDLE,
                last_outer_seen=None,
                last_inner_seen=None,
                entry_timestamp=None,
                exit_timestamp=None,
                last_update=now
            )
        
        beacon_state = self.beacon_states[beacon_id]
        old_state = beacon_state.current_state
        
        # Determine if this is inner or outer scanner detection
        is_outer = scanner_id == self.outer_scanner_id
        is_inner = scanner_id == self.inner_scanner_id
        
        if not (is_outer or is_inner):
            return None  # Unknown scanner
        
        # Update last seen timestamps
        if is_outer:
            beacon_state.last_outer_seen = now
        if is_inner:
            beacon_state.last_inner_seen = now
        
        # Apply RSSI threshold with hysteresis
        strong_signal = rssi >= self.rssi_threshold
        weak_signal = rssi < (self.rssi_threshold - self.hysteresis)
        
        # State machine logic
        new_state = self._transition_state(beacon_state, is_outer, is_inner, strong_signal, weak_signal, now)
        
        if new_state != old_state:
            beacon_state.current_state = new_state
            beacon_state.last_update = now
            
            # Update timestamps for entry/exit events
            if new_state == FSMState.ENTERED:
                beacon_state.entry_timestamp = now
            elif new_state == FSMState.EXITED:
                beacon_state.exit_timestamp = now
            
            # Save to database
            self._save_beacon_state(beacon_state)
            
            # Log detection
            self.db.log_detection(scanner_id, beacon_id, rssi, DetectionState(new_state.value))
            
            return (old_state, new_state)
        
        return None
    
    def _transition_state(self, beacon_state: BeaconFSM, is_outer: bool, is_inner: bool, 
                         strong_signal: bool, weak_signal: bool, now: datetime) -> FSMState:
        """Determine new state based on current state and detection."""
        current = beacon_state.current_state
        
        # Timeout for state transitions (prevent stuck states)
        timeout_threshold = timedelta(minutes=5)
        
        if current == FSMState.IDLE:
            if is_outer and strong_signal:
                return FSMState.SEEN_OUTER
            elif is_inner and strong_signal:
                return FSMState.SEEN_INNER
        
        elif current == FSMState.SEEN_OUTER:
            if is_inner and strong_signal:
                return FSMState.SEEN_INNER
            elif weak_signal and self._is_timeout(beacon_state.last_outer_seen, now, timeout_threshold):
                return FSMState.IDLE
        
        elif current == FSMState.SEEN_INNER:
            if is_outer and strong_signal:
                return FSMState.ENTERED
            elif weak_signal and self._is_timeout(beacon_state.last_inner_seen, now, timeout_threshold):
                return FSMState.IDLE
        
        elif current == FSMState.ENTERED:
            if is_outer and weak_signal:
                return FSMState.SEEN_OUTER
            elif is_inner and weak_signal:
                return FSMState.SEEN_INNER
            elif weak_signal and self._is_timeout(beacon_state.last_outer_seen, now, timeout_threshold):
                return FSMState.EXITED
        
        elif current == FSMState.EXITED:
            if is_inner and strong_signal:
                return FSMState.SEEN_INNER
            elif is_outer and strong_signal:
                return FSMState.SEEN_OUTER
            elif weak_signal and self._is_timeout(beacon_state.last_outer_seen, now, timeout_threshold):
                return FSMState.IDLE
        
        return current  # No state change
    
    def _is_timeout(self, last_seen: Optional[datetime], now: datetime, threshold: timedelta) -> bool:
        """Check if last seen time exceeds threshold."""
        if last_seen is None:
            return True
        return (now - last_seen) > threshold
    
    def _save_beacon_state(self, beacon_state: BeaconFSM):
        """Save beacon state to database."""
        self.db.update_beacon_state(
            beacon_id=beacon_state.beacon_id,
            state=DetectionState(beacon_state.current_state.value),
            last_outer_seen=beacon_state.last_outer_seen,
            last_inner_seen=beacon_state.last_inner_seen,
            entry_timestamp=beacon_state.entry_timestamp,
            exit_timestamp=beacon_state.exit_timestamp
        )
    
    def get_beacon_state(self, beacon_id: str) -> Optional[FSMState]:
        """Get current state of a beacon."""
        if beacon_id in self.beacon_states:
            return self.beacon_states[beacon_id].current_state
        return FSMState.IDLE
    
    def get_entered_beacons(self) -> List[str]:
        """Get list of beacon IDs currently in ENTERED state."""
        return [
            beacon_id for beacon_id, state in self.beacon_states.items()
            if state.current_state == FSMState.ENTERED
        ]
    
    def get_exited_beacons(self) -> List[str]:
        """Get list of beacon IDs currently in EXITED state."""
        return [
            beacon_id for beacon_id, state in self.beacon_states.items()
            if state.current_state == FSMState.EXITED
        ]
    
    def cleanup_old_states(self, max_age_hours: int = 24):
        """Clean up old beacon states to prevent memory bloat."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        to_remove = []
        for beacon_id, state in self.beacon_states.items():
            if state.last_update < cutoff_time and state.current_state == FSMState.IDLE:
                to_remove.append(beacon_id)
        
        for beacon_id in to_remove:
            del self.beacon_states[beacon_id]
        
        if to_remove:
            print(f"Cleaned up {len(to_remove)} old beacon states")
