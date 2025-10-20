#!/usr/bin/env python3
"""
Direction Classifier (Door Left/Right): lag/peak/threshold majority voting.
Skeleton implementation with data structures and method stubs per brief.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Dict, Literal, Optional, List
from collections import deque
from .logging_config import get_logger

logger = get_logger()


@dataclass
class LRParams:
    active_dbm: float
    energy_dbm: float
    delta_db: float
    dwell_s: float
    window_s: float
    tau_min_s: float
    cooldown_s: float
    slope_min_db_per_s: float
    min_peak_sep_s: float


@dataclass
class RollingSeries:
    times: Deque[float]
    values: Deque[float]
    ema_alpha: float
    median_len: int
    clip_dbm: float


@dataclass
class BeaconState:
    state: Literal["IDLE", "ARMED", "DECIDING", "DECIDED", "COOLDOWN"]
    t_arm: Optional[float]
    t_cooldown: Optional[float]
    tL1: Optional[float]
    tR1: Optional[float]
    last_emit_ts: Optional[float]
    calib_map: Dict[str, str]
    left: RollingSeries
    right: RollingSeries


@dataclass
class Event:
    beacon_id: str
    direction: str
    timestamp: float
    confidence: float
    scanner_id: str = ""
    rssi: float = 0.0


class DirectionClassifier:
    def __init__(self, params: LRParams, calib_map: Dict[str, str], logger, calib_path: str = None):
        self.params = params
        self.calib_map = calib_map or {"lag_positive": "LEAVE", "lag_negative": "ENTER"}
        self.logger = logger
        self.state_by_beacon: Dict[str, BeaconState] = {}
        
        # Load calibration data
        self.calibration = None
        self.rssi_offsets = {'gate-left': 0.0, 'gate-right': 0.0, 'door-left': 0.0, 'door-right': 0.0}
        self._load_calibration(calib_path)
    
    def _load_calibration(self, calib_path: str = None):
        """Load calibration data from file"""
        import json
        import os
        
        # Try default path if none provided
        if not calib_path:
            calib_path = 'calibration/sessions/latest/door_lr_calib.json'
        
        if not os.path.exists(calib_path):
            self.logger.warning(f"No calibration file found at {calib_path} - using default offsets (0.0 dB)")
            return
        
        try:
            with open(calib_path, 'r') as f:
                self.calibration = json.load(f)
            
            # Extract RSSI offsets
            if 'rssi_offsets' in self.calibration:
                self.rssi_offsets.update(self.calibration['rssi_offsets'])
                self.logger.info(f"Loaded calibration from {calib_path}")
                self.logger.info(f"  Offsets: L={self.rssi_offsets['gate-left']:+.2f} dB, R={self.rssi_offsets['gate-right']:+.2f} dB")
                
                # Update thresholds if available
                if 'thresholds' in self.calibration:
                    t = self.calibration['thresholds']
                    self.logger.info(f"  Thresholds loaded: strong_left={t.get('strong_left', 'N/A')}, strong_right={t.get('strong_right', 'N/A')}")
            else:
                self.logger.warning(f"Calibration file found but no rssi_offsets - using defaults")
        
        except Exception as e:
            self.logger.error(f"Failed to load calibration: {e} - using default offsets")
            self.calibration = None

    def _new_series(self, ema_alpha: float, median_len: int, clip_dbm: float) -> RollingSeries:
        return RollingSeries(times=deque(maxlen=256), values=deque(maxlen=256), ema_alpha=ema_alpha, median_len=median_len, clip_dbm=clip_dbm)

    def _get_state(self, beacon_id: str, ema_alpha: float, median_len: int, clip_dbm: float) -> BeaconState:
        st = self.state_by_beacon.get(beacon_id)
        if st:
            return st
        st = BeaconState(
            state="IDLE",
            t_arm=None,
            t_cooldown=None,
            tL1=None,
            tR1=None,
            last_emit_ts=None,
            calib_map=dict(self.calib_map),
            left=self._new_series(ema_alpha, median_len, clip_dbm),
            right=self._new_series(ema_alpha, median_len, clip_dbm),
        )
        self.state_by_beacon[beacon_id] = st
        return st

    # --- helpers (stubs) ---
    def _filter(self, rs: RollingSeries, x_dbm: float, t: float) -> float:
        # Clip very low noise and update series
        clip = max(x_dbm, rs.clip_dbm)
        rs.times.append(t)
        rs.values.append(clip)
        # Simple EMA
        if not hasattr(rs, 'ema'):
            rs.ema = clip
        else:
            rs.ema = rs.ema_alpha * clip + (1.0 - rs.ema_alpha) * rs.ema
        return rs.ema

    def _slope(self, rs: RollingSeries, window_s: float = 0.3) -> float:
        if not rs.times:
            return 0.0
        t_end = rs.times[-1]
        xs: List[float] = []
        ys: List[float] = []
        for ti, vi in zip(reversed(rs.times), reversed(rs.values)):
            if t_end - ti > window_s:
                break
            xs.append(ti)
            ys.append(vi)
        if len(xs) < 2:
            return 0.0
        n = float(len(xs))
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = sum((x - mean_x) ** 2 for x in xs) or 1e-6
        return num / den

    def _first_stable_crossing(self, rs: RollingSeries, thr_dbm: float, dwell_s: float) -> Optional[float]:
        if not rs.times:
            return None
        for i in range(len(rs.values)):
            if rs.values[i] >= thr_dbm:
                t0 = rs.times[i]
                j = i
                ok = True
                while j < len(rs.values) and rs.times[j] - t0 <= dwell_s:
                    if rs.values[j] < thr_dbm:
                        ok = False
                        break
                    j += 1
                if ok:
                    return rs.times[i]
        return None

    def _xcorr_lag(self, L: RollingSeries, R: RollingSeries, max_lag_s: float = 0.6) -> Optional[float]:
        tL = self._first_stable_crossing(L, self.params.energy_dbm, self.params.dwell_s)
        tR = self._first_stable_crossing(R, self.params.energy_dbm, self.params.dwell_s)
        if tL is None or tR is None:
            return None
        lag = tR - tL
        if abs(lag) > max_lag_s:
            return None
        return lag

    def _main_peak_time(self, rs: RollingSeries) -> Optional[float]:
        if not rs.values:
            return None
        vmax = max(rs.values)
        for i, v in enumerate(rs.values):
            if v == vmax:
                return rs.times[i]
        return None

    def _delta_zero_time(self, L: RollingSeries, R: RollingSeries) -> Optional[float]:
        # TODO: find time when L-R crosses zero (interpolated)
        return None

    def _majority(self, votes: List[str]) -> Optional[str]:
        if not votes:
            return None
        from collections import Counter
        c = Counter(votes)
        best, cnt = c.most_common(1)[0]
        return best if cnt >= 2 or len(votes) == 1 else None

    # --- main ingest/update ---
    def update(self, beacon_id: str, scanner_id: str, rssi_dbm: float, t: float) -> List[Event]:
        evs: List[Event] = []
        p = self.params
        
        # Apply calibration offsets
        rssi_corrected = rssi_dbm
        sid = (scanner_id or '').lower()
        
        if 'left' in sid or 'inner' in sid:
            offset = self.rssi_offsets.get('gate-left', 0.0)
            rssi_corrected = rssi_dbm - offset
            if abs(offset) > 0.1:
                self.logger.debug(f"Applied offset to LEFT: {rssi_dbm:.1f} → {rssi_corrected:.1f} dBm (offset: {offset:+.2f})")
        elif 'right' in sid or 'outer' in sid:
            offset = self.rssi_offsets.get('gate-right', 0.0)
            rssi_corrected = rssi_dbm - offset
            if abs(offset) > 0.1:
                self.logger.debug(f"Applied offset to RIGHT: {rssi_dbm:.1f} → {rssi_corrected:.1f} dBm (offset: {offset:+.2f})")
        
        # Get or create beacon state
        st = self._get_state(beacon_id, 0.3, 3, -80)
        
        # Route sample to appropriate scanner (using corrected RSSI)
        if scanner_id.endswith('left') or scanner_id.endswith('door-left') or scanner_id.endswith('gate-left'):
            self._filter(st.left, rssi_corrected, t)
        else:
            self._filter(st.right, rssi_corrected, t)
        
        # Debug logging
        logger.debug(f"DirectionClassifier: beacon={beacon_id}, scanner={scanner_id}, rssi={rssi_dbm}, state={st.state}")
        logger.debug(f"  Left values: {len(st.left.values)}, Right values: {len(st.right.values)}")
        
        # Check if we have enough data to make a decision
        if len(st.left.values) < 1 or len(st.right.values) < 1:
            logger.debug(f"  Not enough data: left={len(st.left.values)}, right={len(st.right.values)}")
            return evs
        
        # Get latest filtered values
        L_latest = st.left.values[-1] if st.left.values else None
        R_latest = st.right.values[-1] if st.right.values else None
        
        if L_latest is None or R_latest is None:
            logger.debug(f"  Latest values are None: L={L_latest}, R={R_latest}")
            return evs
        
        logger.debug(f"  Latest values: L={L_latest:.1f}, R={R_latest:.1f}")
        
        # Door-LR Logic: Determine direction based on which scanner sees stronger signal first
        # and the pattern of signal strength changes
        
        # Check if both scanners are active (above threshold) - make more sensitive
        L_active = L_latest >= p.active_dbm
        R_active = R_latest >= p.active_dbm
        
        logger.debug(f"  Active check: L_active={L_active} (>= {p.active_dbm}), R_active={R_active} (>= {p.active_dbm})")
        
        # State machine for door-lr detection - make it extremely aggressive
        if st.state == "IDLE":
            # As soon as we have any data from either scanner, start processing
            if len(st.left.values) >= 1 or len(st.right.values) >= 1:
                logger.debug(f"  Transitioning IDLE -> ARMED")
                st.state = "ARMED"
                st.t_arm = t
                st.tL1 = st.left.times[-1] if st.left.times else t
                st.tR1 = st.right.times[-1] if st.right.times else t
                
        elif st.state == "ARMED":
            # Make decision very quickly - reduce window time
            logger.debug(f"  ARMED state: t_arm={st.t_arm:.3f}, current_t={t:.3f}, diff={t - st.t_arm:.3f}")
            if t - st.t_arm > 0.1:  # Very short window
                logger.debug(f"  Transitioning ARMED -> DECIDING")
                st.state = "DECIDING"
                
                # Determine direction based on signal patterns
                direction = self._determine_direction(st, p)
                logger.debug(f"  Determined direction: {direction}")
                
                if direction:
                    logger.debug(f"  Transitioning DECIDING -> DECIDED")
                    st.state = "DECIDED"
                    st.last_emit_ts = t
                    
                    # Create event
                    event = Event(
                        beacon_id=beacon_id,
                        direction=direction,
                        confidence=0.9,  # High confidence
                        timestamp=t,
                        scanner_id=scanner_id,
                        rssi=rssi_dbm
                    )
                    evs.append(event)
                    logger.info(f"DirectionClassifier generated event: {direction} for {beacon_id}")
                    
                    # Enter cooldown
                    st.state = "COOLDOWN"
                    st.t_cooldown = t
                    
        elif st.state == "COOLDOWN":
            # Check if cooldown period has passed
            if t - st.t_cooldown > 0.5:  # Very short cooldown
                logger.debug(f"  Transitioning COOLDOWN -> IDLE")
                st.state = "IDLE"
                
        return evs
    
    def _determine_direction(self, st: BeaconState, p: LRParams) -> Optional[str]:
        """Determine direction: LEFT stronger = ENTER, RIGHT stronger = EXIT"""
        if not st.left.values or not st.right.values:
            return None
        
        L_avg = sum(st.left.values) / len(st.left.values)
        R_avg = sum(st.right.values) / len(st.right.values)
        
        # Simple: stronger left = ENTER (shed side), stronger right = EXIT (water side)
        return "ENTER" if L_avg > R_avg else "EXIT"


