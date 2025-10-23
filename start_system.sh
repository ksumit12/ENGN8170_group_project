#!/bin/bash
# Comprehensive Boat Tracking System Startup Script
# Handles WiFi setup, dependencies, security, calibration, and system launch

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

# Default values
ENABLE_SECURITY=false
ENABLE_EMERGENCY=false
SKIP_CALIBRATION=false
DISPLAY_MODE="web"
API_PORT=8000
WEB_PORT=5000

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --security)
            ENABLE_SECURITY=true
            shift
            ;;
        --emergency)
            ENABLE_EMERGENCY=true
            shift
            ;;
        --skip-calibration)
            SKIP_CALIBRATION=true
            shift
            ;;
        --display-mode)
            DISPLAY_MODE="$2"
            shift 2
            ;;
        --api-port)
            API_PORT="$2"
            shift 2
            ;;
        --web-port)
            WEB_PORT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --security              Enable security features (HTTPS + encryption)"
            echo "  --emergency             Enable emergency notification system"
            echo "  --skip-calibration      Skip calibration process"
            echo "  --display-mode MODE     Set display mode: web, terminal, both (default: web)"
            echo "  --api-port PORT         Set API port (default: 8000)"
            echo "  --web-port PORT         Set web port (default: 5000)"
            echo "  --help                  Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Basic startup"
            echo "  $0 --security --emergency             # Full security + emergency"
            echo "  $0 --display-mode both                # Web + terminal display"
            echo "  $0 --skip-calibration                 # Skip calibration"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

print_header "Boat Tracking System Startup"
echo "Configuration:"
echo "  Security: $ENABLE_SECURITY"
echo "  Emergency Notifications: $ENABLE_EMERGENCY"
echo "  Skip Calibration: $SKIP_CALIBRATION"
echo "  Display Mode: $DISPLAY_MODE"
echo "  API Port: $API_PORT"
echo "  Web Port: $WEB_PORT"
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root"
   exit 1
fi

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    print_error "Python 3.8 or higher is required. Found: $python_version"
    exit 1
fi

print_status "Python version check passed: $python_version"

# Step 1: WiFi Setup
print_header "Step 1: WiFi Network Setup"

if [ -f "wifi_auto.sh" ]; then
    print_status "Running WiFi setup..."
    chmod +x wifi_auto.sh
    ./wifi_auto.sh
else
    print_warning "WiFi setup script not found, skipping WiFi configuration"
fi

# Step 2: System Dependencies
print_header "Step 2: Installing System Dependencies"

# Update package list
print_status "Updating package list..."
sudo apt-get update

# Install essential packages
print_status "Installing essential packages..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    bluez \
    bluez-tools \
    libbluetooth-dev \
    openssl \
    curl \
    git \
    htop \
    vim

# Install Python packages
print_status "Installing Python packages..."
pip3 install --user -r requirements.txt

# Step 3: Virtual Environment Setup
print_header "Step 3: Virtual Environment Setup"

