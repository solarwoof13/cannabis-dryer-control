#!/bin/bash

echo "Cannabis Dryer Pi Setup"
echo "======================="

# Update system
sudo apt update
sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3-pip python3-venv git redis-server
sudo apt install -y python3-dev python3-smbus i2c-tools

# Enable I2C
sudo raspi-config nonint do_i2c 0

# Create project directory
mkdir -p ~/cannabis-dryer/logs

# Clone repository
cd ~
git clone https://github.com/solarwoof13/cannabis-dryer-control.git cannabis-dryer

# Copy Pi-specific files
cp ~/cannabis-dryer/pi/sensor_manager.py ~/cannabis-dryer/software/control/

# Create virtual environment
cd ~/cannabis-dryer
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt
pip install -r pi/requirements_pi.txt

echo "Setup complete! Run with:"
echo "cd ~/cannabis-dryer && source venv/bin/activate && python main.py"