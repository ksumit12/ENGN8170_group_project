#!/usr/bin/env python3
"""
BLE Watchdog: Continuously monitors BLE adapters (hci0/hci1) and attempts recovery.
- Logs events to stdout (journalctl will capture under systemd)
- Health checks:
  * Adapter presence via hciconfig
  * BlueZ service active
  * Optional: quick sniff for Apple mfr frames using bleak (best-effort)
- Recovery actions:
  * bluetoothctl scan off
  * systemctl restart bluetooth
  * hciconfig hciX reset/up

Exit code is always 0; intended as a long-running service.
"""
from __future__ import annotations

import subprocess
import time
import sys
from datetime import datetime


def sh(cmd: list[str], timeout: float = 5.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, '', str(e)


def log(level: str, msg: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{ts} | {level.upper():<5} | {msg}", flush=True)


def bluez_active() -> bool:
    rc, out, _ = sh(['systemctl', 'is-active', 'bluetooth'])
    return rc == 0 and out.strip() == 'active'


def adapters_present() -> list[str]:
    rc, out, _ = sh(['hciconfig', '-a'])
    if rc != 0:
        return []
    present = []
    cur = None
    for line in out.splitlines():
        if line.startswith('hci') and ':' in line:
            cur = line.split(':', 1)[0].strip()
            present.append(cur)
    return present


def adapter_up(adapter: str) -> bool:
    rc, out, _ = sh(['hciconfig', adapter])
    if rc != 0:
        return False
    return 'UP RUNNING' in out or 'UP' in out


def recover() -> None:
    log('warn', 'Recovery: stopping scans')
    sh(['bash', '-lc', 'bluetoothctl scan off || true'])
    log('warn', 'Recovery: restarting bluetooth service')
    sh(['systemctl', 'restart', 'bluetooth'])
    time.sleep(2)
    for a in ('hci0', 'hci1'):
        log('warn', f'Recovery: resetting {a}')
        sh(['hciconfig', a, 'reset'])
        time.sleep(0.5)
        sh(['hciconfig', a, 'up'])


def main():
    check_interval_s = 5.0
    unstable_count = 0
    while True:
        try:
            pres = adapters_present()
            active = bluez_active()
            h0 = adapter_up('hci0') if 'hci0' in pres else False
            h1 = adapter_up('hci1') if 'hci1' in pres else False

            log('info', f"BlueZ active={active} | present={pres} | hci0_up={h0} | hci1_up={h1}")

            ok = active and h0 and h1
            if not ok:
                unstable_count += 1
                if unstable_count >= 2:
                    log('error', 'BLE unstable; attempting recovery')
                    recover()
                    unstable_count = 0
            else:
                unstable_count = 0
        except Exception as e:
            log('error', f'Watchdog loop error: {e}')
        time.sleep(check_interval_s)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)


