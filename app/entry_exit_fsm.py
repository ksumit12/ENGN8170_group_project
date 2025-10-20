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
    INSIDE = "entered"        # boat inside (DB value "entered")
    OUTSIDE = "exited"        # boat outside (DB value "exited")
    OUT_PENDING = "going_out" # saw inner, waiting for outer
    IN_PENDING = "going_in"   # saw outer, waiting for inner
    # Backward-compatible aliases
    ENTERED = "entered"
    EXITED = "exited"
    GOING_OUT = "going_out"
    GOING_IN = "going_in"

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
    # State timers
    pending_since: Optional[datetime] = None
    # Exponential moving averages for trend detection per scanner
    ema_outer: Optional[float] = None
    ema_inner: Optional[float] = None
    # Dominance timing
    outer_dominant_start: Optional[datetime] = None
    inner_dominant_start: Optional[datetime] = None

class EntryExitFSM:
    def __init__(self, db_manager: DatabaseManager, 
                 outer_scanner_id: str, inner_scanner_id: str,
                 rssi_threshold: int = -70, hysteresis: int = 5,
                 confirm_k: int = 3, confirm_window_s: float = 2.0,
                 absent_timeout_s: float = 12.0, alpha: float = 0.35):
        self.db = db_manager
        self.outer_scanner_id = (outer_scanner_id or "").strip().lower()
        self.inner_scanner_id = (inner_scanner_id or "").strip().lower()
        self.rssi_threshold = rssi_threshold
        self.hysteresis = hysteresis  # dBm hysteresis to prevent flicker
        # Robust signal processing params
        self.confirm_k = confirm_k
        self.confirm_window_s = confirm_window_s
        self.absent_timeout_s = absent_timeout_s
        self.alpha = alpha
        # Ignore very weak tails to avoid false flips (raise floor to reduce flapping)
        self.rssi_floor_dbm = -70
        # Quick-weak timeout so we don't wait full absent_timeout to begin exit
        self.weak_timeout_s = 3.0
        # FSM timing parameters aligned with diagram
        # Direction-specific pair windows: exit reflections are slower
        self.w_pair_enter_s = 6.0   # OUTER->INNER within this window to commit ENTERED
        self.w_pair_exit_s = 15.0   # INNER->OUTER within this window to commit EXITED
        # Dominance commit windows as a fallback if pairs are missed
        self.dom_enter_s = 4.0      # sustained inner strong with outer weak
        self.dom_exit_s = 6.0       # sustained outer strong with inner weak
        self.d_clear_s = 3.0     # Duration to be clear before committing exit
        # After ENTERED, if there is no movement for 30 minutes, go back to IDLE
        self.t_idle_s = 1800.0   # Timeout to IDLE from ENTERED (inactivity)
        # Keep a longer timeout for EXITED before collapsing to IDLE
        self.t_idle_long_s = 3600.0  # Timeout to IDLE from EXITED (long absence)
        
        # State cache for performance
        self.beacon_states: Dict[str, BeaconFSM] = {}
        self._states_loaded = False
        # Delay loading states until first use to avoid blocking API startup
        self._lazy_load_states()
    
    def load_beacon_states(self):
        """Load all beacon states from database."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT beacon_id, current_state, last_outer_seen, last_inner_seen,
                           entry_timestamp, exit_timestamp, updated_at
                    FROM beacon_states
                """)
                
                for row in cursor.fetchall():
                    beacon_id = row[0]
                    # Normalize possible string timestamps to timezone-aware datetime
                    def norm(ts):
                        if ts is None:
                            return None
                        if isinstance(ts, str):
                            try:
                                dt = datetime.fromisoformat(ts)
                            except Exception:
                                return None
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            return dt
                        return ts
                    self.beacon_states[beacon_id] = BeaconFSM(
                        beacon_id=beacon_id,
                        current_state=FSMState(row[1]),
                        last_outer_seen=norm(row[2]),
                        last_inner_seen=norm(row[3]),
                        entry_timestamp=norm(row[4]),
                        exit_timestamp=norm(row[5]),
                        last_update=norm(row[6])
                    )
                logger.info(f"Loaded {len(self.beacon_states)} beacon states from database", "FSM")
        except Exception as e:
            logger.error(f"Failed to load beacon states: {e}. Starting with empty state.", "FSM")
            self.beacon_states = {}
        finally:
            self._states_loaded = True
    
    def _lazy_load_states(self):
        """Load states asynchronously to avoid blocking API startup."""
        import threading
        def load_async():
            try:
                self.load_beacon_states()
            except Exception as e:
                logger.error(f"Async state loading failed: {e}", "FSM")
                self._states_loaded = True
        
        thread = threading.Thread(target=load_async, daemon=True)
        thread.start()
    
    def process_detection(self, scanner_id: str, beacon_id: str, rssi: int) -> Optional[Tuple[FSMState, FSMState]]:
        """Disabled in single-scanner branch. Leave decisions to API server updater."""
        return None
        # Normalize scanner id to avoid case/whitespace mismatches
        try:
            scanner_id = (scanner_id or "").strip().lower()
        except Exception:
            pass
        # Drop very weak tails
        try:
            if rssi is not None and rssi < self.rssi_floor_dbm:
                return None
        except Exception:
            pass
        # Ensure states are loaded (wait briefly if needed)
        if not self._states_loaded:
            import time
            for _ in range(10):  # Wait up to 1 second
                if self._states_loaded:
                    break
                time.sleep(0.1)
            if not self._states_loaded:
                logger.warning("Processing detection before states fully loaded", "FSM")
        
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
        except Exception as e:
            logger.debug(f"Failed to get boat for beacon {beacon_id}: {e}", "FSM")
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
        
        # Update last seen timestamps and EMA/trend per scanner
        outer_trending_closer = False
        inner_trending_closer = False
        if is_outer:
            beacon_state.last_outer_seen = now
            prev = beacon_state.ema_outer
            if prev is None:
                beacon_state.ema_outer = float(rssi)
            else:
                new_ema = self.alpha * float(rssi) + (1.0 - self.alpha) * prev
                outer_trending_closer = new_ema > prev
                beacon_state.ema_outer = new_ema
        if is_inner:
            beacon_state.last_inner_seen = now
            prev = beacon_state.ema_inner
            if prev is None:
                beacon_state.ema_inner = float(rssi)
            else:
                new_ema = self.alpha * float(rssi) + (1.0 - self.alpha) * prev
                inner_trending_closer = new_ema > prev
                beacon_state.ema_inner = new_ema

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

        # Quick weak flags based on short silence windows (do not wait full absent_timeout)
        def quick_weak(last_seen: Optional[datetime]) -> bool:
            if last_seen is None:
                return True
            return (now - last_seen).total_seconds() > self.weak_timeout_s
        inner_quick_weak = quick_weak(beacon_state.last_inner_seen)
        outer_quick_weak = quick_weak(beacon_state.last_outer_seen)

        # Update dominance timers (sustained strength on one side while the other is weak)
        if outer_strong and inner_quick_weak:
            if beacon_state.outer_dominant_start is None:
                beacon_state.outer_dominant_start = now
        else:
            beacon_state.outer_dominant_start = None

        if inner_strong and outer_quick_weak:
            if beacon_state.inner_dominant_start is None:
                beacon_state.inner_dominant_start = now
        else:
            beacon_state.inner_dominant_start = None

        strong_signal = outer_strong if is_outer else inner_strong
        weak_signal = outer_weak if is_outer else inner_weak
        
        # Fast pair-commit using immediate strong-now flags to avoid confirm latency
        fast_commit: Optional[FSMState] = None
        try:
            if is_inner and inner_strong_now and (beacon_state.last_outer_seen is not None) \
               and (now - beacon_state.last_outer_seen).total_seconds() <= self.w_pair_enter_s:
                fast_commit = FSMState.ENTERED
            elif is_outer and outer_strong_now and (beacon_state.last_inner_seen is not None) \
                 and (now - beacon_state.last_inner_seen).total_seconds() <= self.w_pair_exit_s:
                fast_commit = FSMState.EXITED
        except Exception:
            fast_commit = None

        # State machine logic (direction-aware with quick-weak gating)
        new_state = fast_commit or self._transition_state(
            beacon_state,
            is_outer,
            is_inner,
            strong_signal,
            weak_signal,
            now,
            inner_trending_closer,
            outer_trending_closer,
            inner_quick_weak,
            outer_quick_weak,
            inner_strong,
            outer_strong,
        )
        try:
            logger.debug(
                f"FSM_DECISION beacon={beacon_id} side={'outer' if is_outer else ('inner' if is_inner else 'unknown')} "
                f"rssi={rssi} strong={strong_signal} weak={weak_signal} innerStrong={inner_strong} outerStrong={outer_strong} "
                f"innerWeakQ={inner_quick_weak} outerWeakQ={outer_quick_weak} innerTrendUp={inner_trending_closer} outerTrendUp={outer_trending_closer} "
                f"state={old_state.value}→{new_state.value} lastInner={beacon_state.last_inner_seen} lastOuter={beacon_state.last_outer_seen}",
                "FSM"
            )
        except Exception:
            pass
        
        if new_state != old_state:
            beacon_state.current_state = new_state
            beacon_state.last_update = now
            
            # Update timestamps for entry/exit events and log trips
            if new_state == FSMState.ENTERED:
                beacon_state.entry_timestamp = now
                # Log trip end when boat returns to shed
                if beacon_state.boat_id:
                    try:
                        trip_id, duration = self.db.end_trip(beacon_state.boat_id, beacon_id, now)
                        if trip_id:
                            logger.info(f"Trip completed for boat {beacon_state.boat_id}: {duration} min", "TRIP")
                    except Exception as e:
                        logger.error(f"Failed to end trip: {e}", "TRIP")
            elif new_state == FSMState.EXITED:
                beacon_state.exit_timestamp = now
                # Log trip start when boat exits to water
                if beacon_state.boat_id:
                    try:
                        trip_id = self.db.start_trip(beacon_state.boat_id, beacon_id, now)
                        logger.info(f"Trip started for boat {beacon_state.boat_id}: {trip_id}", "TRIP")
                    except Exception as e:
                        logger.error(f"Failed to start trip: {e}", "TRIP")
            
            # Save to database
            self._save_beacon_state(beacon_state)
            
            # Log detection
            self.db.log_detection(scanner_id, beacon_id, rssi, DetectionState(new_state.value))
            
            # Reflect boat status for dashboard on hard transitions
            try:
                if beacon_state.boat_id:
                    from .database_models import BoatStatus
                    if new_state in (FSMState.INSIDE, FSMState.ENTERED):
                        self.db.update_boat_status(beacon_state.boat_id, BoatStatus.IN_HARBOR)
                    elif new_state in (FSMState.OUTSIDE, FSMState.EXITED):
                        self.db.update_boat_status(beacon_state.boat_id, BoatStatus.OUT)
            except Exception:
                pass

            # Log state change with context
            if new_state == FSMState.IDLE and old_state != FSMState.IDLE:
                logger.info(f"Beacon timeout: {beacon_id} - {old_state.value} → {new_state.value} (no signal for 5+ minutes)", "FSM")
            else:
                logger.info(f"Beacon state change: {beacon_id} - {old_state.value} → {new_state.value} (RSSI: {rssi} dBm)", "FSM")
            
            return (old_state, new_state)
        
        return None

    def _transition_state(self, beacon_state: BeaconFSM, is_outer: bool, is_inner: bool, 
                         strong_signal: bool, weak_signal: bool, now: datetime,
                         inner_trending_closer: bool, outer_trending_closer: bool,
                         inner_weak_flag: bool, outer_weak_flag: bool,
                         inner_strong_flag: bool, outer_strong_flag: bool) -> FSMState:
        """Simple 5-state FSM matching physical movement patterns."""
        current = beacon_state.current_state
        
        # Helper functions
        def within_window(timestamp: Optional[datetime], window_s: float) -> bool:
            if timestamp is None:
                return False
            return (now - timestamp).total_seconds() <= window_s
        
        def cleared_duration(timestamp: Optional[datetime], duration_s: float) -> bool:
            if timestamp is None:
                return True
            return (now - timestamp).total_seconds() >= duration_s
        
        # Global pair-commit overrides: commit regardless of current when clear pair is observed
        if is_inner and strong_signal and within_window(beacon_state.last_outer_seen, self.w_pair_enter_s):
            return FSMState.ENTERED
        if is_outer and strong_signal and within_window(beacon_state.last_inner_seen, self.w_pair_exit_s):
            return FSMState.EXITED

        # Dominance-based commits (fallback if pair was missed due to jitter)
        if beacon_state.inner_dominant_start and (now - beacon_state.inner_dominant_start).total_seconds() >= self.dom_enter_s:
            beacon_state.pending_since = None
            return FSMState.ENTERED
        if beacon_state.outer_dominant_start and (now - beacon_state.outer_dominant_start).total_seconds() >= self.dom_exit_s:
            beacon_state.pending_since = None
            return FSMState.EXITED

        if current == FSMState.IDLE:
            if is_inner and strong_signal:
                return FSMState.ENTERED
            elif is_outer and strong_signal:
                return FSMState.EXITED
                
        elif current == FSMState.ENTERED:
            # Exit sequence starts: inner strong while outer is weak/recently absent
            if is_inner and strong_signal and inner_weak_flag and not outer_trending_closer:
                beacon_state.pending_since = now
                return FSMState.GOING_OUT
            # Long idle timeout
            elif cleared_duration(beacon_state.last_inner_seen, self.t_idle_s) and cleared_duration(beacon_state.last_outer_seen, self.t_idle_s):
                return FSMState.IDLE
                
        elif current == FSMState.GOING_OUT:
            # Complete exit: outer strong within pair window from last INNER
            if is_outer and strong_signal and within_window(beacon_state.last_inner_seen, self.w_pair_exit_s):
                beacon_state.pending_since = None
                return FSMState.EXITED
            # Corrective: if inner becomes strong within window from last OUTER, this was actually an ENTRY
            if is_inner and strong_signal and within_window(beacon_state.last_outer_seen, self.w_pair_enter_s):
                beacon_state.pending_since = None
                return FSMState.ENTERED
            # Timeout on pending regardless of continuous inner activity
            if beacon_state.pending_since and (now - beacon_state.pending_since).total_seconds() > self.w_pair_exit_s:
                beacon_state.pending_since = None
                return FSMState.ENTERED
                
        elif current == FSMState.EXITED:
            # Re-entry sequence starts: outer strong while inner is weak/recently absent
            if is_outer and strong_signal and inner_weak_flag and not outer_trending_closer:
                beacon_state.pending_since = now
                return FSMState.GOING_IN
            # Long idle timeout
            elif cleared_duration(beacon_state.last_outer_seen, self.t_idle_long_s) and cleared_duration(beacon_state.last_inner_seen, self.t_idle_long_s):
                return FSMState.IDLE
                
        elif current == FSMState.GOING_IN:
            # Complete entry: inner strong within pair window from last OUTER
            if is_inner and strong_signal and within_window(beacon_state.last_outer_seen, self.w_pair_enter_s):
                beacon_state.pending_since = None
                return FSMState.ENTERED
            # Corrective: if outer becomes strong within window from last INNER, this was actually an EXIT
            if is_outer and strong_signal and within_window(beacon_state.last_inner_seen, self.w_pair_exit_s):
                beacon_state.pending_since = None
                return FSMState.EXITED
            # Timeout on pending regardless of continuous outer activity
            if beacon_state.pending_since and (now - beacon_state.pending_since).total_seconds() > self.w_pair_enter_s:
                beacon_state.pending_since = None
                return FSMState.EXITED
        
        return current

    def _is_timeout(self, last_seen: Optional[datetime], now: datetime, threshold: timedelta) -> bool:
        """Check if last seen time exceeds threshold."""
        if last_seen is None:
            return True
        return (now - last_seen) > threshold
    
    def _update_scores_and_dominance(self, beacon_state: BeaconFSM, outer_strong: bool, inner_strong: bool, 
                                   outer_weak: bool, inner_weak: bool, now: datetime):
        """Update directional scores and dominance timing."""
        # Aggressive scoring for faster commitment
        decay_factor = 0.8  # Faster decay
        
        # Enter score: stronger when inner stronger than outer
        if inner_strong and not outer_strong:
            beacon_state.enter_score = beacon_state.enter_score * decay_factor + 2.0  # Faster buildup
        elif outer_strong and not inner_strong:
            beacon_state.enter_score = max(0, beacon_state.enter_score * decay_factor - 1.0)
        else:
            beacon_state.enter_score = beacon_state.enter_score * decay_factor
            
        # Exit score: stronger when outer stronger than inner  
        if outer_strong and not inner_strong:
            beacon_state.exit_score = beacon_state.exit_score * decay_factor + 2.0  # Faster buildup
        elif inner_strong and not outer_strong:
            beacon_state.exit_score = max(0, beacon_state.exit_score * decay_factor - 1.0)
        else:
            beacon_state.exit_score = beacon_state.exit_score * decay_factor
            
        # Track dominance timing
        if outer_strong and inner_weak:
            if beacon_state.outer_dominant_start is None:
                beacon_state.outer_dominant_start = now
        else:
            beacon_state.outer_dominant_start = None
            
        if inner_strong and outer_weak:
            if beacon_state.inner_dominant_start is None:
                beacon_state.inner_dominant_start = now
        else:
            beacon_state.inner_dominant_start = None
    
    def _check_dominance(self, start_time: Optional[datetime], now: datetime, condition: bool) -> bool:
        """Check if dominance condition has been sustained for required duration."""
        if not condition or start_time is None:
            return False
        return (now - start_time).total_seconds() >= self.dominance_window_s
    
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
