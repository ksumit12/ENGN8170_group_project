#!/usr/bin/env python3
"""
Physical Test Runner: T2 Real-Time Update (R2)

Requirement
- The system shall provide real-time operational status updates within 5 seconds
  of a change in state (visible to users).

Method (physical)
- Operator initiates a real movement (e.g., take beacon out of shed or bring in).
- At the exact moment movement starts, operator hits Enter to mark t0.
- Script polls /api/v1/presence/<boat_id> at a fixed rate until the first state
  flip is observed; latency = t_detect - t0.
- Pass if latency <= 5.00 seconds.

Outputs (saved under test_plan/results/T2/<timestamp>/)
- results.csv                # Trial table with latency and pass/fail
- presence_log.jsonl         # Raw samples (timestamped) for each trial
- latency_hist.png           # Histogram of measured latencies
- timeline_trial_<n>.png     # Optional per-trial step plot of observed state vs time

Usage
  python3 test_plan/physical_T2.py --boat-id BOAT123 [--server-url http://127.0.0.1:8000] \
      [--trials 10] [--max-wait-seconds 30] [--sample-rate-hz 5]

Dependencies
- Python packages: requests, matplotlib
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


LATENCY_SLA = 5.0  # seconds


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_out_dir(base_dir: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(base_dir, "results", "T2", ts)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def presence_snapshot(server_url: str, boat_id: str) -> Dict[str, Any]:
    r = requests.get(f"{server_url}/api/v1/presence/{boat_id}", timeout=3)
    r.raise_for_status()
    return r.json()


def observed_label(in_harbor: bool) -> str:
    return "In Shed" if in_harbor else "On Water"


def write_csv_header(csv_path: str) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Trial",
            "Expected",
            "Observed",
            "LatencySeconds",
            "DashboardOrLog",
            "Time",
            "PassFail",
            "Comments",
        ])


def append_csv_row(csv_path: str, row: List[str]) -> None:
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def plot_latency_hist(latencies: List[float], png_path: str) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:  # pragma: no cover
        print("Skipping histogram (matplotlib not installed)")
        return
    if not latencies:
        return
    
    # Create comprehensive latency analysis plot
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
    
    # Plot 1: Latency histogram with SLA line
    bins = min(15, max(5, len(latencies)//2))
    n, bins, patches = ax1.hist(latencies, bins=bins, color="#4c78a8", edgecolor="#333", alpha=0.7)
    
    # Color bars based on SLA compliance
    for i, patch in enumerate(patches):
        if bins[i] <= LATENCY_SLA:
            patch.set_facecolor('#2ca02c')  # Green for compliant
        else:
            patch.set_facecolor('#d62728')  # Red for non-compliant
    
    ax1.axvline(LATENCY_SLA, color="red", linestyle="--", linewidth=2, label=f"SLA {LATENCY_SLA:.1f}s")
    ax1.set_xlabel("Latency (s)")
    ax1.set_ylabel("Count")
    ax1.set_title("T2 Real-Time Update Latency Distribution")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Latency over time (trial sequence)
    trial_nums = list(range(1, len(latencies) + 1))
    colors = ['green' if l <= LATENCY_SLA else 'red' for l in latencies]
    ax2.scatter(trial_nums, latencies, c=colors, s=100, alpha=0.7, edgecolors='black')
    ax2.axhline(LATENCY_SLA, color="red", linestyle="--", linewidth=2, label=f"SLA {LATENCY_SLA:.1f}s")
    ax2.set_xlabel("Trial Number")
    ax2.set_ylabel("Latency (s)")
    ax2.set_title("Latency by Trial Sequence")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Add trial numbers as annotations
    for i, (trial, lat) in enumerate(zip(trial_nums, latencies)):
        ax2.annotate(f'T{trial}', (trial, lat), xytext=(0, 10), textcoords='offset points',
                    ha='center', va='bottom', fontsize=8)
    
    # Plot 3: SLA compliance pie chart
    compliant = sum(1 for l in latencies if l <= LATENCY_SLA)
    non_compliant = len(latencies) - compliant
    labels = ['Compliant', 'Non-Compliant']
    sizes = [compliant, non_compliant]
    colors_pie = ['#2ca02c', '#d62728']
    
    if sizes[0] > 0 or sizes[1] > 0:
        wedges, texts, autotexts = ax3.pie(sizes, labels=labels, colors=colors_pie, autopct='%1.1f%%', 
                                          startangle=90, textprops={'fontsize': 10})
        ax3.set_title(f"SLA Compliance\n({compliant}/{len(latencies)} trials)")
    
    # Plot 4: Statistical summary
    if latencies:
        stats_text = f"""Latency Statistics:
        
