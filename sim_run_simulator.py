#!/usr/bin/env python3
import random
import time
import requests
import json
from datetime import datetime, timezone

from app.database_models import DatabaseManager, DetectionState


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def send_detection_to_api(scanner_id: str, beacon_mac: str, rssi: int, server_url: str = "http://127.0.0.1:8000", log=None):
    """Send a detection to the API server like a real BLE scanner would."""
    payload = {
        "scanner_id": scanner_id,
        "gate_id": "main_gate", 
        "adapter": "hci0",
        "observations": [{
            "protocol": "ibeacon",
            "beacon_stable_id": f"uuid:major:minor:{beacon_mac.replace(':', '')}",
            "mac": beacon_mac,
            "name": f"Beacon-{beacon_mac[-5:]}",
            "rssi": rssi,
            "ts": time.time(),
            "ibeacon_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "ibeacon_major": 1,
            "ibeacon_minor": int(beacon_mac.split(':')[-1], 16),
            "ibeacon_tx_power": -20,
            "eddystone_namespace": None,
            "eddystone_instance": None,
            "eddystone_url": None,
            "eddystone_tx_power": None,
        }]
    }
    if log:
        log("detection_send", scanner_id=scanner_id, beacon_mac=beacon_mac, rssi=rssi, payload=payload)
    
    try:
        response = requests.post(
            f"{server_url}/api/v1/detections",
            json=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer default-key"},
            timeout=2
        )
        if response.status_code == 200:
            print(f"SENT {scanner_id}: {beacon_mac} @ {rssi} dBm")
            if log:
                log("detection_ack", scanner_id=scanner_id, beacon_mac=beacon_mac, rssi=rssi, status=response.status_code)
            return True
        else:
            print(f"ERROR {response.status_code}: {response.text}")
            if log:
                log("detection_error", scanner_id=scanner_id, beacon_mac=beacon_mac, rssi=rssi, status=response.status_code, error=response.text[:500])
            return False
    except Exception as e:
        print(f"FAILED: {e}")
        if log:
            log("detection_fail", scanner_id=scanner_id, beacon_mac=beacon_mac, rssi=rssi, error=str(e))
        return False


def _rssi_series(start: int, end: int, steps: int, noise: int = 2):
    """Generate an RSSI series from start to end (inclusive) with jitter."""
    if steps <= 1:
        return [end]
    delta = (end - start) / float(steps - 1)
    series = []
    cur = float(start)
    for _ in range(steps):
        jitter = random.randint(-noise, noise)
        series.append(int(round(cur)) + jitter)
        cur += delta
    return series


def _sleep_jitter(low: float, high: float):
    time.sleep(random.uniform(low, high))


