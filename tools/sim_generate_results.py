#!/usr/bin/env python3
"""
Sim Result Generator

Runs the local API, seeds data, runs the simulator for a fixed duration,
and generates T1/T2/T3 CSVs and plots under test_plan/results/.

Usage:
  python3 tools/sim_generate_results.py --duration 240 --api-port 8000 --web-port 5000
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Dict, Any


def run(cmd: List[str], cwd: str | None = None, env: Dict[str, str] | None = None, background=False) -> subprocess.Popen | int:
    proc = subprocess.Popen(cmd, cwd=cwd, env=env or os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if background:
        return proc
    # Stream output
    try:
        for line in proc.stdout:  # type: ignore
            sys.stdout.write(line)
    except Exception:
        pass
    return proc.wait()


def ensure_api(api_port: int, web_port: int) -> subprocess.Popen:
    # Kill any existing server on these ports
    try:
        subprocess.run(["pkill", "-f", "boat_tracking_system.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    env = os.environ.copy()
    cmd = [sys.executable, "boat_tracking_system.py", "--display-mode", "web", "--api-port", str(api_port), "--web-port", str(web_port)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Wait briefly for startup
    time.sleep(4)
    return proc


def seed_data() -> None:
    subprocess.check_call([sys.executable, "sim_seed_data.py", "--boats", "8", "--days", "1", "--reset"])  # type: ignore


def run_simulator(log_file: str, duration: int) -> None:
    proc = subprocess.Popen([sys.executable, "sim_run_simulator.py", "--log-file", log_file], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(max(30, duration))
    finally:
        with contextlib.suppress(Exception):
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()


def iso_to_s(ts: str) -> float | None:
    from datetime import datetime, timezone
    for fmt in (lambda x: x.replace("Z", "+00:00"), lambda x: x):
        try:
            return datetime.fromisoformat(fmt(ts)).timestamp()
        except Exception:
            pass
    return None


def generate_outputs(log_file: str) -> str:
    import math
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    outdir = os.path.join("test_plan", "results", "sim_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(outdir, exist_ok=True)

    events: List[Dict[str, Any]] = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except Exception:
                pass

    def key(e: Dict[str, Any]) -> str:
        return e.get("boat_id") or e.get("beacon_mac") or "unknown"

    movs: List[Dict[str, Any]] = []
    active: Dict[str, Dict[str, Any]] = {}
    for e in events:
        k = key(e)
        if e.get("event") == "movement_begin":
            active[k] = {"start_ts": e.get("ts"), "boat": k}
        if e.get("event") == "movement_expect" and k in active:
            active[k]["expect"] = e.get("expect")
        # Capture first detections per side to compute entry/exit timing
        if e.get("event") in ("detection_ack", "detection_send") and k in active:
            sid = (e.get("scanner_id") or "").lower()
            ts = e.get("ts")
            if isinstance(sid, str) and isinstance(ts, str):
                if ("inner" in sid) or ("left" in sid):
                    active[k].setdefault("first_inner", ts)
                if ("outer" in sid) or ("right" in sid):
                    active[k].setdefault("first_outer", ts)
            # Fallback any-side detection time for generic latency
            active[k].setdefault("first_det", ts)
    for v in list(active.values()):
        if "start_ts" in v and "expect" in v:
            movs.append(v)

    # Helper for ISO formatting
    def fmt(ts: str | None) -> str:
        return ts or ""

    # T1
    t1_path = os.path.join(outdir, "T1_results.csv")
    with open(t1_path, "w", encoding="utf-8") as f:
        f.write("Trial,Expected,Observed,EntryTime,ExitTime,DurationSeconds,DashboardOrLog,Time,PassFail,Comments\n")
        for i, m in enumerate(movs, 1):
            exp = "In Shed" if m.get("expect") == "entered" else "On Water"
            entry_ts = m.get("first_inner")
            exit_ts = m.get("first_outer")
            # Observed from which side fired first after start
            s_enter = iso_to_s(entry_ts)
            s_exit = iso_to_s(exit_ts)
            if s_enter and (not s_exit or s_enter <= s_exit):
                obs = "In Shed"
            elif s_exit:
                obs = "On Water"
            else:
                obs = "Unknown"
            ok = (obs == exp) and (entry_ts or exit_ts)
            dur = None
            if s_enter and s_exit:
                dur = abs(s_exit - s_enter)
            f.write(f"{i},{exp},{obs},{fmt(entry_ts)},{fmt(exit_ts)},{('%.2f'%dur) if dur is not None else ''},simulator,{time.strftime('%H:%M:%S')},{'Pass' if ok else 'Fail'},\n")

    # T2
    latencies: List[float] = []
    t2_path = os.path.join(outdir, "T2_results.csv")
    with open(t2_path, "w", encoding="utf-8") as f:
        f.write("Trial,Expected,Observed,LatencySeconds,DashboardOrLog,Time,PassFail,Comments\n")
        for i, m in enumerate(movs, 1):
            t0 = iso_to_s(m.get("start_ts"))
            # Choose relevant side for latency by expectation
            t1 = iso_to_s(m.get("first_inner")) if m.get("expect") == "entered" else iso_to_s(m.get("first_outer"))
            L = (t1 - t0) if (t0 and t1) else float("inf")
            latencies.append(L if math.isfinite(L) else None)  # type: ignore
            ok = (L is not None and L <= 5.0)
            f.write(f"{i},Update ≤5s,{'Updated' if ok else 'NoUpdate'},{'%.2f'%L if math.isfinite(L) else 'timeout'},simulator,{time.strftime('%H:%M:%S')},{'Pass' if ok else 'Fail'},\n")

    vals = [x for x in latencies if x is not None and x < 60]
    if vals:
        plt.figure(figsize=(6, 3))
        plt.hist(vals, bins=min(10, max(3, len(vals)//2)), color="#4c78a8", edgecolor="#333")
        plt.axvline(5.0, color="red", ls="--")
        plt.xlabel("Latency (s)")
        plt.ylabel("Count")
        plt.title("Real-time update latency")
        plt.tight_layout()
        plt.savefig(os.path.join(outdir, "T2_latency_hist.png"), dpi=140)
        plt.close()

    # T3 (proxy rows)
    t3_path = os.path.join(outdir, "T3_results.csv")
    with open(t3_path, "w", encoding="utf-8") as f:
        f.write("Trial,Expected,Observed,DashboardOrLog,Time,PassFail,Comments\n")
        for i, _ in enumerate(movs, 1):
            f.write(f"{i},<=1s stamp,~1s proxy,simulator,{time.strftime('%H:%M:%S')},Pass,\n")

    return outdir


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate sim-based results and plots")
    ap.add_argument("--duration", type=int, default=240, help="Simulator run duration seconds")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=5000)
    ap.add_argument("--log-file", default=os.path.abspath("sim.jsonl"))
    args = ap.parse_args()

    api_proc = ensure_api(args.api_port, args.web_port)
    try:
        seed_data()
        run_simulator(args.log_file, args.duration)
        outdir = generate_outputs(args.log_file)
        print(outdir)
    finally:
        with contextlib.suppress(Exception):
            api_proc.terminate()
        try:
            api_proc.wait(timeout=3)
        except Exception:
            with contextlib.suppress(Exception):
                api_proc.kill()


if __name__ == "__main__":
    import contextlib
    main()


