#!/usr/bin/env python3
"""
Flask API Server for Cannabis Drying Control System
Provides REST API for GUI interaction and remote monitoring
"""

from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
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

def init_controller(ctrl):
    """Initialize the controller reference"""
    global controller
    controller = ctrl
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
    """Get current system status"""
    if not controller:
        return jsonify({'error': 'System not initialized'}), 503
    
    try:
        status = controller.get_system_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500

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