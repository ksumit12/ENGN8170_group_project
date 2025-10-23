#!/bin/bash
# Two-Scanner Boat Tracking System - Complete Startup Script
# This script sets up and starts the complete two-scanner system with security

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
VENV_DIR="$PROJECT_DIR/.venv"
CONFIG_DIR="$PROJECT_DIR/system/json"
CALIBRATION_DIR="$PROJECT_DIR/calibration"

# Default settings
API_PORT=8000
WEB_PORT=5000
API_HOST="0.0.0.0"
WEB_HOST="0.0.0.0"
ENABLE_SECURITY=true
SKIP_CALIBRATION=false
SKIP_WIFI_SETUP=false

# Helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

show_usage() {
    cat << EOF
Two-Scanner Boat Tracking System Startup Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --skip-wifi          Skip WiFi setup (if already configured)
    --skip-calibration   Skip calibration (if already done)
    --no-security        Disable security features (HTTPS, encryption)
    --api-port PORT      API server port (default: 8000)
    --web-port PORT      Web dashboard port (default: 5000)
    --help               Show this help message

WORKFLOW:
    1. WiFi Setup (if not skipped)
    2. System Dependencies Installation
    3. Security Setup (if enabled)
    4. Calibration (if not skipped)
    5. System Startup

EXAMPLES:
    # Full setup with calibration
    $0

    # Skip WiFi setup, do calibration
    $0 --skip-wifi

    # Skip calibration, enable security
    $0 --skip-calibration

    # No security, skip calibration
    $0 --no-security --skip-calibration

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-wifi)
            SKIP_WIFI_SETUP=true
            shift
            ;;
        --skip-calibration)
            SKIP_CALIBRATION=true
            shift
            ;;
        --no-security)
            ENABLE_SECURITY=false
            shift
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
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Change to project directory
cd "$PROJECT_DIR"

log_info "Starting Two-Scanner Boat Tracking System Setup"
log_info "Project directory: $PROJECT_DIR"
log_info "Security enabled: $ENABLE_SECURITY"
log_info "Skip WiFi setup: $SKIP_WIFI_SETUP"
log_info "Skip calibration: $SKIP_CALIBRATION"

# =============================================================================
# STEP 1: WiFi Setup
# =============================================================================
if [[ "$SKIP_WIFI_SETUP" == "false" ]]; then
    log_info "Step 1/5: WiFi Setup"
    
    if [[ -f "wifi_auto_modified.sh" ]]; then
        log_info "Running WiFi setup script..."
        chmod +x wifi_auto_modified.sh
        ./wifi_auto_modified.sh
        log_success "WiFi setup completed"
    else
        log_warning "WiFi setup script not found, skipping..."
    fi
else
    log_info "Step 1/5: WiFi Setup (SKIPPED)"
fi

# =============================================================================
# STEP 2: System Dependencies
# =============================================================================
log_info "Step 2/5: System Dependencies"

# Update package lists
log_info "Updating package lists..."
sudo apt-get update -qq

# Install required system packages
log_info "Installing system dependencies..."
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    bluetooth \
    bluez \
    libbluetooth-dev \
    sqlcipher \
    libsqlcipher-dev \
    openssl \
    curl \
    wget \
    htop \
    vim

# Create virtual environment if it doesn't exist
if [[ ! -d "$VENV_DIR" ]]; then
    log_info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
log_info "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Install Python dependencies
log_info "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

log_success "System dependencies installed"

# =============================================================================
# STEP 3: Security Setup
# =============================================================================
if [[ "$ENABLE_SECURITY" == "true" ]]; then
    log_info "Step 3/5: Security Setup"
    
    if [[ -f "enable_security.sh" ]]; then
        log_info "Running security setup script..."
        chmod +x enable_security.sh
        ./enable_security.sh
        log_success "Security setup completed"
    else
        log_warning "Security setup script not found, skipping..."
    fi
