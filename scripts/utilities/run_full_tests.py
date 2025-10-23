#!/usr/bin/env python3
"""
Comprehensive Test Runner for Door-LR System
Runs complete test suite with 3 boats and generates comprehensive results.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.OKGREEN} {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.FAIL} {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.WARNING} {text}{Colors.ENDC}")


def run_command(cmd: List[str], description: str, check: bool = True, timeout: int = None):
    """Run a shell command and return the result."""
    print_info(f"{description}...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout
        )
        if result.returncode == 0:
            print_success(f"{description} completed")
        else:
            print_error(f"{description} failed with code {result.returncode}")
            if result.stderr:
                print(f"  Error: {result.stderr[:200]}")
        return result
    except subprocess.TimeoutExpired:
        print_error(f"{description} timed out")
        return None
    except Exception as e:
        print_error(f"{description} failed: {e}")
        return None


def check_api_server(api_url: str = "http://127.0.0.1:8000", web_url: str = "http://127.0.0.1:5000"):
    """Check if API server is running."""
    try:
        import requests
        resp = requests.get(f"{api_url}/api/presence", timeout=2)
        if resp.status_code == 200:
            print_success(f"API server is running at {api_url}")
            return True
    except:
        pass
    
    print_warning(f"API server is not running at {api_url}")
    print_info("Please start the server in another terminal:")
    print(f"  python3 boat_tracking_system.py --api-port 8000 --web-port 5000")
    return False


def seed_database(num_boats: int = 3, days: int = 7):
    """Seed the database with test boats."""
    print_header("SEEDING DATABASE")
    cmd = [
        sys.executable, "sim_seed_data.py",
        "--boats", str(num_boats),
        "--days", str(days),
        "--reset"
    ]
    result = run_command(cmd, f"Seeding database with {num_boats} boats")
    return result and result.returncode == 0


def run_simulator_movements(num_movements: int = 6, log_file: str = "test_sim.jsonl"):
    """Run simulator to generate test movements."""
    print_header("RUNNING SIMULATOR")
    cmd = [
        sys.executable, "door_lr_simulator.py",
        "--test-movements", str(num_movements),
        "--log-file", log_file,
        "--min-wait", "2.0",
        "--max-wait", "3.0"
    ]
    result = run_command(cmd, f"Running {num_movements} test movements", timeout=600)
    return result and result.returncode == 0


def run_test_t1(boat_id: str, server_url: str = "http://127.0.0.1:5000"):
    """Run automated T1 test (Location Detection)."""
    print_header("TEST T1: LOCATION DETECTION")
    cmd = [
        sys.executable, "test_plan/automated_T1.py",
        "--boat-id", boat_id,
        "--server-url", server_url,
        "--trials", "5",
        "--sample-seconds", "10",
        "--sample-rate-hz", "2"
    ]
    result = run_command(cmd, "Running T1 Location Detection test")
    return result and result.returncode == 0


def run_test_t2(boat_id: str, server_url: str = "http://127.0.0.1:5000"):
    """Run automated T2 test (Real-time Updates)."""
    print_header("TEST T2: REAL-TIME UPDATES")
    cmd = [
        sys.executable, "test_plan/automated_T2.py",
        "--boat-id", boat_id,
        "--server-url", server_url,
        "--duration", "60"
    ]
    result = run_command(cmd, "Running T2 Real-time Updates test")
    return result and result.returncode == 0


def run_test_t3(boat_id: str, server_url: str = "http://127.0.0.1:5000"):
    """Run automated T3 test (Timestamp Accuracy)."""
    print_header("TEST T3: TIMESTAMP ACCURACY")
    cmd = [
        sys.executable, "test_plan/automated_T3.py",
        "--boat-id", boat_id,
        "--server-url", server_url,
        "--duration", "60"
    ]
    result = run_command(cmd, "Running T3 Timestamp Accuracy test")
    return result and result.returncode == 0


def collect_test_results():
    """Collect and summarize all test results."""
    print_header("COLLECTING TEST RESULTS")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }
    
    # Find latest test results
    test_dirs = {
        "T1": "test_plan/results/T1",
        "T2": "test_plan/results/T2",
        "T3": "test_plan/results/T3"
    }
    
    for test_name, base_dir in test_dirs.items():
        if not os.path.exists(base_dir):
            print_warning(f"No results found for {test_name}")
            continue
        
        # Find latest result directory
        subdirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
        if not subdirs:
            print_warning(f"No result subdirectories for {test_name}")
            continue
        
        latest_dir = sorted(subdirs)[-1]
        result_path = os.path.join(base_dir, latest_dir)
        
        print_info(f"Found {test_name} results: {result_path}")
        
        # Try to read results
        csv_files = {
            "T1": "results.csv",
            "T2": "robustness.csv",
            "T3": "db_latency.csv"
        }
        
        csv_file = csv_files.get(test_name)
        if csv_file:
            csv_path = os.path.join(result_path, csv_file)
            if os.path.exists(csv_path):
                results["tests"][test_name] = {
                    "path": result_path,
                    "csv": csv_path,
                    "status": "completed"
                }
                print_success(f"{test_name} results collected")
            else:
                print_warning(f"CSV file not found: {csv_path}")
    
    return results


def generate_summary_report(results: Dict):
    """Generate a comprehensive summary report."""
    print_header("TEST SUMMARY REPORT")
    
    report_path = f"test_plan/results/summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print_success(f"Summary report saved to: {report_path}")
    
    # Print summary
    print(f"\n{Colors.BOLD}Test Results Summary:{Colors.ENDC}")
    for test_name, test_data in results.get("tests", {}).items():
        status = test_data.get("status", "unknown")
        path = test_data.get("path", "N/A")
        
        if status == "completed":
            print_success(f"{test_name}: {status}")
            print(f"  Results: {path}")
        else:
            print_error(f"{test_name}: {status}")
    
    # List all plots
    print(f"\n{Colors.BOLD}Generated Plots:{Colors.ENDC}")
    for test_name, test_data in results.get("tests", {}).items():
        path = test_data.get("path", "")
        if path and os.path.exists(path):
            png_files = [f for f in os.listdir(path) if f.endswith('.png')]
            for png_file in png_files:
                print(f"  {test_name}/{png_file}: {os.path.join(path, png_file)}")
    
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Run comprehensive door-lr system tests")
    parser.add_argument("--boats", type=int, default=3, help="Number of boats to test")
    parser.add_argument("--skip-seed", action="store_true", help="Skip database seeding")
    parser.add_argument("--skip-sim", action="store_true", help="Skip simulator run")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="API server URL")
    parser.add_argument("--web-url", default="http://127.0.0.1:5000", help="Web server URL")
    parser.add_argument("--movements", type=int, default=6, help="Number of simulator movements")
    parser.add_argument("--test-boat", default="RC-001", help="Boat ID to use for testing")
    
    args = parser.parse_args()
    
    print_header("DOOR-LR COMPREHENSIVE TEST SUITE")
    print_info(f"Test Configuration:")
    print(f"  Boats: {args.boats}")
    print(f"  Test Boat: {args.test_boat}")
    print(f"  Movements: {args.movements}")
    print(f"  API URL: {args.api_url}")
    print(f"  Web URL: {args.web_url}")
    
    # Step 1: Check if API server is running
    if not check_api_server(args.api_url, args.web_url):
        print_error("API server must be running to proceed")
        print_info("Start it with: python3 boat_tracking_system.py --api-port 8000 --web-port 5000")
        return 1
    
    # Step 2: Seed database
    if not args.skip_seed:
        if not seed_database(args.boats, days=7):
            print_error("Database seeding failed")
            return 1
        time.sleep(2)  # Allow database to settle
    else:
        print_info("Skipping database seeding")
    
    # Step 3: Run simulator movements
    if not args.skip_sim:
        if not run_simulator_movements(args.movements):
            print_warning("Simulator movements had issues, but continuing...")
        time.sleep(2)  # Allow system to settle
    else:
        print_info("Skipping simulator run")
    
    # Step 4: Run all tests
    test_results = []
    
    # T1: Location Detection
    t1_success = run_test_t1(args.test_boat, args.web_url)
    test_results.append(("T1", t1_success))
    time.sleep(2)
    
    # T2: Real-time Updates
    t2_success = run_test_t2(args.test_boat, args.web_url)
    test_results.append(("T2", t2_success))
    time.sleep(2)
    
    # T3: Timestamp Accuracy
    t3_success = run_test_t3(args.test_boat, args.web_url)
    test_results.append(("T3", t3_success))
    
    # Step 5: Collect and generate summary
    results = collect_test_results()
    report_path = generate_summary_report(results)
    
    # Final summary
    print_header("FINAL RESULTS")
    total_tests = len(test_results)
    passed_tests = sum(1 for _, success in test_results if success)
    
    for test_name, success in test_results:
        if success:
            print_success(f"{test_name}: PASSED")
        else:
            print_error(f"{test_name}: FAILED")
    
    print(f"\n{Colors.BOLD}Overall Success Rate: {passed_tests}/{total_tests} ({100*passed_tests//total_tests}%){Colors.ENDC}")
    print(f"\n{Colors.BOLD}Summary report: {report_path}{Colors.ENDC}")
    
    if passed_tests == total_tests:
        print_success("\n All tests passed!")
        return 0
    else:
        print_warning(f"\n {total_tests - passed_tests} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())









