#!/usr/bin/env python3
"""
Standalone IR Receiver Test
Location: tests/ir_testing/test_ir_receiver.py

Tests the IR receiver module independently before integration.
This does NOT integrate with your existing cannabis dryer code.

WIRING FOR IR RECEIVER (3 wires):
===================================
DORHEA 38kHz IR Receiver Module:
Pins labeled: DAT, VCC, GND

RECOMMENDED WIRING (Start with 3.3V):
1. VCC  -> Connect to Raspberry Pi Pin 1 (3.3V) - Try this first!
2. GND  -> Connect to Raspberry Pi Pin 6 (Ground)
3. DAT  -> Connect to Raspberry Pi Pin 12 (GPIO 18)

NOTE: Module spec says 5V, but often works at 3.3V with reduced range.
      If 3.3V doesn't work, use Pin 2 (5V) with voltage divider!
      See IR_WIRING_GUIDE.md for voltage divider circuit.

Pin Layout Reference:
    Pin 1  (3.3V)   [X] [ ] Pin 2  (5V)
    Pin 3           [ ] [ ] Pin 4
    Pin 5           [ ] [X] Pin 6  (GND)
    Pin 7           [ ] [ ] Pin 8
    Pin 9           [ ] [ ] Pin 10
    Pin 11          [ ] [X] Pin 12 (GPIO 18)
    
This test will listen for IR signals and print them to the console.
"""

import RPi.GPIO as GPIO
import time
import sys

# Configuration
IR_RECEIVER_PIN = 18  # GPIO 18 (Physical Pin 12)

# Setup GPIO
def setup_gpio():
    """Initialize GPIO for IR receiver"""
    try:
        GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
        GPIO.setup(IR_RECEIVER_PIN, GPIO.IN)  # Set as input
        print("✅ GPIO initialized successfully")
        print(f"   Listening on GPIO {IR_RECEIVER_PIN}")
        return True
    except Exception as e:
        print(f"❌ GPIO setup failed: {e}")
        return False

def read_ir_signal():
    """
    Read raw IR signal (basic pulse detection)
    This is a simple test - just detects when signal goes HIGH/LOW
    """
    print("\n" + "="*60)
    print("IR RECEIVER TEST - Point remote at receiver and press buttons")
    print("="*60)
    print("Press Ctrl+C to exit\n")
    
    last_value = GPIO.input(IR_RECEIVER_PIN)
    pulse_count = 0
    
    try:
        while True:
            current_value = GPIO.input(IR_RECEIVER_PIN)
            
            # Detect state change (IR signal detected)
            if current_value != last_value:
                pulse_count += 1
                state = "HIGH" if current_value == 1 else "LOW"
                timestamp = time.strftime("%H:%M:%S")
                
                print(f"[{timestamp}] Pin {IR_RECEIVER_PIN}: {state} (pulse #{pulse_count})")
                
                # If we see pulses, IR receiver is working!
                if pulse_count == 1:
                    print("\n🎉 IR RECEIVER IS WORKING! Detected signal from remote.\n")
                
                last_value = current_value
            
            time.sleep(0.0001)  # 0.1ms delay for responsiveness
            
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print(f"Test stopped. Total pulses detected: {pulse_count}")
        if pulse_count > 0:
            print("✅ IR Receiver is working correctly!")
        else:
            print("⚠️  No IR signals detected. Check wiring:")
            print("   - VCC connected to 3.3V (Pin 1)?")
            print("   - GND connected to Ground (Pin 6)?")
            print("   - DATA connected to GPIO 18 (Pin 12)?")
            print("   - Is remote pointed at receiver?")
            print("   - Are batteries in remote good?")
        print("="*60)

def cleanup():
    """Clean up GPIO on exit"""
    try:
        GPIO.cleanup()
        print("\n✅ GPIO cleaned up")
    except Exception as e:
        print(f"\n⚠️  Cleanup warning: {e}")

def main():
    """Main test function"""
    print("\n" + "="*60)
    print("STANDALONE IR RECEIVER TEST")
    print("="*60)
    print("\nWIRING CHECK:")
    print("  IR Receiver VCC  -> Raspberry Pi Pin 1 (3.3V)")
    print("  IR Receiver GND  -> Raspberry Pi Pin 6 (GND)")
    print("  IR Receiver DAT -> Raspberry Pi Pin 12 (GPIO 18)")
    print("\n" + "="*60)
    
    response = input("\nIs wiring connected as shown above? (yes/no): ")
    if response.lower() != 'yes':
        print("\n⚠️  Please wire the IR receiver first, then run this test again.")
        return
    
    # Setup GPIO
    if not setup_gpio():
        print("\n❌ Cannot proceed without GPIO. Exiting.")
        return
    
    try:
        # Run the test
        read_ir_signal()
    finally:
        cleanup()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        cleanup()
        sys.exit(1)
    