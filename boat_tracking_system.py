#!/usr/bin/env python3
"""
Boat Tracking System - Main Orchestrator
Manages scanners, API server, and web dashboard
"""

import os
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

from app.database_models import DatabaseManager, BoatStatus
from ble_scanner import BLEScanner, ScannerConfig
from api_server import APIServer
from app import admin_service
from app.logging_config import get_logger, setup_logging

# Setup comprehensive logging
system_logger = setup_logging()
logger = system_logger

class TerminalDisplay:
    """Terminal-based dashboard for HDMI display on headless Raspberry Pi."""
    
    def __init__(self, db):
        self.db = db
        self.last_update = None
        self.update_interval = 3  # seconds
        
    def clear_screen(self):
        """Clear the terminal screen."""
        import os
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def format_time(self, dt):
        """Format datetime for display."""
        if not dt:
            return "Never"
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except:
                return str(dt)
        return dt.strftime("%H:%M:%S")
    
    def format_date(self, dt):
        """Format date for display."""
        if not dt:
            return "Never"
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except:
                return str(dt)
        return dt.strftime("%m/%d %H:%M")
    
    def rssi_to_percent(self, rssi):
        """Convert RSSI to percentage."""
        if rssi is None:
            return "N/A"
        max_rssi = -30
        min_rssi = -100
        clamped = max(min_rssi, min(max_rssi, rssi))
        pct = round(((clamped - min_rssi) / (max_rssi - min_rssi)) * 100)
        return f"{pct}%"
    
    def get_boat_status_icon(self, status):
        """Get status icon for terminal display."""
        if status == 'in_harbor':
            return "[IN]"  # In harbor
        else:
            return "[OUT]"  # Out of harbor
    
    def update_display(self):
        """Update the terminal display with current data."""
        try:
            # Get current data
            boats = self.db.get_all_boats()
            presence_data = self.get_presence_data()
            
            # Clear screen
            self.clear_screen()
            
            # Header
            print("=" * 80)
            print("BLACK MOUNTAIN ROWING CLUB - BOAT TRACKING SYSTEM")
            print("=" * 80)
            print(f"Date: {datetime.now().strftime('%A, %B %d, %Y')} | Time: {datetime.now().strftime('%H:%M:%S')}")
            print(f"Boats in Shed: {presence_data['total_in_harbor']}")
            print("=" * 80)
            
            # Boat status table
            print("\nBOAT STATUS BOARD")
            print("-" * 80)
            print(f"{'Boat Name':<25} {'Class':<8} {'Status':<12} {'Last Seen':<12} {'Signal':<8}")
            print("-" * 80)
            
            # Sort boats: in_harbor first, then by last seen
            sorted_boats = []
            for boat in boats:
                beacon = self.db.get_beacon_by_boat(boat.id)
                last_seen_ts = 0
                if beacon and beacon.last_seen:
                    ls = beacon.last_seen
                    if isinstance(ls, str):
                        try:
                            ls = datetime.fromisoformat(ls)
                        except:
                            last_seen_ts = 0
                            ls = None
                    if ls:
                        # Ensure timezone awareness
                        if ls.tzinfo is None:
                            ls = ls.replace(tzinfo=timezone.utc)
                        last_seen_ts = ls.timestamp()
                    else:
                        last_seen_ts = 0
                
                sorted_boats.append((boat, beacon, last_seen_ts))
            
            sorted_boats.sort(key=lambda x: (0 if x[0].status.value == 'in_harbor' else 1, -x[2]))
            
            for boat, beacon, last_seen_ts in sorted_boats:
                status_icon = self.get_boat_status_icon(boat.status.value)
                # Better status words: in_harbor -> "IN SHED", out -> "ON WATER"
                if boat.status.value == 'in_harbor':
                    status_text = f"{status_icon} IN SHED"
                elif boat.status.value == 'out':
                    status_text = f"{status_icon} ON WATER"
                else:
                    status_text = f"{status_icon} {boat.status.value.replace('_', ' ').upper()}"
                last_seen = self.format_time(beacon.last_seen) if beacon and beacon.last_seen else "Never"
                signal = f"{self.rssi_to_percent(beacon.last_rssi)}" if beacon and beacon.last_rssi else "N/A"
                
                print(f"{boat.name:<25} {boat.class_type:<8} {status_text:<12} {last_seen:<12} {signal:<8}")
            
            # Currently in shed section
            if presence_data['boats_in_harbor']:
                print(f"\nBOATS CURRENTLY IN SHED ({len(presence_data['boats_in_harbor'])})")
                print("-" * 50)
                for boat_data in presence_data['boats_in_harbor']:
                    signal = self.rssi_to_percent(boat_data['last_rssi'])
                    last_seen = self.format_time(boat_data['last_seen'])
                    print(f"[IN] {boat_data['boat_name']} ({boat_data['boat_class']}) - Signal: {signal} - Last: {last_seen}")
            
            # System status
            print(f"\nSYSTEM STATUS")
            print("-" * 50)
            print(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
            print(f"Database: Connected")
            print(f"Scanners: Active")
            
            # Footer
            print("\n" + "=" * 80)
            print("Press Ctrl+C to stop | Updates every 3 seconds")
            print("=" * 80)
            
            self.last_update = datetime.now()
            
        except Exception as e:
            print(f"Error updating display: {e}")
    
    def get_presence_data(self):
        """Get presence data similar to web API."""
        boats = self.db.get_all_boats()
        boats_in_harbor = []
        
        for boat in boats:
            try:
                status_val = getattr(boat.status, 'value', str(boat.status))
            except Exception:
                status_val = str(boat.status)
                
            if status_val == 'in_harbor':
                beacon = self.db.get_beacon_by_boat(boat.id)
                if beacon:
                    boats_in_harbor.append({
                        'boat_id': boat.id,
                        'boat_name': boat.name,
                        'boat_class': boat.class_type,
                        'beacon_mac': beacon.mac_address,
                        'last_seen': beacon.last_seen,
                        'last_rssi': beacon.last_rssi
                    })
        
        return {
            'boats_in_harbor': boats_in_harbor,
            'total_in_harbor': len(boats_in_harbor)
        }
    
    def start_display_loop(self):
        """Start the terminal display update loop."""
        import threading
        import time
        
        def display_loop():
            while True:
                try:
                    self.update_display()
                    time.sleep(self.update_interval)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Display error: {e}")
                    time.sleep(1)
        
        display_thread = threading.Thread(target=display_loop, daemon=True)
        display_thread.start()
        return display_thread

class BoatTrackingSystem:
    def __init__(self, config: dict, display_mode: str = 'web'):
        try:
            self.config = config
            self.display_mode = display_mode
            self.db = DatabaseManager(config['database_path'])
            self.api_server = None
            self.scanners: List[BLEScanner] = []
            self.running = False
            
            # Web dashboard (only if web mode is enabled)
            if display_mode in ['web', 'both']:
                self.web_app = Flask(__name__)
                CORS(self.web_app)
                self.setup_web_routes()
            else:
                self.web_app = None
                
            # simple settings persistence (file-based to avoid DB migration)
            self.settings_file = 'system/json/settings.json'
            
            # Initialize status monitoring
            self.health_check_interval = 30  # seconds
            self.last_health_check = datetime.now(timezone.utc)
            
            # Terminal display (only if terminal mode is enabled)
            if display_mode in ['terminal', 'both']:
                self.terminal_display = TerminalDisplay(self.db)
            else:
                self.terminal_display = None
            
            logger.info("BoatTrackingSystem initialized successfully", "INIT")
            logger.audit("SYSTEM_INIT", "SYSTEM", f"Config: {config}, Display Mode: {display_mode}")
            
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
                # Proper credential validation
                ADMIN_USER = 'admin_red_shed'
                ADMIN_PASS = 'Bmrc_2025'
                
                user = data.get('user', '').strip()
                password = data.get('pass', '').strip()
                
                if not user or not password:
                    return jsonify({'error': 'Username and password required'}), 401
                
                if user != ADMIN_USER or password != ADMIN_PASS:
                    logger.warning(f"Failed admin login attempt: {user}", "SECURITY")
                    return jsonify({'error': 'Invalid credentials'}), 401
                
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
            try:
                boats = self.db.get_all_boats()
                result = []
                
                for boat in boats:
                    beacon = self.db.get_beacon_by_boat(boat.id)
                    if not beacon:
                        # Skip boats with no assigned beacon to avoid clutter
                        continue
                    beacon_state = None
                    last_seen_ts = 0
                    entry_ts = None
                    exit_ts = None
                    if beacon and beacon.last_seen:
                        ls = beacon.last_seen
                        if isinstance(ls, str):
                            try:
                                ls = datetime.fromisoformat(ls)
                            except Exception:
                                last_seen_ts = 0
                                ls = None
                        if ls:
                            # Ensure timezone awareness
                            if ls.tzinfo is None:
                                ls = ls.replace(tzinfo=timezone.utc)
                            last_seen_ts = ls.timestamp()
                        else:
                            last_seen_ts = 0
                    # Use event-based summary for today's timestamps
                    summary = None
                    entry_ts = None
                    exit_ts = None
                    try:
                        summary = self.db.summarize_today(boat.id)
                        # Map event-based timestamps to API fields
                        if summary['in_shed_ts_local']:
                            entry_ts = summary['in_shed_ts_local']
                        if summary['on_water_ts_local']:
                            exit_ts = summary['on_water_ts_local']
                        # Override boat status with event-based status
                        event_status = summary['status']
                    except Exception as e:
                        # Fallback to old method if event system fails
                        logger.debug(f"Event summary failed for {boat.id}, using fallback: {e}")
                        event_status = boat.status.value
                        try:
                            with self.db.get_connection() as conn:
                                c = conn.cursor()
                                c.execute("SELECT entry_timestamp, exit_timestamp FROM beacon_states WHERE beacon_id = ?", (beacon.id,))
                                row = c.fetchone()
                                if row:
                                    entry_ts = row[0]
                                    exit_ts = row[1]
                        except Exception:
                            entry_ts = None
                            exit_ts = None
                    
                    # Get water time today for this boat
                    water_time_today = 0
                    try:
                        water_time_today = self.db.get_boat_water_time_today(boat.id)
                    except Exception:
                        pass
                    
                    result.append({
                        'id': boat.id,
                        'name': boat.name,
                        'class_type': boat.class_type,
                        'status': event_status if summary else boat.status.value,
                        'op_status': getattr(boat, 'op_status', 'ACTIVE'),
                        'status_updated_at': getattr(boat, 'status_updated_at', None),
                        'last_entry': (entry_ts.isoformat() if hasattr(entry_ts, 'isoformat') else entry_ts) if entry_ts else None,
                        'last_exit': (exit_ts.isoformat() if hasattr(exit_ts, 'isoformat') else exit_ts) if exit_ts else None,
                        'water_time_today_minutes': water_time_today,
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
            except Exception as e:
                logger.exception('GET /api/boats failed')
                # Fail soft to avoid breaking the whiteboard; caller shows a friendly message
                return jsonify([])

        @self.web_app.route('/api/fsm-states')
        def api_fsm_states():
            """Return current FSM states per beacon with boat context for live viewers."""
            rows = []
            try:
                with self.db.get_connection() as conn:
                    c = conn.cursor()
                    c.execute(
                        """
                        SELECT bs.beacon_id,
                               bs.current_state,
                               bs.entry_timestamp,
                               bs.exit_timestamp,
                               b.id as boat_id,
                               b.name as boat_name,
                               be.mac_address
                        FROM beacon_states bs
                        LEFT JOIN boat_beacon_assignments ba ON ba.beacon_id = bs.beacon_id AND ba.is_active = 1
                        LEFT JOIN boats b ON b.id = ba.boat_id
                        LEFT JOIN beacons be ON be.id = bs.beacon_id
                        ORDER BY b.name
                        """
                    )
                    for r in c.fetchall():
                        rows.append({
                            'beacon_id': r[0],
                            'state': r[1],
                            'entry_timestamp': r[2],
                            'exit_timestamp': r[3],
                            'boat_id': r[4],
                            'boat_name': r[5],
                            'mac_address': r[6],
                        })
            except Exception as e:
                logger.exception('api_fsm_states failed')
                return jsonify({'error': str(e)}), 500
            return jsonify(rows)

        @self.web_app.route('/api/fsm-profile')
        def api_fsm_profile():
            """Report which scanner profile is expected given current Git branch/env.
            Mirrors the scanner_service auto-selection logic for viewer awareness.
            """
            try:
                import os, subprocess
                profile = 'inside_outside'
                branch = os.getenv('GIT_BRANCH')
                if not branch:
                    try:
                        # Determine repo root relative to this file
                        import pathlib
                        repo_dir = str(pathlib.Path(__file__).resolve().parent)
                        branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo_dir, text=True).strip()
                    except Exception:
                        branch = 'main'
                # Env override
                forced = os.getenv('FSM_PROFILE')
                if forced in ('door_left_right', 'inside_outside'):
                    profile = forced
                else:
                    profile = 'inside_outside' if branch == 'main' else 'door_left_right'
                return jsonify({'branch': branch, 'profile': profile})
            except Exception as e:
                return jsonify({'branch': None, 'profile': 'inside_outside', 'error': str(e)})

        @self.web_app.route('/fsm')
        def fsm_viewer_page():
            """Simple GUI viewer for FSM states with Mermaid diagram and live updates."""
            return render_template_string(self.get_fsm_viewer_html())
        
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
        
        @self.web_app.route('/api/events/<boat_id>')
        def api_events(boat_id):
            """Get today's events for a boat (for debugging)."""
            try:
                events = self.db.get_events_for_boat(boat_id)
                summary = self.db.summarize_today(boat_id)
                return jsonify({
                    'events': [{
                        'type': e['event_type'],
                        'time': e['ts_local'].isoformat() if e['ts_local'] else None
                    } for e in events],
                    'summary': {
                        'status': summary['status'],
                        'on_water_ts': summary['on_water_ts_local'].isoformat() if summary['on_water_ts_local'] else None,
                        'in_shed_ts': summary['in_shed_ts_local'].isoformat() if summary['in_shed_ts_local'] else None
                    }
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
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
                    try:
                        dt = datetime.fromisoformat(ls)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.isoformat()
                    except:
                        return ls
                try:
                    if ls.tzinfo is None:
                        ls = ls.replace(tzinfo=timezone.utc)
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
            # load closing time from system/json/settings.json
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
                        # Show human-friendly boat names instead of IDs
                        overdue_ids.append(boat.name)
            
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

        @self.web_app.route('/manage')
        def manage_page():
            return render_template_string(self.get_manage_html())

        # Search API (UI local) - case-insensitive, prefix + substring
        @self.web_app.route('/api/v1/boats/search')
        def ui_search_boats():
            try:
                q = (request.args.get('q') or '').strip()
                limit = request.args.get('limit')
                items = self.db.search_boats_by_name(q, int(limit) if limit else 20) if q else []
                return jsonify(items)
            except Exception as e:
                logger.error(f"Search error: {e}")
                return jsonify([])

        @self.web_app.route('/api/v1/boats/by-name')
        def ui_boat_by_name():
            try:
                name = (request.args.get('name') or '').strip()
                if not name:
                    return jsonify({'error':'name required'}), 400
                # exact match ignoring case
                matches = self.db.search_boats_by_name(name, 1)
                for b in matches:
                    if b['name'].lower() == name.lower():
                        return jsonify(b)
                return jsonify(None), 404
            except Exception as e:
                logger.error(f"Lookup error: {e}")
                return jsonify({'error': str(e)}), 500

        # Mirror management endpoints locally so Manage page can PATCH on same origin
        @self.web_app.route('/api/v1/boats/<boat_id>/status', methods=['PATCH'])
        def ui_patch_boat_status(boat_id):
            try:
                data = request.get_json() or {}
                status = data.get('status')
                if status not in ('ACTIVE','MAINTENANCE','RETIRED'):
                    return jsonify({'error': 'Invalid status'}), 400
                # Persist op_status directly via DB helper
                self.db.set_boat_op_status(boat_id, status)
                return jsonify({'ok': True})
            except Exception as e:
                logger.error(f"ui_patch_boat_status failed: {e}")
                return jsonify({'error': str(e)}), 500

        @self.web_app.route('/api/v1/boats/<boat_id>/replace-beacon', methods=['POST'])
        def ui_replace_beacon(boat_id):
            try:
                data = request.get_json() or {}
                new_mac = (data.get('new_mac') or '').strip()
                if not new_mac:
                    return jsonify({'error': 'new_mac required'}), 400
                beacon = self.db.replace_beacon_for_boat(boat_id, new_mac)
                return jsonify({'ok': True, 'beacon_mac': beacon.mac_address})
            except Exception as e:
                logger.error(f"ui_replace_beacon failed: {e}")
                return jsonify({'error': str(e)}), 500

        @self.web_app.route('/api/v1/presence/<boat_id>')
        def ui_boat_presence(boat_id):
            try:
                boat = self.db.get_boat(boat_id)
                if not boat:
                    return jsonify({'error': 'Boat not found'}), 404
                beacon = self.db.get_beacon_by_boat(boat_id)
                in_harbor = False
                last_seen = None
                last_rssi = None
                if beacon and beacon.last_seen:
                    ls = beacon.last_seen
                    if isinstance(ls, str):
                        try:
                            ls = datetime.fromisoformat(ls)
                        except Exception:
                            ls = None
                    if ls and ls.tzinfo is None:
                        ls = ls.replace(tzinfo=timezone.utc)
                    
                    last_seen = ls.isoformat() if ls else None
                    last_rssi = beacon.last_rssi
                    
                    # simple recency check (8s window)
                    if ls:
                        in_harbor = (datetime.now(timezone.utc) - ls).total_seconds() <= 8
                else:
                    in_harbor = False
                return jsonify({
                    'boat_id': boat.id,
                    'boat_name': boat.name,
                    'op_status': getattr(boat, 'op_status', None),
                    'beacon_id': beacon.id if beacon else None,
                    'beacon_mac': beacon.mac_address if beacon else None,
                    'status': 'entered' if in_harbor else 'out',
                    'in_harbor': in_harbor,
                    'last_seen': last_seen,
                    'last_rssi': last_rssi
                })
            except Exception as e:
                logger.error(f"ui_boat_presence failed: {e}")
                return jsonify({'error': str(e)}), 500

        @self.web_app.route('/api/reports/usage')
        def reports_usage():
            """Aggregate outings from detections by pairing EXITED->ENTERED events per boat.
            Returns per-boat totals within optional ISO range with detailed boat information.
            Optional: includeSessions=1 to also return session list per boat.
            """
            from_iso = request.args.get('from')
            to_iso = request.args.get('to')
            boat_id = request.args.get('boatId')
            include_sessions = request.args.get('includeSessions') in ('1','true','True')
            def parse_iso(s):
                if not s: return None
                try: 
                    dt = datetime.fromisoformat(s.replace('Z','+00:00'))
                    # Ensure timezone awareness
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception: return None
            start = parse_iso(from_iso)
            end = parse_iso(to_iso)
            # Helper: Use event-based system instead of old detections
            boats = self.db.get_all_boats()
            summaries = []
            
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo('Australia/Canberra')
            except:
                tz = timezone.utc
            
            for b in boats:
                if boat_id and b.id != boat_id: continue
                beacon = self.db.get_beacon_by_boat(b.id)
                if not beacon: continue
                
                # Get all shed_events for this boat in date range
                with self.db.get_connection() as conn:
                    cur = conn.cursor()
                    
                    if start and end:
                        cur.execute("""
                            SELECT event_type, ts_utc FROM shed_events
                            WHERE boat_id = ? AND ts_utc >= ? AND ts_utc <= ?
                            ORDER BY ts_utc ASC
                        """, (b.id, start, end))
                    else:
                        cur.execute("""
                            SELECT event_type, ts_utc FROM shed_events
                            WHERE boat_id = ?
                            ORDER BY ts_utc ASC
                        """, (b.id,))
                    
                    event_rows = cur.fetchall()
                
                # Pair OUT_SHED -> IN_SHED as sessions
                total_minutes = 0
                count = 0
                opened = None
                sessions = []
                
                for event_type, ts_utc_str in event_rows:
                    ts_utc = datetime.fromisoformat(ts_utc_str) if isinstance(ts_utc_str, str) else ts_utc_str
                    if ts_utc.tzinfo is None:
                        ts_utc = ts_utc.replace(tzinfo=timezone.utc)
                    
                    if event_type == 'OUT_SHED' and opened is None:
                        opened = ts_utc
                    elif event_type == 'IN_SHED' and opened is not None:
                        dur = (ts_utc - opened).total_seconds() / 60.0
                        # Include ALL sessions, even 0-minute ones (quick in/out)
                        total_minutes += max(0, int(dur))
                        count += 1
                        if include_sessions:
                            sessions.append({
                                'start': opened.isoformat(), 
                                'end': ts_utc.isoformat(), 
                                'minutes': int(dur)
                            })
                        opened = None
                
                # Get additional boat details
                op_status = getattr(b, 'op_status', 'ACTIVE')
                last_seen = beacon.last_seen.isoformat() if beacon.last_seen else None
                last_rssi = beacon.last_rssi
                
                item = {
                    'boat_id': b.id, 
                    'boat_name': b.name,
                    'boat_class': b.class_type,
                    'boat_notes': b.notes,
                    'op_status': op_status,
                    'beacon_mac': beacon.mac_address,
                    'last_seen': last_seen,
                    'last_rssi': last_rssi,
                    'total_outings': count, 
                    'total_minutes': total_minutes,
                    'avg_duration': round(total_minutes / count, 1) if count > 0 else 0
                }
                if include_sessions:
                    item['sessions'] = sessions
                summaries.append(item)
            return jsonify(summaries)

        @self.web_app.route('/api/reports/usage/export.csv')
        def reports_usage_csv():
            import io, csv
            from flask import Response
            
            data = request.args.to_dict(flat=True)
            include_trips = data.get('includeTrips', '0') == '1'
            
            buf = io.StringIO()
            w = csv.writer(buf)
            
            if include_trips:
                # Export detailed trip logs from shed_events
                from_date = data.get('from')
                to_date = data.get('to')
                boat_id_filter = data.get('boatId')
                
                # Parse dates
                if from_date:
                    start_dt = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
                else:
                    start_dt = datetime.now(timezone.utc) - timedelta(days=30)
                
                if to_date:
                    end_dt = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
                else:
                    end_dt = datetime.now(timezone.utc)
                
                # Get all boats
                boats = self.db.get_all_boats()
                
                # Write header
                w.writerow(['Sequence', 'Boat Name', 'Boat Class', 'Exit Time', 'Entry Time', 'Duration (min)'])
                
                # Collect all sessions from shed_events
                sequence = 1
                for boat in boats:
                    if boat_id_filter and boat.id != boat_id_filter:
                        continue
                    
                    beacon = self.db.get_beacon_by_boat(boat.id)
                    if not beacon:
                        continue
                    
                    # Get shed_events for this boat
                    with self.db.get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT event_type, ts_utc FROM shed_events
                            WHERE boat_id = ? AND ts_utc >= ? AND ts_utc <= ?
                            ORDER BY ts_utc ASC
                        """, (boat.id, start_dt.isoformat(), end_dt.isoformat()))
                        events = cur.fetchall()
                    
                    # Pair OUT -> IN as sessions
                    opened = None
                    for event_type, ts_utc_str in events:
                        ts_utc = datetime.fromisoformat(ts_utc_str) if isinstance(ts_utc_str, str) else ts_utc_str
                        if ts_utc.tzinfo is None:
                            ts_utc = ts_utc.replace(tzinfo=timezone.utc)
                        
                        if event_type == 'OUT_SHED' and opened is None:
                            opened = ts_utc
                        elif event_type == 'IN_SHED' and opened is not None:
                            duration = int((ts_utc - opened).total_seconds() / 60.0)
                            # Include ALL sessions, even 0-minute ones
                            w.writerow([
                                sequence,
                                boat.name,
                                boat.class_type,
                                opened.strftime('%Y-%m-%d %H:%M:%S'),
                                ts_utc.strftime('%Y-%m-%d %H:%M:%S'),
                                duration
                            ])
                            sequence += 1
                            opened = None
            else:
                # Export summary data
                with self.web_app.test_request_context('/api/reports/usage', query_string=data):
                    resp = reports_usage()
                    rows = resp.get_json()
                
                w.writerow([
                    'boat_id', 'boat_name', 'boat_class', 'op_status', 'beacon_mac', 
                    'last_seen', 'last_rssi', 'total_outings', 'total_minutes', 'avg_duration', 'boat_notes'
                ])
                for r in rows:
                    w.writerow([
                        r['boat_id'], r['boat_name'], r['boat_class'], r['op_status'], 
                        r['beacon_mac'], r['last_seen'], r['last_rssi'], r['total_outings'], 
                        r['total_minutes'], r['avg_duration'], r['boat_notes']
                    ])
            
            # Set filename from query param or generate default
            filename = data.get('filename', 'boat_usage_report.csv')
            
            response = Response(buf.getvalue(), mimetype='text/csv')
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        
        @self.web_app.route('/api/boats/list')
        def api_boats_list():
            """Get list of all boats for dropdown selection."""
            try:
                boats = self.db.get_all_boats()
                boat_list = []
                for boat in boats:
                    op_status = getattr(boat, 'op_status', 'ACTIVE')
                    boat_list.append({
                        'id': boat.id,
                        'name': boat.name,
                        'class_type': boat.class_type,
                        'op_status': op_status,
                        'display_name': f"{boat.name} ({boat.class_type})" + (f" - {op_status}" if op_status != 'ACTIVE' else "")
                    })
                return jsonify(boat_list)
            except Exception as e:
                logger.error(f"Failed to get boats list: {e}", "API", e)
                return jsonify({'error': str(e)}), 500

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
        
        @self.web_app.route('/api/logs/export', methods=['POST'])
        def export_logs():
            """Export logs with date/time range selection."""
            try:
                data = request.get_json() or {}
                start_date = data.get('start_date')
                end_date = data.get('end_date')
                export_type = data.get('type', 'all')  # all, errors, main
                
                if not start_date or not end_date:
                    return jsonify({'error': 'start_date and end_date are required'}), 400
                
                # Parse dates
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                except ValueError:
                    return jsonify({'error': 'Invalid date format. Use ISO format.'}), 400
                
                # Generate filename
                filename = f"boat_tracking_logs_{start_dt.strftime('%Y%m%d_%H%M')}_to_{end_dt.strftime('%Y%m%d_%H%M')}.csv"
                
                # Export logs
                log_data = self._export_logs_by_date_range(start_dt, end_dt, export_type)
                
                # Create CSV response
                import io
                import csv
                from flask import Response
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write header
                writer.writerow(['timestamp', 'level', 'component', 'message'])
                
                # Write log entries
                for entry in log_data:
                    writer.writerow([
                        entry.get('timestamp', ''),
                        entry.get('level', ''),
                        entry.get('component', ''),
                        entry.get('message', '')
                    ])
                
                output.seek(0)
                
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
                
            except Exception as e:
                logger.error(f"Failed to export logs: {e}", "API", e)
                return jsonify({'error': str(e)}), 500
        
        @self.web_app.route('/api/logs/export/weekly', methods=['POST'])
        def export_weekly_logs():
            """Export logs for the past week."""
            try:
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=7)
                
                # Generate filename
                filename = f"boat_tracking_weekly_logs_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
                
                # Export logs
                log_data = self._export_logs_by_date_range(start_date, end_date, 'all')
                
                # Create CSV response
                import io
                import csv
                from flask import Response
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write header
                writer.writerow(['timestamp', 'level', 'component', 'message'])
                
                # Write log entries
                for entry in log_data:
                    writer.writerow([
                        entry.get('timestamp', ''),
                        entry.get('level', ''),
                        entry.get('component', ''),
                        entry.get('message', '')
                    ])
                
                output.seek(0)
                
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
                
            except Exception as e:
                logger.error(f"Failed to export weekly logs: {e}", "API", e)
                return jsonify({'error': str(e)}), 500
        
        @self.web_app.route('/api/boats/export-sessions', methods=['POST'])
        def export_boat_sessions():
            """Export all boat sessions from events (each trip as separate row)."""
            try:
                import io, csv
                from flask import Response
                
                data = request.get_json() or {}
                boat_id = data.get('boat_id')  # Optional filter
                days = int(data.get('days', 7))  # Last N days
                
                # Get date range
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo('Australia/Canberra')
                except:
                    tz = timezone.utc
                
                end_date = datetime.now(tz).date()
                start_date = end_date - timedelta(days=days)
                
                # Collect all sessions from events
                sessions = []
                boats = [self.db.get_boat(boat_id)] if boat_id else self.db.get_all_boats()
                
                for boat in boats:
                    if not boat:
                        continue
                    
                    # Get events for each day in range
                    current_date = start_date
                    while current_date <= end_date:
                        events = self.db.get_events_for_boat(boat.id, current_date)
                        
                        # Pair OUT/IN events as sessions
                        i = 0
                        while i < len(events):
                            if events[i]['event_type'] == 'OUT_SHED':
                                out_event = events[i]
                                in_event = None
                                
                                # Find matching IN event
                                if i + 1 < len(events) and events[i + 1]['event_type'] == 'IN_SHED':
                                    in_event = events[i + 1]
                                    i += 2
                                else:
                                    i += 1
                                
                                # Calculate duration
                                if in_event:
                                    duration_sec = (in_event['ts_utc'] - out_event['ts_utc']).total_seconds()
                                    duration_min = int(duration_sec / 60)
                                    duration_hr = round(duration_sec / 3600, 2)
                                    status = 'Completed'
                                else:
                                    duration_min = None
                                    duration_hr = None
                                    status = 'Still Out'
                                
                                sessions.append({
                                    'boat_id': boat.id,
                                    'boat_name': boat.name,
                                    'boat_class': boat.class_type,
                                    'date': current_date.isoformat(),
                                    'left_shed': out_event['ts_local'].strftime('%Y-%m-%d %H:%M:%S'),
                                    'returned_shed': in_event['ts_local'].strftime('%Y-%m-%d %H:%M:%S') if in_event else '—',
                                    'duration_minutes': duration_min or '—',
                                    'duration_hours': duration_hr or '—',
                                    'status': status
                                })
                            else:
                                i += 1
                        
                        current_date += timedelta(days=1)
                
                # Create CSV
                output = io.StringIO()
                writer = csv.writer(output)
                
                writer.writerow([
                    'Boat ID', 'Boat Name', 'Class', 'Date', 
                    'Left Shed (Time Out)', 'Returned Shed (Time In)', 
                    'Duration (Minutes)', 'Duration (Hours)', 'Status'
                ])
                
                for session in sessions:
                    writer.writerow([
                        session['boat_id'],
                        session['boat_name'],
                        session['boat_class'],
                        session['date'],
                        session['left_shed'],
                        session['returned_shed'],
                        session['duration_minutes'],
                        session['duration_hours'],
                        session['status']
                    ])
                
                output.seek(0)
                filename = f"boat_sessions_{start_date.isoformat()}_to_{end_date.isoformat()}.csv"
                
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
                
            except Exception as e:
                logger.error(f"Failed to export sessions: {e}", "API")
                return jsonify({'error': str(e)}), 500
        
        @self.web_app.route('/api/boats/export-water-time', methods=['POST'])
        def export_boat_water_time():
            """Export boat water time data with date range selection."""
            try:
                data = request.get_json() or {}
                start_date = data.get('start_date')
                end_date = data.get('end_date')
                boat_id = data.get('boat_id')  # Optional: specific boat
                
                if not start_date or not end_date:
                    return jsonify({'error': 'start_date and end_date are required'}), 400
                
                # Parse dates
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                except ValueError:
                    return jsonify({'error': 'Invalid date format. Use ISO format.'}), 400
                
                # Generate filename
                if boat_id:
                    filename = f"boat_water_time_{boat_id}_{start_dt.strftime('%Y%m%d')}_to_{end_dt.strftime('%Y%m%d')}.csv"
                else:
                    filename = f"all_boats_water_time_{start_dt.strftime('%Y%m%d')}_to_{end_dt.strftime('%Y%m%d')}.csv"
                
                # Get boat water time data
                water_time_data = self._export_boat_water_time_data(start_dt, end_dt, boat_id)
                
                # Create CSV response
                import io
                import csv
                from flask import Response
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write header with enhanced maintenance insights
                writer.writerow([
                    'sequence_number', 'boat_id', 'boat_name', 'boat_class', 'trip_date', 
                    'exit_time', 'entry_time', 'duration_minutes', 'duration_hours', 
                    'trip_id', 'movement_type', 'time_since_last_trip_minutes',
                    'daily_trip_count', 'weekly_trip_count', 'maintenance_notes'
                ])
                
                # Write water time data with enhanced insights
                for i, entry in enumerate(water_time_data, 1):
                    writer.writerow([
                        i,  # sequence_number
                        entry.get('boat_id', ''),
                        entry.get('boat_name', ''),
                        entry.get('boat_class', ''),
                        entry.get('trip_date', ''),
                        entry.get('exit_time', ''),
                        entry.get('entry_time', ''),
                        entry.get('duration_minutes', ''),
                        entry.get('duration_hours', ''),
                        entry.get('trip_id', ''),
                        entry.get('movement_type', ''),
                        entry.get('time_since_last_trip_minutes', ''),
                        entry.get('daily_trip_count', ''),
                        entry.get('weekly_trip_count', ''),
                        entry.get('maintenance_notes', '')
                    ])
                
                output.seek(0)
                
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
                
            except Exception as e:
                logger.error(f"Failed to export boat water time: {e}", "API", e)
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

            # Detect available BLE adapters (hci*) so we can skip missing ones gracefully
            import os, glob
            present_adapters = {os.path.basename(p) for p in glob.glob('/sys/class/bluetooth/hci*')}
            # Fallback: if sysfs missing, try hciconfig output
            if not present_adapters:
                try:
                    out = subprocess.check_output(['hciconfig'], text=True)
                    present_adapters = {line.split(':')[0] for line in out.splitlines() if line.startswith('hci')}
                except Exception:
                    present_adapters = set()
            
            # SINGLE_SCANNER override: if env set, only start the specified scanner
            single_scanner = os.getenv('SINGLE_SCANNER', '0') == '1'
            preferred_id = os.getenv('SCANNER_ID')
            
            for scanner_config in self.config['scanners']:
                try:
                    # Skip scanners if in single-scanner mode and this isn't the preferred one
                    if single_scanner and preferred_id and scanner_config.get('id') != preferred_id:
                        logger.info(f"Skipping scanner {scanner_config['id']} - single scanner mode, using {preferred_id}", "SCANNER")
                        continue
                    
                    adapter = scanner_config.get('adapter', None)
                    if adapter and present_adapters and adapter not in present_adapters:
                        logger.warning(f"Skipping scanner {scanner_config['id']} - adapter {adapter} not found (present: {sorted(present_adapters)})", "SCANNER")
                        continue
                    config = ScannerConfig(
                        scanner_id=scanner_config['id'],
                        server_url=server_base_url,
                        api_key=scanner_config.get('api_key', 'default-key'),
                        rssi_threshold=scanner_config.get('rssi_threshold', -80),
                        scan_interval=scanner_config.get('scan_interval', 1.0),
                        adapter=adapter,
                        active_window_seconds=scanner_config.get('active_window_seconds', 6)
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
            # Check if SSL certificates exist for HTTPS
            ssl_cert = 'ssl/cert.pem'
            ssl_key = 'ssl/key.pem'
            
            if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
                # Run with HTTPS
                logger.info("Starting web dashboard with HTTPS", "WEB")
                self.web_app.run(
                    host=self.config['web_host'],
                    port=self.config['web_port'],
                    debug=False,
                    ssl_context=(ssl_cert, ssl_key)
                )
            else:
                # Run with HTTP (fallback)
                logger.warning("SSL certificates not found. Running with HTTP.", "WEB")
                logger.warning("Run ./generate_ssl_cert.sh to enable HTTPS", "WEB")
                self.web_app.run(
                    host=self.config['web_host'],
                    port=self.config['web_port'],
                    debug=False
                )
        except Exception as e:
            logger.critical(f"Web dashboard crashed: {e}", "WEB", e)
    
    def start_terminal_display(self):
        """Start terminal display for HDMI output."""
        try:
            if self.terminal_display:
                self.terminal_display.start_display_loop()
                logger.info("Terminal display started successfully", "TERMINAL")
                logger.audit("TERMINAL_DISPLAY_START", "SYSTEM", "Terminal display started for HDMI output")
            else:
                logger.warning("Terminal display not initialized", "TERMINAL")
        except Exception as e:
            logger.critical(f"Failed to start terminal display: {e}", "TERMINAL", e)
            raise
    
    def _export_logs_by_date_range(self, start_date, end_date, export_type='all'):
        """Export logs within a date range."""
        try:
            # This is a simplified implementation - in a real system, you'd query log files
            # For now, we'll return a placeholder structure
            log_entries = []
            
            # In a real implementation, you would:
            # 1. Read log files from the logging system
            # 2. Parse timestamps and filter by date range
            # 3. Filter by log type (all, errors, main)
            # 4. Return structured log data
            
            # Placeholder implementation
            log_entries.append({
                'timestamp': start_date.isoformat(),
                'level': 'INFO',
                'component': 'SYSTEM',
                'message': f'Log export requested for {start_date} to {end_date}'
            })
            
            return log_entries
            
        except Exception as e:
            logger.error(f"Failed to export logs by date range: {e}", "EXPORT", e)
            return []
    
    def _export_boat_water_time_data(self, start_date, end_date, boat_id=None):
        """Export boat water time data within a date range with enhanced maintenance insights."""
        try:
            water_time_data = []
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build query based on whether we want specific boat or all boats
                if boat_id:
                    query = """
                        SELECT 
                            bt.boat_id,
                            b.name as boat_name,
                            b.class_type as boat_class,
                            bt.trip_date,
                            bt.exit_time,
                            bt.entry_time,
                            bt.duration_minutes,
                            bt.id as trip_id
                        FROM boat_trips bt
                        JOIN boats b ON bt.boat_id = b.id
                        WHERE bt.trip_date >= ? AND bt.trip_date <= ? 
                        AND bt.boat_id = ?
                        AND bt.duration_minutes IS NOT NULL
                        ORDER BY bt.exit_time ASC
                    """
                    params = (start_date.date(), end_date.date(), boat_id)
                else:
                    query = """
                        SELECT 
                            bt.boat_id,
                            b.name as boat_name,
                            b.class_type as boat_class,
                            bt.trip_date,
                            bt.exit_time,
                            bt.entry_time,
                            bt.duration_minutes,
                            bt.id as trip_id
                        FROM boat_trips bt
                        JOIN boats b ON bt.boat_id = b.id
                        WHERE bt.trip_date >= ? AND bt.trip_date <= ? 
                        AND bt.duration_minutes IS NOT NULL
                        ORDER BY bt.exit_time ASC
                    """
                    params = (start_date.date(), end_date.date())
                
                cursor.execute(query, params)
                all_trips = cursor.fetchall()
                
                # Calculate maintenance insights for each trip
                boat_stats = {}  # Track stats per boat
                
                for i, row in enumerate(all_trips):
                    boat_id_val = row[0]
                    duration_minutes = row[6] if row[6] else 0
                    duration_hours = round(duration_minutes / 60.0, 2) if duration_minutes else 0
                    
                    # Initialize boat stats if not exists
                    if boat_id_val not in boat_stats:
                        boat_stats[boat_id_val] = {
                            'daily_trips': {},
                            'weekly_trips': {},
                            'last_exit_time': None
                        }
                    
                    # Calculate time since last trip
                    time_since_last = None
                    if boat_stats[boat_id_val]['last_exit_time']:
                        try:
                            last_exit = datetime.fromisoformat(boat_stats[boat_id_val]['last_exit_time'])
                            current_exit = datetime.fromisoformat(row[4])
                            time_since_last = int((current_exit - last_exit).total_seconds() / 60)
                        except Exception:
                            time_since_last = None
                    
                    # Update daily and weekly trip counts
                    trip_date = row[3]
                    week_start = trip_date - timedelta(days=trip_date.weekday())
                    
                    boat_stats[boat_id_val]['daily_trips'][trip_date] = boat_stats[boat_id_val]['daily_trips'].get(trip_date, 0) + 1
                    boat_stats[boat_id_val]['weekly_trips'][week_start] = boat_stats[boat_id_val]['weekly_trips'].get(week_start, 0) + 1
                    
                    # Generate maintenance notes
                    maintenance_notes = []
                    if duration_minutes > 180:  # More than 3 hours
                        maintenance_notes.append("Long session - check for wear")
                    if time_since_last and time_since_last < 30:  # Less than 30 min between trips
                        maintenance_notes.append("Frequent use - monitor stress")
                    if boat_stats[boat_id_val]['daily_trips'][trip_date] > 5:  # More than 5 trips per day
                        maintenance_notes.append("Heavy daily usage")
                    if boat_stats[boat_id_val]['weekly_trips'][week_start] > 20:  # More than 20 trips per week
                        maintenance_notes.append("High weekly usage - schedule inspection")
                    
                    # Determine movement type
                    movement_type = "EXIT" if i == 0 or all_trips[i-1][0] != boat_id_val else "CONTINUATION"
                    
                    water_time_data.append({
                        'boat_id': row[0],
                        'boat_name': row[1],
                        'boat_class': row[2],
                        'trip_date': row[3],
                        'exit_time': row[4],
                        'entry_time': row[5],
                        'duration_minutes': duration_minutes,
                        'duration_hours': duration_hours,
                        'trip_id': row[7],
                        'movement_type': movement_type,
                        'time_since_last_trip_minutes': time_since_last,
                        'daily_trip_count': boat_stats[boat_id_val]['daily_trips'][trip_date],
                        'weekly_trip_count': boat_stats[boat_id_val]['weekly_trips'][week_start],
                        'maintenance_notes': '; '.join(maintenance_notes) if maintenance_notes else 'Normal usage'
                    })
                    
                    # Update last exit time for this boat
                    boat_stats[boat_id_val]['last_exit_time'] = row[4]
            
            return water_time_data
            
        except Exception as e:
            logger.error(f"Failed to export boat water time data: {e}", "EXPORT", e)
            return []
    
    def start(self):
        """Start the entire system."""
        try:
            logger.info("Starting Boat Tracking System...", "SYSTEM")
            logger.audit("SYSTEM_START", "SYSTEM", f"Boat Tracking System starting with display mode: {self.display_mode}")
            
            # Start API server
            self.start_api_server()
            time.sleep(2)  # Give API server time to start
            
            # Start scanners
            self.start_scanners()
            
            # Start web dashboard (if enabled)
            if self.display_mode in ['web', 'both']:
                self.start_web_dashboard()
            
            # Start terminal display (if enabled)
            if self.display_mode in ['terminal', 'both']:
                self.start_terminal_display()
            
            # Start health monitoring
            self._start_health_monitoring()
            
            self.running = True
            logger.info("Boat Tracking System started successfully", "SYSTEM")
            logger.info(f"API Server: http://{self.config['api_host']}:{self.config['api_port']}", "SYSTEM")
            
            if self.display_mode in ['web', 'both']:
                logger.info(f"Web Dashboard: http://{self.config['web_host']}:{self.config['web_port']}", "SYSTEM")
            
            if self.display_mode in ['terminal', 'both']:
                logger.info("Terminal Display: Active on HDMI output", "SYSTEM")
            
            logger.audit("SYSTEM_START_SUCCESS", "SYSTEM", f"All components started successfully with display mode: {self.display_mode}")
            
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
        
        # Start weekly log export scheduler
        self._start_weekly_log_export()
    
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
    
    def _start_weekly_log_export(self):
        """Start weekly log export scheduler (runs every Sunday at 11:59 PM)."""
        def weekly_export_scheduler():
            while self.running:
                try:
                    now = datetime.now(timezone.utc)
                    
                    # Check if it's Sunday and time is close to midnight
                    if now.weekday() == 6 and now.hour == 23 and now.minute >= 59:
                        self._perform_weekly_log_export()
                        # Wait for next week to avoid multiple exports
                        time.sleep(3600)  # Wait 1 hour
                    else:
                        # Check every minute
                        time.sleep(60)
                        
                except Exception as e:
                    logger.error(f"Weekly log export scheduler failed: {e}", "EXPORT", e)
                    time.sleep(300)  # Wait 5 minutes on error
        
        export_thread = threading.Thread(target=weekly_export_scheduler, daemon=True)
        export_thread.start()
        logger.info("Weekly log export scheduler started", "EXPORT")
    
    def _perform_weekly_log_export(self):
        """Perform weekly log export."""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
            
            # Create exports directory if it doesn't exist
            import os
            exports_dir = "data/exports"
            os.makedirs(exports_dir, exist_ok=True)
            
            # Generate filename
            filename = f"boat_tracking_weekly_logs_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
            filepath = os.path.join(exports_dir, filename)
            
            # Export logs
            log_data = self._export_logs_by_date_range(start_date, end_date, 'all')
            
            # Write to file
            import csv
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['timestamp', 'level', 'component', 'message'])
                
                for entry in log_data:
                    writer.writerow([
                        entry.get('timestamp', ''),
                        entry.get('level', ''),
                        entry.get('component', ''),
                        entry.get('message', '')
                    ])
            
            logger.info(f"Weekly log export completed: {filepath}", "EXPORT")
            logger.audit("WEEKLY_LOG_EXPORT", "SYSTEM", f"Exported logs from {start_date} to {end_date}")
            
        except Exception as e:
            logger.error(f"Weekly log export failed: {e}", "EXPORT", e)
    
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
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
        .brand { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
        .brand h1 { color: var(--paper); font-size: 2rem; letter-spacing: 1px; }
        .brand span { color: var(--sand); font-weight: 600; font-size: 0.95rem; }
        .primary-btn {
            background: var(--red); color: var(--paper); border: none; padding: 12px 20px;
            border-radius: 8px; font-weight: 700; cursor: pointer; letter-spacing: .3px;
            box-shadow: 0 6px 16px rgba(229,75,75,0.25);
            transition: all 0.3s ease;
            white-space: nowrap;
        }
        .primary-btn:hover { filter: brightness(1.05); transform: translateY(-1px); }
        .dashboard { display: grid; grid-template-columns: 1.1fr 1fr 1fr; gap: 20px; }
        
        /* Mobile optimization (Portrait phones) */
        @media (max-width: 480px) {
            body { padding: 8px; }
            .header { flex-direction: column; align-items: flex-start; gap: 10px; }
            .brand { flex-direction: column; gap: 4px; }
            .brand h1 { font-size: 1.1rem; line-height: 1.3; }
            .brand span { font-size: 0.8rem; }
            .header > div:last-child { 
                display: flex; 
                flex-wrap: wrap; 
                gap: 6px; 
                width: 100%; 
            }
            .primary-btn { 
                padding: 8px 12px; 
                font-size: 0.8rem; 
                flex: 1 1 auto;
                min-width: calc(50% - 3px);
            }
            .whiteboard-board { padding: 10px; margin-bottom: 12px; }
            .wb-title { font-size: 1rem; margin-bottom: 8px; }
            .wb-table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; }
            .wb-table { font-size: 0.75rem; min-width: 600px; }
            .wb-table th, .wb-table td { padding: 6px 4px; }
            .wb-table th { font-size: 0.7rem; }
            .dashboard { gap: 10px; grid-template-columns: 1fr; }
            .card { padding: 12px; }
            .card h2 { font-size: 1.1rem; margin-bottom: 10px; }
            .boat-item, .beacon-item { padding: 8px; margin: 8px 0; }
            .status-badge { font-size: 0.7rem; padding: 2px 6px; }
            .rssi-info { font-size: 0.75rem; }
            #overdueBanner { font-size: 0.85rem; padding: 8px; }
            #closingTimeDisplay { font-size: 0.85rem; }
            .subnote { font-size: 0.75rem; }
        }
        
        /* Mobile optimization (Landscape phones & small tablets) */
        @media (min-width: 481px) and (max-width: 768px) {
            body { padding: 12px; }
            .header { gap: 10px; }
            .brand h1 { font-size: 1.4rem; }
            .brand span { font-size: 0.85rem; }
            .header > div:last-child { display: flex; flex-wrap: wrap; gap: 8px; }
            .primary-btn { padding: 10px 14px; font-size: 0.85rem; }
            .whiteboard-board { padding: 12px; }
            .wb-title { font-size: 1.3rem; }
            .wb-table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; }
            .wb-table { font-size: 0.85rem; min-width: 700px; }
            .wb-table th, .wb-table td { padding: 8px 6px; }
            .dashboard { gap: 12px; grid-template-columns: 1fr; }
            .card { padding: 14px; }
            .boat-item, .beacon-item { padding: 10px; }
            .status-badge { font-size: 0.8rem; }
        }
        
        /* Tablet optimization (Portrait tablets) */
        @media (min-width: 769px) and (max-width: 1024px) {
            body { padding: 16px; }
            .dashboard { grid-template-columns: 1fr 1fr; gap: 16px; }
            .whiteboard-board { padding: 16px; }
            .wb-table th, .wb-table td { padding: 10px 8px; }
            .header > div:last-child { gap: 10px; }
        }
        
        /* Desktop optimization */
        @media (min-width: 1025px) {
            .dashboard { grid-template-columns: 1.1fr 1fr 1fr; }
        }
        
        /* Wide screens */
        @media (min-width: 1600px) {
            .container { max-width: 1600px; }
        }
        
        /* Modal responsive styles */
        .modal-content {
            background-color: white; 
            margin: 5% auto; 
            padding: 20px; 
            border-radius: 15px; 
            width: 80%; 
            max-width: 800px; 
            max-height: 80vh;
            overflow-y: auto; 
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        @media (max-width: 768px) {
            .modal-content {
                width: 95%;
                margin: 2% auto;
                padding: 15px;
                max-height: 95vh;
            }
            .modal-content h2 {
                font-size: 1.2rem;
            }
        }
        
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
                <a href="/manage" class="primary-btn" style="text-decoration:none; display:inline-block; background:#0d6efd;">Search / Manage</a>
                <button class="primary-btn" onclick="openBeaconDiscovery()">+ Register New Beacon</button>
                <button class="primary-btn" onclick="openLogViewer()" style="background:#6c757d;">Logs</button>
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
            <div class="wb-title">Boat Out Board - <span id="todayDate">Loading...</span></div>
            <div class="wb-table-wrapper">
                <table class="wb-table" id="wbTable">
                    <thead>
                        <tr>
                            <th>Boat</th>
                            <th>Status</th>
                            <th>Time IN SHED</th>
                            <th>Time ON WATER</th>
                            <th>Last Seen</th>
                            <th>Water Today</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr><td colspan="6" style="text-align:center; padding:14px; font-weight:600; color:#666;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
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
            
            <!-- Boats Outside (replaces Beacons Status) -->
            <div class="card">
                <h2>Boats Outside <span id="outsideCount" style="color:var(--danger);font-weight:800;"></span></h2>
                <div id="outsideList">
                    <p>Loading boats...</p>
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
        <div class="modal-content">
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
                    " placeholder="e.g., RC-2024-001 (Optional - leave blank for old boats)">
                    <small style="color: #666; font-size: 0.9rem;">Leave blank for boats without serial numbers</small>
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
        <div class="modal-content" style="max-width: 1200px; width: 95%;">
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
                    border-radius: 20px; cursor: pointer; margin-right: 10px;
                ">Refresh</button>
            </div>
            
            <!-- Log Export Section -->
            <div style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;">
                <h3 style="margin: 0 0 15px 0; color: #2c3e50;">Export Logs</h3>
                
                <div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
                    <button onclick="exportWeeklyLogs()" style="
                        background: #17a2b8; color: white; border: none; padding: 8px 16px; 
                        border-radius: 20px; cursor: pointer; font-weight: bold;
                    ">Export Last Week</button>
                    <button onclick="openCustomExport()" style="
                        background: #6f42c1; color: white; border: none; padding: 8px 16px; 
                        border-radius: 20px; cursor: pointer; font-weight: bold;
                    ">Custom Date Range</button>
                </div>
                
                <div id="customExportForm" style="display: none; margin-top: 15px;">
                    <div style="display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap;">
                        <div>
                            <label style="display: block; font-weight: bold; margin-bottom: 5px; color: #2c3e50;">Start Date:</label>
                            <input type="datetime-local" id="exportStartDate" style="padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
                        </div>
                        <div>
                            <label style="display: block; font-weight: bold; margin-bottom: 5px; color: #2c3e50;">End Date:</label>
                            <input type="datetime-local" id="exportEndDate" style="padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
                        </div>
                        <div>
                            <label style="display: block; font-weight: bold; margin-bottom: 5px; color: #2c3e50;">Type:</label>
                            <select id="exportType" style="padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
                                <option value="all">All Logs</option>
                                <option value="errors">Errors Only</option>
                                <option value="main">Main Logs</option>
                            </select>
                        </div>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button onclick="exportCustomLogs()" style="
                            background: #28a745; color: white; border: none; padding: 8px 16px; 
                            border-radius: 20px; cursor: pointer; font-weight: bold;
                        ">Export</button>
                        <button onclick="closeCustomExport()" style="
                            background: #6c757d; color: white; border: none; padding: 8px 16px; 
                            border-radius: 20px; cursor: pointer;
                        ">Cancel</button>
                    </div>
                </div>
            </div>
            
            <div id="logContent" style="
                background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; 
                padding: 15px; max-height: 500px; overflow-y: auto; font-family: monospace; 
                font-size: 12px; white-space: pre-wrap; color: #2c3e50;
            ">
                Click a button above to load logs or status information.
            </div>
        </div>
    </div>
    
    <script>
        function filterBoats() {
            const q = (document.getElementById('boatSearch')?.value || '').toLowerCase().trim();
            // Filter whiteboard rows
            try {
                const rows = document.querySelectorAll('#wbTable tbody tr');
                rows.forEach(tr => {
                    const td = tr.querySelector('td');
                    const name = td ? (td.textContent || '').toLowerCase() : '';
                    tr.style.display = q && !name.includes(q) ? 'none' : '';
                });
            } catch (e) {}
            // Filter Boats Status list
            try {
                const items = document.querySelectorAll('#boatsList .boat-item');
                items.forEach(div => {
                    const label = div.querySelector('strong')?.textContent || '';
                    const name = label.toLowerCase();
                    div.style.display = q && !name.includes(q) ? 'none' : '';
                });
            } catch (e) {}
        }
        function updateBoats() {
            fetch('/api/boats')
                .then(response => response.json())
                .then(data => {
                    const boatsList = document.getElementById('boatsList');
                    if (data.length === 0) {
                        boatsList.innerHTML = '<p>No boats registered</p>';
                        return;
                    }
                    
                    const formatTimestamp = (iso) => {
                        if (!iso) return '—';
                        try {
                            const d = new Date(iso);
                            if (Number.isNaN(d.getTime())) return iso;
                            const now = new Date();
                            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                            const yesterday = new Date(today);
                            yesterday.setDate(yesterday.getDate() - 1);
                            const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
                            if (day.getTime() === today.getTime()) return `Today ${d.toLocaleTimeString()}`;
                            if (day.getTime() === yesterday.getTime()) return `Yesterday ${d.toLocaleTimeString()}`;
                            return d.toLocaleDateString('en-AU') + ' ' + d.toLocaleTimeString();
                        } catch (err) {
                            return iso;
                        }
                    };
                    const elapsedSince = (iso) => {
                        if (!iso) return null;
                        try {
                            const d = new Date(iso);
                            if (Number.isNaN(d.getTime())) return null;
                            const diffMs = Date.now() - d.getTime();
                            if (diffMs < 0) return 'just now';
                            const minutes = Math.floor(diffMs / 60000);
                            if (minutes < 1) return 'just now';
                            if (minutes < 60) return `${minutes} min ago`;
                            const hours = Math.floor(minutes / 60);
                            const mins = minutes % 60;
                            if (hours < 24) return `${hours}h ${mins}m ago`;
                            const days = Math.floor(hours / 24);
                            const remHours = hours % 24;
                            return `${days}d ${remHours}h ago`;
                        } catch (err) {
                            return null;
                        }
                    };
                    let html = '';
                    let outsideHtml = '';
                    const outsideBoats = [];
                    data.forEach(boat => {
                        const statusClass = boat.status === 'in_harbor' ? 'in-harbor' : 'out';
                        const statusBadge = boat.status === 'in_harbor' ? 'status-in-harbor' : 'status-out';
                        const statusText = boat.status === 'in_harbor' ? 'IN SHED' : 'ON WATER';
                        const beaconInfo = boat.beacon ? 
                            `<div class=\"rssi-info\">Beacon: ${boat.beacon.mac_address}<br>Signal: ${rssiToPercent(boat.beacon.last_rssi)}% (${boat.beacon.last_rssi || 'N/A'} dBm)</div>` : 
                            '<div class="rssi-info">No beacon assigned</div>';
                        
                        html += `
                            <div class="boat-item ${statusClass}">
                                <div>
                                    <strong>${boat.name}</strong> (${boat.class_type})
                                    <span class="status-badge ${statusBadge}">${statusText}</span>
                                    ${boat.op_status ? `<span class="status-badge ${boat.op_status==='MAINTENANCE'?'status-unclaimed':'status-assigned'}">${boat.op_status}</span>` : ''}
                                </div>
                                ${beaconInfo}
                            </div>
                        `;

                        if (boat.status !== 'in_harbor') {
                            outsideBoats.push(boat);
                            const outsideBeaconInfo = boat.beacon ? 
                                `<div class=\"rssi-info\">Beacon: ${boat.beacon.mac_address}<br>Signal: ${rssiToPercent(boat.beacon.last_rssi)}% (${boat.beacon.last_rssi || 'N/A'} dBm)</div>` : 
                                '<div class=\"rssi-info\">No beacon assigned</div>';
                            const lastSeen = boat.beacon ? formatTimestamp(boat.beacon.last_seen) : null;
                            const lastSeenAge = boat.beacon ? elapsedSince(boat.beacon.last_seen) : null;
                            const lastSeenInfo = boat.beacon ? `<div class=\"rssi-info\">Last seen: ${lastSeen}${lastSeenAge ? ` (${lastSeenAge})` : ''}</div>` : '';
                            outsideHtml += `
                                <div class=\"boat-item out\">
                                    <div><strong>${boat.name}</strong> (${boat.class_type})</div>
                                    ${lastSeenInfo}
                                    ${outsideBeaconInfo}
                                </div>
                            `;
                        }
                    });
                    boatsList.innerHTML = html;
                    const outsideList = document.getElementById('outsideList');
                    const outsideSummary = `
                        <div style="text-align: center; margin-bottom: 20px;">
                            <div style="font-size: 3rem; font-weight: bold; color: var(--danger);">${outsideBoats.length}</div>
                            <div style="color: #666;">Boats Outside</div>
                        </div>
                    `;
                    if (outsideList) {
                        outsideList.innerHTML = outsideHtml 
                            ? (outsideSummary + '<h3>Currently Outside:</h3>' + outsideHtml)
                            : (outsideSummary + '<p>No boats outside</p>');
                    }
                    const outsideCount = document.getElementById('outsideCount');
                    if (outsideCount) outsideCount.textContent = outsideBoats.length > 0 ? `(${outsideBoats.length})` : '';
                })
                .catch(error => console.error('Error updating boats:', error));
        }
        
        function updateBeacons() { /* removed in this branch */ }
        
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
            
            updateTodayDate();
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

        function updateTodayDate() {
            const today = new Date();
            const options = { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
            };
            const todayStr = today.toLocaleDateString('en-AU', options);
            const todayElement = document.getElementById('todayDate');
            if (todayElement) {
                todayElement.textContent = todayStr;
            }
        }

        function updateWhiteboard() {
            Promise.all([
                fetch('/api/boats').then(r => r.json()),
                fetch('/api/presence').then(r => r.json())
            ]).then(([boats, presence]) => {
                const tbody = document.querySelector('#wbTable tbody');
                if (!Array.isArray(boats) || boats.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:14px; font-weight:600; color:#666;">No boats registered</td></tr>';
                    return;
                }

                const rows = boats.map(b => {
                    const boatName = b.name;
                    const status = b.status === 'in_harbor' ? '<span class="wb-status-in">IN SHED</span>' : '<span class="wb-status-out">ON WATER</span>';
                    // helpers
                    const formatNice = (iso) => {
                        if (!iso) return '—';
                        const d = new Date(iso);
                        const now = new Date();
                        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                        const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
                        const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
                        if (day.getTime() === today.getTime()) return `Today ${d.toLocaleTimeString()}`;
                        if (day.getTime() === yesterday.getTime()) return `Yesterday ${d.toLocaleTimeString()}`;
                        return d.toLocaleDateString('en-AU') + ' ' + d.toLocaleTimeString();
                    };

                    const timeIn = formatNice(b.last_entry);
                    const timeOut = formatNice(b.last_exit);

                    let lastSeen = '—';
                    if (b.beacon && b.beacon.last_seen) {
                        const lastSeenDate = new Date(b.beacon.last_seen);
                        const now = new Date();
                        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                        const yesterday = new Date(today);
                        yesterday.setDate(yesterday.getDate() - 1);
                        const lastSeenDay = new Date(lastSeenDate.getFullYear(), lastSeenDate.getMonth(), lastSeenDate.getDate());
                        
                        if (lastSeenDay.getTime() === today.getTime()) {
                            lastSeen = `Today ${lastSeenDate.toLocaleTimeString()}`;
                        } else if (lastSeenDay.getTime() === yesterday.getTime()) {
                            lastSeen = `Yesterday ${lastSeenDate.toLocaleTimeString()}`;
                        } else {
                            lastSeen = lastSeenDate.toLocaleDateString('en-AU') + ' ' + lastSeenDate.toLocaleTimeString();
                        }
                    }
                    const waterToday = (b.water_time_today_minutes != null) ? `${b.water_time_today_minutes} min` : '—';
                    return `<tr><td>${boatName}</td><td>${status}</td><td>${timeIn}</td><td>${timeOut}</td><td>${lastSeen}</td><td>${waterToday}</td></tr>`;
                }).join('');
                tbody.innerHTML = rows;
            }).catch(() => {
                const tbody = document.querySelector('#wbTable tbody');
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:14px; font-weight:600; color:#666;">Error loading whiteboard</td></tr>';
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
        
        // Update every 1 second for faster UI reflection
        setInterval(updateAllData, 1000);
        
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
API Server: ${data.api_server_running ? 'Running' : 'Stopped'}
Database: ${data.database_healthy ? 'Healthy' : 'Unhealthy'}
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
        
        // Log Export Functions
        function exportWeeklyLogs() {
            fetch('/api/logs/export/weekly', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error('Export failed');
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `boat_tracking_weekly_logs_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                alert('Weekly logs exported successfully!');
            })
            .catch(error => {
                console.error('Export error:', error);
                alert('Failed to export weekly logs: ' + error.message);
            });
        }
        
        function openCustomExport() {
            document.getElementById('customExportForm').style.display = 'block';
            
            // Set default dates (last 7 days)
            const endDate = new Date();
            const startDate = new Date();
            startDate.setDate(startDate.getDate() - 7);
            
            document.getElementById('exportStartDate').value = startDate.toISOString().slice(0, 16);
            document.getElementById('exportEndDate').value = endDate.toISOString().slice(0, 16);
        }
        
        function closeCustomExport() {
            document.getElementById('customExportForm').style.display = 'none';
        }
        
        function exportCustomLogs() {
            const startDate = document.getElementById('exportStartDate').value;
            const endDate = document.getElementById('exportEndDate').value;
            const exportType = document.getElementById('exportType').value;
            
            if (!startDate || !endDate) {
                alert('Please select both start and end dates');
                return;
            }
            
            if (new Date(startDate) >= new Date(endDate)) {
                alert('Start date must be before end date');
                return;
            }
            
            fetch('/api/logs/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate,
                    type: exportType
                })
            })
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error('Export failed');
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `boat_tracking_logs_${startDate.replace(/[:\-T]/g, '')}_to_${endDate.replace(/[:\-T]/g, '')}.csv`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                alert('Custom logs exported successfully!');
                closeCustomExport();
            })
            .catch(error => {
                console.error('Export error:', error);
                alert('Failed to export custom logs: ' + error.message);
            });
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
      if(!user || !pass){ alert('Please enter username and password'); return; }
      try{
        const r=await fetch('/admin/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user,pass,dry:true})});
        if(r.status===401){ alert('Invalid credentials'); return; }
        if(!r.ok){ alert('Login failed'); return; }
        CRED={user,pass};
        document.getElementById('actions').style.display='block';
        loadClosing();
      }catch(e){ alert('Login error: '+e); }
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
    <div style=\"margin:8px 0\"><input id=\"user\" placeholder=\"User ID\"></div>
    <div style=\"margin:8px 0\"><input id=\"pass\" type=\"password\" placeholder=\"Password\"></div>
    <div style=\"margin:8px 0\"><button class=\"primary\" onclick=\"login()\">Login</button></div>
    <p class=\"muted\">Credentials are configured server-side. Contact admin for access.</p>
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

    def get_fsm_viewer_html(self):
        """Generate the FSM viewer page HTML."""
        mermaid_diagram = """stateDiagram-v2
    direction LR
    [*] --> IDLE
    state "INSIDE (ENTERED)" as ENTERED
    state "OUTSIDE (EXITED)" as EXITED
    state "OUT_PENDING (GOING_OUT)" as GOING_OUT
    state "IN_PENDING (GOING_IN)" as GOING_IN

    %% Baseline commits from IDLE
    IDLE --> ENTERED: InnerStrong
    IDLE --> EXITED: OuterStrong

    %% Exit flow (shed -> inner -> outer -> water)
    ENTERED --> GOING_OUT: InnerStrong && InnerWeakQ && !OuterTrendUp
    GOING_OUT --> EXITED: OuterStrong && OuterWithin(last_inner_seen, w_pair_exit_s)
    GOING_OUT --> ENTERED: InnerStrong && InnerWithin(last_outer_seen, w_pair_enter_s)
    GOING_OUT --> ENTERED: pending_since > w_pair_exit_s

    %% Enter flow (water -> outer -> inner -> shed)
    EXITED --> GOING_IN: OuterStrong && InnerWeakQ && !OuterTrendUp
    GOING_IN --> ENTERED: InnerStrong && InnerWithin(last_outer_seen, w_pair_enter_s)
    GOING_IN --> EXITED: OuterStrong && OuterWithin(last_inner_seen, w_pair_exit_s)
    GOING_IN --> EXITED: pending_since > w_pair_enter_s

    %% Idle collapses when quiet
    ENTERED --> IDLE: NoMovement >= t_idle_s
    EXITED --> IDLE: NoMovement >= t_idle_long_s"""
        
        return """{% raw %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FSM Viewer</title>
  <script>
    // Dynamically load Mermaid with CDN fallbacks and expose a readiness promise
    (function(){
      const cdns = [
        'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js',
        'https://unpkg.com/mermaid@10/dist/mermaid.min.js'
      ];
      let idx = 0;
      function tryLoad(resolve, reject){
        if (window.mermaid){ resolve(); return; }
        if (idx >= cdns.length){ reject(new Error('Mermaid failed to load')); return; }
        const s = document.createElement('script');
        s.src = cdns[idx++];
        s.async = true;
        s.onload = function(){ resolve(); };
        s.onerror = function(){ tryLoad(resolve, reject); };
        document.head.appendChild(s);
      }
      window.ensureMermaid = function(){
        return new Promise((resolve,reject)=>{
          if (window.mermaid){ resolve(); return; }
          tryLoad(resolve, reject);
        }).then(()=>{ try { window.mermaid.initialize({ startOnLoad: false, theme: 'dark' }); } catch(e){} });
      }
    })();
  </script>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:#0b1020; color:#f3f4f6; margin:0; }}
    .header {{ display:flex; align-items:center; justify-content:space-between; padding:16px 20px; background:#111827; border-bottom:1px solid #374151; }}
    .brand {{ display:flex; gap:10px; align-items:baseline; }}
    .brand h1 {{ margin:0; color:#ef4444; letter-spacing:2px; }}
    .btn {{ background:#ef4444; color:#fff; padding:8px 12px; border-radius:6px; text-decoration:none; }}
    .container {{ max-width:1400px; margin:0 auto; padding:20px; }}
    .grid {{ display:grid; grid-template-columns: 2fr 1fr; gap:20px; }}
    .card {{ background:#111827; border:1px solid #374151; border-radius:12px; padding:16px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #374151; }}
    .state {{ font-weight:600; }}
    .st-IDLE {{ color:#9ca3af; }}
    .st-SEEN_OUTER {{ color:#60a5fa; }}
    .st-SEEN_INNER {{ color:#f59e0b; }}
    .st-ENTERED {{ color:#34d399; }}
    .st-EXITED {{ color:#f87171; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
    
    @keyframes flash {{
      0% {{ background-color: #374151; }}
      50% {{ background-color: #60a5fa; }}
      100% {{ background-color: transparent; }}
    }}
    
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.7; transform: scale(1.05); }}
    }}
    
    /* Enhanced SVG state styling */
    #diagram { min-height: 520px; }
    #diagram svg {{
      width: 100%;
      height: auto;
    }}
    
    .fsm-active {{
      animation: pulse 1.5s ease-in-out infinite;
    }}
  </style>
  <script></script>
</head>
<body>
  <div class="header">
    <div class="brand">
      <h1>RED SHED</h1><span>FSM Viewer</span>
    </div>
    <div>
      <a class="btn" href="/">← Dashboard</a>
    </div>
  </div>
  <div class="container">
    <div class="grid">
      <div class="card">
        <h2>Live FSM Animation</h2>
        <div id="diagram"></div>
        <div style="margin-top:10px; font-size:0.9em; color:#9ca3af;">
          <span id="stateStats">Loading...</span>
        </div>
        <div id="profilePanel" style="margin-top:10px; font-size:0.9em; color:#9ca3af;">
          <span>Profile: <b id="profileName">…</b> | Branch: <span id="branchName">…</span></span>
        </div>
        <div id="doorLRPanel" style="display:none; margin-top:10px; font-size:0.9em; color:#9ca3af;">
          <div><b>Door L/R Params</b></div>
          <pre id="doorLRParams" style="white-space:pre-wrap; background:#0f172a; padding:10px; border-radius:8px; border:1px solid #374151; max-height:200px; overflow:auto;"></pre>
        </div>
      </div>
      <div class="card">
        <h2>Live States</h2>
        <table>
          <thead><tr><th>Boat</th><th>Beacon</th><th>MAC</th><th>State</th><th>Last Entry</th><th>Last Exit</th></tr></thead>
          <tbody id="stateBody"></tbody>
        </table>
      </div>
    </div>
  </div>
  <script>
    let currentStates = {{}};
    let lastUpdate = 0;
    
    function createAnimatedMermaid(stateCounts) {{
      // Create dynamic Mermaid matching current 5-state FSM
      const idle = stateCounts.idle || 0;
      const goingIn = stateCounts.going_in || 0;
      const goingOut = stateCounts.going_out || 0;
      const entered = stateCounts.entered || 0;
      const exited = stateCounts.exited || 0;

      let src = `stateDiagram-v2
    direction LR
    [*] --> IDLE
    state "INSIDE (ENTERED)" as ENTERED
    state "OUTSIDE (EXITED)" as EXITED
    state "OUT_PENDING (GOING_OUT)" as GOING_OUT
    state "IN_PENDING (GOING_IN)" as GOING_IN

    IDLE --> ENTERED: InnerStrong
    IDLE --> EXITED: OuterStrong

    ENTERED --> GOING_OUT: InnerStrong && InnerWeakQ && !OuterTrendUp
    GOING_OUT --> EXITED: OuterStrong && OuterWithin(last_inner_seen, w_pair_exit_s)
    GOING_OUT --> ENTERED: InnerStrong && InnerWithin(last_outer_seen, w_pair_enter_s)
    GOING_OUT --> ENTERED: pending_since > w_pair_exit_s

    EXITED --> GOING_IN: OuterStrong && InnerWeakQ && !OuterTrendUp
    GOING_IN --> ENTERED: InnerStrong && InnerWithin(last_outer_seen, w_pair_enter_s)
    GOING_IN --> EXITED: OuterStrong && OuterWithin(last_inner_seen, w_pair_exit_s)
    GOING_IN --> EXITED: pending_since > w_pair_enter_s

    ENTERED --> IDLE: NoMovement >= t_idle_s
    EXITED --> IDLE: NoMovement >= t_idle_long_s

    classDef activeIdle fill:#6b7280,stroke:#9ca3af,stroke-width:3px
    classDef activePending fill:#f59e0b,stroke:#f97316,stroke-width:4px
    classDef activeEntered fill:#10b981,stroke:#059669,stroke-width:4px
    classDef activeExited fill:#ef4444,stroke:#dc2626,stroke-width:4px
    classDef pulsing fill:#3b82f6,stroke:#2563eb,stroke-width:5px
    classDef inactive fill:#1f2937,stroke:#374151,stroke-width:1px`;

      if (idle > 0) src += `\n    class IDLE activeIdle`;
      if (goingOut > 0) src += `\n    class GOING_OUT ${goingOut > 2 ? 'pulsing' : 'activePending'}`;
      if (goingIn > 0) src += `\n    class GOING_IN ${goingIn > 2 ? 'pulsing' : 'activePending'}`;
      if (entered > 0) src += `\n    class ENTERED activeEntered`;
      if (exited > 0) src += `\n    class EXITED activeExited`;

      return src;
    }}

    function renderMermaid(stateCounts) {{
      const src = createAnimatedMermaid(stateCounts);
      if (!window.mermaid) {{
        document.getElementById('diagram').innerText = 'Loading diagram engine…';
        return;
      }}
      mermaid.render('fsmGraph' + Date.now(), src).then(({{ svg }}) => {{
        document.getElementById('diagram').innerHTML = svg;
        applyLiveStateColors(stateCounts);
      }}).catch(err => {{
        document.getElementById('diagram').innerText = 'Mermaid render error: ' + err;
      }});
    }}
    
    function applyLiveStateColors(stateCounts) {{
      // Direct SVG manipulation for live state highlighting
      setTimeout(() => {{
        const diagram = document.getElementById('diagram');
        if (!diagram) return;
        
        // Target Mermaid state diagram elements more specifically
        const svg = diagram.querySelector('svg');
        if (!svg) return;
        
        // Find all shapes (rectangles, circles) that represent states
        const stateShapes = svg.querySelectorAll('rect, circle, ellipse, polygon');
        const stateTexts = svg.querySelectorAll('text');
        
        // Create mapping of text content to shapes
        stateTexts.forEach(text => {{
          const textContent = text.textContent.trim().toUpperCase();
          
          // Find the associated shape (usually previous sibling or parent)
          let shape = text.parentElement?.querySelector('rect, circle, ellipse, polygon');
          if (!shape) {{
            shape = text.previousElementSibling;
          }}
          if (!shape) {{
            shape = text.parentElement?.previousElementSibling?.querySelector('rect, circle, ellipse, polygon');
          }}
          
          if (shape) {{
            shape.style.transition = 'all 0.5s ease';
            
            if (textContent.includes('IDLE') && stateCounts.idle > 0) {{
              shape.style.fill = '#6b7280';
              shape.style.stroke = '#9ca3af';
              shape.style.strokeWidth = '3';
            }}
            else if (textContent.includes('SEEN_OUTER') && stateCounts.seen_outer > 0) {{
              shape.style.fill = '#f59e0b';
              shape.style.stroke = '#f97316';
              shape.style.strokeWidth = '4';
              if (stateCounts.seen_outer > 1) {{
                shape.classList.add('fsm-active');
              }}
            }}
            else if (textContent.includes('SEEN_INNER') && stateCounts.seen_inner > 0) {{
              shape.style.fill = '#f59e0b';
              shape.style.stroke = '#f97316';
              shape.style.strokeWidth = '4';
              if (stateCounts.seen_inner > 1) {{
                shape.classList.add('fsm-active');
              }}
            }}
            else if (textContent.includes('ENTERED') && stateCounts.entered > 0) {{
              shape.style.fill = '#10b981';
              shape.style.stroke = '#059669';
              shape.style.strokeWidth = '5';
              shape.classList.add('fsm-active');
            }}
            else if (textContent.includes('EXITED') && stateCounts.exited > 0) {{
              shape.style.fill = '#ef4444';
              shape.style.stroke = '#dc2626';
              shape.style.strokeWidth = '5';
              shape.classList.add('fsm-active');
            }}
            else {{
              // Inactive state
              shape.style.fill = '#1f2937';
              shape.style.stroke = '#374151';
              shape.style.strokeWidth = '1';
              shape.classList.remove('fsm-active');
            }}
          }}
        }});
      }}, 200);
    }}

    async function loadStates() {{
      try {{
        const res = await fetch('/api/fsm-states');
        const data = await res.json();
        
        // Count states for animation
        const stateCounts = {{
          idle: 0, seen_outer: 0, seen_inner: 0, both_seen: 0, entered: 0, exited: 0
        }};
        
        data.forEach(r => {{
          const state = (r.state || 'idle').toString().toLowerCase();
          if (stateCounts.hasOwnProperty(state)) {{
            stateCounts[state]++;
          }}
        }});
        
        // Update stats display with live counts
        const total = data.length;
        document.getElementById('stateStats').innerHTML = 
          `🚤 ${{total}} boats | ⭕ IDLE: ${{stateCounts.idle}} | 🔵 OUTER: ${{stateCounts.seen_outer}} | 🟡 INNER: ${{stateCounts.seen_inner}} | 🟢 ENTERED: ${{stateCounts.entered}} | 🔴 EXITED: ${{stateCounts.exited}}`;
        
        // Only re-render diagram if state counts changed significantly
        const stateKey = JSON.stringify(stateCounts);
        if (window.lastStateKey !== stateKey) {{
          renderMermaid(stateCounts);
          window.lastStateKey = stateKey;
        }} else {{
          // Just update colors without full re-render
          applyLiveStateColors(stateCounts);
        }}
        
        // Update table with state change indicators
        const tb = document.getElementById('stateBody');
        tb.innerHTML = data.map(r => {{
          const state = (r.state || '').toUpperCase();
          const isRecentChange = currentStates[r.beacon_id] !== state;
          currentStates[r.beacon_id] = state;
          
          return `
          <tr ${{isRecentChange ? 'style="animation: flash 0.5s ease-in-out;"' : ''}}>
            <td>${{r.boat_name || r.boat_id || '-'}}</td>
            <td>${{r.beacon_id}}</td>
            <td>${{r.mac_address || '-'}}</td>
            <td class="state st-${{state}}">${{state}}</td>
            <td>${{r.entry_timestamp || '-'}}</td>
            <td>${{r.exit_timestamp || '-'}}</td>
          </tr>
          `;
        }}).join('');
      }} catch (e) {{
        console.error(e);
      }}
    }}

    // Initial render (wait for Mermaid to be ready first)
    ensureMermaid().then(() => {{
      // Render a baseline diagram immediately even before data arrives
      renderMermaid({{ idle: 0, going_in: 0, going_out: 0, entered: 0, exited: 0, seen_outer: 0, seen_inner: 0 }});
      loadStates();
      setInterval(loadStates, 500);
    }}).catch(() => {{
      // Still poll states; when mermaid later available a refresh will draw
      loadStates();
      setInterval(loadStates, 500);
    }});
  </script>
</body>
</html>
{% endraw %}""".replace("{{", "{").replace("}}", "}")

    def get_reports_html(self):
        return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Boat Usage Reports</title>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, Verdana, sans-serif;
      background: linear-gradient(135deg, #0b1b1e 0%, #1a2a3a 100%);
      color: #e9ecef;
      padding: 24px;
      margin: 0;
      min-height: 100vh;
    }
    
    .container {
      max-width: 1400px;
      margin: 0 auto;
    }
    
    .card {
      background: #fff;
      color: #2c3e50;
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 15px 35px rgba(0,0,0,.3);
      border: 1px solid #e0e6ed;
    }
    
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 2px solid #e9ecef;
    }
    
    .header h1 {
      margin: 0;
      color: #2c3e50;
      font-size: 28px;
      font-weight: 600;
    }
    
    .filters {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
      padding: 20px;
      background: #f8f9fa;
      border-radius: 12px;
      border: 1px solid #e9ecef;
    }
    
    .filter-group {
      display: flex;
      flex-direction: column;
    }
    
    .filter-group label {
      font-weight: 600;
      margin-bottom: 6px;
      color: #2c3e50;
      font-size: 14px;
    }
    
    .filter-group input,
    .filter-group select {
      padding: 12px;
      border: 2px solid #ddd;
      border-radius: 8px;
      font-size: 14px;
      transition: border-color 0.3s ease;
    }
    
    .filter-group input:focus,
    .filter-group select:focus {
      outline: none;
      border-color: #007bff;
      box-shadow: 0 0 0 3px rgba(0,123,255,0.1);
    }
    
    .actions {
      display: flex;
      gap: 12px;
      align-items: end;
    }
    
    .btn {
      padding: 12px 24px;
      border: none;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s ease;
      font-size: 14px;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    
    .btn-primary {
      background: #007bff;
      color: white;
    }
    
    .btn-primary:hover {
      background: #0056b3;
      transform: translateY(-1px);
    }
    
    .btn-success {
      background: #28a745;
      color: white;
    }
    
    .btn-success:hover {
      background: #1e7e34;
      transform: translateY(-1px);
    }
    
    .btn-secondary {
      background: #6c757d;
      color: white;
    }
    
    .btn-secondary:hover {
      background: #545b62;
      transform: translateY(-1px);
    }
    
    .table-container {
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid #e9ecef;
    }
    
    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
    }
    
    th {
      background: #f8f9fa;
      color: #2c3e50;
      font-weight: 600;
      padding: 16px 12px;
      text-align: left;
      border-bottom: 2px solid #e9ecef;
      font-size: 14px;
      position: sticky;
      top: 0;
    }
    
    td {
      padding: 12px;
      border-bottom: 1px solid #f1f3f4;
      font-size: 14px;
      vertical-align: middle;
    }
    
    tr:hover {
      background: #f8f9fa;
    }
    
    .status-badge {
      padding: 4px 8px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }
    
    .status-active {
      background: #d4edda;
      color: #155724;
    }
    
    .status-retired {
      background: #f8d7da;
      color: #721c24;
    }
    
    .number-cell {
      text-align: right;
      font-weight: 600;
    }
    
    .loading {
      text-align: center;
      padding: 40px;
      color: #6c757d;
      font-style: italic;
    }
    
    .no-data {
      text-align: center;
      padding: 40px;
      color: #6c757d;
    }
    
    .quick-filters {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    
    .quick-filter-btn {
      padding: 8px 16px;
      border: 1px solid #ddd;
      background: white;
      border-radius: 20px;
      cursor: pointer;
      font-size: 12px;
      transition: all 0.3s ease;
    }
    
    .quick-filter-btn:hover,
    .quick-filter-btn.active {
      background: #007bff;
      color: white;
      border-color: #007bff;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="header">
        <h1>Boat Usage Reports</h1>
        <div class="actions">
          <button class="btn btn-success" onclick="exportData()">
            Export CSV
          </button>
        </div>
      </div>
      
      <div class="quick-filters">
        <button class="quick-filter-btn active" onclick="setQuickFilter('today')">Today</button>
        <button class="quick-filter-btn" onclick="setQuickFilter('yesterday')">Yesterday</button>
        <button class="quick-filter-btn" onclick="setQuickFilter('week')">This Week</button>
        <button class="quick-filter-btn" onclick="setQuickFilter('month')">This Month</button>
        <button class="quick-filter-btn" onclick="setQuickFilter('all')">All Time</button>
      </div>
      
      <div class="filters">
        <div class="filter-group">
          <label for="fromDate">From Date & Time</label>
          <input type="datetime-local" id="fromDate" />
        </div>
        
        <div class="filter-group">
          <label for="toDate">To Date & Time</label>
          <input type="datetime-local" id="toDate" />
        </div>
        
        <div class="filter-group">
          <label for="boatSelect">Boat (Optional)</label>
          <select id="boatSelect" onchange="runReport()">
            <option value="">All Boats</option>
          </select>
        </div>
        
        <div class="filter-group">
          <label for="statusFilter">Status Filter</label>
          <select id="statusFilter" onchange="runReport()">
            <option value="">All Status</option>
            <option value="ACTIVE">Active Only</option>
            <option value="RETIRED">Retired Only</option>
          </select>
        </div>
        
        <div class="actions">
          <button class="btn btn-secondary" onclick="clearFilters()">
            Clear Filters
          </button>
        </div>
      </div>
      
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Boat Name</th>
              <th>Class</th>
              <th>Status</th>
              <th>Total Outings</th>
              <th>Total Minutes</th>
              <th>Avg Duration</th>
              <th>Last Seen</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody id="reportRows">
            <tr>
              <td colspan="8" class="loading">Loading boat data...</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="table-container" style="margin-top:16px;" id="sessionsContainer">
        <table>
          <thead>
            <tr>
              <th colspan="4">Individual Trip Logs (All Sessions)</th>
            </tr>
            <tr>
              <th>Boat</th>
              <th>Exit Time</th>
              <th>Enter Time</th>
              <th>Minutes</th>
            </tr>
          </thead>
          <tbody id="sessionRows">
            <tr><td colspan="4" class="no-data">Loading sessions...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    let boats = [];
    let currentData = [];
    
    // Initialize page
    document.addEventListener('DOMContentLoaded', function() {
      loadBoats();
      setQuickFilter('today');
    });
    
    async function loadBoats() {
      try {
        const response = await fetch('/api/boats/list');
        boats = await response.json();
        
        const select = document.getElementById('boatSelect');
        select.innerHTML = '<option value="">All Boats</option>';
        
        boats.forEach(boat => {
          const option = document.createElement('option');
          option.value = boat.id;
          option.textContent = boat.display_name;
          select.appendChild(option);
        });
      } catch (error) {
        console.error('Failed to load boats:', error);
      }
    }
    
    function setQuickFilter(period) {
      // Update active button
      document.querySelectorAll('.quick-filter-btn').forEach(btn => btn.classList.remove('active'));
      event.target.classList.add('active');
      
      const now = new Date();
      const fromDate = document.getElementById('fromDate');
      const toDate = document.getElementById('toDate');
      
      switch(period) {
        case 'today':
          fromDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().slice(0, 16);
          toDate.value = now.toISOString().slice(0, 16);
          break;
        case 'yesterday':
          const yesterday = new Date(now);
          yesterday.setDate(yesterday.getDate() - 1);
          fromDate.value = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate()).toISOString().slice(0, 16);
          toDate.value = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate(), 23, 59).toISOString().slice(0, 16);
          break;
        case 'week':
          const weekStart = new Date(now);
          weekStart.setDate(now.getDate() - now.getDay());
          fromDate.value = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate()).toISOString().slice(0, 16);
          toDate.value = now.toISOString().slice(0, 16);
          break;
        case 'month':
          fromDate.value = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 16);
          toDate.value = now.toISOString().slice(0, 16);
          break;
        case 'all':
          fromDate.value = '';
          toDate.value = '';
          break;
      }
      
      runReport();
    }
    
    function clearFilters() {
      document.getElementById('fromDate').value = '';
      document.getElementById('toDate').value = '';
      document.getElementById('boatSelect').value = '';
      document.getElementById('statusFilter').value = '';
      document.querySelectorAll('.quick-filter-btn').forEach(btn => btn.classList.remove('active'));
      runReport();
    }
    
    async function runReport() {
      const fromDate = document.getElementById('fromDate').value;
      const toDate = document.getElementById('toDate').value;
      const boatId = document.getElementById('boatSelect').value;
      const statusFilter = document.getElementById('statusFilter').value;
      
      const params = new URLSearchParams();
      if (fromDate) params.set('from', fromDate);
      if (toDate) params.set('to', toDate);
      if (boatId) params.set('boatId', boatId);
      // Ask API to include session details so we can show them if a boat is selected
      params.set('includeSessions', '1');
      
      try {
        document.getElementById('reportRows').innerHTML = '<tr><td colspan="8" class="loading">Loading report data...</td></tr>';
        
        const response = await fetch('/api/reports/usage?' + params.toString());
        currentData = await response.json();
        
        // Apply status filter
        if (statusFilter) {
          currentData = currentData.filter(boat => boat.op_status === statusFilter);
        }
        
        displayData(currentData);
        displaySessions(currentData, boatId);
      } catch (error) {
        console.error('Failed to load report:', error);
        document.getElementById('reportRows').innerHTML = '<tr><td colspan="8" class="no-data">Error loading report data</td></tr>';
      }
    }
    
    function displayData(data) {
      const tbody = document.getElementById('reportRows');
      
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-data">No data found for the selected criteria</td></tr>';
        return;
      }
      
      tbody.innerHTML = data.map(boat => {
        const lastSeen = boat.last_seen ? new Date(boat.last_seen).toLocaleString() : 'Never';
        const signal = boat.last_rssi ? `${boat.last_rssi} dBm` : 'N/A';
        const avgDuration = boat.avg_duration > 0 ? `${boat.avg_duration} min` : 'N/A';
        
        return `
          <tr>
            <td><strong>${boat.boat_name}</strong><br><small style="color: #6c757d;">${boat.boat_id}</small></td>
            <td>${boat.boat_class}</td>
            <td><span class="status-badge status-${boat.op_status.toLowerCase()}">${boat.op_status}</span></td>
            <td class="number-cell">${boat.total_outings}</td>
            <td class="number-cell">${boat.total_minutes} min</td>
            <td class="number-cell">${avgDuration}</td>
            <td><small>${lastSeen}</small></td>
            <td><small>${signal}</small></td>
          </tr>
        `;
      }).join('');
    }
    
    function exportData() {
      const fromDate = document.getElementById('fromDate').value;
      const toDate = document.getElementById('toDate').value;
      const boatId = document.getElementById('boatSelect').value;
      
      // Generate filename with date range
      let filename = 'boat_trips';
      if (fromDate && toDate) {
        const fromStr = fromDate.split('T')[0].replace(/-/g, '');
        const toStr = toDate.split('T')[0].replace(/-/g, '');
        filename += `_${fromStr}_to_${toStr}`;
      } else {
        const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
        filename += `_${today}`;
      }
      filename += '.csv';
      
      const params = new URLSearchParams();
      if (fromDate) params.set('from', fromDate);
      if (toDate) params.set('to', toDate);
      if (boatId) params.set('boatId', boatId);
      params.set('includeTrips', '1');  // Include detailed trip logs
      params.set('filename', filename);  // Send desired filename
      
      const url = '/api/reports/usage/export.csv?' + params.toString();
      
      // Use download link instead of window.open to control filename
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
    }

    function displaySessions(data, boatId) {
      const container = document.getElementById('sessionsContainer');
      const tbody = document.getElementById('sessionRows');
      
      // Collect ALL sessions from ALL boats (or filtered boat)
      let allSessions = [];
      data.forEach(boat => {
        if (boatId && boat.boat_id !== boatId) return; // Skip if filtering by boat
        if (boat.sessions && boat.sessions.length > 0) {
          boat.sessions.forEach(s => {
            allSessions.push({
              boat_name: boat.boat_name,
              start: s.start,
              end: s.end,
              minutes: s.minutes
            });
          });
        }
      });
      
      if (allSessions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="no-data">No sessions found in this range</td></tr>';
        return;
      }
      
      // Sort by exit time (most recent first)
      allSessions.sort((a, b) => new Date(b.start) - new Date(a.start));
      
      tbody.innerHTML = allSessions.map(s => {
        const fmt = (iso) => new Date(iso).toLocaleString();
        return `<tr>
          <td>${s.boat_name}</td>
          <td>${fmt(s.start)}</td>
          <td>${fmt(s.end)}</td>
          <td class="number-cell">${s.minutes}</td>
        </tr>`
      }).join('');
    }
  </script>
</body>
</html>
        """

    def get_manage_html(self):
        return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Manage Boats & Beacons</title>
  <style>
    body { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background:#0f1a1f; color:#e8eef2; }
    .container { max-width: 980px; margin: 24px auto; padding: 0 16px; }
    .card { background:#13232b; border:1px solid #20323b; border-radius:10px; padding:16px; box-shadow: 0 6px 18px rgba(0,0,0,.35); }
    .row { display:flex; gap:10px; align-items:center; }
    .title { font-weight:800; margin:0 0 12px 0; font-size: 1.4rem; letter-spacing:.3px; }
    .muted { color:#9fb2bd; font-size:.9rem; }
    input[type=text] { padding:8px 10px; border:1px solid #2a3f49; background:#0d171c; color:#e8eef2; border-radius:8px; min-width:280px; }
    button { background:#0d6efd; color:white; border:none; padding:8px 12px; border-radius:8px; cursor:pointer; font-weight:700; }
    button.secondary { background:#6c757d; }
    table { width:100%; border-collapse: collapse; margin-top:12px; }
    th,td { border:1px solid #2a3f49; padding:10px; }
    th { background:#0f1a1f; text-align:left; }
    .badge { padding:3px 8px; border-radius:999px; font-size:.75rem; font-weight:800; }
    .badge.active { background:#d4edda; color:#155724; }
    .badge.maint { background:#fff3cd; color:#856404; }
    .actions { display:flex; gap:6px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="row" style="justify-content:space-between; gap:12px;">
        <div class="title">Search & Manage</div>
        <a href="/" class="muted" style="text-decoration:none;">← Back to Dashboard</a>
      </div>
      <div class="row" style="margin-bottom:10px;">
        <input id="q" type="text" placeholder="Search boats by name..." oninput="suggest()" />
        <button onclick="doSearch()">Search</button>
      </div>
      <div id="suggestions" class="muted" style="margin-bottom:8px;"></div>
      <div id="results" class="muted">Type a boat name and click Search.</div>
    </div>
  </div>

  <script>
    async function doSearch() {
      const q = document.getElementById('q').value.trim();
      const res = await fetch('/api/v1/boats/search?q=' + encodeURIComponent(q));
      const items = await res.json();
      if (!items.length) { document.getElementById('results').innerHTML = 'No matches.'; return; }
      let html = '<table><thead><tr><th>Name</th><th>Class</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
      for (const b of items) {
        const rowId = `row_${b.id}`;
        html += `<tr id="${rowId}">
          <td>${b.name}</td>
          <td>${b.class_type}</td>
          <td id="status_${b.id}">
            <span id="statusBadge_${b.id}" class="badge active">ACTIVE</span>
            <select id="opSel_${b.id}" style="margin-left:8px;" onchange="updateStatus('${b.id}', this.value)">
              <option value="ACTIVE">Running</option>
              <option value="MAINTENANCE">Maintenance</option>
            </select>
          </td>
          <td class="actions">
            <button class="secondary" onclick="openReplaceModal('${b.id}', '${b.name.replace(/'/g, "\\'")}')">Replace Beacon</button>
          </td>
        </tr>`;
      }
      html += '</tbody></table>';
      document.getElementById('results').innerHTML = html;
      // fetch presence to render status/toggle labels
      for (const b of items) { renderPresence(b.id); }
    }

    let suggestTimer;
    async function suggest() {
      clearTimeout(suggestTimer);
      suggestTimer = setTimeout(async () => {
        const q = document.getElementById('q').value.trim();
        if (!q) { document.getElementById('suggestions').innerHTML=''; return; }
        const res = await fetch('/api/v1/boats/search?q=' + encodeURIComponent(q));
        const items = await res.json();
        if (!items.length) { document.getElementById('suggestions').innerHTML=''; return; }
        const list = items.map(b => `<a href=\"#\" onclick=\"document.getElementById('q').value='${b.name.replace(/'/g, "\'")}';doSearch();return false;\" style=\"margin-right:10px; text-decoration:none; color:#0d6efd;\">${b.name}</a>`).join('');
        document.getElementById('suggestions').innerHTML = 'Suggestions: ' + list;
      }, 200);
    }

    async function updateStatus(boatId, value) {
      try {
        const ok = confirm('Change status to ' + value + '?');
        if (!ok) { const sel=document.getElementById('opSel_'+boatId); if (sel) sel.value = (document.getElementById('statusBadge_'+boatId)?.textContent || 'ACTIVE'); return; }
        const r = await fetch(`/api/v1/boats/${boatId}/status`, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status:value}) });
        const j = await r.json().catch(()=>({}));
        if (!r.ok || j.error) throw new Error(j.error || 'Save failed');
        // Visual confirmation
        const badge = document.getElementById('statusBadge_' + boatId);
        if (badge) { badge.className = 'badge ' + (value==='MAINTENANCE'?'maint':'active'); badge.textContent = value; }
        // Also refresh dashboard cards
        updateBoats();
        alert('Status updated to ' + value);
        renderPresence(boatId);
      } catch(e) { alert('Failed: ' + e.message); }
    }

    async function renderPresence(boatId) {
      try {
        const r = await fetch(`/api/v1/presence/${boatId}`);
        const j = await r.json();
        const badge = document.getElementById('statusBadge_' + boatId);
        const sel = document.getElementById('opSel_' + boatId);
        const op = (j.op_status || 'ACTIVE').toUpperCase();
        const isMaint = op === 'MAINTENANCE';
        if (badge) { badge.className = 'badge ' + (isMaint ? 'maint' : 'active'); badge.textContent = op; }
        if (sel) sel.value = op;
      } catch (e) { /* ignore */ }
    }

    async function replaceBeacon(boatId) {
      const mac = prompt('Enter new beacon MAC (AA:BB:CC:DD:EE:FF):');
      if (!mac) return;
      try {
        const res = await fetch(`/api/v1/boats/${boatId}/replace-beacon`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({new_mac: mac}) });
        const j = await res.json();
        if (!res.ok) throw new Error(j.error || 'Unknown error');
        alert('Replaced. New MAC: ' + j.beacon_mac);
      } catch(e) { alert('Failed: ' + e.message); }
    }

    // Replace Beacon Modal with Start/Stop scanning
    let replaceScanTimer = null;
    function openReplaceModal(boatId, boatName) {
      const modal = document.getElementById('replaceModal');
      modal.style.display = 'block';
      modal.setAttribute('data-boat', boatId);
      modal.setAttribute('data-name', boatName);
      document.getElementById('scanList').innerHTML = '<div class="muted">Click Start Scanning to find nearby unassigned beacons.</div>';
      const btn = document.getElementById('scanToggle');
      btn.textContent = 'Start Scanning';
      btn.style.background = '#0d6efd';
      if (replaceScanTimer) { clearInterval(replaceScanTimer); replaceScanTimer = null; }
    }
    function closeReplaceModal(){
      const modal = document.getElementById('replaceModal');
      modal.style.display = 'none';
      if (replaceScanTimer) { clearInterval(replaceScanTimer); replaceScanTimer = null; }
    }
    async function pollReplaceBeacons(){
      const res = await fetch('/api/active-beacons');
      const data = await res.json();
      const list = document.getElementById('scanList');
      // unassigned only
      const unassigned = data.filter(b => b.status === 'unclaimed');
      if (!unassigned.length) { list.innerHTML = '<div class="muted">Scanning… no unassigned beacons yet.</div>'; return; }
      const boatId = document.getElementById('replaceModal').getAttribute('data-boat');
      const boatName = document.getElementById('replaceModal').getAttribute('data-name');
      list.innerHTML = unassigned.map(b => `<button class="secondary" onclick="confirmReplace('${boatId}','${boatName.replace(/'/g, "\\'")}','${b.mac_address}')">${b.mac_address}</button>`).join(' ');
    }
    function toggleReplaceScan(){
      const btn = document.getElementById('scanToggle');
      if (replaceScanTimer){
        clearInterval(replaceScanTimer); replaceScanTimer = null;
        btn.textContent = 'Start Scanning';
        btn.style.background = '#0d6efd';
      } else {
        pollReplaceBeacons();
        replaceScanTimer = setInterval(pollReplaceBeacons, 1500);
        btn.textContent = 'Stop Scanning';
        btn.style.background = '#dc3545';
      }
    }

    async function confirmReplace(boatId, boatName, mac) {
      if (!confirm(`Replace current beacon for ${boatName} with ${mac}?`)) return;
      try {
        const res = await fetch(`/api/v1/boats/${boatId}/replace-beacon`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({new_mac: mac}) });
        const j = await res.json();
        if (!res.ok) throw new Error(j.error || 'Unknown error');
        alert('Replaced. New MAC: ' + j.beacon_mac);
      } catch(e) { alert('Failed: ' + e.message); }
    }
  </script>
  
  <!-- Replace Beacon Modal -->
  <div id="replaceModal" style="display:none; position:fixed; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,.5); z-index:1000;">
    <div style="background:#fff; color:#2c3e50; width:80%; max-width:700px; margin:6% auto; border-radius:12px; padding:16px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h3 style="margin:0;">Replace Beacon</h3>
        <button onclick="closeReplaceModal()" style="background:#dc3545; color:#fff; border:none; padding:6px 10px; border-radius:6px;">×</button>
      </div>
      <div style="margin:12px 0;">
        <button id="scanToggle" onclick="toggleReplaceScan()" style="background:#0d6efd; color:#fff; border:none; padding:8px 12px; border-radius:8px; font-weight:700;">Start Scanning</button>
      </div>
      <div id="scanList" class="muted">Click Start Scanning to find nearby unassigned beacons.</div>
    </div>
  </div>
</body>
</html>
        """

def get_default_config():
    """Get default configuration."""
    return {
        # Use same default path as API server so both share one DB
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
                'rssi_threshold': -85,  # Accept weaker signals (was -60, too strict!)
                'scan_interval': 0.5,
                'batch_size': 1,
                'active_window_seconds': 6,
                'adapter': 'hci1'  # Using hci1 - hci0 has locking issues
            },
            {
                'id': 'gate-inner',
                'api_key': 'default-key',
                'rssi_threshold': -55,  # Right scanner - detects when beacon is within ~0.5m
                'scan_interval': 0.5,
                'batch_size': 1,
                'active_window_seconds': 6,
                'adapter': 'hci0'  # TP-Link BLE Scanner #2 (Right side)
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
        parser.add_argument("--db-path", default="data/boat_tracking.db", help="Database file path (relative paths stored under data/)")
        parser.add_argument("--display-mode", choices=['web', 'terminal', 'both'], default='web', 
                           help="Display mode: 'web' for web dashboard, 'terminal' for HDMI display, 'both' for both")
        
        args = parser.parse_args()
        
        # Helper: choose an available port to reduce 'address in use' errors
        import socket
        def choose_port(preferred: int) -> int:
            port = preferred
            for _ in range(10):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        s.bind(("127.0.0.1", port))
                        return port
                    except OSError:
                        port += 1
            return preferred
        
        # Load configuration
        config = get_default_config()
        if args.config:
            # Load from file (implement if needed)
            pass
        
        # Override with command line args
        config['api_port'] = choose_port(args.api_port)
        config['web_port'] = choose_port(args.web_port)
        # Accept either bare filename or explicit path; resolver will map to data/
        config['database_path'] = args.db_path
        
        logger.info(f"Starting Boat Tracking System with config: {config}", "MAIN")
        logger.info(f"Display mode: {args.display_mode}", "MAIN")
        
        # Create and start system
        system = BoatTrackingSystem(config, args.display_mode)
        
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
