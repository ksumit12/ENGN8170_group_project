#!/bin/bash

# Setup Verification Script for Boat Tracking System
# Checks if everything is properly configured

echo "🔍 Boat Tracking System - Setup Verification"
echo "==========================================="
echo ""

# Check Python version
echo "🐍 Checking Python version..."
python_version=$(python3 --version 2>&1)
echo "  $python_version"

if [[ $python_version == *"3.10"* ]] || [[ $python_version == *"3.11"* ]] || [[ $python_version == *"3.12"* ]]; then
    echo "  ✅ Python version is compatible"
else
    echo "  ⚠️  Python version may not be compatible (recommend 3.10+)"
fi
echo ""

# Check virtual environment
echo "📦 Checking virtual environment..."
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "  ❌ Virtual environment not activated!"
    echo "  💡 Run: source .venv/bin/activate"
    exit 1
else
    echo "  ✅ Virtual environment activated: $VIRTUAL_ENV"
fi
echo ""

# Check required packages
echo "📚 Checking required packages..."
missing_packages=()
required_packages=("flask" "flask_cors" "bleak" "sqlite3")

for package in "${required_packages[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        echo "  ✅ $package"
    else
        echo "  ❌ $package (missing)"
        missing_packages+=("$package")
    fi
done

if [ ${#missing_packages[@]} -gt 0 ]; then
    echo "  💡 Install missing packages: pip install ${missing_packages[*]}"
    exit 1
fi
echo ""

# Check database
echo "🗄️  Checking database..."
if [ -f "data/boat_tracking.db" ]; then
    echo "  ✅ Database exists: data/boat_tracking.db"
    
    # Check if database has tables
    table_count=$(python3 -c "
import sqlite3
conn = sqlite3.connect('data/boat_tracking.db')
cursor = conn.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = cursor.fetchall()
print(len(tables))
conn.close()
" 2>/dev/null)
    
    if [ "$table_count" -gt 0 ]; then
        echo "  ✅ Database has $table_count tables"
    else
        echo "  ⚠️  Database exists but has no tables"
        echo "  💡 Run: python3 setup_new_system.py"
    fi
else
    echo "  ❌ Database not found"
    echo "  💡 Run: python3 setup_new_system.py"
fi
echo ""

# Check BLE support
echo "📡 Checking BLE support..."
if command -v bluetoothctl &> /dev/null; then
    echo "  ✅ BlueZ installed"
else
    echo "  ⚠️  BlueZ not found (BLE may not work)"
fi

# Check if user is in bluetooth group
if groups | grep -q bluetooth; then
    echo "  ✅ User in bluetooth group"
else
    echo "  ⚠️  User not in bluetooth group (may need sudo for BLE)"
fi
echo ""

# Check ports
echo "🔌 Checking ports..."
for port in 5000 8000; do
    if lsof -ti:$port &>/dev/null; then
        echo "  ⚠️  Port $port is in use"
    else
        echo "  ✅ Port $port is available"
    fi
done
echo ""

# Check scripts
echo "📜 Checking scripts..."
scripts=("scripts/setup_rpi.sh" "scripts/stop_everything.sh" "scripts/quick_start.sh")
for script in "${scripts[@]}"; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            echo "  ✅ $script (executable)"
        else
            echo "  ⚠️  $script (not executable)"
            echo "  💡 Run: chmod +x $script"
        fi
    else
        echo "  ❌ $script (missing)"
    fi
done
echo ""

# Summary
echo "📋 Setup Summary"
echo "================"
if [ ${#missing_packages[@]} -eq 0 ] && [ -f "data/boat_tracking.db" ]; then
    echo "✅ Setup looks good! You can start the system with:"
    echo "   ./scripts/quick_start.sh"
    echo ""
    echo "Or manually:"
    echo "   python3 boat_tracking_system.py --display-mode web --api-port 8000 --web-port 5000"
else
    echo "⚠️  Setup needs attention. Please fix the issues above."
fi
echo ""

