# Scripts Directory

This directory contains all the scripts for the Boat Tracking System, organized by function.

## Directory Structure

### `setup/`
Contains setup and installation scripts:
- `setup_system.sh` - Comprehensive system setup script

### `management/`
Contains system management scripts:
- `manage_system.sh` - Start, stop, restart, status, logs, maintenance

### `testing/`
Contains testing and validation scripts:
- `test_system.sh` - Comprehensive system testing suite

### `utilities/`
Contains utility scripts and legacy scripts:
- `run_full_tests.py` - Legacy test runner
- `setup_new_system.py` - Database initialization
- `start_two_scanner_system.sh` - Legacy startup script
- `start_with_simulator.sh` - Simulator startup
- `stop_scanner.sh` - Scanner stop script
- `test_setup.sh` - Setup testing
- `setup_emergency_system.sh` - Emergency system setup
- `setup_emergency_notifications.sh` - Legacy emergency setup
- `setup_wifi_emergency_notifications.sh` - Legacy WiFi emergency setup

## Quick Start

### 1. Initial Setup
```bash
./scripts/setup/setup_system.sh --security --emergency
```

### 2. Start System
```bash
./start_system.sh --security --emergency
```

### 3. Manage System
```bash
./scripts/management/manage_system.sh start
./scripts/management/manage_system.sh status
./scripts/management/manage_system.sh logs
```

### 4. Test System
```bash
./scripts/testing/test_system.sh all
```

## Main Scripts

### `start_system.sh` (Root Directory)
The main startup script that handles everything:
- WiFi setup
- Dependencies installation
- Security configuration
- Emergency notification setup
- Database initialization
- Calibration guidance
- System launch

### `scripts/management/manage_system.sh`
System management operations:
- `start` - Start the system
- `stop` - Stop the system
- `restart` - Restart the system
- `status` - Show system status
- `logs [TYPE]` - Show logs (system, boat, emergency)
- `test` - Test system functionality
- `maintenance [TASK]` - Run maintenance tasks
- `update` - Update system

### `scripts/testing/test_system.sh`
Comprehensive testing suite:
- `environment` - Test Python environment and dependencies
- `hardware` - Test BLE hardware and network
- `software` - Test database, config, and API
- `features` - Test emergency notifications and security
- `integration` - Test system integration and performance
- `all` - Run all tests

## Script Organization

The scripts are organized to reduce clutter in the root directory:

- **Root Directory**: Only essential scripts (`start_system.sh`)
- **Setup Scripts**: Installation and configuration
- **Management Scripts**: Day-to-day operations
- **Testing Scripts**: Validation and testing
- **Utilities**: Legacy scripts and specialized tools

This organization makes the system easier to use and maintain.
