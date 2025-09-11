# Migration Guide: Single Beacon → Multi-Beacon System

## Overview
This guide helps you migrate from the single-beacon system to the new multi-beacon database-backed system.

## Key Changes

### 1. Architecture Changes
- **Old**: Hardcoded MAC address, single beacon
- **New**: Database-backed, supports 30-40 beacons
- **Old**: CSV logging only
- **New**: SQLite database with full history

### 2. New Components
- `database_models.py` - Database schema and operations
- `ble_scanner.py` - Multi-beacon scanner (replaces `ble_beacon_detector.py`)
- `entry_exit_fsm.py` - Entry/exit state machine with hysteresis
- `api_server.py` - REST API server (replaces `boat_tracker.py`)
- `boat_tracking_system.py` - Main orchestrator (replaces `simple_boat_tracker.py`)

### 3. Database Schema
```sql
boats - Boat metadata
beacons - Beacon MAC addresses and status
boat_beacon_assignments - Beacon ↔ Boat mappings
detections - Detection events for analytics
beacon_states - FSM states for entry/exit logic
scanners - Scanner device information
```

## Migration Steps

### Step 1: Install Dependencies
```bash
pip install -r requirements_new.txt
```

### Step 2: Setup New System
```bash
python3 setup_new_system.py
```

### Step 3: Start New System
```bash
# Start complete system
python3 boat_tracking_system.py

# Or start components separately
python3 api_server.py --port 8000
python3 ble_scanner.py --scanner-id gate-outer --server-url http://localhost:8000
python3 ble_scanner.py --scanner-id gate-inner --server-url http://localhost:8000
```

### Step 4: Configure Scanners
- Place two scanners at the gate (inner/outer)
- Each scanner detects all beacons in range
- No code changes needed for new beacons

### Step 5: Assign Beacons to Boats
- Use web dashboard at http://localhost:5000
- Or use API endpoints to assign beacons
- Beacons auto-detect when placed near scanners

## API Endpoints

### Boats
- `GET /api/v1/boats` - List all boats
- `POST /api/v1/boats` - Create new boat
- `POST /api/v1/boats/{id}/assign-beacon` - Assign beacon to boat

### Beacons
- `GET /api/v1/beacons` - List all beacons
- `PATCH /api/v1/beacons/{id}` - Update beacon info

### Detections
- `POST /api/v1/detections` - Submit scanner detections

### Presence
- `GET /api/v1/presence` - Get current harbor status

## Configuration

### Scanner Configuration
```python
scanners = [
    {
        'id': 'gate-outer',
        'api_key': 'default-key',
        'rssi_threshold': -70,
        'scan_interval': 1.0
    },
    {
        'id': 'gate-inner', 
        'api_key': 'default-key',
        'rssi_threshold': -70,
        'scan_interval': 1.0
    }
]
```

### FSM Configuration
- RSSI threshold: -70 dBm
- Hysteresis: 5 dBm (prevents flicker)
- Timeout: 5 minutes (prevents stuck states)

## Benefits of New System

1. **Scalability**: Supports 30-40 boats/beacons
2. **Flexibility**: Easy beacon onboarding without code changes
3. **Reliability**: Hysteresis prevents false positives
4. **History**: Full audit trail of all events
5. **Admin UI**: Web interface for management
6. **API**: RESTful API for integration
7. **Real-time**: WebSocket support for live updates

## Troubleshooting

### Common Issues
1. **Beacons not detected**: Check RSSI threshold and scanner placement
2. **False entries**: Adjust hysteresis value
3. **Database errors**: Check file permissions and disk space
4. **API errors**: Verify scanner IDs and API keys

### Logs
- Check console output for error messages
- Database file: `boat_tracking.db`
- Logs include detection events and state changes

## Rollback Plan
If issues occur, you can temporarily use the old system:
1. Stop new system
2. Run old `simple_boat_tracker.py`
3. Fix issues in new system
4. Migrate back when ready

