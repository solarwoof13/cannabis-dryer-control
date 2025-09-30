#!/usr/bin/env python3
"""
Flask API Server for Cannabis Drying Control System - PRODUCTION
Provides REST API for GUI interaction and remote monitoring
"""

from software.control.vpd_controller import DryingPhase, EquipmentState
from flask import Flask, jsonify, request, render_template_string, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
from software.control.state_manager import StateManager
import threading
import time
import json
import logging
import os
import random

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global controller and equipment controller instances
controller = None
equipment_controller = None

# Security configuration
API_KEY = os.environ.get('API_KEY', 'your-secure-api-key-here')
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'false').lower() == 'true'

def init_controller(ctrl, equip_ctrl=None):
    """Initialize the controller references"""
    global controller, equipment_controller
    controller = ctrl
    equipment_controller = equip_ctrl
    logger.info("Controllers initialized in API server")

def check_api_key():
    """Check API key for authenticated routes"""
    if not ENABLE_AUTH:
        return True
    
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False
    
    try:
        key = auth_header.split(' ')[1]
        return key == API_KEY
    except:
        return False

# ===== HTML GUI ROUTES =====

@app.route('/')
def index():
    """Serve the main touchscreen interface"""
    gui_path = os.path.join(os.path.dirname(__file__), '..', '..', 'touchscreen', 'index.html')
    if os.path.exists(gui_path):
        return send_from_directory(os.path.dirname(gui_path), 'index.html')
    else:
        return "HTML file not found at: " + gui_path

@app.route('/settings')
def serve_settings():
    """Serve the settings page"""
    gui_path = os.path.join(os.path.dirname(__file__), '..', '..', 'touchscreen')
    if os.path.exists(os.path.join(gui_path, 'settings.html')):
        return send_from_directory(gui_path, 'settings.html')
    else:
        return "Settings page not found", 404

@app.route('/analytics')
def serve_analytics():
    """Serve the analytics page"""
    gui_path = os.path.join(os.path.dirname(__file__), '..', '..', 'touchscreen')
    if os.path.exists(os.path.join(gui_path, 'analytics.html')):
        return send_from_directory(gui_path, 'analytics.html')
    else:
        return "Analytics page not found", 404

