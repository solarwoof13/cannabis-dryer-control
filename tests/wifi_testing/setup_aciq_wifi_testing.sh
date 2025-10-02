#!/bin/bash
#
# ACiQ WiFi Control - Quick Start Setup Script
# =============================================
# Prepares your Raspberry Pi for ACiQ WiFi mini-split testing
#
# Usage: ./setup_aciq_wifi_testing.sh
#
# This script:
# 1. Installs required dependencies
# 2. Creates necessary directories
# 3. Sets up test environment
# 4. Configures security basics
# 5. Runs initial discovery
#
# SAFE TO RUN: Does not modify main system operation
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$HOME/cannabis-dryer"

echo -e "${BOLD}${BLUE}"
echo "╔════════════════════════════════════════════════╗"
echo "║  ACiQ Mini-Split WiFi Control Setup            ║"
echo "║  Cannabis Dryer Control System                 ║"
echo "╚════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}⚠  Warning: Not running on Raspberry Pi${NC}"
    echo "This script is designed for Raspberry Pi but will continue anyway."
    read -p "Continue? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for sudo
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}✗ Do not run this script as root${NC}"
    echo "Run without sudo: ./setup_aciq_wifi_testing.sh"
    exit 1
fi

# Function to print status
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1 failed${NC}"
        return 1
    fi
}

# Function to check command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "\n${BOLD}Step 1: Checking Prerequisites${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Python
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓ Python 3 installed: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi

# Check pip
if command_exists pip3; then
    echo -e "${GREEN}✓ pip3 installed${NC}"
else
    echo -e "${YELLOW}⚠ pip3 not found, installing...${NC}"
    sudo apt-get update -qq
    sudo apt-get install -y python3-pip
    print_status "pip3 installation"
fi

# Check git
if command_exists git; then
    echo -e "${GREEN}✓ git installed${NC}"
else
    echo -e "${RED}✗ git not found${NC}"
    echo "Install git: sudo apt-get install git"
    exit 1
fi

# Check project directory
if [ -d "$PROJECT_ROOT" ]; then
    echo -e "${GREEN}✓ Project directory found: $PROJECT_ROOT${NC}"
    cd "$PROJECT_ROOT"
else
    echo -e "${YELLOW}⚠ Project directory not found${NC}"
    echo "Expected location: $PROJECT_ROOT"
    read -p "Enter cannabis-dryer project path: " PROJECT_ROOT
    
    if [ ! -d "$PROJECT_ROOT" ]; then
        echo -e "${RED}✗ Directory does not exist: $PROJECT_ROOT${NC}"
        exit 1
    fi
    cd "$PROJECT_ROOT"
fi

echo -e "\n${BOLD}Step 2: Installing Dependencies${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create requirements file if it doesn't exist
ACIQ_REQUIREMENTS="$PROJECT_ROOT/requirements-aciq.txt"
cat > "$ACIQ_REQUIREMENTS" << 'EOF'
# ACiQ WiFi Control Dependencies
paho-mqtt==1.6.1
requests==2.31.0
cryptography==41.0.0
scapy==2.5.0
EOF

echo "Installing Python packages..."
pip3 install -q -r "$ACIQ_REQUIREMENTS"
print_status "Python dependencies installed"

# Optional: Install network tools
echo -e "\n${BOLD}Installing Optional Network Tools${NC}"
read -p "Install arp-scan and nmap for better network discovery? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing network tools (requires sudo)..."
    sudo apt-get update -qq
    sudo apt-get install -y arp-scan nmap > /dev/null 2>&1
    print_status "Network tools installed"
fi

echo -e "\n${BOLD}Step 3: Setting Up Directory Structure${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create test directories
mkdir -p "$PROJECT_ROOT/tests/aciq_testing"
print_status "Created tests/aciq_testing/"

mkdir -p "$PROJECT_ROOT/software/config"
print_status "Created software/config/"

mkdir -p "$PROJECT_ROOT/logs"
print_status "Created logs/"

