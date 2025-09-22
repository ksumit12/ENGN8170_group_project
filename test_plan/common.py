#!/usr/bin/env python3
"""
Common helpers for test_plan benchmarks:
- Synthetic RSSI generator for two scanners (S1/S2)
- Simple inline FSM (replace with production FSM adapter if desired)
- Filtering (median + EWMA), trend, visuals
"""

import os, math, random
from collections import deque, namedtuple
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import medfilt


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def savefig(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def ewma(x, alpha, y0=None):
    out = np.empty_like(x, dtype=float)
    y = x[0] if y0 is None else y0
    for i, xi in enumerate(x):
        y = alpha * xi + (1 - alpha) * y
        out[i] = y
    return out


def derivative(y, t, span_s=1.0):
    out = np.zeros_like(y, dtype=float)
    n = len(y)
    if n < 2:
        return out
    dt = t[1] - t[0]
    k = max(1, int(round(span_s / dt)))
    for i in range(n):
        j = max(0, i - k)
        if t[i] == t[j]:
            out[i] = 0.0
        else:
            out[i] = (y[i] - y[j]) / (t[i] - t[j])
    return out


Phase = namedtuple("Phase", "name dur_s rssi_S1 rssi_S2 note")


def _rssi(v):
    return (lambda s: v(s)) if callable(v) else (lambda s: v)


def generate_trace(phases: List[Phase], dt=0.2, noise_sigma=2.0, dropout=0.0, seed=1):
    rng = random.Random(seed)
    rows = []
    t = 0.0
    for p in phases:
        steps = int(round(p.dur_s / dt))
        r1 = _rssi(p.rssi_S1)
        r2 = _rssi(p.rssi_S2)
        for k in range(steps):
            base1 = r1(k * dt)
            base2 = r2(k * dt)
            if base1 is not None and rng.random() > dropout:
                rows.append([t, "S1", "B1", base1 + rng.gauss(0, noise_sigma), p.name])
            if base2 is not None and rng.random() > dropout:
                rows.append([t, "S2", "B1", base2 + rng.gauss(0, noise_sigma), p.name])
            t += dt
    df = pd.DataFrame(rows, columns=["t", "scanner", "beacon", "rssi", "gt_state"])
    return df


def default_phases():
    return [
        Phase("INSIDE", 6, -60, -88, "deep inside"),
        Phase("MOVING", 3, -63, -78, "approach gate"),
        Phase("AT_GATE", 3, -66, -65, "at gate both visible"),
        Phase("EXITING", 3, -80, -62, "past gate"),
        Phase("OUTSIDE", 6, None, -72, "outside; S1 lost"),
        Phase("ENTERING", 3, -78, -66, "returning"),
        Phase("INSIDE", 6, -60, -88, "back inside"),
    ]


@dataclass
class FSMParams:
    S1_HIGH: float = -67
    S1_LOW: float = -75
    S2_HIGH: float = -67
    S2_LOW: float = -75
    V_TH: float = 3.0
    DELTA_POS: float = +6.0
    DELTA_NEG: float = -6.0
    CONFIRM_K: int = 3
    WIN_S: float = 2.0


class RollingBool:
    def __init__(self, win_s, dt):
        from collections import deque
        self.n = max(1, int(round(win_s / dt)))
        self.buf = deque(maxlen=self.n)

    def push(self, b):
        self.buf.append(bool(b))

    def good(self, k):
        return sum(self.buf) >= k


class BeaconFSM:
    """Reference FSM for simulation. Replace with production FSM if desired."""

    def __init__(self, params: FSMParams, dt=0.2):
        self.p = params
        self.state = "INSIDE"
        self.last_in = None
        self.last_out = None
        self.dt = dt
        self.rb = {k: RollingBool(self.p.WIN_S, dt) for k in [
            "S1s", "S2s", "S1w", "S2w", "S1a", "S2a", "S1r", "S2r", "Dpos", "Dneg"
        ]}

    def step(self, t, f1, f2, v1, v2):
        S1s = (f1 is not None and f1 >= self.p.S1_HIGH)
        S2s = (f2 is not None and f2 >= self.p.S2_HIGH)
        S1w = (f1 is None) or (f1 <= self.p.S1_LOW)
        S2w = (f2 is None) or (f2 <= self.p.S2_LOW)
        S1a = (v1 is not None and v1 >= self.p.V_TH)
        S2a = (v2 is not None and v2 >= self.p.V_TH)
        S1r = (v1 is not None and v1 <= -self.p.V_TH)
        S2r = (v2 is not None and v2 <= -self.p.V_TH)
        D = None if (f1 is None or f2 is None) else (f2 - f1)
        Dpos = (D is not None and D >= self.p.DELTA_POS)
        Dneg = (D is not None and D <= self.p.DELTA_NEG)

        for k, b in zip(
            ["S1s", "S2s", "S1w", "S2w", "S1a", "S2a", "S1r", "S2r", "Dpos", "Dneg"],
            [S1s, S2s, S1w, S2w, S1a, S2a, S1r, S2r, Dpos, Dneg],
        ):
            self.rb[k].push(b)

        k = self.p.CONFIRM_K
        st = self.state
        if st == "INSIDE":
            if self.rb["S1s"].good(k) and (self.rb["S1a"].good(k) or self.rb["Dpos"].good(k)):
                self.state = "MOVING"
        elif st == "MOVING":
            if self.rb["S2s"].good(k):
                self.state = "AT_GATE"
            elif self.rb["S1w"].good(k):
                self.state = "INSIDE"
        elif st == "AT_GATE":
            if (self.rb["S2a"].good(k) and self.rb["S1r"].good(k)) or self.rb["Dpos"].good(k):
                self.state = "EXITING"
        elif st == "EXITING":
            if self.rb["S1w"].good(k) and self.rb["S2s"].good(k):
                self.last_out = t
                self.state = "OUTSIDE"
            elif self.rb["S2w"].good(k):
                self.state = "AT_GATE"
        elif st == "OUTSIDE":
            if (self.rb["S2a"].good(k) and not self.rb["S1w"].good(k)) or self.rb["Dneg"].good(k):
                self.state = "ENTERING"
        elif st == "ENTERING":
            if self.rb["S2w"].good(k) and self.rb["S1s"].good(k):
                self.last_in = t
                self.state = "INSIDE"

        return self.state


def _clean_series(x):
    xn = x.copy()
    s = pd.Series(xn).interpolate(limit=3).bfill().ffill().values
    med = medfilt(s, kernel_size=5)
    f = ewma(med, alpha=0.35)
    f[np.isnan(xn)] = np.nan
    return f


def run_trial(phases: List[Phase], out_dir: str, noise_sigma=2.0, dropout=0.0, dt=0.2, seed=1,
              params: FSMParams = FSMParams()):
    out_dir = ensure_dir(out_dir)
    df = generate_trace(phases, dt=dt, noise_sigma=noise_sigma, dropout=dropout, seed=seed)
    t = sorted(df.t.unique())
    T = np.array(t)

    def series(scanner):
        m = {row.t: row.rssi for row in df.itertuples() if row.scanner == scanner}
        return np.array([m.get(tt, np.nan) for tt in T])

    S1 = series("S1"); S2 = series("S2")
    F1 = _clean_series(S1); F2 = _clean_series(S2)
    V1 = derivative(np.nan_to_num(F1, nan=F1[~np.isnan(F1)][0]), T, span_s=1.0)
    V2 = derivative(np.nan_to_num(F2, nan=F2[~np.isnan(F2)][0]), T, span_s=1.0)

    fsm = BeaconFSM(params, dt=dt)
    states = []
    for i, tt in enumerate(T):
        f1 = None if np.isnan(F1[i]) else float(F1[i])
        f2 = None if np.isnan(F2[i]) else float(F2[i])
        v1 = None if np.isnan(F1[i]) else float(V1[i])
        v2 = None if np.isnan(F2[i]) else float(V2[i])
        states.append(fsm.step(tt, f1, f2, v1, v2))

    out_df = pd.DataFrame({
        "t": T,
        "gt": df.drop_duplicates("t").set_index("t").gt_state.reindex(T).bfill().ffill().values,
        "S1": S1, "S2": S2, "F1": F1, "F2": F2, "V1": V1, "V2": V2, "state": states,
    })
    out_df.to_csv(os.path.join(out_dir, "log.csv"), index=False)
    return out_df, fsm


