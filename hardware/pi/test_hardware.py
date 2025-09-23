#!/usr/bin/env python3
"""
Hardware Test Script for Cannabis Dryer Control System
Tests all GPIO relays and I2C sensors
"""

import time
import sys
import RPi.GPIO as GPIO
import board
import adafruit_sht31d

print("=" * 60)
print("Cannabis Dryer Hardware Test")
print("=" * 60)

# GPIO Pin Configuration - must match main system
RELAY_PINS = {
    'DEHUMIDIFIER': 17,
    'HUMIDIFIER_SOLENOID': 27,
    'ERV': 22,
    'SUPPLY_FAN': 23,
    'RETURN_FAN': 24,
    'HUMIDIFIER_FAN': 25,
    'SPARE_1': 20,
    'SPARE_2': 21,
}

# Sensor addresses - must match main system
SENSOR_ADDRESSES = {
    'dry_zone_1': 0x44,
    'supply_duct': 0x45,
}

# Active LOW relay logic
RELAY_ON = GPIO.LOW
RELAY_OFF = GPIO.HIGH

# Test mode selection
print("\nSelect test mode:")
print("1. Test relays only")
print("2. Test sensors only")
print("3. Test everything")
print("4. Emergency stop test")
choice = input("Enter choice (1-4): ")

if choice in ['1', '3']:
    print("\n" + "=" * 40)
    print("TESTING RELAYS (Active LOW logic)")
    print("=" * 40)
    print("Each relay will turn ON for 2 seconds")
    print("Listen for clicking sounds from relay board")
    input("Press Enter to start relay test...")
    
    # Setup GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Initialize all pins as OFF (HIGH = OFF)
    for name, pin in RELAY_PINS.items():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, RELAY_OFF)
        print(f"Initialized {name} on GPIO {pin} (OFF)")
    
    time.sleep(1)
    
    # Test each relay
    for name, pin in RELAY_PINS.items():
        print(f"\nTesting {name} (GPIO {pin})...")
        print("  Turning ON (GPIO LOW)...")
        GPIO.output(pin, RELAY_ON)
        time.sleep(2)
        print("  Turning OFF (GPIO HIGH)...")
        GPIO.output(pin, RELAY_OFF)
        time.sleep(1)
    
    print("\nRelay test complete!")
    GPIO.cleanup()

if choice in ['2', '3']:
    print("\n" + "=" * 40)
    print("TESTING I2C SENSORS (SHT31)")
    print("=" * 40)
    
    # First check what's on the I2C bus
    import subprocess
    print("\nScanning I2C bus for devices...")
    result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True)
    print(result.stdout)
    
    print("\nAttempting to read SHT31 sensors...")
    
    # Initialize I2C
    try:
        i2c = board.I2C()
        sensors_found = 0
        sensors_failed = 0
        
        for name, address in SENSOR_ADDRESSES.items():
            try:
                print(f"\n{name} (0x{address:02X}):")
                sensor = adafruit_sht31d.SHT31D(i2c, address=address)
                
                # Try multiple reads to ensure stability
                readings = []
                for i in range(3):
                    temp_c = sensor.temperature
                    humidity = sensor.relative_humidity
                    temp_f = (temp_c * 9/5) + 32
                    readings.append((temp_f, humidity))
                    time.sleep(0.1)
                
                # Average the readings
                avg_temp = sum(r[0] for r in readings) / 3
                avg_hum = sum(r[1] for r in readings) / 3
                
                print(f"  Temperature: {avg_temp:.1f}°F ({(avg_temp-32)*5/9:.1f}°C)")
                print(f"  Humidity: {avg_hum:.1f}%")
                
                # Calculate VPD
                temp_c = (avg_temp - 32) * 5/9
                svp = 0.61078 * (2.718281828 ** ((17.269 * temp_c) / (237.3 + temp_c)))
                avp = svp * (avg_hum / 100)
                vpd = svp - avp
                print(f"  VPD: {vpd:.2f} kPa")
                
                sensors_found += 1
                
            except Exception as e:
                print(f"  ERROR: {str(e)}")
                sensors_failed += 1
        
        print("\n" + "=" * 40)
        print(f"Sensor Summary: {sensors_found} found, {sensors_failed} failed")
        
    except Exception as e:
        print(f"ERROR: Failed to initialize I2C: {str(e)}")
        print("Make sure I2C is enabled in raspi-config")

if choice == '4':
    print("\n" + "=" * 40)
    print("EMERGENCY STOP TEST")
    print("=" * 40)
    print("This will:")
    print("1. Turn ON all relays")
    print("2. Wait 3 seconds")
    print("3. Execute emergency stop (turn OFF all)")
    input("Press Enter to start...")
    
    # Setup GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Initialize and turn ON all relays
    print("\nTurning ON all relays...")
    for name, pin in RELAY_PINS.items():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, RELAY_ON)
        print(f"  {name} ON")
    
    print("\nAll relays ON. Waiting 3 seconds...")
    time.sleep(3)
    
    print("\nEXECUTING EMERGENCY STOP!")
    for name, pin in RELAY_PINS.items():
        GPIO.output(pin, RELAY_OFF)
        print(f"  {name} OFF")
    
    print("\nEmergency stop complete!")
    GPIO.cleanup()

print("\n" + "=" * 60)
print("Hardware test completed!")
print("=" * 60)