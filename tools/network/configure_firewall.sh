#!/bin/bash

echo "CONFIGURING FIREWALL FOR BOAT TRACKING SYSTEM"
echo "============================================="

# Check if ufw is installed
if command -v ufw &> /dev/null; then
    echo "Configuring UFW firewall..."
    
    # Allow SSH (important!)
    sudo ufw allow ssh
    
    # Allow boat tracking ports
    sudo ufw allow 5000/tcp comment "Boat Tracking Web Dashboard"
    sudo ufw allow 8000/tcp comment "Boat Tracking API Server"
    
    # Enable firewall if not already enabled
    sudo ufw --force enable
    
    echo "Firewall configured successfully!"
    echo "Ports 5000 and 8000 are now open for network access"
else
    echo "UFW not found. Checking iptables..."
    
    # Basic iptables rules (be careful with these)
    echo "Adding iptables rules for ports 5000 and 8000..."
    sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
    sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
    
    echo "iptables rules added (temporary - will be lost on reboot)"
    echo "Consider installing UFW for persistent firewall rules"
fi

echo ""
echo "FIREWALL CONFIGURATION COMPLETE"
echo "==============================="
echo "Your boat tracking system should now be accessible from other devices"