# Create .gitignore entries for sensitive data
GITIGNORE="$PROJECT_ROOT/.gitignore"
if ! grep -q "aciq_config.json" "$GITIGNORE" 2>/dev/null; then
    echo "" >> "$GITIGNORE"
    echo "# ACiQ WiFi Control - Sensitive Data" >> "$GITIGNORE"
    echo "software/config/aciq_config.json" >> "$GITIGNORE"
    echo "tests/aciq_testing/*.pcapng" >> "$GITIGNORE"
    echo "tests/aciq_testing/credentials.txt" >> "$GITIGNORE"
    echo ".aciq_key" >> "$GITIGNORE"
    print_status "Updated .gitignore for security"
fi

echo -e "\n${BOLD}Step 4: Creating Configuration Template${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CONFIG_FILE="$PROJECT_ROOT/software/config/aciq_config.json"

if [ -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}⚠ Configuration file already exists${NC}"
    read -p "Backup and create new? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        echo -e "${GREEN}✓ Backup created${NC}"
    else
        echo "Keeping existing configuration"
        CONFIG_EXISTS=true
    fi
fi

if [ ! "$CONFIG_EXISTS" = true ]; then
    cat > "$CONFIG_FILE" << 'EOF'
{
  "enabled": false,
  "control_method": "mqtt_local",
  "device_ip": "192.168.1.100",
  "device_id": "aciq_minisplit_001",
  
  "mqtt": {
    "broker": "192.168.1.100",
    "port": 1883,
    "username": "",
    "password": "",
    "topic_prefix": "aciq",
    "use_tls": false
  },
  
  "http": {
    "base_url": "http://192.168.1.100",
    "api_key": "",
    "use_https": false,
    "verify_ssl": false
  },
  
  "cloud": {
    "api_url": "https://api.aciq.com",
    "username": "",
    "password": "",
    "app_token": ""
  },
  
  "limits": {
    "temp_min": 60,
    "temp_max": 75,
    "max_commands_per_minute": 10
  },
  
  "ir_fallback": {
    "enabled": true,
    "gpio_pin": 18
  },
  
  "encrypted": false
}
EOF
    print_status "Created default configuration"
    echo -e "${YELLOW}  → Edit: $CONFIG_FILE${NC}"
fi

echo -e "\n${BOLD}Step 5: Security Setup${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Generate encryption key
KEY_FILE="$HOME/.aciq_key"
if [ ! -f "$KEY_FILE" ]; then
    echo "Generating encryption key..."
    python3 << EOF
from cryptography.fernet import Fernet
key = Fernet.generate_key()
with open('$KEY_FILE', 'wb') as f:
    f.write(key)
EOF
    chmod 600 "$KEY_FILE"
    print_status "Encryption key generated at $KEY_FILE"
    echo -e "${YELLOW}  → BACKUP THIS FILE SECURELY!${NC}"
else
    echo -e "${GREEN}✓ Encryption key already exists${NC}"
fi

# Set file permissions
chmod 600 "$CONFIG_FILE" 2>/dev/null
chmod 700 "$PROJECT_ROOT/tests/aciq_testing" 2>/dev/null
print_status "File permissions secured"

echo -e "\n${BOLD}Step 6: Creating Test Scripts${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create quick test script
TEST_SCRIPT="$PROJECT_ROOT/tests/aciq_testing/quick_test.sh"
cat > "$TEST_SCRIPT" << 'EOF'
#!/bin/bash
# Quick connectivity test for ACiQ mini-split

DEVICE_IP="192.168.1.100"  # UPDATE THIS!

echo "Testing ACiQ Mini-Split Connectivity"
echo "===================================="
echo ""

echo "1. Ping test..."
if ping -c 3 -W 2 $DEVICE_IP > /dev/null 2>&1; then
    echo "✓ Device responding to ping"
else
    echo "✗ Device not responding"
    exit 1
fi

echo ""
echo "2. Port scan..."
for PORT in 80 443 1883 8080; do
    if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$DEVICE_IP/$PORT" 2>/dev/null; then
        echo "✓ Port $PORT is OPEN"
    else
        echo "  Port $PORT is closed"
    fi
