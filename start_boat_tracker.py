#!/usr/bin/env python3
"""
Startup script for Boat Tracker System
Runs both the button logger and web server
"""

import subprocess
import time
import signal
import sys
import os

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\n🛑 Shutting down Boat Tracker System...")
    sys.exit(0)

def main():
    print("🚢 Boat Tracker System Startup")
    print("=" * 50)
    print("This script will start:")
    print("1. Button Logger (sudo required)")
    print("2. Web Server (Flask)")
    print("=" * 50)
    
    # Check if running as root
    if os.geteuid() != 0:
        print("⚠️  Warning: Not running as root")
        print("   The button logger may not work properly")
        print("   Consider running with: sudo python3 start_boat_tracker.py")
        print()
    
    # Check if required files exist
    if not os.path.exists("bt_trigger_logger.py"):
        print("❌ Error: bt_trigger_logger.py not found!")
        return
    
    if not os.path.exists("boat_tracker.py"):
        print("❌ Error: boat_tracker.py not found!")
        return
    
    print("✅ All required files found")
    print()
    
    # Start the button logger in background
    print("🚀 Starting Button Logger...")
    try:
        logger_process = subprocess.Popen(
            ["python3", "bt_trigger_logger.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print("✅ Button Logger started (PID: {})".format(logger_process.pid))
    except Exception as e:
        print("❌ Failed to start Button Logger: {}".format(e))
        return
    
    # Wait a moment for logger to initialize
    time.sleep(2)
    
    # Start the web server
    print("🌐 Starting Web Server...")
    try:
        web_process = subprocess.Popen(
            ["python3", "boat_tracker.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print("✅ Web Server started (PID: {})".format(web_process.pid))
    except Exception as e:
        print("❌ Failed to start Web Server: {}".format(e))
        logger_process.terminate()
        return
    
    print()
    print("🎉 Boat Tracker System is running!")
    print("=" * 50)
    print("📱 Button Logger: Monitoring selfie stick button")
    print("🌍 Web Interface: http://localhost:5000")
    print("💡 Press the button on your selfie stick to log boat entries!")
    print("🛑 Press Ctrl+C to stop both services")
    print("=" * 50)
    
    try:
        # Wait for processes
        while True:
            time.sleep(1)
            
            # Check if processes are still running
            if logger_process.poll() is not None:
                print("❌ Button Logger stopped unexpectedly")
                break
                
            if web_process.poll() is not None:
                print("❌ Web Server stopped unexpectedly")
                break
                
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    
    finally:
        # Clean up processes
        print("🔄 Stopping Button Logger...")
        logger_process.terminate()
        logger_process.wait()
        
        print("🔄 Stopping Web Server...")
        web_process.terminate()
        web_process.wait()
        
        print("✅ All services stopped")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    main()
