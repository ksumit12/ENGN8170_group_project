# Fixed System Deployment Guide

## Overview

This guide covers the deployment of the **fixed** boat tracking system with improved reliability, error handling, and simplified operation. The fixes address the major issues that prevented successful deployment at the Red Shed.

## Key Fixes Applied

### 1. Direction Detection Algorithm
- **Fixed**: Updated parameters for real-world metal environment
- **Before**: Too sensitive thresholds (-90 dBm, 0.05s timing)
- **After**: Robust thresholds (-75 dBm, 0.5s timing) with longer analysis windows

### 2. Scanner Configuration Standardization
- **Fixed**: Consistent adapter assignments across all config files
- **Before**: Conflicting hci0/hci1 mappings
- **After**: Standardized hci0=left, hci1=right with updated thresholds

### 3. Error Handling and Recovery
- **Fixed**: Added comprehensive try-catch blocks and retry mechanisms
- **Before**: System crashes on single errors
- **After**: Graceful degradation with automatic recovery

### 4. Database Robustness
- **Fixed**: WAL mode, retry logic, and corruption recovery
- **Before**: Database locks and corruption during power outages
- **After**: Resilient database with automatic backups and recovery

### 5. Simplified Calibration
- **Fixed**: Created user-friendly calibration script
- **Before**: Complex multi-step calibration process
- **After**: Simple guided calibration with clear instructions

### 6. System Monitoring
- **Fixed**: Added comprehensive health monitoring
- **Before**: No visibility into system issues
- **After**: Real-time health monitoring and diagnostics

## Hardware Requirements

### Minimum Requirements
- Raspberry Pi 4 (2GB RAM minimum)
- 2x TP-Link UB500 BLE adapters
- 2x 2-meter USB extension cables
- microSD card (32GB+, Class 10)
- Stable power supply (5V, 3A)
- WiFi/Ethernet connectivity

### Optional Components
- HDMI monitor for local display
- DFRobot buzzer for audio alerts
- Protective enclosure

## Software Installation

### Step 1: System Setup
```bash
# Clone the repository
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project

# Switch to the fixed branch
git checkout door-lr-v2

# Run comprehensive setup
./scripts/setup/setup_system.sh --security --emergency
```

### Step 2: Hardware Configuration
```bash
# Check BLE adapters
python3 scripts/utilities/system_health_monitor.py

# Verify scanner detection
python3 tools/ble_testing/identify_ble_dongles.py
```

### Step 3: Calibration
```bash
# Run simplified calibration
python3 scripts/utilities/simple_calibration.py --beacon-mac YOUR_BEACON_MAC --duration 30 --runs 3
```

### Step 4: Start System
```bash
# Start with monitoring
./start_system.sh --security --emergency --display-mode both

# Or use management script
./scripts/management/manage_system.sh start
```

## Physical Installation

### Scanner Placement
1. **Left Scanner (hci0)**:
   - Mount on left side of door (viewed from inside shed)
   - Height: 1-2 meters (match beacon height)
   - Distance: 0.5-1 meter from doorway centerline
   - Clear line of sight through doorway

2. **Right Scanner (hci1)**:
   - Mount on right side of door (viewed from inside shed)
   - Same height and distance as left scanner
   - Ensure symmetric positioning

### USB Extension Setup
1. Connect each BLE adapter to 2-meter USB extension cable
2. Connect extension cables to Raspberry Pi USB ports
3. Secure cables to prevent movement and interference
4. Test connections before final mounting

### Power and Network
1. Ensure stable power supply with UPS if possible
2. Verify WiFi signal strength at scanner locations
3. Consider Ethernet connection for reliability
4. Install surge protection

## Configuration Files

### Scanner Configuration
The system now uses standardized configuration files:

- `system/json/scanner_config.json` - Main configuration
- `system/json/scanner_config.door_left_right.json` - Alternative configuration

Both files now have consistent settings:
- hci0 = left scanner
- hci1 = right scanner
- Updated thresholds: -70 dBm enter, -75 dBm exit
- Increased hold time: 2000ms

