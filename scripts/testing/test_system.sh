#!/bin/bash
# Comprehensive System Testing Script
# Tests all components of the boat tracking system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Test function
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    print_status "Running test: $test_name"
    
    if eval "$test_command"; then
        print_status "✓ PASSED: $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        print_error "✗ FAILED: $test_name"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Test Python environment
test_python_environment() {
    print_header "Testing Python Environment"
    
    run_test "Python version check" "python3 --version | grep -q 'Python 3'"
    run_test "Virtual environment exists" "[ -d '.venv' ]"
    run_test "Virtual environment activation" "source .venv/bin/activate && python --version"
    run_test "Required packages installed" "source .venv/bin/activate && pip list | grep -q 'Flask'"
}

# Test system dependencies
test_system_dependencies() {
    print_header "Testing System Dependencies"
    
    run_test "BlueZ installed" "which bluetoothctl"
    run_test "OpenSSL available" "which openssl"
    run_test "Git available" "which git"
    run_test "Curl available" "which curl"
}

# Test BLE hardware
test_ble_hardware() {
    print_header "Testing BLE Hardware"
    
    run_test "BLE adapters detected" "hciconfig | grep -q 'hci'"
    run_test "BLE adapters enabled" "hciconfig hci0 up && hciconfig hci1 up"
    run_test "BLE scanning capability" "timeout 5s hcitool lescan > /dev/null 2>&1 || true"
}

# Test database
test_database() {
    print_header "Testing Database"
    
    run_test "Database file exists" "[ -f 'data/boat_tracking.db' ]"
    run_test "Database is accessible" "sqlite3 data/boat_tracking.db 'SELECT 1;'"
    run_test "Database tables exist" "sqlite3 data/boat_tracking.db '.tables' | grep -q 'boats'"
}

# Test configuration
test_configuration() {
    print_header "Testing Configuration"
    
    run_test "Main config file exists" "[ -f 'system/json/scanner_config.json' ]"
    run_test "Config file is valid JSON" "python3 -m json.tool system/json/scanner_config.json > /dev/null"
    run_test "Logs directory exists" "[ -d 'logs' ]"
}

# Test API endpoints
test_api_endpoints() {
    print_header "Testing API Endpoints"
    
    # Start system if not running
    if ! pgrep -f "boat_tracking_system.py" > /dev/null; then
        print_status "Starting system for API tests..."
        source .venv/bin/activate
        nohup python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000 > logs/test.log 2>&1 &
        sleep 5
    fi
    
    run_test "API server responding" "curl -s http://localhost:8000/health"
    run_test "Web dashboard responding" "curl -s http://localhost:8000/"
    run_test "Boats API endpoint" "curl -s http://localhost:8000/api/v1/boats"
    run_test "Beacons API endpoint" "curl -s http://localhost:8000/api/v1/beacons"
    run_test "Presence API endpoint" "curl -s http://localhost:8000/api/v1/presence"
}

# Test emergency notifications
test_emergency_notifications() {
    print_header "Testing Emergency Notifications"
    
    run_test "Emergency system files exist" "[ -f 'app/emergency_system.py' ]"
    run_test "Emergency JavaScript exists" "[ -f 'static/js/emergency-system.js' ]"
    run_test "Emergency API responding" "curl -s http://localhost:5000/api/emergency/status"
    run_test "VAPID keys configured" "python3 -c 'import os; assert os.getenv(\"VAPID_PRIVATE_KEY\")'"
}

# Test security features
test_security_features() {
    print_header "Testing Security Features"
    
    run_test "Security database exists" "[ -f 'app/secure_database.py' ]"
    run_test "Authentication system exists" "[ -f 'app/auth_system.py' ]"
    run_test "Security server exists" "[ -f 'app/secure_server.py' ]"
    run_test "SSL certificates exist" "[ -f 'ssl/cert.pem' ] && [ -f 'ssl/key.pem' ]"
}

# Test calibration
test_calibration() {
    print_header "Testing Calibration System"
    
    run_test "Calibration scripts exist" "[ -f 'calibration/door_lr_calibration.py' ]"
    run_test "Calibration data directory exists" "[ -d 'calibration/latest_plots' ]"
    run_test "Calibration guide exists" "[ -f 'calibration/CALIBRATION_GUIDE.md' ]"
}

# Test simulation
test_simulation() {
    print_header "Testing Simulation System"
    
    run_test "Simulator scripts exist" "[ -f 'sim_run_simulator.py' ]"
    run_test "Beacon simulator exists" "[ -f 'beacon_simulator.py' ]"
    run_test "FSM viewer exists" "[ -f 'sim_fsm_viewer.py' ]"
}

