#!/usr/bin/env python3
"""
Physical Test Runner: T3 Timestamp Accuracy (R3)

Requirement
- The system shall log boat usage data (entry time, exit time, total duration)
  with timestamps accurate to within one second.

Method (physical)
- Operator triggers two keypress markers per outing: exit moment and entry moment.
- Script polls /api/v1/presence/<boat_id> to detect the corresponding state flips:
  - Exit flip: in_harbor goes True -> False
  - Entry flip: in_harbor goes False -> True
- Measure differences between operator-marked times and detected flip times.
- Compute total duration differences as well.

Outputs (saved under test_plan/results/T3/<timestamp>/)
- results.csv                 # Per-trial with deltas and pass/fail
- presence_log.jsonl          # Raw samples during both phases
- delta_hist_entry.png        # Histogram of |entry delta|
- delta_hist_exit.png         # Histogram of |exit delta|
- duration_delta_hist.png     # Histogram of |duration delta|
- timeline_trial_<n>.png      # Per-trial timeline with user marks and flips

Usage
  python3 test_plan/physical_T3.py --boat-id BOAT123 [--server-url http://127.0.0.1:8000] 
      [--trials 10] [--sample-rate-hz 5] [--max-wait-seconds 90]

Assumptions
- Typical sequence per trial: Exit (leave shed) then Entry (return to shed).
- If your starting baseline is On Water, the script will guide you to perform
  Entry first, then Exit, and compute the same deltas accordingly.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

try:
    import requests
except Exception as e:  # pragma: no cover
    print("ERROR: requests is required. Try: pip install requests", file=sys.stderr)
    raise


SLA_SECONDS = 1.0


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_out_dir(base_dir: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(base_dir, "results", "T3", ts)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def presence_snapshot(server_url: str, boat_id: str) -> Dict[str, Any]:
    r = requests.get(f"{server_url}/api/v1/presence/{boat_id}", timeout=3)
    r.raise_for_status()
    return r.json()


def observed_label(in_harbor: bool) -> str:
    return "In Shed" if in_harbor else "On Water"


def wait_for_flip(server_url: str, boat_id: str, baseline: bool, sample_rate_hz: float,
                  max_wait_seconds: float, logf) -> Tuple[float, List[float], List[int]]:
    interval = 1.0 / max(sample_rate_hz, 0.1)
    t0 = time.time()
    deadline = t0 + max(max_wait_seconds, 0.1)
    times: List[float] = []
    vals: List[int] = []

    while True:
        now = time.time()
        if now > deadline:
            return float("inf"), times, vals
        try:
            data = presence_snapshot(server_url, boat_id)
            inh = bool(data.get("in_harbor", False))
            rec = {
                "ts": iso_now(),
                "since_t0_s": now - t0,
                "in_harbor": inh,
                "status": data.get("status"),
                "last_seen": data.get("last_seen"),
                "last_rssi": data.get("last_rssi"),
            }
            logf.write(json.dumps(rec) + "\n")
            times.append(now - t0)
            vals.append(1 if inh else 0)
            if inh != baseline:
                return now, times, vals
        except Exception as e:  # pragma: no cover
            rec = {"ts": iso_now(), "error": str(e)}
            logf.write(json.dumps(rec) + "\n")
        time.sleep(interval)


def hist(values: List[float], png_path: str, title: str) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:  # pragma: no cover
        return
    if not values:
        return
    
    # Create comprehensive histogram with statistics
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Plot 1: Histogram with SLA line
    bins = min(15, max(5, len(values)//2))
    n, bins, patches = ax1.hist(values, bins=bins, color="#72b7b2", edgecolor="#333", alpha=0.7)
    
    # Color bars based on SLA compliance
    for i, patch in enumerate(patches):
        if bins[i] <= SLA_SECONDS:
            patch.set_facecolor('#2ca02c')  # Green for compliant
        else:
            patch.set_facecolor('#d62728')  # Red for non-compliant
    
    ax1.axvline(SLA_SECONDS, color="red", linestyle="--", linewidth=2, label=f"SLA {SLA_SECONDS:.1f}s")
    ax1.set_xlabel("Absolute Delta (s)")
    ax1.set_ylabel("Count")
    ax1.set_title(title)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Statistical summary
    compliant = sum(1 for v in values if v <= SLA_SECONDS)
    stats_text = f"""Timestamp Accuracy Statistics:

