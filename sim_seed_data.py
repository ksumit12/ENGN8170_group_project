#!/usr/bin/env python3
import random
import argparse
from datetime import datetime, timedelta, timezone

from app.database_models import DatabaseManager, DetectionState, BeaconStatus, BoatStatus


def generate_boat_details(boat_number: int):
    """Generate realistic boat details."""
    # Boat classes with typical characteristics
    boat_classes = {
        "1x": {"type": "Single Scull", "crew": 1, "weight_kg": 14},
        "2x": {"type": "Double Scull", "crew": 2, "weight_kg": 27},
        "2-": {"type": "Coxless Pair", "crew": 2, "weight_kg": 27},
        "4x": {"type": "Quad Scull", "crew": 4, "weight_kg": 52},
        "4-": {"type": "Coxless Four", "crew": 4, "weight_kg": 51},
        "4+": {"type": "Coxed Four", "crew": 5, "weight_kg": 51},
        "8+": {"type": "Eight", "crew": 9, "weight_kg": 96}
    }
    
    # Realistic boat names
    boat_names = [
        "Thunder", "Lightning", "Phoenix", "Cyclone", "Vortex", "Tempest",
        "Odyssey", "Navigator", "Voyager", "Explorer", "Pioneer", "Challenger",
        "Victory", "Triumph", "Champion", "Spirit", "Legend", "Dynasty",
        "Horizon", "Aurora", "Meridian", "Zenith", "Apex", "Summit"
    ]
    
    class_type = random.choice(list(boat_classes.keys()))
    boat_info = boat_classes[class_type]
    
    # Generate boat details
    boat_id = f"RC-{boat_number:03d}"
    base_name = random.choice(boat_names)
    name = f"{base_name} {boat_info['type']}"
    
    # Detailed notes with boat specifications
    serial_num = f"BMRC{2020 + boat_number}{boat_number:03d}"
    manufacturer = random.choice(["Empacher", "Filippi", "Vespoli", "Wintech", "Hudson"])
    year = random.randint(2018, 2024)
    condition = random.choice(["Excellent", "Good", "Fair", "Needs Maintenance"])
    
    notes = f"Serial: {serial_num} | Manufacturer: {manufacturer} | Year: {year} | Condition: {condition} | Weight: {boat_info['weight_kg']}kg | Crew: {boat_info['crew']}"
    
    return {
        "boat_id": boat_id,
        "name": name,
        "class_type": class_type,
        "notes": notes,
        "crew_size": boat_info['crew'],
        "weight_kg": boat_info['weight_kg']
    }


