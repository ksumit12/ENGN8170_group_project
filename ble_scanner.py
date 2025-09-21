#!/usr/bin/env python3
"""
BLE Scanner - Multi-beacon detection and server communication
Scans ONLY iBeacon and Eddystone (UID/URL) beacons and posts detections to the server.
Extracts stable identifiers for reliable boat mapping:
- iBeacon        -> uuid:major:minor
- Eddystone-UID  -> namespace:instance
- Eddystone-URL  -> decoded URL
"""

import asyncio
import time
import threading
import json
import requests
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from bleak import BleakScanner
from logging_config import get_logger

# Use the system logger
logger = get_logger()

# ---- Beacon protocol constants ----
APPLE_CID = 0x004C  # iBeacon lives under Apple Manufacturer Specific Data
EDDYSTONE_UUID = "0000feaa-0000-1000-8000-00805f9b34fb"  # 0xFEAA

# Eddystone frame types
EDDYSTONE_UID = 0x00
EDDYSTONE_URL = 0x10
# (0x20 TLM and 0x30 EID are ignored)

# Eddystone URL decoding (per spec)
URL_SCHEMES = {
    0x00: "http://www.",
    0x01: "https://www.",
    0x02: "http://",
    0x03: "https://",
}
URL_ENCODINGS = {
    0x00: ".com/", 0x01: ".org/", 0x02: ".edu/", 0x03: ".net/",
    0x04: ".info/", 0x05: ".biz/", 0x06: ".gov/",
    0x07: ".com",  0x08: ".org",  0x09: ".edu",  0x0a: ".net",
    0x0b: ".info", 0x0c: ".biz",  0x0d: ".gov",
}

@dataclass
class DetectionObservation:
    # Common
    mac: str
    rssi: int
    ts: float
    name: Optional[str] = None

    # Protocol + stable ID
    protocol: Optional[str] = None         # "ibeacon" | "eddystone-uid" | "eddystone-url"
    beacon_stable_id: Optional[str] = None # key to tie beacon -> boat

    # iBeacon fields (if present)
    ibeacon_uuid: Optional[str] = None
    ibeacon_major: Optional[int] = None
    ibeacon_minor: Optional[int] = None
    ibeacon_tx_power: Optional[int] = None

    # Eddystone UID fields (if present)
    eddystone_namespace: Optional[str] = None
    eddystone_instance: Optional[str] = None
    eddystone_tx_power: Optional[int] = None

    # Eddystone URL (if present)
    eddystone_url: Optional[str] = None

@dataclass
class ScannerConfig:
    scanner_id: str
    server_url: str
    api_key: str
    scan_interval: float = 1.0
    rssi_threshold: int = -80
    batch_size: int = 10
    dry_run: bool = False  # If True, print payload instead of POST
    active_window_seconds: int = 8  # Consider detections "active" within this many seconds
    adapter: str = None  # BLE adapter to use (e.g., 'hci0', 'hci1', 'hci2')

# ---------- Parsing helpers ----------
def _fmt_uuid(b: bytes) -> str:
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def parse_ibeacon(mfg_payload: bytes) -> Optional[dict]:
    """
    iBeacon payload (after Apple CID):
    0: 0x02, 1: 0x15, 2..17: UUID, 18..19: Major, 20..21: Minor, 22: TxPower
    """
    if len(mfg_payload) < 23 or mfg_payload[0] != 0x02 or mfg_payload[1] != 0x15:
        return None
    uuid = _fmt_uuid(mfg_payload[2:18])
    major = int.from_bytes(mfg_payload[18:20], "big")
    minor = int.from_bytes(mfg_payload[20:22], "big")
    tx_power = int.from_bytes(mfg_payload[22:23], "big", signed=True)
    return {
        "protocol": "ibeacon",
        "stable_id": f"{uuid}:{major}:{minor}",
        "uuid": uuid, "major": major, "minor": minor, "tx_power": tx_power
    }

def parse_eddystone(advertisement_data) -> Optional[dict]:
    """
    Accept only Eddystone UID (0x00) and URL (0x10) frames.
    Ignore TLM/EID/unknown frames.
    """
    uuids = (advertisement_data.service_uuids or [])
    if EDDYSTONE_UUID not in [u.lower() for u in uuids]:
        return None

    sd = advertisement_data.service_data or {}
    feaa = None
    for k, v in sd.items():
        if k.lower() == EDDYSTONE_UUID:
            feaa = bytes(v)
            break
    if not feaa or len(feaa) < 1:
        return None

    ftype = feaa[0]
    # UID
    if ftype == EDDYSTONE_UID:
        if len(feaa) < 18:
            return None
        tx_power = int.from_bytes(feaa[1:2], "big", signed=True)
        namespace = feaa[2:12].hex()
        instance  = feaa[12:18].hex()
        return {
            "protocol": "eddystone-uid",
            "stable_id": f"{namespace}:{instance}",
            "namespace": namespace, "instance": instance, "tx_power": tx_power
        }
    # URL
    if ftype == EDDYSTONE_URL:
        if len(feaa) < 3:
            return None
        tx_power = int.from_bytes(feaa[1:2], "big", signed=True)
        scheme = URL_SCHEMES.get(feaa[2], "")
        url = scheme
        for b in feaa[3:]:
            url += URL_ENCODINGS[b] if b in URL_ENCODINGS else (chr(b) if 32 <= b <= 126 else "")
        return {
            "protocol": "eddystone-url",
            "stable_id": url,
            "url": url, "tx_power": tx_power
        }
    # TLM/EID/others -> ignore
    return None

