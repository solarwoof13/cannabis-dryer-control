#!/bin/bash
# Cannabis Dryer - Fullscreen Kiosk Setup
# Run this ONCE on your Raspberry Pi to configure autostart

set -e

echo "=========================================="
echo "Cannabis Dryer - Kiosk Mode Setup"
echo "=========================================="

# Get project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Project directory: $PROJECT_DIR"

# Create systemd service
echo "Creating backend service..."
sudo tee /etc/systemd/system/cannabis-dryer.service > /dev/null <<EOF
[Unit]
Description=Cannabis Dryer Control System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/python3 $PROJECT_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/system.log
StandardError=append:$PROJECT_DIR/logs/system_error.log

[Install]
WantedBy=multi-user.target
EOF

# Create kiosk launcher
echo "Creating kiosk launcher..."
mkdir -p "$PROJECT_DIR/deployment"
cat > "$PROJECT_DIR/deployment/start_kiosk.sh" <<'EOF'
#!/bin/bash
sleep 10
xset s off
xset -dpms
xset s noblank
unclutter -idle 5 -root &
chromium-browser --kiosk --noerrdialogs --disable-infobars --start-fullscreen http://localhost:5000
EOF
chmod +x "$PROJECT_DIR/deployment/start_kiosk.sh"

# Create autostart entry
echo "Creating autostart entry..."
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/cannabis-dryer-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cannabis Dryer Kiosk
Exec=$PROJECT_DIR/deployment/start_kiosk.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

# Install packages
echo "Installing packages..."
sudo apt-get update -qq
sudo apt-get install -y chromium-browser unclutter xdotool

# Enable service
echo "Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable cannabis-dryer.service
sudo systemctl start cannabis-dryer.service

echo ""
echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Exit fullscreen: Alt+F4 or F11"
echo "View logs: tail -f $PROJECT_DIR/logs/dryer_control.log"
echo ""
read -p "Reboot now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo reboot
fi