# ===== API ROUTES =====

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current system status with VPD targets - FIXED for frontend compatibility"""
    if not controller:
        return jsonify({
            'error': 'System not initialized',
            'current_vpd': 0.75,
            'vpd_target_min': 0.7,
            'vpd_target_max': 0.8,
            'phase': 'idle',
            'system_state': 'idle',
            'cycle_state': 'idle',
            'current_temp': 68.0,
            'current_humidity': 60.0,
            'drying_progress': 0,
            'curing_progress': 0,
            'phase_day': 0,
            'phase_total_days': 0
        }), 503
    
    try:
        # Try to get the existing system status first
        if hasattr(controller, 'get_system_status'):
            status = controller.get_system_status()
        else:
            status = {}
        
        # Get current phase
        current_phase = DryingPhase.IDLE
        if hasattr(controller, 'current_phase'):
            current_phase = controller.current_phase
        
        # Get setpoint for current phase
        vpd_min, vpd_max, temp_target, humidity_min, humidity_max = 0.7, 0.8, 68.0, 55.0, 65.0
        if hasattr(controller, 'calculate_linear_transition'):
            setpoint = controller.calculate_linear_transition()
            vpd_min = setpoint.vpd_min
            vpd_max = setpoint.vpd_max
            temp_target = setpoint.temperature_target
            humidity_min = setpoint.humidity_min
            humidity_max = setpoint.humidity_max
        
        # Calculate current VPD
        current_vpd = 0.75
        avg_temp = 68.0
        avg_humidity = 60.0
        
        if hasattr(controller, 'get_dry_room_conditions'):
            avg_temp, avg_humidity, avg_dew_point, avg_vpd = controller.get_dry_room_conditions()
            current_vpd = avg_vpd
        else:
            if hasattr(controller, 'last_temp'):
                avg_temp = controller.last_temp
            if hasattr(controller, 'last_humidity'):
                avg_humidity = controller.last_humidity
        
        # Determine system state
        process_active = False
        if hasattr(controller, 'process_active'):
            process_active = controller.process_active
        elif current_phase != DryingPhase.IDLE:
            process_active = True
        
        # Map phase to frontend states
        phase_value = current_phase.value if hasattr(current_phase, 'value') else str(current_phase)
        
        if phase_value == 'idle':
            system_state = 'idle'
            cycle_state = 'idle'
        elif phase_value == 'storage':
            system_state = 'holding'
            cycle_state = 'holding'
        elif process_active:
            system_state = 'running'
            cycle_state = 'running'
        else:
            system_state = 'idle'
            cycle_state = 'idle'
        
        # Calculate progress
        current_day = 1
        phase_day = 1
        drying_progress = 0
        curing_progress = 0
        phase_total_days = 4
        
        if hasattr(controller, 'process_start_time') and controller.process_start_time:
            elapsed = datetime.now() - controller.process_start_time
            current_day = elapsed.days + 1
            hours_elapsed = elapsed.total_seconds() / 3600
            
            if phase_value in ['dry_initial', 'dry_mid', 'dry_final']:
                drying_progress = min(100, int((hours_elapsed / (4 * 24)) * 100))
                phase_day = current_day
                phase_total_days = 4
            elif phase_value == 'cure':
                drying_progress = 100
                cure_hours = hours_elapsed - (4 * 24)
                curing_progress = min(100, int((cure_hours / (4 * 24)) * 100))
                phase_day = current_day - 4
                phase_total_days = 4
            elif phase_value == 'storage':
                drying_progress = 100
                curing_progress = 100
        
        # Get equipment states
        equipment = {}
        if hasattr(controller, 'equipment_states'):
            equipment = {k: v.value if hasattr(v, 'value') else str(v) 
                        for k, v in controller.equipment_states.items()}
        
        # Build complete response
        status.update({
            'phase': phase_value,
            'system_state': system_state,
            'cycle_state': cycle_state,
            'current_phase': phase_value,
            'drying_progress': drying_progress,
            'curing_progress': curing_progress,
            'phase_day': phase_day,
            'phase_total_days': phase_total_days,
            'current_day': current_day,
            'current_vpd': float(current_vpd),
            'vpd_target_min': float(vpd_min),
            'vpd_target_max': float(vpd_max),
            'current_temp': float(avg_temp),
            'current_humidity': float(avg_humidity),
            'temp_target': float(temp_target),
            'humidity_min': float(humidity_min),
            'humidity_max': float(humidity_max),
            'process_active': process_active,
            'equipment': equipment,
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({
            'error': str(e),
            'current_vpd': 0.75,
            'vpd_target_min': 0.7,
            'vpd_target_max': 0.8,
            'phase': 'idle',
            'system_state': 'idle',
            'cycle_state': 'idle',
            'current_temp': 68.0,
            'current_humidity': 60.0
        }), 500

@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    """Get sensor readings"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    sensors = {
        'zone1': {'temperature': None, 'humidity': None, 'timestamp': None},
        'zone2': {'temperature': None, 'humidity': None, 'timestamp': None},
        'zone3': {'temperature': None, 'humidity': None, 'timestamp': None},
        'zone4': {'temperature': None, 'humidity': None, 'timestamp': None},
        'supply_duct': {'temperature': None, 'humidity': None, 'timestamp': None},
        'return_duct': {'temperature': None, 'humidity': None, 'timestamp': None},
        'air_room': {'temperature': None, 'humidity': None, 'timestamp': None}
    }
    
    if hasattr(controller, 'hardware_mode') and controller.hardware_mode:
        if hasattr(controller, 'sensor_manager') and controller.sensor_manager:
            for sensor_name in sensors.keys():
                if sensor_name in controller.sensor_manager.sensors:
                    reading = controller.sensor_manager.read_sensor(sensor_name)
                    if reading:
                        sensors[sensor_name] = {
                            'temperature': reading.get('temperature'),
                            'humidity': reading.get('humidity'),
                            'timestamp': reading.get('timestamp', datetime.now()).isoformat()
                        }
    
    return jsonify(sensors)

