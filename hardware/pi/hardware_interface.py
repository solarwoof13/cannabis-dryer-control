#!/usr/bin/env python3
"""
Raspberry Pi Hardware Interface for Cannabis Dryer Control
This replaces SimulationMode when running on actual Pi hardware
"""

import time
import logging
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ahtx0

logger = logging.getLogger(__name__)

class GPIOController:
    """Controls relays via GPIO pins"""
    
    def __init__(self):
        # GPIO pin assignments
        self.pins = {
            'dehum': 17,           # Channel 1 - Dehumidifier power
            'hum_solenoid': 27,    # Channel 2 - Humidifier water solenoid  
            'erv': 22,             # Channel 3 - ERV control
            'supply_fan': 23,      # Channel 4 - Supply fan
            'return_fan': 24,      # Channel 5 - Return fan
            'hum_fan': 25         # Channel 6 - Humidifier fan
        }
        
        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup all pins as outputs (HIGH = OFF for most relays)
        for device, pin in self.pins.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)  # Start with everything OFF
            logger.info(f"GPIO {pin} configured for {device}")
    
    def set_device(self, device, state):
        """Control a device via GPIO relay
        Args:
            device: Device name from self.pins
            state: 'ON' or 'OFF'
        """
        if device not in self.pins:
            logger.error(f"Unknown device: {device}")
            return False
        
        pin = self.pins[device]
        # Most relays are active LOW (LOW = ON, HIGH = OFF)
        gpio_state = GPIO.LOW if state == 'ON' else GPIO.HIGH
        
        GPIO.output(pin, gpio_state)
        logger.info(f"{device} set to {state} (GPIO {pin} = {gpio_state})")
        return True
    
    def cleanup(self):
        """Clean up GPIO on exit"""
        logger.info("Cleaning up GPIO")
        GPIO.cleanup()


class I2CSensorReader:
    """Read temperature/humidity sensors via I2C"""
    
    def __init__(self):
        # Initialize I2C bus
        self.i2c = busio.I2C(board.SCL, board.SDA)
        
        # Sensor addresses for SparkFun Qwiic sensors
        # Adjust these based on your actual sensor addresses
        self.sensor_addresses = {
            'dry_1': 0x38,
            'dry_2': 0x39,
            'dry_3': 0x3A,
            'dry_4': 0x3B,
            'air_room': 0x3C,
            'supply_duct': 0x3D
        }
        
        # Initialize sensors
        self.sensors = {}
        for name, address in self.sensor_addresses.items():
            try:
                sensor = adafruit_ahtx0.AHTx0(self.i2c, address=address)
                self.sensors[name] = sensor
                logger.info(f"Initialized sensor {name} at address 0x{address:02X}")
            except Exception as e:
                logger.error(f"Failed to initialize sensor {name}: {e}")
    
    def read_sensor(self, sensor_id):
        """Read a specific sensor
        Returns:
            tuple: (temperature_f, humidity_percent) or (None, None) on error
        """
        if sensor_id not in self.sensors:
            logger.error(f"Sensor {sensor_id} not found")
            return None, None
        
        try:
            sensor = self.sensors[sensor_id]
            temp_c = sensor.temperature
            humidity = sensor.relative_humidity
            
            # Convert to Fahrenheit
            temp_f = (temp_c * 9/5) + 32
            
            return temp_f, humidity
            
        except Exception as e:
            logger.error(f"Error reading sensor {sensor_id}: {e}")
            return None, None
    
    def read_all_sensors(self):
        """Read all sensors and return dict of readings"""
        readings = {}
        for sensor_id in self.sensors.keys():
            temp, humidity = self.read_sensor(sensor_id)
            if temp is not None:
                readings[sensor_id] = {
                    'temperature': temp,
                    'humidity': humidity
                }
        return readings


class IRController:
    """Control mini-split via IR commands"""
    
    def __init__(self):
        # This might need an Arduino bridge for reliable IR
        # Or use LIRC (Linux Infrared Remote Control)
        logger.info("IR Controller initialized")
        self.current_setpoint = 68
    
    def set_temperature(self, temp_f):
        """Send temperature setpoint to mini-split via IR"""
        self.current_setpoint = temp_f
        temp_c = int((temp_f - 32) * 5/9)
        
        # TODO: Implement actual IR transmission
        # Options:
        # 1. Use LIRC: subprocess.run(['irsend', 'SEND_ONCE', 'mini_split', f'temp_{temp_c}'])
        # 2. Use Arduino over serial
        # 3. Use IR LED directly on GPIO
        
        logger.info(f"IR: Set mini-split to {temp_f}°F ({temp_c}°C)")
        return True


class HardwareInterface:
    """Main hardware interface combining GPIO, I2C, and IR"""
    
    def __init__(self, controller):
        self.controller = controller
        self.gpio = GPIOController()
        self.sensors = I2CSensorReader()
        self.ir = IRController()
        
        logger.info("Hardware interface initialized")
    
    def update_sensors(self):
        """Read all sensors and update controller"""
        readings = self.sensors.read_all_sensors()
        
        for sensor_id, data in readings.items():
            self.controller.update_sensor_reading(
                sensor_id,
                data['temperature'],
                data['humidity']
            )
    
    def update_equipment(self):
        """Update physical equipment based on controller states"""
        from software.control.vpd_controller import EquipmentState
        
        for device, state in self.controller.equipment_states.items():
            if device == 'mini_split':
                # Handle mini-split via IR
                self.ir.set_temperature(self.controller.mini_split_setpoint)
            elif device == 'hum_fan':
                # Humidifier fan is always on, skip
                continue
            elif device in self.gpio.pins:
                # Handle GPIO-controlled devices
                self.gpio.set_device(device, state.value)
    
    def run(self):
        """Main hardware control loop"""
        logger.info("Starting hardware interface loop")
        
        try:
            while True:
                # Read sensors
                self.update_sensors()
                
                # Update equipment
                self.update_equipment()
                
                # Wait before next cycle
                time.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("Hardware interface stopped")
        finally:
            self.gpio.cleanup()


if __name__ == "__main__":
    # Test hardware interface
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Hardware Interface")
    print("-" * 40)
    
    # Test GPIO
    gpio = GPIOController()
    print("Testing relays...")
    for device in gpio.pins.keys():
        print(f"  {device}: ON")
        gpio.set_device(device, 'ON')
        time.sleep(0.5)
        gpio.set_device(device, 'OFF')
        time.sleep(0.5)
    
    # Test I2C
    print("\nTesting sensors...")
    sensors = I2CSensorReader()
    readings = sensors.read_all_sensors()
    for sensor_id, data in readings.items():
        print(f"  {sensor_id}: {data['temperature']:.1f}°F, {data['humidity']:.1f}%")
    
    # Cleanup
    gpio.cleanup()
    print("\nHardware test complete")