if [ ! -d ".venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv .venv
fi

print_status "Activating virtual environment..."
source .venv/bin/activate

# Install requirements in virtual environment
print_status "Installing requirements in virtual environment..."
pip install -r requirements.txt

# Step 4: Security Setup (if requested)
if [ "$ENABLE_SECURITY" = true ]; then
    print_header "Step 4: Security Setup"
    
    if [ -f "enable_security.sh" ]; then
        print_status "Enabling security features..."
        chmod +x enable_security.sh
        ./enable_security.sh
    else
        print_warning "Security setup script not found"
    fi
fi

# Step 5: Emergency Notification Setup (if requested)
if [ "$ENABLE_EMERGENCY" = true ]; then
    print_header "Step 5: Emergency Notification Setup"
    
    if [ -f "setup_emergency_system.sh" ]; then
        print_status "Setting up emergency notification system..."
        chmod +x setup_emergency_system.sh
        ./setup_emergency_system.sh
    else
        print_warning "Emergency setup script not found"
    fi
fi

# Step 6: Database Initialization
print_header "Step 6: Database Initialization"

if [ -f "setup_new_system.py" ]; then
    print_status "Initializing database..."
    python3 setup_new_system.py
else
    print_warning "Database setup script not found"
fi

# Step 7: Calibration (if not skipped)
if [ "$SKIP_CALIBRATION" = false ]; then
    print_header "Step 7: System Calibration"
    
    print_status "Starting calibration process..."
    echo ""
    echo "Calibration is required for accurate boat detection."
    echo "Please follow the calibration guide:"
    echo "1. Place beacons in known positions (CENTER, LEFT, RIGHT)"
    echo "2. Run calibration script: python3 calibration/door_lr_calibration.py"
    echo "3. Follow the prompts to complete calibration"
    echo ""
    
    read -p "Press Enter when calibration is complete, or 's' to skip: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        print_warning "Calibration skipped"
    else
        print_status "Calibration completed"
    fi
fi

# Step 8: System Configuration
print_header "Step 8: System Configuration"

# Create configuration file
config_file="system/json/scanner_config.json"
if [ ! -f "$config_file" ]; then
    print_status "Creating default configuration..."
    mkdir -p system/json
    
    cat > "$config_file" << EOF
{
  "database_path": "data/boat_tracking.db",
  "api_host": "0.0.0.0",
  "api_port": $API_PORT,
  "web_host": "0.0.0.0",
  "web_port": $WEB_PORT,
  "scanners": [
    {
      "scanner_id": "door-left",
      "adapter": "hci1",
      "scan_interval": 1.0,
      "scan_window": 0.5,
      "passive": false
    },
    {
      "scanner_id": "door-right", 
      "adapter": "hci0",
      "scan_interval": 1.0,
      "scan_window": 0.5,
      "passive": false
    }
  ],
  "emergency_notifications": {
    "enabled": $ENABLE_EMERGENCY,
    "closing_time": "18:00",
    "check_interval": 60,
    "escalation_enabled": true,
    "vapid_private_key": "",
    "vapid_public_key": "",
    "wifi_network": {
      "ssid": "Red Shed WiFi",
      "range": "192.168.1.0/24"
    }
  },
  "logging": {
    "level": "INFO",
    "file": "logs/boat_tracking.log",
    "max_size": "10MB",
    "backup_count": 5
  },
  "security": {
    "enable_https": $ENABLE_SECURITY,
    "enable_auth": $ENABLE_SECURITY,
    "enable_encryption": $ENABLE_SECURITY
  }
}
EOF
    print_status "Configuration file created: $config_file"
fi

# Step 9: Start System
print_header "Step 9: Starting Boat Tracking System"

print_status "Starting system with display mode: $DISPLAY_MODE"

# Create logs directory
mkdir -p logs

# Start the system
python3 boat_tracking_system.py \
    --display-mode "$DISPLAY_MODE" \
    --api-port "$API_PORT" \
    --web-port "$WEB_PORT" \
    --config "$config_file"

print_header "System Started Successfully"
echo ""
echo "System is now running!"
echo ""
echo "Access Points:"
echo "  Web Dashboard: http://localhost:$WEB_PORT"
echo "  API Server: http://localhost:$API_PORT"
echo "  Health Check: http://localhost:$API_PORT/health"
echo ""
echo "Display Mode: $DISPLAY_MODE"
if [ "$ENABLE_SECURITY" = true ]; then
    echo "Security: Enabled (HTTPS + Encryption)"
fi
if [ "$ENABLE_EMERGENCY" = true ]; then
    echo "Emergency Notifications: Enabled"
fi
echo ""
echo "To stop the system: Ctrl+C or run ./scripts/management/stop_system.sh"
echo "To view logs: tail -f logs/boat_tracking.log"
echo ""
print_status "Boat Tracking System startup completed successfully!"