def generate_realistic_usage_pattern(boat_details: dict, beacon, db: DatabaseManager, days_back: int = 30):
    """Generate realistic usage patterns for a boat over the specified period."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days_back)
    
    # Different boat classes have different usage patterns
    crew_size = boat_details['crew_size']
    
    # Adjust usage frequency based on boat type
    if crew_size == 1:  # Singles - used more frequently
        sessions_per_week = random.uniform(4, 7)
    elif crew_size <= 2:  # Doubles/pairs - moderate usage
        sessions_per_week = random.uniform(3, 5)
    elif crew_size <= 4:  # Quads/fours - less frequent
        sessions_per_week = random.uniform(2, 4)
    else:  # Eights - least frequent (need full crew)
        sessions_per_week = random.uniform(1, 3)
    
    total_sessions = int((days_back / 7) * sessions_per_week * random.uniform(0.8, 1.2))
    
    print(f"  Generating {total_sessions} sessions for {boat_details['name']} ({boat_details['class_type']})")
    
    current_date = start_date
    session_count = 0
    
    while session_count < total_sessions and current_date < now:
        # Skip some days randomly
        if random.random() < 0.3:  # 30% chance to skip a day
            current_date += timedelta(days=1)
            continue
            
        # Realistic rowing times
        # Morning sessions (5:30-9:00)
        # Evening sessions (16:00-19:30)
        session_time = random.choice(['morning', 'evening'])
        
        if session_time == 'morning':
            hour = random.randint(5, 8)
            minute = random.choice([0, 15, 30, 45])
        else:
            hour = random.randint(16, 19)
            minute = random.choice([0, 15, 30, 45])
        
        # Create departure time
        departure = current_date.replace(
            hour=hour, 
            minute=minute, 
            second=random.randint(0, 59), 
            microsecond=0
        )
        
        # Session duration based on boat type and conditions
        base_duration = {
            1: random.randint(45, 90),    # Singles: 45-90 min
            2: random.randint(60, 120),   # Doubles: 60-120 min  
            4: random.randint(75, 150),   # Fours: 75-150 min
            9: random.randint(90, 180)    # Eights: 90-180 min
        }.get(crew_size, random.randint(60, 120))
        
        # Weather/seasonal adjustments
        season_factor = 1.0
        if current_date.month in [12, 1, 2]:  # Winter - shorter sessions
            season_factor = 0.8
        elif current_date.month in [6, 7, 8]:  # Summer - longer sessions
            season_factor = 1.2
            
        duration_minutes = int(base_duration * season_factor)
        return_time = departure + timedelta(minutes=duration_minutes)
        
        # Generate realistic RSSI values with jitter and slight asymmetry
        exit_rssi_inner = random.randint(-67, -56)
        exit_rssi_outer = random.randint(-66, -54)
        enter_rssi_outer = random.randint(-67, -56)
        enter_rssi_inner = random.randint(-66, -54)
        def jitter_db(x, spread=3):
            return x + random.randint(-spread, spread)
        # Small random timing jitter to emulate walking variability and reflections
        j = lambda s: s + random.uniform(-0.6, 0.6)
        
        # COMPLETE EXIT SEQUENCE (boat leaving shed) - door-lr logic
        # New FSM: INSIDE → OUT_PENDING (left) → OUTSIDE (right within W)
        # 1. Initial movement detected by left scanner
        db.insert_detection("gate-left", beacon.id, rssi=jitter_db(exit_rssi_inner-12), state=DetectionState.OUT_PENDING, timestamp=departure)
        
        # 2. Boat reaches left scanner (stronger signal)
        db.insert_detection("gate-left", beacon.id, rssi=jitter_db(exit_rssi_inner), state=DetectionState.OUT_PENDING, timestamp=departure + timedelta(seconds=j(2)))
        
        # 3. Boat detected by right scanner (within W_pair ~5s)
        db.insert_detection("gate-right", beacon.id, rssi=jitter_db(exit_rssi_outer-6), state=DetectionState.OUT_PENDING, timestamp=departure + timedelta(seconds=j(4)))
        
        # 4. Boat exits (commits to OUTSIDE)
        db.insert_detection("gate-right", beacon.id, rssi=jitter_db(exit_rssi_outer), state=DetectionState.OUTSIDE, timestamp=departure + timedelta(seconds=j(6)))
        # Add weak tail reflections after exit
        db.insert_detection("gate-left", beacon.id, rssi=jitter_db(exit_rssi_inner-18, 4), state=DetectionState.OUT_PENDING, timestamp=departure + timedelta(seconds=j(8)))
        
        # COMPLETE ENTER SEQUENCE (boat returning to shed) - door-lr logic
        # New FSM: OUTSIDE → IN_PENDING (right) → INSIDE (left within W)
        # 1. Boat approaching from water (right scanner first detection)
        db.insert_detection("gate-right", beacon.id, rssi=jitter_db(enter_rssi_outer-12), state=DetectionState.IN_PENDING, timestamp=return_time)
        
        # 2. Boat reaches right scanner (stronger signal)
        db.insert_detection("gate-right", beacon.id, rssi=jitter_db(enter_rssi_outer), state=DetectionState.IN_PENDING, timestamp=return_time + timedelta(seconds=j(2)))
        
        # 3. Boat detected by left scanner (within W_pair ~5s)
        db.insert_detection("gate-left", beacon.id, rssi=jitter_db(enter_rssi_inner-6), state=DetectionState.IN_PENDING, timestamp=return_time + timedelta(seconds=j(4)))
        
        # 4. Boat enters shed (commits to INSIDE)
        db.insert_detection("gate-left", beacon.id, rssi=jitter_db(enter_rssi_inner), state=DetectionState.INSIDE, timestamp=return_time + timedelta(seconds=j(6)))
        # Add weak right tail after entry
        db.insert_detection("gate-right", beacon.id, rssi=jitter_db(enter_rssi_outer-18, 4), state=DetectionState.IN_PENDING, timestamp=return_time + timedelta(seconds=j(8)))
        
        session_count += 1
        
        # Advance to next potential session day
        current_date += timedelta(days=random.uniform(0.5, 3.0))

    print(f"    → {session_count} sessions created with detailed exit/entry sequences")
    return session_count


def main():
    parser = argparse.ArgumentParser(description="Seed boat tracking database with realistic data")
    parser.add_argument("--boats", type=int, default=3, help="Number of boats to create (default: 3)")
    parser.add_argument("--days", type=int, default=30, help="Days of historical data to generate (default: 30)")
    parser.add_argument("--reset", action="store_true", help="Reset database before seeding")
    
    args = parser.parse_args()
    
    db = DatabaseManager()
    
    # Reset database if requested
    if args.reset:
        print("Resetting database...")
        db.reset_all()
        print("Database reset complete")
    
    print(f"Seeding database with {args.boats} boats and {args.days} days of history...")

    # Ensure scanners exist with correct IDs for door-lr FSM
    db.upsert_scanner("gate-right", "Right Gate Scanner", "Gate - Water Side")
    db.upsert_scanner("gate-left", "Left Gate Scanner", "Gate - Shed Side")
    print("Created/updated scanner definitions")

    # Create boats with detailed specifications
    boats = []
    beacons = []
    
    for i in range(1, args.boats + 1):
        boat_details = generate_boat_details(i)
        
        # Create or get existing boat
        boat = db.get_boat(boat_details["boat_id"])
        if not boat:
            boat = db.create_boat(
                boat_details["boat_id"], 
                boat_details["name"], 
                boat_details["class_type"], 
                notes=boat_details["notes"]
            )
            print(f"Created: {boat_details['name']} ({boat_details['class_type']})")
        else:
            # Update existing boat with detailed notes
            db.update_boat(boat.id, notes=boat_details["notes"])
            db.update_boat_status(boat.id, __import__('app.database_models', fromlist=['BoatStatus']).BoatStatus.IN_HARBOR)
            print(f"Updated: {boat_details['name']} ({boat_details['class_type']})")
        
        boats.append((boat, boat_details))

        # Create or find beacon for this boat
        mac = f"AA:BB:CC:DD:EE:{i:02X}"
        beacon = db.get_beacon_by_mac(mac)
        if not beacon:
            beacon_name = f"{boat_details['boat_id']}-Beacon"
            beacon = db.upsert_beacon(mac, name=beacon_name, rssi=-80)
            print(f"Created beacon: {beacon_name} ({mac})")
        
        # Ensure beacon is assigned to boat
        if beacon.status != BeaconStatus.ASSIGNED:
            success = db.assign_beacon_to_boat(beacon.id, boat.id, notes=f"Assigned to {boat_details['name']}")
            if success:
                print(f"Assigned beacon {mac} to {boat_details['name']}")
        
        # Initialize boat as INSIDE shed (default state)
        db.update_beacon_state(beacon.id, DetectionState.INSIDE)
        db.update_boat_status(boat.id, BoatStatus.IN_HARBOR)
        print(f"Initialized {boat_details['name']} as INSIDE shed")
        
        beacons.append(beacon)

    print(f"\nGenerating {args.days} days of detailed usage history...")
    
    # Generate detailed historical data for each boat
    total_sessions = 0
    for (boat, boat_details), beacon in zip(boats, beacons):
        print(f"\nProcessing {boat_details['name']}...")
        sessions = generate_realistic_usage_pattern(boat_details, beacon, db, args.days)
        total_sessions += sessions

    # IMPORTANT: After generating history, ensure all boats are set to IN_HARBOR
    print(f"\nSetting all boats to IN_HARBOR state...")
    for (boat, boat_details), beacon in zip(boats, beacons):
        db.update_beacon_state(beacon.id, DetectionState.INSIDE)
        db.update_boat_status(boat.id, BoatStatus.IN_HARBOR)
        print(f"  {boat_details['name']}: IN_HARBOR + INSIDE")
    
    print(f"\nDatabase seeding complete!")
    print(f"Summary:")
    print(f"   - {args.boats} boats created with detailed specifications")
    print(f"   - {len(beacons)} beacons assigned")
    print(f"   - {args.days} days of historical data")
    print(f"   - Detailed exit/entry sequences for realistic FSM behavior")
    print(f"   - All boats initialized in SHED (IN_HARBOR + INSIDE state)")
    print(f"\nNext steps:")
    print(f"   1. Run the boat tracking system: python3 boat_tracking_system.py --api-port 8000 --web-port 5000")
    print(f"   2. Run realistic simulation: python3 door_lr_simulator.py")
    print(f"   3. View dashboard: http://127.0.0.1:5000/")
    print(f"   4. View FSM animation: http://127.0.0.1:5000/fsm")


if __name__ == "__main__":
    main()


