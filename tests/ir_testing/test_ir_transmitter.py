#!/usr/bin/env python3
"""
IR Transmitter Module for Mini-Split Control
Location: ~/cannabis-dryer/software/control/ir_transmitter.py

Transmits IR codes recorded in ~/aciq_codes/ directory
Uses GPIO 16 (Pin 36) for transmission
"""

import RPi.GPIO as GPIO
import time
import os
import logging

logger = logging.getLogger(__name__)

class IRTransmitter:
    """
    IR code transmitter for mini-split AC control
    Reads and transmits IR codes from file
    """
    
    def __init__(self, gpio_pin=16, codes_dir="/home/mikejames/aciq_codes"):
        """
        Initialize IR transmitter
        
        Args:
            gpio_pin: GPIO pin number (BCM) for IR LED (default: 16)
            codes_dir: Directory containing IR code files
        """
        self.gpio_pin = gpio_pin
        self.codes_dir = codes_dir
        self.carrier_freq = 38000  # 38kHz carrier for most AC remotes
        
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        
        logger.info(f"IR Transmitter initialized on GPIO {self.gpio_pin}")
        
    def parse_ir_file(self, filename):
        """
        Parse IR timing file and extract pulse/space data
        
        Args:
            filename: Path to IR code file
            
        Returns:
            list: List of (pulse_time, space_time) tuples in microseconds
        """
        filepath = os.path.join(self.codes_dir, filename)
        
        if not os.path.exists(filepath):
            logger.error(f"IR code file not found: {filepath}")
            return None
            
        timings = []
        
        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
                
            # Skip first line if it's garbage data (starts with huge number)
            start_line = 0
            if lines and lines[0].strip().startswith('+') and int(lines[0].strip().split()[0][1:]) > 100000:
                start_line = 1
                
            # Parse only first 2 lines of actual IR data (skip long gap on line 3)
            for line_num in range(start_line, min(start_line + 2, len(lines))):
                line = lines[line_num].strip()
                if not line:
                    continue
                    
                # Parse pulse/space pairs
                tokens = line.split()
                for token in tokens:
                    token = token.strip()
                    if token.startswith('+'):
                        # Pulse (ON time)
                        timings.append((int(token[1:]), 0))  # Store pulse, space added next
                    elif token.startswith('-'):
                        # Space (OFF time) - add to last pulse
                        if timings:
                            pulse, _ = timings[-1]
                            timings[-1] = (pulse, int(token[1:]))
                            
            logger.info(f"Parsed {len(timings)} pulse/space pairs from {filename}")
            return timings
            
        except Exception as e:
            logger.error(f"Error parsing IR file {filename}: {e}")
            return None
    
    def send_carrier_pulse(self, duration_us):
        """
        Send IR carrier pulse for specified duration
        
        Args:
            duration_us: Pulse duration in microseconds
        """
        # Calculate timing for 38kHz carrier
        period_us = 1000000.0 / self.carrier_freq  # Period in microseconds
        half_period = period_us / 2.0 / 1000000.0  # Half period in seconds
        
        cycles = int(duration_us / period_us)
        
        # Send carrier by toggling GPIO
        for _ in range(cycles):
            GPIO.output(self.gpio_pin, GPIO.HIGH)
            time.sleep(half_period)
            GPIO.output(self.gpio_pin, GPIO.LOW)
            time.sleep(half_period)
    
    def send_code(self, filename):
        """
        Transmit IR code from file
        
        Args:
            filename: Name of IR code file (e.g., 'auto_70_autofan.txt')
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Transmitting IR code: {filename}")
        
        # Parse the file
        timings = self.parse_ir_file(filename)
        if not timings:
            return False
            
        try:
            # Send each pulse/space pair
            for pulse_us, space_us in timings:
                # Send modulated pulse
                if pulse_us > 0:
                    self.send_carrier_pulse(pulse_us)
                
                # Send space (off time)
                if space_us > 0:
                    GPIO.output(self.gpio_pin, GPIO.LOW)
                    time.sleep(space_us / 1000000.0)  # Convert to seconds
            
            # Ensure LED is off at end
            GPIO.output(self.gpio_pin, GPIO.LOW)
            
            logger.info(f"Successfully transmitted {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error transmitting {filename}: {e}")
            GPIO.output(self.gpio_pin, GPIO.LOW)
            return False
    
    def power_on(self):
        """Turn on AC with default settings"""
        return self.send_code("power_on_default.txt")
    
    def power_off(self):
        """Turn off AC"""
        return self.send_code("power_off.txt")
    
    def set_temp_auto(self, temp_f):
        """
        Set AC to specific temperature in AUTO mode
        
        Args:
            temp_f: Target temperature in Fahrenheit
            
        Returns:
            bool: True if successful
        """
        # Map temperature to available code files
        filename = f"auto_{int(temp_f)}_autofan.txt"
        return self.send_code(filename)
    
    def cleanup(self):
        """Clean up GPIO"""
        GPIO.cleanup()
        logger.info("IR Transmitter cleaned up")


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("IR Transmitter Test")
    print("="*60)
    print("\nThis will test IR transmission using your recorded codes.")
    print("Point the IR transmitter at your mini-split AC.\n")
    
    try:
        # Create transmitter
        ir = IRTransmitter()
        
        # Test menu
        while True:
            print("\n" + "="*60)
            print("TEST MENU:")
            print("  1. Power ON (default)")
            print("  2. Power OFF")
            print("  3. Set to 70°F AUTO")
            print("  4. Set to 68°F AUTO")
            print("  5. Set to 65°F AUTO")
            print("  6. Custom temperature")
            print("  q. Quit")
            print("="*60)
            
            choice = input("\nEnter choice: ").strip().lower()
            
            if choice == 'q':
                break
            elif choice == '1':
                print("\n📡 Sending POWER ON...")
                ir.power_on()
            elif choice == '2':
                print("\n📡 Sending POWER OFF...")
                ir.power_off()
            elif choice == '3':
                print("\n📡 Setting to 70°F AUTO...")
                ir.set_temp_auto(70)
            elif choice == '4':
                print("\n📡 Setting to 68°F AUTO...")
                ir.set_temp_auto(68)
            elif choice == '5':
                print("\n📡 Setting to 65°F AUTO...")
                ir.set_temp_auto(65)
            elif choice == '6':
                temp = input("Enter temperature (62-75): ")
                try:
                    temp_f = int(temp)
                    if 62 <= temp_f <= 75:
                        print(f"\n📡 Setting to {temp_f}°F AUTO...")
                        ir.set_temp_auto(temp_f)
                    else:
                        print("Temperature out of range!")
                except ValueError:
                    print("Invalid temperature!")
            else:
                print("Invalid choice!")
            
            time.sleep(1)
        
        print("\nCleaning up...")
        ir.cleanup()
        print("Done!")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        GPIO.cleanup()
    except Exception as e:
        print(f"\nError: {e}")
        GPIO.cleanup()