Mean: {np.mean(values):.3f}s
Median: {np.median(values):.3f}s
Min: {np.min(values):.3f}s
Max: {np.max(values):.3f}s
Std Dev: {np.std(values):.3f}s

SLA Compliance:
{compliant}/{len(values)} trials ({compliant/len(values)*100:.1f}%)

95th Percentile: {np.percentile(values, 95):.3f}s
99th Percentile: {np.percentile(values, 99):.3f}s

Distribution:
- Within 0.1s: {sum(1 for v in values if v <= 0.1)} trials
- Within 0.5s: {sum(1 for v in values if v <= 0.5)} trials
- Within 1.0s: {compliant} trials"""
    
    ax2.text(0.05, 0.95, stats_text, transform=ax2.transAxes, fontsize=9,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue", alpha=0.8))
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis('off')
    ax2.set_title("Performance Summary")
    
    plt.tight_layout()
    plt.savefig(png_path, dpi=150, bbox_inches='tight')
    plt.close()


def plot_timeline(times: List[float], vals: List[int], t_user_mark: float, t_sys_flip_rel: float,
                  png_path: str, title: str) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:  # pragma: no cover
        return
    if not times:
        return
    
    # Create enhanced timeline plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    
    # Plot 1: Timeline with user mark and system flip
    ax1.step(times, vals, where="post", linewidth=2, color='#1f77b4')
    ax1.set_yticks([0, 1])
    ax1.set_yticklabels(["On Water", "In Shed"]) 
    ax1.set_xlabel("Time (s, relative to user mark)")
    ax1.set_ylabel("Observed Status")
    ax1.set_title(f"{title} - Timeline")
    
    # User mark at 0
    ax1.axvline(0.0, color="#444", linestyle=":", linewidth=2, label="User Mark")
    # System flip at t_sys_flip_rel
    ax1.axvline(t_sys_flip_rel, color="#e45756", linestyle="--", linewidth=2, label="System Flip")
    
    # Add delta annotation
    delta_text = f"Δ = {abs(t_sys_flip_rel):.3f}s"
    ax1.annotate(delta_text, xy=(t_sys_flip_rel, 0.5), xytext=(t_sys_flip_rel + 0.5, 0.7),
                arrowprops=dict(arrowstyle='->', color='red', alpha=0.7),
                fontsize=10, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))
    
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Plot 2: Delta analysis
    delta = abs(t_sys_flip_rel)
    sla_compliant = delta <= SLA_SECONDS
    
    # Create a simple bar chart showing delta vs SLA
    categories = ['Measured Δ', 'SLA Limit']
    values = [delta, SLA_SECONDS]
    colors = ['green' if sla_compliant else 'red', 'red']
    
    bars = ax2.bar(categories, values, color=colors, alpha=0.7, edgecolor='black')
    ax2.set_ylabel("Time (s)")
    ax2.set_title(f"Delta Analysis - {'PASS' if sla_compliant else 'FAIL'}")
    ax2.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                f'{value:.3f}s', ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(png_path, dpi=140, bbox_inches='tight')
    plt.close()


def create_comprehensive_summary(abs_deltas_exit: List[float], abs_deltas_entry: List[float], 
                                abs_deltas_duration: List[float], out_dir: str) -> None:
    """Create a comprehensive summary plot for T3 test results"""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception:  # pragma: no cover
        return
    
    fig = plt.figure(figsize=(16, 12))
    
    # Create a grid layout
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
    
    # Plot 1: Exit Delta Histogram
    ax1 = fig.add_subplot(gs[0, 0])
    if abs_deltas_exit:
        bins = min(10, max(3, len(abs_deltas_exit)//2))
        n, bins, patches = ax1.hist(abs_deltas_exit, bins=bins, color="#ff7f0e", alpha=0.7, edgecolor='black')
        for i, patch in enumerate(patches):
            if bins[i] <= SLA_SECONDS:
                patch.set_facecolor('#2ca02c')
            else:
                patch.set_facecolor('#d62728')
        ax1.axvline(SLA_SECONDS, color="red", linestyle="--", linewidth=2)
        ax1.set_title("Exit Delta Distribution")
        ax1.set_xlabel("Delta (s)")
        ax1.set_ylabel("Count")
        ax1.grid(True, alpha=0.3)
    
    # Plot 2: Entry Delta Histogram
    ax2 = fig.add_subplot(gs[0, 1])
    if abs_deltas_entry:
        bins = min(10, max(3, len(abs_deltas_entry)//2))
        n, bins, patches = ax2.hist(abs_deltas_entry, bins=bins, color="#2ca02c", alpha=0.7, edgecolor='black')
        for i, patch in enumerate(patches):
            if bins[i] <= SLA_SECONDS:
                patch.set_facecolor('#2ca02c')
            else:
                patch.set_facecolor('#d62728')
        ax2.axvline(SLA_SECONDS, color="red", linestyle="--", linewidth=2)
        ax2.set_title("Entry Delta Distribution")
        ax2.set_xlabel("Delta (s)")
        ax2.set_ylabel("Count")
        ax2.grid(True, alpha=0.3)
    
    # Plot 3: Duration Delta Histogram
    ax3 = fig.add_subplot(gs[0, 2])
    if abs_deltas_duration:
        bins = min(10, max(3, len(abs_deltas_duration)//2))
        n, bins, patches = ax3.hist(abs_deltas_duration, bins=bins, color="#d62728", alpha=0.7, edgecolor='black')
        ax3.set_title("Duration Delta Distribution")
        ax3.set_xlabel("Delta (s)")
        ax3.set_ylabel("Count")
        ax3.grid(True, alpha=0.3)
    
    # Plot 4: Trial-by-trial comparison
    ax4 = fig.add_subplot(gs[1, :])
    trials = list(range(1, max(len(abs_deltas_exit), len(abs_deltas_entry)) + 1))
    
    x = np.arange(len(trials))
    width = 0.25
    
    if abs_deltas_exit:
        bars1 = ax4.bar(x - width, abs_deltas_exit, width, label='Exit Δ', color='#ff7f0e', alpha=0.7)
    if abs_deltas_entry:
        bars2 = ax4.bar(x, abs_deltas_entry, width, label='Entry Δ', color='#2ca02c', alpha=0.7)
    
    ax4.axhline(SLA_SECONDS, color="red", linestyle="--", linewidth=2, label=f"SLA {SLA_SECONDS:.1f}s")
    ax4.set_xlabel("Trial Number")
    ax4.set_ylabel("Delta (s)")
    ax4.set_title("Trial-by-Trial Delta Comparison")
    ax4.set_xticks(x)
    ax4.set_xticklabels([f'T{t}' for t in trials])
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    # Plot 5: Overall statistics
    ax5 = fig.add_subplot(gs[2, :])
    ax5.axis('off')
    
    # Calculate statistics
    stats_text = "T3 Timestamp Accuracy Test - Comprehensive Summary\n" + "="*60 + "\n\n"
    
    if abs_deltas_exit:
        exit_compliant = sum(1 for d in abs_deltas_exit if d <= SLA_SECONDS)
        stats_text += f"EXIT DELTAS:\n"
        stats_text += f"  Mean: {np.mean(abs_deltas_exit):.3f}s, Median: {np.median(abs_deltas_exit):.3f}s\n"
        stats_text += f"  Min: {np.min(abs_deltas_exit):.3f}s, Max: {np.max(abs_deltas_exit):.3f}s\n"
        stats_text += f"  SLA Compliance: {exit_compliant}/{len(abs_deltas_exit)} ({exit_compliant/len(abs_deltas_exit)*100:.1f}%)\n\n"
    
    if abs_deltas_entry:
        entry_compliant = sum(1 for d in abs_deltas_entry if d <= SLA_SECONDS)
        stats_text += f"ENTRY DELTAS:\n"
        stats_text += f"  Mean: {np.mean(abs_deltas_entry):.3f}s, Median: {np.median(abs_deltas_entry):.3f}s\n"
        stats_text += f"  Min: {np.min(abs_deltas_entry):.3f}s, Max: {np.max(abs_deltas_entry):.3f}s\n"
        stats_text += f"  SLA Compliance: {entry_compliant}/{len(abs_deltas_entry)} ({entry_compliant/len(abs_deltas_entry)*100:.1f}%)\n\n"
    
    if abs_deltas_duration:
        stats_text += f"DURATION DELTAS:\n"
        stats_text += f"  Mean: {np.mean(abs_deltas_duration):.3f}s, Median: {np.median(abs_deltas_duration):.3f}s\n"
        stats_text += f"  Min: {np.min(abs_deltas_duration):.3f}s, Max: {np.max(abs_deltas_duration):.3f}s\n\n"
    
    # Overall pass/fail
    total_trials = max(len(abs_deltas_exit), len(abs_deltas_entry))
    if total_trials > 0:
        exit_passes = sum(1 for d in abs_deltas_exit if d <= SLA_SECONDS) if abs_deltas_exit else 0
        entry_passes = sum(1 for d in abs_deltas_entry if d <= SLA_SECONDS) if abs_deltas_entry else 0
        overall_passes = min(exit_passes, entry_passes) if abs_deltas_exit and abs_deltas_entry else max(exit_passes, entry_passes)
        
        stats_text += f"OVERALL RESULT:\n"
        stats_text += f"  Total Trials: {total_trials}\n"
        stats_text += f"  Passes: {overall_passes}\n"
        stats_text += f"  Fails: {total_trials - overall_passes}\n"
        stats_text += f"  Accuracy: {overall_passes/total_trials*100:.1f}%\n"
        stats_text += f"  Status: {'PASS' if overall_passes/total_trials >= 0.95 else 'FAIL'}"
    
    ax5.text(0.05, 0.95, stats_text, transform=ax5.transAxes, fontsize=11,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.8))
    
    plt.suptitle("T3 Timestamp Accuracy Test - Comprehensive Analysis", fontsize=16, fontweight='bold')
    plt.savefig(os.path.join(out_dir, "comprehensive_summary.png"), dpi=150, bbox_inches='tight')
    plt.close()


def write_csv_header(csv_path: str) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "Trial",
            "ExpectedSequence",
            "UserExitTS",
            "SysExitTS",
            "ExitDeltaS",
            "UserEntryTS",
            "SysEntryTS",
            "EntryDeltaS",
            "UserDurationS",
            "SysDurationS",
            "DurationDeltaS",
            "DashboardOrLog",
            "Time",
            "PassFail",
            "Comments",
        ])


def append_csv(csv_path: str, row: List[str]) -> None:
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(row)


def run_interactive(args: argparse.Namespace) -> None:
    out_dir = ensure_out_dir(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.realpath(out_dir)
    csv_path = os.path.join(out_dir, "results.csv")
    jsonl_path = os.path.join(out_dir, "presence_log.jsonl")
    print(f"Output directory: {out_dir}")
    write_csv_header(csv_path)

    abs_deltas_entry: List[float] = []
    abs_deltas_exit: List[float] = []
    abs_deltas_duration: List[float] = []
    total = 0
    passes = 0

    print("\nInstructions:")
    print("- Each trial is an outing with two marks: Exit moment and Entry moment.")
    print("- At the exact physical moment you cross the gate (exit), press Enter.")
    print("- Later, when returning (entry), press Enter again at the gate.")
    print("- The script measures the difference between your mark and the first system-observed flip.")
    print(f"- PASS if both |ExitDeltaS| and |EntryDeltaS| <= {SLA_SECONDS:.2f}s. Duration delta is reported.\n")

    for trial in range(1, args.trials + 1):
        # Read baseline
        base = presence_snapshot(args.server_url, args.boat_id)
        baseline_inh = bool(base.get("in_harbor", False))
        baseline_label = observed_label(baseline_inh)
        print(f"Baseline: {baseline_label} (status={base.get('status')})")

        seq = "Exit-then-Entry" if baseline_inh else "Entry-then-Exit"
        print(f"Sequence this trial: {seq}")

        # Exit phase (flip away from baseline)
        with open(jsonl_path, "a", encoding="utf-8") as logf:
            input("Press Enter AT THE EXIT MOMENT (leaving/arriving to cause first flip)...")
            t_user_exit = time.time()
            t_sys_exit, times_exit, vals_exit = wait_for_flip(
                args.server_url, args.boat_id, baseline_inh, args.sample_rate_hz, args.max_wait_seconds, logf
            )

        if t_sys_exit == float("inf"):
            # No flip observed; record timeout and continue
            when = datetime.now().strftime("%H:%M:%S")
            append_csv(csv_path, [str(trial), seq, f"{t_user_exit:.3f}", "timeout", "inf", "", "", "", "", "", "", "presence endpoint", when, "Fail", "No first flip observed"])
            print("No first flip observed within wait window -> Fail")
            total += 1
            continue

        exit_delta = abs(t_sys_exit - t_user_exit)
        abs_deltas_exit.append(exit_delta)

        # Entry phase (flip back to baseline)
        with open(jsonl_path, "a", encoding="utf-8") as logf:
            input("Press Enter AT THE ENTRY MOMENT (returning to cause second flip)...")
            t_user_entry = time.time()
            t_sys_entry, times_entry, vals_entry = wait_for_flip(
                args.server_url, args.boat_id, not baseline_inh, args.sample_rate_hz, args.max_wait_seconds, logf
            )

        if t_sys_entry == float("inf"):
            when = datetime.now().strftime("%H:%M:%S")
            append_csv(csv_path, [str(trial), seq, f"{t_user_exit:.3f}", f"{t_sys_exit:.3f}", f"{exit_delta:.2f}", f"{t_user_entry:.3f}", "timeout", "inf", "", "", "", "presence endpoint", when, "Fail", "No second flip observed"])
            print("No second flip observed within wait window -> Fail")
            total += 1
            continue

        entry_delta = abs(t_sys_entry - t_user_entry)
        abs_deltas_entry.append(entry_delta)

        user_duration = t_user_entry - t_user_exit
        sys_duration = t_sys_entry - t_sys_exit
        duration_delta = abs(sys_duration - user_duration)
        abs_deltas_duration.append(duration_delta)

        passfail = "Pass" if (exit_delta <= SLA_SECONDS and entry_delta <= SLA_SECONDS) else "Fail"
        total += 1
        if passfail == "Pass":
            passes += 1

        when = datetime.now().strftime("%H:%M:%S")
        append_csv(
            csv_path,
            [
                str(trial),
                seq,
                f"{t_user_exit:.3f}",
                f"{t_sys_exit:.3f}",
                f"{exit_delta:.2f}",
                f"{t_user_entry:.3f}",
                f"{t_sys_entry:.3f}",
                f"{entry_delta:.2f}",
                f"{user_duration:.2f}",
                f"{sys_duration:.2f}",
                f"{duration_delta:.2f}",
                "presence endpoint",
                when,
                passfail,
                "",
            ],
        )
        print(
            f"Trial {trial}: ExitΔ={exit_delta:.2f}s EntryΔ={entry_delta:.2f}s DurΔ={duration_delta:.2f}s => {passfail}"
        )

        # Plots per trial
        try:
            # For timeline, align user mark as t=0; system flip relative = t_sys - t_user
            import math
            rel_sys_exit = t_sys_exit - t_user_exit
            rel_sys_entry = t_sys_entry - t_user_entry
            # Reuse recorded series with approximate alignment: since_t0_s starts at first call in wait_for_flip
            # We won't recompute exact per-sample alignment to user mark; guiding visualization is enough
            timeline_exit_png = os.path.join(out_dir, f"timeline_trial_{trial}_exit.png")
            timeline_entry_png = os.path.join(out_dir, f"timeline_trial_{trial}_entry.png")
            plot_timeline(times_exit, vals_exit, 0.0, rel_sys_exit, timeline_exit_png, "Exit Phase")
            plot_timeline(times_entry, vals_entry, 0.0, rel_sys_entry, timeline_entry_png, "Entry Phase")
        except Exception:
            pass

    # Summary
    accuracy = (passes * 100.0 / total) if total else 0.0
    print("\nSummary:")
    print(f"  Total Trials: {total}")
    print(f"  Passes: {passes}")
    print(f"  Fails: {total - passes}")
    print(f"  Accuracy (%): {accuracy:.2f}")

    # Aggregate plots
    try:
        hist(abs_deltas_exit, os.path.join(out_dir, "delta_hist_exit.png"), "|Exit Timestamp Delta|")
        hist(abs_deltas_entry, os.path.join(out_dir, "delta_hist_entry.png"), "|Entry Timestamp Delta|")
        hist(abs_deltas_duration, os.path.join(out_dir, "duration_delta_hist.png"), "|Duration Delta|")
        create_comprehensive_summary(abs_deltas_exit, abs_deltas_entry, abs_deltas_duration, out_dir)
        print("Saved delta histograms and comprehensive summary.")
    except Exception as e:  # pragma: no cover
        print(f"Histogram generation failed: {e}")

    print(f"CSV: {csv_path}")
    print(f"Raw log: {jsonl_path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Physical T3 Timestamp Accuracy Test Runner")
    p.add_argument("--boat-id", required=True, help="Boat ID to observe")
    p.add_argument("--server-url", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument("--trials", type=int, default=10, help="Number of trials to run")
    p.add_argument("--sample-rate-hz", type=float, default=5.0, help="Polling rate while waiting for flips")
    p.add_argument("--max-wait-seconds", type=float, default=90.0, help="Max seconds to wait for each flip")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_interactive(args)


if __name__ == "__main__":
    main()


