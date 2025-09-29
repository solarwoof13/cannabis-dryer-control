#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

print("Testing GPIO relay control...")

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Test each relay
relays = {
    'DEHUM': 17,
    'HUM': 27,
    'ERV': 22,
    'SUPPLY': 23,
    'RETURN': 24
}

for name, pin in relays.items():
    print(f"Testing {name} on GPIO {pin}")
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # ON
    print("  ON - you should hear a click")
    time.sleep(1)
    GPIO.output(pin, GPIO.HIGH)  # OFF
    print("  OFF")
    time.sleep(1)

GPIO.cleanup()
print("Test complete")