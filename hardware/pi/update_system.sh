#!/bin/bash

echo "================================"
echo "Cannabis Dryer System Updater"
echo "================================"

# Configuration
REPO_URL="https://github.com/solarwoof13/cannabis-dryer-control.git"
PI_DIR="/home/mikejames/cannabis-dryer"
BACKUP_DIR="/home/mikejames/cannabis-dryer-backups/$(date +%Y%m%d_%H%M%S)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $2 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
    fi
}

# Parse arguments
UPDATE_TYPE=${1:-all}  # Default to updating everything

case $UPDATE_TYPE in
    gui)
        echo "Updating GUI files only..."
        ;;
    code)
        echo "Updating Python code only..."
        ;;
    all)
        echo "Updating everything..."
        ;;
    *)
        echo "Usage: $0 [gui|code|all]"
        echo "  gui  - Update only HTML/CSS/JS files"
        echo "  code - Update only Python files"
        echo "  all  - Update everything (default)"
        exit 1
        ;;
esac

# Create backup
echo -e "\n${YELLOW}Creating backup...${NC}"
mkdir -p "$BACKUP_DIR"

if [ "$UPDATE_TYPE" = "gui" ] || [ "$UPDATE_TYPE" = "all" ]; then
    cp -r "$PI_DIR/touchscreen" "$BACKUP_DIR/" 2>/dev/null
    print_status "GUI backup created" $?
fi

if [ "$UPDATE_TYPE" = "code" ] || [ "$UPDATE_TYPE" = "all" ]; then
    cp -r "$PI_DIR/software" "$BACKUP_DIR/" 2>/dev/null
    cp "$PI_DIR/main.py" "$BACKUP_DIR/" 2>/dev/null
    print_status "Code backup created" $?
fi

# Stop the running system
if pgrep -f "main.py" > /dev/null; then
    echo -e "\n${YELLOW}Stopping current system...${NC}"
    pkill -f "main.py"
    sleep 2
    print_status "System stopped" 0
fi

# Update from Git
echo -e "\n${YELLOW}Pulling latest changes from GitHub...${NC}"
cd "$PI_DIR"
git stash 2>/dev/null  # Stash local changes
git pull origin main
PULL_STATUS=$?
print_status "Git pull completed" $PULL_STATUS

if [ $PULL_STATUS -ne 0 ]; then
    echo -e "${RED}Git pull failed. Trying to clone fresh copy...${NC}"
    cd ~
    rm -rf cannabis-dryer-temp
    git clone "$REPO_URL" cannabis-dryer-temp
    
    if [ $? -eq 0 ]; then
        # Copy specific directories based on update type
        if [ "$UPDATE_TYPE" = "gui" ] || [ "$UPDATE_TYPE" = "all" ]; then
            cp -r cannabis-dryer-temp/touchscreen/* "$PI_DIR/touchscreen/"
            print_status "GUI files updated from fresh clone" $?
        fi
        
        if [ "$UPDATE_TYPE" = "code" ] || [ "$UPDATE_TYPE" = "all" ]; then
            cp -r cannabis-dryer-temp/software/* "$PI_DIR/software/"
            cp cannabis-dryer-temp/main.py "$PI_DIR/"
            print_status "Python files updated from fresh clone" $?
        fi
        
        rm -rf cannabis-dryer-temp
    else
        echo -e "${RED}Failed to clone repository${NC}"
        exit 1
    fi
fi

# Apply Pi-specific modifications
if [ "$UPDATE_TYPE" = "code" ] || [ "$UPDATE_TYPE" = "all" ]; then
    echo -e "\n${YELLOW}Applying Pi-specific modifications...${NC}"
    
    # Copy Pi-specific sensor manager if it exists
    if [ -f "$PI_DIR/pi/sensor_manager.py" ]; then
        cp "$PI_DIR/pi/sensor_manager.py" "$PI_DIR/software/control/sensor_manager.py"
        print_status "Pi sensor_manager.py applied" $?
    fi
    
    # Apply any other Pi-specific files
    if [ -d "$PI_DIR/pi" ]; then
        # Copy any other Pi-specific overrides
        for file in "$PI_DIR/pi"/*.py; do
            if [ -f "$file" ] && [ "$(basename $file)" != "sensor_manager.py" ]; then
                filename=$(basename "$file")
                cp "$file" "$PI_DIR/software/control/$filename" 2>/dev/null
            fi
        done
    fi
fi

# Update dependencies if requirements changed
if [ "$UPDATE_TYPE" = "code" ] || [ "$UPDATE_TYPE" = "all" ]; then
    if [ -f "$PI_DIR/requirements.txt" ]; then
        echo -e "\n${YELLOW}Checking Python dependencies...${NC}"
        cd "$PI_DIR"
        source venv/bin/activate
        pip install -q -r requirements.txt
        
        # Install Pi-specific requirements
        if [ -f "$PI_DIR/pi/requirements_pi.txt" ]; then
            pip install -q -r pi/requirements_pi.txt
        fi
        print_status "Dependencies updated" $?
    fi
fi

# Restart the system
echo -e "\n${YELLOW}Starting system...${NC}"
cd "$PI_DIR"
source venv/bin/activate
nohup python main.py > logs/system.log 2>&1 &
sleep 3

if pgrep -f "main.py" > /dev/null; then
    print_status "System started successfully" 0
else
    print_status "Failed to start system" 1
    echo "Check logs at: $PI_DIR/logs/system.log"
fi

echo -e "\n================================"
echo -e "${GREEN}Update Complete!${NC}"
echo "================================"
echo ""
echo "Backup saved to: $BACKUP_DIR"
echo "Access system at: http://192.168.1.184:5000"
echo ""
echo "To restore from backup:"
echo "  cp -r $BACKUP_DIR/* $PI_DIR/"