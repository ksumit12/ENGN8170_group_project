#!/usr/bin/env python3
"""
Vercel-compatible Flask app for Boat Tracking System
Standalone version that works without external dependencies
"""

import os
import json
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from datetime import datetime, timezone

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Mock data for demonstration
MOCK_BOATS = [
    {
        'id': 1,
        'name': 'Red Shed Racer',
        'class_type': 'Single Scull',
        'status': 'in_harbor',
        'beacon': {
            'mac_address': 'AA:BB:CC:DD:EE:FF',
            'last_seen': datetime.now().isoformat(),
            'last_rssi': -45
        }
    },
    {
        'id': 2,
        'name': 'Black Mountain',
        'class_type': 'Double Scull',
        'status': 'out',
        'beacon': {
            'mac_address': '11:22:33:44:55:66',
            'last_seen': datetime.now().isoformat(),
            'last_rssi': -78
        }
    }
]

MOCK_BEACONS = [
    {
        'id': 1,
        'mac_address': 'AA:BB:CC:DD:EE:FF',
        'name': 'Beacon_1',
        'status': 'assigned',
        'last_seen': datetime.now().isoformat(),
        'last_rssi': -45,
        'assigned_boat': {
            'id': 1,
            'name': 'Red Shed Racer',
            'class_type': 'Single Scull'
        }
    },
    {
        'id': 2,
        'mac_address': '11:22:33:44:55:66',
        'name': 'Beacon_2',
        'status': 'assigned',
        'last_seen': datetime.now().isoformat(),
        'last_rssi': -78,
        'assigned_boat': {
            'id': 2,
            'name': 'Black Mountain',
            'class_type': 'Double Scull'
        }
    }
]

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template_string(get_dashboard_html())

@app.route('/api/boats')
def api_boats():
    """Get all boats."""
    try:
        return jsonify(MOCK_BOATS)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/beacons')
def api_beacons():
    """Get all beacons."""
    try:
        return jsonify(MOCK_BEACONS)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/presence')
def api_presence():
    """Get shed presence information."""
    try:
        boats_in_harbor = [boat for boat in MOCK_BOATS if boat['status'] == 'in_harbor']
        total_in_harbor = len(boats_in_harbor)
        
        result = {
            'total_in_harbor': total_in_harbor,
            'boats_in_harbor': []
        }
        
        for boat in boats_in_harbor:
            result['boats_in_harbor'].append({
                'boat_name': boat['name'],
                'boat_class': boat['class_type'],
                'beacon_mac': boat['beacon']['mac_address'],
                'last_rssi': boat['beacon']['last_rssi']
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/overdue')
def api_overdue():
    """Get overdue boats information."""
    try:
        return jsonify({
            'overdue_boat_ids': [],
            'closing_time': '20:00'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings/closing-time')
def api_closing_time():
    """Get closing time setting."""
    try:
        return jsonify({'closing_time': '20:00'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs')
def api_logs():
    """Get recent system logs."""
    try:
        log_type = request.args.get('type', 'main')
        count = int(request.args.get('count', 50))
        
        # Mock logs
        logs = [
            f"[{datetime.now().strftime('%H:%M:%S')}] System started",
            f"[{datetime.now().strftime('%H:%M:%S')}] Database connected",
            f"[{datetime.now().strftime('%H:%M:%S')}] Web server running on Vercel",
            f"[{datetime.now().strftime('%H:%M:%S')}] Mock data loaded successfully"
        ]
        
        return jsonify({'logs': logs[:count]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_dashboard_html():
    """Get the HTML for the web dashboard."""
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
        /* Whiteboard-first layout */
        .whiteboard-board { background: #fff; color: #222; border-radius: 14px; padding: 18px 18px 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); margin-bottom: 18px; }
        .wb-title { text-align: center; color: var(--red); font-weight: 800; font-size: 1.6rem; letter-spacing: .5px; margin-bottom: 12px; }
        .wb-table { width: 100%; border-collapse: collapse; }
        .wb-table th, .wb-table td { border: 2px solid #ddd; padding: 10px 12px; font-weight: 700; }
        .wb-table th { background: #f7f7f7; color: #333; text-transform: uppercase; letter-spacing: .6px; }
        .wb-status-in { color: #1e7e34; }
        .wb-status-out { color: #b02a37; }
        .subnote { font-weight: 500; color: #666; font-size: .85rem; margin-top: 8px; text-align: center; }
        .demo-notice { background: #fff3cd; color: #856404; padding: 10px; border-radius: 8px; margin-bottom: 20px; text-align: center; font-weight: bold; }
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
                <button class="primary-btn" onclick="openLogViewer()" style="background:#6c757d;">Logs</button>
            </div>
        </div>
        
        
        <!-- Closing Time Display -->
        <div style="margin:10px 0; padding:8px 12px; background:#f8f9fa; border-left:4px solid #007bff; border-radius:4px; color:#495057;">
            <strong>Closing Time:</strong> <span id="closingTimeDisplay">Loading...</span>
        </div>
        
        <!-- Whiteboard-style priority view -->
        <div class="whiteboard-board">
            <div class="wb-title">Boat Out Board - <span id="todayDate">Loading...</span></div>
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
                <button onclick="refreshLogs()" style="
                    background: #6c757d; color: white; border: none; padding: 8px 16px; 
                    border-radius: 20px; cursor: pointer;
                ">Refresh</button>
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
                            `<div class="rssi-info">Beacon: ${boat.beacon.mac_address}<br>Signal: ${rssiToPercent(boat.beacon.last_rssi)}% (${boat.beacon.last_rssi || 'N/A'} dBm)</div>` : 
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
            fetch('/api/beacons')
                .then(response => response.json())
                .then(data => {
                    const beaconsList = document.getElementById('beaconsList');
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
            
            updateTodayDate();
            updateWhiteboard();
            updateBoats();
            updateBeacons();
            updatePresence();
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
            fetch('/api/boats')
                .then(response => response.json())
                .then(boats => {
                    const tbody = document.querySelector('#wbTable tbody');
                    if (!Array.isArray(boats) || boats.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:14px; font-weight:600; color:#666;">No boats registered</td></tr>';
                        return;
                    }

                    const rows = boats.map(b => {
                        const boatName = b.name;
                        const status = b.status === 'in_harbor' ? '<span class="wb-status-in">IN SHED</span>' : '<span class="wb-status-out">OUT</span>';
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
                        const signal = b.beacon && b.beacon.last_rssi != null ? `${rssiToPercent(b.beacon.last_rssi)}% (${b.beacon.last_rssi} dBm)` : '—';
                        return `<tr><td>${boatName}</td><td>${status}</td><td>${lastSeen}</td><td>${signal}</td></tr>`;
                    }).join('');
                    tbody.innerHTML = rows;
                })
                .catch(error => {
                    console.error('Error loading whiteboard:', error);
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
        
        // Log Viewer Functions
        function openLogViewer() {
            document.getElementById('logModal').style.display = 'block';
            loadLogs('main');
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
                        logContent.textContent = data.logs.join('\n');
                    } else {
                        logContent.textContent = 'No logs available.';
                    }
                })
                .catch(error => {
                    logContent.textContent = `Error loading logs: ${error.message}`;
                });
        }
        
        function refreshLogs() {
            loadLogs('main');
        }
        
        // Update every 3 seconds
        setInterval(updateAllData, 3000);
        
        // Initial load
        updateAllData();
    </script>
</body>
</html>
    """

# This is required for Vercel
if __name__ == "__main__":
    app.run(debug=True)