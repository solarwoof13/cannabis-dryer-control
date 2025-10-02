#!/usr/bin/env python3
"""
Standalone IR Transmitter Test
Location: tests/ir_testing/test_ir_transmitter.py

Tests the IR transmitter module independently before integration.
This does NOT integrate with your existing cannabis dryer code.

WIRING FOR IR TRANSMITTER (3 wires):
=====================================
DORHEA 38kHz IR Transmitter Module:
Pins labeled: DAT, VCC, GND

REQUIRED WIRING:
1. VCC  -> Connect to Raspberry Pi Pin 2 (5V) - Transmitter NEEDS 5V!
2. GND  -> Connect to Raspberry Pi Pin 9 (Ground)
3. DAT  -> Connect to Raspberry Pi Pin 36 (GPIO 16)

NOTE: Transmitter must use 5V for sufficient IR power.
      GPIO 16 is OUTPUT, so safe to connect directly (no voltage divider needed).
      Using GPIO 16 because GPIO 17 is used by dehum fan in main system.

Pin Layout Reference:
    Pin 1           [ ] [X] Pin 2  (5V)
    Pin 3           [ ] [ ] Pin 4
    Pin 5           [ ] [ ] Pin 6
    Pin 7           [ ] [ ] Pin 8
    Pin 9  (GND)    [X] [ ] Pin 10
    Pin 11          [ ] [ ] Pin 12
    ...
    Pin 35          [ ] [X] Pin 36 (GPIO16)
    
This test will send basic IR pulses. You can verify with:
- Your phone camera (you'll see the IR LED light up on camera)
- The IR receiver test (run both tests simultaneously)
"""

import RPi.GPIO as GPIO
import time
import sys

# Configuration
IR_TRANSMITTER_PIN = 16  # GPIO 16 (Physical Pin 36)

# Setup GPIO
def setup_gpio():
    """Initialize GPIO for IR transmitter"""
    try:
        GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
        GPIO.setup(IR_TRANSMITTER_PIN, GPIO.OUT)  # Set as output
        GPIO.output(IR_TRANSMITTER_PIN, GPIO.LOW)  # Start LOW (off)
        print("✅ GPIO initialized successfully")
        print(f"   Transmitting on GPIO {IR_TRANSMITTER_PIN}")
        return True
    except Exception as e:
        print(f"❌ GPIO setup failed: {e}")
        return False

def send_test_pulse(frequency=38000, duration_ms=100):
    """
    Send a basic IR pulse at specified frequency
    
    Args:
        frequency: IR carrier frequency in Hz (typically 38kHz for most remotes)
        duration_ms: Duration of pulse in milliseconds
    """
    # Calculate timing for the frequency
    period = 1.0 / frequency  # seconds per cycle
    half_period = period / 2  # half period for HIGH and LOW
    
    cycles = int(frequency * (duration_ms / 1000.0))
    
    print(f"\n📡 Sending IR pulse:")
    print(f"   Frequency: {frequency} Hz")
    print(f"   Duration: {duration_ms} ms")
    print(f"   Cycles: {cycles}")
    
    # Send the pulse by toggling GPIO at the frequency
    for _ in range(cycles):
        GPIO.output(IR_TRANSMITTER_PIN, GPIO.HIGH)
        time.sleep(half_period)
        GPIO.output(IR_TRANSMITTER_PIN, GPIO.LOW)
        time.sleep(half_period)
    
    print("   ✅ Pulse sent!")

def test_sequence():
    """Run a test sequence of IR pulses"""
    print("\n" + "="*60)
    print("IR TRANSMITTER TEST SEQUENCE")
    print("="*60)
    print("\nVERIFICATION METHODS:")
    print("1. Point phone camera at IR LED - you'll see it flash")
    print("2. Run test_ir_receiver.py to detect the signal")
    print("3. Point at AC remote receiver (if close enough)")
    print("="*60)
    
    try:
        # Send 5 test pulses with delays
        for i in range(1, 6):
            print(f"\n[Test {i}/5]")
            send_test_pulse(frequency=38000, duration_ms=100)
            print("   Waiting 1 second...")
            time.sleep(1)
        
        print("\n" + "="*60)
        print("✅ Test sequence complete!")
        print("="*60)
        print("\nDid you see the IR LED flash?")
        print("  - On phone camera: Should see purple/white flashes")
        print("  - With IR receiver test: Should detect pulses")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")

def interactive_test():
    """Interactive test - send pulse on command"""
    print("\n" + "="*60)
    print("INTERACTIVE IR TRANSMITTER TEST")
    print("="*60)
    print("\nPress ENTER to send an IR pulse, or 'q' to quit\n")
    
    pulse_count = 0
    
    try:
        while True:
            user_input = input("Press ENTER to send pulse (or 'q' to quit): ")
            
            if user_input.lower() == 'q':
                break
            
            pulse_count += 1
            print(f"\n[Pulse #{pulse_count}]")
            send_test_pulse(frequency=38000, duration_ms=100)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
    
    print(f"\n✅ Sent {pulse_count} pulses total")

def cleanup():
    """Clean up GPIO on exit"""
    try:
        GPIO.output(IR_TRANSMITTER_PIN, GPIO.LOW)  # Ensure OFF
        GPIO.cleanup()
        print("\n✅ GPIO cleaned up")
    except Exception as e:
        print(f"\n⚠️  Cleanup warning: {e}")

def main():
    """Main test function"""
    print("\n" + "="*60)
    print("STANDALONE IR TRANSMITTER TEST")
    print("="*60)
    print("\nWIRING CHECK:")
    print("  IR Transmitter VCC  -> Raspberry Pi Pin 2 (5V)")
    print("  IR Transmitter GND  -> Raspberry Pi Pin 9 (GND)")
    print("  IR Transmitter DAT -> Raspberry Pi Pin 36 (GPIO 16)")
    print("\n" + "="*60)
    
    response = input("\nIs wiring connected as shown above? (yes/no): ")
    if response.lower() != 'yes':
        print("\n⚠️  Please wire the IR transmitter first, then run this test again.")
        return
    
    # Setup GPIO
    if not setup_gpio():
        print("\n❌ Cannot proceed without GPIO. Exiting.")
        return
    
    try:
        # Choose test mode
        print("\n" + "="*60)
        print("SELECT TEST MODE:")
        print("  1. Automatic test sequence (5 pulses)")
        print("  2. Interactive mode (press ENTER to send)")
        print("="*60)
        
        choice = input("\nEnter choice (1 or 2): ")
        
        if choice == '1':
            test_sequence()
        elif choice == '2':
            interactive_test()
        else:
            print("\n⚠️  Invalid choice. Exiting.")
            
    finally:
        cleanup()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        cleanup()
        sys.exit(1)