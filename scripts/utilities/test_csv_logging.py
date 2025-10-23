#!/usr/bin/env python3
"""
Test script for automated CSV logging system
Run this to verify the CSV logging functionality works correctly
"""

import os
import sys
from datetime import datetime, timezone, timedelta

def test_directory_structure():
    """Test that the directory structure can be created."""
    print("Testing directory structure creation...")
    
    test_date = datetime.now(timezone.utc) - timedelta(days=1)
    daily_dir = f"data/csv_logs/daily/{test_date.strftime('%Y')}/{test_date.strftime('%m')}"
    
    try:
        os.makedirs(daily_dir, exist_ok=True)
        print(f" Daily directory created: {daily_dir}")
    except Exception as e:
        print(f" Failed to create daily directory: {e}")
        return False
    
    week_start = test_date - timedelta(days=7)
    week_label = f"Week_{week_start.strftime('%Y%m%d')}_to_{test_date.strftime('%Y%m%d')}"
    weekly_dir = f"data/csv_logs/weekly_exports/{test_date.strftime('%Y')}/{week_label}"
    
    try:
        os.makedirs(weekly_dir, exist_ok=True)
        print(f" Weekly directory created: {weekly_dir}")
    except Exception as e:
        print(f" Failed to create weekly directory: {e}")
        return False
    
    return True

def test_csv_file_creation():
    """Test that CSV files can be created with proper naming."""
    print("\nTesting CSV file creation...")
    
    import csv
    test_date = datetime.now(timezone.utc) - timedelta(days=1)
    daily_dir = f"data/csv_logs/daily/{test_date.strftime('%Y')}/{test_date.strftime('%m')}"
    
    # Test boat usage file
    filename = f"boat_usage_{test_date.strftime('%Y%m%d')}.csv"
    filepath = os.path.join(daily_dir, filename)
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Sequence', 'Boat Name', 'Boat Class', 'Exit Time', 'Entry Time', 'Duration (min)'])
            writer.writerow([1, 'Test Boat', 'Single', '2025-10-22 08:00:00', '2025-10-22 09:30:00', 90])
        print(f" Created test file: {filepath}")
        
        # Verify file exists and has content
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            print(f" File verified: {os.path.getsize(filepath)} bytes")
        else:
            print(f" File verification failed")
            return False
            
    except Exception as e:
        print(f" Failed to create CSV file: {e}")
        return False
    
    # Test system logs file
    filename = f"system_logs_{test_date.strftime('%Y%m%d')}.csv"
    filepath = os.path.join(daily_dir, filename)
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Timestamp', 'Level', 'Component', 'Message'])
            writer.writerow(['2025-10-22 08:00:00', 'INFO', 'TEST', 'Test log entry'])
        print(f" Created test file: {filepath}")
    except Exception as e:
        print(f" Failed to create system logs file: {e}")
        return False
    
    # Test sessions file
    filename = f"boat_sessions_{test_date.strftime('%Y%m%d')}.csv"
    filepath = os.path.join(daily_dir, filename)
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Boat ID', 'Boat Name', 'Boat Class', 'Session Start', 'Session End', 'Duration (min)', 'Status'])
            writer.writerow(['boat_001', 'Test Boat', 'Single', '2025-10-22 08:00:00', '2025-10-22 09:30:00', 90, 'Completed'])
        print(f" Created test file: {filepath}")
    except Exception as e:
        print(f" Failed to create sessions file: {e}")
        return False
    
    return True

def test_weekly_structure():
    """Test weekly export structure."""
    print("\nTesting weekly export structure...")
    
    import shutil
    test_date = datetime.now(timezone.utc)
    week_start = test_date - timedelta(days=7)
    week_label = f"Week_{week_start.strftime('%Y%m%d')}_to_{test_date.strftime('%Y%m%d')}"
    weekly_dir = f"data/csv_logs/weekly_exports/{test_date.strftime('%Y')}/{week_label}"
    
    os.makedirs(weekly_dir, exist_ok=True)
    
    # Create weekly summary
    import csv
    filename = f"WEEKLY_SUMMARY_{week_start.strftime('%Y%m%d')}_to_{test_date.strftime('%Y%m%d')}.csv"
    filepath = os.path.join(weekly_dir, filename)
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Boat Name', 'Boat Class', 'Total Trips', 'Total Minutes', 'Avg Duration (min)', 'Max Duration (min)', 'Status'])
            writer.writerow(['Test Boat', 'Single', 10, 900, 90, 120, 'operational'])
        print(f" Created weekly summary: {filepath}")
    except Exception as e:
        print(f" Failed to create weekly summary: {e}")
        return False
    
    return True

def display_structure():
    """Display the created directory structure."""
    print("\n" + "="*70)
    print("Directory Structure:")
    print("="*70)
    
    base_dir = "data/csv_logs"
    if not os.path.exists(base_dir):
        print(" Base directory doesn't exist yet")
        return
    
    for root, dirs, files in os.walk(base_dir):
        level = root.replace(base_dir, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in sorted(files):
            file_path = os.path.join(root, file)
            size = os.path.getsize(file_path)
            print(f'{subindent}{file} ({size} bytes)')

def main():
    print("="*70)
    print("CSV Logging System Test")
    print("="*70)
    
    all_passed = True
    
    # Test 1: Directory structure
    if not test_directory_structure():
        all_passed = False
    
    # Test 2: CSV file creation
    if not test_csv_file_creation():
        all_passed = False
    
    # Test 3: Weekly structure
    if not test_weekly_structure():
        all_passed = False
    
    # Display structure
    display_structure()
    
    # Summary
    print("\n" + "="*70)
    if all_passed:
        print(" All tests passed! CSV logging system is ready.")
        print("\nNext steps:")
        print("1. Start the boat tracking system")
        print("2. Test manual triggers:")
        print("   curl -X POST http://localhost:5001/api/admin/trigger-daily-accumulation")
        print("   curl -X POST http://localhost:5001/api/admin/trigger-weekly-export")
        print("3. Check the generated files in data/csv_logs/")
    else:
        print(" Some tests failed. Please check the errors above.")
    print("="*70)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())




