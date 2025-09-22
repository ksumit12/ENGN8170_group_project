#!/usr/bin/env python3
"""
Feature 3: DB/update integrity (simulated pipeline delay distribution).
Outputs into test_plan/results/f3/
"""
import os, random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from common import ensure_dir, savefig, run_trial, default_phases

OUT = ensure_dir("test_plan/results/f3")


def main():
    df, _ = run_trial(default_phases(), OUT, noise_sigma=2.0, dropout=0.05)
    rng = random.Random(7)
    events = (df.state.shift(1) != df.state).fillna(False)
    times = df.t[events].values
    sim_lat = []
    for t in times:
        pipe_delay = rng.gauss(0.12, 0.04)
        sim_lat.append(max(0, pipe_delay))
    if sim_lat:
        plt.hist(sim_lat, bins=15)
        plt.xlabel("Simulated DB/UI latency (s)")
        plt.ylabel("Events")
        plt.title("Update latency distribution (simulated)")
        savefig(os.path.join(OUT, "db_latency_hist.png"))
    pd.DataFrame({"latency_s": sim_lat}).to_csv(os.path.join(OUT, "db_latency.csv"), index=False)
    print("F3 integrity: results ->", OUT)


if __name__ == "__main__":
    main()