Mean: {np.mean(latencies):.2f}s
Median: {np.median(latencies):.2f}s
Min: {np.min(latencies):.2f}s
Max: {np.max(latencies):.2f}s
Std Dev: {np.std(latencies):.2f}s

SLA Compliance:
{compliant}/{len(latencies)} trials ({compliant/len(latencies)*100:.1f}%)

95th Percentile: {np.percentile(latencies, 95):.2f}s"""
        
        ax4.text(0.1, 0.9, stats_text, transform=ax4.transAxes, fontsize=10,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray", alpha=0.8))
        ax4.set_xlim(0, 1)
        ax4.set_ylim(0, 1)
        ax4.axis('off')
        ax4.set_title("Performance Summary")
    
    plt.tight_layout()
    plt.savefig(png_path, dpi=150, bbox_inches='tight')
    plt.close()


def plot_timeline(times: List[float], vals: List[int], png_path: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover
        return
    if not times:
        return
    plt.figure(figsize=(8, 2.6))
    plt.step(times, vals, where="post")
    plt.yticks([0, 1], ["On Water", "In Shed"]) 
    plt.xlabel("Time (s, relative to t0)")
    plt.ylabel("Observed")
    plt.title("Observed Location Over Time (trial)")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(png_path, dpi=140)
    plt.close()


def poll_until_flip(server_url: str, boat_id: str, baseline_in_harbor: bool,
                    jsonl_path: str, trial_no: int, sample_rate_hz: float,
                    max_wait_seconds: float) -> Tuple[float, List[float], List[int]]:
    interval = 1.0 / max(sample_rate_hz, 0.1)
    t0 = time.time()
    deadline = t0 + max(max_wait_seconds, 0.1)
    flipped_at: float = None  # type: ignore
    times: List[float] = []
    vals: List[int] = []

    with open(jsonl_path, "a", encoding="utf-8") as f:
        while True:
            now = time.time()
            if now > deadline:
                break
            try:
                data = presence_snapshot(server_url, boat_id)
                inh = bool(data.get("in_harbor", False))
                rec = {
                    "ts": iso_now(),
                    "trial": trial_no,
                    "since_t0_s": now - t0,
                    "in_harbor": inh,
                    "status": data.get("status"),
                    "last_seen": data.get("last_seen"),
                    "last_rssi": data.get("last_rssi"),
                }
                f.write(json.dumps(rec) + "\n")
                times.append(now - t0)
                vals.append(1 if inh else 0)
                if flipped_at is None and inh != baseline_in_harbor:
                    flipped_at = now
                    break
            except Exception as e:  # pragma: no cover
                rec = {"ts": iso_now(), "trial": trial_no, "error": str(e)}
                f.write(json.dumps(rec) + "\n")
            time.sleep(interval)

    if flipped_at is None:
        return float("inf"), times, vals
    return flipped_at - t0, times, vals


def run_interactive(args: argparse.Namespace) -> None:
    out_dir = ensure_out_dir(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.realpath(out_dir)
    csv_path = os.path.join(out_dir, "results.csv")
    jsonl_path = os.path.join(out_dir, "presence_log.jsonl")
    hist_png = os.path.join(out_dir, "latency_hist.png")

    print(f"Output directory: {out_dir}")
    write_csv_header(csv_path)

    latencies: List[float] = []
    total = 0
    passes = 0

    print("\nInstructions:")
    print("- For each trial, position the beacon ready to change state (e.g. at gate).")
    print("- The script reads the current dashboard state as baseline.")
    print("- When you START the movement, press Enter to mark t0. The script will poll the API and measure latency to the first state flip.")
    print(f"- PASS if latency <= {LATENCY_SLA:.2f}s.\n")

    for trial in range(1, args.trials + 1):
        # Read baseline
        try:
            base = presence_snapshot(args.server_url, args.boat_id)
        except Exception as e:
            print(f"Failed to query presence: {e}")
            return
        baseline_inh = bool(base.get("in_harbor", False))
        baseline_label = observed_label(baseline_inh)
        print(f"Baseline: {baseline_label} (status={base.get('status')})")

        exp = input(f"Trial {trial} expected after change (In Shed/On Water): ").strip()
        exp_norm = exp.lower().replace(" ", "")
        if exp_norm not in ("inshed", "onwater"):
            print("Please type exactly 'In Shed' or 'On Water'.")
            exp = input(f"Trial {trial} expected after change (In Shed/On Water): ").strip()
            exp_norm = exp.lower().replace(" ", "")

        input("Press Enter AT THE MOMENT you START the movement (t0)...")

        latency, times, vals = poll_until_flip(
            args.server_url, args.boat_id, baseline_inh, jsonl_path, trial, args.sample_rate_hz, args.max_wait_seconds
        )
        total += 1
        if latency == float("inf"):
            obs_label = observed_label(baseline_inh)  # no flip observed
            passfail = "Fail"
            latency_str = "timeout"
        else:
            obs_label = observed_label(not baseline_inh)
            passfail = "Pass" if latency <= LATENCY_SLA else "Fail"
            latency_str = f"{latency:.2f}"
            latencies.append(latency)

        when = datetime.now().strftime("%H:%M:%S")
        dash = f"presence endpoint: {('entered' if (not baseline_inh) else 'exited')} (flip)"
        append_csv_row(csv_path, [str(trial), exp, obs_label, latency_str, dash, when, passfail, ""])
        print(f"Trial {trial}: expected={exp} observed={obs_label} latency={latency_str}s => {passfail}")

        # Timeline per trial
        try:
            tl_png = os.path.join(out_dir, f"timeline_trial_{trial}.png")
            plot_timeline(times, vals, tl_png)
        except Exception:
            pass

    # Summary
    num_pass = sum(1 for _l in latencies if _l <= LATENCY_SLA)
    # Include timeouts as fails
    fails = total - num_pass
    accuracy = (num_pass * 100.0 / total) if total else 0.0
    print("\nSummary:")
    print(f"  Total Trials: {total}")
    print(f"  Passes: {num_pass}")
    print(f"  Fails: {fails}")
    print(f"  Accuracy (%): {accuracy:.2f}")

    try:
        plot_latency_hist(latencies, hist_png)
        print(f"Latency histogram: {hist_png}")
    except Exception as e:  # pragma: no cover
        print(f"Histogram failed: {e}")

    print(f"CSV: {csv_path}")
    print(f"Raw log: {jsonl_path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Physical T2 Real-Time Update Test Runner")
    p.add_argument("--boat-id", required=True, help="Boat ID to observe")
    p.add_argument("--server-url", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument("--trials", type=int, default=10, help="Number of trials to run")
    p.add_argument("--max-wait-seconds", type=float, default=30.0, help="Max seconds to wait for state flip")
    p.add_argument("--sample-rate-hz", type=float, default=5.0, help="Polling rate while waiting for flip")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_interactive(args)


if __name__ == "__main__":
    main()