def simulate_once(db: DatabaseManager, boat_id: str, beacon_mac: str,
                  *,
                  direction: str,
                  in_detect_delay_s=(2.0, 3.0),
                  path_time_s: float = 70.0,
                  outside_duration_s: float = 300.0,
                  out_reflect_delay_s=(10.0, 15.0),
                  server_url: str = "http://127.0.0.1:8000",
                  log=None):
    """Simulate one full movement in the given direction ('exit' or 'enter').

    path_time_s: approximate walk time between inner and outer zones (40–50m path)
    outside_duration_s: time to remain on water/outside before considering return
    """
    if log:
        log("movement_begin", boat_id=boat_id, beacon_mac=beacon_mac, direction=direction)
        # Bind expectation to the declared intent immediately
        log("movement_expect", boat_id=boat_id, expect=("exited" if direction == "exit" else "entered"))
    
    print(f"{direction.upper()} {boat_id} ({beacon_mac})")

    if direction == "exit":
        # EXIT: Shed -> Inner -> Outer -> Water (with latency and lingering reflection)
        print("  Movement: Shed -> Inner -> Outer -> Water")
        if log:
            log("movement_path", boat_id=boat_id, path="shed->inner->outer->water")

        # Enter inner read zone: 2-3s to first detection
        _sleep_jitter(*in_detect_delay_s)

        # Linger at inner for realistic loading/turning: ~30–45s of fluctuating reads
        inner_linger_end = time.time() + max(25.0, min(60.0, path_time_s * 0.5))
        while time.time() < inner_linger_end:
            for rssi in _rssi_series(-70, -52, 3):
                send_detection_to_api("gate-inner", beacon_mac, rssi, server_url, log)
                _sleep_jitter(0.6, 1.0)

        # Begin moving along 40–50m path: inner weakens, occasional outer appears
        steps = max(8, int(path_time_s // 6))
        inner_series = _rssi_series(-60, -78, steps)
        outer_series = _rssi_series(-75, -50, steps)
        for i in range(steps):
            # Inner mostly still visible, weakening
            if random.random() < 0.8:
                send_detection_to_api("gate-inner", beacon_mac, inner_series[i], server_url, log)
            # Outer occasionally begins to see, then strengthens
            if i > steps // 3 and random.random() < 0.7:
                send_detection_to_api("gate-outer", beacon_mac, outer_series[i], server_url, log)
            _sleep_jitter(0.8, 1.2)

        # Outer dominates near exit
        for rssi in _rssi_series(-60, -46, 4):
            send_detection_to_api("gate-outer", beacon_mac, rssi, server_url, log)
            _sleep_jitter(0.4, 0.7)

        # Reflection tail: keep reporting sporadic weaker readings for 10-15s
        tail_end = time.time() + random.uniform(*out_reflect_delay_s)
        while time.time() < tail_end:
            if random.random() < 0.6:
                send_detection_to_api("gate-outer", beacon_mac, random.randint(-82, -68), server_url, log)
            _sleep_jitter(0.8, 1.5)

        # While outside, stay silent for the remainder (simulates going away)
        if outside_duration_s > 0:
            remain = max(0.0, outside_duration_s - (time.time() - inner_linger_end))
            if log:
                log("outside_dwell", boat_id=boat_id, seconds=int(remain))
            time.sleep(remain)

        print("  -> Boat should be ON WATER")
            
    else:
        # ENTER: Water -> Outer -> Inner -> Shed (with approach latency)
        print("  Movement: Water -> Outer -> Inner -> Shed")
        if log:
            log("movement_path", boat_id=boat_id, path="water->outer->inner->shed")

        # Approaching outer read zone
        _sleep_jitter(*in_detect_delay_s)

        # Arriving from water to outer: progressive strengthening
        steps = max(8, int(path_time_s // 6))
        outer_series = _rssi_series(-72, -52, steps)
        for i in range(steps):
            send_detection_to_api("gate-outer", beacon_mac, outer_series[i], server_url, log)
            # Occasional inner pre-read late in the approach
            if i > steps * 2 // 3 and random.random() < 0.6:
                send_detection_to_api("gate-inner", beacon_mac, random.randint(-68, -60), server_url, log)
            _sleep_jitter(0.8, 1.2)

        # Overlap near gate
        for rssi in _rssi_series(-58, -54, 3):
            send_detection_to_api("gate-outer", beacon_mac, rssi, server_url, log)
            send_detection_to_api("gate-inner", beacon_mac, rssi - random.randint(6, 10), server_url, log)
            _sleep_jitter(0.5, 0.8)

        # Inner dominates into shed
        for rssi in _rssi_series(-60, -46, 4):
            send_detection_to_api("gate-inner", beacon_mac, rssi, server_url, log)
            _sleep_jitter(0.4, 0.7)

        # Settling inside: stable reads for ~20–40s
        settle_for = random.uniform(20.0, 40.0)
        end_settle = time.time() + settle_for
        while time.time() < end_settle:
            send_detection_to_api("gate-inner", beacon_mac, random.randint(-56, -48), server_url, log)
            _sleep_jitter(0.8, 1.4)

        print("  -> Boat should be IN SHED")

    return direction


def _state_str(s: DetectionState) -> str:
    try:
        return s.value
    except Exception:
        return str(s)


def _expected_final_state(direction: str) -> DetectionState:
    return DetectionState.OUTSIDE if direction == "exit" else DetectionState.INSIDE


def _get_current_state_for_boat(db: DatabaseManager, boat_id: str) -> DetectionState:
    beacon = db.get_beacon_by_boat(boat_id)
    if not beacon:
        return DetectionState.IDLE
    return db.get_beacon_state(beacon.id) or DetectionState.IDLE


def _poll_actual_state(db: DatabaseManager, boat_id: str, expect: DetectionState, timeout_s: float = 25.0, interval_s: float = 0.5, log=None):
    """Poll current FSM state for a limited time and return the final observed state.
    Prints a few progress lines for visibility."""
    deadline = time.time() + timeout_s
    last_print = 0.0
    while time.time() < deadline:
        cur = _get_current_state_for_boat(db, boat_id)
        # Print at most ~1/sec to keep logs readable
        if time.time() - last_print > 1.0:
            print(f"    observed={_state_str(cur)} (waiting for {_state_str(expect)})")
            if log:
                log("observe_tick", boat_id=boat_id, observed=_state_str(cur), expect=_state_str(expect))
            last_print = time.time()
        if cur == expect:
            return cur
        time.sleep(interval_s)
    return _get_current_state_for_boat(db, boat_id)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Realistic BLE simulator")
    parser.add_argument("--cooldown-after-exit-seconds", type=int, default=300,
                        help="Seconds to wait before changing state again for a boat after an EXIT (default 300s)")
    parser.add_argument("--min-wait", type=float, default=0.5,
                        help="Minimum seconds between movements when eligible boats exist (default 0.5)")
    parser.add_argument("--max-wait", type=float, default=1.5,
                        help="Maximum seconds between movements when eligible boats exist (default 1.5)")
    parser.add_argument("--max-parallel-exited", type=int, default=3,
                        help="Target at most this many boats in exited state concurrently (best-effort)")
    parser.add_argument("--enter_settle_delay", type=float, default=20.0,
                        help="Average seconds to wait after ENTERED before considering exit again (stochastic)")
    parser.add_argument("--log-file", type=str, default="live_sim.log",
                        help="Path to write JSONL log of simulator intents and observed FSM states")
    args = parser.parse_args()

    # Truncate existing log so each run starts fresh
    try:
        with open(args.log_file, "w", encoding="utf-8") as _f:
            _f.write("")
    except Exception:
        pass

    # Structured JSON logger (append JSON lines)
    def log(event: str, **fields):
        rec = {"ts": iso_now(), "event": event}
        rec.update(fields)
        try:
            with open(args.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    db = DatabaseManager()
    
    # Get boat-beacon assignments to simulate
    assignments = db.get_active_assignments()
    if not assignments:
        print("No active boat-beacon assignments found. Run sim_seed_data.py first.")
        return
    
    # Convert beacon IDs to MAC addresses for realistic simulation
    boat_beacons = []
    for boat_id, beacon_id in assignments:
        beacon = db.get_beacon_by_boat(boat_id)
        if beacon and beacon.mac_address:
            boat_beacons.append((boat_id, beacon.mac_address))
    
    if not boat_beacons:
        print("No beacon MAC addresses found for assigned boats.")
        return

    print(f"Starting realistic BLE simulation with {len(boat_beacons)} boats")
    print("Sending HTTP requests to API server like real BLE scanners would...")
    print("Check dashboard: http://127.0.0.1:5000/ and FSM: http://127.0.0.1:5000/fsm")
    print("Press Ctrl+C to stop.\n")
    log("sim_start", boats=len(boat_beacons))
    
    # Ensure all boats start ENTERED by sending a brief inner detection burst
    for boat_id, beacon_mac in boat_beacons:
        for rssi in _rssi_series(-64, -52, 3):
            send_detection_to_api("gate-inner", beacon_mac, rssi, "http://127.0.0.1:8000", log)
            _sleep_jitter(0.3, 0.5)

    # Per-boat cooldown tracker: boat_id -> epoch seconds when next simulation is allowed
    cooldown_until = {boat_id: 0.0 for boat_id, _ in boat_beacons}
    # Track rough state for scheduling (not authoritative)
    approx_state = {boat_id: "entered" for boat_id, _ in boat_beacons}
    # Per-boat episode lock to prevent overlapping intents
    active_episode = {boat_id: False for boat_id, _ in boat_beacons}

    try:
        while True:
            now = time.time()

            # Eligible boats are those whose cooldown has passed
            eligible = [(b, m) for (b, m) in boat_beacons if now >= cooldown_until.get(b, 0.0)]

            if not eligible:
                # No boat eligible yet; wait until the soonest cooldown expires
                next_ready = min(cooldown_until.values()) if cooldown_until else now + 1
                sleep_for = max(0.5, next_ready - now)
                print(f"All boats cooling down. Waiting {sleep_for:.1f}s...")
                log("cooldown_wait", seconds=sleep_for)
                time.sleep(sleep_for)
                continue

            # Choose one eligible boat that is not currently in an active episode
            not_active = [(b, m) for (b, m) in eligible if not active_episode.get(b, False)]
            if not not_active:
                time.sleep(0.5)
                continue
            boat_id, beacon_mac = random.choice(not_active)
            # Randomly choose direction but bias by approx_state to respect sequences
            if approx_state.get(boat_id) in ("entered", "inner", "idle"):
                direction = "exit"
            else:
                direction = "enter"
            # If too many are roughly out, bias toward enter
            if list(approx_state.values()).count("exited") >= max(1, int(args.max_parallel_exited)):
                direction = "enter"

            # Log intent vs current state before starting
            before = _get_current_state_for_boat(db, boat_id)
            print(f"INTENT: {boat_id} -> {direction.upper()} | current={_state_str(before)}")
            log("intent", boat_id=boat_id, direction=direction, current=_state_str(before))

            # Guardrail: mark active to avoid overlapping intents for the same boat
            active_episode[boat_id] = True
            try:
                # Run the chosen direction deterministically and observe convergence
                # Outside time per episode: random < 10 minutes
                outside_s = random.uniform(120.0, 9 * 60.0)
                final_dir = simulate_once(
                    db, boat_id, beacon_mac,
                    direction=direction,
                    in_detect_delay_s=(2.0, 3.0),
                    path_time_s=random.uniform(45.0, 90.0),
                    outside_duration_s=outside_s if direction == "exit" else 0.0,
                    out_reflect_delay_s=(10.0, 15.0),
                    server_url="http://127.0.0.1:8000",
                    log=log
                )
                expected = _expected_final_state(final_dir)
                # With minute-scale steps, allow longer convergence window
                observed = _poll_actual_state(db, boat_id, expected, timeout_s=60.0, interval_s=1.0, log=log)
                print(f"FINAL: expect={_state_str(expected)} observed={_state_str(observed)}")
                log("final", boat_id=boat_id, expect=_state_str(expected), observed=_state_str(observed))
            finally:
                active_episode[boat_id] = False

            # Update approximate state and cooldowns based on observed result
            if _state_str(observed) == DetectionState.OUTSIDE.value:
                approx_state[boat_id] = "exited"
                # Boat will be out for the outside_dwell we already waited; allow immediate scheduling for others
                ready_at = time.time() + random.uniform(10, 40)  # brief pause before allowing re-entry
                cooldown_until[boat_id] = ready_at
                if len(boat_beacons) == 1:
                    wait_left = ready_at - time.time()
                    print(f"Cooling down {boat_id} for {int(wait_left)}s (after EXIT)...")
                    log("cooldown_after_exit", boat_id=boat_id, seconds=int(wait_left))
                    if wait_left > 0:
                        time.sleep(wait_left)
            elif _state_str(observed) == DetectionState.INSIDE.value:
                approx_state[boat_id] = "entered"
                # Add a settle delay before boat can exit again
                settle = max(5.0, random.gauss(args.enter_settle_delay, args.enter_settle_delay * 0.3))
                cooldown_until[boat_id] = time.time() + settle
                log("cooldown_after_enter", boat_id=boat_id, seconds=int(settle))
            else:
                # Mismatch or unresolved; reset scheduling to idle-like
                approx_state[boat_id] = "idle"

            # Short random pause between movements if there are other eligible boats
            wait_time = random.uniform(max(0.0, float(args.min_wait)), max(float(args.min_wait), float(args.max_wait)))
            print(f"Wait {wait_time:.1f}s...\n")
            log("inter_move_wait", seconds=wait_time)
            time.sleep(wait_time)
            
    except KeyboardInterrupt:
        print("Simulation stopped.")
        log("sim_stop")


if __name__ == "__main__":
    main()


