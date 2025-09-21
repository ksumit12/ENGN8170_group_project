# Public Deployment Guide

## Quick Start

1. **Get ngrok auth token**:
   - Go to https://dashboard.ngrok.com/get-started/your-authtoken
   - Copy your auth token

2. **Configure ngrok**:
   - Edit `ngrok.yml`
   - Replace `YOUR_NGROK_AUTH_TOKEN_HERE` with your actual token

3. **Start the system**:
   ```bash
   ./start_public.sh
   ```

## Domain Options

### **Free Options:**
- **ngrok free tier**: Random subdomain (changes on restart)
- **ngrok paid tier**: Custom subdomain like `boat-tracking-ksumit12.ngrok.io`

### **Custom Domain Options:**
1. **ngrok Pro** ($8/month):
   - Custom domain: `boat-tracking.yourdomain.com`
   - Static URL that never changes
   - Professional setup

2. **Cloudflare Tunnel** (Free):
   - Use your own domain
   - More control over routing
   - Free SSL certificates

3. **Port forwarding + Dynamic DNS**:
   - Configure router port forwarding
   - Use No-IP or DuckDNS for dynamic DNS
   - Free but requires router access

## Current Setup

- **Public URL**: `https://2796006bc3c4.ngrok-free.app`
- **Local access**: `http://localhost:5000`
- **ngrok dashboard**: `http://localhost:4040`

## Troubleshooting

- **URL changes**: Restart ngrok (free tier limitation)
- **Connection issues**: Check if boat tracking system is running
- **Auth token error**: Verify token in ngrok.yml

## Security Notes

- ngrok.yml contains sensitive auth token - never commit to git
- Use HTTPS URLs only for production
- Consider rate limiting for public access
