#!/usr/bin/env python3
"""
Simple Boat Tracker - Compatible with Python 3.10
A simplified version that works with your current Python version
"""

import time
import threading
from flask import Flask, render_template_string, jsonify
from ble_beacon_detector import BLEBeaconDetector
from boat_tracker import BoatTracker

# Configuration
BEACON_ADDRESS = "DC:0D:30:23:05:F8"
BEACON_NAME = "rowing_clu"
RSSI_THRESHOLD = -60
CSV_PATH = "boat_entries.csv"

class SimpleBoatTracker:
    def __init__(self):
        self.boat_tracker = BoatTracker()
        self.beacon_detector = BLEBeaconDetector(callback=self.beacon_callback)
        self.current_rssi = None
        self.current_signal_percentage = 0
        self.current_signal_strength = "No Signal"
        
    def beacon_callback(self, event_type, data):
        """Callback for beacon events from BLE detector."""
        if event_type == 'beacon_detected':
            self.boat_tracker.handle_beacon_detected(
                data['rssi'], 
                data['signal_percentage'], 
                data['signal_strength']
            )
        elif event_type == 'beacon_lost':
            self.boat_tracker.handle_beacon_lost(
                data['rssi'], 
                data['signal_percentage'], 
                data['signal_strength']
            )
        elif event_type == 'signal_update':
            # Just update signal info
            self.current_rssi = data['rssi']
            self.current_signal_percentage = data['signal_percentage']
            self.current_signal_strength = data['signal_strength']
    
    def get_stats(self):
        """Get current statistics."""
        stats = self.boat_tracker.get_stats()
        beacon_status = self.beacon_detector.get_status()
        
        # Merge beacon status into stats
        stats.update({
            'current_rssi': beacon_status['current_rssi'],
            'signal_percentage': beacon_status['signal_percentage'],
            'signal_strength': beacon_status['signal_strength']
        })
        
        return stats
    
    def get_entries(self):
        """Get recent entries."""
        return self.boat_tracker.get_entries()
    
    def get_boats(self):
        """Get all boats with health information."""
        return self.boat_tracker.get_boats()
    
    def start_tracking(self):
        """Start beacon detection and boat tracking."""
        self.boat_tracker.csv_file, self.boat_tracker.csv_writer = self.boat_tracker.ensure_csv(CSV_PATH)
        self.beacon_detector.start_scanning()
    
    def stop_tracking(self):
        """Stop beacon detection and boat tracking."""
        self.beacon_detector.stop_scanning()
        self.boat_tracker.close_csv()

# Global tracker instance
boat_tracker = SimpleBoatTracker()

# Flask app
app = Flask(__name__)

# HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simple Boat Tracker</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; color: #333; padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; color: white; }
        .header h1 { font-size: 2.5rem; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .header p { font-size: 1.1rem; opacity: 0.9; }
        .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { 
            background: white; border-radius: 15px; padding: 25px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.1); 
        }
        .card h2 { color: #2c3e50; margin-bottom: 20px; }
        .stat { display: flex; justify-content: space-between; margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 8px; }
        .stat-value { font-weight: bold; color: #2c3e50; }
        .status-indicator { 
            padding: 15px; border-radius: 10px; text-align: center; font-weight: bold; margin: 10px 0;
        }
        .detected { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .not-detected { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .entries { max-height: 400px; overflow-y: auto; }
        .entry { 
            padding: 10px; margin: 5px 0; border-radius: 8px; 
            border-left: 4px solid #667eea; background: #f8f9fa;
        }
        .entry.entry { border-left-color: #28a745; }
        .entry.exit { border-left-color: #dc3545; }
        .update-indicator { 
            position: fixed; top: 20px; right: 20px; padding: 10px 15px; 
            background: #28a745; color: white; border-radius: 20px; 
            font-size: 0.9rem; font-weight: bold; z-index: 1000;
            opacity: 0; transition: opacity 0.3s ease;
        }
        .update-indicator.show { opacity: 1; }
        .rssi-info { font-size: 0.9rem; color: #6c757d; margin-top: 5px; }
        .health-score { 
            display: inline-block; padding: 4px 8px; border-radius: 12px; 
            font-weight: bold; font-size: 0.9rem; margin-left: 5px;
        }
        .health-excellent { background: #d4edda; color: #155724; }
        .health-good { background: #d1ecf1; color: #0c5460; }
        .health-fair { background: #fff3cd; color: #856404; }
        .health-poor { background: #f8d7da; color: #721c24; }
        .boat-health-item { 
            padding: 10px; margin: 5px 0; border-radius: 8px; 
            background: #f8f9fa; border-left: 4px solid #667eea;
        }
        .health-breakdown { font-size: 0.8rem; color: #6c757d; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Simple Boat Tracker</h1>
            <p>BLE-powered boat usage tracking with RSSI percentage display</p>
        </div>
        
        <div class="update-indicator" id="updateIndicator">Updating...</div>
        
        <div class="dashboard">
            <!-- Beacon Status -->
            <div class="card">
                <h2>Beacon Status</h2>
                <div id="beaconStatus" class="status-indicator not-detected">
                    Beacon Not Detected - No Boat
                </div>
                <div class="rssi-info">
                    <strong>Target Beacon:</strong> {{ beacon_address }} ({{ beacon_name }})<br>
                    <strong>RSSI Threshold:</strong> {{ rssi_threshold }} dBm<br>
                    <strong>Status:</strong> <span id="connectionStatus">Scanning...</span>
                </div>
            </div>
            
            <!-- Statistics -->
            <div class="card">
                <h2>Statistics</h2>
                <div class="stat">
                    <span>Total Events:</span>
                    <span class="stat-value" id="totalEvents">0</span>
                </div>
                <div class="stat">
                    <span>Boats Entered:</span>
                    <span class="stat-value" id="boatsEntered">0</span>
                </div>
                <div class="stat">
                    <span>Boats Exited:</span>
                    <span class="stat-value" id="boatsExited">0</span>
                </div>
                <div class="stat">
                    <span>Currently in Harbor:</span>
                    <span class="stat-value" id="boatsInHarbor">0</span>
                </div>
            </div>
            
            <!-- Boat Health -->
            <div class="card">
                <h2>Boat Health</h2>
                <div id="healthInfo">
                    <p>No boats tracked yet. Health scores will appear here as boats are detected.</p>
                </div>
            </div>
            
            <!-- Recent Activity -->
            <div class="card">
                <h2>Recent Activity</h2>
                <div class="entries" id="entriesList">
                    <p>No boat activity yet. Make sure your beacon is nearby and powered on!</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function updateBeaconStatus() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    const statusElement = document.getElementById('beaconStatus');
                    const connectionElement = document.getElementById('connectionStatus');
                    
                    if (data.beacon_in_range && data.current_rssi) {
                        statusElement.className = 'status-indicator detected';
                        statusElement.innerHTML = `Beacon Detected - Boat in Harbor<br>
                            <strong>RSSI:</strong> ${data.current_rssi} dBm<br>
                            <strong>Signal:</strong> ${data.signal_percentage}% (${data.signal_strength})`;
                        connectionElement.textContent = 'Connected';
                    } else {
                        statusElement.className = 'status-indicator not-detected';
                        statusElement.textContent = 'Beacon Not Detected - No Boat';
                        connectionElement.textContent = 'Scanning...';
                    }
                })
                .catch(error => console.error('Error updating status:', error));
        }
        
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('totalEvents').textContent = data.total_entries;
                    document.getElementById('boatsEntered').textContent = data.entry_count;
                    document.getElementById('boatsExited').textContent = data.exit_count;
                    document.getElementById('boatsInHarbor').textContent = data.boats_in_harbor;
                })
                .catch(error => console.error('Error updating stats:', error));
        }
        
        function updateEntries() {
            fetch('/api/entries')
                .then(response => response.json())
                .then(data => {
                    const entriesList = document.getElementById('entriesList');
                    if (data.length === 0) {
                        entriesList.innerHTML = '<p>No boat activity yet. Make sure your beacon is nearby and powered on!</p>';
                        return;
                    }
                    
                    let html = '';
                    data.slice(0, 10).forEach(entry => {
                        const rssiHtml = entry.rssi ? `<div class="rssi-info">RSSI: ${entry.rssi} dBm (${entry.signal_percentage}% - ${entry.signal_strength})</div>` : '';
                        const healthHtml = entry.health_score ? `<div class="rssi-info">Health: ${entry.health_score}/100 (${entry.health_status})</div>` : '';
                        const sessionHtml = entry.session_duration_hours ? `<div class="rssi-info">Session Duration: ${entry.session_duration_hours.toFixed(2)} hours</div>` : '';
                        html += `
                            <div class="entry ${entry.status.toLowerCase()}">
                                <div><strong>${entry.boat_name}</strong> (${entry.boat_id}) - ${entry.boat_class || 'Unknown'}</div>
                                <div>${entry.local_time} - ${entry.status}</div>
                                ${rssiHtml}
                                ${healthHtml}
                                ${sessionHtml}
                            </div>
                        `;
                    });
                    entriesList.innerHTML = html;
                })
                .catch(error => console.error('Error updating entries:', error));
        }
        
        function updateHealthInfo() {
            fetch('/api/boats')
                .then(response => response.json())
                .then(data => {
                    const healthInfo = document.getElementById('healthInfo');
                    if (data.length === 0) {
                        healthInfo.innerHTML = '<p>No boats tracked yet. Health scores will appear here as boats are detected.</p>';
                        return;
                    }
                    
                    let html = '';
                    data.forEach(boat => {
                        const healthClass = `health-${boat.health_breakdown?.color || 'good'}`;
                        const healthScore = boat.health_score || 0;
                        const healthStatus = boat.health_breakdown?.status || 'Unknown';
                        const breakdown = boat.health_breakdown?.breakdown || {};
                        
                        let breakdownHtml = '';
                        if (Object.keys(breakdown).length > 0) {
                            breakdownHtml = '<div class="health-breakdown">' + 
                                Object.values(breakdown).join(', ') + '</div>';
                        }
                        
                        html += `
                            <div class="boat-health-item">
                                <div>
                                    <strong>${boat.name}</strong> (${boat.id}) - ${boat.class || 'Unknown'}
                                    <span class="health-score ${healthClass}">${healthScore}/100 ${healthStatus}</span>
                                </div>
                                <div class="rssi-info">
                                    Sessions: ${boat.total_sessions || 0} | 
                                    Water Hours: ${(boat.total_water_hours || 0).toFixed(1)}h | 
                                    Service Hours: ${(boat.service_hours_since || 0).toFixed(1)}h
                                </div>
                                ${breakdownHtml}
                            </div>
                        `;
                    });
                    healthInfo.innerHTML = html;
                })
                .catch(error => console.error('Error updating health info:', error));
        }
        
        function updateAllData() {
            const indicator = document.getElementById('updateIndicator');
            indicator.classList.add('show');
            
            updateBeaconStatus();
            updateStats();
            updateEntries();
            updateHealthInfo();
            
            setTimeout(() => {
                indicator.classList.remove('show');
            }, 500);
        }
        
        // Update every 2 seconds
        setInterval(updateAllData, 2000);
        
        // Initial load
        updateAllData();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template_string(HTML_TEMPLATE, 
                                beacon_address=BEACON_ADDRESS,
                                beacon_name=BEACON_NAME,
                                rssi_threshold=RSSI_THRESHOLD)

@app.route('/api/stats')
def api_stats():
    """Get current statistics."""
    return jsonify(boat_tracker.get_stats())

@app.route('/api/entries')
def api_entries():
    """Get recent entries."""
    recent_entries = boat_tracker.get_entries()[-20:]  # Last 20 entries
    return jsonify(recent_entries)

@app.route('/api/boats')
def api_boats():
    """Get all boats with health information."""
    boats_list = boat_tracker.get_boats()
    return jsonify(boats_list)

def simulate_beacon_events():
    """Simulate beacon events for testing with realistic session durations."""
    print("Starting beacon simulation...")
    print("This will simulate realistic boat sessions with varying durations")
    print("   - Beacon ON = Boat ENTERS (session starts)")
    print("   - Beacon OFF = Boat EXITS (session ends, duration tracked)")
    print("Waiting 10 seconds before starting simulation...")
    
    # Wait before starting simulation to avoid false positives
    time.sleep(10)
    
    beacon_state = False
    while True:
        try:
            if beacon_state:
                # Simulate session duration (10-30 seconds for testing)
                session_duration = 10 + (time.time() % 20)  # 10-30 seconds
                print(f"Beacon ON - Session started, will last {session_duration:.1f} seconds")
                time.sleep(session_duration)  # Convert to seconds
                
                # Simulate beacon turning OFF (boat exits)
                print("Simulating beacon OFF - Boat EXITS")
                boat_tracker.boat_tracker.handle_beacon_lost(-60, 50, "Fair")
                beacon_state = False
                
                # Wait between sessions (5-15 seconds for testing)
                break_duration = 5 + (time.time() % 10)  # 5-15 seconds
                print(f"Break between sessions: {break_duration:.1f} seconds")
                time.sleep(break_duration)
            else:
                # Simulate beacon turning ON (boat enters)
                print("Simulating beacon ON - Boat ENTERS")
                rssi = -45  # Strong signal
                boat_tracker.boat_tracker.handle_beacon_detected(rssi, 80, "Excellent")
                beacon_state = True
                
        except KeyboardInterrupt:
            print("\nStopping simulation...")
            break
        except Exception as e:
            print(f"Error in simulation: {e}")

def main():
    """Main entry point."""
    import sys
    
    # Check for simulation flag
    enable_simulation = '--simulate' in sys.argv or '--sim' in sys.argv
    
    print("Simple Boat Tracker System")
    print("=" * 50)
    print(f"Target Beacon: {BEACON_ADDRESS} ({BEACON_NAME})")
    print(f"RSSI Threshold: {RSSI_THRESHOLD} dBm")
    print(f"Website: http://localhost:5000")
    if enable_simulation:
        print("Simulation Mode: ENABLED")
    else:
        print("Simulation Mode: DISABLED (use --simulate to enable)")
    print("=" * 50)
    
    # Start tracking
    if enable_simulation:
        boat_tracker.start_tracking()
        simulation_thread = threading.Thread(target=simulate_beacon_events, daemon=True)
        simulation_thread.start()
    else:
        print("Starting real BLE scanning...")
        print("   Turn on your beacon to start tracking!")
        boat_tracker.start_tracking()
    
    # Start Flask app
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        boat_tracker.stop_tracking()
        print("Goodbye!")

if __name__ == "__main__":
    main()
