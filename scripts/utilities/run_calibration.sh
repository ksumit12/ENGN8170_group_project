#!/bin/bash
# Calibration Helper Script for Two-Scanner System
# Guides users through the calibration process

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
CALIBRATION_DIR="$PROJECT_DIR/calibration"

# Helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

show_usage() {
    cat << EOF
Two-Scanner Calibration Helper Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --mac MAC_ADDRESS    Beacon MAC address (required)
    --duration SECONDS   Duration for each position (default: 10)
    --quick              Quick calibration (single height)
    --test-live          Test live movement detection
    --help               Show this help message

EXAMPLES:
    # Full calibration with height testing
    $0 --mac AA:BB:CC:DD:EE:FF

    # Quick calibration (single height)
    $0 --mac AA:BB:CC:DD:EE:FF --quick

    # Test live movement detection
    $0 --mac AA:BB:CC:DD:EE:FF --test-live

EOF
}

# Parse command line arguments
MAC_ADDRESS=""
DURATION=10
QUICK_MODE=false
TEST_LIVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --mac)
            MAC_ADDRESS="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --test-live)
            TEST_LIVE=true
            shift
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

# Validate MAC address
if [[ -z "$MAC_ADDRESS" ]]; then
    log_error "MAC address is required. Use --mac option."
    show_usage
    exit 1
fi

# Change to project directory
cd "$PROJECT_DIR"

log_info "Two-Scanner Calibration Helper"
log_info "Beacon MAC: $MAC_ADDRESS"
log_info "Duration: $DURATION seconds"
log_info "Quick mode: $QUICK_MODE"
log_info "Test live: $TEST_LIVE"

# Check if system is running
log_info "Checking if system is running..."
if pgrep -f "boat_tracking_system.py" > /dev/null; then
    log_success "System is running"
else
    log_error "System is not running. Please start the system first:"
    log_info "  ./start_two_scanner_system.sh --skip-calibration"
    exit 1
fi

# Check if calibration directory exists
if [[ ! -d "$CALIBRATION_DIR" ]]; then
    log_error "Calibration directory not found: $CALIBRATION_DIR"
    exit 1
fi

# Activate virtual environment
if [[ -d ".venv" ]]; then
    source .venv/bin/activate
    log_info "Virtual environment activated"
fi

# Set Python path
export PYTHONPATH="$PROJECT_DIR"

# Run calibration based on mode
if [[ "$TEST_LIVE" == "true" ]]; then
    log_info "Running live movement test..."
    log_warning "Make sure you have completed calibration first!"
    log_info "Press Enter to continue..."
    read -r
    
    python3 "$CALIBRATION_DIR/door_lr_calibration.py" \
        --mac "$MAC_ADDRESS" \
        --test-live
    
elif [[ "$QUICK_MODE" == "true" ]]; then
    log_info "Running quick calibration (single height)..."
    log_info "This will test CENTER, LEFT, and RIGHT positions at chest height only."
    log_info "Press Enter to continue..."
    read -r
    
    python3 "$CALIBRATION_DIR/door_lr_calibration.py" \
        --mac "$MAC_ADDRESS" \
        --duration "$DURATION" \
        --no-heights
    
else
    log_info "Running full calibration with height testing..."
    log_info "This will test CENTER, LEFT, and RIGHT positions at 3 heights each."
    log_info "Total time: ~3-4 minutes"
    log_info ""
    log_info "Heights tested:"
    log_info "  - GROUND: Lowest surface (floor/ground)"
    log_info "  - CHEST: Normal carrying height"
    log_info "  - OVERHEAD: Arms fully extended up"
    log_info ""
    log_info "Press Enter to continue..."
    read -r
    
    python3 "$CALIBRATION_DIR/door_lr_calibration.py" \
        --mac "$MAC_ADDRESS" \
        --duration "$DURATION"
fi

log_success "Calibration completed!"
log_info ""
log_info "Next steps:"
log_info "1. Review the calibration results"
log_info "2. If calibration looks good, restart the system:"
log_info "   ./start_two_scanner_system.sh --skip-calibration"
log_info "3. Test the system with real boat movements"
log_info ""
log_info "Calibration files saved to:"
log_info "  - $CALIBRATION_DIR/sessions/latest/"
log_info "  - $CALIBRATION_DIR/sessions/TIMESTAMP/"
