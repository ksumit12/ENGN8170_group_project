#!/bin/bash
# Comprehensive System Management Script
# Handles start, stop, restart, status, logs, and maintenance

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

# Check if system is running
is_system_running() {
    pgrep -f "boat_tracking_system.py" > /dev/null 2>&1
}

# Get system status
get_system_status() {
    if is_system_running; then
        echo "RUNNING"
    else
        echo "STOPPED"
    fi
}

# Start system
start_system() {
    if is_system_running; then
        print_warning "System is already running"
        return 0
    fi
    
    print_header "Starting Boat Tracking System"
    
    # Check if virtual environment exists
    if [ ! -d ".venv" ]; then
        print_error "Virtual environment not found. Please run setup first."
        exit 1
    fi
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Start system in background
    nohup python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000 > logs/system.log 2>&1 &
    
    sleep 3
    
    if is_system_running; then
        print_status "System started successfully"
        echo "  Web Dashboard: http://localhost:5000"
        echo "  API Server: http://localhost:8000"
        echo "  Logs: tail -f logs/system.log"
    else
        print_error "Failed to start system"
        exit 1
    fi
}

# Stop system
stop_system() {
    if ! is_system_running; then
        print_warning "System is not running"
        return 0
    fi
    
    print_header "Stopping Boat Tracking System"
    
    # Stop main system
    pkill -f "boat_tracking_system.py" || true
    
    # Stop any scanner processes
    pkill -f "ble_scanner.py" || true
    
    # Stop any API server processes
    pkill -f "api_server.py" || true
    
    sleep 2
    
    if ! is_system_running; then
        print_status "System stopped successfully"
    else
        print_warning "Some processes may still be running"
    fi
}

# Restart system
restart_system() {
    print_header "Restarting Boat Tracking System"
    stop_system
    sleep 2
    start_system
}

# Show system status
show_status() {
    print_header "System Status"
    
    status=$(get_system_status)
    echo "Status: $status"
    
    if [ "$status" = "RUNNING" ]; then
        echo ""
        echo "Running Processes:"
        pgrep -f "boat_tracking_system.py" | while read pid; do
            echo "  PID $pid: $(ps -p $pid -o cmd= --no-headers)"
        done
        
        echo ""
        echo "Network Ports:"
        netstat -tlnp 2>/dev/null | grep -E ":(5000|8000)" || echo "  No ports found"
        
        echo ""
        echo "Access Points:"
        echo "  Web Dashboard: http://localhost:5000"
        echo "  API Server: http://localhost:8000"
        echo "  Health Check: http://localhost:8000/health"
    fi
    
    echo ""
    echo "Log Files:"
    if [ -f "logs/system.log" ]; then
        echo "  System Log: logs/system.log ($(wc -l < logs/system.log) lines)"
    fi
    if [ -f "logs/boat_tracking.log" ]; then
        echo "  Boat Tracking Log: logs/boat_tracking.log ($(wc -l < logs/boat_tracking.log) lines)"
    fi
}

# Show logs
show_logs() {
    local log_type=${1:-"system"}
    
    case $log_type in
        "system")
            log_file="logs/system.log"
            ;;
        "boat")
            log_file="logs/boat_tracking.log"
            ;;
        "emergency")
            log_file="logs/emergency.log"
            ;;
        *)
            print_error "Unknown log type: $log_type"
            echo "Available log types: system, boat, emergency"
            exit 1
            ;;
    esac
    
    if [ ! -f "$log_file" ]; then
        print_error "Log file not found: $log_file"
        exit 1
    fi
    
    print_header "Showing $log_type logs"
    tail -f "$log_file"
}

# Test system
test_system() {
    print_header "Testing System"
    
    if ! is_system_running; then
        print_error "System is not running. Please start it first."
        exit 1
    fi
    
    print_status "Testing API endpoints..."
    
    # Test health endpoint
    if curl -s http://localhost:8000/health > /dev/null; then
        print_status "✓ API server is responding"
    else
        print_error "✗ API server is not responding"
    fi
    
    # Test web dashboard
    if curl -s http://localhost:5000 > /dev/null; then
        print_status "✓ Web dashboard is responding"
    else
        print_error "✗ Web dashboard is not responding"
    fi
    
    # Test emergency notifications if enabled
    if curl -s http://localhost:5000/api/emergency/status > /dev/null 2>&1; then
        print_status "✓ Emergency notification system is available"
    else
        print_warning "⚠ Emergency notification system not available"
    fi
    
    print_status "System test completed"
}

# Maintenance tasks
maintenance() {
    local task=${1:-"all"}
    
    print_header "System Maintenance"
    
    case $task in
        "logs")
            print_status "Cleaning old log files..."
            find logs/ -name "*.log" -mtime +7 -delete 2>/dev/null || true
            print_status "Log cleanup completed"
            ;;
        "database")
            print_status "Database maintenance..."
            if [ -f "data/boat_tracking.db" ]; then
                sqlite3 data/boat_tracking.db "VACUUM;" 2>/dev/null || true
                print_status "Database optimization completed"
            else
                print_warning "Database file not found"
            fi
            ;;
        "backups")
            print_status "Creating system backup..."
            backup_dir="backups/$(date +%Y%m%d_%H%M%S)"
            mkdir -p "$backup_dir"
            
            if [ -f "data/boat_tracking.db" ]; then
                cp data/boat_tracking.db "$backup_dir/"
            fi
            
            if [ -d "logs" ]; then
                cp -r logs "$backup_dir/"
            fi
            
            print_status "Backup created: $backup_dir"
            ;;
        "all")
            maintenance "logs"
            maintenance "database"
            maintenance "backups"
            ;;
        *)
            print_error "Unknown maintenance task: $task"
            echo "Available tasks: logs, database, backups, all"
            exit 1
            ;;
    esac
}

# Update system
update_system() {
    print_header "Updating System"
    
    print_status "Stopping system..."
    stop_system
    
    print_status "Updating code..."
    git pull origin main || print_warning "Git pull failed"
    
    print_status "Updating dependencies..."
    source .venv/bin/activate
    pip install -r requirements.txt --upgrade
    
    print_status "Starting system..."
    start_system
    
    print_status "System update completed"
}

# Show help
show_help() {
    echo "Boat Tracking System Management Script"
    echo ""
    echo "Usage: $0 COMMAND [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start                    Start the system"
    echo "  stop                     Stop the system"
    echo "  restart                  Restart the system"
    echo "  status                   Show system status"
    echo "  logs [TYPE]              Show logs (system, boat, emergency)"
    echo "  test                     Test system functionality"
    echo "  maintenance [TASK]       Run maintenance tasks (logs, database, backups, all)"
    echo "  update                   Update system code and dependencies"
    echo "  help                     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start                # Start the system"
    echo "  $0 status               # Check system status"
    echo "  $0 logs system          # Show system logs"
    echo "  $0 maintenance all      # Run all maintenance tasks"
    echo "  $0 test                 # Test system functionality"
}

# Main script logic
case "${1:-help}" in
    "start")
        start_system
        ;;
    "stop")
        stop_system
        ;;
    "restart")
        restart_system
        ;;
    "status")
        show_status
        ;;
    "logs")
        show_logs "$2"
        ;;
    "test")
        test_system
        ;;
    "maintenance")
        maintenance "$2"
        ;;
    "update")
        update_system
        ;;
    "help"|"--help"|"-h")
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
