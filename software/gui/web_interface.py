#!/usr/bin/env python3
"""
Cannabis Dryer Web Interface Backend with Data Logging
Flask-SocketIO server for real-time monitoring and comprehensive data logging

Enhanced with historical data tracking, analytics, and export capabilities.
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import json
import logging
from datetime import datetime, timedelta
import threading
import time
from typing import Dict, Any
import os
import sys
import tempfile
import zipfile

# Add the control directory to Python path
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
control_dir = os.path.join(parent_dir, 'control')
sys.path.insert(0, control_dir)

from vpd_calculator import ResearchOptimizedVPD, DryingPhase
from intelligent_controller import IntelligentController, DisturbanceLevel
from data_logger import DataLogger, EventType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'cannabis_dryer_secret_key_change_in_production'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global instances
controller = None
data_logger = None
process_start_time = None
monitoring_active = False

class WebMonitoringService:
    """Enhanced service class with data logging capabilities"""
    
    def __init__(self):
        self.controller = IntelligentController()
        self.data_logger = DataLogger("cannabis_dryer_data.db")
        self.mock_sensor_data = self._generate_mock_sensor_data()
        self.monitoring_thread = None
        self.monitoring_active = False
        self.current_session_id = None
        
    def _generate_mock_sensor_data(self) -> Dict:
        """Generate realistic mock sensor data for development"""
        import random
        
        # Base conditions for current drying phase
        base_temp = 67.5 + random.uniform(-0.5, 0.5)
        base_humidity = 58.0 + random.uniform(-2.0, 2.0)
        
        return {
            "zone_1": {
                "temperature": base_temp + random.uniform(-0.3, 0.3),
                "humidity": base_humidity + random.uniform(-1.0, 1.0),
                "sensor_id": "SHT31_Zone1",
                "last_update": datetime.now().isoformat()
            },
            "zone_2": {
                "temperature": base_temp + random.uniform(-0.2, 0.2),
                "humidity": base_humidity + random.uniform(-0.8, 0.8),
                "sensor_id": "SHT31_Zone2", 
                "last_update": datetime.now().isoformat()
            },
            "zone_3": {
                "temperature": base_temp + random.uniform(-0.4, 0.4),
                "humidity": base_humidity + random.uniform(-1.2, 1.2),
                "sensor_id": "SHT31_Zone3",
                "last_update": datetime.now().isoformat()
            },
            "zone_4": {
                "temperature": base_temp + random.uniform(-0.3, 0.3),
                "humidity": base_humidity + random.uniform(-0.9, 0.9),
                "sensor_id": "SHT31_Zone4",
                "last_update": datetime.now().isoformat()
            },
            "air_room": {
                "temperature": base_temp + 1.2 + random.uniform(-0.5, 0.5),
                "humidity": base_humidity - 3.0 + random.uniform(-1.5, 1.5),
                "sensor_id": "SHT31_AirRoom",
                "last_update": datetime.now().isoformat()
            },
            "supply_duct": {
                "temperature": base_temp - 0.8 + random.uniform(-0.3, 0.3),
                "humidity": base_humidity + 1.5 + random.uniform(-1.0, 1.0),
                "sensor_id": "SHT31_Supply",
                "last_update": datetime.now().isoformat()
            }
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status for web interface with logging data"""
        global process_start_time
        
        # Get current sensor data
        sensor_data = self._generate_mock_sensor_data()
        
        # Log sensor data if session is active
        if self.current_session_id:
            self.data_logger.log_sensor_reading(sensor_data)
            self.data_logger.log_equipment_status(self.controller.current_settings)
        
        # Analyze with intelligent controller
        trends = self.controller.analyze_sensor_trends(sensor_data)
        disturbance_level = self.controller.detect_environmental_disturbance(trends)
        
        # Calculate average conditions
        drying_zones = [sensor_data[f"zone_{i}"] for i in range(1, 5)]
        avg_temp = sum(zone["temperature"] for zone in drying_zones) / len(drying_zones)
        avg_humidity = sum(zone["humidity"] for zone in drying_zones) / len(drying_zones)
        
        # Get VPD calculation
        vpd_reading = self.controller.vpd_calc.calculate_vpd_from_conditions(avg_temp, avg_humidity)
        
        # Get current phase if process is running
        current_phase = DryingPhase.INITIAL_MOISTURE_REMOVAL
        phase_progress = 0.0
        time_remaining = "Not started"
        
        if process_start_time:
            current_phase = self.controller.vpd_calc.get_current_phase_from_elapsed_time(process_start_time)
            phase_progress = self.controller.vpd_calc.calculate_phase_progress(process_start_time, current_phase)
            
            # Calculate time remaining
            total_duration = sum(profile.duration_hours for profile in self.controller.vpd_calc.step_profiles.values())
            elapsed_hours = (datetime.now() - process_start_time).total_seconds() / 3600
            remaining_hours = max(0, total_duration - elapsed_hours)
            time_remaining = f"{remaining_hours:.1f} hours"
        
        # Get target conditions
        target_temp, target_dew, target_rh = self.controller.vpd_calc.get_phase_target_conditions(current_phase, phase_progress)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system_active": process_start_time is not None,
            "process_start_time": process_start_time.isoformat() if process_start_time else None,
            "session_id": self.current_session_id,
            
            # Current conditions
            "current_conditions": {
                "temperature_f": round(avg_temp, 1),
                "humidity_percent": round(avg_humidity, 1),
                "dew_point_f": round(vpd_reading.dew_point_f, 1),
                "vpd_kpa": round(vpd_reading.vpd_kpa, 3),
                "water_activity": round(vpd_reading.estimated_water_activity, 3)
            },
            
            # Target conditions
            "target_conditions": {
                "temperature_f": round(target_temp, 1),
                "humidity_percent": round(target_rh, 1), 
                "dew_point_f": round(target_dew, 1)
            },
            
            # Process status
            "process_status": {
                "current_phase": current_phase.value,
                "phase_progress_percent": round(phase_progress * 100, 1),
                "time_remaining": time_remaining,
                "disturbance_level": disturbance_level.value
            },
            
            # Sensor readings
            "sensor_readings": sensor_data,
            
            # Equipment status
            "equipment_status": self.controller.current_settings,
            
            # Trichome protection
            "trichome_protection": self.controller.get_trichome_protection_status(),
            
            # System health
            "system_health": {
                "all_sensors_online": True,
                "equipment_responding": True,
                "network_connected": True,
                "disk_space_ok": True,
                "database_connected": True
            },
            
            # Data logging status
            "data_logging": {
                "active": self.current_session_id is not None,
                "session_id": self.current_session_id,
                "records_logged": self._get_session_record_count() if self.current_session_id else 0
            }
        }
    
    def _get_session_record_count(self) -> int:
        """Get number of records logged for current session"""
        if not self.current_session_id:
            return 0
        
        try:
            session_data = self.data_logger.get_session_data(self.current_session_id)
            return len(session_data["sensors"]) + len(session_data["equipment"]) + len(session_data["events"])
        except:
            return 0
    
    def start_drying_process(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start drying process with data logging"""
        global process_start_time
        
        try:
            # Generate session ID
            self.current_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            process_start_time = datetime.now()
            
            # Start data logging
            initial_conditions = {
                "config": config,
                "start_conditions": self.get_system_status()["current_conditions"],
                "target_water_activity": 0.62
            }
            
            self.data_logger.start_session(self.current_session_id, initial_conditions)
            
            # Start monitoring if not already running
            if not self.monitoring_active:
                self.start_monitoring()
            
            logger.info(f"Started drying process with data logging: {self.current_session_id}")
            
            return {
                "success": True,
                "session_id": self.current_session_id,
                "start_time": process_start_time.isoformat(),
                "message": "Drying process started with data logging"
            }
            
        except Exception as e:
            logger.error(f"Failed to start drying process: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def stop_drying_process(self, notes: str = "") -> Dict[str, Any]:
        """Stop drying process and finalize data logging"""
        global process_start_time
        
        try:
            if self.current_session_id:
                # End data logging
                final_conditions = {
                    "end_conditions": self.get_system_status()["current_conditions"],
                    "total_runtime_hours": (datetime.now() - process_start_time).total_seconds() / 3600 if process_start_time else 0
                }
                
                self.data_logger.end_session(final_conditions, notes)
                
                session_id = self.current_session_id
                self.current_session_id = None
            else:
                session_id = "no_session"
            
            process_start_time = None
            logger.info(f"Stopped drying process: {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "message": "Drying process stopped and data saved"
            }
            
        except Exception as e:
            logger.error(f"Failed to stop drying process: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def start_monitoring(self):
        """Start background monitoring thread"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("Web monitoring service started with data logging")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        logger.info("Web monitoring service stopped")
    
    def _monitoring_loop(self):
        """Background thread for real-time monitoring with data logging"""
        while self.monitoring_active:
            try:
                # Get system status (includes automatic data logging)
                status = self.get_system_status()
                
                # Emit to all connected clients
                socketio.emit('system_update', status, namespace='/')
                
                # Update every 5 seconds
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(10)  # Wait longer on error

# Initialize monitoring service
monitoring_service = WebMonitoringService()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/analytics')
def analytics():
    """Analytics dashboard page"""
    return render_template('analytics.html')

@app.route('/api/status')
def get_status():
    """API endpoint for current system status"""
    try:
        status = monitoring_service.get_system_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Status API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/start_process', methods=['POST'])
def start_process():
    """API endpoint to start drying process with data logging"""
    try:
        config = request.get_json() or {}
        result = monitoring_service.start_drying_process(config)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Start process error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stop_process', methods=['POST'])
def stop_process():
    """API endpoint to stop drying process"""
    try:
        data = request.get_json() or {}
        notes = data.get('notes', '')
        result = monitoring_service.stop_drying_process(notes)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Stop process error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions')
def get_sessions():
    """API endpoint to get list of all sessions"""
    try:
        # Get all session summaries (simplified for now)
        # In a real implementation, you'd query the database
        return jsonify({
            "sessions": [
                {
                    "session_id": monitoring_service.current_session_id,
                    "start_time": process_start_time.isoformat() if process_start_time else None,
                    "status": "active" if monitoring_service.current_session_id else "completed"
                }
            ] if monitoring_service.current_session_id else []
        })
        
    except Exception as e:
        logger.error(f"Sessions API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/session/<session_id>/data')
def get_session_data(session_id):
    """API endpoint to get data for specific session"""
    try:
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        
        data = monitoring_service.data_logger.get_session_data(session_id, start_dt, end_dt)
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Session data API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/session/<session_id>/analytics')
def get_session_analytics(session_id):
    """API endpoint to get analytics data for charts"""
    try:
        analytics = monitoring_service.data_logger.get_analytics_data(session_id)
        return jsonify(analytics)
        
    except Exception as e:
        logger.error(f"Analytics API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/session/<session_id>/export')
def export_session(session_id):
    """API endpoint to export session data as CSV"""
    try:
        # Create temporary directory for export
        temp_dir = tempfile.mkdtemp()
        export_dir = monitoring_service.data_logger.export_session_csv(session_id, temp_dir)
        
        if export_dir:
            # Create zip file
            zip_path = os.path.join(temp_dir, f"{session_id}_export.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for root, dirs, files in os.walk(export_dir):
                    for file in files:
                        if file.endswith('.csv'):
                            file_path = os.path.join(root, file)
                            zipf.write(file_path, file)
            
            return send_file(zip_path, as_attachment=True, download_name=f"{session_id}_data_export.zip")
        else:
            return jsonify({"error": "Export failed"}), 500
            
    except Exception as e:
        logger.error(f"Export API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/equipment/<equipment_name>', methods=['POST'])
def control_equipment(equipment_name):
    """API endpoint for manual equipment control"""
    try:
        data = request.get_json()
        setting = data.get('setting', 0)
        
        # Update equipment setting
        if equipment_name in monitoring_service.controller.current_settings:
            old_setting = monitoring_service.controller.current_settings[equipment_name]
            monitoring_service.controller.current_settings[equipment_name] = float(setting)
            
            # Log equipment change event
            if monitoring_service.current_session_id:
                monitoring_service.data_logger.log_event(
                    EventType.MANUAL_OVERRIDE,
                    f"Manual control: {equipment_name} changed from {old_setting} to {setting}",
                    {"equipment": equipment_name, "old_setting": old_setting, "new_setting": setting},
                    "info"
                )
            
            return jsonify({
                "success": True,
                "equipment": equipment_name,
                "new_setting": setting
            })
        else:
            return jsonify({"error": f"Unknown equipment: {equipment_name}"}), 400
            
    except Exception as e:
        logger.error(f"Equipment control error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/analytics')
def analytics():
    """Analytics dashboard page"""
    return render_template('analytics.html')

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    
    # Send current status to new client
    try:
        status = monitoring_service.get_system_status()
        emit('system_update', status)
    except Exception as e:
        logger.error(f"Error sending initial status: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('request_status')
def handle_status_request():
    """Handle manual status request from client"""
    try:
        status = monitoring_service.get_system_status()
        emit('system_update', status)
    except Exception as e:
        logger.error(f"Status request error: {e}")

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    
    # Start monitoring service
    monitoring_service.start_monitoring()
    
    try:
        logger.info("Starting Cannabis Dryer Web Interface with Data Logging...")
        logger.info("Access the dashboard at: http://localhost:8080")
        
        # Run the web server
        socketio.run(app, 
                    host='0.0.0.0',  # Allow external connections
                    port=8080, 
                    debug=True,
                    use_reloader=False)  # Disable reloader to prevent threading issues
                    
    except KeyboardInterrupt:
        logger.info("Shutting down web interface...")
        monitoring_service.stop_monitoring()
    except Exception as e:
        logger.error(f"Web interface error: {e}")
        monitoring_service.stop_monitoring()