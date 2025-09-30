#!/usr/bin/env python3
"""
Feature 1: IN/OUT correctness with confusion matrix and latency.
Outputs into test_plan/results/f1/
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from common import ensure_dir, savefig, run_trial, default_phases

OUT = ensure_dir("test_plan/results/f1")


def first_cross(series, df):
    idx = np.where(series.values[1:] - series.values[:-1] == 1)[0]
    return df.t.values[idx[0] + 1] if len(idx) > 0 else None


def main():
    df, fsm = run_trial(default_phases(), OUT, noise_sigma=2.0, dropout=0.05, dt=0.2, seed=42)

    gt_out = (df["gt"] == "OUTSIDE").astype(int)
    pred_out = (df.state == "OUTSIDE").astype(int)

    TP = int(((pred_out == 1) & (gt_out == 1)).sum())
    TN = int(((pred_out == 0) & (gt_out == 0)).sum())
    FP = int(((pred_out == 1) & (gt_out == 0)).sum())
    FN = int(((pred_out == 0) & (gt_out == 1)).sum())

    cm = np.array([[TP, FP], [FN, TN]])
    fig, ax = plt.subplots()
    im = ax.imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, str(v), ha="center", va="center")
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["OUT", "IN"]) ; ax.set_yticklabels(["OUT", "IN"]) 
    ax.set_title("Confusion Matrix (OUT vs not OUT)")
    savefig(os.path.join(OUT, "confusion_matrix.png"))

    gt_cross_out = first_cross(gt_out, df)
    pd_cross_out = first_cross(pred_out, df)
    lat_out = None if (gt_cross_out is None or pd_cross_out is None) else (pd_cross_out - gt_cross_out)

    gt_in = (df["gt"] == "INSIDE").astype(int)
    pred_in = (df.state == "INSIDE").astype(int)
    lat_in = None
    try:
        lat_in = first_cross(pred_in, df) - first_cross(gt_in, df)
    except Exception:
        pass

    pd.DataFrame([{"TP": TP, "FP": FP, "FN": FN, "TN": TN, "latency_out_s": lat_out, "latency_in_s": lat_in}]).to_csv(
        os.path.join(OUT, "metrics_summary.csv"), index=False
    )
    print("F1 correctness: results ->", OUT)


if __name__ == "__main__":
    main()


