#!/usr/bin/env python3
"""
Resilient Bluetooth Selfie Stick Logger (evdev-only, no set_nonblocking)
- Scans for input devices that expose KEY_VOLUMEDOWN
- Uses select() on fds (blocking reads are fine once select() says ready)
- Survives device sleep/disconnect (ENODEV/EIO) and rescans
"""

import os, csv, time, errno, select
from datetime import datetime, timezone
from evdev import InputDevice, list_devices, ecodes

PREFERRED_NAMES = {"Q07", "PICO"}   # names to prefer if present
WATCH_CODE = ecodes.KEY_VOLUMEDOWN  # change to KEY_PLAYPAUSE if your button sends that
CSV_PATH = "bt_triggers.csv"
GRAB_DEVICE = False                 # sleepy remotes often vanish mid-grab; leave False
RESCAN_INTERVAL = 0.5               # seconds

def ensure_csv(path):
    new = not os.path.exists(path)
    f = open(path, "a", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(["iso_time_utc","epoch_s","device_path","device_name","value","meaning"])
    return f, w

def candidates():
    """Return InputDevices that support WATCH_CODE, sorted by preference."""
    found = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            caps = set(dev.capabilities().get(ecodes.EV_KEY, []))
            if WATCH_CODE in caps:
                score = 0
                name = (dev.name or "")
                if any(pref.lower() in name.lower() for pref in PREFERRED_NAMES):
                    score += 5
                if "consumer" in name.lower():
                    score += 1
                found.append((score, dev))
        except Exception:
            pass
    found.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in found]

def open_and_register(devmap, dev):
    """Open device, optionally grab, and register fd -> dev."""
    try:
        _ = dev.fd  # force-open underlying fd
        if GRAB_DEVICE:
            try:
                dev.grab()
            except Exception:
                # not fatal; continue without grabbing
                pass
        devmap[dev.fd] = dev
        print(f"[open] {dev.path}  name='{dev.name}'")
    except Exception as e:
        try: dev.close()
        except Exception: pass
        print(f"[skip] {getattr(dev,'path','?')}: {e}")

def rescan_devices(devmap):
    """Purge closed devices and open any new candidates."""
    # purge invalid fds
    for fd in list(devmap.keys()):
        d = devmap[fd]
        try:
            _ = d.fd
        except Exception:
            devmap.pop(fd, None)

    paths_tracked = {d.path for d in devmap.values()}
    for dev in candidates():
        if dev.path not in paths_tracked:
            open_and_register(devmap, dev)

def main():
    if os.geteuid() != 0:
        print("Tip: run with sudo (or add a udev rule) to read /dev/input/*")

    f, w = ensure_csv(CSV_PATH)
    devmap = {}  # fd -> InputDevice
    last_rescan = 0.0

    print("Listening for KEY_VOLUMEDOWN… Press the selfie button to wake it. Ctrl+C to stop.")
    try:
        while True:
            now = time.time()
            if now - last_rescan > RESCAN_INTERVAL or not devmap:
                rescan_devices(devmap)
                last_rescan = now

            if not devmap:
                time.sleep(0.1)
                continue

            # Wait up to 0.5s for any device to become readable
            r, _, _ = select.select(list(devmap.keys()), [], [], 0.5)
            if not r:
                continue

            for fd in r:
                dev = devmap.get(fd)
                if not dev:
                    continue
                try:
                    for ev in dev.read():  # safe after select()
                        if ev.type == ecodes.EV_KEY and ev.code == WATCH_CODE:
                            meaning = {0:"release", 1:"press", 2:"repeat"}.get(ev.value, str(ev.value))
                            t = time.time()
                            iso = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
                            print(f"[{iso}] {dev.path} '{dev.name}': KEY_VOLUMEDOWN {meaning}")
                            w.writerow([iso, f"{t:.6f}", dev.path, dev.name, ev.value, meaning])
                            f.flush()
                except OSError as e:
                    # Device went away (sleep/disconnect) – clean up and let rescan reopen later
                    if e.errno in (errno.ENODEV, errno.EIO):
                        try: dev.ungrab()
                        except Exception: pass
                        try: dev.close()
                        except Exception: pass
                        devmap.pop(fd, None)
                        print(f"[close] {dev.path} vanished; will rescan…")
                    else:
                        print(f"[error] read {dev.path}: {e}")
                except BlockingIOError:
                    # Shouldn't happen since select() said ready, but ignore if it does
                    pass
                except Exception as e:
                    print(f"[error] unexpected on {dev.path}: {e}")

    except KeyboardInterrupt:
        pass
    finally:
        for d in devmap.values():
            try: d.ungrab()
            except Exception: pass
            try: d.close()
            except Exception: pass
        f.close()
        print("Stopped.")

if __name__ == "__main__":
    main()
