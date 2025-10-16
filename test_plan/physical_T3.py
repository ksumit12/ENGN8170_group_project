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
    except Exception:  # pragma: no cover
        return
    if not values:
        return
    plt.figure(figsize=(6, 3))
    plt.hist(values, bins=min(10, max(3, len(values)//2)), color="#72b7b2", edgecolor="#333")
    plt.axvline(SLA_SECONDS, color="red", linestyle="--", label=f"SLA {SLA_SECONDS:.1f}s")
    plt.xlabel("Absolute Delta (s)")
    plt.ylabel("Count")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(png_path, dpi=150)
    plt.close()


def plot_timeline(times: List[float], vals: List[int], t_user_mark: float, t_sys_flip_rel: float,
                  png_path: str, title: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover
        return
    if not times:
        return
    plt.figure(figsize=(8, 2.6))
    plt.step(times, vals, where="post")
    plt.yticks([0, 1], ["On Water", "In Shed"]) 
    plt.xlabel("Time (s, relative to user mark)")
    plt.ylabel("Observed")
    plt.title(title)
    # user mark at 0
    plt.axvline(0.0, color="#444", linestyle=":", label="User Mark")
    # system flip at t_sys_flip_rel
    plt.axvline(t_sys_flip_rel, color="#e45756", linestyle="--", label="System Flip")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(png_path, dpi=140)
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
        print("Saved delta histograms.")
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


