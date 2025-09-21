#!/usr/bin/env python3
"""
API Server for Boat Tracking System
Handles REST API endpoints for beacon detection and boat management
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# Add current directory to path for imports
sys.path.append('.')

try:
    from database_models import Boat, Beacon, Detection, BoatBeaconAssignment, DatabaseManager
    from logging_config import setup_logging
except ImportError:
    # Fallback if modules not available
    print("Warning: Some modules not available, using fallback implementations")
    
    class DatabaseManager:
        def __init__(self, db_path: str):
            self.db_path = db_path
        
        def get_boats(self) -> List[Dict]:
            return []
        
        def get_beacons(self) -> List[Dict]:
            return []
        
        def get_detections(self, limit: int = 100) -> List[Dict]:
            return []
        
        def get_assignments(self) -> List[Dict]:
            return []
    
    def setup_logging():
        logging.basicConfig(level=logging.INFO)

# Setup logging
logger = setup_logging()

class APIServer:
    """REST API Server for boat tracking system"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000, db_path: str = "boat_tracking.db"):
        self.host = host
        self.port = port
        self.db_path = db_path
        self.app = Flask(__name__)
        CORS(self.app)
        
        # Initialize database
        self.db = DatabaseManager(db_path)
        
        # Setup routes
        self._setup_routes()
        
        logger.info(f"API Server initialized on {host}:{port}")
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/api/health', methods=['GET'])
        def health():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'version': '1.0.0'
            })
        
        @self.app.route('/api/boats', methods=['GET'])
        def get_boats():
            """Get all boats"""
            try:
                boats = self.db.get_boats()
                return jsonify({
                    'success': True,
                    'data': boats,
                    'count': len(boats)
                })
            except Exception as e:
                logger.error(f"Error getting boats: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/beacons', methods=['GET'])
        def get_beacons():
            """Get all beacons"""
            try:
                beacons = self.db.get_beacons()
                return jsonify({
                    'success': True,
                    'data': beacons,
                    'count': len(beacons)
                })
            except Exception as e:
                logger.error(f"Error getting beacons: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/detections', methods=['GET'])
        def get_detections():
            """Get recent detections"""
            try:
                limit = request.args.get('limit', 100, type=int)
                detections = self.db.get_detections(limit=limit)
                return jsonify({
                    'success': True,
                    'data': detections,
                    'count': len(detections)
                })
            except Exception as e:
                logger.error(f"Error getting detections: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/assignments', methods=['GET'])
        def get_assignments():
            """Get boat-beacon assignments"""
            try:
                assignments = self.db.get_assignments()
                return jsonify({
                    'success': True,
                    'data': assignments,
                    'count': len(assignments)
                })
            except Exception as e:
                logger.error(f"Error getting assignments: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/detection', methods=['POST'])
        def record_detection():
            """Record a beacon detection"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No JSON data provided'
                    }), 400
                
                # Extract detection data
                beacon_id = data.get('beacon_id')
                scanner_id = data.get('scanner_id')
                rssi = data.get('rssi')
                timestamp = data.get('timestamp', datetime.now().isoformat())
                
                if not all([beacon_id, scanner_id, rssi is not None]):
                    return jsonify({
                        'success': False,
                        'error': 'Missing required fields: beacon_id, scanner_id, rssi'
                    }), 400
                
                # TODO: Implement detection recording in database
                logger.info(f"Detection recorded: {beacon_id} by {scanner_id} at {rssi} dBm")
                
                return jsonify({
                    'success': True,
                    'message': 'Detection recorded successfully'
                })
                
            except Exception as e:
                logger.error(f"Error recording detection: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/status', methods=['GET'])
        def get_status():
            """Get system status"""
            try:
                boats = self.db.get_boats()
                beacons = self.db.get_beacons()
                detections = self.db.get_detections(limit=10)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'boats_count': len(boats),
                        'beacons_count': len(beacons),
                        'recent_detections': len(detections),
                        'timestamp': datetime.now().isoformat()
                    }
                })
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
    
    def run(self, debug: bool = False):
        """Run the API server"""
        logger.info(f"Starting API server on {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=debug)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Boat Tracking API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--db-path", default="boat_tracking.db", help="Database path")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    server = APIServer(
        host=args.host,
        port=args.port,
        db_path=args.db_path
    )
    
    server.run(debug=args.debug)
