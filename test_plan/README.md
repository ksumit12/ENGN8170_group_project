Test Plan
=========

This suite benchmarks the four core features end-to-end using realistic synthetic data and
produces plots and CSVs under `test_plan/results/<feature>/`.

Scripts
-------
- f1_correctness.py: IN/OUT correctness (confusion matrix, latency)
- f2_robustness.py: noise/dropout robustness sweep
- f3_integrity.py: pipeline latency (simulated DB/UI delay)
- f4_scalability.py: concurrency accuracy and throughput

Common utilities live in `test_plan/common.py` and include RSSI generators, filters and a
reference FSM you can swap with the production FSM.

Usage
-----
1) pip install -r requirements.txt (plus: numpy pandas matplotlib scipy)
2) Run any script:
   - python3 test_plan/f1_correctness.py
   - python3 test_plan/f2_robustness.py
   - python3 test_plan/f3_integrity.py
   - python3 test_plan/f4_scalability.py

Outputs
-------
- results/f1: confusion_matrix.png, metrics_summary.csv
- results/f2: noise_vs_false_events.png, robustness.csv
- results/f3: db_latency_hist.png, db_latency.csv
- results/f4: concurrency_accuracy.png, throughput_events_per_sec.png, CSVs







