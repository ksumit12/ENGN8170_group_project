# Event-Based Timestamp System

## Overview

Clean, deterministic system where timestamps come from **events**, not UI actions.

---

## Architecture

### Events Table (Append-Only)
```sql
CREATE TABLE shed_events (
    id TEXT PRIMARY KEY,
    boat_id TEXT,
    beacon_id TEXT,
    event_type TEXT CHECK(event_type IN ('IN_SHED', 'OUT_SHED')),
    ts_utc TIMESTAMP,  -- Always UTC
    created_at TIMESTAMP
)
```

Every transition creates exactly ONE event.

### Daily Summary (Computed)
```python
summary = {
    'status': 'IN_SHED' or 'ON_WATER',  # Current presence
    'last_seen_utc': datetime,           # From beacon.last_seen
    'on_water_ts_local': datetime,       # First OUT today
    'in_shed_ts_local': datetime,        # Latest IN today
    'day_key': date                      # Local date
}
```

---

## Rules

### Event Emission

**IN_SHED Event:**
- Triggered when: Beacon detected AND boat was OUT
- NOT triggered on: Startup, multiple detections while already IN

**OUT_SHED Event:**
- Triggered when: beacon.last_seen > 12 seconds AND boat was IN
- NOT triggered on: Startup before first detection, multiple timeouts while already OUT

### Status Computation

**Current status** = Live beacon presence (overrides stale DB):
- Beacon seen in last 15s → `IN_SHED`
- Beacon not seen → `ON_WATER`

**on_water_ts_local** = First time boat went out today:
- If OUT event today → use first OUT today
- Else if currently ON_WATER AND no IN today AND OUT yesterday → carry over yesterday's last OUT
- Else → null

**in_shed_ts_local** = Last time boat came back today:
- If IN event today → use latest IN today
- Else → null

### Midnight Rollover

**Automatic!** No special code needed.

When `summarize_today()` is called after midnight:
- `today` advances to new date
- Events for new `today` = empty
- on_water_ts_local and in_shed_ts_local reset to null
- Status recomputed from current presence

---

## Edge Cases Handled

### 1. System starts with beacon ON, no events today
```
status: IN_SHED (presence detected)
in_shed_ts_local: null (no IN event yet)
on_water_ts_local: null
```

### 2. Boat goes OUT, comes back, goes OUT again (multiple trips)
```
Events: OUT(06:00), IN(08:00), OUT(10:00), IN(12:00)

on_water_ts_local: 06:00 (first OUT)
in_shed_ts_local: 12:00 (latest IN)
```

### 3. Beacon OFF/ON toggle without moving
```
Events: OUT(timeout), IN(detected)

Timestamps reflect the events (even if boat didn't physically move)
Use debounce/loss-timeout to ignore glitches if needed
```

### 4. Yesterday → Today transition
```
Yesterday: Boat went OUT at 18:00, never returned
Today: No events yet, beacon still not detected

status: ON_WATER (not present)
on_water_ts_local: Yesterday 18:00 (carry-over)
in_shed_ts_local: null
```

---

## Implementation

### Database Methods

```python
# Log an event (append-only)
db.log_shed_event(boat_id, beacon_id, 'IN_SHED', ts_utc)

# Get events for a date
events = db.get_events_for_boat(boat_id, date_local, 'Australia/Canberra')

# Compute daily summary
summary = db.summarize_today(boat_id, 'Australia/Canberra')
```

### Detection Flow

```python
# On beacon detected (api_server.py)
if was_OUT:
    db.log_shed_event(boat_id, beacon_id, 'IN_SHED')
    # Also update boat.status for compatibility

# On beacon timeout (background thread)
if was_IN and not_seen_for_12s:
    db.log_shed_event(boat_id, beacon_id, 'OUT_SHED')
    # Also update boat.status for compatibility
```

### API Response

```python
# /api/boats endpoint
for boat in boats:
    summary = db.summarize_today(boat.id)
    return {
        'status': summary['status'],
        'last_entry': summary['in_shed_ts_local'],
        'last_exit': summary['on_water_ts_local'],
        'last_seen': summary['last_seen_utc']
    }
```

---

## Benefits

✅ **No fake timestamps** - Only real transitions create timestamps
✅ **Deterministic** - Same events always produce same summary
✅ **Restartable** - Recomputed from events, not cached state
✅ **Timezone-aware** - All logic in club local time
✅ **Yesterday carry-over** - Boats still out show when they left
✅ **Multiple trips** - First OUT, latest IN preserved

---

## Configuration

```bash
# Club timezone (used for "today/yesterday" logic)
CLUB_TIMEZONE=Australia/Canberra  # Default

# Presence detection window
PRESENCE_ACTIVE_WINDOW_S=12  # Seconds before OUT event
```

---

## Testing

### Test 1: Beacon ON at start
```
Expected:
- status: IN_SHED (presence)
- in_shed_ts_local: null (no event yet)
- on_water_ts_local: null
```

### Test 2: OUT → IN cycle
```
1. Turn beacon OFF → wait 12s
   - OUT_SHED event logged
   - status: ON_WATER
   - on_water_ts_local: now

2. Turn beacon ON
   - IN_SHED event logged
   - status: IN_SHED
   - in_shed_ts_local: now
```

### Test 3: Midnight rollover
```
Before midnight (23:59):
- on_water_ts_local: 18:00 today
- in_shed_ts_local: 19:00 today

After midnight (00:01):
- on_water_ts_local: null (new day, no events)
- in_shed_ts_local: null
- If beacon still present → status: IN_SHED (but no timestamp)
```

---

## Database Schema

```sql
-- Events (append-only)
SELECT * FROM shed_events ORDER BY ts_utc;
-- Shows complete history of all transitions

-- Query today's events
SELECT * FROM shed_events 
WHERE boat_id = 'B123' 
  AND date(ts_utc, 'localtime') = date('now', 'localtime');
```

---

## Notes

- **BLE detection unchanged**: This system sits on top, doesn't affect scanning
- **Backward compatible**: Falls back to beacon_states if event system fails
- **No migrations needed**: New table created automatically on first run
- **Timezone**: Uses zoneinfo (Python 3.9+), falls back to UTC if unavailable

---

**Implementation Date**: October 21, 2025  
**Branch**: working-single-scanner  
**Status**: ✅ Implemented and ready for testing

