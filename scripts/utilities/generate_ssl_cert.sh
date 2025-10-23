#!/bin/bash
# Generate self-signed SSL certificate for HTTPS

echo "=========================================="
echo "  Generating SSL Certificate for HTTPS"
echo "=========================================="
echo ""

# Create ssl directory
mkdir -p ssl

# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 -nodes \
    -out ssl/cert.pem \
    -keyout ssl/key.pem \
    -days 365 \
    -subj "/C=AU/ST=ACT/L=Canberra/O=Black Mountain Rowing Club/CN=boat-tracking"

echo ""
echo " SSL certificate generated!"
echo "  Certificate: ssl/cert.pem"
echo "  Private key: ssl/key.pem"
echo "  Valid for: 365 days"
echo ""
echo "NOTE: This is a self-signed certificate."
echo "Browsers will show a security warning - click 'Advanced' and 'Proceed'."
echo "This is safe for local network use."
echo ""

