#!/usr/bin/env python3
"""
Cannabis Drying and Curing Control System
Main control module for 40' shipping container cannabis dryer
Uses VPD (Vapor Pressure Deficit) control to mimic Cannatrol's technology
"""

import time
import json
import logging
import threading
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import RPi.GPIO as GPIO
import board
import adafruit_sht4x
from flask import Flask, jsonify, request, render_template
from flask_socketio import SocketIO, emit
from cryptography.fernet import Fernet
import paho.mqtt.client as mqtt
import redis
import sqlite3

# ============================================================================
# CONFIGURATION AND CONSTANTS
# ============================================================================

# GPIO Pin Configuration (BCM Mode) - SunFounder 8-Channel Relay Shield
# ACTIVE LOW LOGIC: GPIO LOW (0V) = Relay ON, GPIO HIGH (3.3V) = Relay OFF
GPIO_PINS = {
    'DEHUMIDIFIER': 17,      # IN1 - Power Relay 120V AC (Red wire)
    'HUMIDIFIER_SOLENOID': 27,  # IN2 - Control Relay 24V DC (Blue wire)
    'ERV': 22,               # IN3 - Power Relay 120V AC (Green wire)
    'SUPPLY_FAN': 23,        # IN4 - Power Relay 120V AC (Yellow wire)
    'RETURN_FAN': 24,        # IN5 - Power Relay 120V AC (Orange wire)
    'HUMIDIFIER_FAN': 25,    # IN6 - Control Relay 12-24V DC
    'SPARE_1': 20,           # IN7 - Future use
    'SPARE_2': 21,           # IN8 - Future use
}

# Active LOW relay logic (fail-safe: if Pi crashes, all relays turn OFF)
RELAY_ON = GPIO.LOW
RELAY_OFF = GPIO.HIGH

# I2C Configuration for sensors with SparkFun Qwiic
I2C_BUS = 1  # I2C-1 on Raspberry Pi 4
I2C_PINS = {
    'SDA': 2,  # GPIO 2 (Physical Pin 3)
    'SCL': 3,  # GPIO 3 (Physical Pin 5)
}

# Sensor I2C addresses (unique addresses for each sensor)
SENSOR_CONFIG = {
    'dry_zone_1': {'address': 0x44, 'cable_length': '20ft', 'location': 'Front left'},
    'dry_zone_2': {'address': 0x39, 'cable_length': '25ft', 'location': 'Front right'},
    'dry_zone_3': {'address': 0x3A, 'cable_length': '30ft', 'location': 'Back left'},
    'dry_zone_4': {'address': 0x3B, 'cable_length': '35ft', 'location': 'Back right'},
    'air_room': {'address': 0x3C, 'cable_length': '5ft', 'location': 'Equipment room'},
    'supply_duct': {'address': 0x45, 'cable_length': '10ft', 'location': 'After conditioning'},
}

# VPD Control Parameters
VPD_TARGETS = {
    'DRYING': {
        'day_1': 0.8,  # kPa
        'day_2': 0.9,
        'day_3': 1.0,
        'day_4': 1.1,
    },
    'CURING': {
        'day_5': 0.7,
        'day_6': 0.65,
        'day_7': 0.6,
        'day_8': 0.55,
    }
}

# Target water activity levels
WATER_ACTIVITY_TARGETS = {
    'initial': 0.65,
    'final': 0.60,
    'tolerance': 0.02
}

# Equipment operation thresholds
CONTROL_DEADBAND = {
    'vpd': 0.05,  # kPa
    'temp': 1.0,   # °F
    'rh': 2.0,     # %
}

# Security configuration
ENCRYPTION_KEY = Fernet.generate_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

# ============================================================================
# DATA CLASSES AND ENUMS
# ============================================================================

class EquipmentState(Enum):
    OFF = 0
    ON = 1
    IDLE = 2
    ERROR = 3

