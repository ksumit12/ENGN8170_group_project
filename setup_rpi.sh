#!/bin/bash
# Complete RPi Setup Script for Boat Tracking System
# Run this once on a fresh RPi and you're done!

set -e  # Exit on any error

echo "Boat Tracking System - Complete RPi Setup"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Don't run as root! Run as regular user with sudo access."
    exit 1
fi

# Check if we're on a Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    print_warning "This script is designed for Raspberry Pi. Continue anyway? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

print_status "Starting complete setup..."

# Step 1: Update system
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Step 2: Install required system packages
print_status "Installing system dependencies..."
sudo apt install -y python3 python3-pip python3-venv git curl wget hciconfig bluetooth bluez

# Step 3: Install ngrok
print_status "Installing ngrok..."
if ! command -v ngrok &> /dev/null; then
    curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
    sudo apt update
    sudo apt install -y ngrok
    print_success "ngrok installed successfully"
else
    print_success "ngrok already installed"
fi

# Step 4: Create Python virtual environment
print_status "Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate

# Step 5: Install Python dependencies
print_status "Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Step 6: Set up ngrok configuration
print_status "Setting up ngrok configuration..."

# Check if ngrok.yml exists and has auth token
if [ ! -f "ngrok.yml" ] || grep -q "YOUR_NGROK_AUTH_TOKEN_HERE" ngrok.yml; then
    print_warning "ngrok auth token not configured!"
    echo ""
    echo "To get your ngrok auth token:"
    echo "1. Go to: https://dashboard.ngrok.com/get-started/your-authtoken"
    echo "2. Sign up/login and copy your auth token"
    echo "3. Run this command:"
    echo "   ngrok config add-authtoken YOUR_TOKEN_HERE"
    echo ""
    echo "After adding your token, run this script again."
    exit 1
fi

# Step 7: Set up Bluetooth adapters
print_status "Configuring Bluetooth adapters..."

# Enable Bluetooth service
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Unblock Bluetooth if needed
sudo rfkill unblock bluetooth

# Bring up adapters
sudo hciconfig hci0 up 2>/dev/null || true
sudo hciconfig hci1 up 2>/dev/null || true

print_success "Bluetooth adapters configured"

# Step 8: Create systemd service for auto-start
print_status "Creating systemd service for auto-start..."

# Get current user and directory
CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)

# Create systemd service file
sudo tee /etc/systemd/system/boat-tracking.service > /dev/null <<EOF
[Unit]
Description=Boat Tracking System
After=network.target bluetooth.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/.venv/bin
ExecStart=$CURRENT_DIR/.venv/bin/python $CURRENT_DIR/boat_tracking_system.py --api-port 8000 --web-port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create ngrok service
sudo tee /etc/systemd/system/boat-tracking-ngrok.service > /dev/null <<EOF
[Unit]
Description=Boat Tracking System - ngrok Tunnel
After=boat-tracking.service
Requires=boat-tracking.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=/usr/bin/ngrok start boat-tracking --config $CURRENT_DIR/ngrok.yml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable services
sudo systemctl daemon-reload
sudo systemctl enable boat-tracking.service
sudo systemctl enable boat-tracking-ngrok.service

print_success "Systemd services created and enabled"

# Step 9: Create startup script
print_status "Creating startup script..."

cat > start_system.sh <<'EOF'
#!/bin/bash
# Start Boat Tracking System with ngrok

echo "Starting Boat Tracking System..."

# Start the main service
sudo systemctl start boat-tracking.service

# Wait a moment for it to start
sleep 5

# Start ngrok tunnel
sudo systemctl start boat-tracking-ngrok.service

echo "System started!"
echo "Check your public URL at: https://dashboard.ngrok.com/tunnels"
echo "Local access: http://localhost:5000"
echo "ngrok dashboard: http://localhost:4040"
echo ""
echo "To stop: sudo systemctl stop boat-tracking-ngrok.service boat-tracking.service"
EOF

chmod +x start_system.sh

# Step 10: Create status script
cat > check_status.sh <<'EOF'
#!/bin/bash
# Check system status

echo "Boat Tracking System Status"
echo "=============================="

echo "Main Service:"
sudo systemctl status boat-tracking.service --no-pager -l

echo ""
echo "ngrok Service:"
sudo systemctl status boat-tracking-ngrok.service --no-pager -l

echo ""
echo "Active Tunnels:"
curl -s http://localhost:4040/api/tunnels | python3 -m json.tool 2>/dev/null || echo "ngrok dashboard not accessible"
EOF

chmod +x check_status.sh

# Step 11: Final setup
print_status "Finalizing setup..."

# Create logs directory
mkdir -p logs

# Set proper permissions
chmod +x start_public.sh
chmod +x start_system.sh
chmod +x check_status.sh

print_success "Setup complete! "
echo ""
echo "=============================================="
echo "READY TO USE!"
echo "=============================================="
echo ""
echo "To start the system:"
echo " ./start_system.sh"
echo ""
echo "To check status:"
echo " ./check_status.sh"
echo ""
echo "To stop the system:"
echo " sudo systemctl stop boat-tracking-ngrok.service boat-tracking.service"
echo ""
echo "Your system will auto-start on boot!"
echo "Check your public URL at: https://dashboard.ngrok.com/tunnels"
echo ""
print_warning "Make sure your ngrok auth token is configured in ngrok.yml"
