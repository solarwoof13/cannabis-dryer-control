#!/usr/bin/env python3
"""
Local Test Server for Cannabis Dryer Control System
Run this on your Mac to test the GUI without the Raspberry Pi
"""

from flask import Flask, jsonify, send_from_directory
import random
import time
from datetime import datetime

app = Flask(__name__, static_folder='touchscreen')

# Simulated sensor data
def get_simulated_data():
    """Generate realistic test data for the GUI"""
    # Simulate gradual VPD changes
    base_vpd = 0.75
    vpd_variation = random.uniform(-0.2, 0.3)
    current_vpd = base_vpd + vpd_variation
    
    return {
        'current_vpd': round(current_vpd, 2),
        'vpd_target_min': 0.70,
        'vpd_target_max': 0.80,
        'mode': 'CURE MODE',
        'phase_day': 2,
        'phase_total_days': 4,
        'temperature': round(68 + random.uniform(-2, 2), 1),
        'humidity': round(60 + random.uniform(-5, 5), 1),
        'sensors': {
            'dry1': {
                'temp': round(68 + random.uniform(-1, 1), 1),
                'humidity': round(60 + random.uniform(-3, 3), 1),
                'vpd': round(0.75 + random.uniform(-0.1, 0.1), 2)
            },
            'dry2': {
                'temp': round(68 + random.uniform(-1, 1), 1),
                'humidity': round(60 + random.uniform(-3, 3), 1),
                'vpd': round(0.75 + random.uniform(-0.1, 0.1), 2)
            },
            'dry3': {
                'temp': round(68 + random.uniform(-1, 1), 1),
                'humidity': round(60 + random.uniform(-3, 3), 1),
                'vpd': round(0.75 + random.uniform(-0.1, 0.1), 2)
            },
            'dry4': {
                'temp': round(68 + random.uniform(-1, 1), 1),
                'humidity': round(60 + random.uniform(-3, 3), 1),
                'vpd': round(0.75 + random.uniform(-0.1, 0.1), 2)
            },
            'air': {
                'temp': round(70 + random.uniform(-2, 2), 1),
                'humidity': round(55 + random.uniform(-5, 5), 1),
                'vpd': round(0.9 + random.uniform(-0.2, 0.2), 2)
            },
            'supply': {
                'temp': round(67 + random.uniform(-1, 1), 1),
                'humidity': round(62 + random.uniform(-3, 3), 1),
                'vpd': round(0.7 + random.uniform(-0.1, 0.1), 2)
            }
        },
        'equipment': {
            'dehumidifier': random.choice(['ON', 'OFF', 'IDLE']),
            'humidifier': random.choice(['OFF', 'IDLE']),
            'mini_split': 'ON',
            'erv': random.choice(['ON', 'AUTO']),
            'exhaust_fan': random.choice(['ON', 'OFF']),
            'supply_fan': 'ON'
        },
        'drying_progress': 100,  # Drying complete
        'curing_progress': 45,   # 45% through curing
        'water_activity': 0.62,
        'timestamp': datetime.now().isoformat()
    }

# Routes
@app.route('/')
def index():
    """Serve the main index.html"""
    return send_from_directory('touchscreen', 'index.html')

@app.route('/index.html')
def index_html():
    """Serve index.html directly"""
    return send_from_directory('touchscreen', 'index.html')

@app.route('/settings')
def settings():
    """Serve the settings page"""
    return send_from_directory('touchscreen', 'settings.html')

@app.route('/analytics')
def analytics():
    """Serve the analytics page"""
    return send_from_directory('touchscreen', 'analytics.html')

@app.route('/api/status')
def api_status():
    """API endpoint that the GUI calls for updates"""
    return jsonify(get_simulated_data())

@app.route('/api/emergency-stop', methods=['POST'])
def emergency_stop():
    """Handle emergency stop"""
    print("⚠️  EMERGENCY STOP TRIGGERED!")
    return jsonify({'status': 'emergency_stop_activated'})

@app.route('/api/sensor/<sensor_id>')
def get_sensor(sensor_id):
    """Get specific sensor data"""
    data = get_simulated_data()
    if sensor_id in data['sensors']:
        return jsonify(data['sensors'][sensor_id])
    return jsonify({'error': 'Sensor not found'}), 404

@app.route('/api/equipment/<equipment_id>/toggle', methods=['POST'])
def toggle_equipment(equipment_id):
    """Toggle equipment state (simulated)"""
    print(f"Toggling {equipment_id}")
    return jsonify({
        'equipment': equipment_id,
        'new_state': random.choice(['ON', 'OFF', 'AUTO'])
    })

@app.route('/api/config')
def get_config():
    """Get system configuration"""
    return jsonify({
        'system_name': 'Cannabis Dryer Test System',
        'location': 'Local Test Environment',
        'profiles': {
            'standard': {'name': 'Standard 8-Day', 'days': 8},
            'fast': {'name': 'Fast 6-Day', 'days': 6},
            'gentle': {'name': 'Gentle 10-Day', 'days': 10}
        },
        'current_profile': 'standard'
    })

# Serve static files (CSS, JS, images if any)
@app.route('/<path:path>')
def serve_static(path):
    """Serve any other static files"""
    return send_from_directory('touchscreen', path)

if __name__ == '__main__':
    print("🌿 Cannabis Dryer Control System - Local Test Server")
    print("=" * 50)
    print("📍 Starting server at http://127.0.0.1:8080")
    print("📂 Serving files from: ./touchscreen/")
    print("=" * 50)
    print("\n✅ Server is running!")
    print("🌐 Open http://127.0.0.1:8080 in your browser")
    print("🛑 Press Ctrl+C to stop the server\n")
    
    # Run the Flask development server on localhost only with a different port
    app.run(host='127.0.0.1', port=8080, debug=True)