class BLEScanner:
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.running = False
        self.detected_beacons: Dict[str, DetectionObservation] = {}
        self.observation_queue: List[DetectionObservation] = []
        self.lock = threading.Lock()

    def detection_callback(self, device, advertisement_data):
        """
        Accept **only** iBeacon or Eddystone (UID/URL).
        Extract a stable ID + include MAC and Name for boat mapping.
        """
        # Prefer RSSI from advertisement; fall back to device RSSI if missing
        rssi = getattr(advertisement_data, 'rssi', None)
        if rssi is None:
            rssi = getattr(device, 'rssi', None)
        if rssi is None:
            logger.debug(f"Skipping advertisement with no RSSI for {getattr(device, 'address', 'unknown')}", "SCANNER")
            return
        if rssi < self.config.rssi_threshold:
            logger.debug(f"Ignoring {getattr(device, 'address', 'unknown')} due to RSSI {rssi}dBm < threshold {self.config.rssi_threshold}dBm", "SCANNER")
            return

        mac = device.address
        name = getattr(advertisement_data, 'local_name', None) or device.name or "Unknown"
        ts = time.time()

        obs: Optional[DetectionObservation] = None

        # Try iBeacon (Apple 0x004C)
        try:
            mfg = advertisement_data.manufacturer_data or {}
            apple_payload = mfg.get(APPLE_CID)
            if apple_payload:
                parsed = parse_ibeacon(bytes(apple_payload))
                if parsed:
                    obs = DetectionObservation(
                        mac=mac, rssi=rssi, ts=ts, name=name,
                        protocol=parsed["protocol"],
                        beacon_stable_id=parsed["stable_id"],
                        ibeacon_uuid=parsed["uuid"],
                        ibeacon_major=parsed["major"],
                        ibeacon_minor=parsed["minor"],
                        ibeacon_tx_power=parsed["tx_power"],
                    )
        except Exception as e:
            logger.debug(f"iBeacon parse error for {mac}: {e}", "SCANNER")
            obs = None

        # Else try Eddystone UID/URL
        if obs is None:
            try:
                edd = parse_eddystone(advertisement_data)
            except Exception as e:
                logger.debug(f"Eddystone parse error for {mac}: {e}", "SCANNER")
                edd = None
            if edd:
                if edd["protocol"] == "eddystone-uid":
                    obs = DetectionObservation(
                        mac=mac, rssi=rssi, ts=ts, name=name,
                        protocol="eddystone-uid",
                        beacon_stable_id=edd["stable_id"],
                        eddystone_namespace=edd["namespace"],
                        eddystone_instance=edd["instance"],
                        eddystone_tx_power=edd["tx_power"],
                    )
                elif edd["protocol"] == "eddystone-url":
                    obs = DetectionObservation(
                        mac=mac, rssi=rssi, ts=ts, name=name,
                        protocol="eddystone-url",
                        beacon_stable_id=edd["stable_id"],
                        eddystone_url=edd["url"],
                        eddystone_tx_power=edd["tx_power"],
                    )

        # If neither matched, ignore (non-beacon or unsupported Eddystone frame)
        if obs is None:
            logger.debug(f"Unsupported frame for {mac} - not iBeacon/Eddystone UID/URL", "SCANNER")
            return

        with self.lock:
            # Latest per MAC (handy for status)
            self.detected_beacons[mac] = obs
            self.observation_queue.append(obs)
            
            # Log beacon detection
            logger.info(f"BLE beacon detected: {name} ({mac}) - {obs.protocol} - RSSI: {rssi} dBm", "SCANNER")
            
            if len(self.observation_queue) >= self.config.batch_size:
                self._process_observations()

    def _process_observations(self):
        """Send or print a batch of observations."""
        if not self.observation_queue:
            return

        observations = self.observation_queue.copy()
        self.observation_queue.clear()

        payload = {
            "scanner_id": self.config.scanner_id,
            "observations": [
                {
                    # Always send these (tie to boat using protocol + beacon_stable_id)
                    "protocol": o.protocol,
                    "beacon_stable_id": o.beacon_stable_id,
                    "mac": o.mac,
                    "name": o.name,
                    "rssi": o.rssi,
                    "ts": o.ts,
                    # iBeacon details
                    "ibeacon_uuid": o.ibeacon_uuid,
                    "ibeacon_major": o.ibeacon_major,
                    "ibeacon_minor": o.ibeacon_minor,
                    "ibeacon_tx_power": o.ibeacon_tx_power,
                    # Eddystone details
                    "eddystone_namespace": o.eddystone_namespace,
                    "eddystone_instance": o.eddystone_instance,
                    "eddystone_url": o.eddystone_url,
                    "eddystone_tx_power": o.eddystone_tx_power,
                } for o in observations
            ]
        }

        if self.config.dry_run:
            logger.info(f"[DRY-RUN] Would POST {len(observations)} observation(s):\n{json.dumps(payload, indent=2)}", "SCANNER")
            return

        # POST to server
        try:
            response = requests.post(
                f"{self.config.server_url}/api/v1/detections",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}"
                },
                timeout=5
            )
            response.raise_for_status()
            logger.debug(f"Posted {len(observations)} observations to server", "SCANNER")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post observations to server: {e}", "SCANNER")
            # Re-queue a small slice to avoid unbounded growth
            with self.lock:
                self.observation_queue = observations[:5] + self.observation_queue

    async def scan_continuously(self):
        """Continuously scan for BLE devices (beacon-filtered)."""
        logger.info(f"Starting BLE scanner {self.config.scanner_id}", "SCANNER")
        logger.info(f"Server URL: {self.config.server_url}", "SCANNER")
        logger.info(f"RSSI threshold: {self.config.rssi_threshold} dBm", "SCANNER")

        # Active scanning improves discovery of iBeacon/Eddystone on some platforms
        # Use specified adapter if provided
        scanner_kwargs = {"scanning_mode": "active"}
        if self.config.adapter:
            scanner_kwargs["adapter"] = self.config.adapter
            logger.info(f"Using BLE adapter: {self.config.adapter}", "SCANNER")
        
        scanner = BleakScanner(self.detection_callback, **scanner_kwargs)

        try:
            await scanner.start()
            logger.info("BLE scanner started successfully", "SCANNER")
            self.running = True

            while self.running:
                await asyncio.sleep(self.config.scan_interval)
                with self.lock:
                    # Prune stale detections so UI reflects beacons that are truly active now
                    now_ts = time.time()
                    stale_keys = [mac for mac, obs in self.detected_beacons.items()
                                  if obs.ts is None or (now_ts - obs.ts) > self.config.active_window_seconds]
                    for mac in stale_keys:
                        self.detected_beacons.pop(mac, None)
                    if self.observation_queue:
                        self._process_observations()
        except Exception as e:
            logger.error(f"BLE scan error: {e}", "SCANNER")
        finally:
            self.running = False
            await scanner.stop()
            logger.info("BLE scanner stopped", "SCANNER")

    def start_scanning(self):
        """Start BLE scanning in a separate thread."""
        def run_scanner():
            asyncio.run(self.scan_continuously())
        self.scanner_thread = threading.Thread(target=run_scanner, daemon=True)
        self.scanner_thread.start()

    def stop_scanning(self):
        """Stop BLE scanning."""
        self.running = False
        if hasattr(self, 'scanner_thread'):
            self.scanner_thread.join(timeout=5)

    def get_detected_beacons(self) -> Dict[str, DetectionObservation]:
        """Get currently detected beacons."""
        with self.lock:
            now_ts = time.time()
            # Return only fresh detections within the active window
            return {
                mac: obs for mac, obs in self.detected_beacons.copy().items()
                if obs.ts is not None and (now_ts - obs.ts) <= self.config.active_window_seconds
            }

    def get_status(self) -> Dict:
        """Get scanner status."""
        with self.lock:
            return {
                'scanner_id': self.config.scanner_id,
                'running': self.running,
                'detected_beacons': len(self.detected_beacons),
                'queued_observations': len(self.observation_queue),
                'last_scan': max([obs.ts for obs in self.detected_beacons.values()]) if self.detected_beacons else None
            }

def main():
    """Main entry point for standalone scanner."""
    import argparse

    parser = argparse.ArgumentParser(description="BLE Scanner for Boat Tracking (iBeacon/Eddystone only)")
    parser.add_argument("--scanner-id", required=True, help="Unique scanner identifier")
    parser.add_argument("--server-url", default="http://localhost:8000", help="Server API URL")
    parser.add_argument("--api-key", default="default-key", help="API key for server authentication")
    parser.add_argument("--rssi-threshold", type=int, default=-80, help="RSSI threshold in dBm")
    parser.add_argument("--scan-interval", type=float, default=1.0, help="Scan interval in seconds")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size before POST")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads instead of POSTing (for testing)")

    args = parser.parse_args()

    config = ScannerConfig(
        scanner_id=args.scanner_id,
        server_url=args.server_url,
        api_key=args.api_key,
        rssi_threshold=args.rssi_threshold,
        scan_interval=args.scan_interval,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    scanner = BLEScanner(config)

    try:
        scanner.start_scanning()
        logger.info("Scanner started. Press Ctrl+C to stop.", "SCANNER")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping scanner...", "SCANNER")
        scanner.stop_scanning()
        logger.info("Scanner stopped", "SCANNER")

if __name__ == "__main__":
    main()
