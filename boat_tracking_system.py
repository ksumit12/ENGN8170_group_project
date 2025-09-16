#!/usr/bin/env python3
"""
Boat Tracking System - Main Orchestrator
Manages scanners, API server, and web dashboard
"""

import time
import threading
import logging
import requests
import argparse
import subprocess
import sys
import traceback
from typing import List, Optional
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # py<3.9 fallback
from flask_cors import CORS

from database_models import DatabaseManager, BoatStatus
from ble_scanner import BLEScanner, ScannerConfig
from api_server import APIServer
import admin_service
from logging_config import get_logger, setup_logging

# Setup comprehensive logging
system_logger = setup_logging()
logger = system_logger

class BoatTrackingSystem:
    def __init__(self, config: dict):
        try:
            self.config = config
            self.db = DatabaseManager(config['database_path'])
            self.api_server = None
            self.scanners: List[BLEScanner] = []
            self.running = False
            
            # Web dashboard
            self.web_app = Flask(__name__)
            CORS(self.web_app)
            self.setup_web_routes()
            # simple settings persistence (file-based to avoid DB migration)
            self.settings_file = 'settings.json'
            
            # Initialize status monitoring
            self.health_check_interval = 30  # seconds
            self.last_health_check = datetime.now(timezone.utc)
            
            logger.info("BoatTrackingSystem initialized successfully", "INIT")
            logger.audit("SYSTEM_INIT", "SYSTEM", f"Config: {config}")
            
        except Exception as e:
            logger.critical(f"Failed to initialize BoatTrackingSystem: {e}", "INIT", e)
            raise
    
    def setup_web_routes(self):
        """Setup web dashboard routes."""
        
        @self.web_app.route('/')
        def dashboard():
            """Main dashboard page."""
            return render_template_string(self.get_dashboard_html())

        @self.web_app.route('/admin')
        def admin_page_root():
            return render_template_string(self.get_admin_login_html())

        @self.web_app.route('/admin/reset', methods=['POST'])
        def admin_reset_endpoint():
            data = request.get_json() or {}
            try:
                if not (data.get('user') and data.get('pass')):
                    return jsonify({'error': 'Unauthorized'}), 401
                if data.get('dry'):
                    return jsonify({'message': 'Auth OK'})
                code, payload = admin_service.admin_reset(self.db)
                return jsonify(payload), code
            except Exception as e:
                logger.exception('admin reset failed')
                return jsonify({'error': str(e)}), 500
        
        @self.web_app.route('/api/boats', methods=['GET','POST'])
        def api_boats():
            """Get or create boats.
            GET: list boats for dashboard
            POST: create boat {id,name,class_type}
            """
            if request.method == 'POST':
                try:
                    data = request.get_json() or {}
                    boat_id = data.get('id') or data.get('boat_id')
                    name = data.get('name') or data.get('display_name')
                    class_type = data.get('class_type') or data.get('class') or 'unknown'
                    if not boat_id or not name:
                        return jsonify({'error':'id and name required'}), 400
                    boat = self.db.create_boat(boat_id, name, class_type)
                    return jsonify({'id': boat.id, 'name': boat.name, 'class_type': boat.class_type}), 201
                except Exception as e:
                    logger.exception('create boat failed')
                    return jsonify({'error': str(e)}), 500
            boats = self.db.get_all_boats()
            result = []
            
            for boat in boats:
                beacon = self.db.get_beacon_by_boat(boat.id)
                if not beacon:
                    # Skip boats with no assigned beacon to avoid clutter
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
            """Get current presence status.
            Use boat status IN_HARBOR (set by background updater) rather than FSM states,
            so single-scanner setups report presence correctly.
            """
            boats = self.db.get_all_boats()
            boats_in_harbor = []
            for b in boats:
                try:
                    status_val = getattr(b.status, 'value', str(b.status))
                except Exception:
                    status_val = str(b.status)
                if status_val == 'in_harbor':
                    beacon = self.db.get_beacon_by_boat(b.id)
                    if beacon:
                        boats_in_harbor.append((b, beacon))

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

        @self.web_app.route('/api/overdue')
        def api_overdue():
            """Return boats that are OUT after closing time (default 20:00 Australia/Sydney)."""
            # load closing time from settings.json
            import json, os
            closing_str = '20:00'
            if os.path.exists(self.settings_file):
                try:
                    with open(self.settings_file,'r') as f:
                        closing_str = json.load(f).get('closing_time', '20:00')
                except Exception:
                    closing_str = '20:00'
            try:
                hh, mm = map(int, closing_str.split(':'))
                # Validate hour and minute ranges
                if not (0 <= hh < 24 and 0 <= mm < 60):
                    hh, mm = 20, 0  # fallback to 20:00
            except Exception:
                hh, mm = 20, 0

            now_utc = datetime.now(timezone.utc)
            if ZoneInfo:
                local = now_utc.astimezone(ZoneInfo('Australia/Sydney'))
            else:
                local = now_utc  # fallback
            try:
                cutoff = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
            except ValueError as e:
                logger.error(f"Invalid closing time {closing_str}: {e}, using 20:00")
                cutoff = local.replace(hour=20, minute=0, second=0, microsecond=0)

            overdue_ids = []
            if local >= cutoff:
                # Any active boat with status OUT is considered on water/overdue
                for boat in self.db.get_all_boats():
                    if boat.status.value == 'out':
                        overdue_ids.append(boat.id)

            return jsonify({
                'closing_time': closing_str,
                'overdue_boat_ids': overdue_ids
            })

        @self.web_app.route('/api/settings/closing-time', methods=['GET','PATCH'])
        def closing_time_setting():
            if request.method == 'GET':
                code, payload = admin_service.get_closing(self.settings_file)
                return jsonify(payload), code
            data = request.get_json() or {}
            code, payload = admin_service.set_closing(self.settings_file, data.get('closing_time',''))
            return jsonify(payload), code

        # remove duplicate admin route if present (no-op placeholder to avoid rebind)

        @self.web_app.route('/reports')
        def reports_page():
            return render_template_string(self.get_reports_html())

        @self.web_app.route('/api/reports/usage')
        def reports_usage():
            """Aggregate outings from detections by pairing EXITED->ENTERED events per boat.
            Returns per-boat totals within optional ISO range.
            """
            from_iso = request.args.get('from')
            to_iso = request.args.get('to')
            boat_id = request.args.get('boatId')
            def parse_iso(s):
                if not s: return None
                try: return datetime.fromisoformat(s.replace('Z','+00:00'))
                except Exception: return None
            start = parse_iso(from_iso)
            end = parse_iso(to_iso)
            # Helper: for each boat -> beacon id
            boats = self.db.get_all_boats()
            summaries = []
            for b in boats:
                if boat_id and b.id != boat_id: continue
                beacon = self.db.get_beacon_by_boat(b.id)
                if not beacon: continue
                with self.db.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT timestamp, state FROM detections
                        WHERE beacon_id = ?
                        ORDER BY timestamp ASC
                    """, (beacon.id,))
                    rows = cur.fetchall()
                # filter by range
                events = []
                for ts, st in rows:
                    t = datetime.fromisoformat(ts) if isinstance(ts,str) else ts
                    if start and t < start: continue
                    if end and t > end: continue
                    events.append((t, st))
                # pair ON_WATER (exited) -> IN_SHED (entered)
                total_minutes = 0
                count = 0
                opened = None
                for t, st in events:
                    if st in ('exited', 'ON_WATER') and opened is None:
                        opened = t
                    elif st in ('entered', 'IN_SHED') and opened is not None:
                        dur = (t - opened).total_seconds()/60.0
                        if dur > 0:
                            total_minutes += int(dur)
                            count += 1
                        opened = None
                summaries.append({'boat_id': b.id, 'total_outings': count, 'total_minutes': total_minutes})
            return jsonify(summaries)

        @self.web_app.route('/api/reports/usage/export.csv')
        def reports_usage_csv():
            import io, csv
            data = request.args.to_dict(flat=True)
            # Reuse JSON endpoint
            with self.web_app.test_request_context('/api/reports/usage', query_string=data):
                resp = reports_usage()
                rows = resp.get_json()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['boat_id','total_outings','total_minutes'])
            for r in rows:
                w.writerow([r['boat_id'], r['total_outings'], r['total_minutes']])
            from flask import Response
            return Response(buf.getvalue(), mimetype='text/csv')
        
        @self.web_app.route('/api/register-beacon', methods=['POST'])
        def register_beacon():
            try:
                data = request.get_json() or {}
                logger.audit("BEACON_REGISTER_ATTEMPT", "WEB", f"MAC: {data.get('mac_address', 'unknown')}")
                
                code, payload = admin_service.register_beacon(self.db, data)
                
                if code == 200:
                    logger.audit("BEACON_REGISTER_SUCCESS", "WEB", f"MAC: {data.get('mac_address')}, Boat: {data.get('boat_name')}")
                else:
                    logger.warning(f"Beacon registration failed: {payload}", "WEB")
                
                return jsonify(payload), code
            except Exception as e:
                logger.error(f"register_beacon failed: {e}", "WEB", e)
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.web_app.route('/api/logs')
        def api_logs():
            """Get recent system logs for monitoring."""
            try:
                log_type = request.args.get('type', 'main')
                count = min(int(request.args.get('count', '50')), 200)  # Limit to 200 entries
                
                if log_type == 'errors':
                    logs = logger.get_recent_errors(count)
                else:
                    logs = logger.get_recent_logs(count)
                
                return jsonify({
                    'logs': [line.strip() for line in logs],
                    'count': len(logs),
                    'type': log_type
                })
            except Exception as e:
                logger.error(f"Failed to get logs: {e}", "API", e)
                return jsonify({'error': str(e)}), 500
        
        @self.web_app.route('/api/status')
        def api_status():
            """Get system status and health information."""
            try:
                status = logger.get_status()
                
                # Add additional runtime status
                status.update({
                    'scanners_count': len(self.scanners),
                    'scanners_running': sum(1 for s in self.scanners if hasattr(s, 'scanning') and s.scanning),
                    'api_server_running': self.api_server is not None,
                    'database_connected': True,  # Will be updated by health check
                    'uptime_seconds': (datetime.now(timezone.utc) - status['system_started']).total_seconds(),
                    'last_health_check': self.last_health_check.isoformat()
                })
                
                return jsonify(status)
            except Exception as e:
                logger.error(f"Failed to get status: {e}", "API", e)
                return jsonify({'error': str(e)}), 500
    
    def start_api_server(self):
        """Start the API server."""
        try:
            self.api_server = APIServer(
                db_path=self.config['database_path'],
                outer_scanner_id=self.config['outer_scanner_id'],
                inner_scanner_id=self.config['inner_scanner_id']
            )
            
            api_thread = threading.Thread(
                target=self._run_api_server,
                daemon=True
            )
            api_thread.start()
            logger.info(f"API server thread started on {self.config['api_host']}:{self.config['api_port']}", "API")
            logger.audit("API_SERVER_START", "SYSTEM", f"Host: {self.config['api_host']}, Port: {self.config['api_port']}")
            
        except Exception as e:
            logger.critical(f"Failed to start API server: {e}", "API", e)
            raise
    
    def _run_api_server(self):
        """Internal method to run API server with error handling."""
        try:
            self.api_server.run(
                host=self.config['api_host'],
                port=self.config['api_port'],
                debug=False
            )
        except Exception as e:
            logger.critical(f"API server crashed: {e}", "API", e)
            logger.update_status('api_healthy', False)
    
    def start_scanners(self):
        """Start BLE scanners."""
        try:
            # Resolve a client-usable API host. 0.0.0.0 is a bind address, not a client address.
            api_host = self.config['api_host']
            client_api_host = 'localhost' if api_host in ('0.0.0.0', '::', '0:0:0:0:0:0:0:0') else api_host
            server_base_url = f"http://{client_api_host}:{self.config['api_port']}"

            for scanner_config in self.config['scanners']:
                try:
                    config = ScannerConfig(
                        scanner_id=scanner_config['id'],
                        server_url=server_base_url,
                        api_key=scanner_config.get('api_key', 'default-key'),
                        rssi_threshold=scanner_config.get('rssi_threshold', -80),
                        scan_interval=scanner_config.get('scan_interval', 1.0)
                    )
                    
                    scanner = BLEScanner(config)
                    scanner.start_scanning()
                    self.scanners.append(scanner)
                    logger.info(f"Scanner {scanner_config['id']} started successfully", "SCANNER")
                    logger.audit("SCANNER_START", "SYSTEM", f"Scanner ID: {scanner_config['id']}")
                    
                except Exception as e:
                    logger.error(f"Failed to start scanner {scanner_config['id']}: {e}", "SCANNER", e)
                    continue
            
            logger.update_status('scanners_active', len(self.scanners))
            
        except Exception as e:
            logger.critical(f"Failed to start scanners: {e}", "SCANNER", e)
            raise
    
    def start_web_dashboard(self):
        """Start web dashboard."""
        try:
            web_thread = threading.Thread(
                target=self._run_web_dashboard,
                daemon=True
            )
            web_thread.start()
            logger.info(f"Web dashboard thread started on {self.config['web_host']}:{self.config['web_port']}", "WEB")
            logger.audit("WEB_DASHBOARD_START", "SYSTEM", f"Host: {self.config['web_host']}, Port: {self.config['web_port']}")
            
        except Exception as e:
            logger.critical(f"Failed to start web dashboard: {e}", "WEB", e)
            raise
    
    def _run_web_dashboard(self):
        """Internal method to run web dashboard with error handling."""
        try:
            self.web_app.run(
                host=self.config['web_host'],
                port=self.config['web_port'],
                debug=False
            )
        except Exception as e:
            logger.critical(f"Web dashboard crashed: {e}", "WEB", e)
    
    def start(self):
        """Start the entire system."""
        try:
            logger.info("Starting Boat Tracking System...", "SYSTEM")
            logger.audit("SYSTEM_START", "SYSTEM", "Boat Tracking System starting")
            
            # Start API server
            self.start_api_server()
            time.sleep(2)  # Give API server time to start
            
            # Start scanners
            self.start_scanners()
            
            # Start web dashboard
            self.start_web_dashboard()
            
            # Start health monitoring
            self._start_health_monitoring()
            
            self.running = True
            logger.info("Boat Tracking System started successfully", "SYSTEM")
            logger.info(f"API Server: http://{self.config['api_host']}:{self.config['api_port']}", "SYSTEM")
            logger.info(f"Web Dashboard: http://{self.config['web_host']}:{self.config['web_port']}", "SYSTEM")
            logger.audit("SYSTEM_START_SUCCESS", "SYSTEM", "All components started successfully")
            
        except Exception as e:
            logger.critical(f"Failed to start Boat Tracking System: {e}", "SYSTEM", e)
            self.stop()  # Cleanup on failure
            raise
    
    def _start_health_monitoring(self):
        """Start background health monitoring thread."""
        def health_monitor():
            while self.running:
                try:
                    self._perform_health_check()
                    time.sleep(self.health_check_interval)
                except Exception as e:
                    logger.error(f"Health check failed: {e}", "HEALTH", e)
                    time.sleep(5)  # Short delay before retry
        
        health_thread = threading.Thread(target=health_monitor, daemon=True)
        health_thread.start()
        logger.info("Health monitoring started", "HEALTH")
    
    def _perform_health_check(self):
        """Perform system health check."""
        try:
            self.last_health_check = datetime.now(timezone.utc)
            
            # Check database connectivity
            try:
                self.db.get_connection()
                logger.update_status('database_healthy', True)
            except Exception as e:
                logger.update_status('database_healthy', False)
                logger.warning(f"Database health check failed: {e}", "HEALTH")
            
            # Check scanner status
            active_scanners = sum(1 for s in self.scanners if hasattr(s, 'scanning') and s.scanning)
            logger.update_status('scanners_running', active_scanners)
            
            # Check API server (basic connectivity test)
            try:
                response = requests.get(f"http://localhost:{self.config['api_port']}/api/v1/health", timeout=5)
                if response.status_code == 200:
                    logger.update_status('api_healthy', True)
                else:
                    logger.update_status('api_healthy', False)
            except Exception:
                logger.update_status('api_healthy', False)
            
            logger.debug("Health check completed", "HEALTH")
            
        except Exception as e:
            logger.error(f"Health check error: {e}", "HEALTH", e)
    
    def stop(self):
        """Stop the entire system."""
        try:
            logger.info("Stopping Boat Tracking System...", "SYSTEM")
            logger.audit("SYSTEM_STOP", "SYSTEM", "Boat Tracking System stopping")
            
            self.running = False
            
            # Stop scanners
            for scanner in self.scanners:
                try:
                    scanner.stop_scanning()
                    logger.info(f"Scanner {getattr(scanner, 'scanner_id', 'unknown')} stopped", "SCANNER")
                except Exception as e:
                    logger.error(f"Error stopping scanner: {e}", "SCANNER", e)
            
            # Clear scanner list
            self.scanners.clear()
            
            logger.info("Boat Tracking System stopped successfully", "SYSTEM")
            logger.audit("SYSTEM_STOP_SUCCESS", "SYSTEM", "All components stopped successfully")
            
        except Exception as e:
            logger.critical(f"Error during system shutdown: {e}", "SYSTEM", e)
    
    def get_dashboard_html(self):
        """Get HTML for the web dashboard."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Red Shed | Boat Tracking</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --red: #e54b4b;         /* Red Shed primary */
            --deep: #113036;        /* Deep teal/green */
            --sand: #6a8f95;        /* Muted accent */
            --ink: #0b1b1e;         /* Dark background */
            --paper: #ffffff;       /* Cards */
            --success: #27ae60;
            --danger: #dc3545;
            --warning: #ffc107;
        }
        body {
            font-family: 'Montserrat', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--ink);
            color: #e9ecef;
            min-height: 100vh;
            padding: 24px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
        .brand { display: flex; align-items: baseline; gap: 12px; }
        .brand h1 { color: var(--paper); font-size: 2rem; letter-spacing: 1px; }
        .brand span { color: var(--sand); font-weight: 600; font-size: 0.95rem; }
        .primary-btn {
            background: var(--red); color: var(--paper); border: none; padding: 12px 20px;
            border-radius: 8px; font-weight: 700; cursor: pointer; letter-spacing: .3px;
            box-shadow: 0 6px 16px rgba(229,75,75,0.25);
        }
        .primary-btn:hover { filter: brightness(1.05); }
        .dashboard { display: grid; grid-template-columns: 1.1fr 1fr 1fr; gap: 20px; }
        @media (max-width: 1100px) { .dashboard { grid-template-columns: 1fr; } }
        .card {
            background: var(--paper); color: #2c3e50; border-radius: 14px; padding: 22px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
        }
        .card h2 { color: var(--deep); margin-bottom: 14px; letter-spacing: 0.5px; }
        .boat-item, .beacon-item {
            padding: 14px; margin: 10px 0; border-radius: 10px; background: #f6f7f8; border-left: 4px solid var(--sand);
        }
        .boat-item.in-harbor { border-left-color: var(--success); }
        .boat-item.out { border-left-color: var(--danger); }
        .beacon-item.assigned { border-left-color: var(--success); }
        .beacon-item.unclaimed { border-left-color: var(--warning); }
        .status-badge { display: inline-block; padding: 4px 8px; border-radius: 12px; font-weight: 700; font-size: 0.75rem; margin-left: 10px; }
        .status-in-harbor { background: #d4edda; color: #155724; }
        .status-out { background: #f8d7da; color: #721c24; }
        .status-assigned { background: #d4edda; color: #155724; }
        .status-unclaimed { background: #fff3cd; color: #856404; }
        .update-indicator { position: fixed; top: 20px; right: 20px; padding: 10px 15px; background: var(--success); color: white; border-radius: 20px; font-size: 0.9rem; font-weight: bold; z-index: 1000; opacity: 0; transition: opacity 0.3s ease; }
        .update-indicator.show { opacity: 1; }
        .rssi-info { font-size: 0.9rem; color: #6c757d; margin-top: 5px; }
        /* Overdue banner blink */
        @keyframes blink { 0%,100% { opacity: .8 } 50% { opacity: .4 } }
        #overdueBanner { opacity: .8; animation: blink 1s linear infinite; }
        /* Whiteboard-first layout */
        .whiteboard-board { background: #fff; color: #222; border-radius: 14px; padding: 18px 18px 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); margin-bottom: 18px; }
        .wb-title { text-align: center; color: var(--red); font-weight: 800; font-size: 1.6rem; letter-spacing: .5px; margin-bottom: 12px; }
        .wb-table { width: 100%; border-collapse: collapse; }
        .wb-table th, .wb-table td { border: 2px solid #ddd; padding: 10px 12px; font-weight: 700; }
        .wb-table th { background: #f7f7f7; color: #333; text-transform: uppercase; letter-spacing: .6px; }
        .wb-status-in { color: #1e7e34; }
        .wb-status-out { color: #b02a37; }
        .subnote { font-weight: 500; color: #666; font-size: .85rem; margin-top: 8px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="brand">
                <h1>Black Mountain Rowing Club</h1>
                <span>Black Mountain Peninsula, Canberra</span>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
                <a href="/admin" class="primary-btn" style="text-decoration:none; display:inline-block;">Admin</a>
                <button class="primary-btn" onclick="openBeaconDiscovery()">+ Register New Beacon</button>
                <button class="primary-btn" onclick="openLogViewer()" style="background:#6c757d;">📋 Logs</button>
            </div>
        </div>
        <div id="overdueBanner" style="display:none; margin:10px 0; padding:12px; background:#b02a37; color:white; border-radius:8px; animation: blink 1s infinite;">
            Overdue boats after closing time
        </div>
        
        <!-- Closing Time Display -->
        <div style="margin:10px 0; padding:8px 12px; background:#f8f9fa; border-left:4px solid #007bff; border-radius:4px; color:#495057;">
            <strong>Closing Time:</strong> <span id="closingTimeDisplay">Loading...</span>
        </div>
        
        <!-- Whiteboard-style priority view -->
        <div class="whiteboard-board">
            <div class="wb-title">Boat Out Board</div>
            <table class="wb-table" id="wbTable">
                <thead>
                    <tr>
                        <th>Boat</th>
                        <th>Status</th>
                        <th>Last Seen</th>
                        <th>Signal</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="4" style="text-align:center; padding:14px; font-weight:600; color:#666;">Loading...</td></tr>
                </tbody>
            </table>
            <div class="subnote">This board updates automatically from live scanner readings.</div>
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
    
    <!-- Log Viewer Modal -->
    <div id="logModal" style="
        display: none; position: fixed; z-index: 1002; left: 0; top: 0; 
        width: 100%; height: 100%; background-color: rgba(0,0,0,0.5);
    ">
        <div style="
            background-color: white; margin: 2% auto; padding: 20px; 
            border-radius: 15px; width: 95%; max-width: 1200px; max-height: 90vh;
            overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="color: #2c3e50; margin: 0;">System Logs & Status</h2>
                <button onclick="closeLogViewer()" style="
                    background: #dc3545; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer; font-size: 1.2rem;
                ">×</button>
            </div>
            
            <div style="margin-bottom: 20px;">
                <button onclick="loadLogs('main')" style="
                    background: #007bff; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer; margin-right: 10px;
                ">Main Logs</button>
                <button onclick="loadLogs('errors')" style="
                    background: #dc3545; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer; margin-right: 10px;
                ">Error Logs</button>
                <button onclick="loadSystemStatus()" style="
                    background: #28a745; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer; margin-right: 10px;
                ">System Status</button>
                <button onclick="refreshLogs()" style="
                    background: #6c757d; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer;
                ">Refresh</button>
            </div>
            
            <div id="logContent" style="
                background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; 
                padding: 15px; max-height: 500px; overflow-y: auto; font-family: monospace; 
                font-size: 12px; white-space: pre-wrap;
            ">
                Click a button above to load logs or status information.
            </div>
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
            
            updateWhiteboard();
            updateBoats();
            updateBeacons();
            updatePresence();
            updateOverdue();
            updateClosingTime();
            
            setTimeout(() => {
                indicator.classList.remove('show');
            }, 500);
        }

        function updateWhiteboard() {
            Promise.all([
                fetch('/api/boats').then(r => r.json()),
                fetch('/api/presence').then(r => r.json())
            ]).then(([boats, presence]) => {
                const tbody = document.querySelector('#wbTable tbody');
                if (!Array.isArray(boats) || boats.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:14px; font-weight:600; color:#666;">No boats registered</td></tr>';
                    return;
                }

                const rows = boats.map(b => {
                    const boatName = b.name;
                    const status = b.status === 'in_harbor' ? '<span class="wb-status-in">IN SHED</span>' : '<span class="wb-status-out">OUT</span>';
                    const lastSeen = b.beacon && b.beacon.last_seen ? new Date(b.beacon.last_seen).toLocaleTimeString() : '—';
                    const signal = b.beacon && b.beacon.last_rssi != null ? `${rssiToPercent(b.beacon.last_rssi)}% (${b.beacon.last_rssi} dBm)` : '—';
                    return `<tr><td>${boatName}</td><td>${status}</td><td>${lastSeen}</td><td>${signal}</td></tr>`;
                }).join('');
                tbody.innerHTML = rows;
            }).catch(() => {
                const tbody = document.querySelector('#wbTable tbody');
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:14px; font-weight:600; color:#666;">Error loading whiteboard</td></tr>';
            });
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

        function updateOverdue() {
            fetch('/api/overdue')
                .then(r => r.json())
                .then(d => {
                    const banner = document.getElementById('overdueBanner');
                    if (d.overdue_boat_ids && d.overdue_boat_ids.length > 0) {
                        banner.style.display = 'block';
                        banner.textContent = `Overdue after ${d.closing_time}: ` + d.overdue_boat_ids.join(', ');
                        banner.style.opacity = 0.8;
                    } else {
                        banner.style.display = 'none';
                    }
                })
                .catch(() => {})
        }
        
        function updateClosingTime() {
            fetch('/api/settings/closing-time')
                .then(r => r.json())
                .then(d => {
                    const display = document.getElementById('closingTimeDisplay');
                    if (display) {
                        display.textContent = d.closing_time || '20:00';
                    }
                })
                .catch(() => {})
        }
        
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
        
        // Log Viewer Functions
        function openLogViewer() {
            document.getElementById('logModal').style.display = 'block';
            loadSystemStatus(); // Load status by default
        }
        
        function closeLogViewer() {
            document.getElementById('logModal').style.display = 'none';
        }
        
        function loadLogs(logType) {
            const logContent = document.getElementById('logContent');
            logContent.textContent = 'Loading logs...';
            
            fetch(`/api/logs?type=${logType}&count=100`)
                .then(response => response.json())
                .then(data => {
                    if (data.logs && data.logs.length > 0) {
                        logContent.textContent = data.logs.join('\\n');
                    } else {
                        logContent.textContent = 'No logs found.';
                    }
                })
                .catch(error => {
                    logContent.textContent = 'Error loading logs: ' + error.message;
                });
        }
        
        function loadSystemStatus() {
            const logContent = document.getElementById('logContent');
            logContent.textContent = 'Loading system status...';
            
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    const statusText = `SYSTEM STATUS
================
System Started: ${new Date(data.system_started).toLocaleString()}
Uptime: ${Math.round(data.uptime_seconds / 60)} minutes
Last Health Check: ${new Date(data.last_health_check).toLocaleString()}

COMPONENT STATUS
================
API Server: ${data.api_server_running ? '✅ Running' : '❌ Stopped'}
Database: ${data.database_healthy ? '✅ Healthy' : '❌ Unhealthy'}
Scanners: ${data.scanners_running}/${data.scanners_count} Active

ERRORS & ISSUES
================
Total Errors: ${data.error_count}
Last Error: ${data.last_error ? new Date(data.last_error.timestamp).toLocaleString() + ' - ' + data.last_error.message : 'None'}

RECENT ACTIVITY
================
Last Scan: ${data.last_scan ? new Date(data.last_scan).toLocaleString() : 'Never'}
Last Detection: ${data.last_detection ? new Date(data.last_detection).toLocaleString() : 'Never'}`;
                    
                    logContent.textContent = statusText;
                })
                .catch(error => {
                    logContent.textContent = 'Error loading status: ' + error.message;
                });
        }
        
        function refreshLogs() {
            // Reload whatever is currently displayed
            const buttons = document.querySelectorAll('#logModal button');
            for (let button of buttons) {
                if (button.style.backgroundColor === 'rgb(40, 167, 69)') { // Green button (System Status)
                    loadSystemStatus();
                    return;
                }
            }
            // Default to main logs if no button is highlighted
            loadLogs('main');
        }
    </script>
</body>
</html>
        """

    def get_admin_login_html(self):
        """Admin login page with reset action. Uses server-side auth via /admin/reset (dry run)."""
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Admin</title>
  <style>
    body{font-family:Segoe UI,Tahoma,Verdana,sans-serif;background:#0b1b1e;color:#e9ecef;padding:24px}
    .card{background:#fff;color:#2c3e50;border-radius:12px;padding:18px;max-width:520px;margin:24px auto;box-shadow:0 10px 30px rgba(0,0,0,.25)}
    input{padding:10px;border:1px solid #ccc;border-radius:6px;width:100%}
    button{padding:10px 16px;border:0;border-radius:6px;cursor:pointer}
    .primary{background:#007bff;color:#fff}
    .danger{background:#dc3545;color:#fff}
    .muted{color:#666;font-size:.9em}
  </style>
  <script>
    let CRED=null;
    async function login(){
      const user=document.getElementById('user').value.trim();
      const pass=document.getElementById('pass').value.trim();
      try{
        const r=await fetch('/admin/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user,pass,dry:true})});
        if(r.status===401){ alert('Unauthorized'); return; }
        if(!r.ok){ alert('Server error'); return; }
        CRED={user,pass};
        document.getElementById('actions').style.display='block';
        loadClosing();
      }catch(e){ alert('Network error: '+e); }
    }
    async function loadClosing(){
      try{
        const d = await fetch('/api/settings/closing-time').then(r=>r.json());
        document.getElementById('closing').value = d.closing_time || '20:00';
      }catch(e){ console.log('closing load failed', e); }
    }
    async function saveClosing(){
      const v = (document.getElementById('closing').value||'').trim();
      if(!/^\d{2}:\d{2}$/.test(v)){ alert('Use HH:MM 24h format'); return; }
      try{
        const r = await fetch('/api/settings/closing-time', {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({closing_time:v})});
        if(r.ok){ alert('Closing time saved'); } else { alert('Save failed'); }
      }catch(e){ alert('Save failed: '+e); }
    }
    async function resetSystem(){
      if(!CRED){ alert('Login first'); return; }
      const r=await fetch('/admin/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(CRED)});
      const t=await r.text();
      if(r.ok){ alert('System reset complete'); } else { alert('Error: '+t); }
    }
  </script>
</head>
<body>
  <div class=\"card\">
    <h2>Admin Login</h2>
    <div style=\"margin:8px 0\"><input id=\"user\" placeholder=\"User ID\" value=\"admin\"></div>
    <div style=\"margin:8px 0\"><input id=\"pass\" type=\"password\" placeholder=\"Password\" value=\"change_this_password\"></div>
    <div style=\"margin:8px 0\"><button class=\"primary\" onclick=\"login()\">Login</button></div>
    <p class=\"muted\">Credentials are configured server-side. Change before production.</p>
  </div>
  <div id=\"actions\" class=\"card\" style=\"display:none\">
    <h2>Admin Actions</h2>
    <div style=\"margin:8px 0; display:flex; gap:8px; align-items:center;\">
      <label for=\"closing\" style=\"min-width:120px;\">Overdue after:</label>
      <input id=\"closing\" placeholder=\"HH:MM\" style=\"flex:0 0 120px\"> <button class=\"primary\" onclick=\"saveClosing()\">Save</button>
    </div>
    <div style=\"display:flex; gap:10px; align-items:center; margin:8px 0\">
      <a href=\"/reports\" style=\"background:#007bff;color:#fff;text-decoration:none;padding:10px 16px;border-radius:6px\">Reports</a>
      <button class=\"danger\" onclick=\"resetSystem()\">Reset: Clear all assignments & states</button>
    </div>
    <p class=\"muted\">This will unassign all beacons, clear FSM states and detections.</p>
  </div>
</body>
</html>
        """

    def get_admin_html(self):
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Admin</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .card { max-width: 480px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px; }
    .row { margin-bottom: 12px; }
    input { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; }
    button { padding: 10px 16px; border: 0; border-radius: 6px; cursor: pointer; }
    .primary { background: #007bff; color: white; }
    .danger { background: #dc3545; color: white; }
    .muted { color: #666; font-size: 0.9em; }
  </style>
  <script>
    async function resetSystem() {
      const user = document.getElementById('user').value.trim();
      const pass = document.getElementById('pass').value.trim();
      if (!user || !pass) { alert('Enter admin user and password'); return; }
      try {
        const resp = await fetch('/admin/reset', { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify({user, pass}) });
        const text = await resp.text();
        if (resp.ok) { alert('System reset complete'); } else { alert('Error: ' + text); }
      } catch (e) { alert('Request failed: ' + e); }
    }
  </script>
</head>
<body>
  <div class=\"card\">
    <h2>Admin Login</h2>
    <div class=\"row\"><input id=\"user\" placeholder=\"User ID\" value=\"admin\"></div>
    <div class=\"row\"><input id=\"pass\" type=\"password\" placeholder=\"Password\" value=\"change_this_password\"></div>
    <div class=\"row\"><button class=\"danger\" onclick=\"resetSystem()\">Reset: Clear all assignments and states</button></div>
    <p class=\"muted\">This will unassign all beacons, clear states and detections. Use with care.</p>
  </div>
</body>
</html>
        """

    def get_admin_html(self):
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Admin</title>
  <style>body{font-family:Segoe UI,Tahoma,Verdana,sans-serif;background:#0b1b1e;color:#e9ecef;padding:24px} .card{background:#fff;color:#2c3e50;border-radius:12px;padding:18px;max-width:900px;margin:0 auto 18px auto;box-shadow:0 10px 30px rgba(0,0,0,.25)} input{padding:8px;border:1px solid #ccc;border-radius:6px}</style>
</head>
<body>
  <div class=\"card\">
    <h2>Closing Time</h2>
    <div><input id=\"closing\" placeholder=\"HH:MM\"> <button onclick=\"saveClosing()\">Save</button></div>
  </div>
  <div class=\"card\">
    <h2>Create Boat</h2>
    <div style=\"display:flex; gap:8px;\">
      <input id=\"bid\" placeholder=\"boat id\">
      <input id=\"bname\" placeholder=\"display name\">
      <input id=\"bclass\" placeholder=\"class (e.g., 4x)\">
      <button onclick=\"createBoat()\">Create</button>
    </div>
  </div>
  <div class=\"card\">
    <h2>Boats</h2>
    <div id=\"boats\">Loading...</div>
  </div>
  <script>
    async function load(){
      const ct=await fetch('/api/settings/closing-time').then(r=>r.json()).catch(()=>({closing_time:'20:00'}));
      document.getElementById('closing').value=ct.closing_time||'20:00';
      const boats=await fetch('/api/boats?includeDeactivated=true').then(r=>r.json());
      document.getElementById('boats').innerHTML = boats.map(b=>`<div style="margin:6px 0;">${b.name} (${b.class_type}) — ${b.status}</div>`).join('')||'None';
    }
    async function saveClosing(){ const v=document.getElementById('closing').value||'20:00'; await fetch('/api/settings/closing-time',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({closing_time:v})}); alert('Saved'); }
    async function createBoat(){ const id=bid.value,name=bname.value,cls=bclass.value||'unknown'; if(!id||!name){alert('id and name required');return;} await fetch('/api/boats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,name:name,class_type:cls})}); load(); }
    load();
  </script>
</body></html>
        """

    def get_reports_html(self):
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Reports</title>
  <style>body{font-family:Segoe UI,Tahoma,Verdana,sans-serif;background:#0b1b1e;color:#e9ecef;padding:24px} .card{background:#fff;color:#2c3e50;border-radius:12px;padding:18px;max-width:900px;margin:0 auto 18px auto;box-shadow:0 10px 30px rgba(0,0,0,.25)} input{padding:8px;border:1px solid #ccc;border-radius:6px} table{width:100%;border-collapse:collapse} th,td{border-bottom:1px solid #eee;padding:8px}</style>
</head>
<body>
  <div class=\"card\">
    <h2>Usage Summary</h2>
    <div style=\"display:flex;gap:8px;margin:8px 0;\">
      <input id=\"from\" placeholder=\"From (ISO)\">
      <input id=\"to\" placeholder=\"To (ISO)\">
      <input id=\"boat\" placeholder=\"Boat ID (optional)\">
      <button onclick=\"run()\">Run</button>
      <a id=\"csv\" href=\"#\" style=\"margin-left:auto\">Export CSV</a>
    </div>
    <table><thead><tr><th>Boat ID</th><th>Total Outings</th><th>Total Minutes</th></tr></thead><tbody id=\"rows\"></tbody></table>
  </div>
  <script>
    async function run(){ const qs=new URLSearchParams(); if(from.value)qs.set('from',from.value); if(to.value)qs.set('to',to.value); if(boat.value)qs.set('boatId',boat.value); const res=await fetch('/api/reports/usage?'+qs.toString()); const data=await res.json(); rows.innerHTML=data.map(r=>`<tr><td>${r.boat_id}</td><td>${r.total_outings}</td><td>${r.total_minutes}</td></tr>`).join(''); csv.href='/api/reports/usage/export.csv?'+qs.toString(); }
    run();
  </script>
</body></html>
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
    try:
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
        
        logger.info(f"Starting Boat Tracking System with config: {config}", "MAIN")
        
        # Create and start system
        system = BoatTrackingSystem(config)
        
        try:
            system.start()
            logger.info("System running. Press Ctrl+C to stop.", "MAIN")
            
            # Keep main thread alive
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user", "MAIN")
            system.stop()
            
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}", "MAIN", e)
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