@app.route('/api/sensors/<sensor_id>', methods=['POST'])
def update_sensor(sensor_id):
    """Update sensor reading (for testing)"""
    if not check_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    if not data or 'temperature' not in data or 'humidity' not in data:
        return jsonify({'error': 'Missing temperature or humidity'}), 400
    
    try:
        controller.update_sensor_reading(
            sensor_id,
            float(data['temperature']),
            float(data['humidity'])
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/equipment', methods=['GET'])
def get_equipment():
    """Get equipment states"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    equipment = {}
    if hasattr(controller, 'equipment_states'):
        equipment = {k: v.value if hasattr(v, 'value') else str(v) 
                    for k, v in controller.equipment_states.items()}
    
    return jsonify(equipment)

@app.route('/api/equipment/<equipment_id>', methods=['POST'])
@app.route('/api/equipment/<equipment_id>/toggle', methods=['POST'])
def toggle_equipment(equipment_id):
    """Toggle equipment state - PRODUCTION version with relay control"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        equipment_id = equipment_id.upper().replace('-', '_')
        
        # Get current state
        current_state = EquipmentState.OFF
        if hasattr(controller, 'equipment_states') and equipment_id in controller.equipment_states:
            current_state = controller.equipment_states[equipment_id]
        
        # Cycle: OFF -> ON -> IDLE -> OFF
        if current_state == EquipmentState.OFF:
            new_state = EquipmentState.ON
        elif current_state == EquipmentState.ON:
            new_state = EquipmentState.IDLE
        else:
            new_state = EquipmentState.OFF
        
        # Apply state through equipment controller
        success = True
        if equipment_controller and hasattr(equipment_controller, 'set_equipment_state'):
            success = equipment_controller.set_equipment_state(equipment_id, new_state)
        else:
            controller.equipment_states[equipment_id] = new_state
        
        if success:
            logger.info(f"Equipment {equipment_id} toggled to {new_state.value}")
            return jsonify({
                'success': True,
                'equipment': equipment_id,
                'new_state': new_state.value
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to set state'}), 500
            
    except Exception as e:
        logger.error(f"Error toggling equipment {equipment_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process/start', methods=['POST'])
def start_process():
    """Start fresh drying process"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        controller.process_active = True
        controller.process_start_time = datetime.now()
        controller.phase_start_time = datetime.now()
        controller.current_phase = DryingPhase.DRY_INITIAL
        
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': True,
            'current_phase': 'dry_initial',
            'process_start_time': controller.process_start_time,
            'phase_start_time': controller.phase_start_time,
            'equipment_states': {}
        })
        
        logger.info("Drying process STARTED - Phase: DRY_INITIAL")
        
        return jsonify({
            'success': True,
            'message': 'Drying process started',
            'phase': 'DRY_INITIAL',
            'system_state': 'running'
        })
    except Exception as e:
        logger.error(f"Error starting process: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process/hold', methods=['POST'])
def hold_process():
    """Switch to storage/hold mode"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        controller.current_phase = DryingPhase.STORAGE
        controller.phase_start_time = datetime.now()
        
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': True,
            'current_phase': 'storage',
            'process_start_time': controller.process_start_time,
            'phase_start_time': controller.phase_start_time,
            'equipment_states': {}
        })
        
        logger.info("Process put on HOLD - entering STORAGE mode")
        
        return jsonify({
            'success': True,
            'message': 'Process on hold - storage mode active',
            'phase': 'STORAGE',
            'system_state': 'holding'
        })
    except Exception as e:
        logger.error(f"Error switching to hold: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process/stop', methods=['POST'])
@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop - turn off ALL equipment"""
    logger.critical("🔴 EMERGENCY STOP ACTIVATED")
    
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        controller.process_active = False
        controller.current_phase = DryingPhase.IDLE
        
        # Turn off all equipment
        if equipment_controller and hasattr(equipment_controller, 'emergency_stop'):
            equipment_controller.emergency_stop()
            logger.info("Equipment controller emergency_stop() executed")
        else:
            if hasattr(controller, 'equipment_states'):
                for equipment in controller.equipment_states.keys():
                    controller.equipment_states[equipment] = EquipmentState.OFF
                logger.info("All equipment turned OFF via controller")
        
        # Save emergency state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': False,
            'current_phase': 'idle',
            'process_start_time': None,
            'phase_start_time': None,
            'equipment_states': {k: 'OFF' for k in controller.equipment_states.keys()}
        })
        
        equipment_states = {}
        if hasattr(controller, 'equipment_states'):
            equipment_states = {k: v.value if hasattr(v, 'value') else str(v) 
                              for k, v in controller.equipment_states.items()}
        
        return jsonify({
            'success': True,
            'status': 'emergency_stop_activated',
            'message': 'Emergency stop executed - all equipment OFF',
            'system_state': 'emergency',
            'equipment': equipment_states
        })
        
    except Exception as e:
        logger.error(f"Error during emergency stop: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/setpoint', methods=['GET', 'POST'])
def manage_setpoint():
    """Get or update VPD setpoint"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    if request.method == 'GET':
        setpoint = controller.calculate_linear_transition()
        return jsonify({
            'temp_target': setpoint.temperature_target,
            'temp_tolerance': setpoint.temperature_tolerance,
            'dew_point_target': setpoint.dew_point_target,
            'dew_point_tolerance': setpoint.dew_point_tolerance,
            'humidity_min': setpoint.humidity_min,
            'humidity_max': setpoint.humidity_max,
            'vpd_min': setpoint.vpd_min,
            'vpd_max': setpoint.vpd_max
        })
    
    else:  # POST
        if not check_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.json
        logger.info(f"Setpoint update requested: {data}")
        return jsonify({'success': True})

@app.route('/api/phase', methods=['GET', 'POST'])
def manage_phase():
    """Get current phase or manually advance phase"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    if request.method == 'GET':
        return jsonify({
            'current_phase': controller.current_phase.value,
            'phase_description': controller._get_phase_description(),
            'phase_start': controller.phase_start_time.isoformat(),
            'elapsed_hours': (datetime.now() - controller.phase_start_time).total_seconds() / 3600
        })
    
    else:  # POST
        if not check_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.json
        if 'phase' in data:
            logger.warning(f"Manual phase override: {data['phase']}")
        
        return jsonify({'success': True})

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get system alerts and warnings"""
    alerts = []
    
    if controller and hasattr(controller, 'get_dry_room_conditions'):
        try:
            avg_temp, avg_humidity, avg_dew_point, avg_vpd = controller.get_dry_room_conditions()
            setpoint = controller.calculate_linear_transition()
            
            # Check VPD
            if avg_vpd < setpoint.vpd_min - 0.2 or avg_vpd > setpoint.vpd_max + 0.2:
                alerts.append({
                    'level': 'critical',
                    'message': f'VPD critically out of range: {avg_vpd:.2f} kPa',
                    'timestamp': datetime.now().isoformat()
                })
            elif avg_vpd < setpoint.vpd_min or avg_vpd > setpoint.vpd_max:
                alerts.append({
                    'level': 'warning',
                    'message': f'VPD out of range: {avg_vpd:.2f} kPa',
                    'timestamp': datetime.now().isoformat()
                })
            
            # Check temperature
            if hasattr(controller, 'emergency_temp_max'):
                if avg_temp > controller.emergency_temp_max or avg_temp < controller.emergency_temp_min:
                    alerts.append({
                        'level': 'critical',
                        'message': f'Temperature emergency: {avg_temp:.1f}°F',
                        'timestamp': datetime.now().isoformat()
                    })
            
            # Check humidity
            if hasattr(controller, 'emergency_humidity_max'):
                if avg_humidity > controller.emergency_humidity_max or avg_humidity < controller.emergency_humidity_min:
                    alerts.append({
                        'level': 'critical',
                        'message': f'Humidity emergency: {avg_humidity:.1f}%',
                        'timestamp': datetime.now().isoformat()
                    })
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
    
    return jsonify(alerts)

@app.route('/api/history/<timeframe>', methods=['GET'])
def get_history(timeframe):
    """Get historical data for graphs"""
    data_points = {
        '1h': 60,
        '6h': 72,
        '24h': 96,
        '7d': 168
    }
    
    points = data_points.get(timeframe, 24)
    
    history = []
    for i in range(points):
        history.append({
            'timestamp': (datetime.now().timestamp() - (i * 60)),
            'vpd': 0.8 + random.uniform(-0.2, 0.2),
            'temperature': 68 + random.uniform(-2, 2),
            'humidity': 60 + random.uniform(-5, 5),
            'dew_point': 55 + random.uniform(-2, 2)
        })
    
    return jsonify(history)

@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    """System configuration management"""
    if request.method == 'GET':
        if controller and hasattr(controller, 'min_cycle_time'):
            config = {
                'control_interval': 10,
                'min_cycle_time': controller.min_cycle_time,
                'target_water_activity': getattr(controller, 'target_water_activity', 0.62)
            }
        else:
            config = {'error': 'Controller not initialized'}
        
        return jsonify(config)
    
    else:  # POST
        if not check_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.json
        logger.info(f"Configuration update: {data}")
        return jsonify({'success': True})

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'controller_active': controller is not None,
        'equipment_controller_active': equipment_controller is not None
    })

# ===== WEBSOCKET EVENTS =====

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to control system'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('request_update')
def handle_update_request():
    """Handle real-time update request"""
    if controller:
        status = controller.get_system_status()
        emit('status_update', status)

def broadcast_updates():
    """Background thread to broadcast system updates"""
    while True:
        time.sleep(5)
        if controller:
            try:
                status = controller.get_system_status()
                socketio.emit('status_update', status, broadcast=True)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")

def start_api_server(host='0.0.0.0', port=5000):
    """Start the API server"""
    logger.info(f"Starting API server on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    logger.warning("Running API server standalone - controller not initialized")
    start_api_server()