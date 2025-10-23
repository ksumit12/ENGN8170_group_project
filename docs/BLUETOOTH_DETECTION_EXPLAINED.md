# Bluetooth iBeacon Detection System - Complete Explanation

##  You are on: `door-lr-v2` branch

---

##  How iBeacon Detection Works (The Core)

### **Main Detection Script: `ble_scanner.py`**

This is THE file that actually detects iBeacons using Bluetooth.

#### **Key Functions:**

1. **`detection_callback()` (Line 192-285)**
   - This is called every time a Bluetooth device is seen
   - **Filters by RSSI threshold** (default -80 dBm)
   - **Parses iBeacon data** from Apple manufacturer data (0x004C)
   - Extracts: UUID, Major, Minor, TxPower
   - Also supports Eddystone beacons (UID/URL)

2. **`parse_ibeacon()` (Line 93-108)**
   - Parses the raw iBeacon packet
   - Creates stable ID: `{uuid}:{major}:{minor}`
   - This ID is used to identify boats

3. **`scan_continuously()` (Line 345-381)**
   - Runs continuously using `BleakScanner` (async Bluetooth library)
   - Calls `detection_callback` for every detected device
   - Batches detections and sends to API server

4. **`_process_observations()` (Line 287-343)**
   - Sends detected beacons to the API server
   - POST to `/api/v1/detections`
   - Payload includes: scanner_id, beacon info, RSSI, timestamp

---

##  Current Architecture: **Single Scanner Approach**

### How it works now (working-single-scanner):

```

  BLE Scanner      ← ble_scanner.py
  (ONE scanner)       Detects iBeacons

          Posts detections
         

  API Server               ← api_server.py
  /api/v1/detections          Receives detections

          Processes with FSM
         

  SingleScannerEngine       ← app/single_scanner_engine.py
  (Simple FSM)            

         
         
    Decision: "If detected = INSIDE harbor"
              "If not seen for X seconds = OUT"
```

### **SingleScannerEngine Logic** (app/single_scanner_engine.py):

```python
# Line 29-58: process_detection()
def process_detection():
    # ANY detection → Boat is INSIDE
    state = DetectionState.INSIDE
    boat_status = BoatStatus.IN_HARBOR
    
    # API server background task checks "last seen"
    # If not seen for X seconds → Mark as OUT
```

**Limitations:**
-  Can't tell ENTER vs EXIT direction
-  Can't detect which side of door boat is on
-  Simple timeout-based OUT detection
-  Good for: showcase events with one scanner

---

##  Your Previous Approach: **Two Scanner Door Left/Right**

### How it SHOULD work (your original idea):

```
                  DOOR
                    
    
     LEFT Scanner    RIGHT Scanner
       (INSIDE)       (OUTSIDE)   
    
                            
             Both POST to   
                            
    
         API Server               
      /api/v1/detections          
    
              Processes with
             
    
       DoorLREngine (FSM)           ← app/door_lr_engine.py
       DirectionClassifier          ← app/direction_classifier.py
    
             
             
    Decision based on:
    - Which scanner sees beacon FIRST?
    - Which scanner sees STRONGER signal?
    - RSSI pattern over time (entering vs leaving)
```

### **DoorLREngine Logic** (app/door_lr_engine.py):

```python
# Line 43-120: process_detection()
def process_detection(scanner_id, beacon_id, rssi):
    # Determine which scanner (LEFT or RIGHT)
    leftish = scanner_id.endswith('left')
    rightish = scanner_id.endswith('right')
    
    # Use DirectionClassifier to analyze RSSI patterns
    events = classifier.update(beacon_id, logical_scanner, rssi, timestamp)
    
    if event.direction == 'ENTER':
        state = DetectionState.INSIDE
        boat_status = BoatStatus.IN_HARBOR
        end_trip()
    elif event.direction == 'LEAVE':
        state = DetectionState.OUTSIDE
        boat_status = BoatStatus.OUT
        start_trip()
```

### **DirectionClassifier** (app/direction_classifier.py):

This is your sophisticated FSM that analyzes:
- **RSSI peaks** from both scanners
- **Time lag** between left and right peaks
- **Signal strength patterns** (rising vs falling)
- **Dwell time** (how long beacon stays in range)

**Parameters (Line 29-39 in door_lr_engine.py):**
```python
active_dbm=-90      # Threshold for "beacon is active"
energy_dbm=-85      # Threshold for "strong signal"
delta_db=2.0        # Min difference between scanners
dwell_s=0.05        # Min time beacon must be seen
window_s=0.5        # Time window for analysis
tau_min_s=0.05      # Min time between peaks
cooldown_s=1.0      # Cooldown after detection
slope_min_db_per_s=2.0    # Min RSSI change rate
min_peak_sep_s=0.05       # Min separation between peaks
```

---

##  Where to Start Your Two-Scanner Implementation

### **Files You Already Have (Ready to Use):**

1. **`ble_scanner.py`** 
   - Already detects iBeacons perfectly
   - Already supports multiple scanners
   - Just need to run TWO instances (one for left, one for right)

