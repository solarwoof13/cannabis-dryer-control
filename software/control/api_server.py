#!/usr/bin/env python3
"""
Flask API Server for Cannabis Drying Control System
Provides REST API for GUI interaction and remote monitoring
"""

from software.control.vpd_controller import DryingPhase
from flask import Flask, jsonify, request, render_template_string, send_from_directory, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
from software.control.state_manager import StateManager
import threading
import time
import json
import logging
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global controller instance
controller = None

# Security configuration
API_KEY = os.environ.get('API_KEY', 'your-secure-api-key-here')
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'false').lower() == 'true'

equipment_controller = None  # Add this global variable

def init_controller(ctrl, equip_ctrl=None):
    """Initialize the controller reference"""
    global controller, equipment_controller
    controller = ctrl
    equipment_controller = equip_ctrl
    logger.info("Controller initialized in API server")

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

# Serve the HTML GUI from software/gui directory
@app.route('/')
def index():
    """Serve the main touchscreen interface"""
    gui_path = os.path.join(os.path.dirname(__file__), '..', '..', 'touchscreen', 'index.html')
    if os.path.exists(gui_path):
        return send_from_directory(os.path.dirname(gui_path), 'index.html')
    else:
        # Fallback - try to find it
        return "HTML file not found at: " + gui_path
    
