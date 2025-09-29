#!/usr/bin/env python3
"""
Cannabis Drying and Curing Control System - Main Controller
Unified control system for 40' shipping container cannabis dryer
"""

import time
import json
import logging
import threading
from datetime import datetime
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import sys

# Try to import RPi.GPIO - use mock if not on Pi
try:
    import RPi.GPIO as GPIO
    ON_RASPBERRY_PI = True
except ImportError:
    print("WARNING: RPi.GPIO not found - running in simulation mode")
    ON_RASPBERRY_PI = False
    # Create mock GPIO
    class MockGPIO:
        BCM = "BCM"
        OUT = "OUT"
        HIGH = 1
        LOW = 0
        
        @staticmethod
        def setmode(mode): pass
        @staticmethod
        def setwarnings(warn): pass
        @staticmethod
        def setup(pin, mode): pass
        @staticmethod
        def output(pin, state): pass
        @staticmethod
        def cleanup(): pass
    
    GPIO = MockGPIO()

# ============================================================================
# CONFIGURATION
# ============================================================================

# GPIO Pin Configuration (BCM Mode) - Active LOW relay logic
RELAY_PINS = {
    'dehumidifier': 17,
    'humidifier': 27,
    'erv': 22,
    'supply_fan': 23,
    'return_fan': 24,
    'humidifier_fan': 25,
    'spare_1': 20,
    'spare_2': 21
}

# Active LOW relay logic (GPIO LOW = Relay ON, GPIO HIGH = Relay OFF)
RELAY_ON = GPIO.LOW
RELAY_OFF = GPIO.HIGH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cannabis_dryer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# RELAY CONTROLLER
# ============================================================================

