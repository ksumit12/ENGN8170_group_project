# Automated CSV Logging System

## Overview

The Boat Tracking System now includes a comprehensive automated CSV logging system that:
- **Accumulates data daily** at midnight (00:00 UTC)
- **Exports weekly reports** every Sunday at 11:55 PM (23:55 UTC)
- **Organizes files** in a structured directory hierarchy
- **Uses proper naming conventions** with timestamps and descriptive labels

---

## Directory Structure

```
data/csv_logs/
├── daily/
│   └── {YEAR}/
│       └── {MONTH}/
│           ├── boat_usage_{YYYYMMDD}.csv
│           ├── system_logs_{YYYYMMDD}.csv
│           └── boat_sessions_{YYYYMMDD}.csv
│
└── weekly_exports/
    └── {YEAR}/
        └── Week_{YYYYMMDD}_to_{YYYYMMDD}/
            ├── boat_usage_{YYYYMMDD}.csv (for each day)
            ├── system_logs_{YYYYMMDD}.csv (for each day)
            ├── boat_sessions_{YYYYMMDD}.csv (for each day)
            ├── WEEKLY_SUMMARY_{YYYYMMDD}_to_{YYYYMMDD}.csv
            └── WEEKLY_WATER_TIME_{YYYYMMDD}_to_{YYYYMMDD}.csv
```

### Example Directory Structure

```
data/csv_logs/
├── daily/
│   ├── 2025/
│   │   ├── 10/
│   │   │   ├── boat_usage_20251015.csv
│   │   │   ├── boat_usage_20251016.csv
│   │   │   ├── boat_usage_20251017.csv
│   │   │   ├── system_logs_20251015.csv
│   │   │   ├── system_logs_20251016.csv
│   │   │   ├── system_logs_20251017.csv
│   │   │   ├── boat_sessions_20251015.csv
│   │   │   ├── boat_sessions_20251016.csv
│   │   │   └── boat_sessions_20251017.csv
│   │   └── 11/
│   │       └── ...
│   └── 2026/
│       └── ...
│
└── weekly_exports/
    └── 2025/
        ├── Week_20251013_to_20251020/
        │   ├── boat_usage_20251013.csv
        │   ├── boat_usage_20251014.csv
        │   ├── boat_usage_20251015.csv
        │   ├── boat_usage_20251016.csv
        │   ├── boat_usage_20251017.csv
        │   ├── boat_usage_20251018.csv
        │   ├── boat_usage_20251019.csv
        │   ├── boat_usage_20251020.csv
        │   ├── system_logs_20251013.csv
        │   ├── ...
        │   ├── boat_sessions_20251013.csv
        │   ├── ...
        │   ├── WEEKLY_SUMMARY_20251013_to_20251020.csv
        │   └── WEEKLY_WATER_TIME_20251013_to_20251020.csv
        └── Week_20251020_to_20251027/
            └── ...
```

---

## CSV File Types

### 1. Daily Boat Usage (`boat_usage_{YYYYMMDD}.csv`)

**Description:** Daily record of all boat trips with entry/exit times.

**Columns:**
- Sequence
- Boat Name
- Boat Class
- Exit Time
- Entry Time
- Duration (min)

**Example:**
```csv
Sequence,Boat Name,Boat Class,Exit Time,Entry Time,Duration (min)
1,Thunder,Single,2025-10-22 08:15:30,2025-10-22 09:45:30,90
2,Lightning,Double,2025-10-22 09:00:00,2025-10-22 10:30:00,90
3,Thunder,Single,2025-10-22 14:20:00,2025-10-22 15:50:00,90
```

---

### 2. Daily System Logs (`system_logs_{YYYYMMDD}.csv`)

**Description:** Complete system logs for troubleshooting and audit.

**Columns:**
- Timestamp
- Level
- Component
- Message

