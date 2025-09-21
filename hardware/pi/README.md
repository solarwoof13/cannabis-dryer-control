# Raspberry Pi Hardware Integration

This folder contains all Raspberry Pi-specific hardware interface code for the Cannabis Drying Control System.

## Hardware Components

### Sensors (I2C)
- 6x Temperature/Humidity sensors on SparkFun Qwiic bus
- I2C addresses: 0x38-0x3D
- 100ft cable run capability

### Relay Control (GPIO)
- Dehumidifier: GPIO 17 (Power relay)
- Humidifier Solenoid: GPIO 27 (Control relay)
- ERV: GPIO 22 (Control relay)
- Supply Fan: GPIO 23 (Power relay)
- Return Fan: GPIO 24 (Power relay)

### IR Control
- Mini-split AC control via IR blaster
- May require Arduino bridge for reliable IR transmission

## Installation on Raspberry Pi
```bash
# Enable I2C
sudo raspi-config
# Select: Interface Options -> I2C -> Enable

# Install system dependencies
sudo apt-get update
sudo apt-get install python3-pip python3-venv i2c-tools

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Pi-specific requirements
pip install -r hardware/pi/requirements_pi.txt