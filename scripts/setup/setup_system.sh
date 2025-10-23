#!/bin/bash
# Comprehensive System Setup Script
# Handles initial setup, configuration, and preparation

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
SKIP_WIFI=false
SKIP_CALIBRATION=false

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
        --skip-wifi)
            SKIP_WIFI=true
            shift
            ;;
        --skip-calibration)
            SKIP_CALIBRATION=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --security              Enable security features (HTTPS + encryption)"
            echo "  --emergency             Enable emergency notification system"
            echo "  --skip-wifi             Skip WiFi configuration"
            echo "  --skip-calibration      Skip calibration setup"
            echo "  --help                  Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Basic setup"
            echo "  $0 --security --emergency            # Full setup with all features"
            echo "  $0 --skip-wifi --skip-calibration     # Minimal setup"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

print_header "Boat Tracking System Setup"
echo "Configuration:"
echo "  Security: $ENABLE_SECURITY"
echo "  Emergency Notifications: $ENABLE_EMERGENCY"
echo "  Skip WiFi: $SKIP_WIFI"
echo "  Skip Calibration: $SKIP_CALIBRATION"
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

# Step 1: System Dependencies
print_header "Step 1: Installing System Dependencies"

print_status "Updating package list..."
sudo apt-get update

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
    vim \
    sqlite3 \
    nmap \
    iw \
    wireless-tools

print_status "System dependencies installed"

# Step 2: Python Virtual Environment
print_header "Step 2: Setting Up Python Virtual Environment"