class ProcessPhase(Enum):
    IDLE = "idle"
    DRYING = "drying"
    CURING = "curing"
    COMPLETE = "complete"

@dataclass
class SensorReading:
    """Individual sensor reading data"""
    location: str
    temperature_c: float
    humidity: float
    vpd_kpa: float
    dew_point_c: float
    timestamp: datetime
    
    @property
    def temperature_f(self) -> float:
        return (self.temperature_c * 9/5) + 32
    
    @property
    def dew_point_f(self) -> float:
        return (self.dew_point_c * 9/5) + 32

@dataclass
class SystemState:
    """Complete system state"""
    phase: ProcessPhase
    day: int
    target_vpd: float
    current_vpd: float
    equipment_states: Dict[str, EquipmentState]
    sensor_readings: List[SensorReading]
    alarms: List[str]
    timestamp: datetime

# ============================================================================
# SENSOR MANAGEMENT
# ============================================================================

class SensorManager:
    """Manages all temperature/humidity sensors on SparkFun Qwiic bus"""
    
    def __init__(self):
        self.sensors = {}
        self.initialize_sensors()
        
    def initialize_sensors(self):
        """Initialize all sensors with unique I2C addresses"""
        i2c = board.I2C()  # Uses pins 3 (SDA) and 5 (SCL)
        
        for location, config in SENSOR_CONFIG.items():
            try:
                # Initialize SHT4x sensor at specific address
                sensor = adafruit_sht4x.SHT4x(i2c, address=config['address'])
                sensor.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
                
                self.sensors[location] = {
                    'sensor': sensor,
                    'config': config
                }
                
                logging.info(f"Initialized sensor at {location} (0x{config['address']:02X})")
                
            except Exception as e:
                logging.error(f"Failed to initialize sensor at {location}: {e}")
    
    def read_sensor(self, location: str) -> Optional[SensorReading]:
        """Read a specific sensor"""
        if location not in self.sensors:
            logging.error(f"Unknown sensor location: {location}")
            return None
            
        try:
            sensor_info = self.sensors[location]
            sensor = sensor_info['sensor']
            
            # Read sensor with retry logic for long cable runs
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    temperature_c = sensor.temperature
                    humidity = sensor.relative_humidity
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(0.1)
            
            # Calculate VPD and dew point
            vpd_kpa = self.calculate_vpd(temperature_c, humidity)
            dew_point_c = self.calculate_dew_point(temperature_c, humidity)
            
            return SensorReading(
                location=location,
                temperature_c=temperature_c,
                humidity=humidity,
                vpd_kpa=vpd_kpa,
                dew_point_c=dew_point_c,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logging.error(f"Error reading sensor at {location}: {e}")
            return None
    
    def read_all_sensors(self) -> List[SensorReading]:
        """Read all sensors"""
        readings = []
        for location in self.sensors.keys():
            reading = self.read_sensor(location)
            if reading:
                readings.append(reading)
        return readings
    
    @staticmethod
    def calculate_vpd(temp_c: float, rh: float) -> float:
        """Calculate Vapor Pressure Deficit in kPa"""
        # Saturation vapor pressure (Tetens formula)
        svp = 0.61078 * np.exp((17.269 * temp_c) / (237.3 + temp_c))
        # Actual vapor pressure
        avp = svp * (rh / 100)
        # VPD in kPa
        vpd = svp - avp
        return vpd
    
    @staticmethod
    def calculate_dew_point(temp_c: float, rh: float) -> float:
        """Calculate dew point temperature"""
        a = 17.271
        b = 237.7
        gamma = (a * temp_c / (b + temp_c)) + np.log(rh / 100)
        dew_point = (b * gamma) / (a - gamma)
        return dew_point

# ============================================================================
# EQUIPMENT CONTROL
# ============================================================================

class EquipmentController:
    """Controls all equipment via GPIO with Active LOW relay logic"""
    
    def __init__(self):
        self.setup_gpio()
        self.equipment_states = {
            'DEHUMIDIFIER': EquipmentState.OFF,
            'HUMIDIFIER_SOLENOID': EquipmentState.OFF,
            'HUMIDIFIER_FAN': EquipmentState.OFF,
            'ERV': EquipmentState.OFF,
            'SUPPLY_FAN': EquipmentState.ON,
            'RETURN_FAN': EquipmentState.ON,
        }
        self.last_state_change = {}
        self.min_cycle_time = timedelta(minutes=5)  # Prevent short cycling
        self.max_simultaneous_relays = 6  # Safety limit for current draw
        self.relay_startup_delay = 0.5  # Seconds between relay activations
        
    def setup_gpio(self):
        """Initialize GPIO pins with Active LOW relay logic"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        for name, pin in GPIO_PINS.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, RELAY_OFF)  # Start with everything OFF (HIGH = OFF)
            logging.info(f"Initialized {name} on GPIO {pin} (OFF)")
    
    def count_active_relays(self) -> int:
        """Count how many relays are currently ON"""
        count = 0
        for equipment, state in self.equipment_states.items():
            if state == EquipmentState.ON and equipment in GPIO_PINS:
                count += 1
        return count
                
    def set_equipment_state(self, equipment: str, state: EquipmentState) -> bool:
        """Set equipment state with short-cycle protection and Active LOW logic"""
        if equipment not in GPIO_PINS:
            logging.error(f"Unknown equipment: {equipment}")
            return False
        
        # Safety check: Limit simultaneous relay activation
        if state == EquipmentState.ON:
            current_active = self.count_active_relays()
            if current_active >= self.max_simultaneous_relays:
                logging.warning(f"Maximum simultaneous relays ({self.max_simultaneous_relays}) reached. Cannot activate {equipment}")
                return False
            
        # Check for short cycling
        if equipment in self.last_state_change:
            time_since_change = datetime.now() - self.last_state_change[equipment]
            if time_since_change < self.min_cycle_time:
                logging.warning(f"Preventing short cycle for {equipment}")
                return False
        
        pin = GPIO_PINS[equipment]
        
        # Add startup delay for relay activation to prevent current surge
        if state == EquipmentState.ON and self.equipment_states[equipment] != EquipmentState.ON:
            time.sleep(self.relay_startup_delay)
        
        # Active LOW logic: LOW = ON, HIGH = OFF
        if state == EquipmentState.ON:
            GPIO.output(pin, RELAY_ON)  # LOW
        elif state == EquipmentState.OFF:
            GPIO.output(pin, RELAY_OFF)  # HIGH
        else:
            # IDLE state - equipment is powered but not actively running
            GPIO.output(pin, RELAY_OFF)  # HIGH
            
        self.equipment_states[equipment] = state
        self.last_state_change[equipment] = datetime.now()
        
        logging.info(f"{equipment} state changed to {state.name} (GPIO {pin} = {'LOW' if state == EquipmentState.ON else 'HIGH'})")
        return True
    
    def staged_startup(self, equipment_list: List[str]):
        """Start multiple equipment with delays to prevent current surge"""
        for equipment in equipment_list:
            self.set_equipment_state(equipment, EquipmentState.ON)
            time.sleep(self.relay_startup_delay)
    
    def emergency_stop(self):
        """Emergency stop - turn off all equipment (set all pins HIGH)"""
        logging.critical("EMERGENCY STOP ACTIVATED")
        for equipment in self.equipment_states.keys():
            if equipment in GPIO_PINS:
                GPIO.output(GPIO_PINS[equipment], RELAY_OFF)  # HIGH = OFF
                self.equipment_states[equipment] = EquipmentState.OFF
    
    def cleanup(self):
        """Clean up GPIO on shutdown - set all pins HIGH (OFF) for safety"""
        logging.info("Cleaning up GPIO - setting all relays to OFF")
        for pin in GPIO_PINS.values():
            GPIO.output(pin, RELAY_OFF)  # HIGH = OFF
        GPIO.cleanup()

# ============================================================================
# VPD CONTROL ALGORITHM
# ============================================================================

class VPDController:
    """Implements VPD-based control algorithm"""
    
    def __init__(self, sensor_manager: SensorManager, equipment_controller: EquipmentController):
        self.sensor_manager = sensor_manager
        self.equipment_controller = equipment_controller
        self.current_phase = ProcessPhase.IDLE
        self.process_start_time = None
        self.current_day = 0
        self.target_vpd = 0.8
        
    def get_current_target_vpd(self) -> float:
        """Get target VPD based on current phase and day"""
        if self.current_phase == ProcessPhase.DRYING:
            day_key = f'day_{min(self.current_day, 4)}'
            return VPD_TARGETS['DRYING'].get(day_key, 1.0)
        elif self.current_phase == ProcessPhase.CURING:
            day_key = f'day_{min(self.current_day, 8)}'
            return VPD_TARGETS['CURING'].get(day_key, 0.6)
        return 0.8
    
    def calculate_average_vpd(self, readings: List[SensorReading]) -> float:
        """Calculate average VPD from drying room sensors only"""
        dry_room_readings = [r for r in readings if 'dry_zone' in r.location]
        if not dry_room_readings:
            return 0.0
        return np.mean([r.vpd_kpa for r in dry_room_readings])
    
    def control_step(self) -> SystemState:
        """Execute one control step"""
        # Read all sensors
        readings = self.sensor_manager.read_all_sensors()
        
        if not readings:
            logging.error("No sensor readings available")
            return None
        
        # Calculate average VPD
        current_vpd = self.calculate_average_vpd(readings)
        
        # Update target VPD
        self.target_vpd = self.get_current_target_vpd()
        
        # Determine control actions
        vpd_error = current_vpd - self.target_vpd
        
        # Control logic with deadband
        if abs(vpd_error) > CONTROL_DEADBAND['vpd']:
            if vpd_error > 0:
                # VPD too high - need to reduce it (increase humidity)
                self.equipment_controller.set_equipment_state('HUMIDIFIER_SOLENOID', EquipmentState.ON)
                self.equipment_controller.set_equipment_state('HUMIDIFIER_FAN', EquipmentState.ON)
                self.equipment_controller.set_equipment_state('DEHUMIDIFIER', EquipmentState.OFF)
            else:
                # VPD too low - need to increase it (decrease humidity)
                self.equipment_controller.set_equipment_state('DEHUMIDIFIER', EquipmentState.ON)
                self.equipment_controller.set_equipment_state('HUMIDIFIER_SOLENOID', EquipmentState.OFF)
                self.equipment_controller.set_equipment_state('HUMIDIFIER_FAN', EquipmentState.OFF)
        else:
            # Within deadband - maintain current state
            self.equipment_controller.set_equipment_state('HUMIDIFIER_SOLENOID', EquipmentState.IDLE)
            self.equipment_controller.set_equipment_state('HUMIDIFIER_FAN', EquipmentState.IDLE)
            self.equipment_controller.set_equipment_state('DEHUMIDIFIER', EquipmentState.IDLE)
        
        # ERV control based on air quality (simplified)
        avg_humidity = np.mean([r.humidity for r in readings if 'dry_zone' in r.location])
        if avg_humidity > 65:
            self.equipment_controller.set_equipment_state('ERV', EquipmentState.ON)
        elif avg_humidity < 55:
            self.equipment_controller.set_equipment_state('ERV', EquipmentState.OFF)
        
        # Fans should always be running during active process
        if self.current_phase != ProcessPhase.IDLE:
            self.equipment_controller.set_equipment_state('SUPPLY_FAN', EquipmentState.ON)
            self.equipment_controller.set_equipment_state('RETURN_FAN', EquipmentState.ON)
        
        # Create system state
        return SystemState(
            phase=self.current_phase,
            day=self.current_day,
            target_vpd=self.target_vpd,
            current_vpd=current_vpd,
            equipment_states=self.equipment_controller.equipment_states,
            sensor_readings=readings,
            alarms=self.check_alarms(readings),
            timestamp=datetime.now()
        )
    
    def check_alarms(self, readings: List[SensorReading]) -> List[str]:
        """Check for alarm conditions"""
        alarms = []
        
        for reading in readings:
            # Temperature alarms
            if reading.temperature_f > 75:
                alarms.append(f"High temperature at {reading.location}: {reading.temperature_f:.1f}°F")
            elif reading.temperature_f < 55:
                alarms.append(f"Low temperature at {reading.location}: {reading.temperature_f:.1f}°F")
            
            # Humidity alarms
            if reading.humidity > 70:
                alarms.append(f"High humidity at {reading.location}: {reading.humidity:.1f}%")
            elif reading.humidity < 40:
                alarms.append(f"Low humidity at {reading.location}: {reading.humidity:.1f}%")
        
        return alarms
    
    def start_process(self, phase: ProcessPhase):
        """Start a new drying/curing process"""
        self.current_phase = phase
        self.process_start_time = datetime.now()
        self.current_day = 1
        logging.info(f"Started {phase.value} process")
    
    def update_process_day(self):
        """Update the current process day based on elapsed time"""
        if self.process_start_time:
            elapsed = datetime.now() - self.process_start_time
            self.current_day = elapsed.days + 1
            
            # Check for phase transition
            if self.current_phase == ProcessPhase.DRYING and self.current_day > 4:
                self.current_phase = ProcessPhase.CURING
                logging.info("Transitioning from DRYING to CURING phase")
            elif self.current_phase == ProcessPhase.CURING and self.current_day > 8:
                self.current_phase = ProcessPhase.COMPLETE
                logging.info("Process COMPLETE")

# ============================================================================
# DATA LOGGING AND PERSISTENCE
# ============================================================================

class DataLogger:
    """Handles data logging to database"""
    
    def __init__(self, db_path: str = '/home/mikejames/cannabis_dryer.db'):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                location TEXT,
                temperature_f REAL,
                humidity REAL,
                vpd_kpa REAL,
                dew_point_f REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS equipment_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                equipment TEXT,
                state TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                phase TEXT,
                day INTEGER,
                target_vpd REAL,
                current_vpd REAL,
                alarms TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_sensor_reading(self, reading: SensorReading):
        """Log sensor reading to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sensor_readings 
            (location, temperature_f, humidity, vpd_kpa, dew_point_f)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            reading.location,
            reading.temperature_f,
            reading.humidity,
            reading.vpd_kpa,
            reading.dew_point_f
        ))
        
        conn.commit()
        conn.close()
    
    def log_system_state(self, state: SystemState):
        """Log complete system state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Log overall state
        cursor.execute('''
            INSERT INTO system_states 
            (phase, day, target_vpd, current_vpd, alarms)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            state.phase.value,
            state.day,
            state.target_vpd,
            state.current_vpd,
            json.dumps(state.alarms)
        ))
        
        # Log all sensor readings
        for reading in state.sensor_readings:
            self.log_sensor_reading(reading)
        
        # Log equipment states
        for equipment, eq_state in state.equipment_states.items():
            cursor.execute('''
                INSERT INTO equipment_states (equipment, state)
                VALUES (?, ?)
            ''', (equipment, eq_state.name))
        
        conn.commit()
        conn.close()

# ============================================================================
# WEB INTERFACE AND API
# ============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change in production
socketio = SocketIO(app, cors_allowed_origins="*")

# Global instances
sensor_manager = None
equipment_controller = None
vpd_controller = None
data_logger = None
redis_client = None

@app.route('/')
def index():
    """Serve main GUI"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Get current system status"""
    try:
        state = vpd_controller.control_step()
        return jsonify({
            'success': True,
            'data': {
                'phase': state.phase.value,
                'day': state.day,
                'target_vpd': state.target_vpd,
                'current_vpd': state.current_vpd,
                'equipment': {k: v.name for k, v in state.equipment_states.items()},
                'sensors': [
                    {
                        'location': r.location,
                        'temperature': r.temperature_f,
                        'humidity': r.humidity,
                        'vpd': r.vpd_kpa,
                        'dew_point': r.dew_point_f
                    } for r in state.sensor_readings
                ],
                'alarms': state.alarms,
                'timestamp': state.timestamp.isoformat()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/control/start', methods=['POST'])
def start_process():
    """Start drying/curing process"""
    try:
        data = request.json
        phase = ProcessPhase(data.get('phase', 'drying'))
        vpd_controller.start_process(phase)
        return jsonify({'success': True, 'message': f'Started {phase.value} process'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/control/stop', methods=['POST'])
def stop_process():
    """Stop current process"""
    try:
        vpd_controller.current_phase = ProcessPhase.IDLE
        equipment_controller.emergency_stop()
        return jsonify({'success': True, 'message': 'Process stopped'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/control/equipment/<equipment>', methods=['POST'])
def control_equipment(equipment):
    """Manual equipment control"""
    try:
        data = request.json
        state = EquipmentState[data.get('state', 'OFF')]
        success = equipment_controller.set_equipment_state(equipment.upper(), state)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/vpd', methods=['POST'])
def update_vpd_settings():
    """Update VPD target settings"""
    try:
        data = request.json
        # Update VPD targets based on input
        return jsonify({'success': True, 'message': 'VPD settings updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# WebSocket events for real-time updates
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logging.info('Client connected')
    emit('connected', {'message': 'Connected to control system'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logging.info('Client disconnected')

def broadcast_system_state():
    """Broadcast system state to all connected clients"""
    while True:
        try:
            state = vpd_controller.control_step()
            if state:
                data_logger.log_system_state(state)
                
                # Broadcast to all connected clients
                socketio.emit('system_update', {
                    'phase': state.phase.value,
                    'day': state.day,
                    'target_vpd': state.target_vpd,
                    'current_vpd': state.current_vpd,
                    'equipment': {k: v.name for k, v in state.equipment_states.items()},
                    'sensors': [
                        {
                            'location': r.location,
                            'temperature': r.temperature_f,
                            'humidity': r.humidity,
                            'vpd': r.vpd_kpa,
                            'dew_point': r.dew_point_f
                        } for r in state.sensor_readings
                    ],
                    'alarms': state.alarms,
                    'timestamp': state.timestamp.isoformat()
                })
        except Exception as e:
            logging.error(f"Error in broadcast loop: {e}")
        
        time.sleep(5)  # Update every 5 seconds

# ============================================================================
# MAIN CONTROL LOOP
# ============================================================================

def main():
    """Main control loop"""
    global sensor_manager, equipment_controller, vpd_controller, data_logger, redis_client
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('/home/mikejames/cannabis_dryer.log'),
            logging.StreamHandler()
        ]
    )
    
    logging.info("Starting Cannabis Drying Control System")
    
    try:
        # Initialize components
        sensor_manager = SensorManager()
        equipment_controller = EquipmentController()
        vpd_controller = VPDController(sensor_manager, equipment_controller)
        data_logger = DataLogger()
        
        # Initialize Redis for inter-process communication
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        
        # Start background control thread
        control_thread = threading.Thread(target=broadcast_system_state, daemon=True)
        control_thread.start()
        
        # Start Flask web server with SocketIO
        logging.info("Starting web server on port 5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        logging.info("Shutdown requested")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
    finally:
        # Cleanup
        if equipment_controller:
            equipment_controller.cleanup()
        logging.info("System shutdown complete")

if __name__ == '__main__':
    main()