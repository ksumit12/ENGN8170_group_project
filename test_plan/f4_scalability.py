#!/usr/bin/env python3
"""
Feature 4: Scalability under concurrency (accuracy & throughput).
Outputs into test_plan/results/f4/
"""
import os, random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from common import ensure_dir, savefig, run_trial, default_phases

OUT = ensure_dir("test_plan/results/f4")


def main():
    rng = random.Random(3)
    N = [1, 3, 5, 10, 15]
    acc_rows = []
    thr_rows = []
    for n in N:
        dt = 0.2; T = 60
        all_rows = []
        for b in range(n):
            shift = rng.uniform(0, 10)
            df, _ = run_trial(default_phases(), OUT, noise_sigma=2.0, dropout=0.1, dt=dt, seed=b + 10)
            df["t"] = df["t"] + shift
            df["beacon"] = f"B{b + 1}"
            all_rows.append(df)
        big = pd.concat(all_rows).sort_values("t")
        ev = (big.groupby("beacon").state.apply(lambda s: (s.shift(1) != s).sum()).sum()) / T
        thr_rows.append({"boats": n, "events_per_sec": ev})
        acc = []
        for b, g in big.groupby("beacon"):
            Gt = (g["gt"] == "OUTSIDE").astype(int).values
            Pd = (g.state == "OUTSIDE").astype(int).values
            inter = int(((Gt == 1) & (Pd == 1)).sum())
            union = int(((Gt == 1) | (Pd == 1)).sum())
            jac = inter / union if union > 0 else 1.0
            acc.append(jac)
        acc_rows.append({"boats": n, "mean_jaccard": float(np.mean(acc))})
    accdf = pd.DataFrame(acc_rows); thrdf = pd.DataFrame(thr_rows)
    plt.plot(accdf.boats, accdf.mean_jaccard, marker='o'); plt.ylim(0,1)
    plt.xlabel("# Boats concurrently"); plt.ylabel("Mean Jaccard (OUTSIDE mask)")
    plt.title("Accuracy vs concurrency")
    savefig(os.path.join(OUT, "concurrency_accuracy.png"))

    plt.plot(thrdf.boats, thrdf.events_per_sec, marker='o')
    plt.xlabel("# Boats concurrently"); plt.ylabel("Events / second")
    plt.title("Throughput vs concurrency")
    savefig(os.path.join(OUT, "throughput_events_per_sec.png"))

    accdf.to_csv(os.path.join(OUT, "concurrency_accuracy.csv"), index=False)
    thrdf.to_csv(os.path.join(OUT, "throughput.csv"), index=False)
    print("F4 scalability: results ->", OUT)


if __name__ == "__main__":
    main()


