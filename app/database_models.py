#!/usr/bin/env python3
"""
Database Models for BLE Boat Tracking System
Supports multiple beacons, boats, and assignments with full history
"""

import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class BeaconStatus(Enum):
    UNCLAIMED = "unclaimed"
    ASSIGNED = "assigned"
    RETIRED = "retired"

class BoatStatus(Enum):
    IN_HARBOR = "in_harbor"
    OUT = "out"
    UNKNOWN = "unknown"

class DetectionState(Enum):
    IDLE = "idle"
    INSIDE = "entered"        # canonical name, value for DB compat
    OUTSIDE = "exited"        # canonical name, value for DB compat
    # Backward-compatible aliases (kept minimal)
    ENTERED = "entered"
    EXITED = "exited"

@dataclass
class Boat:
    id: str
    name: str
    class_type: str
    status: BoatStatus
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    op_status: str = 'ACTIVE'
    status_updated_at: Optional[datetime] = None

@dataclass
class Beacon:
    id: str
    mac_address: str
    name: Optional[str]
    status: BeaconStatus
    last_seen: Optional[datetime]
    last_rssi: Optional[int]
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None

@dataclass
class BoatBeaconAssignment:
    id: str
    boat_id: str
    beacon_id: str
    assigned_at: datetime
    unassigned_at: Optional[datetime]
    is_active: bool
    notes: Optional[str] = None

@dataclass
class Detection:
    id: str
    scanner_id: str
    beacon_id: str
    rssi: int
    timestamp: datetime
    state: DetectionState

@dataclass
class Scanner:
    id: str
    name: str
    location: str
    is_active: bool
    created_at: datetime

