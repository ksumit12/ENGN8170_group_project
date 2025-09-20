# Utility Scripts

This folder contains utility scripts for managing the boat tracking system.

## Files

- **`kill_all_servers.sh`** - Kills all boat tracking related processes and frees up ports
- **`kill_boat_servers.sh`** - Safer version that only kills boat tracking processes

## Usage

### Kill All Servers (Comprehensive)
```bash
./kill_all_servers.sh
```
This script:
- Kills all boat tracking processes
- Frees up ports 5000, 8000, 8001, 8002
- Cleans up zombie processes
- Shows remaining processes

### Kill Boat Servers Only (Safer)
```bash
./kill_boat_servers.sh
```
This script:
- Only kills boat tracking specific processes
- Safer for shared systems
- Less aggressive cleanup

## When to Use

Use these scripts when:
- Ports are already in use
- System becomes unresponsive
- Need to restart the boat tracking system
- Switching between different configurations

## Safety

- `kill_boat_servers.sh` is safer and only targets boat tracking processes
- `kill_all_servers.sh` is more comprehensive but may affect other services
- Always check what processes are running before using these scripts