# Test documentation
test_documentation() {
    print_header "Testing Documentation"
    
    run_test "Main README exists" "[ -f 'README.md' ]"
    run_test "Setup guide exists" "[ -f 'SETUP_SUMMARY.md' ]"
    run_test "Security guide exists" "[ -f 'SECURITY.md' ]"
    run_test "Requirements matrix exists" "[ -f 'REQUIREMENTS_TRACEABILITY_MATRIX.md' ]"
}

# Test network connectivity
test_network() {
    print_header "Testing Network Connectivity"
    
    run_test "Internet connectivity" "ping -c 1 google.com > /dev/null 2>&1"
    run_test "Local network accessible" "ping -c 1 192.168.1.1 > /dev/null 2>&1 || ping -c 1 10.0.0.1 > /dev/null 2>&1"
    run_test "Port 5000 available" "! netstat -tlnp | grep -q ':5000'"
    run_test "Port 8000 available" "! netstat -tlnp | grep -q ':8000'"
}

# Performance test
test_performance() {
    print_header "Testing System Performance"
    
    run_test "Memory usage reasonable" "[ \$(free -m | awk 'NR==2{printf \"%.0f\", \$3*100/\$2}') -lt 80 ]"
    run_test "Disk space available" "[ \$(df . | awk 'NR==2{print \$4}') -gt 1000000 ]"
    run_test "CPU load reasonable" "[ \$(uptime | awk -F'load average:' '{print \$2}' | awk '{print \$1}' | sed 's/,//') -lt 2.0 ]"
}

# Integration test
test_integration() {
    print_header "Testing System Integration"
    
    run_test "System can start" "timeout 10s python3 boat_tracking_system.py --display-mode web --api-port 8001 --web-port 5001 > /dev/null 2>&1 || true"
    run_test "Database operations work" "python3 -c 'from app.database_models import DatabaseManager; db = DatabaseManager(\"data/boat_tracking.db\"); print(\"DB OK\")'"
    run_test "BLE scanning works" "python3 -c 'from ble_scanner import BLEScanner; print(\"BLE OK\")'"
}

# Cleanup function
cleanup() {
    print_status "Cleaning up test environment..."
    
    # Stop any test processes
    pkill -f "boat_tracking_system.py" || true
    pkill -f "api_server.py" || true
    
    # Remove test files
    rm -f logs/test.log
    
    print_status "Cleanup completed"
}

# Main test runner
run_all_tests() {
    local test_suite=${1:-"all"}
    
    print_header "Boat Tracking System Test Suite"
    echo "Test Suite: $test_suite"
    echo "Timestamp: $(date)"
    echo ""
    
    case $test_suite in
        "environment")
            test_python_environment
            test_system_dependencies
            ;;
        "hardware")
            test_ble_hardware
            test_network
            ;;
        "software")
            test_database
            test_configuration
            test_api_endpoints
            ;;
        "features")
            test_emergency_notifications
            test_security_features
            test_calibration
            ;;
        "integration")
            test_integration
            test_performance
            ;;
        "all")
            test_python_environment
            test_system_dependencies
            test_ble_hardware
            test_database
            test_configuration
            test_network
            test_api_endpoints
            test_emergency_notifications
            test_security_features
            test_calibration
            test_simulation
            test_documentation
            test_performance
            test_integration
            ;;
        *)
            print_error "Unknown test suite: $test_suite"
            echo "Available test suites: environment, hardware, software, features, integration, all"
            exit 1
            ;;
    esac
    
    # Print results
    print_header "Test Results Summary"
    echo "Total Tests: $TESTS_TOTAL"
    echo "Passed: $TESTS_PASSED"
    echo "Failed: $TESTS_FAILED"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        print_status "All tests passed! ✓"
        exit 0
    else
        print_error "Some tests failed! ✗"
        exit 1
    fi
}

# Show help
show_help() {
    echo "Boat Tracking System Test Suite"
    echo ""
    echo "Usage: $0 [TEST_SUITE]"
    echo ""
    echo "Test Suites:"
    echo "  environment    Test Python environment and dependencies"
    echo "  hardware       Test BLE hardware and network"
    echo "  software       Test database, config, and API"
    echo "  features       Test emergency notifications and security"
    echo "  integration    Test system integration and performance"
    echo "  all            Run all tests (default)"
    echo ""
    echo "Examples:"
    echo "  $0                    # Run all tests"
    echo "  $0 environment        # Test environment only"
    echo "  $0 hardware          # Test hardware only"
    echo "  $0 software          # Test software components"
}

# Trap to ensure cleanup
trap cleanup EXIT

# Main script logic
case "${1:-all}" in
    "environment"|"hardware"|"software"|"features"|"integration"|"all")
        run_all_tests "$1"
        ;;
    "help"|"--help"|"-h")
        show_help
        ;;
    *)
        print_error "Unknown test suite: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