class DatabaseManager:
    def __init__(self, db_path: str = "boat_tracking.db"):
        # Always use a stable absolute path under project/data to prevent accidental
        # creation of a new empty database when CWD changes.
        import os
        # Resolve project root as parent of the app/ package directory so DB path
        # remains stable even if this module moves.
        app_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(app_dir)
        if not os.path.isabs(db_path):
            # Preferred location: <project_root>/data/<db>
            data_dir = os.path.join(project_root, 'data')
            os.makedirs(data_dir, exist_ok=True)
            preferred = os.path.join(data_dir, db_path)
            # Legacy candidates
            legacy_root = os.path.join(project_root, db_path)
            legacy_app_data = os.path.join(app_dir, 'data', db_path)
            legacy_app_root = os.path.join(app_dir, db_path)

            # If preferred exists, always use it
            if os.path.exists(preferred):
                db_path = preferred
            # Otherwise, adopt the first legacy that exists and migrate to preferred
            elif os.path.exists(legacy_root):
                db_path = legacy_root
                try:
                    import shutil
                    shutil.copy2(legacy_root, preferred)
                    db_path = preferred
                except Exception:
                    pass
            elif os.path.exists(legacy_app_data):
                db_path = legacy_app_data
                try:
                    import shutil
                    shutil.copy2(legacy_app_data, preferred)
                    db_path = preferred
                except Exception:
                    pass
            elif os.path.exists(legacy_app_root):
                db_path = legacy_app_root
                try:
                    import shutil
                    shutil.copy2(legacy_app_root, preferred)
                    db_path = preferred
                except Exception:
                    pass
            else:
                db_path = preferred
        self.db_path = db_path
        self._ensure_backup_dir()
        self.init_database()

    def _ensure_backup_dir(self):
        import os
        bdir = os.path.join(os.path.dirname(self.db_path), 'backups')
        os.makedirs(bdir, exist_ok=True)
        self._backup_dir = bdir
    
    def init_database(self):
        """Initialize database with all required tables."""
        # Safeguard: if DB exists, make a lightweight backup once per day
        import os, shutil, datetime
        if os.path.exists(self.db_path):
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')
            backup_path = os.path.join(self._backup_dir, f'boat_tracking_{stamp}.sqlite')
            if not os.path.exists(backup_path):
                try:
                    shutil.copy2(self.db_path, backup_path)
                except Exception:
                    pass
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Boats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS boats (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    class_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    notes TEXT
                )
            """)
            
            # Beacons table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS beacons (
                    id TEXT PRIMARY KEY,
                    mac_address TEXT UNIQUE NOT NULL,
                    name TEXT,
                    status TEXT NOT NULL DEFAULT 'unclaimed',
                    last_seen TIMESTAMP,
                    last_rssi INTEGER,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    notes TEXT
                )
            """)
            
            # Boat-Beacon assignments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS boat_beacon_assignments (
                    id TEXT PRIMARY KEY,
                    boat_id TEXT NOT NULL,
                    beacon_id TEXT NOT NULL,
                    assigned_at TIMESTAMP NOT NULL,
                    unassigned_at TIMESTAMP,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    notes TEXT,
                    FOREIGN KEY (boat_id) REFERENCES boats (id),
                    FOREIGN KEY (beacon_id) REFERENCES beacons (id),
                    UNIQUE(boat_id, beacon_id, is_active) ON CONFLICT REPLACE
                )
            """)
            
            # Detections table for analytics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id TEXT PRIMARY KEY,
                    scanner_id TEXT NOT NULL,
                    beacon_id TEXT NOT NULL,
                    rssi INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    state TEXT NOT NULL,
                    FOREIGN KEY (beacon_id) REFERENCES beacons (id)
                )
            """)
            
            # Scanners table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scanners (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            
            # Beacon states table for FSM
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS beacon_states (
                    beacon_id TEXT PRIMARY KEY,
                    current_state TEXT NOT NULL DEFAULT 'idle',
                    last_outer_seen TIMESTAMP,
                    last_inner_seen TIMESTAMP,
                    entry_timestamp TIMESTAMP,
                    exit_timestamp TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (beacon_id) REFERENCES beacons (id)
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_beacons_mac ON beacons (mac_address)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_boat ON boat_beacon_assignments (boat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_beacon ON boat_beacon_assignments (beacon_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_active ON boat_beacon_assignments (is_active)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections (timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_beacon ON detections (beacon_id)")
            
            conn.commit()

            # --- Non-destructive evolutions: add columns/tables if missing ---
            # Add operational status columns on boats (op_status, status_updated_at)
            try:
                cursor.execute("PRAGMA table_info(boats)")
                cols = {row[1] for row in cursor.fetchall()}
                if 'op_status' not in cols:
                    cursor.execute("ALTER TABLE boats ADD COLUMN op_status TEXT NOT NULL DEFAULT 'ACTIVE'")
                if 'status_updated_at' not in cols:
                    cursor.execute("ALTER TABLE boats ADD COLUMN status_updated_at TIMESTAMP")
            except Exception:
                pass

            # Boat trips table for tracking water time and usage analytics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS boat_trips (
                    id TEXT PRIMARY KEY,
                    boat_id TEXT NOT NULL,
                    beacon_id TEXT NOT NULL,
                    exit_time TIMESTAMP NOT NULL,
                    entry_time TIMESTAMP,
                    duration_minutes INTEGER,
                    trip_date DATE NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (boat_id) REFERENCES boats (id),
                    FOREIGN KEY (beacon_id) REFERENCES beacons (id)
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_boat ON boat_trips (boat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_date ON boat_trips (trip_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_boat_date ON boat_trips (boat_id, trip_date)")
            
            # Shed events table (append-only event log)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shed_events (
                    id TEXT PRIMARY KEY,
                    boat_id TEXT NOT NULL,
                    beacon_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('IN_SHED', 'OUT_SHED')),
                    ts_utc TIMESTAMP NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (boat_id) REFERENCES boats (id),
                    FOREIGN KEY (beacon_id) REFERENCES beacons (id)
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_boat ON shed_events (boat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON shed_events (ts_utc)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_boat_ts ON shed_events (boat_id, ts_utc)")
            
            # Audit log for administrative actions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    occurred_at TIMESTAMP NOT NULL,
                    actor TEXT,
                    action TEXT NOT NULL,
                    entity TEXT,
                    entity_id TEXT,
                    details TEXT
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log (occurred_at)")

            conn.commit()
    
    def get_connection(self):
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    # Boat operations
    def create_boat(self, boat_id: str, name: str, class_type: str, notes: str = None) -> Boat:
        """Create a new boat."""
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO boats (id, name, class_type, status, created_at, updated_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (boat_id, name, class_type, BoatStatus.IN_HARBOR.value, now, now, notes))
            conn.commit()
        
        return Boat(boat_id, name, class_type, BoatStatus.IN_HARBOR, now, now, notes)
    
    def get_boat(self, boat_id: str) -> Optional[Boat]:
        """Get boat by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM boats WHERE id = ?", (boat_id,))
            row = cursor.fetchone()
            if row:
                # Parse datetime strings
                created_at = datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4]
                updated_at = datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5]
                status_updated_at = None
                try:
                    status_updated_at = datetime.fromisoformat(row[8]) if len(row) > 8 and isinstance(row[8], str) else (row[8] if len(row) > 8 else None)
                except Exception:
                    status_updated_at = row[8] if len(row) > 8 else None
                
                return Boat(
                    id=row[0], name=row[1], class_type=row[2],
                    status=BoatStatus(row[3]), created_at=created_at, updated_at=updated_at, notes=row[6],
                    op_status=(row[7] if len(row) > 7 and row[7] else 'ACTIVE'), status_updated_at=status_updated_at
                )
        return None
    
    def get_all_boats(self) -> List[Boat]:
        """Get all boats."""
        boats = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM boats ORDER BY name")
            for row in cursor.fetchall():
                # Parse datetime strings
                created_at = datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4]
                updated_at = datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5]
                status_updated_at = None
                try:
                    status_updated_at = datetime.fromisoformat(row[8]) if len(row) > 8 and isinstance(row[8], str) else (row[8] if len(row) > 8 else None)
                except Exception:
                    status_updated_at = row[8] if len(row) > 8 else None
                
                boats.append(Boat(
                    id=row[0], name=row[1], class_type=row[2],
                    status=BoatStatus(row[3]), created_at=created_at, updated_at=updated_at, notes=row[6],
                    op_status=(row[7] if len(row) > 7 and row[7] else 'ACTIVE'), status_updated_at=status_updated_at
                ))
        return boats

    # -------- Operational status & search helpers (non-breaking) --------
    def set_boat_op_status(self, boat_id: str, op_status: str) -> None:
        """Set operational status (ACTIVE|MAINTENANCE|RETIRED) on boats.op_status."""
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE boats SET op_status = ?, status_updated_at = ? WHERE id = ?",
                (op_status, now, boat_id),
            )
            conn.commit()
        self._audit('system', 'set_op_status', 'boat', boat_id, json.dumps({'op_status': op_status}))

    def search_boats_by_name(self, query: str, limit: int = 20) -> List[Dict]:
        q = f"%{query.lower()}%"
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, name, class_type FROM boats WHERE LOWER(name) LIKE ? ORDER BY name LIMIT ?",
                (q, limit),
            )
            rows = c.fetchall()
        return [{ 'id': r[0], 'name': r[1], 'class_type': r[2] } for r in rows]

    def get_current_beacon_for_boat(self, boat_id: str) -> Optional[Beacon]:
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT be.* FROM beacons be
                JOIN boat_beacon_assignments ba ON be.id = ba.beacon_id
                WHERE ba.boat_id = ? AND ba.is_active = 1
                """,
                (boat_id,),
            )
            row = c.fetchone()
            if not row:
                return None
            return Beacon(
                id=row[0], mac_address=row[1], name=row[2], status=BeaconStatus(row[3]),
                last_seen=row[4], last_rssi=row[5], created_at=row[6], updated_at=row[7], notes=row[8]
            )

    def replace_beacon_for_boat(self, boat_id: str, new_mac: str) -> Beacon:
        """Transactional: deactivate current assignment and link a beacon with given MAC (create if needed)."""
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            c = conn.cursor()
            # Find or create beacon by MAC
            c.execute("SELECT * FROM beacons WHERE mac_address = ?", (new_mac,))
            row = c.fetchone()
            if row:
                beacon_id = row[0]
            else:
                beacon_id = f"BC{int(now.timestamp() * 1000)}"
                c.execute(
                    "INSERT INTO beacons (id, mac_address, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (beacon_id, new_mac, BeaconStatus.UNCLAIMED.value, now, now),
                )
            # Close current assignment
            c.execute(
                "UPDATE boat_beacon_assignments SET is_active = 0, unassigned_at = ? WHERE boat_id = ? AND is_active = 1",
                (now, boat_id),
            )
            # Create new assignment
            assignment_id = f"AS{int(now.timestamp() * 1000)}"
            c.execute(
                "INSERT INTO boat_beacon_assignments (id, boat_id, beacon_id, assigned_at, is_active) VALUES (?, ?, ?, ?, 1)",
                (assignment_id, boat_id, beacon_id, now),
            )
            # Ensure beacon marked assigned
            c.execute(
                "UPDATE beacons SET status = ?, updated_at = ? WHERE id = ?",
                (BeaconStatus.ASSIGNED.value, now, beacon_id),
            )
            conn.commit()

        self._audit('system', 'replace_beacon', 'boat', boat_id, json.dumps({'new_mac': new_mac}))
        return self.get_beacon_by_mac(new_mac)

    def get_beacon_history_by_mac(self, mac: str) -> List[Dict]:
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT ba.id, ba.boat_id, ba.beacon_id, ba.assigned_at, ba.unassigned_at, ba.is_active
                FROM boat_beacon_assignments ba
                JOIN beacons be ON be.id = ba.beacon_id
                WHERE be.mac_address = ?
                ORDER BY ba.assigned_at DESC
                """,
                (mac,),
            )
            rows = c.fetchall()
        return [
            {
                'assignment_id': r[0],
                'boat_id': r[1],
                'beacon_id': r[2],
                'valid_from': r[3],
                'valid_to': r[4],
                'is_active': bool(r[5]),
            }
            for r in rows
        ]

    def _audit(self, actor: str, action: str, entity: str, entity_id: str, details: str = None) -> None:
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO audit_log (id, occurred_at, actor, action, entity, entity_id, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"AU{int(now.timestamp() * 1000)}", now, actor, action, entity, entity_id, details),
            )
            conn.commit()
    
    def update_boat_status(self, boat_id: str, status: BoatStatus):
        """Update boat status."""
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE boats SET status = ?, updated_at = ? WHERE id = ?
            """, (status.value, now, boat_id))
            conn.commit()

    def update_boat(self, boat_id: str, name: Optional[str] = None,
                    class_type: Optional[str] = None, notes: Optional[str] = None) -> None:
        """Update boat metadata (name, class, notes). Ignores None fields."""
        now = datetime.now(timezone.utc)
        sets = []
        args = []
        if name is not None:
            sets.append("name = ?")
            args.append(name)
        if class_type is not None:
            sets.append("class_type = ?")
            args.append(class_type)
        if notes is not None:
            sets.append("notes = ?")
            args.append(notes)
        if not sets:
            return
        sets.append("updated_at = ?")
        args.append(now)
        args.append(boat_id)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE boats SET {' , '.join(sets)} WHERE id = ?", args)
            conn.commit()
    
    # Beacon operations
    def upsert_beacon(self, mac_address: str, name: str = None, rssi: int = None) -> Beacon:
        """Upsert beacon (create if not exists, update if exists)."""
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if beacon exists
            cursor.execute("SELECT * FROM beacons WHERE mac_address = ?", (mac_address,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing beacon
                beacon_id = existing[0]
                cursor.execute("""
                    UPDATE beacons SET last_seen = ?, last_rssi = ?, updated_at = ?
                    WHERE mac_address = ?
                """, (now, rssi, now, mac_address))
            else:
                # Create new beacon
                beacon_id = f"BC{int(now.timestamp() * 1000)}"
                cursor.execute(
                    """
                    INSERT INTO beacons (id, mac_address, name, status, last_seen, last_rssi, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        beacon_id,
                        mac_address,
                        name,
                        BeaconStatus.UNCLAIMED.value,
                        now,                # last_seen - set to now on first detection
                        rssi,               # last_rssi
                        now,
                        now,
                    ),
                )
            
            conn.commit()
            
            # Return updated beacon
            cursor.execute("SELECT * FROM beacons WHERE mac_address = ?", (mac_address,))
            row = cursor.fetchone()
            return Beacon(
                id=row[0], mac_address=row[1], name=row[2], status=BeaconStatus(row[3]),
                last_seen=row[4], last_rssi=row[5], created_at=row[6], updated_at=row[7], notes=row[8]
            )
    
    def get_beacon_by_mac(self, mac_address: str) -> Optional[Beacon]:
        """Get beacon by MAC address."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM beacons WHERE mac_address = ?", (mac_address,))
            row = cursor.fetchone()
            if row:
                # Parse datetime strings and ensure timezone awareness
                last_seen = row[4]
                if last_seen and isinstance(last_seen, str):
                    last_seen = datetime.fromisoformat(last_seen)
                if last_seen and last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                
                created_at = row[6]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                updated_at = row[7]
                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at)
                if updated_at and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                
                return Beacon(
                    id=row[0], mac_address=row[1], name=row[2], status=BeaconStatus(row[3]),
                    last_seen=last_seen, last_rssi=row[5], created_at=created_at, updated_at=updated_at, notes=row[8]
                )
        return None
    
    def get_all_beacons(self) -> List[Beacon]:
        """Get all beacons."""
        beacons = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM beacons ORDER BY mac_address")
            for row in cursor.fetchall():
                # Parse datetime strings and ensure timezone awareness
                last_seen = row[4]
                if last_seen and isinstance(last_seen, str):
                    last_seen = datetime.fromisoformat(last_seen)
                if last_seen and last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                
                created_at = row[6]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                updated_at = row[7]
                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at)
                if updated_at and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                
                beacons.append(Beacon(
                    id=row[0], mac_address=row[1], name=row[2], status=BeaconStatus(row[3]),
                    last_seen=last_seen, last_rssi=row[5], created_at=created_at, updated_at=updated_at, notes=row[8]
                ))
        return beacons
    
    def assign_beacon_to_boat(self, beacon_id: str, boat_id: str, notes: str = None) -> bool:
        """Assign beacon to boat. Returns True if successful."""
        now = datetime.now(timezone.utc)
        assignment_id = f"AS{int(now.timestamp() * 1000)}"
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if beacon is already assigned
            cursor.execute("""
                SELECT id FROM boat_beacon_assignments 
                WHERE beacon_id = ? AND is_active = 1
            """, (beacon_id,))
            if cursor.fetchone():
                return False  # Beacon already assigned
            
            # Check if boat already has an active beacon
            cursor.execute("""
                SELECT id FROM boat_beacon_assignments 
                WHERE boat_id = ? AND is_active = 1
            """, (boat_id,))
            if cursor.fetchone():
                return False  # Boat already has active beacon
            
            # Create assignment
            cursor.execute("""
                INSERT INTO boat_beacon_assignments 
                (id, boat_id, beacon_id, assigned_at, is_active, notes)
                VALUES (?, ?, ?, ?, 1, ?)
            """, (assignment_id, boat_id, beacon_id, now, notes))
            
            # Update beacon status
            cursor.execute("""
                UPDATE beacons SET status = ?, updated_at = ? WHERE id = ?
            """, (BeaconStatus.ASSIGNED.value, now, beacon_id))
            
            conn.commit()
            return True
    
    def unassign_beacon(self, beacon_id: str) -> bool:
        """Unassign beacon from boat."""
        now = datetime.now(timezone.utc)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Deactivate assignment
            cursor.execute("""
                UPDATE boat_beacon_assignments 
                SET is_active = 0, unassigned_at = ?
                WHERE beacon_id = ? AND is_active = 1
            """, (now, beacon_id))
            
            if cursor.rowcount == 0:
                return False  # No active assignment found
            
            # Update beacon status
            cursor.execute("""
                UPDATE beacons SET status = ?, updated_at = ? WHERE id = ?
            """, (BeaconStatus.UNCLAIMED.value, now, beacon_id))
            
            conn.commit()
            return True
    
    def get_boat_by_beacon(self, beacon_id: str) -> Optional[Boat]:
        """Get boat assigned to beacon."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.* FROM boats b
                JOIN boat_beacon_assignments ba ON b.id = ba.boat_id
                WHERE ba.beacon_id = ? AND ba.is_active = 1
            """, (beacon_id,))
            row = cursor.fetchone()
            if row:
                return Boat(
                    id=row[0], name=row[1], class_type=row[2],
                    status=BoatStatus(row[3]), created_at=row[4], updated_at=row[5], notes=row[6]
                )
        return None
    
    def get_beacon_by_boat(self, boat_id: str) -> Optional[Beacon]:
        """Get beacon assigned to boat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT be.* FROM beacons be
                JOIN boat_beacon_assignments ba ON be.id = ba.beacon_id
                WHERE ba.boat_id = ? AND ba.is_active = 1
            """, (boat_id,))
            row = cursor.fetchone()
            if row:
                # Parse datetime strings and ensure timezone awareness
                last_seen = row[4]
                if last_seen and isinstance(last_seen, str):
                    last_seen = datetime.fromisoformat(last_seen)
                if last_seen and last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                
                created_at = row[6]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                updated_at = row[7]
                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at)
                if updated_at and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                return Beacon(
                    id=row[0], mac_address=row[1], name=row[2], status=BeaconStatus(row[3]),
                    last_seen=last_seen, last_rssi=row[5], created_at=created_at, updated_at=updated_at, notes=row[8]
                )
        return None
    
    # Detection operations
    def log_detection(self, scanner_id: str, beacon_id: str, rssi: int, state: DetectionState) -> str:
        """Log a detection event."""
        detection_id = f"DT{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        now = datetime.now(timezone.utc)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO detections (id, scanner_id, beacon_id, rssi, timestamp, state)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (detection_id, scanner_id, beacon_id, rssi, now, state.value))
            conn.commit()
        
        return detection_id

    def insert_detection(self, scanner_id: str, beacon_id: str, rssi: int, state: DetectionState, timestamp: datetime) -> str:
        """Insert a detection event at a specific timestamp (for backfilling history)."""
        detection_id = f"DT{int(timestamp.timestamp() * 1000)}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO detections (id, scanner_id, beacon_id, rssi, timestamp, state)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (detection_id, scanner_id, beacon_id, rssi, timestamp, state.value),
            )
            conn.commit()
        return detection_id

    # Scanner helpers
    def upsert_scanner(self, scanner_id: str, name: str, location: str, is_active: bool = True) -> None:
        """Create or update a scanner row."""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM scanners WHERE id = ?", (scanner_id,))
            now = datetime.now(timezone.utc)
            if c.fetchone():
                c.execute(
                    "UPDATE scanners SET name = ?, location = ?, is_active = ? WHERE id = ?",
                    (name, location, 1 if is_active else 0, scanner_id),
                )
            else:
                c.execute(
                    "INSERT INTO scanners (id, name, location, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                    (scanner_id, name, location, 1 if is_active else 0, now),
                )
            conn.commit()

    def get_active_assignments(self) -> List[Tuple[str, str]]:
        """Return list of (boat_id, beacon_id) for active assignments."""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT boat_id, beacon_id FROM boat_beacon_assignments WHERE is_active = 1
                """
            )
            return [(r[0], r[1]) for r in c.fetchall()]
    
    def update_beacon_state(self, beacon_id: str, state: DetectionState, 
                          last_outer_seen: datetime = None, last_inner_seen: datetime = None,
                          entry_timestamp: datetime = None, exit_timestamp: datetime = None):
        """Update beacon FSM state."""
        now = datetime.now(timezone.utc)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO beacon_states 
                (beacon_id, current_state, last_outer_seen, last_inner_seen, 
                 entry_timestamp, exit_timestamp, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (beacon_id, state.value, last_outer_seen, last_inner_seen, 
                  entry_timestamp, exit_timestamp, now))
            conn.commit()
    
    def get_beacon_state(self, beacon_id: str) -> Optional[DetectionState]:
        """Get current beacon state."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_state FROM beacon_states WHERE beacon_id = ?", (beacon_id,))
            row = cursor.fetchone()
            if row:
                return DetectionState(row[0])
        return DetectionState.IDLE
    
    def get_boats_in_harbor(self) -> List[Tuple[Boat, Beacon]]:
        """Get all boats currently in harbor."""
        boats_in_harbor = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.*, be.* FROM boats b
                JOIN boat_beacon_assignments ba ON b.id = ba.boat_id
                JOIN beacons be ON ba.beacon_id = be.id
                JOIN beacon_states bs ON be.id = bs.beacon_id
                WHERE ba.is_active = 1 AND bs.current_state = 'entered'
            """)
            for row in cursor.fetchall():
                boat = Boat(
                    id=row[0], name=row[1], class_type=row[2],
                    status=BoatStatus(row[3]), created_at=row[4], updated_at=row[5], notes=row[6]
                )
                beacon = Beacon(
                    id=row[7], mac_address=row[8], name=row[9], status=BeaconStatus(row[10]),
                    last_seen=row[11], last_rssi=row[12], created_at=row[13], updated_at=row[14], notes=row[15]
                )
                boats_in_harbor.append((boat, beacon))
        return boats_in_harbor

    # Administrative operations
    # -------- Boat Trip Tracking --------
    def start_trip(self, boat_id: str, beacon_id: str, exit_time: datetime) -> str:
        """Start a new trip when boat exits to water."""
        import uuid
        trip_id = str(uuid.uuid4())
        trip_date = exit_time.date()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO boat_trips 
                (id, boat_id, beacon_id, exit_time, trip_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (trip_id, boat_id, beacon_id, exit_time, trip_date, exit_time))
            conn.commit()
        
        return trip_id
    
    def end_trip(self, boat_id: str, beacon_id: str, entry_time: datetime):
        """End the most recent trip when boat returns."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Find the most recent open trip (no entry_time) for this boat/beacon
            cursor.execute("""
                SELECT id, exit_time FROM boat_trips
                WHERE boat_id = ? AND beacon_id = ? AND entry_time IS NULL
                ORDER BY exit_time DESC
                LIMIT 1
            """, (boat_id, beacon_id))
            
            row = cursor.fetchone()
            if row:
                trip_id, exit_time = row
                if isinstance(exit_time, str):
                    exit_time = datetime.fromisoformat(exit_time)
                
                # Calculate duration in minutes
                duration = int((entry_time - exit_time).total_seconds() / 60)
                
                cursor.execute("""
                    UPDATE boat_trips
                    SET entry_time = ?, duration_minutes = ?
                    WHERE id = ?
                """, (entry_time, duration, trip_id))
                conn.commit()
                
                return trip_id, duration
        
        return None, 0
    
    def get_boat_water_time_today(self, boat_id: str) -> int:
        """Get total minutes on water today for a boat."""
        today = datetime.now(timezone.utc).date()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(duration_minutes) FROM boat_trips
                WHERE boat_id = ? AND trip_date = ? AND duration_minutes IS NOT NULL
            """, (boat_id, today))
            
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0
    
    def get_boat_trip_history(self, boat_id: str, days: int = 30) -> List[Dict]:
        """Get trip history for a boat."""
        cutoff_date = (datetime.now(timezone.utc) - __import__('datetime').timedelta(days=days)).date()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, exit_time, entry_time, duration_minutes, trip_date
                FROM boat_trips
                WHERE boat_id = ? AND trip_date >= ?
                ORDER BY exit_time DESC
            """, (boat_id, cutoff_date))
            
            trips = []
            for row in cursor.fetchall():
                trips.append({
                    'id': row[0],
                    'exit_time': row[1],
                    'entry_time': row[2],
                    'duration_minutes': row[3],
                    'trip_date': row[4]
                })
            
            return trips
    
    def get_boat_usage_stats(self, boat_id: str = None) -> List[Dict]:
        """Get usage statistics for boat(s) - total trips and hours."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if boat_id:
                query = """
                    SELECT 
                        b.id, b.name, b.class_type,
                        COUNT(t.id) as total_trips,
                        COALESCE(SUM(t.duration_minutes), 0) as total_minutes
                    FROM boats b
                    LEFT JOIN boat_trips t ON b.id = t.boat_id
                    WHERE b.id = ?
                    GROUP BY b.id
                """
                cursor.execute(query, (boat_id,))
            else:
                query = """
                    SELECT 
                        b.id, b.name, b.class_type,
                        COUNT(t.id) as total_trips,
                        COALESCE(SUM(t.duration_minutes), 0) as total_minutes
                    FROM boats b
                    LEFT JOIN boat_trips t ON b.id = t.boat_id
                    GROUP BY b.id
                    ORDER BY total_minutes DESC
                """
                cursor.execute(query)
            
            stats = []
            for row in cursor.fetchall():
                total_hours = row[4] / 60.0 if row[4] else 0
                stats.append({
                    'boat_id': row[0],
                    'boat_name': row[1],
                    'class_type': row[2],
                    'total_trips': row[3],
                    'total_minutes': row[4],
                    'total_hours': round(total_hours, 2)
                })
            
            return stats

    def reset_all(self) -> None:
        """Reset all beacon assignments and states.

        - Deactivate all active assignments
        - Mark all beacons as UNCLAIMED
        - Clear beacon FSM states
        - Delete all boats and detections
        - Clear all historical data for a fresh start
        """
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Deactivate assignments
            cursor.execute(
                """
                UPDATE boat_beacon_assignments
                SET is_active = 0, unassigned_at = ?
                WHERE is_active = 1
                """,
                (now,)
            )
            # Mark all beacons as unclaimed
            cursor.execute(
                """
                UPDATE beacons
                SET status = ?, last_seen = NULL, last_rssi = NULL, updated_at = ?
                """,
                (BeaconStatus.UNCLAIMED.value, now)
            )
            # Delete all boats to completely reset the system
            cursor.execute("DELETE FROM boats")
            # Clear FSM states
            cursor.execute("DELETE FROM beacon_states")
            # Clear detections history to avoid visual clutter
            cursor.execute("DELETE FROM detections")
            # Clear all assignments (both active and inactive)
            cursor.execute("DELETE FROM boat_beacon_assignments")
            conn.commit()

    # Additional helpers
    def update_beacon(self, beacon_id: str, name: Optional[str] = None, notes: Optional[str] = None):
        """Update beacon attributes such as name and notes."""
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if name is not None and notes is not None:
                cursor.execute("""
                    UPDATE beacons SET name = ?, notes = ?, updated_at = ? WHERE id = ?
                """, (name, notes, now, beacon_id))
            elif name is not None:
                cursor.execute("""
                    UPDATE beacons SET name = ?, updated_at = ? WHERE id = ?
                """, (name, now, beacon_id))
            elif notes is not None:
                cursor.execute("""
                    UPDATE beacons SET notes = ?, updated_at = ? WHERE id = ?
                """, (notes, now, beacon_id))
            conn.commit()
    
    # ========== EVENT-BASED TIMESTAMP SYSTEM ==========
    
    def log_shed_event(self, boat_id: str, beacon_id: str, event_type: str, ts_utc: datetime = None) -> str:
        """
        Log a shed event (IN_SHED or OUT_SHED) to append-only events table.
        
        Args:
            boat_id: Boat ID
            beacon_id: Beacon ID  
            event_type: 'IN_SHED' or 'OUT_SHED'
            ts_utc: Event timestamp in UTC (defaults to now)
            
        Returns:
            Event ID
        """
        if ts_utc is None:
            ts_utc = datetime.now(timezone.utc)
        
        event_id = f"EV{int(ts_utc.timestamp() * 1000)}"
        created_at = datetime.now(timezone.utc)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO shed_events (id, boat_id, beacon_id, event_type, ts_utc, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_id, boat_id, beacon_id, event_type, ts_utc, created_at))
            conn.commit()
        
        return event_id
    
    def get_events_for_boat(self, boat_id: str, date_local: datetime.date = None, timezone_str: str = 'Australia/Canberra') -> List[dict]:
        """
        Get events for a boat on a specific local date.
        
        Args:
            boat_id: Boat ID
            date_local: Local date (defaults to today in club timezone)
            timezone_str: Club timezone
            
        Returns:
            List of events: [{'id', 'event_type', 'ts_utc', 'ts_local'}, ...]
        """
        try:
            from zoneinfo import ZoneInfo
            club_tz = ZoneInfo(timezone_str)
        except:
            club_tz = timezone.utc
        
        if date_local is None:
            date_local = datetime.now(club_tz).date()
        
        # Get start and end of day in UTC
        start_local = datetime.combine(date_local, datetime.min.time()).replace(tzinfo=club_tz)
        end_local = datetime.combine(date_local, datetime.max.time()).replace(tzinfo=club_tz)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, event_type, ts_utc
                FROM shed_events
                WHERE boat_id = ? AND ts_utc >= ? AND ts_utc <= ?
                ORDER BY ts_utc ASC
            """, (boat_id, start_utc, end_utc))
            
            rows = cursor.fetchall()
            events = []
            for row in rows:
                ts_utc_val = datetime.fromisoformat(row[2]) if isinstance(row[2], str) else row[2]
                if ts_utc_val.tzinfo is None:
                    ts_utc_val = ts_utc_val.replace(tzinfo=timezone.utc)
                
                ts_local = ts_utc_val.astimezone(club_tz)
                
                events.append({
                    'id': row[0],
                    'event_type': row[1],
                    'ts_utc': ts_utc_val,
                    'ts_local': ts_local
                })
            
            return events
    
    def summarize_today(self, boat_id: str, timezone_str: str = 'Australia/Canberra') -> dict:
        """
        Compute daily summary for a boat based on events + current beacon presence.
        
        This implements the deterministic algorithm:
        - status: Current presence overrides stale DB status
        - on_water_ts_local: First OUT today (or yesterday carry-over if still out)
        - in_shed_ts_local: Latest IN today
        
        Args:
            boat_id: Boat ID
            timezone_str: Club timezone
            
        Returns:
            {
                'status': 'IN_SHED' or 'ON_WATER',
                'last_seen_utc': datetime or None,
                'on_water_ts_local': datetime or None,
                'in_shed_ts_local': datetime or None,
                'day_key': date
            }
        """
        try:
            from zoneinfo import ZoneInfo
            club_tz = ZoneInfo(timezone_str)
        except:
            club_tz = timezone.utc
        
        now_local = datetime.now(club_tz)
        today = now_local.date()
        yesterday = today - timedelta(days=1)
        
        # Get events for today and yesterday
        ev_today = self.get_events_for_boat(boat_id, today, timezone_str)
        ev_yest = self.get_events_for_boat(boat_id, yesterday, timezone_str)
        
        # Get current beacon presence
        beacon = self.get_beacon_by_boat(boat_id)
        last_seen_utc = None
        present_now = False
        
        if beacon and beacon.last_seen:
            last_seen_utc = beacon.last_seen if isinstance(beacon.last_seen, datetime) else datetime.fromisoformat(beacon.last_seen)
            if last_seen_utc.tzinfo is None:
                last_seen_utc = last_seen_utc.replace(tzinfo=timezone.utc)
            
            # Beacon is "present" if seen within last 15 seconds
            age_seconds = (datetime.now(timezone.utc) - last_seen_utc).total_seconds()
            present_now = age_seconds <= 15
        
        # Baseline status: presence wins over stale DB status
        status = 'IN_SHED' if present_now else 'ON_WATER'
        
        # ---- on_water_ts_local: FIRST OUT today (always show if exists) ----
        out_today = next((e for e in ev_today if e['event_type'] == 'OUT_SHED'), None)
        on_water_ts_local = out_today['ts_local'] if out_today else None
        
        # If no OUT today but boat currently ON_WATER, carry over yesterday's last OUT
        if not on_water_ts_local and status == 'ON_WATER':
            any_in_today = any(e['event_type'] == 'IN_SHED' for e in ev_today)
            if not any_in_today:  # No return today
                last_out_yest = next((e for e in reversed(ev_yest) if e['event_type'] == 'OUT_SHED'), None)
                on_water_ts_local = last_out_yest['ts_local'] if last_out_yest else None
        
        # ---- in_shed_ts_local: LATEST IN today (always show if exists) ----
        ins_today = next((e for e in reversed(ev_today) if e['event_type'] == 'IN_SHED'), None)
        in_shed_ts_local = ins_today['ts_local'] if ins_today else None
        
        return {
            'status': status,
            'last_seen_utc': last_seen_utc,
            'on_water_ts_local': on_water_ts_local,
            'in_shed_ts_local': in_shed_ts_local,
            'day_key': today
        }
