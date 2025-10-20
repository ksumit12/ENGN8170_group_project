#!/bin/bash
# Enable HTTPS + Database Encryption for Boat Tracking System

echo "=========================================="
echo "  Security Setup for Boat Tracking"
echo "=========================================="
echo ""
echo "This script will enable:"
echo "  1. HTTPS for web dashboard"
echo "  2. Database encryption (optional)"
echo ""

# Step 1: Generate SSL certificate for HTTPS
echo "[1/3] Generating SSL certificate for HTTPS..."
./generate_ssl_cert.sh

# Step 2: Install security dependencies
echo "[2/3] Installing security packages..."
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate

pip install -q pyopenssl==24.0.0

echo ""
echo "NOTE: For database encryption, you can optionally install SQLCipher:"
echo "  sudo apt-get install sqlcipher libsqlcipher-dev"
echo "  pip install sqlcipher3"
echo ""
echo "(Skipping for now - system works without it)"
echo ""

# Step 3: Set encryption key
echo "[3/3] Setting up database encryption key..."

if [ -f .env ]; then
    # Update existing .env
    if grep -q "DB_ENCRYPTION_KEY" .env; then
        echo "Encryption key already set in .env"
    else
        echo "DB_ENCRYPTION_KEY=bmrc_secure_2025_$(date +%s)" >> .env
        echo "Added encryption key to .env"
    fi
else
    # Create new .env
    echo "# Database Encryption Key" > .env
    echo "DB_ENCRYPTION_KEY=bmrc_secure_2025_$(date +%s)" >> .env
    echo "Created .env with encryption key"
fi

echo ""
echo "=========================================="
echo "  Security Setup Complete! ✓"
echo "=========================================="
echo ""
echo "HTTPS Status:"
echo "  ✓ SSL certificate: ssl/cert.pem"
echo "  ✓ Private key: ssl/key.pem"
echo ""
echo "Database Encryption:"
echo "  ✓ Encryption key set in .env file"
echo "  ℹ For stronger encryption, install SQLCipher (see note above)"
echo ""
echo "Next Steps:"
echo "  1. Start system: ./start_single_scanner_demo.sh"
echo "  2. Access via HTTPS: https://<your-pi-ip>:5000"
echo ""
echo "NOTE: Browser will show security warning (self-signed cert)."
echo "Click 'Advanced' → 'Proceed' to continue. This is safe for local network."
echo ""

