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

from .database_models import DetectionState, DatabaseManager
from .logging_config import get_logger

# Use the system logger
logger = get_logger()

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
    boat_id: Optional[str] = None
    last_outer_seen: Optional[datetime] = None
    last_inner_seen: Optional[datetime] = None
    entry_timestamp: Optional[datetime] = None
    exit_timestamp: Optional[datetime] = None
    last_update: Optional[datetime] = None

class EntryExitFSM:
    def __init__(self, db_manager: DatabaseManager, 
                 outer_scanner_id: str, inner_scanner_id: str,
                 rssi_threshold: int = -70, hysteresis: int = 5,
                 confirm_k: int = 3, confirm_window_s: float = 2.0,
                 absent_timeout_s: float = 12.0, alpha: float = 0.35):
        self.db = db_manager
        self.outer_scanner_id = outer_scanner_id
        self.inner_scanner_id = inner_scanner_id
        self.rssi_threshold = rssi_threshold
        self.hysteresis = hysteresis  # dBm hysteresis to prevent flicker
        # Robust signal processing params
        self.confirm_k = confirm_k
        self.confirm_window_s = confirm_window_s
        self.absent_timeout_s = absent_timeout_s
        self.alpha = alpha
        
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
                boat_id=None,
                last_outer_seen=None,
                last_inner_seen=None,
                entry_timestamp=None,
                exit_timestamp=None,
                last_update=now
            )
        
        beacon_state = self.beacon_states[beacon_id]
        old_state = beacon_state.current_state
        
        # Lookup mapped boat and enforce maintenance & mapping-change reset
        mapped_boat = None
        try:
            mapped_boat = self.db.get_boat_by_beacon(beacon_id)
        except Exception:
            mapped_boat = None
        # Maintenance override: ignore transitions
        if mapped_boat and getattr(mapped_boat, 'op_status', None) == 'MAINTENANCE':
            logger.info(f"Ignoring detection for maintenance boat {mapped_boat.name} (beacon {beacon_id})", "FSM")
            return None
        # Reset if boat mapping changed
        current_boat_id = getattr(mapped_boat, 'id', None)
        if beacon_state.boat_id is not None and beacon_state.boat_id != current_boat_id:
            logger.info(f"Beacon {beacon_id} mapping changed {beacon_state.boat_id} -> {current_boat_id}; resetting FSM", "FSM")
            beacon_state.current_state = FSMState.IDLE
            beacon_state.last_outer_seen = None
            beacon_state.last_inner_seen = None
            beacon_state.entry_timestamp = None
            beacon_state.exit_timestamp = None
        beacon_state.boat_id = current_boat_id

        # Determine if this is inner or outer scanner detection
        is_outer = scanner_id == self.outer_scanner_id
        is_inner = scanner_id == self.inner_scanner_id
        
        if not (is_outer or is_inner):
            return None  # Unknown scanner
        
        # Update last seen timestamps and simple EMA/trend
        if is_outer:
            beacon_state.last_outer_seen = now
        if is_inner:
            beacon_state.last_inner_seen = now

        # Use recent-window confirmation counters per beacon
        # Store tuples: (ts, outer_strong, outer_weak, inner_strong, inner_weak)
        if not hasattr(self, '_recent_flags'):
            self._recent_flags = {}
        flags = self._recent_flags.setdefault(beacon_id, [])

        # Visibility-aware strong/weak classification
        def visible(last_seen: Optional[datetime]) -> bool:
            return last_seen is not None and (now - last_seen).total_seconds() <= self.absent_timeout_s

        s_high = self.rssi_threshold
        s_low = self.rssi_threshold - self.hysteresis
        outer_vis = visible(beacon_state.last_outer_seen)
        inner_vis = visible(beacon_state.last_inner_seen)
        outer_strong_now = outer_vis and rssi >= s_high if is_outer else False
        inner_strong_now = inner_vis and rssi >= s_high if is_inner else False
        outer_weak_now = (not outer_vis) or (is_outer and rssi <= s_low)
        inner_weak_now = (not inner_vis) or (is_inner and rssi <= s_low)

        flags.append((now, outer_strong_now, outer_weak_now, inner_strong_now, inner_weak_now))
        cutoff = now - timedelta(seconds=self.confirm_window_s)
        while flags and flags[0][0] < cutoff:
            flags.pop(0)

        def confirmed(idx: int) -> bool:
            return sum(1 for t,*vals in flags if vals[idx]) >= self.confirm_k

        outer_strong = confirmed(0)
        outer_weak = confirmed(1)
        inner_strong = confirmed(2)
        inner_weak = confirmed(3)

        strong_signal = outer_strong if is_outer else inner_strong
        weak_signal = outer_weak if is_outer else inner_weak
        
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
            
            # Log state change with context
            if new_state == FSMState.IDLE and old_state != FSMState.IDLE:
                logger.info(f"Beacon timeout: {beacon_id} - {old_state.value} → {new_state.value} (no signal for 5+ minutes)", "FSM")
            else:
                logger.info(f"Beacon state change: {beacon_id} - {old_state.value} → {new_state.value} (RSSI: {rssi} dBm)", "FSM")
            
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
