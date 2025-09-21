# Vercel Deployment Guide

This guide explains how to deploy the Boat Tracking System to Vercel for web access.

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **Vercel CLI**: Install with `npm i -g vercel`
3. **GitHub Repository**: Your code should be in a GitHub repository

## Deployment Steps

### 1. Install Vercel CLI
```bash
npm install -g vercel
```

### 2. Login to Vercel
```bash
vercel login
```

### 3. Deploy from Project Directory
```bash
cd /path/to/your/grp_project
vercel
```

Follow the prompts:
- Set up and deploy? **Yes**
- Which scope? **Your account**
- Link to existing project? **No** (for first deployment)
- What's your project's name? **boat-tracking-system** (or your preferred name)
- In which directory is your code located? **./** (current directory)

### 4. Automatic GitHub Integration

After the first deployment, Vercel will:
- Create a GitHub integration
- Deploy automatically on every push to main branch
- Provide a live URL (e.g., `https://boat-tracking-system.vercel.app`)

## File Structure for Vercel

```
grp_project/
├── api/
│   └── index.py          # Main Flask app for Vercel
├── vercel.json           # Vercel configuration
├── requirements.txt      # Python dependencies
├── .vercelignore        # Files to ignore
├── database_models.py   # Database models
├── logging_config.py    # Logging configuration
└── admin_service.py     # Admin services
```

## Important Notes

### What Works on Vercel
- ✅ Web dashboard interface
- ✅ API endpoints for boats, beacons, presence
- ✅ Database operations (SQLite)
- ✅ Log viewing
- ✅ Real-time updates via JavaScript

### What Doesn't Work on Vercel
- ❌ BLE scanning (requires physical hardware)
- ❌ Long-running background processes
- ❌ Real-time beacon detection

### Database Considerations
- SQLite database is stored in Vercel's serverless environment
- Data persists during function execution but may reset between deployments
- For production, consider using a cloud database (PostgreSQL, MongoDB, etc.)

## Local Development vs Production

### Local Development
- Run `python3 boat_tracking_system.py` for full functionality
- Includes BLE scanning and real-time detection
- Uses local SQLite database

### Production (Vercel)
- Web interface only
- No BLE scanning
- Database may reset between deployments
- Perfect for monitoring and management

## Updating the Deployment

1. **Make changes** to your code
2. **Commit and push** to GitHub:
   ```bash
   git add .
   git commit -m "Update boat tracking system"
   git push origin main
   ```
3. **Vercel automatically deploys** the changes
4. **Visit your Vercel URL** to see updates

## Custom Domain (Optional)

1. Go to your Vercel dashboard
2. Select your project
3. Go to Settings > Domains
4. Add your custom domain
5. Follow DNS configuration instructions

## Troubleshooting

### Common Issues

1. **Import Errors**: Make sure all Python files are in the root directory
2. **Database Errors**: Check that database_models.py is accessible
3. **Function Timeout**: Vercel has a 30-second timeout limit
4. **Missing Dependencies**: Check requirements.txt includes all needed packages

### Debugging

1. **Check Vercel Logs**: Go to your project dashboard > Functions tab
2. **Test Locally**: Run `vercel dev` to test locally
3. **Check Build Logs**: Look at deployment logs for errors

## Environment Variables

If you need environment variables:

1. Go to Vercel dashboard > Project Settings > Environment Variables
2. Add variables like:
   - `DATABASE_URL` (for cloud database)
   - `API_KEY` (for external services)
   - `DEBUG` (for development)

## Next Steps

1. **Deploy to Vercel** using the steps above
2. **Test the web interface** at your Vercel URL
3. **Set up monitoring** for the production site
4. **Consider adding** a cloud database for persistent data
5. **Add authentication** if needed for admin functions

## Support

- Vercel Documentation: https://vercel.com/docs
- Flask Documentation: https://flask.palletsprojects.com/
- Project Issues: Check your GitHub repository issues
