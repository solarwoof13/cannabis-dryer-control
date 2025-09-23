#!/usr/bin/env python3
"""
Sensor Manager for SHT31 Temperature/Humidity Sensors
"""

import time
import logging
from datetime import datetime
from typing import Dict, Optional
import board
import busio
import adafruit_sht31d

logger = logging.getLogger(__name__)

class SensorManager:
    """Manages SHT31 sensors on I2C bus"""
    
    # Your actual sensor addresses
    SENSOR_ADDRESSES = {
        'dry_room_1': 0x44,
        'supply_duct': 0x45,
        # Add more when you get them configured
        # 'dry_room_2': 0x39,
        # 'dry_room_3': 0x3A,
        # 'dry_room_4': 0x3B,
        # 'utility_room': 0x3C,
    }
    
    def __init__(self):
        """Initialize I2C and sensors"""
        self.sensors = {}
        self.last_readings = {}
        self.initialize_sensors()
    
    def initialize_sensors(self):
        """Initialize all configured sensors"""
        try:
            # Create I2C bus
            i2c = busio.I2C(board.SCL, board.SDA)
            
            # Initialize each sensor
            for name, address in self.SENSOR_ADDRESSES.items():
                try:
                    sensor = adafruit_sht31d.SHT31D(i2c, address=address)
                    self.sensors[name] = sensor
                    logger.info(f"Initialized sensor {name} at address 0x{address:02X}")
                except Exception as e:
                    logger.error(f"Failed to initialize sensor {name} at 0x{address:02X}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize I2C bus: {e}")
            raise
    
    def read_sensor(self, sensor_id: str) -> Optional[Dict]:
        """Read a single sensor"""
        if sensor_id not in self.sensors:
            logger.warning(f"Sensor {sensor_id} not found")
            return None
            
        try:
            sensor = self.sensors[sensor_id]
            temp_c = sensor.temperature
            humidity = sensor.relative_humidity
            
            # Convert to Fahrenheit
            temp_f = (temp_c * 9/5) + 32
            
            reading = {
                'sensor_id': sensor_id,
                'temperature': temp_f,
                'humidity': humidity,
                'temperature_c': temp_c,
                'timestamp': datetime.now(),
                'status': 'ok'
            }
            
            self.last_readings[sensor_id] = reading
            return reading
            
        except Exception as e:
            logger.error(f"Error reading sensor {sensor_id}: {e}")
            return {
                'sensor_id': sensor_id,
                'temperature': 0,
                'humidity': 0,
                'temperature_c': 0,
                'timestamp': datetime.now(),
                'status': 'error',
                'error': str(e)
            }
    
    def read_all_sensors(self) -> Dict:
        """Read all configured sensors"""
        readings = {}
        for sensor_id in self.sensors.keys():
            reading = self.read_sensor(sensor_id)
            if reading:
                readings[sensor_id] = reading
        return readings
    
    def get_average_readings(self) -> Dict:
        """Get average of all working sensors"""
        all_readings = self.read_all_sensors()
        working_readings = [r for r in all_readings.values() if r['status'] == 'ok']
        
        if not working_readings:
            return {'temperature': 0, 'humidity': 0, 'sensor_count': 0}
        
        avg_temp = sum(r['temperature'] for r in working_readings) / len(working_readings)
        avg_humidity = sum(r['humidity'] for r in working_readings) / len(working_readings)
        
        return {
            'temperature': avg_temp,
            'humidity': avg_humidity,
            'sensor_count': len(working_readings)
        }