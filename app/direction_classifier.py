#!/usr/bin/env python3
"""
Direction Classifier (Door Left/Right): lag/peak/threshold majority voting.
Skeleton implementation with data structures and method stubs per brief.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Dict, Literal, Optional, List
from collections import deque


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
    direction: Literal["ENTER", "LEAVE"]
    timestamp: float
    confidence: float
    meta: Dict


class DirectionClassifier:
    def __init__(self, params: LRParams, calib_map: Dict[str, str], logger):
        self.params = params
        self.calib_map = calib_map or {"lag_positive": "LEAVE", "lag_negative": "ENTER"}
        self.logger = logger
        self.state_by_beacon: Dict[str, BeaconState] = {}

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
        # TODO: implement clip->median->EMA; record t,x
        rs.times.append(t)
        rs.values.append(x_dbm)
        return x_dbm

    def _slope(self, rs: RollingSeries, window_s: float = 0.3) -> float:
        # TODO: implement linear fit slope over window
        return 0.0

    def _first_stable_crossing(self, rs: RollingSeries, thr_dbm: float, dwell_s: float) -> Optional[float]:
        # TODO: implement dwell-based threshold crossing time
        return None

    def _xcorr_lag(self, L: RollingSeries, R: RollingSeries, max_lag_s: float = 0.6) -> Optional[float]:
        # TODO: implement discrete lag scan
        return None

    def _main_peak_time(self, rs: RollingSeries) -> Optional[float]:
        # TODO: implement peak detection (simple argmax of filtered series)
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
        # Assume external provides profile config (ema_alpha, median_len, clip)
        ema_alpha = 0.3
        median_len = 3
        clip_dbm = -80
        st = self._get_state(beacon_id, ema_alpha, median_len, clip_dbm)

        # Route sample
        if scanner_id.endswith('left') or scanner_id.endswith('door-left') or scanner_id.endswith('gate-left'):
            Lf = self._filter(st.left, rssi_dbm, t)
            Rf = st.right.values[-1] if st.right.values else None
        else:
            Rf = self._filter(st.right, rssi_dbm, t)
            Lf = st.left.values[-1] if st.left.values else None

        # Minimal state machine placeholder; to be implemented per brief
        # Keep skeleton to avoid breaking imports.
        return evs