**Example:**
```csv
Timestamp,Level,Component,Message
2025-10-22 00:05:12,INFO,SYSTEM,System health check completed
2025-10-22 08:15:30,INFO,TRACKER,Boat 'Thunder' exited shed
2025-10-22 09:45:30,INFO,TRACKER,Boat 'Thunder' entered shed
```

---

### 3. Daily Boat Sessions (`boat_sessions_{YYYYMMDD}.csv`)

**Description:** Detailed session records with boat IDs and status.

**Columns:**
- Boat ID
- Boat Name
- Boat Class
- Session Start
- Session End
- Duration (min)
- Status

**Example:**
```csv
Boat ID,Boat Name,Boat Class,Session Start,Session End,Duration (min),Status
boat_001,Thunder,Single,2025-10-22 08:15:30,2025-10-22 09:45:30,90,Completed
boat_002,Lightning,Double,2025-10-22 09:00:00,2025-10-22 10:30:00,90,Completed
```

---

### 4. Weekly Summary (`WEEKLY_SUMMARY_{YYYYMMDD}_to_{YYYYMMDD}.csv`)

**Description:** Consolidated weekly statistics for all boats.

**Columns:**
- Boat Name
- Boat Class
- Total Trips
- Total Minutes
- Avg Duration (min)
- Max Duration (min)
- Status

**Example:**
```csv
Boat Name,Boat Class,Total Trips,Total Minutes,Avg Duration (min),Max Duration (min),Status
Thunder,Single,12,1080,90,120,operational
Lightning,Double,8,720,90,110,operational
Storm,Quad,5,450,90,95,operational
```

---

### 5. Weekly Water Time Report (`WEEKLY_WATER_TIME_{YYYYMMDD}_to_{YYYYMMDD}.csv`)

**Description:** Comprehensive water time analytics with maintenance insights.

**Columns:** (Variable based on water time data structure)
- Boat ID
- Boat Name
- Total Water Time (hours)
- Number of Sessions
- Average Session Duration
- Maintenance Status
- etc.

---

## Automation Schedule

### Daily Accumulation
- **When:** Every day at 00:00 UTC (midnight)
- **What:** Creates three CSV files for the previous day's data
- **Where:** `data/csv_logs/daily/{YEAR}/{MONTH}/`
- **Files Created:**
  1. `boat_usage_{YYYYMMDD}.csv`
  2. `system_logs_{YYYYMMDD}.csv`
  3. `boat_sessions_{YYYYMMDD}.csv`

### Weekly Export
- **When:** Every Sunday at 23:55 UTC (11:55 PM)
- **What:** Creates a comprehensive weekly export folder
- **Where:** `data/csv_logs/weekly_exports/{YEAR}/Week_{START}_to_{END}/`
- **Contents:**
  - All daily CSV files from the past 7 days
  - Consolidated weekly summary
  - Weekly water time report

---

## File Naming Conventions

### Daily Files
- Format: `{type}_{YYYYMMDD}.csv`
- Example: `boat_usage_20251022.csv`
- Date format: YYYYMMDD (ISO 8601 basic format)

### Weekly Folders
- Format: `Week_{YYYYMMDD}_to_{YYYYMMDD}`
- Example: `Week_20251015_to_20251022`
- Dates: Start date (Monday) to End date (Sunday)

### Weekly Summary Files
- Format: `WEEKLY_SUMMARY_{YYYYMMDD}_to_{YYYYMMDD}.csv`
- Example: `WEEKLY_SUMMARY_20251015_to_20251022.csv`

### Weekly Water Time Files
- Format: `WEEKLY_WATER_TIME_{YYYYMMDD}_to_{YYYYMMDD}.csv`
- Example: `WEEKLY_WATER_TIME_20251015_to_20251022.csv`

---

## Manual Triggers (API Endpoints)

You can manually trigger exports for testing or immediate needs:

### Trigger Daily Accumulation
```bash
curl -X POST http://localhost:5001/api/admin/trigger-daily-accumulation
```

### Trigger Weekly Export
```bash
curl -X POST http://localhost:5001/api/admin/trigger-weekly-export
```