2. **`app/door_lr_engine.py`** 
   - Your FSM logic for two scanners
   - Uses DirectionClassifier

3. **`app/direction_classifier.py`** 
   - Sophisticated RSSI analysis
   - Determines ENTER vs LEAVE based on patterns

4. **`api_server.py`** 
   - Already receives detections from multiple scanners
   - Already routes to FSM engine

### **What Needs Configuration:**

1. **Enable DoorLREngine instead of SingleScannerEngine**
   
   In `api_server.py` or `boat_tracking_system.py`, change the FSM engine:
   
   ```python
   # Current (single scanner):
   from app.single_scanner_engine import SingleScannerEngine
   fsm_engine = SingleScannerEngine(db, outer_id, inner_id)
   
   # Change to (two scanners):
   from app.door_lr_engine import DoorLREngine
   fsm_engine = DoorLREngine(db, outer_id, inner_id)
   ```

2. **Run TWO Scanner Instances**
   
   ```bash
   # Scanner 1 (LEFT/INSIDE)
   python3 ble_scanner.py --scanner-id="scanner-left" \
                          --server-url="http://localhost:5001" \
                          --adapter="hci0"
   
   # Scanner 2 (RIGHT/OUTSIDE)  
   python3 ble_scanner.py --scanner-id="scanner-right" \
                          --server-url="http://localhost:5001" \
                          --adapter="hci1"
   ```

3. **Configure Scanner IDs in Config**
   
   In `system/json/scanner_config.json`:
   ```json
   {
     "outer_scanner_id": "scanner-right",
     "inner_scanner_id": "scanner-left",
     "mode": "door-lr"
   }
   ```

---

##  Detection Flow Comparison

### **Single Scanner (Current):**
```
iBeacon detected → POST to API → SingleScannerEngine
                                        ↓
                                  Mark as INSIDE
                                        ↓
                             Timeout → Mark as OUT
```

### **Two Scanner (Your Goal):**
```
Left Scanner sees beacon  → POST to API 
Right Scanner sees beacon → POST to API 
                                          ↓
                                   DoorLREngine
                                   DirectionClassifier
                                          ↓
                         Analyze RSSI patterns from BOTH
                                          ↓
                              
                                                     
                         ENTER pattern           LEAVE pattern
                              ↓                       
                        Mark INSIDE              Mark OUTSIDE
                        End trip                 Start trip
```

---

##  Implementation Plan for Two-Scanner Approach

### **Step 1: Fix DoorLREngine**

The current `door_lr_engine.py` has a bypass (Line 44-49):
```python
# REMOVE THIS:
try:
    from .database_models import DetectionState
    return (DetectionState.IDLE, DetectionState.IDLE)
except Exception:
    return None
```

This was added to disable it during single-scanner demo. Remove it!

### **Step 2: Configure System to Use DoorLREngine**

Find where the FSM engine is initialized and switch it.

### **Step 3: Tune Parameters**

Adjust the parameters in `door_lr_engine.py` (Line 29-39) based on:
- Physical distance between scanners
- Door width
- Boat passing speed
- Beacon signal strength

### **Step 4: Calibration**

Use your calibration tools:
- `calibration/door_lr_calibration.py`
- `calibration/find_center_live.py`
- `calibration/precheck_door_lr.py`

### **Step 5: Test with Simulator**

Use `door_lr_simulator.py` to test the FSM without physical hardware.

---

##  Key Files Reference

| File | Purpose | Line of Interest |
|------|---------|------------------|
| `ble_scanner.py` | **iBeacon detection** | Line 192 (detection_callback) |
| `app/single_scanner_engine.py` | Current FSM (demo mode) | Line 29 (process_detection) |
| `app/door_lr_engine.py` | Two-scanner FSM (your goal) | Line 43 (process_detection) |
| `app/direction_classifier.py` | RSSI analysis logic | Entire file |
| `api_server.py` | Receives detections | Search for "FSM" |
| `boat_tracking_system.py` | Main orchestrator | Search for "FSM" or "engine" |

---

##  Summary

### **iBeacon Detection (Hardware Layer):**
- **WHERE:** `ble_scanner.py`
- **HOW:** Using `BleakScanner` library
- **WHAT:** Parses Apple manufacturer data (0x004C)
- **OUTPUT:** Sends to API server with scanner_id, beacon_id, RSSI

### **Processing (Logic Layer):**
- **Current:** `SingleScannerEngine` - simple "detected = inside"
- **Your Goal:** `DoorLREngine` - sophisticated RSSI pattern analysis

### **Next Steps to Implement Two-Scanner:**
1. Remove the bypass in `door_lr_engine.py` (Line 44-49)
2. Switch FSM engine from Single to DoorLR
3. Configure two scanner IDs (left/right)
4. Run two scanner instances
5. Calibrate parameters
6. Test!

---

**You have all the code ready! Just need to:**
-  Enable `DoorLREngine` 
-  Configure scanner IDs
-  Run two scanners
-  Tune parameters

Your `door-lr-v2` branch is the perfect starting point for this! 




