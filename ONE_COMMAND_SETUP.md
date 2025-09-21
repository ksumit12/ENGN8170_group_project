#  ONE COMMAND SETUP

## For Fresh Raspberry Pi:

```bash
# 1. Clone the repo
git clone https://github.com/ksumit12/ENGN8170_group_project.git
cd ENGN8170_group_project

# 2. Get ngrok auth token (one-time setup)
# Go to: https://dashboard.ngrok.com/get-started/your-authtoken
# Copy your token, then run:
ngrok config add-authtoken YOUR_TOKEN_HERE

# 3. Reserve your static domain (one-time setup)
# Go to: https://dashboard.ngrok.com/cloud-edge/domains
# Reserve: boat-tracking.ngrok.io

# 4. Run the complete setup (this does EVERYTHING)
chmod +x setup_rpi.sh
./setup_rpi.sh

# 5. Start the system
./start_system.sh
```

## That's it! Your static URL will be:
**https://boat-tracking.ngrok.io**

This URL **NEVER CHANGES** - you can share it with everyone!

## What the setup script does:
-  Updates system packages
-  Installs Python, ngrok, Bluetooth tools
-  Creates virtual environment
-  Installs all dependencies
-  Configures Bluetooth adapters
-  Creates systemd services (auto-start on boot)
-  Sets up static ngrok domain
-  Creates management scripts

## After setup, you can:
- **Start**: `./start_system.sh`
- **Stop**: `sudo systemctl stop boat-tracking-ngrok.service boat-tracking.service`
- **Status**: `./check_status.sh`
- **Auto-start**: System starts automatically on boot!

## Your static domain:
- **Public URL**: `https://boat-tracking-ksumit12.ngrok.io` (NEVER CHANGES!)
- **Local access**: `http://localhost:5000`
- **ngrok dashboard**: `http://localhost:4040`
