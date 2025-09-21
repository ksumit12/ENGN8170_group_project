#!/usr/bin/env python3
"""
API Server for BLE Boat Tracking System
Handles detections, manages database, and provides REST API endpoints
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time

from database_models import DatabaseManager, Boat, Beacon, BoatBeaconAssignment, DetectionState, BoatStatus
from entry_exit_fsm import EntryExitFSM, FSMState
from logging_config import get_logger

# Use the system logger
logger = get_logger()

class APIServer:
    def __init__(self, db_path: str = "boat_tracking.db", 
                 outer_scanner_id: str = "gate-outer", 
                 inner_scanner_id: str = "gate-inner"):
        self.app = Flask(__name__)
        CORS(self.app)
        
        self.db = DatabaseManager(db_path)
        self.fsm = EntryExitFSM(
            db_manager=self.db,
            outer_scanner_id=outer_scanner_id,
            inner_scanner_id=inner_scanner_id
        )
        
        self.setup_routes()
        self.setup_websocket_handlers()
        
        # Background task for updating boat statuses
        self.status_update_thread = threading.Thread(target=self._update_boat_statuses, daemon=True)
        self.status_update_thread.start()
    
    def setup_routes(self):
        """Setup all API routes."""
        
        # Simple admin auth (hardcoded credentials)
        ADMIN_USER = 'admin_red_shed'
        ADMIN_PASS = 'Bmrc_2025'

        def _is_admin(req):
            data = req.get_json(silent=True) or {}
            return data.get('user') == ADMIN_USER and data.get('pass') == ADMIN_PASS

        # Detection endpoints
        @self.app.route('/api/v1/detections', methods=['POST'])
        def post_detections():
            """Receive detections from scanners."""
            try:
                data = request.get_json()
                scanner_id = data.get('scanner_id')
                observations = data.get('observations', [])
                
                if not scanner_id or not observations:
                    return jsonify({'error': 'Missing scanner_id or observations'}), 400
                
                processed_count = 0
                state_changes = []
                
                for obs in observations:
                    mac_address = obs.get('mac')
                    rssi = obs.get('rssi')
                    name = obs.get('name', 'Unknown')
                    
                    if not mac_address or rssi is None:
                        continue
                    
                    # Upsert beacon
                    beacon = self.db.upsert_beacon(mac_address, name, rssi)
                    
                    # Log beacon detection
                    logger.info(f"Beacon detected: {name} ({mac_address}) - RSSI: {rssi} dBm from {scanner_id}", "SCANNER")
                    
                    # Only process through FSM if beacon is assigned to a boat
                    assigned_boat = self.db.get_boat_by_beacon(beacon.id)
                    if not assigned_boat:
                        # Skip FSM/state updates for unassigned beacons; discovery UI uses live scanner feed
                        logger.debug(f"Unassigned beacon detected: {name} ({mac_address}) - skipping FSM processing", "SCANNER")
                        processed_count += 1
                        continue

                    state_change = self.fsm.process_detection(scanner_id, beacon.id, rssi)
                    
                    if state_change:
                        old_state, new_state = state_change
                        boat_name = assigned_boat.name if assigned_boat else "Unknown"
                        logger.info(f"Boat state change: {boat_name} ({mac_address}) - {old_state.value} → {new_state.value} (RSSI: {rssi} dBm)", "SCANNER")
                        state_changes.append({
                            'beacon_id': beacon.id,
                            'mac_address': mac_address,
                            'old_state': old_state.value,
                            'new_state': new_state.value,
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        })
                    else:
                        # Log regular detection for assigned beacons
                        boat_name = assigned_boat.name if assigned_boat else "Unknown"
                        logger.debug(f"Boat beacon detected: {boat_name} ({mac_address}) - RSSI: {rssi} dBm (no state change)", "SCANNER")
                    
                    processed_count += 1
                
                return jsonify({
                    'processed': processed_count,
                    'state_changes': state_changes
                })
                
            except Exception as e:
                logger.error(f"Error processing detections: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Boat endpoints
        @self.app.route('/api/v1/boats', methods=['GET'])
        def get_boats():
            """Get all boats."""
            boats = self.db.get_all_boats()
            return jsonify([{
                'id': boat.id,
                'name': boat.name,
                'class_type': boat.class_type,
                'status': boat.status.value,
                'created_at': boat.created_at.isoformat(),
                'updated_at': boat.updated_at.isoformat(),
                'notes': boat.notes
            } for boat in boats])
        
        @self.app.route('/api/v1/boats', methods=['POST'])
        def create_boat():
            """Create a new boat."""
            try:
                data = request.get_json()
                boat_id = data.get('id')
                name = data.get('name')
                class_type = data.get('class_type')
                notes = data.get('notes')
                
                if not boat_id or not name or not class_type:
                    return jsonify({'error': 'Missing required fields'}), 400
                
                boat = self.db.create_boat(boat_id, name, class_type, notes)
                return jsonify({
                    'id': boat.id,
                    'name': boat.name,
                    'class_type': boat.class_type,
                    'status': boat.status.value,
                    'created_at': boat.created_at.isoformat(),
                    'updated_at': boat.updated_at.isoformat(),
                    'notes': boat.notes
                }), 201
                
            except Exception as e:
                logger.error(f"Error creating boat: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/v1/boats/<boat_id>/assign-beacon', methods=['POST'])
        def assign_beacon_to_boat(boat_id):
            """Assign beacon to boat."""
            try:
                data = request.get_json()
                beacon_id = data.get('beacon_id')
                notes = data.get('notes')
                
                if not beacon_id:
                    return jsonify({'error': 'Missing beacon_id'}), 400
                
                success = self.db.assign_beacon_to_boat(beacon_id, boat_id, notes)
                
                if success:
                    return jsonify({'message': 'Beacon assigned successfully'})
                else:
                    return jsonify({'error': 'Assignment failed - beacon or boat may already be assigned'}), 400
                
            except Exception as e:
                logger.error(f"Error assigning beacon: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/v1/boats/<boat_id>/unassign-beacon', methods=['POST'])
        def unassign_beacon_from_boat(boat_id):
            """Unassign beacon from boat."""
            try:
                # Get current beacon assignment
                beacon = self.db.get_beacon_by_boat(boat_id)
                if not beacon:
                    return jsonify({'error': 'No beacon assigned to this boat'}), 400
                
                success = self.db.unassign_beacon(beacon.id)
                
                if success:
                    return jsonify({'message': 'Beacon unassigned successfully'})
                else:
                    return jsonify({'error': 'Unassignment failed'}), 400
                
            except Exception as e:
                logger.error(f"Error unassigning beacon: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Beacon endpoints
        @self.app.route('/api/v1/beacons', methods=['GET'])
        def get_beacons():
            """Get all beacons."""
            beacons = self.db.get_all_beacons()
            return jsonify([{
                'id': beacon.id,
                'mac_address': beacon.mac_address,
                'name': beacon.name,
                'status': beacon.status.value,
                'last_seen': beacon.last_seen.isoformat() if beacon.last_seen else None,
                'last_rssi': beacon.last_rssi,
                'created_at': beacon.created_at.isoformat(),
                'updated_at': beacon.updated_at.isoformat(),
                'notes': beacon.notes
            } for beacon in beacons])
        
        @self.app.route('/api/v1/beacons/<beacon_id>', methods=['PATCH'])
        def update_beacon(beacon_id):
            """Update beacon information."""
            try:
                data = request.get_json()
                # Implementation for updating beacon details
                return jsonify({'message': 'Beacon updated successfully'})
                
            except Exception as e:
                logger.error(f"Error updating beacon: {e}")
                return jsonify({'error': str(e)}), 500

        # Admin: reset assignments and states
        @self.app.route('/api/admin/reset', methods=['POST'])
        def admin_reset():
            try:
                if not _is_admin(request):
                    return jsonify({'error': 'Unauthorized'}), 401
                data = request.get_json(silent=True) or {}
                if data.get('dry'):
                    return jsonify({'message': 'Auth OK'})
                self.db.reset_all()
                return jsonify({'message': 'System reset complete'})
            except Exception as e:
                logger.error(f"Error during admin reset: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Presence endpoints
        @self.app.route('/api/v1/presence', methods=['GET'])
        def get_presence():
            """Get current boat presence status.
            Uses boat status (IN_HARBOR) as truth. Falls back from FSM state to status to
            support single-scanner deployments where FSM ENTERED may not be set.
            """
            boats = self.db.get_all_boats()
            boats_in_harbor = []
            for b in boats:
                if getattr(b.status, 'value', str(b.status)) in ('in_harbor', 'IN_HARBOR') or str(b.status) == 'BoatStatus.IN_HARBOR':
                    beacon = self.db.get_beacon_by_boat(b.id)
                    if beacon:
                        boats_in_harbor.append((b, beacon))

            return jsonify({
                'boats_in_harbor': [{
                    'boat_id': boat.id,
                    'boat_name': boat.name,
                    'boat_class': boat.class_type,
                    'beacon_id': beacon.id,
                    'beacon_mac': beacon.mac_address,
                    'last_seen': beacon.last_seen.isoformat() if beacon.last_seen else None,
                    'last_rssi': beacon.last_rssi
                } for boat, beacon in boats_in_harbor],
                'total_in_harbor': len(boats_in_harbor),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        
        @self.app.route('/api/v1/presence/<boat_id>', methods=['GET'])
        def get_boat_presence(boat_id):
            """Get presence status for specific boat."""
            try:
                boat = self.db.get_boat(boat_id)
                if not boat:
                    return jsonify({'error': 'Boat not found'}), 404
                
                beacon = self.db.get_beacon_by_boat(boat_id)
                if not beacon:
                    return jsonify({
                        'boat_id': boat_id,
                        'boat_name': boat.name,
                        'status': 'no_beacon_assigned',
                        'in_harbor': False
                    })
                
                # Check if beacon is in ENTERED state
                beacon_state = self.fsm.get_beacon_state(beacon.id)
                in_harbor = beacon_state == FSMState.ENTERED
                
                return jsonify({
                    'boat_id': boat_id,
                    'boat_name': boat.name,
                    'beacon_id': beacon.id,
                    'beacon_mac': beacon.mac_address,
                    'status': beacon_state.value,
                    'in_harbor': in_harbor,
                    'last_seen': beacon.last_seen.isoformat() if beacon.last_seen else None,
                    'last_rssi': beacon.last_rssi
                })
                
            except Exception as e:
                logger.error(f"Error getting boat presence: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Health check
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'database': 'connected'
            })
    
    def setup_websocket_handlers(self):
        """Setup WebSocket handlers for real-time updates."""
        # This would be implemented with Flask-SocketIO for real-time updates
        pass
    
    def _update_boat_statuses(self):
        """Background task to update boat statuses.
        Single-scanner friendly: mark IN_HARBOR when assigned beacon was seen recently; otherwise OUT.
        """
        while True:
            try:
                # Get all boats with assigned beacons
                boats = self.db.get_all_boats()
                
                for boat in boats:
                    beacon = self.db.get_beacon_by_boat(boat.id)
                    if beacon:
                        # Consider the beacon "in shed" if seen recently
                        window_seconds = 8
                        if beacon.last_seen:
                            last_seen_dt = beacon.last_seen if isinstance(beacon.last_seen, datetime) else datetime.fromisoformat(beacon.last_seen)
                        else:
                            last_seen_dt = None

                        # Check if beacon was seen recently
                        is_recently_seen = last_seen_dt and (datetime.now(timezone.utc) - last_seen_dt).total_seconds() <= window_seconds
                        
                        # Determine new status
                        new_status = BoatStatus.IN_HARBOR if is_recently_seen else BoatStatus.OUT
                        
                        # Only update and log if status changed
                        if boat.status != new_status:
                            self.db.update_boat_status(boat.id, new_status)
                            
                            if new_status == BoatStatus.IN_HARBOR:
                                logger.info(f"Boat entered harbor: {boat.name} (beacon: {beacon.mac_address})", "STATUS")
                            else:
                                logger.info(f"Boat left harbor: {boat.name} (beacon: {beacon.mac_address}) - last seen: {last_seen_dt}", "STATUS")
                
                time.sleep(5)  # Update every 5 seconds
                
            except Exception as e:
                logger.error(f"Error updating boat statuses: {e}")
                time.sleep(10)
    
    def run(self, host='0.0.0.0', port=8000, debug=False):
        """Run the API server."""
        logger.info(f"Starting API server on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

def main():
    """Main entry point for standalone API server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="API Server for Boat Tracking")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--db-path", default="boat_tracking.db", help="Database file path")
    parser.add_argument("--outer-scanner", default="gate-outer", help="Outer scanner ID")
    parser.add_argument("--inner-scanner", default="gate-inner", help="Inner scanner ID")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    server = APIServer(
        db_path=args.db_path,
        outer_scanner_id=args.outer_scanner,
        inner_scanner_id=args.inner_scanner
    )
    
    try:
        server.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("Shutting down API server...")

if __name__ == "__main__":
    main()