### Export Custom Date Range
Use the existing export endpoints in the Admin/Reports page with custom date ranges.

---

## System Logs

All export activities are logged:

- **Daily accumulation:** Logged with component `EXPORT`
- **Weekly export:** Logged with component `EXPORT`
- **Audit trail:** Logged in `audit.log`

Example log entries:
```
2025-10-22 00:01:15 INFO EXPORT Daily CSV accumulation completed for 2025-10-21
2025-10-22 23:56:30 INFO EXPORT Starting weekly export for Week_20251015_to_20251022
2025-10-22 23:57:45 INFO EXPORT Weekly export completed: data/csv_logs/weekly_exports/2025/Week_20251015_to_20251022
```

---

## Accessing Weekly Exports

### Local Access
Weekly exports are saved locally in:
```
/home/sumit/grp_project/data/csv_logs/weekly_exports/
```

### Finding Latest Export
The most recent weekly export will be in the latest folder:
```bash
ls -lt data/csv_logs/weekly_exports/2025/
```

### Opening/Downloading
1. Navigate to the weekly export folder
2. All CSV files are ready to open with Excel, Google Sheets, or any CSV viewer
3. Files can be copied, shared, or backed up as needed

---

## Retention and Cleanup

### Daily Files
- Kept indefinitely in organized year/month folders
- Can be manually deleted if disk space is a concern
- Recommended: Keep at least 90 days

### Weekly Exports
- Each weekly export contains copies of daily files
- Kept indefinitely for historical records
- Recommended: Archive older exports (>1 year) to external storage

### Manual Cleanup Script
You can create a cleanup script to remove old daily files if needed:
```bash
# Example: Remove daily files older than 90 days
find data/csv_logs/daily -type f -mtime +90 -delete
```

---

## Troubleshooting

### Daily Accumulation Not Running
1. Check system logs: `tail -f logs/boat_tracking.log | grep EXPORT`
2. Verify system time is correct: `date -u`
3. Check scheduler status in logs: Look for "Daily CSV accumulation scheduler started"

### Weekly Export Not Running
1. Verify it's Sunday: `date +%u` (should return 7)
2. Check time is near 23:55 UTC: `date -u`
3. Check logs for "Weekly export system scheduler started"

### Missing CSV Files
1. Check if directories exist: `ls -R data/csv_logs/`
2. Verify database has data for the requested dates
3. Check error logs: `tail -f logs/errors.log`

### Permission Issues
If you see permission errors:
```bash
chmod -R 755 data/csv_logs/
```

---

## Benefits

### For Administrators
- ✅ Automatic daily backups of all data
- ✅ Weekly consolidated reports ready to share
- ✅ No manual intervention required
- ✅ Organized file structure for easy navigation

### For Data Analysis
- ✅ Historical data readily available
- ✅ CSV format compatible with Excel, Python, R, etc.
- ✅ Consistent file naming for automated processing
- ✅ Multiple perspectives (usage, logs, sessions, summaries)

### For Compliance/Auditing
- ✅ Complete audit trail
- ✅ Daily snapshots for point-in-time analysis
- ✅ System logs included for troubleshooting
- ✅ Automated timestamped records

---

## Integration with Existing Features

This automated system **complements** the existing manual export features in the Admin/Reports page:

- Manual exports: Use for custom date ranges or immediate needs
- Automated exports: Ensure consistent daily/weekly backups

Both systems use the same underlying data and export functions, ensuring consistency.

---

## Future Enhancements

Possible future improvements:
- Email delivery of weekly exports
- Cloud storage integration (Google Drive, Dropbox, S3)
- Compressed archives for weekly exports
- Customizable export schedules
- Export status dashboard in web UI

---

## Support

For questions or issues:
1. Check logs in `logs/boat_tracking.log`
2. Review error logs in `logs/errors.log`
3. Check audit trail in `logs/audit.log`
4. Contact system administrator

---

**Last Updated:** October 22, 2025
**System Version:** Boat Tracking System v2.0 with Automated CSV Logging