else
    log_info "Step 3/5: Security Setup (DISABLED)"
fi

# =============================================================================
# STEP 4: Calibration
# =============================================================================
if [[ "$SKIP_CALIBRATION" == "false" ]]; then
    log_info "Step 4/5: Calibration Setup"
    
    # Check if calibration directory exists
    if [[ ! -d "$CALIBRATION_DIR" ]]; then
        log_error "Calibration directory not found: $CALIBRATION_DIR"
        exit 1
    fi
    
    # Check if scanner config exists
    if [[ ! -f "$CONFIG_DIR/scanner_config.json" ]]; then
        log_error "Scanner configuration not found: $CONFIG_DIR/scanner_config.json"
        exit 1
    fi
    
    log_info "Calibration setup completed"
    log_warning "IMPORTANT: You must run calibration before starting the system!"
    log_info "To run calibration:"
    log_info "  1. Start the system first: $0 --skip-calibration"
    log_info "  2. Run calibration: python3 calibration/rf_bias_calibration.py --mac YOUR_BEACON_MAC"
    log_info "  3. Restart the system"
else
    log_info "Step 4/5: Calibration (SKIPPED)"
fi

# =============================================================================
# STEP 5: System Startup
# =============================================================================
log_info "Step 5/5: System Startup"

# Cleanup existing processes
log_info "Stopping existing processes..."
sudo pkill -f "boat_tracking_system.py" 2>/dev/null || true
sudo pkill -f "ble_scanner.py" 2>/dev/null || true
sudo pkill -f "scanner_service.py" 2>/dev/null || true
sleep 2

# Free up ports
log_info "Freeing up ports..."
sudo fuser -k "$API_PORT/tcp" 2>/dev/null || true
sudo fuser -k "$WEB_PORT/tcp" 2>/dev/null || true
sleep 1

# Reset BLE adapters
log_info "Resetting BLE adapters..."
sudo systemctl restart bluetooth
sleep 2
sudo hciconfig hci0 down 2>/dev/null || true
sudo hciconfig hci1 down 2>/dev/null || true
sleep 1
sudo hciconfig hci0 up 2>/dev/null || true
sudo hciconfig hci1 up 2>/dev/null || true
sleep 2

# Set environment variables
export PYTHONPATH="$PROJECT_DIR"
export FSM_ENGINE="app.door_lr_engine:DoorLREngine"

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

# Start the system
log_success "Starting Two-Scanner Boat Tracking System..."
log_info "Configuration:"
log_info "  - API Server: http://$LOCAL_IP:$API_PORT"
if [[ "$ENABLE_SECURITY" == "true" ]]; then
    log_info "  - Web Dashboard: https://$LOCAL_IP:$WEB_PORT"
else
    log_info "  - Web Dashboard: http://$LOCAL_IP:$WEB_PORT"
fi
log_info "  - Scanner Config: $CONFIG_DIR/scanner_config.json"
log_info "  - Security: $ENABLE_SECURITY"
log_info ""
log_info "Press Ctrl+C to stop the system"
log_info ""

# Start the appropriate system based on security settings
if [[ "$ENABLE_SECURITY" == "true" ]]; then
    if [[ -f "secure_boat_tracking_system.py" ]]; then
        log_info "Starting secure system..."
        python3 secure_boat_tracking_system.py \
            --secure \
            --api-port "$API_PORT" \
            --web-port "$WEB_PORT" \
            --api-host "$API_HOST" \
            --web-host "$WEB_HOST" \
            --display-mode web
    else
        log_warning "Secure system not found, starting standard system with security..."
        python3 boat_tracking_system.py \
            --api-port "$API_PORT" \
            --web-port "$WEB_PORT" \
            --display-mode web
    fi
else
    log_info "Starting standard system..."
    python3 boat_tracking_system.py \
        --api-port "$API_PORT" \
        --web-port "$WEB_PORT" \
        --display-mode web
fi
