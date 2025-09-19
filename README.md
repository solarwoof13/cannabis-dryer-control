# cannabis-dryer-control
Cannabis Dryer Control System
A Raspberry Pi-based environmental control system for precise cannabis drying and curing in a 40' shipping container using VPD (Vapor Pressure Deficit) control.
🎯 Project Overview
This system mimics precision drying technology (like Cannatrol) but uses open-source implementation focused on VPD control to prevent case hardening and preserve terpenes.
Key Features

Precision VPD Control: Touch-based setpoint adjustment
Multi-Zone Sensing: 6 temperature/humidity sensors
Automated Equipment Control: Mini-split, dehumidifier, humidifier, ERV, fans
Touch Interface: Optimized for 7" Raspberry Pi display
Security Focused: Industry-grade security practices

🏗️ Hardware Setup
Control System

Raspberry Pi 4 Model B with 7" touchscreen (1024x600)
I2C Sensor Network via SparkFun Qwiic bus (100' range)

Equipment Controlled

Mini-Split A/C (IR control, may need Arduino bridge)
Dehumidifier (Power relay)
Humidifier (Relay control)
ERV (Energy Recovery Ventilator - Relay control)
Exhaust Fan (400 CFM - Power relay)
Supply Fan (400 CFM - Power relay)

Sensor Layout

Air Room: 1 sensor (equipment area)
Drying Room: 4 sensors (monitoring zones)
Supply Duct: 1 sensor

🚀 Quick Start
Installation
bashgit clone https://github.com/yourusername/cannabis-dryer-control.git
cd cannabis-dryer-control
pip install -r requirements.txt
python main.py
Development
bash# Test the system
python main.py

# View logs
tail -f logs/dryer_control.log
📊 Drying Process
VPD Targets

Early Drying: 1.0-1.2 kPa (4 days)
Curing: 0.4-0.6 kPa (4 days)
Target Water Activity: 0.62

Safety Limits

Temperature: 60-75°F
Humidity: 55-65% RH
VPD: 0.3-2.0 kPa (safety range)

🎛️ User Interface
The touch interface provides:

Central VPD Gauge with swipe control
Real-time sensor readings from all 6 sensors
Equipment status indicators
Alert system for out-of-range conditions
Emergency stop functionality

📁 Project Structure
cannabis-dryer-control/
├── hardware/          # Wiring diagrams, specs
├── software/
│   ├── gui/           # Web interface files
│   ├── control/       # Python control modules
│   ├── arduino/       # Arduino code (if needed)
│   └── config/        # Configuration files
├── docs/              # Documentation
├── tests/             # Test files
├── logs/              # System logs
├── main.py            # Application entry point
└── requirements.txt   # Python dependencies
🔧 Development Status

✅ Project structure created
✅ Basic GUI interface designed
🔄 Hardware integration modules
🔄 VPD calculation engine
🔄 Equipment control system
🔄 Alert and safety systems
🔄 Web interface backend

📜 License
MIT License - see LICENSE file for details.
⚠️ Legal Notice
This system is for educational and personal use. Ensure compliance with local laws and regulations regarding cannabis cultivation and processing.

Building precise environmental control for better cannabis quality 🌱