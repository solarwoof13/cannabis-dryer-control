#!/bin/bash

echo "================================"
echo "Updating GUI from GitHub..."
echo "================================"

# Base URLs
GITHUB_BASE="https://raw.githubusercontent.com/solarwoof13/cannabis-dryer-control/main/touchscreen"
TOUCHSCREEN_DIR="/home/mikejames/cannabis-dryer/touchscreen"

# Backup current files first
echo "Creating backup..."
cp "$TOUCHSCREEN_DIR/index.html" "$TOUCHSCREEN_DIR/index.html.bak" 2>/dev/null

# Update HTML files
echo "Updating HTML files..."
wget -q "$GITHUB_BASE/index.html" -O "$TOUCHSCREEN_DIR/index.html" && echo "✓ index.html updated" || echo "✗ Failed to update index.html"
wget -q "$GITHUB_BASE/analytics.html" -O "$TOUCHSCREEN_DIR/analytics.html" && echo "✓ analytics.html updated" || echo "✗ Failed to update analytics.html"
wget -q "$GITHUB_BASE/settings.html" -O "$TOUCHSCREEN_DIR/settings.html" && echo "✓ settings.html updated" || echo "✗ Failed to update settings.html"
wget -q "$GITHUB_BASE/index3.html" -O "$TOUCHSCREEN_DIR/index3.html" 2>/dev/null && echo "✓ index3.html updated" || echo "- No index3.html found or no changes"

# Check if the main.py process is running and restart if needed
echo ""
if pgrep -f "main.py" > /dev/null; then
    echo "Restarting cannabis dryer control system..."
    pkill -f "main.py"
    sleep 2
    cd /home/mikejames/cannabis-dryer
    source venv/bin/activate
    nohup python main.py > logs/system.log 2>&1 &
    echo "✓ System restarted"
else
    echo "System not currently running. Start with:"
    echo "  cd ~/cannabis-dryer && source venv/bin/activate && python main.py"
fi

echo ""
echo "================================"
echo "GUI Update Complete!"
echo "================================"
echo ""
echo "Access the system at:"
echo "  http://localhost:5000/"
echo "  http://192.168.1.184:5000/"
echo ""
echo "Note: Your local changes to index.html have been backed up to index.html.bak"