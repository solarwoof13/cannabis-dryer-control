#!/bin/bash

# setup_ir_tests.sh
# Setup script for IR testing environment
# Run this on your Raspberry Pi to verify the test structure

echo "========================================"
echo "IR Testing Environment Setup"
echo "========================================"
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "⚠️  Warning: This doesn't appear to be a Raspberry Pi"
    echo "   IR testing requires Raspberry Pi hardware"
    read -p "Continue anyway? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Exiting..."
        exit 1
    fi
fi

# Navigate to project root
cd ~/cannabis-dryer || { echo "❌ Error: ~/cannabis-dryer directory not found"; exit 1; }

echo "📁 Creating test directory structure..."

# Create IR testing directory
mkdir -p tests/ir_testing
cd tests/ir_testing

echo "✅ Directory created: tests/ir_testing"
echo ""

# Create a simple GPIO test script
cat > gpio_test.py << 'EOF'
#!/usr/bin/env python3
"""
Quick GPIO test to verify RPi.GPIO is working
"""
import sys

try:
    import RPi.GPIO as GPIO
    print("✅ RPi.GPIO module is installed and working!")
    print(f"   Version: {GPIO.VERSION}")
    
    # Quick pin test
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    print("✅ GPIO initialized successfully")
    GPIO.cleanup()
    
    sys.exit(0)
    
except ImportError:
    print("❌ RPi.GPIO not installed!")
    print("\nInstall with:")
    print("  sudo apt-get update")
    print("  sudo apt-get install python3-rpi.gpio")
    sys.exit(1)
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
EOF

chmod +x gpio_test.py

echo "✅ gpio_test.py created"
echo ""

# Test GPIO installation
echo "🔧 Testing GPIO installation..."
python3 gpio_test.py

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "✅ Setup Complete!"
    echo "========================================"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Create test files in this directory:"
    echo "   - test_ir_receiver.py"
    echo "   - test_ir_transmitter.py"
    echo "   - IR_WIRING_GUIDE.md"
    echo "   - VISUAL_WIRING_DIAGRAM.txt"
    echo "   - IR_TESTING_README.md"
    echo ""
    echo "2. Wire your IR modules (see VISUAL_WIRING_DIAGRAM.txt)"
    echo ""
    echo "   IR Receiver:"
    echo "     VCC → Pin 1 (3.3V)"
    echo "     GND → Pin 6"
    echo "     DAT → Pin 12 (GPIO 18)"
    echo ""
    echo "   IR Transmitter:"
    echo "     VCC → Pin 2 (5V)"
    echo "     GND → Pin 9"
    echo "     DAT → Pin 36 (GPIO 16) ← Not Pin 11!"
    echo ""
    echo "3. Test receiver:"
    echo "   python3 test_ir_receiver.py"
    echo ""
    echo "4. Test transmitter:"
    echo "   python3 test_ir_transmitter.py"
    echo ""
    echo "Current directory:"
    pwd
    echo ""
else
    echo ""
    echo "========================================"
    echo "⚠️  Setup Complete (with warnings)"
    echo "========================================"
    echo ""
    echo "RPi.GPIO needs to be installed."
    echo "Install with:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install python3-rpi.gpio"
    echo ""
fi