# 🚣‍♂️ Rowing Boat Health System

A comprehensive BLE-powered system for tracking rowing boat usage, health monitoring, and maintenance management.

## 🚀 Quick Start

### Option 1: Simple Version (Python 3.10+ Compatible)
```bash
python3 quick_start.py
```
Then open: **http://localhost:5000**

### Option 2: Full System (Python 3.11+ Required)
```bash
# Install dependencies
python3 run.py --install

# Run system (bench mode)
python3 run.py

# Access dashboard
# Open: http://localhost:8000
```

## 📋 Available Commands

```bash
# Run in bench mode (default)
python3 run.py

# Run in production mode (dual scanners)
python3 run.py --mode production

# Run only BLE scanner
python3 run.py --scanner-only

# Run only backend API
python3 run.py --backend-only

# Run visualization tools
python3 run.py --visualize

# Install dependencies
python3 run.py --install

# Show system status
python3 run.py --status
```

## 🎯 Modes

### **Bench Mode** (Default)
- Single scanner with beacon ON/OFF simulation
- Perfect for testing and development
- Toggle your beacon to simulate boat entry/exit
- No physical gate required

### **Production Mode**
- Dual scanners for real gate detection
- Direction detection (ENTER vs EXIT)
- MQTT support for distributed scanners
- Full production deployment

## 📊 Features

- **🔍 BLE Detection**: Real-time beacon scanning with RSSI analysis
- **📈 Health Scoring**: 0-100 intelligent health scores
- **📱 Live Dashboard**: Real-time web interface with WebSocket updates
- **🔧 Maintenance Alerts**: Automated service scheduling
- **📊 Visualization**: RSSI plotting and data analysis tools
- **🐳 Docker Support**: Complete containerization

## 📁 Project Structure

```
grp_project/
├── run.py                    # 🚀 Single entry point script
├── README.md                 # This file
└── rowing_system/            # Main system directory
    ├── main.py              # System manager
    ├── scanner.py           # BLE scanner service
    ├── backend.py           # FastAPI web server
    ├── health_scoring.py    # Health scoring algorithm
    ├── visualization.py     # Data analysis tools
    ├── config.yaml          # Configuration
    ├── static/dashboard.html # Web dashboard
    └── ...                  # Other system files
```

## 🔧 Configuration

Edit `rowing_system/config.yaml` to customize:
- RSSI thresholds
- Health scoring parameters
- Maintenance intervals
- Scanner settings

## 📚 Documentation

For detailed documentation, see `rowing_system/README.md`

## 🤝 Support

- Check the troubleshooting section in the detailed README
- Review configuration options
- Use `python3 run.py --status` to check system health

---

**Happy Rowing! 🚣‍♂️**