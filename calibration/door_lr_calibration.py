#!/usr/bin/env python3
"""
Door L/R Calibration Tool (skeleton): guides operator through 4 passes and
computes lag sign majority for mapping.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='system/json/scanner_config.door_left_right.json')
    ap.add_argument('--samples', type=int, default=800)
    ap.add_argument('--max-lag', type=float, default=0.6)
    ap.add_argument('--out', default='calibration/door_lr_calib.json')
    args = ap.parse_args()

    # TODO: subscribe to scan stream, collect 4 passes, compute tau* per pass
    # For now, write a placeholder file
    result = {
        "lag_positive": "LEAVE",
        "lag_negative": "ENTER",
        "min_confidence_tau_s": 0.12,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    with open(args.out, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Calibration stub written to {args.out}")


if __name__ == '__main__':
    main()


