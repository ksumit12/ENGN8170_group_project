# Network Access Tools

This folder contains tools for making the boat tracking system accessible from other devices on the network.

## Files

- **`get_ip.py`** - Detects Raspberry Pi IP address and displays access URLs
- **`start_network.sh`** - Convenient startup script with network information
- **`configure_firewall.sh`** - Configures firewall to allow access on ports 5000 and 8000

## Quick Start

1. **Get your RPi's IP address:**
   ```bash
   python3 get_ip.py
   ```

2. **Configure firewall (run once):**
   ```bash
   ./configure_firewall.sh
   ```

3. **Start the system for network access:**
   ```bash
   ./start_network.sh
   ```

## Usage

These tools enable:
- Network access to the boat tracking dashboard from any device
- Automatic IP address detection
- Firewall configuration for required ports
- Easy startup with network information display

## Access URLs

After running the tools, access your system from any device on the same network:
- **Main Dashboard:** `http://[RPI_IP]:5000`
- **API Server:** `http://[RPI_IP]:8000`
- **Admin Panel:** `http://[RPI_IP]:5000/admin`

Replace `[RPI_IP]` with your Raspberry Pi's actual IP address.
