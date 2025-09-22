#!/usr/bin/env python3
"""
Scanner Service: hardware-only daemon that runs BLE scanners per gate and posts
observations to the API. Keeps hardware concerns isolated from API/FSM.
"""

import argparse
import json
from typing import List, Dict

from ble_scanner import BLEScanner, ScannerConfig
from app.logging_config import get_logger

logger = get_logger()


def load_config(config_path: str) -> Dict:
    with open(config_path, 'r') as f:
        return json.load(f)


def start_scanners_from_config(config: Dict) -> List[BLEScanner]:
    scanners: List[BLEScanner] = []
    api_host = config.get('api_host', 'localhost')
    api_port = config.get('api_port', 8000)
    server_base_url = f"http://{api_host}:{api_port}"

    gates = config.get('gates')
    if not gates:
        # Backward compatibility: fall back to flat scanners list
        for sc in config.get('scanners', []):
            cfg = ScannerConfig(
                scanner_id=sc['id'],
                gate_id=sc.get('gate_id'),
                server_url=server_base_url,
                api_key=sc.get('api_key', 'default-key'),
                rssi_threshold=sc.get('rssi_threshold', -80),
                rssi_bias_db=sc.get('rssi_bias_db', 0),
                scan_interval=sc.get('scan_interval', 1.0),
                batch_size=sc.get('batch_size', 10),
                adapter=sc.get('adapter')
            )
            s = BLEScanner(cfg)
            s.start_scanning()
            scanners.append(s)
        return scanners

    # Multi-gate
    for gate in gates:
        gate_id = gate['id']
        # hysteresis is consumed by API/FSM; scanner only needs scanners list
        for sc in gate.get('scanners', []):
            cfg = ScannerConfig(
                scanner_id=sc.get('id') or f"{gate_id}-{sc.get('adapter','hci')}",
                gate_id=gate_id,
                server_url=server_base_url,
                api_key=sc.get('api_key', 'default-key'),
                rssi_threshold=sc.get('rssi_threshold', -80),
                rssi_bias_db=sc.get('rssi_bias_db', 0),
                scan_interval=sc.get('scan_interval', 1.0),
                batch_size=sc.get('batch_size', 10),
                adapter=sc.get('adapter')
            )
            logger.info(f"Starting scanner {cfg.scanner_id} in gate {gate_id} using {cfg.adapter}", "SCANNER")
            s = BLEScanner(cfg)
            s.start_scanning()
            scanners.append(s)
    return scanners


essential_example_config = {
    "api_host": "localhost",
    "api_port": 8000,
    "gates": [
        {
            "id": "gate-1",
            "hysteresis": {"enter_dbm": -58, "exit_dbm": -64, "min_hold_ms": 1200},
            "scanners": [
                {"id": "gate-1-left", "adapter": "hci0", "rssi_threshold": -60, "rssi_bias_db": 0},
                {"id": "gate-1-right", "adapter": "hci1", "rssi_threshold": -55, "rssi_bias_db": 0}
            ]
        }
    ]
}


def main():
    parser = argparse.ArgumentParser(description="Scanner Service (hardware-only)")
    parser.add_argument('--config', default='scanner_config.json', help='Scanner config JSON (supports gates[])')
    args = parser.parse_args()

    config = load_config(args.config)
    scanners = start_scanners_from_config(config)

    try:
        logger.info("Scanner service running. Ctrl+C to stop.", "SCANNER")
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for s in scanners:
            s.stop_scanning()


if __name__ == '__main__':
    main()
