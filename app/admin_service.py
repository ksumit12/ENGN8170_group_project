#!/usr/bin/env python3
"""
Admin/Registration service layer
Centralizes write logic and validation to avoid duplication and fragile coupling.
"""
from __future__ import annotations

from typing import Tuple, Dict, Any
from datetime import datetime, timezone
import json
import os

from .database_models import DatabaseManager, BoatStatus


def _ok(payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    return 200, payload


def _bad_request(msg: str) -> Tuple[int, Dict[str, Any]]:
    return 400, {"success": False, "error": msg}


def _conflict(msg: str) -> Tuple[int, Dict[str, Any]]:
    return 409, {"success": False, "error": msg}


def _not_found(msg: str) -> Tuple[int, Dict[str, Any]]:
    return 404, {"success": False, "error": msg}


def register_beacon(db: DatabaseManager, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Register a beacon to a boat with robust validation and conflict detection.
    Expected data: mac_address, name(optional display), boat_name, boat_class, boat_serial(optional), boat_brand?, boat_notes?
    """
    mac = (data.get("mac_address") or "").strip()
    boat_name = (data.get("boat_name") or "").strip()
    boat_class = (data.get("boat_class") or "").strip()
    boat_serial = (data.get("boat_serial") or "").strip()
    disp_name = (data.get("name") or "").strip()

    # Required fields (serial is now optional)
    missing = [k for k, v in {
        "mac_address": mac,
        "boat_name": boat_name,
        "boat_class": boat_class,
    }.items() if not v]
    if missing:
        return _bad_request(f"Missing required fields: {', '.join(missing)}")
    
    # Generate boat ID if serial not provided
    if not boat_serial:
        # Generate unique ID based on boat name and timestamp
        import time
        boat_serial = f"{boat_name.replace(' ', '_').lower()}_{int(time.time())}"

    # Check if beacon exists and is available
    beacon = db.get_beacon_by_mac(mac)
    if not beacon:
        return _not_found("Beacon not found. Ensure it is powered and detected.")
    
    # Check if beacon is already assigned to another boat
    existing_beacon_assignment = db.get_boat_by_beacon(beacon.id)
    if existing_beacon_assignment and existing_beacon_assignment.id != boat_serial:
        return _conflict(f"Beacon {mac} is already assigned to boat '{existing_beacon_assignment.name}' (ID: {existing_beacon_assignment.id}). Unassign first.")

    # Check for boat serial number conflicts
    existing_boat_by_serial = db.get_boat(boat_serial)
    if existing_boat_by_serial:
        # Check if this is the same boat or a different one
        if existing_boat_by_serial.name != boat_name:
            return _conflict(f"Boat serial '{boat_serial}' is already registered to boat '{existing_boat_by_serial.name}'. Use a different serial number or update the existing boat.")
        # Same serial and name - update the existing boat
        try:
            db.update_boat(boat_serial, name=boat_name, class_type=boat_class)
        except Exception as e:
            return _bad_request(f"Could not update boat: {e}")
    else:
        # Check for boat name conflicts - only check ACTIVE boats
        all_boats = db.get_all_boats()
        active_boat_with_same_name = None
        for boat in all_boats:
            if boat.name == boat_name and boat.id != boat_serial:
                # Check if boat is active (not retired)
                op_status = getattr(boat, 'op_status', 'ACTIVE')
                if op_status == 'ACTIVE':
                    active_boat_with_same_name = boat
                    break
        
        if active_boat_with_same_name:
            return _conflict(f"Boat name '{boat_name}' is already used by an active boat (ID: {active_boat_with_same_name.id}). Please retire the old boat first or use a different name.")
        
        # Create new boat
        try:
            notes_parts = []
            if boat_serial and not boat_serial.startswith(boat_name.replace(' ', '_').lower()):
                notes_parts.append(f"Serial: {boat_serial}")
            if data.get('boat_brand'):
                notes_parts.append(f"Brand: {data.get('boat_brand')}")
            if data.get('boat_notes'):
                notes_parts.append(data.get('boat_notes'))
            
            notes = ", ".join(notes_parts) if notes_parts else "Auto-generated ID"
            
            db.create_boat(
                boat_id=boat_serial,
                name=boat_name,
                class_type=boat_class,
                notes=notes
            )
        except Exception as e:
            return _bad_request(f"Could not create boat: {e}")

    # Update beacon display name (best-effort)
    try:
        from .database_models import BeaconStatus  # noqa: F401 (import for side-effects/types only)
        db.update_beacon(beacon.id, name=disp_name or beacon.name or boat_name)
    except Exception:
        pass

    # Assign beacon to boat
    if not db.assign_beacon_to_boat(beacon.id, boat_serial):
        return _conflict("Assignment failed: boat or beacon already assigned. Unassign first.")

    try:
        db.update_boat_status(boat_serial, BoatStatus.IN_HARBOR)
    except Exception:
        pass

    return _ok({"success": True, "message": "Beacon registered successfully", "boat_id": boat_serial, "beacon_id": beacon.id})


def admin_reset(db: DatabaseManager) -> Tuple[int, Dict[str, Any]]:
    try:
        db.reset_all()
        return _ok({"message": "System reset complete"})
    except Exception as e:
        return 500, {"error": str(e)}


def get_closing(settings_file: str) -> Tuple[int, Dict[str, Any]]:
    value = "20:00"
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r") as f:
                value = json.load(f).get("closing_time", "20:00")
        except Exception:
            value = "20:00"
    return _ok({"closing_time": value})


def set_closing(settings_file: str, value: str) -> Tuple[int, Dict[str, Any]]:
    if not value:
        return _bad_request("closing_time required")
    try:
        hh, mm = map(int, value.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return _bad_request("closing_time must be HH:MM (24h format, e.g., 08:00, 20:00)")
    except Exception:
        return _bad_request("closing_time must be HH:MM (24h format, e.g., 08:00, 20:00)")
    try:
        # Ensure directory exists if settings_file has a path
        settings_dir = os.path.dirname(settings_file)
        if settings_dir:
            os.makedirs(settings_dir, exist_ok=True)
        with open(settings_file, "w") as f:
            json.dump({"closing_time": value, "updated_at": datetime.now(timezone.utc).isoformat()}, f)
        return _ok({"closing_time": value})
    except Exception as e:
        return 500, {"error": str(e)}