class RelayController:
    """Handles all GPIO relay control with active LOW logic"""
    
    def __init__(self):
        self.relay_states = {}
        self.setup_gpio()
        
    def setup_gpio(self):
        """Initialize all GPIO pins"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        for name, pin in RELAY_PINS.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, RELAY_OFF)  # Start with everything OFF (HIGH)
            self.relay_states[name] = 'OFF'
            logger.info(f"Initialized {name} on GPIO {pin} (OFF)")
    
    def set_relay(self, equipment, state):
        """Set relay state with active LOW logic
        Args:
            equipment: Equipment name (must match RELAY_PINS keys)
            state: 'ON', 'OFF', or 'IDLE'
        """
        if equipment not in RELAY_PINS:
            logger.error(f"Unknown equipment: {equipment}")
            return False
        
        pin = RELAY_PINS[equipment]
        
        if state == 'ON':
            GPIO.output(pin, RELAY_ON)  # LOW = ON
            self.relay_states[equipment] = 'ON'
            logger.info(f"{equipment} turned ON (GPIO {pin} = LOW)")
        else:
            GPIO.output(pin, RELAY_OFF)  # HIGH = OFF
            self.relay_states[equipment] = state
            logger.info(f"{equipment} turned {state} (GPIO {pin} = HIGH)")
        
        return True
    
    def get_all_states(self):
        """Get current state of all relays"""
        return self.relay_states.copy()
    
    def emergency_stop(self):
        """Emergency stop - turn everything OFF"""
        logger.critical("EMERGENCY STOP ACTIVATED!")
        for equipment in RELAY_PINS.keys():
            self.set_relay(equipment, 'OFF')
    
    def cleanup(self):
        """Clean up GPIO on shutdown"""
        logger.info("Cleaning up GPIO...")
        GPIO.cleanup()

# ============================================================================
# SENSOR MANAGER (Simulated for now)
# ============================================================================

class SensorManager:
    """Manages sensor readings"""
    
    def __init__(self):
        self.sensors = {
            'dry1': {'temp': 68.0, 'humidity': 60.0, 'vpd': 0.75},
            'dry2': {'temp': 68.5, 'humidity': 59.0, 'vpd': 0.78},
            'dry3': {'temp': 67.5, 'humidity': 61.0, 'vpd': 0.72},
            'dry4': {'temp': 68.0, 'humidity': 60.5, 'vpd': 0.74},
            'air': {'temp': 70.0, 'humidity': 55.0, 'vpd': 0.90},
            'supply': {'temp': 67.0, 'humidity': 62.0, 'vpd': 0.70}
        }
    
    def get_all_readings(self):
        """Get all sensor readings"""
        # In production, this would read from I2C sensors
        return self.sensors.copy()
    
    def get_average_vpd(self):
        """Calculate average VPD from drying room sensors"""
        dry_sensors = ['dry1', 'dry2', 'dry3', 'dry4']
        vpd_sum = sum(self.sensors[s]['vpd'] for s in dry_sensors)
        return vpd_sum / len(dry_sensors)

# ============================================================================
# FLASK WEB SERVER
# ============================================================================

app = Flask(__name__, static_folder='touchscreen')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global instances
relay_controller = None
sensor_manager = None

# Serve the main GUI
@app.route('/')
def index():
    """Serve the main touchscreen interface"""
    return send_from_directory('touchscreen', 'index.html')

@app.route('/index.html')
def index_html():
    """Alternative route for index.html"""
    return send_from_directory('touchscreen', 'index.html')

@app.route('/settings')
@app.route('/settings.html')
def settings():
    """Serve settings page"""
    return send_from_directory('touchscreen', 'settings.html')

@app.route('/analytics')
@app.route('/analytics.html')
def analytics():
    """Serve analytics page"""
    return send_from_directory('touchscreen', 'analytics.html')

# API Routes
@app.route('/api/status')
def get_status():
    """Get complete system status"""
    try:
        sensor_data = sensor_manager.get_all_readings()
        relay_states = relay_controller.get_all_states()
        avg_vpd = sensor_manager.get_average_vpd()
        
        return jsonify({
            'success': True,
            'current_vpd': avg_vpd,
            'vpd_target_min': 0.70,
            'vpd_target_max': 0.80,
            'mode': 'CURE MODE',
            'phase_day': 2,
            'phase_total_days': 4,
            'temperature': sensor_data['dry1']['temp'],
            'humidity': sensor_data['dry1']['humidity'],
            'sensors': sensor_data,
            'equipment': {
                'dehumidifier': relay_states.get('dehumidifier', 'OFF'),
                'humidifier': relay_states.get('humidifier', 'OFF'),
                'erv': relay_states.get('erv', 'OFF'),
                'supply_fan': relay_states.get('supply_fan', 'OFF'),
                'return_fan': relay_states.get('return_fan', 'OFF'),
                'mini_split': 'ON'  # IR controlled separately
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sensors')
def get_sensors():
    """Get all sensor readings"""
    try:
        return jsonify(sensor_manager.get_all_readings())
    except Exception as e:
        logger.error(f"Error getting sensors: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/equipment/<equipment_id>/toggle', methods=['POST'])
def toggle_equipment(equipment_id):
    """Toggle equipment state"""
    try:
        # Map frontend IDs to backend IDs
        equipment_map = {
            'dehumidifier': 'dehumidifier',
            'humidifier': 'humidifier',
            'erv': 'erv',
            'supply-fan': 'supply_fan',
            'exhaust-fan': 'return_fan',
            'return-fan': 'return_fan'
        }
        
        equipment = equipment_map.get(equipment_id, equipment_id)
        
        if equipment not in RELAY_PINS:
            return jsonify({'error': 'Unknown equipment'}), 400
        
        # Get current state and toggle
        current_state = relay_controller.relay_states.get(equipment, 'OFF')
        new_state = 'OFF' if current_state == 'ON' else 'ON'
        
        success = relay_controller.set_relay(equipment, new_state)
        
        return jsonify({
            'success': success,
            'equipment': equipment_id,
            'new_state': new_state
        })
    except Exception as e:
        logger.error(f"Error toggling equipment: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop endpoint"""
    try:
        relay_controller.emergency_stop()
        return jsonify({'success': True, 'message': 'Emergency stop activated'})
    except Exception as e:
        logger.error(f"Error in emergency stop: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/relay/<relay_name>/<state>', methods=['POST'])
def control_relay(relay_name, state):
    """Direct relay control endpoint"""
    try:
        if relay_name not in RELAY_PINS:
            return jsonify({'error': 'Invalid relay name'}), 400
        
        if state.upper() not in ['ON', 'OFF', 'IDLE']:
            return jsonify({'error': 'Invalid state'}), 400
        
        success = relay_controller.set_relay(relay_name, state.upper())
        
        return jsonify({
            'success': success,
            'relay': relay_name,
            'state': state.upper()
        })
    except Exception as e:
        logger.error(f"Error controlling relay: {e}")
        return jsonify({'error': str(e)}), 500

# WebSocket events for real-time updates
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("Client connected")
    emit('connected', {'data': 'Connected to Cannabis Dryer Control System'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Client disconnected")

def broadcast_status():
    """Broadcast system status to all connected clients"""
    while True:
        try:
            sensor_data = sensor_manager.get_all_readings()
            relay_states = relay_controller.get_all_states()
            
            socketio.emit('status_update', {
                'sensors': sensor_data,
                'relays': relay_states,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")
        
        time.sleep(5)  # Broadcast every 5 seconds

# ============================================================================
# MAIN STARTUP
# ============================================================================

def main():
    """Main entry point"""
    global relay_controller, sensor_manager
    
    logger.info("=" * 60)
    logger.info("Cannabis Drying Control System Starting")
    logger.info("=" * 60)
    
    # Initialize hardware controllers
    relay_controller = RelayController()
    sensor_manager = SensorManager()
    
    # Test relays on startup
    if ON_RASPBERRY_PI:
        logger.info("Testing relays...")
        for equipment in RELAY_PINS.keys():
            relay_controller.set_relay(equipment, 'ON')
            time.sleep(0.5)
            relay_controller.set_relay(equipment, 'OFF')
            time.sleep(0.5)
    
    # Start background status broadcaster
    broadcast_thread = threading.Thread(target=broadcast_status, daemon=True)
    broadcast_thread.start()
    
    # Start Flask web server
    logger.info("Starting web server on port 5000...")
    logger.info("Access the GUI at: http://localhost:5000")
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        relay_controller.cleanup()
        logger.info("System shutdown complete")

if __name__ == '__main__':
    main()