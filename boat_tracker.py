#!/usr/bin/env python3
"""
Boat Tracker Web Application
Reads button trigger logs and displays boat entries/exits with random boat names and serial numbers.
"""

from flask import Flask, render_template, jsonify
import csv
import os
import time
import random
from datetime import datetime
import json

app = Flask(__name__)

# Configuration
CSV_PATH = "bt_triggers.csv"
BOAT_NAMES = [
    "Ocean Explorer", "Sea Breeze", "Blue Horizon", "Wave Rider", "Marina Star",
    "Harbor Light", "Coastal Dream", "Tide Chaser", "Sunset Sail", "Wind Dancer",
    "Ocean Pearl", "Sea Serpent", "Blue Dolphin", "Wave Catcher", "Marina Queen",
    "Harbor Master", "Coastal Breeze", "Tide Runner", "Sunset Cruiser", "Wind Spirit"
]

class BoatTracker:
    def __init__(self):
        self.boats = {}  # boat_id -> boat_info
        self.entries = []  # list of all entries
        self.last_modified = 0
        
    def generate_boat_id(self):
        """Generate a unique boat ID."""
        while True:
            boat_id = f"BT{random.randint(1000, 9999)}"
            if boat_id not in self.boats:
                return boat_id
    
    def get_or_create_boat(self):
        """Get a random boat or create a new one."""
        if not self.boats or random.random() < 0.3:  # 30% chance to create new boat
            boat_id = self.generate_boat_id()
            boat_name = random.choice(BOAT_NAMES)
            self.boats[boat_id] = {
                'id': boat_id,
                'name': boat_name,
                'last_seen': None,
                'status': 'unknown'
            }
            return self.boats[boat_id]
        else:
            # Return a random existing boat
            return random.choice(list(self.boats.values()))
    
    def process_csv(self):
        """Read and process the CSV file for new entries."""
        if not os.path.exists(CSV_PATH):
            return []
        
        current_modified = os.path.getmtime(CSV_PATH)
        if current_modified <= self.last_modified:
            return []
        
        self.last_modified = current_modified
        new_entries = []
        
        try:
            with open(CSV_PATH, 'r', newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
                # Process only new rows
                for row in rows:
                    timestamp = row.get('iso_time_utc', '')
                    value = int(row.get('value', 0))
                    device_name = row.get('device_name', 'Unknown Device')
                    
                    if timestamp and timestamp not in [entry['timestamp'] for entry in self.entries]:
                        boat = self.get_or_create_boat()
                        
                        # Determine status based on button value
                        if value == 1:  # Button press
                            status = 'ENTRY'
                            boat['status'] = 'in_harbor'
                        elif value == 0:  # Button release
                            status = 'EXIT'
                            boat['status'] = 'left_harbor'
                        else:
                            status = 'UNKNOWN'
                        
                        entry = {
                            'id': len(self.entries) + 1,
                            'timestamp': timestamp,
                            'local_time': self.format_local_time(timestamp),
                            'boat_id': boat['id'],
                            'boat_name': boat['name'],
                            'status': status,
                            'device': device_name
                        }
                        
                        self.entries.append(entry)
                        new_entries.append(entry)
                        boat['last_seen'] = timestamp
                        
        except Exception as e:
            print(f"Error reading CSV: {e}")
        
        return new_entries
    
    def format_local_time(self, iso_time):
        """Convert ISO time to local readable format."""
        try:
            dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return iso_time
    
    def get_recent_entries(self, limit=50):
        """Get recent entries for display."""
        return sorted(self.entries, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def get_boat_summary(self):
        """Get summary of all boats."""
        return list(self.boats.values())

# Global boat tracker instance
tracker = BoatTracker()

@app.route('/')
def index():
    """Main page showing boat entries/exits."""
    tracker.process_csv()
    recent_entries = tracker.get_recent_entries()
    boat_summary = tracker.get_boat_summary()
    
    return render_template('index.html', 
                         entries=recent_entries, 
                         boats=boat_summary,
                         total_entries=len(tracker.entries))

@app.route('/api/entries')
def api_entries():
    """API endpoint for recent entries."""
    new_entries = tracker.process_csv()
    recent_entries = tracker.get_recent_entries()
    
    return jsonify({
        'new_entries': new_entries,
        'recent_entries': recent_entries,
        'total_entries': len(tracker.entries),
        'last_update': tracker.last_modified
    })

@app.route('/api/boats')
def api_boats():
    """API endpoint for boat summary."""
    tracker.process_csv()
    return jsonify(tracker.get_boat_summary())

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics."""
    tracker.process_csv()
    
    # Count entries by status
    entry_count = sum(1 for e in tracker.entries if e['status'] == 'ENTRY')
    exit_count = sum(1 for e in tracker.entries if e['status'] == 'EXIT')
    
    # Count boats by status
    boats_in_harbor = sum(1 for b in tracker.boats.values() if b['status'] == 'in_harbor')
    boats_left = sum(1 for b in tracker.boats.values() if b['status'] == 'left_harbor')
    
    return jsonify({
        'total_entries': len(tracker.entries),
        'entry_count': entry_count,
        'exit_count': exit_count,
        'total_boats': len(tracker.boats),
        'boats_in_harbor': boats_in_harbor,
        'boats_left': boats_left,
        'last_update': tracker.last_modified
    })

if __name__ == '__main__':
    print("🚢 Boat Tracker Web Application")
    print("=" * 40)
    print(f"📁 Monitoring CSV file: {CSV_PATH}")
    print("🌐 Starting web server...")
    print("💡 Press the button on your selfie stick to log boat entries/exits!")
    print("🌍 Open http://localhost:5000 in your browser")
    print("=" * 40)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