if [ ! -d ".venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv .venv
else
    print_warning "Virtual environment already exists"
fi

print_status "Activating virtual environment..."
source .venv/bin/activate

print_status "Upgrading pip..."
pip install --upgrade pip

print_status "Installing Python requirements..."
pip install -r requirements.txt

print_status "Python environment setup completed"

# Step 3: WiFi Configuration
if [ "$SKIP_WIFI" = false ]; then
    print_header "Step 3: WiFi Network Configuration"
    
    if [ -f "wifi_auto.sh" ]; then
        print_status "Running WiFi setup..."
        chmod +x wifi_auto.sh
        ./wifi_auto.sh
    else
        print_warning "WiFi setup script not found, skipping WiFi configuration"
    fi
else
    print_warning "Skipping WiFi configuration"
fi

# Step 4: Directory Structure
print_header "Step 4: Creating Directory Structure"

directories=(
    "data"
    "logs"
    "logs/emergency"
    "backups"
    "ssl"
    "static/sounds"
    "static/icons"
    "static/images"
    "calibration/latest_plots"
    "scripts/setup"
    "scripts/management"
    "scripts/testing"
    "scripts/utilities"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
    print_status "Created directory: $dir"
done

print_status "Directory structure created"

# Step 5: Configuration Files
print_header "Step 5: Creating Configuration Files"

# Main configuration
config_file="system/json/scanner_config.json"
if [ ! -f "$config_file" ]; then
    print_status "Creating main configuration file..."
    mkdir -p system/json
    
    cat > "$config_file" << EOF
{
  "database_path": "data/boat_tracking.db",
  "api_host": "0.0.0.0",
  "api_port": 8000,
  "web_host": "0.0.0.0",
  "web_port": 5000,
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
    print_status "Main configuration created: $config_file"
else
    print_warning "Main configuration file already exists"
fi

# Environment file
if [ ! -f ".env" ]; then
    print_status "Creating environment file..."
    cat > ".env" << EOF
# Boat Tracking System Environment Configuration

# Database Configuration
DB_PATH=data/boat_tracking.db
DB_ENCRYPTION_KEY=$(openssl rand -base64 32)

# Security Configuration
JWT_SECRET_KEY=$(openssl rand -base64 32)
FLASK_SECRET_KEY=$(openssl rand -base64 32)

# Emergency Notification Configuration
VAPID_PRIVATE_KEY=
VAPID_PUBLIC_KEY=

# System Configuration
CLOSING_TIME=18:00
NOTIFICATION_INTERVAL=60
EOF
    print_status "Environment file created: .env"
else
    print_warning "Environment file already exists"
fi

# Step 6: Security Setup
if [ "$ENABLE_SECURITY" = true ]; then
    print_header "Step 6: Security Setup"
    
    if [ -f "enable_security.sh" ]; then
        print_status "Enabling security features..."
        chmod +x enable_security.sh
        ./enable_security.sh
    else
        print_warning "Security setup script not found"
    fi
fi

# Step 7: Emergency Notification Setup
if [ "$ENABLE_EMERGENCY" = true ]; then
    print_header "Step 7: Emergency Notification Setup"
    
    if [ -f "setup_emergency_system.sh" ]; then
        print_status "Setting up emergency notification system..."
        chmod +x setup_emergency_system.sh
        ./setup_emergency_system.sh
    else
        print_warning "Emergency setup script not found"
    fi
fi

# Step 8: Database Initialization
print_header "Step 8: Database Initialization"

if [ -f "setup_new_system.py" ]; then
    print_status "Initializing database..."
    python3 setup_new_system.py
else
    print_warning "Database setup script not found"
fi

# Step 9: Calibration Setup
if [ "$SKIP_CALIBRATION" = false ]; then
    print_header "Step 9: Calibration Setup"
    
    print_status "Calibration system is ready"
    echo ""
    echo "To complete calibration:"
    echo "1. Place beacons in known positions (CENTER, LEFT, RIGHT)"
    echo "2. Run: python3 calibration/door_lr_calibration.py"
    echo "3. Follow the calibration prompts"
    echo ""
    echo "Calibration files:"
    echo "  - calibration/door_lr_calibration.py"
    echo "  - calibration/rf_bias_calibration.py"
    echo "  - calibration/CALIBRATION_GUIDE.md"
else
    print_warning "Skipping calibration setup"
fi

# Step 10: Service Configuration
print_header "Step 10: Service Configuration"

# Create systemd service
sudo tee /etc/systemd/system/boat-tracking.service > /dev/null << EOF
[Unit]
Description=Boat Tracking System
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=/usr/bin:/usr/local/bin
EnvironmentFile=$(pwd)/.env
ExecStart=$(pwd)/.venv/bin/python3 $(pwd)/boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

print_status "System service created"

# Step 11: Permissions
print_header "Step 11: Setting Permissions"

# Make scripts executable
chmod +x start_system.sh
chmod +x scripts/management/manage_system.sh
chmod +x scripts/testing/test_system.sh

# Set directory permissions
chmod 755 data logs backups ssl
chmod 644 .env

print_status "Permissions set"

# Step 12: Final Verification
print_header "Step 12: Final Verification"

print_status "Verifying installation..."

# Check virtual environment
if [ -d ".venv" ]; then
    print_status "✓ Virtual environment exists"
else
    print_error "✗ Virtual environment missing"
fi

# Check configuration
if [ -f "$config_file" ]; then
    print_status "✓ Configuration file exists"
else
    print_error "✗ Configuration file missing"
fi

# Check database
if [ -f "data/boat_tracking.db" ]; then
    print_status "✓ Database initialized"
else
    print_warning "⚠ Database not initialized"
fi

# Check Python packages
if source .venv/bin/activate && python -c "import flask" 2>/dev/null; then
    print_status "✓ Python packages installed"
else
    print_error "✗ Python packages missing"
fi

print_header "Setup Complete"
echo ""
echo "Boat Tracking System setup completed successfully!"
echo ""
echo "Next Steps:"
echo "1. Complete calibration (if not skipped):"
echo "   python3 calibration/door_lr_calibration.py"
echo ""
echo "2. Start the system:"
echo "   ./start_system.sh"
echo ""
echo "3. Or use the management script:"
echo "   ./scripts/management/manage_system.sh start"
echo ""
echo "4. Test the system:"
echo "   ./scripts/testing/test_system.sh"
echo ""
echo "Configuration:"
echo "  Security: $ENABLE_SECURITY"
echo "  Emergency Notifications: $ENABLE_EMERGENCY"
echo "  WiFi Setup: $([ "$SKIP_WIFI" = false ] && echo "Completed" || echo "Skipped")"
echo "  Calibration: $([ "$SKIP_CALIBRATION" = false ] && echo "Ready" || echo "Skipped")"
echo ""
print_status "Setup completed successfully!"
