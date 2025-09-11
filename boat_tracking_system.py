#!/usr/bin/env python3
"""
Boat Tracking System - Main Orchestrator
Manages scanners, API server, and web dashboard
"""

import time
import threading
import logging
import argparse
import subprocess
import sys
from typing import List, Optional
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime, timezone, timedelta
from flask_cors import CORS

from database_models import DatabaseManager
from ble_scanner import BLEScanner, ScannerConfig
from api_server import APIServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BoatTrackingSystem:
    def __init__(self, config: dict):
        self.config = config
        self.db = DatabaseManager(config['database_path'])
        self.api_server = None
        self.scanners: List[BLEScanner] = []
        self.running = False
        
        # Web dashboard
        self.web_app = Flask(__name__)
        CORS(self.web_app)
        self.setup_web_routes()
    
    def setup_web_routes(self):
        """Setup web dashboard routes."""
        
        @self.web_app.route('/')
        def dashboard():
            """Main dashboard page."""
            return render_template_string(self.get_dashboard_html())
        
        @self.web_app.route('/api/boats')
        def api_boats():
            """Get all boats for dashboard."""
            boats = self.db.get_all_boats()
            result = []
            
            for boat in boats:
                beacon = self.db.get_beacon_by_boat(boat.id)
                if not beacon:
                    # Skip boats with no assigned beacon to avoid clutter
                    continue
                # Skip legacy/demo boats that were not created via the register flow
                # Registered boats carry a notes field that includes a "Serial:" marker
                if not boat.notes or ('Serial:' not in str(boat.notes)):
                    continue
                beacon_state = None
                last_seen_ts = 0
                if beacon and beacon.last_seen:
                    ls = beacon.last_seen
                    if isinstance(ls, str):
                        try:
                            last_seen_ts = datetime.fromisoformat(ls).timestamp()
                        except Exception:
                            last_seen_ts = 0
                    else:
                        last_seen_ts = ls.timestamp()
                
                result.append({
                    'id': boat.id,
                    'name': boat.name,
                    'class_type': boat.class_type,
                    'status': boat.status.value,
                    'beacon': {
                        'id': beacon.id if beacon else None,
                        'mac_address': beacon.mac_address if beacon else None,
                        'last_seen': beacon.last_seen.isoformat() if beacon and not isinstance(beacon.last_seen, str) and beacon.last_seen else (beacon.last_seen if beacon and isinstance(beacon.last_seen, str) else None),
                        'last_rssi': beacon.last_rssi if beacon else None
                    } if beacon else None,
                    'beacon_state': beacon_state,
                    '_last_seen_ts': last_seen_ts
                })
            
            # Sort so active boats (in_harbor) are first, then by most recently seen beacon
            result.sort(key=lambda b: (
                0 if b['status'] == 'in_harbor' else 1,
                -b.get('_last_seen_ts', 0),
                b['name'].lower()
            ))
            
            # Remove helper field before returning
            for b in result:
                if '_last_seen_ts' in b:
                    del b['_last_seen_ts']
            
            return jsonify(result)
        
        @self.web_app.route('/api/beacons')
        def api_beacons():
            """Get beacons for dashboard. Supports filtering for recently active beacons.
            Query params:
              - active_only=1 to return only beacons seen within the window
              - window=seconds (default 30)
            """
            beacons = self.db.get_all_beacons()
            active_only = request.args.get('active_only') in ('1', 'true', 'True')
            try:
                window_seconds = int(request.args.get('window', '30'))
            except ValueError:
                window_seconds = 30

            now = datetime.now(timezone.utc)
            if active_only:
                cutoff = now - timedelta(seconds=window_seconds)
                beacons = [b for b in beacons if b.last_seen and b.last_seen >= cutoff]

            result = []
            for beacon in beacons:
                boat = self.db.get_boat_by_beacon(beacon.id)
                result.append({
                    'id': beacon.id,
                    'mac_address': beacon.mac_address,
                    'name': beacon.name,
                    'status': beacon.status.value,
                    'last_seen': beacon.last_seen.isoformat() if beacon.last_seen else None,
                    'last_rssi': beacon.last_rssi,
                    'assigned_boat': {
                        'id': boat.id,
                        'name': boat.name
                    } if boat else None
                })
            return jsonify(result)

        @self.web_app.route('/api/active-beacons')
        def api_active_beacons():
            """Return beacons currently detected by running scanners (real-time).
            Merges detections across scanners and annotates assignment status from DB.
            """
            # Merge by MAC, prefer latest timestamp
            latest_by_mac = {}
            for scanner in self.scanners:
                try:
                    detected = scanner.get_detected_beacons()
                except Exception:
                    detected = {}
                for mac, obs in detected.items():
                    prev = latest_by_mac.get(mac)
                    if prev is None or (obs.ts and prev.ts and obs.ts > prev.ts) or (prev is None and obs.ts is not None):
                        latest_by_mac[mac] = obs

            results = []
            for mac, obs in latest_by_mac.items():
                # Lookup in DB to know if this MAC corresponds to an assigned beacon
                beacon = self.db.get_beacon_by_mac(mac)
                assigned_boat = None
                status = 'unclaimed'
                if beacon:
                    boat = self.db.get_boat_by_beacon(beacon.id)
                    if boat:
                        assigned_boat = {'id': boat.id, 'name': boat.name}
                        status = 'assigned'
                results.append({
                    'mac_address': mac,
                    'name': getattr(obs, 'name', None) or (beacon.name if beacon and beacon.name else None),
                    'last_rssi': getattr(obs, 'rssi', None),
                    'last_seen': datetime.fromtimestamp(obs.ts, tz=timezone.utc).isoformat() if getattr(obs, 'ts', None) else None,
                    'status': status,
                    'assigned_boat': assigned_boat
                })

            # Sort by strongest signal first
            results.sort(key=lambda x: (x['last_rssi'] is not None, x['last_rssi']), reverse=True)
            return jsonify(results)
        
        @self.web_app.route('/api/presence')
        def api_presence():
            """Get current presence status."""
            boats_in_harbor = self.db.get_boats_in_harbor()
            
            def normalize_last_seen(ls):
                if not ls:
                    return None
                if isinstance(ls, str):
                    return ls
                try:
                    return ls.isoformat()
                except Exception:
                    return str(ls)

            return jsonify({
                'boats_in_harbor': [{
                    'boat_id': boat.id,
                    'boat_name': boat.name,
                    'boat_class': boat.class_type,
                    'beacon_mac': beacon.mac_address,
                    'last_seen': normalize_last_seen(beacon.last_seen),
                    'last_rssi': beacon.last_rssi
                } for boat, beacon in boats_in_harbor],
                'total_in_harbor': len(boats_in_harbor),
                'timestamp': time.time()
            })
        
        @self.web_app.route('/api/register-beacon', methods=['POST'])
        def register_beacon():
            """Register a new beacon and create associated boat."""
            try:
                data = request.get_json()
                
                # Create the boat first
                boat_serial = data.get('boat_serial')
                if not boat_serial:
                    return jsonify({'success': False, 'error': 'boat_serial is required'}), 400
                self.db.create_boat(
                    boat_id=boat_serial,
                    name=data['boat_name'],
                    class_type=data['boat_class'],
                    notes=f"Serial: {data.get('boat_serial', 'N/A')}, Brand: {data.get('boat_brand', 'N/A')}, {data.get('boat_notes', '')}"
                )
                boat_id = boat_serial
                
                # Update the beacon with the new name and assign to boat
                beacon = self.db.get_beacon_by_mac(data['mac_address'])
                if beacon:
                    # Update beacon name
                    self.db.update_beacon(beacon.id, name=data['name'])
                    # Assign beacon to boat
                    self.db.assign_beacon_to_boat(beacon.id, boat_id)
                    
                    return jsonify({
                        'success': True,
                        'message': 'Beacon registered successfully',
                        'boat_id': boat_id,
                        'beacon_id': beacon.id
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Beacon not found. Make sure the beacon is nearby and detected by the system.'
                    }), 404
                    
            except Exception as e:
                logger.error(f"Error registering beacon: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
    
    def start_api_server(self):
        """Start the API server."""
        self.api_server = APIServer(
            db_path=self.config['database_path'],
            outer_scanner_id=self.config['outer_scanner_id'],
            inner_scanner_id=self.config['inner_scanner_id']
        )
        
        api_thread = threading.Thread(
            target=self.api_server.run,
            kwargs={
                'host': self.config['api_host'],
                'port': self.config['api_port'],
                'debug': False
            },
            daemon=True
        )
        api_thread.start()
        logger.info(f"API server started on {self.config['api_host']}:{self.config['api_port']}")
    
    def start_scanners(self):
        """Start BLE scanners."""
        for scanner_config in self.config['scanners']:
            config = ScannerConfig(
                scanner_id=scanner_config['id'],
                server_url=f"http://{self.config['api_host']}:{self.config['api_port']}",
                api_key=scanner_config.get('api_key', 'default-key'),
                rssi_threshold=scanner_config.get('rssi_threshold', -80),
                scan_interval=scanner_config.get('scan_interval', 1.0)
            )
            
            scanner = BLEScanner(config)
            scanner.start_scanning()
            self.scanners.append(scanner)
            logger.info(f"Scanner {scanner_config['id']} started")
    
    def start_web_dashboard(self):
        """Start web dashboard."""
        web_thread = threading.Thread(
            target=self.web_app.run,
            kwargs={
                'host': self.config['web_host'],
                'port': self.config['web_port'],
                'debug': False
            },
            daemon=True
        )
        web_thread.start()
        logger.info(f"Web dashboard started on {self.config['web_host']}:{self.config['web_port']}")
    
    def start(self):
        """Start the entire system."""
        logger.info("Starting Boat Tracking System...")
        
        # Start API server
        self.start_api_server()
        time.sleep(2)  # Give API server time to start
        
        # Start scanners
        self.start_scanners()
        
        # Start web dashboard
        self.start_web_dashboard()
        
        self.running = True
        logger.info("Boat Tracking System started successfully")
        logger.info(f"API Server: http://{self.config['api_host']}:{self.config['api_port']}")
        logger.info(f"Web Dashboard: http://{self.config['web_host']}:{self.config['web_port']}")
    
    def stop(self):
        """Stop the entire system."""
        logger.info("Stopping Boat Tracking System...")
        
        # Stop scanners
        for scanner in self.scanners:
            scanner.stop_scanning()
        
        self.running = False
        logger.info("Boat Tracking System stopped")
    
    def get_dashboard_html(self):
        """Get HTML for the web dashboard."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Boat Tracking System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; color: #333; padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; color: white; }
        .header h1 { font-size: 2.5rem; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
        .card { 
            background: white; border-radius: 15px; padding: 25px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.1); 
        }
        .card h2 { color: #2c3e50; margin-bottom: 20px; }
        .boat-item, .beacon-item { 
            padding: 15px; margin: 10px 0; border-radius: 8px; 
            background: #f8f9fa; border-left: 4px solid #667eea;
        }
        .boat-item.in-harbor { border-left-color: #28a745; }
        .boat-item.out { border-left-color: #dc3545; }
        .beacon-item.assigned { border-left-color: #28a745; }
        .beacon-item.unclaimed { border-left-color: #ffc107; }
        .status-badge { 
            display: inline-block; padding: 4px 8px; border-radius: 12px; 
            font-weight: bold; font-size: 0.8rem; margin-left: 10px;
        }
        .status-in-harbor { background: #d4edda; color: #155724; }
        .status-out { background: #f8d7da; color: #721c24; }
        .status-assigned { background: #d4edda; color: #155724; }
        .status-unclaimed { background: #fff3cd; color: #856404; }
        .update-indicator { 
            position: fixed; top: 20px; right: 20px; padding: 10px 15px; 
            background: #28a745; color: white; border-radius: 20px; 
            font-size: 0.9rem; font-weight: bold; z-index: 1000;
            opacity: 0; transition: opacity 0.3s ease;
        }
        .update-indicator.show { opacity: 1; }
        .rssi-info { font-size: 0.9rem; color: #6c757d; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Boat Tracking System</h1>
            <p>Multi-beacon BLE tracking with database backend</p>
            <button onclick="openBeaconDiscovery()" style="
                background: #28a745; color: white; border: none; padding: 12px 24px; 
                border-radius: 25px; font-size: 1.1rem; font-weight: bold; 
                cursor: pointer; margin-top: 15px; box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
                transition: all 0.3s ease;
            " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 20px rgba(40, 167, 69, 0.4)'" 
               onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 15px rgba(40, 167, 69, 0.3)'">
                + Register New Beacon
            </button>
        </div>
        
        <div class="update-indicator" id="updateIndicator">Updating...</div>
        
        <div class="dashboard">
            <!-- Boats Status -->
            <div class="card">
                <h2>Boats Status</h2>
                <div id="boatsList">
                    <p>Loading boats...</p>
                </div>
            </div>
            
            <!-- Beacons Status -->
            <div class="card">
                <h2>Beacons Status</h2>
                <div id="beaconsList">
                    <p>Loading beacons...</p>
                </div>
            </div>
            
            <!-- Presence Summary -->
            <div class="card">
                <h2>Shed Presence</h2>
                <div id="presenceInfo">
                    <p>Loading presence data...</p>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Beacon Discovery Modal -->
    <div id="beaconModal" style="
        display: none; position: fixed; z-index: 1000; left: 0; top: 0; 
        width: 100%; height: 100%; background-color: rgba(0,0,0,0.5);
    ">
        <div style="
            background-color: white; margin: 5% auto; padding: 20px; 
            border-radius: 15px; width: 80%; max-width: 800px; max-height: 80vh;
            overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="color: #2c3e50; margin: 0;">Discover & Register Beacons</h2>
                <button onclick="closeBeaconDiscovery()" style="
                    background: #dc3545; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer; font-size: 1.2rem;
                ">×</button>
            </div>
            
            <div style="margin-bottom: 20px;">
                <button id="startScanBtn" onclick="startBeaconScan()" style="
                    background: #007bff; color: white; border: none; padding: 12px 24px; 
                    border-radius: 25px; cursor: pointer; font-weight: bold; margin-right: 10px;
                ">Start Scanning</button>
                <button id="stopScanBtn" onclick="stopBeaconScan()" style="
                    background: #6c757d; color: white; border: none; padding: 12px 24px; 
                    border-radius: 25px; cursor: pointer; font-weight: bold; display: none;
                ">Stop Scanning</button>
                <span id="scanStatus" style="margin-left: 15px; color: #666;">Click "Start Scanning" to discover nearby beacons</span>
            </div>
            
            <div id="beaconList" style="max-height: 400px; overflow-y: auto;">
                <p style="text-align: center; color: #666; padding: 20px;">No beacons discovered yet. Click "Start Scanning" to begin.</p>
            </div>
        </div>
    </div>
    
    <!-- Beacon Registration Modal -->
    <div id="registerModal" style="
        display: none; position: fixed; z-index: 1001; left: 0; top: 0; 
        width: 100%; height: 100%; background-color: rgba(0,0,0,0.5);
    ">
        <div style="
            background-color: white; margin: 10% auto; padding: 30px; 
            border-radius: 15px; width: 90%; max-width: 500px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                <h2 style="color: #2c3e50; margin: 0;">Register Beacon</h2>
                <button onclick="closeRegisterModal()" style="
                    background: #dc3545; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer; font-size: 1.2rem;
                ">×</button>
            </div>
            
            <form id="beaconForm" onsubmit="registerBeacon(event)">
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Beacon MAC Address:</label>
                    <input type="text" id="beaconMac" readonly style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; 
                        font-family: monospace; background: #f8f9fa;
                    ">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Beacon Name:</label>
                    <input type="text" id="beaconName" required style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px;
                    " placeholder="e.g., Boat-01, Training-1x">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Boat Name:</label>
                    <input type="text" id="boatName" required style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px;
                    " placeholder="e.g., Rowing Club 1x, Training Single">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Boat Class:</label>
                    <select id="boatClass" required style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px;
                    ">
                        <option value="">Select boat class</option>
                        <option value="1x">1x (Single Scull)</option>
                        <option value="2-">2- (Pair without Coxswain)</option>
                        <option value="2+">2+ (Pair with Coxswain)</option>
                        <option value="4x">4x (Quad Scull)</option>
                        <option value="4+">4+ (Four with Coxswain)</option>
                        <option value="8+">8+ (Eight with Coxswain)</option>
                    </select>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Serial Number:</label>
                    <input type="text" id="boatSerial" style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px;
                    " placeholder="e.g., RC-2024-001">
                </div>
                
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Brand/Manufacturer:</label>
                    <input type="text" id="boatBrand" style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px;
                    " placeholder="e.g., Empacher, Filippi, Hudson">
                </div>
                
                <div style="margin-bottom: 25px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold; color: #2c3e50;">Notes:</label>
                    <textarea id="boatNotes" style="
                        width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; 
                        height: 80px; resize: vertical;
                    " placeholder="Additional notes about the boat..."></textarea>
                </div>
                
                <div style="text-align: right;">
                    <button type="button" onclick="closeRegisterModal()" style="
                        background: #6c757d; color: white; border: none; padding: 12px 24px; 
                        border-radius: 25px; cursor: pointer; margin-right: 10px;
                    ">Cancel</button>
                    <button type="submit" style="
                        background: #28a745; color: white; border: none; padding: 12px 24px; 
                        border-radius: 25px; cursor: pointer; font-weight: bold;
                    ">Register Beacon</button>
                </div>
            </form>
        </div>
    </div>
    
    <script>
        function updateBoats() {
            fetch('/api/boats')
                .then(response => response.json())
                .then(data => {
                    const boatsList = document.getElementById('boatsList');
                    if (data.length === 0) {
                        boatsList.innerHTML = '<p>No boats registered</p>';
                        return;
                    }
                    
                    let html = '';
                    data.forEach(boat => {
                        const statusClass = boat.status === 'in_harbor' ? 'in-harbor' : 'out';
                        const statusBadge = boat.status === 'in_harbor' ? 'status-in-harbor' : 'status-out';
                        const beaconInfo = boat.beacon ? 
                            `<div class=\"rssi-info\">Beacon: ${boat.beacon.mac_address}<br>Signal: ${rssiToPercent(boat.beacon.last_rssi)}% (${boat.beacon.last_rssi || 'N/A'} dBm)</div>` : 
                            '<div class="rssi-info">No beacon assigned</div>';
                        
                        html += `
                            <div class="boat-item ${statusClass}">
                                <div>
                                    <strong>${boat.name}</strong> (${boat.class_type})
                                    <span class="status-badge ${statusBadge}">${boat.status.replace('_', ' ').toUpperCase()}</span>
                                </div>
                                ${beaconInfo}
                            </div>
                        `;
                    });
                    boatsList.innerHTML = html;
                })
                .catch(error => console.error('Error updating boats:', error));
        }
        
        function updateBeacons() {
            // Beacons Status card: show only beacons that are assigned (registered)
            fetch('/api/beacons')
                .then(response => response.json())
                .then(data => {
                    const beaconsList = document.getElementById('beaconsList');
                    // Only show beacons that are currently assigned and have been seen recently
                    const nowMs = Date.now();
                    const freshnessMs = 15 * 1000; // 15s freshness for status card
                    const assignedOnly = data.filter(b => 
                        b.status === 'assigned' && b.last_seen && (nowMs - new Date(b.last_seen).getTime()) <= freshnessMs
                    );
                    if (assignedOnly.length === 0) {
                        beaconsList.innerHTML = '<p>No beacons detected</p>';
                        return;
                    }
                    
                    let html = '';
                    assignedOnly.forEach(beacon => {
                        const statusClass = beacon.status === 'assigned' ? 'assigned' : 'unclaimed';
                        const statusBadge = beacon.status === 'assigned' ? 'status-assigned' : 'status-unclaimed';
                        const boatInfo = beacon.assigned_boat ? 
                            `<div class="rssi-info">Assigned to: ${beacon.assigned_boat.name}</div>` : 
                            '<div class="rssi-info">Unclaimed</div>';
                        const lastSeen = beacon.last_seen ? 
                            `<div class="rssi-info">Last seen: ${new Date(beacon.last_seen).toLocaleString()}</div>` : 
                            '<div class="rssi-info">Never seen</div>';
                        
                        html += `
                            <div class="beacon-item ${statusClass}">
                                <div>
                                    <strong>${beacon.mac_address}</strong>
                                    <span class="status-badge ${statusBadge}">${beacon.status.toUpperCase()}</span>
                                </div>
                                ${boatInfo}
                                ${lastSeen}
                            </div>
                        `;
                    });
                    beaconsList.innerHTML = html;
                })
                .catch(error => console.error('Error updating beacons:', error));
        }
        
        function updatePresence() {
            fetch('/api/presence')
                .then(response => response.json())
                .then(data => {
                    const presenceInfo = document.getElementById('presenceInfo');
                    let html = `
                        <div style="text-align: center; margin-bottom: 20px;">
                            <div style="font-size: 3rem; font-weight: bold; color: #28a745;">${data.total_in_harbor}</div>
                            <div style="color: #666;">Boats in Shed</div>
                        </div>
                    `;
                    
                    if (data.boats_in_harbor.length > 0) {
                        html += '<h3>Currently in Shed:</h3>';
                        data.boats_in_harbor.forEach(boat => {
                            html += `
                                <div class="boat-item in-harbor">
                                    <div><strong>${boat.boat_name}</strong> (${boat.boat_class})</div>
                                    <div class="rssi-info">Beacon: ${boat.beacon_mac}<br>Signal: ${rssiToPercent(boat.last_rssi)}% (${boat.last_rssi || 'N/A'} dBm)</div>
                                </div>
                            `;
                        });
                    } else {
                        html += '<p style="text-align: center; color: #666;">No boats currently in shed</p>';
                    }
                    
                    presenceInfo.innerHTML = html;
                })
                .catch(error => console.error('Error updating presence:', error));
        }
        
        function updateAllData() {
            const indicator = document.getElementById('updateIndicator');
            indicator.classList.add('show');
            
            updateBoats();
            updateBeacons();
            updatePresence();
            
            setTimeout(() => {
                indicator.classList.remove('show');
            }, 500);
        }

        // Convert RSSI (approx -30..-100 dBm) to 0..100% scale
        function rssiToPercent(rssi) {
            if (rssi === null || rssi === undefined) return 'N/A';
            const max = -30; // very strong
            const min = -100; // very weak
            const clamped = Math.max(min, Math.min(max, rssi));
            const pct = Math.round(((clamped - min) / (max - min)) * 100);
            return pct;
        }
        
        // Update every 3 seconds
        setInterval(updateAllData, 3000);
        
        // Initial load
        updateAllData();
        
        // Beacon Discovery Functions
        let scanInterval = null;
        let discoveredBeacons = new Map();
        let registeredBeacons = new Set();
        
        function openBeaconDiscovery() {
            document.getElementById('beaconModal').style.display = 'block';
            loadRegisteredBeacons();
        }
        
        function closeBeaconDiscovery() {
            document.getElementById('beaconModal').style.display = 'none';
            stopBeaconScan();
        }
        
        function loadRegisteredBeacons() {
            // Only include beacons seen in the last 10 seconds
            fetch('/api/beacons?active_only=1&window=10')
                .then(response => response.json())
                .then(data => {
                    registeredBeacons.clear();
                    // Only consider ASSIGNED beacons as "registered"; leave UNCLAIMED for discovery
                    data.forEach(beacon => {
                        if (beacon.status === 'assigned') {
                            registeredBeacons.add(beacon.mac_address);
                        }
                    });
                })
                .catch(error => console.error('Error loading registered beacons:', error));
        }
        
        function startBeaconScan() {
            document.getElementById('startScanBtn').style.display = 'none';
            document.getElementById('stopScanBtn').style.display = 'inline-block';
            document.getElementById('scanStatus').textContent = 'Scanning for beacons...';
            
            // Start scanning for beacons
            scanInterval = setInterval(scanForBeacons, 2000);
        }
        
        function stopBeaconScan() {
            if (scanInterval) {
                clearInterval(scanInterval);
                scanInterval = null;
            }
            document.getElementById('startScanBtn').style.display = 'inline-block';
            document.getElementById('stopScanBtn').style.display = 'none';
            document.getElementById('scanStatus').textContent = 'Scanning stopped';
        }
        
        function scanForBeacons() {
            // Get real-time detections from scanners (no historical last_seen filtering)
            fetch('/api/active-beacons')
                .then(response => response.json())
                .then(data => {
                    const beaconList = document.getElementById('beaconList');
                    let html = '';
                    
                    // Show beacons that are UNCLAIMED (not yet assigned/registered)
                    // and not already selected for registration in this session
                    const unregisteredBeacons = data.filter(beacon => 
                        beacon.status === 'unclaimed' && !registeredBeacons.has(beacon.mac_address)
                    );
                    
                    if (unregisteredBeacons.length === 0) {
                        html = '<p style="text-align: center; color: #666; padding: 20px;">No new beacons found. Make sure your beacon is nearby and powered on.</p>';
                    } else {
                        unregisteredBeacons.forEach(beacon => {
                            const lastSeen = beacon.last_seen ? 
                                new Date(beacon.last_seen).toLocaleString() : 'Never seen';
                            const rssi = beacon.last_rssi ? `${beacon.last_rssi} dBm` : 'N/A';
                            const displayName = beacon.name || 'Unknown';
                            
                            html += `
                                <div style="
                                    padding: 15px; margin: 10px 0; border-radius: 8px; 
                                    background: #f8f9fa; border-left: 4px solid #007bff;
                                    cursor: pointer; transition: all 0.3s ease;
                                " onclick="selectBeacon('${beacon.mac_address}', '${displayName}')"
                                   onmouseover="this.style.backgroundColor='#e9ecef'; this.style.transform='translateX(5px)'"
                                   onmouseout="this.style.backgroundColor='#f8f9fa'; this.style.transform='translateX(0)'">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <strong style="color: #2c3e50;">${displayName}</strong>
                                            <div style="color: #666; font-size: 0.9rem; margin-top: 5px;">
                                                MAC: <span style="font-family: monospace;">${beacon.mac_address}</span> | RSSI: ${rssi} | Last seen: ${lastSeen}
                                            </div>
                                        </div>
                                        <div style="color: #007bff; font-weight: bold;">Click to Register →</div>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    
                    beaconList.innerHTML = html;
                })
                .catch(error => {
                    console.error('Error scanning for beacons:', error);
                    document.getElementById('scanStatus').textContent = 'Error scanning for beacons';
                });
        }
        
        function selectBeacon(macAddress, beaconName) {
            document.getElementById('beaconMac').value = macAddress;
            document.getElementById('beaconName').value = beaconName;
            document.getElementById('registerModal').style.display = 'block';
            closeBeaconDiscovery();
        }
        
        function closeRegisterModal() {
            document.getElementById('registerModal').style.display = 'none';
            document.getElementById('beaconForm').reset();
        }
        
        function registerBeacon(event) {
            event.preventDefault();
            
            const formData = {
                mac_address: document.getElementById('beaconMac').value,
                name: document.getElementById('beaconName').value,
                boat_name: document.getElementById('boatName').value,
                boat_class: document.getElementById('boatClass').value,
                boat_serial: document.getElementById('boatSerial').value,
                boat_brand: document.getElementById('boatBrand').value,
                boat_notes: document.getElementById('boatNotes').value
            };
            
            // Register the beacon and create the boat
            fetch('/api/register-beacon', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Beacon registered successfully!');
                    closeRegisterModal();
                    updateAllData(); // Refresh the dashboard
                } else {
                    alert('Error registering beacon: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error registering beacon:', error);
                alert('Error registering beacon: ' + error.message);
            });
        }
    </script>
</body>
</html>
        """

def get_default_config():
    """Get default configuration."""
    return {
        'database_path': 'boat_tracking.db',
        'api_host': '0.0.0.0',
        'api_port': 8000,
        'web_host': '0.0.0.0',
        'web_port': 5000,
        'outer_scanner_id': 'gate-outer',
        'inner_scanner_id': 'gate-inner',
        'scanners': [
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
    }

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Boat Tracking System")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--api-port", type=int, default=8000, help="API server port")
    parser.add_argument("--web-port", type=int, default=5000, help="Web dashboard port")
    parser.add_argument("--db-path", default="boat_tracking.db", help="Database file path")
    
    args = parser.parse_args()
    
    # Load configuration
    config = get_default_config()
    if args.config:
        # Load from file (implement if needed)
        pass
    
    # Override with command line args
    config['api_port'] = args.api_port
    config['web_port'] = args.web_port
    config['database_path'] = args.db_path
    
    # Create and start system
    system = BoatTrackingSystem(config)
    
    try:
        system.start()
        logger.info("System running. Press Ctrl+C to stop.")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        system.stop()

if __name__ == "__main__":
    main()