done

echo ""
echo "3. MQTT test..."
if command -v mosquitto_sub >/dev/null 2>&1; then
    timeout 3 mosquitto_sub -h $DEVICE_IP -t '#' -C 1 -v > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✓ MQTT broker responding"
    else
        echo "  MQTT broker not accessible"
    fi
else
    echo "  mosquitto-clients not installed"
    echo "  Install with: sudo apt-get install mosquitto-clients"
fi

echo ""
echo "Test complete!"
EOF

chmod +x "$TEST_SCRIPT"
print_status "Created quick_test.sh"

# Create README in tests directory
cat > "$PROJECT_ROOT/tests/aciq_testing/README.md" << 'EOF'
# ACiQ WiFi Testing

This directory contains all ACiQ mini-split WiFi control testing files.

## Test Files

- `quick_test.sh` - Quick connectivity test
- `discovery_results_*.json` - Network discovery results
- Test logs and captures

## Getting Started

1. Update device IP in quick_test.sh
2. Run discovery: `python3 test_aciq_wifi_discovery.py`
3. Review results in discovery_results_*.json
4. Follow ACIQ_WIFI_TESTING_GUIDE.md

## Security

⚠️ **NEVER commit:**
- Credentials
- API keys
- Packet captures (*.pcapng)
- Configuration files with real passwords

These are already in .gitignore
EOF

print_status "Created testing README"

echo -e "\n${BOLD}Step 7: System Check${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check network connectivity
if ping -c 1 -W 2 8.8.8.8 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Internet connectivity working${NC}"
else
    echo -e "${YELLOW}⚠ No internet connectivity${NC}"
fi

# Check if main system is running
if pgrep -f "main.py" > /dev/null; then
    echo -e "${YELLOW}⚠ Main control system is running${NC}"
    echo -e "  ${RED}STOP main system before testing WiFi control!${NC}"
    echo -e "  Run: pkill -f main.py"
fi

# Summary
echo -e "\n${BOLD}${GREEN}╔════════════════════════════════════════════════╗"
echo "║            Setup Complete!                     ║"
echo "╚════════════════════════════════════════════════╝${NC}"

echo -e "\n${BOLD}Next Steps:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. ${BOLD}Prepare Mini-Split:${NC}"
echo "   • Power on ACiQ mini-split"
echo "   • Connect to WiFi using ACiQ mobile app"
echo "   • Note the device IP address from your router"
echo ""
echo "2. ${BOLD}Update Configuration:${NC}"
echo "   • Edit: $CONFIG_FILE"
echo "   • Set correct device_ip"
echo "   • Update credentials if needed"
echo ""
echo "3. ${BOLD}Run Quick Test:${NC}"
echo "   cd $PROJECT_ROOT/tests/aciq_testing"
echo "   ./quick_test.sh"
echo ""
echo "4. ${BOLD}Run Full Discovery:${NC}"
echo "   cd $PROJECT_ROOT"
echo "   sudo python3 test_aciq_wifi_discovery.py"
echo ""
echo "5. ${BOLD}Review Documentation:${NC}"
echo "   • Read ACIQ_WIFI_TESTING_GUIDE.md"
echo "   • Follow all 5 testing phases"
echo "   • Complete security checklist"
echo ""
echo -e "${BOLD}${BLUE}Important Reminders:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "• ${RED}STOP main system before WiFi testing${NC}"
echo "• Test on isolated network first"
echo "• Keep IR fallback functional"
echo "• Never commit credentials to git"
echo "• Backup encryption key: $KEY_FILE"
echo "• Review logs regularly"
echo ""
echo -e "${BOLD}Support:${NC}"
echo "• Full guide: ACIQ_WIFI_TESTING_GUIDE.md"
echo "• Test logs: tests/aciq_testing/"
echo "• Configuration: $CONFIG_FILE"
echo ""
echo -e "${GREEN}Ready to test! Good luck! 🚀${NC}"