# API Routes

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current system status with VPD targets"""
    if not controller:
        return jsonify({
            'error': 'System not initialized',
            'current_vpd': 0.75,
            'vpd_target_min': 0.7,
            'vpd_target_max': 0.8,
            'current_phase': 'IDLE',
            'current_temp': 68.0,
            'current_humidity': 60.0
        }), 503
    
    try:
        # Try to get the existing system status first
        if hasattr(controller, 'get_system_status'):
            status = controller.get_system_status()
        else:
            status = {}
        
        # Get current phase and VPD targets from controller
        from software.control.vpd_controller import DryingPhase
        current_phase = controller.current_phase if hasattr(controller, 'current_phase') else DryingPhase.DRY_INITIAL
        
        # Get the VPD targets for current phase
        vpd_min = 0.7  # Default
        vpd_max = 0.8  # Default
        temp_target = 68
        humidity_min = 60
        humidity_max = 65
        
        if hasattr(controller, 'phase_setpoints') and current_phase in controller.phase_setpoints:
            phase_settings = controller.phase_setpoints[current_phase]
            vpd_min = phase_settings.vpd_min
            vpd_max = phase_settings.vpd_max
            temp_target = phase_settings.temp_target
            humidity_min = phase_settings.humidity_min
            humidity_max = phase_settings.humidity_max
        
        # Get current VPD and sensor averages - use supply air conditions only
        current_vpd = None  # Don't default to fake value
        avg_temp = None
        avg_humidity = None
        
        # Use supply air conditions only for VPD calculation
        if hasattr(controller, 'get_supply_air_conditions'):
            try:
                supply_temp, supply_humidity, supply_dew_point, supply_vpd = controller.get_supply_air_conditions()
                if supply_vpd is not None and supply_temp is not None and supply_humidity is not None:
                    current_vpd = supply_vpd
                    avg_temp = supply_temp
                    avg_humidity = supply_humidity
                    logger.info(f"Using supply air conditions: VPD={current_vpd:.3f}, T={avg_temp:.1f}°F, RH={avg_humidity:.1f}%")
                else:
                    logger.warning("Supply air conditions returned None values")
            except Exception as e:
                logger.warning(f"Supply air sensors not available: {e}")
        
        # If supply air data is not available, try cached values as fallback
        if current_vpd is None and hasattr(controller, 'last_vpd') and controller.last_vpd is not None:
            current_vpd = controller.last_vpd
            if hasattr(controller, 'last_temp') and controller.last_temp is not None:
                avg_temp = controller.last_temp
            if hasattr(controller, 'last_humidity') and controller.last_humidity is not None:
                avg_humidity = controller.last_humidity
            logger.info(f"Using cached values: VPD={current_vpd:.3f}")
        
        # Final fallback - use reasonable defaults only if nothing else available
        if current_vpd is None:
            current_vpd = 0.75  # Last resort default
            logger.warning("No VPD data available, using default 0.75 kPa")
        if avg_temp is None:
            avg_temp = 68.0
        if avg_humidity is None:
            avg_humidity = 60.0
        
        # Determine process state
        process_active = False
        if hasattr(controller, 'process_active'):
            process_active = controller.process_active
        elif current_phase != DryingPhase.IDLE:
            process_active = True
        
        # Calculate current day
        current_day = 1
        if hasattr(controller, 'process_start_time') and controller.process_start_time:
            elapsed = datetime.now() - controller.process_start_time
            current_day = elapsed.days + 1
        
        # Build the complete status response
        # Include any existing status data and add our VPD specific data
        
        # Check for emergency state first
        state_manager = StateManager()
        saved_state = state_manager.load_state()
        
        # Always define phase_value for later use
        phase_value = current_phase.value if hasattr(current_phase, 'value') else str(current_phase)
        
        if saved_state.get('emergency_stop', False):
            system_state = 'emergency'
            cycle_state = 'emergency'
        else:
            # Map phase to frontend states
            if phase_value == 'idle':
                system_state = 'idle'
                cycle_state = 'idle'
            elif phase_value == 'storage':
                # Storage phase: if process is active, it's resumed from hold (running), otherwise it's holding
                if process_active:
                    system_state = 'running'
                    cycle_state = 'running'
                else:
                    system_state = 'holding'
                    cycle_state = 'holding'
            elif process_active:
                system_state = 'running'
                cycle_state = 'running'
            else:
                system_state = 'idle'
                cycle_state = 'idle'
        
        # Calculate progress
        drying_progress = 0
        curing_progress = 0
        phase_day = 1
        phase_total_days = 4
        
        if hasattr(controller, 'process_start_time') and controller.process_start_time:
            elapsed = datetime.now() - controller.process_start_time
            hours_elapsed = elapsed.total_seconds() / 3600
            
            # Get actual phase durations from controller
            total_drying_hours = 0
            total_curing_hours = 0
            if hasattr(controller, 'phase_setpoints'):
                # Sum up all drying phase durations
                drying_phases = ['dry_initial', 'dry_mid', 'dry_final']
                for phase_name in drying_phases:
                    if phase_name in controller.phase_setpoints:
                        total_drying_hours += controller.phase_setpoints[phase_name].duration_hours
                
                # Get curing phase duration
                if 'cure' in controller.phase_setpoints:
                    total_curing_hours = controller.phase_setpoints['cure'].duration_hours
            
            if phase_value in ['dry_initial', 'dry_mid', 'dry_final']:
                if total_drying_hours > 0:
                    drying_progress = min(100, int((hours_elapsed / total_drying_hours) * 100))
                phase_day = current_day
                phase_total_days = max(1, int(total_drying_hours / 24))  # Convert to days
            elif phase_value == 'cure':
                drying_progress = 100
                cure_hours = hours_elapsed - total_drying_hours
                if total_curing_hours > 0:
                    curing_progress = min(100, int((cure_hours / total_curing_hours) * 100))
                phase_day = current_day - max(1, int(total_drying_hours / 24))
                phase_total_days = max(1, int(total_curing_hours / 24))  # Convert to days
            elif phase_value == 'storage':
                drying_progress = 100
                curing_progress = 100
        
        # Get equipment states from equipment controller (actual GPIO states)
        logger.info(f"DEBUG: equipment_controller = {equipment_controller}, has actual_states = {hasattr(equipment_controller, 'actual_states') if equipment_controller else False}")
        equipment = {}
        if equipment_controller and hasattr(equipment_controller, 'actual_states'):
            # Use the actual GPIO states from equipment controller
            equipment = equipment_controller.actual_states.copy()
            logger.info(f"DEBUG: Using equipment_controller.actual_states = {equipment}")
        elif hasattr(controller, 'equipment_states'):
            # Fallback to VPD controller states
            equipment = {k: v.value if hasattr(v, 'value') else str(v) 
                        for k, v in controller.equipment_states.items()}
            logger.info(f"DEBUG: Using controller.equipment_states = {equipment}")
        
        # Add debug info
        debug_info = {}
        if equipment_controller:
            debug_info = {
                'gpio_initialized': getattr(equipment_controller, 'gpio_initialized', False),
                'process_active': getattr(equipment_controller.vpd_controller, 'process_active', False) if hasattr(equipment_controller, 'vpd_controller') else False,
                'current_phase': getattr(equipment_controller.vpd_controller, 'current_phase', None).value if hasattr(equipment_controller, 'vpd_controller') and hasattr(equipment_controller.vpd_controller, 'current_phase') and equipment_controller.vpd_controller.current_phase else None,
                'control_modes': {k: v.value if hasattr(v, 'value') else str(v) 
                                for k, v in getattr(equipment_controller, 'control_modes', {}).items()},
            }
        
        # Try to get supply air conditions for monitoring
        supply_temp = None
        supply_humidity = None
        supply_vpd = None
        supply_dew_point = None
        
        try:
            if hasattr(controller, 'get_supply_air_conditions'):
                supply_temp, supply_humidity, supply_dew_point, supply_vpd = controller.get_supply_air_conditions()
                # Validate supply VPD
                if supply_vpd is not None and not (0.1 <= supply_vpd <= 5.0):
                    logger.warning(f"Invalid supply VPD from sensor: {supply_vpd:.3f}, setting to None")
                    supply_vpd = None
        except Exception as e:
            logger.debug(f"Supply air data not available: {e}")
            supply_temp = None
            supply_humidity = None
            supply_vpd = None
            supply_dew_point = None
        
        status.update({
            'phase': phase_value,  # ADDED for frontend
            'system_state': system_state,  # ADDED for frontend
            'cycle_state': cycle_state,  # ADDED for frontend
            'current_phase': phase_value,
            'current_day': current_day,
            'drying_progress': drying_progress,  # ADDED
            'curing_progress': curing_progress,  # ADDED
            'phase_day': phase_day,  # ADDED
            'phase_total_days': phase_total_days,  # ADDED
            'current_vpd': float(current_vpd),
            'vpd_target_min': float(vpd_min),
            'vpd_target_max': float(vpd_max),
            'current_temp': float(avg_temp),
            'current_humidity': float(avg_humidity),
            'temp_target': float(temp_target),
            'humidity_min': float(humidity_min),
            'humidity_max': float(humidity_max),
            'process_active': process_active,
            'equipment': equipment,  # ADDED
            'supply_temp': float(supply_temp) if supply_temp is not None else None,
            'supply_humidity': float(supply_humidity) if supply_humidity is not None else None,
            'supply_vpd': float(supply_vpd) if supply_vpd is not None else None,
            'supply_dew_point': float(supply_dew_point) if supply_dew_point is not None else None,
            'timestamp': datetime.now().isoformat(),
            'debug': debug_info
        })
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        # Return default values on error so the display still works
        return jsonify({
            'error': str(e),
            'current_vpd': 0.75,
            'vpd_target_min': 0.7,
            'vpd_target_max': 0.8,
            'current_phase': 'ERROR',
            'current_temp': 68.0,
            'current_humidity': 60.0
        }), 500

@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    """Get sensor readings - real sensors only for hardware mode"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    # Expected sensor structure for frontend
    sensors = {
        'dry_room_1': {'temperature': None, 'humidity': None, 'timestamp': None},
        'dry_room_2': {'temperature': None, 'humidity': None, 'timestamp': None},
        'dry_room_3': {'temperature': None, 'humidity': None, 'timestamp': None},
        'dry_room_4': {'temperature': None, 'humidity': None, 'timestamp': None},
        'supply_duct': {'temperature': None, 'humidity': None, 'timestamp': None},
        'return_duct': {'temperature': None, 'humidity': None, 'timestamp': None},
        'air_room': {'temperature': None, 'humidity': None, 'timestamp': None}
    }
    
    # In hardware mode, get ONLY real sensor data
    if controller.hardware_mode and controller.sensor_manager:
        # Read the actual hardware sensors
        for sensor_name in ['dry_room_1', 'supply_duct']:
            if sensor_name in controller.sensor_manager.sensors:
                reading = controller.sensor_manager.read_sensor(sensor_name)
                if reading:
                    sensors[sensor_name] = {
                        'temperature': reading.get('temperature'),
                        'humidity': reading.get('humidity'),
                        'timestamp': reading.get('timestamp', datetime.now()).isoformat() if reading.get('timestamp') else datetime.now().isoformat()
                    }
    
    return jsonify(sensors)

