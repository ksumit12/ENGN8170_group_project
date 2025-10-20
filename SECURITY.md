# Security Setup Guide

## Quick Setup (1 Command)

Enable HTTPS + encryption in one step:

```bash
./enable_security.sh
```

That's it! The system will now use:
- ✅ **HTTPS** for secure web dashboard access
- ✅ **Database encryption** (basic protection)

---

## What Gets Enabled

### 1. HTTPS (Encrypted Web Traffic)

**Before:**
- URL: `http://192.168.1.100:5000` (unencrypted)
- ⚠️ Data visible on network

**After:**
- URL: `https://192.168.1.100:5000` (encrypted)
- ✅ All web traffic encrypted with SSL/TLS

**Browser Warning:** You'll see a security warning because the certificate is self-signed. This is **normal and safe** for local network use. Click "Advanced" → "Proceed" to continue.

---

### 2. Database Encryption

**Before:**
- Database file: `data/boat_tracking.db` (readable by anyone)
- ⚠️ Anyone with file access can read data

**After:**
- Database file: Encrypted with password key
- ✅ Requires encryption key to access data
- Key stored in `.env` file (keep this secure!)

---

## Manual Setup (If Needed)

### Generate SSL Certificate

```bash
./generate_ssl_cert.sh
```

This creates:
- `ssl/cert.pem` - SSL certificate
- `ssl/key.pem` - Private key

Valid for 365 days.

### Set Encryption Key

Create `.env` file:

```bash
echo "DB_ENCRYPTION_KEY=your_secure_password_here" > .env
```

**Important:** Keep this key secure! Without it, you cannot access the database.

---

## Upgrading to Stronger Encryption (Optional)

For production use with sensitive data, install SQLCipher:

```bash
# Install SQLCipher system library
sudo apt-get install sqlcipher libsqlcipher-dev

# Install Python bindings
source .venv/bin/activate
pip install sqlcipher3
```

The system will automatically use SQLCipher if installed (no code changes needed).

---

## Security Checklist

- ✅ HTTPS enabled (`ssl/cert.pem` exists)
- ✅ Database encryption key set (`.env` file)
- ✅ `.env` file excluded from git (in `.gitignore`)
- ✅ Admin password changed from default
- ✅ Firewall configured (only ports 5000/8000 open)

---

## Troubleshooting

### Browser Shows "Connection Not Secure"

**This is normal!** Self-signed certificates always trigger this warning.

**To proceed:**
1. Click "Advanced" or "Show Details"
2. Click "Proceed to site" or "Accept Risk"
3. Add exception if prompted

**Why?** Your certificate isn't signed by a trusted authority (like Let's Encrypt). For local network use, this is perfectly safe.

### Can't Access Database After Enabling Encryption

**Problem:** Wrong encryption key or key changed.

**Solution:**
1. Check `.env` file has correct `DB_ENCRYPTION_KEY`
2. If key lost, you'll need to reset database (data loss!)
3. Always backup `.env` file securely

### HTTPS Not Working

**Check:**
```bash
ls -la ssl/
# Should show cert.pem and key.pem
```

**Fix:**
```bash
./generate_ssl_cert.sh
```

---

## Best Practices

### For Local Network Use (Current Setup)
- ✅ Self-signed certificate is fine
- ✅ Basic encryption sufficient
- ✅ Change admin password
- ✅ Restrict network access (firewall)

### For Internet-Accessible Deployment
- ⚠️ Use proper certificate (Let's Encrypt)
- ⚠️ Install SQLCipher for stronger encryption
- ⚠️ Add proper user authentication
- ⚠️ Enable audit logging
- ⚠️ Regular security updates

---

## Security Features Summary

| Feature | Status | Strength |
|---------|--------|----------|
| HTTPS/TLS | ✅ Enabled | Self-signed cert (local network) |
| Database Encryption | ✅ Enabled | Basic (upgradeable to SQLCipher) |
| Admin Authentication | ✅ Password protected | Hardcoded (changeable) |
| API Access Control | ⚠️ Open on LAN | Firewall recommended |
| Audit Logging | ✅ All admin actions | Stored in logs/ |
| No Personal Data | ✅ Privacy by design | Only boat/beacon IDs |

---

## Update SSL Certificate (Yearly)

Certificate expires after 365 days. Renew:

```bash
rm -rf ssl/
./generate_ssl_cert.sh
```

---

## Questions?

- **Q: Is this secure enough?**  
  A: Yes, for local network use in a rowing club. Data encrypted in transit (HTTPS) and at rest (database encryption).

- **Q: Can hackers access my data?**  
  A: On local network with firewall: Very unlikely. On internet without proper setup: Possible. Use firewall!

- **Q: Do I need to do anything after running `enable_security.sh`?**  
  A: Nope! Just start the system normally with `./start_single_scanner_demo.sh`

---

*Security setup takes < 1 minute and protects your boat tracking data!*

