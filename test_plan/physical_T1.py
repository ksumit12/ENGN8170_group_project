#!/usr/bin/env python3
"""
Physical Test Runner: T1 Location Detection (R1)

Purpose
- Run a physical test by moving a real beacon and capturing observed location
  (In Shed vs On Water) from the running API.
- Record structured logs (JSONL), a CSV compatible with the result sheet, and plots.

Outputs (saved under test_plan/results/T1/<timestamp>/)
- results.csv              # Trial-by-trial summary (Expected, Observed, Pass/Fail)
- presence_log.jsonl       # Raw samples polled from the API during each trial
- status_over_time.png     # Timeline plot of observed in_harbor vs time

Requirements
- API server must be running (e.g. boat_tracking_system.py on port 8000)
- Python packages: requests, matplotlib (optional: rich for nicer prompts)

Usage
  python3 test_plan/physical_T1.py --boat-id BOAT123 [--server-url http://127.0.0.1:8000] \
      [--trials 10] [--sample-seconds 5] [--sample-rate-hz 2]

Notes
- Observed classification:
    in_harbor=True  -> "In Shed"
    in_harbor=False -> "On Water"
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

try:
    import requests
except Exception as e:  # pragma: no cover
    print("ERROR: requests is required. Try: pip install requests", file=sys.stderr)
    raise


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_out_dir(base_dir: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(base_dir, "results", "T1", ts)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def presence_snapshot(server_url: str, boat_id: str) -> Dict[str, Any]:
    r = requests.get(f"{server_url}/api/v1/presence/{boat_id}", timeout=3)
    r.raise_for_status()
    return r.json()


def observed_label(in_harbor: bool) -> str:
    return "In Shed" if in_harbor else "On Water"


def majority_vote(samples: List[bool]) -> bool:
    if not samples:
        return False
    counts = Counter(samples)
    return counts[True] >= counts[False]


def poll_presence_series(server_url: str, boat_id: str, sample_seconds: float, sample_rate_hz: float,
                         jsonl_path: str, trial_no: int) -> Tuple[List[float], List[bool]]:
    interval = 1.0 / max(sample_rate_hz, 0.1)
    end_time = time.time() + max(sample_seconds, 0.1)
    ts_list: List[float] = []
    inh_list: List[bool] = []

    with open(jsonl_path, "a", encoding="utf-8") as f:
        while True:
            now = time.time()
            if now > end_time:
                break
            try:
                data = presence_snapshot(server_url, boat_id)
                inh = bool(data.get("in_harbor", False))
                rec = {
                    "ts": iso_now(),
                    "trial": trial_no,
                    "in_harbor": inh,
                    "status": data.get("status"),
                    "last_seen": data.get("last_seen"),
                    "last_rssi": data.get("last_rssi"),
                }
                f.write(json.dumps(rec) + "\n")
                ts_list.append(now)
                inh_list.append(inh)
            except Exception as e:  # pragma: no cover
                rec = {"ts": iso_now(), "trial": trial_no, "error": str(e)}
                f.write(json.dumps(rec) + "\n")
            time.sleep(interval)

    return ts_list, inh_list


def write_csv_header(csv_path: str) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Trial",
            "Expected",
            "Observed",
            "DashboardOrLog",
            "Time",
            "PassFail",
            "Comments",
        ])


def append_csv_row(csv_path: str, row: List[str]) -> None:
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def plot_status_over_time(jsonl_path: str, png_path: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover
        print("Skipping plots (matplotlib not installed)")
        return

    times: List[float] = []
    vals: List[int] = []
    t0: float = None  # type: ignore

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if "in_harbor" not in obj:
                continue
            # Use file time offset for simple x-axis
            if t0 is None:
                t0 = time.time()
            times.append(time.time() - t0)
            vals.append(1 if obj.get("in_harbor") else 0)

    if not times:
        print("No data to plot")
        return

    plt.figure(figsize=(8, 3))
    plt.step(times, vals, where="post")
    plt.yticks([0, 1], ["On Water", "In Shed"]) 
    plt.xlabel("Time (s, relative)")
    plt.ylabel("Observed")
    plt.title("Observed Location Over Time")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(png_path, dpi=150)
    plt.close()


def run_interactive(args: argparse.Namespace) -> None:
    out_dir = ensure_out_dir(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.realpath(out_dir)
    csv_path = os.path.join(out_dir, "results.csv")
    jsonl_path = os.path.join(out_dir, "presence_log.jsonl")
    png_path = os.path.join(out_dir, "status_over_time.png")

    print(f"Output directory: {out_dir}")
    write_csv_header(csv_path)

    total = 0
    passes = 0

    print("\nInstructions:")
    print("- Move the real beacon to create the intended location state.")
    print(f"- For each trial, you will enter the expected location (In Shed / On Water).")
    print(f"- The script will sample for {args.sample_seconds:.1f}s @ {args.sample_rate_hz:.1f} Hz and majority-vote the observed state.")
    print("- The result is logged to CSV and raw samples to JSONL; a plot is generated at the end.\n")

    for trial in range(1, args.trials + 1):
        exp = input(f"Trial {trial} expected (In Shed/On Water): ").strip()
        exp_norm = exp.lower().replace(" ", "")
        if exp_norm not in ("inshed", "onwater"):
            print("Please type exactly 'In Shed' or 'On Water'.")
            exp = input(f"Trial {trial} expected (In Shed/On Water): ").strip()
            exp_norm = exp.lower().replace(" ", "")

        print("Sampling...")
        ts_list, inh_list = poll_presence_series(
            args.server_url, args.boat_id, args.sample_seconds, args.sample_rate_hz, jsonl_path, trial
        )
        inh = majority_vote(inh_list)
        obs = observed_label(inh)

        total += 1
        passfail = "Pass" if ((exp_norm == "inshed" and inh) or (exp_norm == "onwater" and not inh)) else "Fail"
        if passfail == "Pass":
            passes += 1

        when = datetime.now().strftime("%H:%M:%S")
        dash = f"presence endpoint: {'entered' if inh else 'exited'}"
        append_csv_row(csv_path, [str(trial), exp, obs, dash, when, passfail, ""])
        print(f"Trial {trial}: expected={exp} observed={obs} => {passfail}")

    # Summary
    accuracy = (passes * 100.0 / total) if total else 0.0
    print("\nSummary:")
    print(f"  Total Trials: {total}")
    print(f"  Passes: {passes}")
    print(f"  Fails: {total - passes}")
    print(f"  Accuracy (%): {accuracy:.2f}")

    # Plot
    try:
        plot_status_over_time(jsonl_path, png_path)
        print(f"Plots written: {png_path}")
    except Exception as e:  # pragma: no cover
        print(f"Plotting failed: {e}")

    print(f"CSV: {csv_path}")
    print(f"Raw log: {jsonl_path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Physical T1 Test Runner (Location Detection)")
    p.add_argument("--boat-id", required=True, help="Boat ID to observe")
    p.add_argument("--server-url", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument("--trials", type=int, default=10, help="Number of trials to run")
    p.add_argument("--sample-seconds", type=float, default=5.0, help="Seconds to sample per trial")
    p.add_argument("--sample-rate-hz", type=float, default=2.0, help="Sample rate in Hz while polling")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_interactive(args)


if __name__ == "__main__":
    main()


