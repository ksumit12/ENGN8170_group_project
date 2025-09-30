#!/usr/bin/env python3
"""
Feature 2: noise/dropout robustness sweep.
Outputs plots + CSV into test_plan/results/f2/
"""
import os
import pandas as pd
import matplotlib.pyplot as plt
from common import ensure_dir, savefig, run_trial, Phase

OUT = ensure_dir("test_plan/results/f2")


def main():
    rows = []
    base = [Phase("INSIDE", 30, -60, -85, "idle")]
    for sigma in [0.5, 1, 2, 3, 4, 5]:
        for drop in [0.0, 0.1, 0.2, 0.3]:
            df, _ = run_trial(base, OUT, noise_sigma=sigma, dropout=drop, seed=42)
            false_events = int(((df.state == "OUTSIDE").astype(int).diff() == 1).sum())
            rows.append({"noise_sigma": sigma, "dropout": drop, "false_events": false_events})
    tab = pd.DataFrame(rows)
    plt.figure()
    for drop, g in tab.groupby("dropout"):
        plt.plot(g.noise_sigma, g.false_events, marker="o", label=f"dropout={drop}")
    plt.xlabel("Noise sigma (dB)"); plt.ylabel("False OUT transitions (30s idle)")
    plt.title("Noise/Dropout robustness"); plt.legend()
    savefig(os.path.join(OUT, "noise_vs_false_events.png"))
    tab.to_csv(os.path.join(OUT, "robustness.csv"), index=False)
    print("F2 robustness: results ->", OUT)


if __name__ == "__main__":
    main()