@app.route('/api/sensors/<sensor_id>', methods=['POST'])
def update_sensor(sensor_id):
    """Update sensor reading (for testing or manual input)"""
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
    
    return jsonify({
        k: v.value for k, v in controller.equipment_states.items()
    })

@app.route('/api/equipment/<equipment_id>/toggle', methods=['POST'])
def toggle_equipment(equipment_id):
    """Toggle equipment state"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        from software.control.vpd_controller import EquipmentState
        
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

@app.route('/api/equipment/<equipment_id>', methods=['POST'])
def control_equipment(equipment_id):
    """Manual equipment control override"""
    if not check_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    if not data or 'state' not in data:
        return jsonify({'error': 'Missing state'}), 400
    
    # In production, this would trigger actual hardware control
    try:
        state = data['state'].upper()
        # Validate state
        if state not in ['ON', 'OFF', 'IDLE']:
            return jsonify({'error': 'Invalid state'}), 400
        
        logger.info(f"Manual override: {equipment_id} -> {state}")
        # Here you would add actual equipment control
        
        return jsonify({'success': True, 'equipment': equipment_id, 'state': state})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/setpoint', methods=['GET', 'POST'])
def manage_setpoint():
    """Get or update VPD setpoint"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    if request.method == 'GET':
        setpoint = controller.calculate_linear_transition()
        return jsonify({
            'temp_target': setpoint.temp_target,
            'temp_tolerance': setpoint.temp_tolerance,
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
        # Update setpoint for current phase
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
    
    else:  # POST - Manual phase advance
        if not check_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.json
        if 'phase' in data:
            # Manual phase override
            logger.warning(f"Manual phase override: {data['phase']}")
            # Update controller phase here
            
        return jsonify({'success': True})

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get system alerts and warnings"""
    alerts = []
    
    if controller:
        avg_temp, avg_humidity, avg_dew_point, avg_vpd = controller.get_dry_room_conditions()
        setpoint = controller.calculate_linear_transition()
        
        # Check VPD deviation
        if avg_vpd < setpoint.vpd_min - 0.2 or avg_vpd > setpoint.vpd_max + 0.2:
            alerts.append({
                'level': 'critical',
                'message': f'VPD critically out of range: {avg_vpd:.2f} kPa',
                'timestamp': datetime.now().isoformat()
            })
        elif avg_vpd < setpoint.vpd_min or avg_vpd > setpoint.vpd_max:
            alerts.append({
                'level': 'warning',
                'message': f'VPD out of range: {avg_vpd:.2f} kPa (target: {setpoint.vpd_min:.1f}-{setpoint.vpd_max:.1f})',
                'timestamp': datetime.now().isoformat()
            })
        
        # Check temperature
        if avg_temp > controller.emergency_temp_max or avg_temp < controller.emergency_temp_min:
            alerts.append({
                'level': 'critical',
                'message': f'Temperature emergency: {avg_temp:.1f}°F',
                'timestamp': datetime.now().isoformat()
            })
        
        # Check humidity
        if avg_humidity > controller.emergency_humidity_max or avg_humidity < controller.emergency_humidity_min:
            alerts.append({
                'level': 'critical',
                'message': f'Humidity emergency: {avg_humidity:.1f}%',
                'timestamp': datetime.now().isoformat()
            })
    
    return jsonify(alerts)

@app.route('/api/history/<timeframe>', methods=['GET'])
def get_history(timeframe):
    """Get historical data for graphs
    timeframe: '1h', '6h', '24h', '7d'
    """
    # In production, this would query a time-series database
    # For now, return mock data
    
    data_points = {
        '1h': 60,    # 1 point per minute
        '6h': 72,    # 1 point per 5 minutes
        '24h': 96,   # 1 point per 15 minutes
        '7d': 168    # 1 point per hour
    }
    
    points = data_points.get(timeframe, 24)
    
    # Generate mock historical data
    import random
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
        # Return current configuration
        if controller:
            config = {
                'control_interval': 10,  # seconds
                'min_cycle_time': controller.min_cycle_time,
                'dehum_min_cycle': controller.dehum_min_cycle,
                'emergency_temp_max': controller.emergency_temp_max,
                'emergency_temp_min': controller.emergency_temp_min,
                'emergency_humidity_max': controller.emergency_humidity_max,
                'emergency_humidity_min': controller.emergency_humidity_min,
                'target_water_activity': controller.target_water_activity
            }
        else:
            config = {'error': 'Controller not initialized'}
        
        return jsonify(config)
    
    else:  # POST
        if not check_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.json
        # Update configuration
        logger.info(f"Configuration update: {data}")
        
        return jsonify({'success': True})
    
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

# WebSocket events for real-time updates

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
        time.sleep(5)  # Broadcast every 5 seconds
        if controller:
            status = controller.get_system_status()
            socketio.emit('status_update', status, to='/')

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'controller_active': controller is not None
    })

@app.route('/api/process/start', methods=['POST'])
def start_process():
    """Start fresh drying process or resume from emergency"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        from software.control.vpd_controller import DryingPhase
        
        data = request.get_json() or {}
        resume_from_emergency = data.get('resume_from_emergency', False)
        resume_from_hold = data.get('resume_from_hold', False)
        restart_process = data.get('restart_process', False)
        
        if resume_from_emergency:
            # Resume existing process from emergency
            controller.process_active = True
            # If process_start_time was cleared, restore it
            if not hasattr(controller, 'process_start_time') or controller.process_start_time is None:
                controller.process_start_time = datetime.now()  # Restore with current time
            # Keep existing phase and times
            logger.info(f"Process RESUMED from emergency - Phase: {controller.current_phase}")
            
            # Clear emergency flag
            state_manager = StateManager()
            saved_state = state_manager.load_state()
            saved_state['emergency_stop'] = False
            state_manager.save_state(saved_state)
            
            # Force equipment controller to sync hardware state immediately
            if equipment_controller and hasattr(equipment_controller, 'sync_hardware_state'):
                logger.info("Syncing hardware state after emergency resume")
                equipment_controller.sync_hardware_state()
            
            return jsonify({
                'success': True,
                'message': 'Process resumed from emergency',
                'phase': controller.current_phase.value if hasattr(controller.current_phase, 'value') else str(controller.current_phase)
            })
        elif resume_from_hold and hasattr(controller, 'process_start_time') and controller.process_start_time:
            # Resume existing process from hold
            controller.process_active = True
            # Keep existing phase and times
            logger.info(f"Process RESUMED from hold - Phase: {controller.current_phase}")
            
            return jsonify({
                'success': True,
                'message': 'Process resumed from hold',
                'phase': controller.current_phase.value if hasattr(controller.current_phase, 'value') else str(controller.current_phase)
            })
        elif restart_process:
            # Restart existing process - reset timers but keep current phase
            controller.process_active = True
            controller.process_start_time = datetime.now()
            controller.phase_start_time = datetime.now()
            # Keep current phase
            logger.info(f"Process RESTARTED - Phase: {controller.current_phase}")
            
            return jsonify({
                'success': True,
                'message': 'Process restarted',
                'phase': controller.current_phase.value if hasattr(controller.current_phase, 'value') else str(controller.current_phase)
            })
        else:
            # Start fresh process
            controller.process_active = True
            controller.process_start_time = datetime.now()
            controller.phase_start_time = datetime.now()
            controller.current_phase = DryingPhase.DRY_INITIAL
            
            # Save state
            state_manager = StateManager()
            state_manager.save_state({
                'process_active': True,
                'current_phase': 'dry_initial',
                'process_start_time': controller.process_start_time,
                'phase_start_time': controller.phase_start_time,
                'equipment_states': {}  # Will be updated by control loop
            })
            
            logger.info("Drying process STARTED - Phase: DRY_INITIAL")
            
            return jsonify({
                'success': True,
                'message': 'Drying process started',
                'phase': 'DRY_INITIAL'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process/hold', methods=['POST'])
def hold_process():
    """Jump to storage/hold mode"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        from software.control.vpd_controller import DryingPhase
        
        controller.current_phase = DryingPhase.STORAGE
        controller.phase_start_time = datetime.now()
        
        # Force equipment states for storage mode immediately
        if equipment_controller:
            logger.info("Forcing equipment states for STORAGE mode")
            
            # Storage mode: fans running, humidity monitoring active
            storage_states = {
                'mini_split': 'ON',    # Maintain temperature
                'supply_fan': 'ON',    # Keep air circulating
                'return_fan': 'ON',    # Keep air circulating
                'hum_fan': 'ON',       # Always on for humidity monitoring
                'hum_solenoid': 'OFF', # Will be controlled by humidity
                'dehum': 'OFF',        # Will be controlled by humidity
                'erv': 'OFF'           # No fresh air exchange
            }
            
            # Apply states directly
            for equipment, state in storage_states.items():
                if equipment in equipment_controller.actual_states:
                    equipment_controller.actual_states[equipment] = state
                    equipment_controller._apply_state(equipment, state)
            
            # Update VPD controller states
            from software.control.vpd_controller import EquipmentState
            for equipment, state in equipment_controller.actual_states.items():
                controller.equipment_states[equipment] = \
                    EquipmentState.ON if state == 'ON' else EquipmentState.OFF
            
            logger.info(f"STORAGE mode states applied: {equipment_controller.actual_states}")
        
        # Save state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': True,
            'current_phase': 'storage',
            'process_start_time': controller.process_start_time,
            'phase_start_time': controller.phase_start_time,
            'equipment_states': equipment_controller.actual_states if equipment_controller else {}
        })
        
        logger.info("Process put on HOLD - entering STORAGE mode")
        
        return jsonify({
            'success': True,
            'message': 'Process on hold - storage mode active'
        })
    except Exception as e:
        logger.error(f"Hold process error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/process/stop', methods=['POST'])  
def stop_process():
    """Stop process completely"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        controller.process_active = False
        controller.current_phase = DryingPhase.IDLE if hasattr(DryingPhase, 'IDLE') else DryingPhase.STORAGE
        
        # Clear saved state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': False,
            'current_phase': 'idle',
            'process_start_time': None,
            'phase_start_time': None,
            'equipment_states': {}
        })
        
        logger.info("Process STOPPED - system idle")
        
        return jsonify({
            'success': True,
            'message': 'Process stopped'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop - turn off ALL equipment"""
    logger.critical("🔴 EMERGENCY STOP ACTIVATED")
    
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        from software.control.vpd_controller import EquipmentState
        
        # Stop the process
        controller.process_active = False
        # Don't change phase during emergency - keep current phase for resume
        # controller.current_phase = DryingPhase.IDLE if hasattr(DryingPhase, 'IDLE') else DryingPhase.STORAGE
        
        # Turn off ALL equipment using equipment controller
        if equipment_controller and hasattr(equipment_controller, 'emergency_stop'):
            equipment_controller.emergency_stop()
            logger.info("Equipment controller emergency_stop() executed")
        else:
            # Fallback: manually turn off all equipment
            if hasattr(controller, 'equipment_states'):
                for equipment in controller.equipment_states.keys():
                    controller.equipment_states[equipment] = EquipmentState.OFF
                logger.info("All equipment turned OFF via controller")
        
        # Save emergency state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': False,
            'current_phase': controller.current_phase.value if hasattr(controller.current_phase, 'value') else str(controller.current_phase),
            'process_start_time': controller.process_start_time,  # Keep existing start time
            'phase_start_time': controller.phase_start_time,
            'equipment_states': {k: 'OFF' for k in controller.equipment_states.keys() if hasattr(controller, 'equipment_states')},
            'emergency_stop': True  # Flag to indicate emergency state
        })
        
        # Get current equipment states for response
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

@app.route('/api/session/start', methods=['POST'])
def start_session():
    """Start a new drying session"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        data = request.json or {}
        
        # Set default values if not provided
        drying_days = data.get('drying_days', 4)
        curing_days = data.get('curing_days', 4)
        target_water_activity = data.get('target_water_activity', 0.62)
        
        # Initialize session
        controller.process_start_time = datetime.now()
        controller.process_active = True
        controller.current_phase = DryingPhase.DRY_INITIAL
        controller.phase_start_time = datetime.now()
        controller.estimated_water_activity = 0.85  # Starting point
        controller.target_water_activity = target_water_activity
        
        # Save state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': True,
            'current_phase': 'dry_initial',
            'process_start_time': controller.process_start_time,
            'phase_start_time': controller.phase_start_time,
            'equipment_states': {}
        })
        
        logger.info(f"Session started: {drying_days}d drying, {curing_days}d curing, target aW={target_water_activity}")
        
        return jsonify({
            'success': True,
            'message': f'Session started with {drying_days}d drying, {curing_days}d curing',
            'session_id': f"session_{int(datetime.now().timestamp())}"
        })
    except Exception as e:
        logger.error(f"Start session error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/pause', methods=['POST'])
def pause_session():
    """Pause the current session"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        controller.process_active = False
        
        # Save state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': False,
            'current_phase': controller.current_phase.value if hasattr(controller.current_phase, 'value') else str(controller.current_phase),
            'process_start_time': controller.process_start_time,
            'phase_start_time': controller.phase_start_time,
            'equipment_states': {}
        })
        
        logger.info("Session paused")
        
        return jsonify({
            'success': True,
            'message': 'Session paused'
        })
    except Exception as e:
        logger.error(f"Pause session error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/stop', methods=['POST'])
def stop_session():
    """Stop the current session"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        controller.process_active = False
        controller.current_phase = DryingPhase.COMPLETE
        
        # Save state
        state_manager = StateManager()
        state_manager.save_state({
            'process_active': False,
            'current_phase': 'complete',
            'process_start_time': controller.process_start_time,
            'phase_start_time': controller.phase_start_time,
            'equipment_states': {}
        })
        
        logger.info("Session stopped")
        
        return jsonify({
            'success': True,
            'message': 'Session stopped'
        })
    except Exception as e:
        logger.error(f"Stop session error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    """Get or update system settings"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        if request.method == 'GET':
            # Return current settings
            settings = {
                'process': {
                    'drying_time_days': 4,
                    'curing_time_days': 4,
                    'target_water_activity': controller.target_water_activity if hasattr(controller, 'target_water_activity') else 0.62,
                    'linear_adjustment': True
                },
                'vpd_control': {
                    'control_mode': 'vpd',
                    'vpd_setpoint': 0.75,
                    'vpd_tolerance': 0.1,
                    'vpd_alert_threshold': 0.2,
                    'temperature_setpoint': controller.mini_split_setpoint if hasattr(controller, 'mini_split_setpoint') else 68,
                    'humidity_setpoint': 62.5
                },
                'equipment': {
                    'fan_speed_percent': 60,
                    'erv_exchange_rate': 4,
                    'mini_split_mode': 'auto',
                    'manual_override': False,
                    'safety_temp_min': controller.emergency_temp_min if hasattr(controller, 'emergency_temp_min') else 60,
                    'safety_temp_max': controller.emergency_temp_max if hasattr(controller, 'emergency_temp_max') else 75
                },
                'data_visualization': {
                    'chart_time_range': 'hourly'
                }
            }
            
            return jsonify({'success': True, 'settings': settings})
        
        else:  # POST
            data = request.json
            logger.info(f"Settings update requested: {data}")
            
            # Apply settings to controller
            if 'process' in data:
                if hasattr(controller, 'target_water_activity'):
                    controller.target_water_activity = data['process'].get('target_water_activity', 0.62)
            
            if 'vpd_control' in data:
                if hasattr(controller, 'mini_split_setpoint'):
                    controller.mini_split_setpoint = data['vpd_control'].get('temperature_setpoint', 68)
            
            if 'equipment' in data:
                if hasattr(controller, 'emergency_temp_min'):
                    controller.emergency_temp_min = data['equipment'].get('safety_temp_min', 60)
                if hasattr(controller, 'emergency_temp_max'):
                    controller.emergency_temp_max = data['equipment'].get('safety_temp_max', 75)
            
            # Save settings (in production, this would save to persistent storage)
            logger.info("Settings updated successfully")
            
            return jsonify({'success': True, 'message': 'Settings updated'})
            
    except Exception as e:
        logger.error(f"Settings error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    """Export session data as CSV"""
    try:
        # In production, this would generate actual CSV from database
        # For now, return a simple CSV response
        
        csv_data = "timestamp,vpd,temperature,humidity,dew_point,phase\n"
        csv_data += "2024-01-01 10:00:00,0.75,68.5,62.3,55.2,dry_initial\n"
        csv_data += "2024-01-01 11:00:00,0.78,69.1,61.8,55.8,dry_initial\n"
        
        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=cannabis-dryer-data-{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Export CSV error: {e}")
        return jsonify({'error': str(e)}), 500

# Simple web dashboard (for testing without the touchscreen GUI)
def dashboard():
    """Simple web dashboard for monitoring"""
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cannabis Drying Control System</title>
        <style>
            body { 
                font-family: 'Inter', Arial, sans-serif; 
                margin: 20px; 
                background: linear-gradient(135deg, #1a1a2e, #0f0f1e);
                color: white;
            }
            .container { max-width: 1400px; margin: 0 auto; }
            h1 { 
                color: #00E515; 
                text-align: center;
                text-shadow: 0 0 20px rgba(0, 229, 21, 0.5);
                margin-bottom: 30px;
            }
            .status-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .status-card { 
                background: linear-gradient(135deg, #8858ed, #6633bb);
                padding: 20px; 
                margin: 10px 0; 
                border-radius: 12px;
                box-shadow: 0 8px 16px rgba(136, 88, 237, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .metric { 
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin: 15px 0;
                padding: 10px;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 8px;
            }
            .label { 
                color: rgba(255, 255, 255, 0.9);
                font-size: 14px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .value { 
                font-size: 24px; 
                font-weight: bold; 
                color: #00E515;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            }
            .equipment { 
                display: inline-block; 
                padding: 8px 16px; 
                margin: 5px; 
                border-radius: 6px;
                font-weight: 600;
                text-transform: uppercase;
                font-size: 12px;
                letter-spacing: 0.5px;
                transition: all 0.3s ease;
            }
            .equipment.ON { 
                background: linear-gradient(135deg, #00C310, #00E515); 
                color: black;
                box-shadow: 0 4px 8px rgba(0, 227, 21, 0.3);
            }
            .equipment.OFF { 
                background: #444;
                color: #999;
            }
            .equipment.IDLE { 
                background: linear-gradient(135deg, #FFA500, #FFB700);
                color: black;
            }
            .phase-indicator {
                text-align: center;
                padding: 15px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 8px;
                margin-bottom: 10px;
            }
            .phase-name {
                font-size: 18px;
                font-weight: bold;
                color: #00E515;
                margin-bottom: 5px;
            }
            .phase-description {
                font-size: 14px;
                color: rgba(255, 255, 255, 0.8);
            }
            .progress-bar {
                width: 100%;
                height: 30px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 15px;
                overflow: hidden;
                margin: 10px 0;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #00E515, #10B981);
                transition: width 0.5s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                color: black;
                font-weight: bold;
            }
        </style>
        <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>🌿 Cannabis Precision Drying System</h1>
            
            <div class="status-grid">
                <div class="status-card">
                    <h2>System Status</h2>
                    <div class="phase-indicator">
                        <div class="phase-name" id="phase">--</div>
                        <div class="phase-description" id="phase-desc">--</div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress" style="width: 0%">0%</div>
                    </div>
                    <div class="metric">
                        <span class="label">Water Activity</span>
                        <span class="value" id="water-activity">--</span>
                    </div>
                </div>
                
                <div class="status-card">
                    <h2>Environmental Conditions</h2>
                    <div class="metric">
                        <span class="label">VPD (kPa)</span>
                        <span class="value" id="vpd">--</span>
                    </div>
                    <div class="metric">
                        <span class="label">Temperature (°F)</span>
                        <span class="value" id="temperature">--</span>
                    </div>
                    <div class="metric">
                        <span class="label">Humidity (%)</span>
                        <span class="value" id="humidity">--</span>
                    </div>
                    <div class="metric">
                        <span class="label">Dew Point (°F)</span>
                        <span class="value" id="dew-point">--</span>
                    </div>
                </div>
                
                <div class="status-card">
                    <h2>Equipment Status</h2>
                    <div id="equipment"></div>
                </div>
                
                <div class="status-card">
                    <h2>Sensor Readings</h2>
                    <div id="sensors"></div>
                </div>
            </div>
        </div>
        
        <script>
            const socket = io();
            
            socket.on('connect', function() {
                console.log('Connected to server');
            });
            
            socket.on('status_update', function(data) {
                // Update phase
                document.getElementById('phase').textContent = data.phase.replace('_', ' ').toUpperCase();
                document.getElementById('phase-desc').textContent = data.phase_description;
                
                // Update progress
                const progressEl = document.getElementById('progress');
                progressEl.style.width = data.progress + '%';
                progressEl.textContent = data.progress.toFixed(1) + '%';
                
                // Update metrics
                document.getElementById('vpd').textContent = data.vpd_current + ' / ' + data.vpd_target;
                document.getElementById('temperature').textContent = data.temperature + '°F';
                document.getElementById('humidity').textContent = data.humidity + '%';
                document.getElementById('dew-point').textContent = data.dew_point + '°F';
                document.getElementById('water-activity').textContent = '~' + data.water_activity_estimate;
                
                // Update equipment
                const equipmentDiv = document.getElementById('equipment');
                equipmentDiv.innerHTML = '';
                for (const [key, value] of Object.entries(data.equipment)) {
                    const span = document.createElement('span');
                    span.className = 'equipment ' + value;
                    span.textContent = key.replace('_', ' ');
                    equipmentDiv.appendChild(span);
                }
                
                // Update sensors
                const sensorsDiv = document.getElementById('sensors');
                sensorsDiv.innerHTML = '';
                for (const [key, value] of Object.entries(data.sensors)) {
                    const div = document.createElement('div');
                    div.className = 'metric';
                    div.innerHTML = `
                        <span class="label">${key.replace('_', ' ').toUpperCase()}</span>
                        <span class="value" style="font-size: 16px">${value.temperature}°F / ${value.humidity}%</span>
                    `;
                    sensorsDiv.appendChild(div);
                }
            });
            
            // Request updates every 2 seconds
            setInterval(function() {
                socket.emit('request_update');
            }, 2000);
            
            // Initial request
            socket.emit('request_update');
        </script>
    </body>
    </html>
    ''')

# Start background update thread
update_thread = None

def start_background_tasks():
    """Start background tasks"""
    global update_thread
    if update_thread is None:
        update_thread = threading.Thread(target=broadcast_updates, daemon=True)
        update_thread.start()
        logger.info("Background update thread started")

@app.route('/api/debug/equipment', methods=['GET'])
def debug_equipment():
    """Debug endpoint to check equipment states and GPIO status"""
    if not equipment_controller:
        return jsonify({'error': 'Equipment controller not initialized'}), 503
    
    try:
        # Get software states
        software_states = equipment_controller.actual_states.copy()
        
        # Try to read hardware states
        hardware_states = {}
        if hasattr(equipment_controller, 'sync_hardware_state'):
            # This will update actual_states to match hardware
            equipment_controller.sync_hardware_state()
            hardware_states = equipment_controller.actual_states.copy()
        
        # Get GPIO initialization status
        gpio_status = {
            'initialized': equipment_controller.gpio_initialized,
            'pins': equipment_controller.gpio_pins if hasattr(equipment_controller, 'gpio_pins') else {}
        }
        
        return jsonify({
            'software_states': software_states,
            'hardware_states': hardware_states,
            'gpio_status': gpio_status,
            'control_modes': {k: v.value if hasattr(v, 'value') else str(v) 
                            for k, v in equipment_controller.control_modes.items()},
            'process_active': equipment_controller.vpd_controller.process_active if hasattr(equipment_controller, 'vpd_controller') else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/gpio', methods=['GET'])
def debug_gpio():
    """Debug endpoint to check GPIO status"""
    if not equipment_controller:
        return jsonify({'error': 'Equipment controller not initialized'}), 503
    
    try:
        gpio_info = {
            'gpio_available': equipment_controller.gpio_initialized,
            'pins': {}
        }
        
        if equipment_controller.gpio_initialized:
            try:
                import RPi.GPIO as GPIO
                for equipment, pin in equipment_controller.gpio_pins.items():
                    try:
                        current_state = GPIO.input(pin)
                        gpio_info['pins'][equipment] = {
                            'pin': pin,
                            'current_state': current_state,
                            'expected_for_on': 'LOW (0)',
                            'expected_for_off': 'HIGH (1)'
                        }
                    except Exception as e:
                        gpio_info['pins'][equipment] = {
                            'pin': pin,
                            'error': str(e)
                        }
            except ImportError:
                gpio_info['gpio_available'] = False
                gpio_info['error'] = 'RPi.GPIO not available'
        
        return jsonify(gpio_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500