#!/usr/bin/env python3
"""
Relay Test Script for Cannabis Dryer Control System
Tests each relay individually and verifies GPIO control
"""

import time
import sys

try:
    import RPi.GPIO as GPIO
    print("✓ RPi.GPIO imported successfully")
except ImportError:
    print("✗ RPi.GPIO not found - are you running this on a Raspberry Pi?")
    sys.exit(1)

# GPIO Pin Configuration
RELAY_PINS = {
    'DEHUMIDIFIER': 17,
    'HUMIDIFIER': 27,
    'ERV': 22,
    'SUPPLY_FAN': 23,
    'RETURN_FAN': 24,
    'HUMIDIFIER_FAN': 25,
    'SPARE_1': 20,
    'SPARE_2': 21
}

# Active LOW logic
RELAY_ON = GPIO.LOW   # 0V = Relay ON
RELAY_OFF = GPIO.HIGH  # 3.3V = Relay OFF

def setup_gpio():
    """Initialize GPIO pins"""
    print("\nInitializing GPIO...")
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    for name, pin in RELAY_PINS.items():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, RELAY_OFF)  # Start with everything OFF
        print(f"  {name}: GPIO {pin} initialized (OFF)")
    
    print("\n✓ All GPIO pins initialized\n")

def test_single_relay(name, pin):
    """Test a single relay"""
    print(f"Testing {name} (GPIO {pin})...")
    
    # Turn ON
    print(f"  Turning ON (GPIO = LOW)...", end="")
    GPIO.output(pin, RELAY_ON)
    time.sleep(2)
    print(" OK")
    
    # Turn OFF
    print(f"  Turning OFF (GPIO = HIGH)...", end="")
    GPIO.output(pin, RELAY_OFF)
    time.sleep(1)
    print(" OK")

def test_all_relays():
    """Test all relays sequentially"""
    print("=" * 50)
    print("TESTING ALL RELAYS SEQUENTIALLY")
    print("=" * 50)
    print("Each relay will turn ON for 2 seconds")
    print("Listen for clicking sounds from the relay board")
    input("\nPress Enter to start...")
    
    for name, pin in RELAY_PINS.items():
        test_single_relay(name, pin)
        print()

def test_all_on():
    """Turn all relays ON simultaneously"""
    print("=" * 50)
    print("TESTING ALL RELAYS ON")
    print("=" * 50)
    input("Press Enter to turn ALL relays ON...")
    
    for name, pin in RELAY_PINS.items():
        GPIO.output(pin, RELAY_ON)
        print(f"  {name}: ON")
    
    print("\nAll relays ON. Waiting 3 seconds...")
    time.sleep(3)
    
    print("Turning all relays OFF...")
    for name, pin in RELAY_PINS.items():
        GPIO.output(pin, RELAY_OFF)
        print(f"  {name}: OFF")

def interactive_test():
    """Interactive relay control"""
    print("=" * 50)
    print("INTERACTIVE RELAY CONTROL")
    print("=" * 50)
    print("\nCommands:")
    print("  1-8: Toggle relay 1-8")
    print("  a: All ON")
    print("  o: All OFF")
    print("  q: Quit")
    
    relay_list = list(RELAY_PINS.items())
    
    while True:
        cmd = input("\nCommand: ").lower()
        
        if cmd == 'q':
            break
        elif cmd == 'a':
            for name, pin in RELAY_PINS.items():
                GPIO.output(pin, RELAY_ON)
            print("All relays ON")
        elif cmd == 'o':
            for name, pin in RELAY_PINS.items():
                GPIO.output(pin, RELAY_OFF)
            print("All relays OFF")
        elif cmd.isdigit() and 1 <= int(cmd) <= 8:
            idx = int(cmd) - 1
            name, pin = relay_list[idx]
            current = GPIO.input(pin)
            new_state = RELAY_OFF if current == RELAY_ON else RELAY_ON
            GPIO.output(pin, new_state)
            state_text = "ON" if new_state == RELAY_ON else "OFF"
            print(f"{name}: {state_text}")
        else:
            print("Invalid command")

def main():
    """Main test program"""
    print("\n" + "=" * 50)
    print("CANNABIS DRYER RELAY TEST PROGRAM")
    print("=" * 50)
    
    try:
        setup_gpio()
        
        print("Select test mode:")
        print("1. Test all relays sequentially")
        print("2. Turn all relays ON")
        print("3. Interactive control")
        print("4. Full test (all modes)")
        
        choice = input("\nChoice (1-4): ")
        
        if choice == '1':
            test_all_relays()
        elif choice == '2':
            test_all_on()
        elif choice == '3':
            interactive_test()
        elif choice == '4':
            test_all_relays()
            test_all_on()
            interactive_test()
        else:
            print("Invalid choice")
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        print("\nCleaning up GPIO...")
        # Turn all relays OFF before cleanup
        for pin in RELAY_PINS.values():
            GPIO.output(pin, RELAY_OFF)
        GPIO.cleanup()
        print("GPIO cleanup complete")
        print("\n✓ Test program finished\n")

if __name__ == '__main__':
    main()