### Database Configuration
- Automatic WAL mode for better concurrency
- Daily backups in `data/backups/`
- Retry logic for database operations
- Corruption recovery mechanisms

## Monitoring and Maintenance

### Health Monitoring
```bash
# Check system health
python3 scripts/utilities/system_health_monitor.py

# Continuous monitoring
python3 scripts/utilities/system_health_monitor.py --watch --interval 60

# Save health report
python3 scripts/utilities/system_health_monitor.py --output logs/health_report.json
```

### Log Monitoring
```bash
# View system logs
tail -f logs/system.log

# Check scanner logs
tail -f logs/scanner.log

# Monitor database activity
tail -f logs/database.log
```

### Maintenance Tasks
1. **Daily**: Check health monitor output
2. **Weekly**: Review error logs and performance
3. **Monthly**: Run full system test and calibration check
4. **Quarterly**: Update system and review configuration

## Troubleshooting

### Common Issues and Solutions

#### 1. Scanner Not Detecting Beacons
**Symptoms**: No beacon detections in logs
**Solutions**:
- Check adapter connections: `hciconfig`
- Verify beacon is transmitting: `hcitool lescan`
- Adjust RSSI thresholds in configuration
- Run health monitor for diagnostics

#### 2. Wrong Direction Detection
**Symptoms**: ENTER/LEAVE events in wrong direction
**Solutions**:
- Verify scanner physical placement
- Check adapter assignments in config
- Re-run calibration with correct positioning
- Review movement patterns in logs

#### 3. Database Errors
**Symptoms**: Database locked or corruption errors
**Solutions**:
- Check disk space: `df -h`
- Restart system to clear locks
- Restore from backup if needed
- Check health monitor for resource issues

#### 4. System Performance Issues
**Symptoms**: Slow response or high CPU usage
**Solutions**:
- Check system resources: `htop`
- Review log file sizes
- Restart services
- Consider hardware upgrade

### Emergency Procedures

#### System Recovery
```bash
# Stop all services
./scripts/management/manage_system.sh stop

# Check system health
python3 scripts/utilities/system_health_monitor.py

# Restore from backup if needed
cp data/backups/boat_tracking_YYYYMMDD.sqlite data/boat_tracking.db

# Restart system
./scripts/management/manage_system.sh start
```

#### Manual Override
If automatic detection fails:
1. Use web dashboard to manually update boat status
2. Check scanner connectivity and positioning
3. Run calibration to retune parameters
4. Contact support if issues persist

## Performance Expectations

### Detection Accuracy
- **Target**: >90% correct direction detection
- **Current**: Improved from 16.7% to expected 85%+ with fixes
- **Factors**: Beacon quality, environmental conditions, calibration accuracy

### System Reliability
- **Uptime**: >99% with proper power and network
- **Recovery**: Automatic recovery from most errors
- **Maintenance**: Minimal intervention required

### Response Time
- **Detection**: <2 seconds from beacon detection to status update
- **Dashboard**: <1 second for real-time updates
- **API**: <500ms response time for most requests

## Support and Documentation

### Log Files
- `logs/system.log` - Main system events
- `logs/scanner.log` - BLE scanner activity
- `logs/database.log` - Database operations
- `logs/health.log` - Health monitoring data

### Configuration Files
- `system/json/scanner_config.json` - Scanner settings
- `system/json/settings.json` - System settings
- `calibration/sessions/latest/door_lr_calib.json` - Calibration data

### Scripts and Utilities
- `scripts/utilities/simple_calibration.py` - Easy calibration
- `scripts/utilities/system_health_monitor.py` - Health monitoring
- `scripts/management/manage_system.sh` - System management
- `scripts/testing/test_system.sh` - System testing

## Conclusion

The fixed system addresses the major deployment issues through:
- Robust direction detection with realistic parameters
- Standardized configuration and error handling
- Simplified calibration and monitoring tools
- Improved database reliability and recovery
- Comprehensive health monitoring and diagnostics

These fixes should enable successful deployment at the Red Shed with minimal maintenance requirements and reliable operation in the challenging metal environment.
