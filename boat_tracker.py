#!/usr/bin/env python3
"""
Boat Tracker
Handles boat entry/exit tracking and health scoring logic
"""

import time
import threading
import csv
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Configuration
BEACON_BOAT_NAME = "rowing_clu"  # This will be the boat name
CSV_PATH = "boat_entries.csv"

class BoatTracker:
    def __init__(self):
        self.boats = {}
        self.entries = []
        self.current_boat = None
        self.lock = threading.Lock()
        self.csv_file = None
        self.csv_writer = None
        
        # Health scoring parameters
        self.target_weekly_hours = {
            '1x': 5, '2-': 8, '4x': 12, '8+': 20
        }
        self.boat_classes = ['1x', '2-', '4x', '8+']
        
    def ensure_csv(self, path):
        """Ensure CSV file exists with proper headers."""
        new = not os.path.exists(path)
        f = open(path, "a", newline="")
        writer = csv.writer(f)
        if new:
            writer.writerow([
                "timestamp", "unix_time", "event_type", "boat_id", 
                "boat_name", "status", "device", "rssi"
            ])
        return f, writer
    
    def close_csv(self):
        """Close CSV file."""
        if self.csv_file:
            self.csv_file.close()
    
    def get_or_create_beacon_boat(self):
        """Get existing beacon boat or create one if it doesn't exist."""
        # Look for existing beacon boat
        for boat_id, boat in self.boats.items():
            if boat['name'] == BEACON_BOAT_NAME:
                return boat
        
        # Create new boat for this beacon
        boat_id = f"BT{len(self.boats) + 1:04d}"
        boat_class = self.boat_classes[len(self.boats) % len(self.boat_classes)]
        
        boat = {
            'id': boat_id,
            'name': BEACON_BOAT_NAME,
            'class': boat_class,
            'status': 'entering',
            'entry_time': None,
            'exit_time': None,
            'total_water_hours': 0,
            'total_sessions': 0,
            'last_activity': None,
            'service_hours_since': 0,
            'last_service': None,
            'health_score': 100,
            'health_breakdown': {},
            'current_session_start': None  # Track when current session started
        }
        self.boats[boat_id] = boat
        return boat
    
    def calculate_health_score(self, boat):
        """Calculate boat health score (0-100)."""
        score = 100
        breakdown = {}
        
        # Get boat class target
        target_hours = self.target_weekly_hours.get(boat['class'], 5)
        
        # Calculate usage metrics (simplified for demo)
        water_hours_7d = min(boat['total_water_hours'], target_hours * 1.5)  # Cap at 1.5x target
        water_hours_30d = min(boat['total_water_hours'] * 4, target_hours * 4)  # Estimate monthly
        
        # Overuse penalty (wear)
        if water_hours_7d > target_hours * 1.2:
            overuse_penalty = min(40, (water_hours_7d - target_hours * 1.2) / target_hours * 100)
            score -= overuse_penalty
            breakdown['overuse'] = f"-{overuse_penalty:.1f} (overuse)"
        
        # Underuse penalty (stale)
        monthly_min = target_hours * 4 * 0.6
        if water_hours_30d < monthly_min:
            underuse_penalty = min(25, (monthly_min - water_hours_30d) / monthly_min * 25)
            score -= underuse_penalty
            breakdown['underuse'] = f"-{underuse_penalty:.1f} (underuse)"
        
        # Idle penalty
        if boat['last_activity']:
            days_idle = (time.time() - boat['last_activity']) / 86400
            if days_idle > 7:
                idle_penalty = min(20, (days_idle - 7) * 2)
                score -= idle_penalty
                breakdown['idle'] = f"-{idle_penalty:.1f} (idle {days_idle:.0f} days)"
        
        # Service penalty
        if boat['service_hours_since'] > 100:
            service_penalty = min(15, (boat['service_hours_since'] - 100) / 50 * 15)
            score -= service_penalty
            breakdown['service'] = f"-{service_penalty:.1f} (service overdue)"
        
        # Clamp to 0-100
        score = max(0, min(100, score))
        
        # Determine health status
        if score >= 80:
            health_status = "Excellent"
            health_color = "green"
        elif score >= 60:
            health_status = "Good"
            health_color = "blue"
        elif score >= 40:
            health_status = "Fair"
            health_color = "orange"
        else:
            health_status = "Poor"
            health_color = "red"
        
        return {
            'score': int(score),
            'status': health_status,
            'color': health_color,
            'breakdown': breakdown,
            'target_hours': target_hours,
            'water_hours_7d': water_hours_7d,
            'water_hours_30d': water_hours_30d,
            'service_hours': boat['service_hours_since']
        }
    
    def update_boat_health(self, boat_id, session_duration_hours=None):
        """Update boat health metrics with actual session duration."""
        if boat_id in self.boats:
            boat = self.boats[boat_id]
            
            # Update basic metrics
            boat['total_sessions'] += 1
            boat['last_activity'] = time.time()
            
            # Use actual session duration if provided, otherwise calculate from current session
            if session_duration_hours is not None:
                session_hours = session_duration_hours
            elif boat.get('current_session_start'):
                # Calculate duration from when session started
                session_hours = (time.time() - boat['current_session_start']) / 3600  # Convert to hours
            else:
                # Fallback to simulation (shouldn't happen in normal operation)
                session_hours = 0.5  # 30 minutes default
            
            boat['total_water_hours'] += session_hours
            boat['service_hours_since'] += session_hours
            
            # Calculate health score
            health_data = self.calculate_health_score(boat)
            boat['health_score'] = health_data['score']
            boat['health_breakdown'] = health_data
    
    def handle_beacon_detected(self, rssi, signal_percentage, signal_strength):
        """Handle beacon detection - boat entering."""
        with self.lock:
            if self.current_boat is None:
                # Get or create the beacon boat
                boat = self.get_or_create_beacon_boat()
                self.current_boat = boat
                boat['status'] = 'entering'
                boat['entry_time'] = datetime.now(timezone.utc).isoformat()
                boat['current_session_start'] = time.time()  # Track session start time
                
                entry = {
                    'id': len(self.entries) + 1,
                    'timestamp': boat['entry_time'],
                    'local_time': self.format_local_time(boat['entry_time']),
                    'boat_id': boat['id'],
                    'boat_name': boat['name'],
                    'boat_class': boat['class'],
                    'status': 'ENTRY',
                    'device': 'BLE Beacon',
                    'rssi': rssi,
                    'signal_percentage': signal_percentage,
                    'signal_strength': signal_strength,
                    'health_score': boat['health_score'],
                    'health_status': boat['health_breakdown'].get('status', 'Unknown')
                }
                self.entries.append(entry)
                
                # Log to CSV
                if self.csv_writer:
                    self.csv_writer.writerow([
                        entry['timestamp'], 
                        time.time(), 
                        'BEACON_DETECTED', 
                        entry['boat_id'], 
                        entry['boat_name'], 
                        entry['status'], 
                        'BLE Beacon',
                        rssi
                    ])
                    self.csv_file.flush()
                
                print(f"Boat {boat['id']} ({boat['name']}) ENTERED harbor - RSSI: {rssi} dBm ({signal_percentage}% - {signal_strength})")
                return entry
            else:
                # Just update signal info for existing boat
                print(f"Beacon update - RSSI: {rssi} dBm ({signal_percentage}% - {signal_strength})")
        return None
    
    def handle_beacon_lost(self, rssi, signal_percentage, signal_strength):
        """Handle beacon lost - boat exiting."""
        with self.lock:
            if self.current_boat is not None:
                # Calculate actual session duration
                session_duration_hours = 0
                if self.current_boat.get('current_session_start'):
                    session_duration_hours = (time.time() - self.current_boat['current_session_start']) / 3600
                    print(f"Session duration: {session_duration_hours:.2f} hours")
                
                # Update boat status
                self.current_boat['status'] = 'exiting'
                self.current_boat['exit_time'] = datetime.now(timezone.utc).isoformat()
                
                # Update boat health with actual session duration
                self.update_boat_health(self.current_boat['id'], session_duration_hours)
                
                # Create exit entry
                entry = {
                    'id': len(self.entries) + 1,
                    'timestamp': self.current_boat['exit_time'],
                    'local_time': self.format_local_time(self.current_boat['exit_time']),
                    'boat_id': self.current_boat['id'],
                    'boat_name': self.current_boat['name'],
                    'boat_class': self.current_boat['class'],
                    'status': 'EXIT',
                    'device': 'BLE Beacon',
                    'rssi': rssi,
                    'signal_percentage': signal_percentage,
                    'signal_strength': signal_strength,
                    'health_score': self.current_boat['health_score'],
                    'health_status': self.current_boat['health_breakdown'].get('status', 'Unknown'),
                    'session_duration_hours': session_duration_hours
                }
                self.entries.append(entry)
                
                # Log to CSV
                if self.csv_writer:
                    self.csv_writer.writerow([
                        entry['timestamp'], 
                        time.time(), 
                        'BEACON_LOST', 
                        entry['boat_id'], 
                        entry['boat_name'], 
                        entry['status'], 
                        'BLE Beacon',
                        rssi
                    ])
                    self.csv_file.flush()
                
                print(f"Boat {self.current_boat['id']} ({self.current_boat['name']}) EXITED harbor - Session: {session_duration_hours:.2f}h - Health: {self.current_boat['health_score']}/100")
                
                # Clear current boat
                self.current_boat = None
                
                return entry
            else:
                # Already handled or no boat to exit
                print("Beacon lost but no boat to exit")
        return None
    
    def format_local_time(self, utc_time_str):
        """Format UTC time to local time string."""
        try:
            dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return utc_time_str
    
    def get_stats(self):
        """Get current statistics."""
        with self.lock:
            entry_count = sum(1 for e in self.entries if e['status'] == 'ENTRY')
            exit_count = sum(1 for e in self.entries if e['status'] == 'EXIT')
            boats_in_harbor = sum(1 for b in self.boats.values() if b['status'] == 'entering')
            boats_left = sum(1 for b in self.boats.values() if b['status'] == 'exiting')
            
            return {
                'total_entries': len(self.entries),
                'entry_count': entry_count,
                'exit_count': exit_count,
                'total_boats': len(self.boats),
                'boats_in_harbor': boats_in_harbor,
                'boats_left': boats_left,
                'current_boat': self.current_boat['id'] if self.current_boat else None,
                'beacon_in_range': self.current_boat is not None
            }
    
    def get_entries(self):
        """Get recent entries."""
        with self.lock:
            return self.entries[-20:]  # Last 20 entries
    
    def get_boats(self):
        """Get all boats with health information."""
        with self.lock:
            boats_list = []
            for boat_id, boat in self.boats.items():
                # Calculate health score if not already done
                if 'health_breakdown' not in boat or not boat['health_breakdown']:
                    health_data = self.calculate_health_score(boat)
                    boat['health_score'] = health_data['score']
                    boat['health_breakdown'] = health_data
                
                boats_list.append(boat)
            return boats_list
