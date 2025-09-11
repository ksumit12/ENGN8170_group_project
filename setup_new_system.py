#!/usr/bin/env python3
"""
Setup script for the new multi-beacon boat tracking system
Handles database initialization and sample data creation
"""

import sys
import os
from database_models import DatabaseManager, Boat, Beacon, BoatBeaconAssignment
from datetime import datetime, timezone

def setup_database(db_path: str = "boat_tracking.db"):
    """Initialize database with sample data."""
    print("Setting up database...")
    
    # Initialize database
    db = DatabaseManager(db_path)
    print("Database initialized successfully")
    
    # Create sample boats
    sample_boats = [
        ("BT0001", "Rowing Club 1x", "1x", "Primary single scull"),
        ("BT0002", "Rowing Club 2-", "2-", "Pair without coxswain"),
        ("BT0003", "Rowing Club 4x", "4x", "Quad scull"),
        ("BT0004", "Rowing Club 8+", "8+", "Eight with coxswain"),
        ("BT0005", "Training 1x", "1x", "Training single scull"),
    ]
    
    print("Creating sample boats...")
    for boat_id, name, class_type, notes in sample_boats:
        try:
            boat = db.create_boat(boat_id, name, class_type, notes)
            print(f"  Created boat: {boat.name} ({boat.id})")
        except Exception as e:
            print(f"  Error creating boat {name}: {e}")
    
    # Create sample beacons (these would be detected automatically in real usage)
    sample_beacons = [
        ("AA:BB:CC:DD:EE:01", "Beacon-01", -45),
        ("AA:BB:CC:DD:EE:02", "Beacon-02", -52),
        ("AA:BB:CC:DD:EE:03", "Beacon-03", -38),
        ("AA:BB:CC:DD:EE:04", "Beacon-04", -61),
        ("AA:BB:CC:DD:EE:05", "Beacon-05", -49),
    ]
    
    print("Creating sample beacons...")
    for mac, name, rssi in sample_beacons:
        try:
            beacon = db.upsert_beacon(mac, name, rssi)
            print(f"  Created beacon: {beacon.mac_address} ({beacon.id})")
        except Exception as e:
            print(f"  Error creating beacon {mac}: {e}")
    
    # Assign some beacons to boats
    print("Assigning beacons to boats...")
    boats = db.get_all_boats()
    beacons = db.get_all_beacons()
    
    assignments = [
        (beacons[0].id, boats[0].id, "Primary assignment"),
        (beacons[1].id, boats[1].id, "Pair boat beacon"),
        (beacons[2].id, boats[2].id, "Quad scull beacon"),
    ]
    
    for beacon_id, boat_id, notes in assignments:
        try:
            success = db.assign_beacon_to_boat(beacon_id, boat_id, notes)
            if success:
                print(f"  Assigned {beacon_id} to {boat_id}")
            else:
                print(f"  Failed to assign {beacon_id} to {boat_id}")
        except Exception as e:
            print(f"  Error assigning beacon: {e}")
    
    print("\nDatabase setup complete!")
    print(f"Database file: {db_path}")
    print(f"Created {len(boats)} boats and {len(beacons)} beacons")
    
    return db

def show_system_info():
    """Show system information and usage instructions."""
    print("\n" + "="*60)
    print("BOAT TRACKING SYSTEM - SETUP COMPLETE")
    print("="*60)
    print()
    print("SYSTEM COMPONENTS:")
    print("  1. database_models.py     - Database schema and operations")
    print("  2. ble_scanner.py         - Multi-beacon BLE scanner")
    print("  3. entry_exit_fsm.py      - Entry/exit state machine")
    print("  4. api_server.py          - REST API server")
    print("  5. boat_tracking_system.py - Main orchestrator")
    print()
    print("USAGE:")
    print("  1. Start the system:")
    print("     python3 boat_tracking_system.py")
    print()
    print("  2. Start individual scanners:")
    print("     python3 ble_scanner.py --scanner-id gate-outer --server-url http://localhost:8000")
    print("     python3 ble_scanner.py --scanner-id gate-inner --server-url http://localhost:8000")
    print()
    print("  3. Start API server only:")
    print("     python3 api_server.py --port 8000")
    print()
    print("WEB INTERFACES:")
    print("  - Main Dashboard: http://localhost:5000")
    print("  - API Server: http://localhost:8000")
    print("  - Health Check: http://localhost:8000/health")
    print()
    print("API ENDPOINTS:")
    print("  - GET  /api/v1/boats           - List all boats")
    print("  - POST /api/v1/boats           - Create new boat")
    print("  - GET  /api/v1/beacons         - List all beacons")
    print("  - POST /api/v1/detections      - Submit detections")
    print("  - GET  /api/v1/presence        - Get harbor presence")
    print()
    print("CONFIGURATION:")
    print("  - Database: boat_tracking.db")
    print("  - API Port: 8000")
    print("  - Web Port: 5000")
    print("  - Scanner IDs: gate-outer, gate-inner")
    print()
    print("NEXT STEPS:")
    print("  1. Install dependencies: pip install -r requirements_new.txt")
    print("  2. Start the system: python3 boat_tracking_system.py")
    print("  3. Place beacons near scanners to auto-detect them")
    print("  4. Use web dashboard to assign beacons to boats")
    print("  5. Monitor boat entry/exit in real-time")
    print()
    print("="*60)

def main():
    """Main setup function."""
    print("Setting up Multi-Beacon Boat Tracking System...")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8+ required")
        sys.exit(1)
    
    # Setup database
    db_path = "boat_tracking.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    try:
        db = setup_database(db_path)
        show_system_info()
        
    except Exception as e:
        print(f"Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

