#!/usr/bin/env python3
"""
Cannabis Drying System - Settings Backend
Handles configuration management, database operations, and API endpoints
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from pathlib import Path

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for touchscreen GUI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_PATH = Path('/home/pi/cannabis-controller/data/settings.db')
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Default settings structure
DEFAULT_SETTINGS = {
    'process': {
        'drying_time_days': 4,
        'curing_time_days': 4,
        'target_water_activity': 0.62,
        'linear_adjustment': True,
        'session_active': False,
        'session_start_time': None,
        'session_pause_time': None,
        'session_status': 'stopped'  # 'running', 'paused', 'stopped'
    },
    'vpd_control': {
        'control_mode': 'vpd',  # 'vpd', 'temperature', 'humidity'
        'vpd_setpoint': 1.2,
        'vpd_tolerance': 0.1,
        'vpd_alert_threshold': 0.3,
        'temperature_setpoint': 72,
        'humidity_setpoint': 55,
        'vpd_min': 1.0,
        'vpd_max': 1.5,
        'vpd_critical_min': 0.6,
        'vpd_critical_max': 2.0
    },
    'equipment': {
        'fan_speed_percent': 60,
        'erv_exchange_rate': 30,
        'mini_split_mode': 'auto',  # 'auto', 'cool', 'heat', 'dry', 'fan'
        'manual_override': False,
        'safety_temp_min': 65,
        'safety_temp_max': 80,
        'safety_humidity_min': 40,
        'safety_humidity_max': 70
    },
    'alerts': {
        'enable_notifications': True,
        'enable_email_alerts': False,
        'enable_sms_alerts': False,
        'alert_email': '',
        'alert_phone': '',
        'vpd_alert_enabled': True,
        'temp_alert_enabled': True,
        'humidity_alert_enabled': True,
        'equipment_alert_enabled': True
    },
    'data_visualization': {
        'chart_time_range': 'hourly',  # 'hourly', 'daily', 'weekly'
        'auto_export': False,
        'export_format': 'csv',  # 'csv', 'pdf'
        'export_interval_hours': 24
    }
}

def init_database():
    """Initialize the database with settings and session tables"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, key)
        )
    ''')
    
    # Session history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_type TEXT NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            status TEXT NOT NULL,
            settings_snapshot TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Settings history table (for tracking changes)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            changed_by TEXT DEFAULT 'touchscreen',
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Initialize with default settings if empty
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        save_all_settings(DEFAULT_SETTINGS, conn)
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def save_all_settings(settings_dict, conn=None):
    """Save all settings to database"""
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        close_conn = True
    
    cursor = conn.cursor()
    
    for category, settings in settings_dict.items():
        for key, value in settings.items():
            # Check if setting exists
            cursor.execute(
                "SELECT value FROM settings WHERE category = ? AND key = ?",
                (category, key)
            )
            existing = cursor.fetchone()
            
            # Convert value to JSON string for storage
            value_str = json.dumps(value)
            
            if existing:
                old_value = existing[0]
                if old_value != value_str:
                    # Update setting
                    cursor.execute(
                        "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE category = ? AND key = ?",
                        (value_str, category, key)
                    )
                    # Log change
                    cursor.execute(
                        "INSERT INTO settings_history (category, key, old_value, new_value) VALUES (?, ?, ?, ?)",
                        (category, key, old_value, value_str)
                    )
            else:
                # Insert new setting
                cursor.execute(
                    "INSERT INTO settings (category, key, value) VALUES (?, ?, ?)",
                    (category, key, value_str)
                )
    
    conn.commit()
    if close_conn:
        conn.close()
    
    logger.info("Settings saved to database")

def load_all_settings():
    """Load all settings from database"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("SELECT category, key, value FROM settings")
    rows = cursor.fetchall()
    
    settings = {}
    for category, key, value in rows:
        if category not in settings:
            settings[category] = {}
        try:
            settings[category][key] = json.loads(value)
        except json.JSONDecodeError:
            settings[category][key] = value
    
    conn.close()
    return settings

def get_setting(category, key):
    """Get a specific setting value"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT value FROM settings WHERE category = ? AND key = ?",
        (category, key)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result:
        try:
            return json.loads(result[0])
        except json.JSONDecodeError:
            return result[0]
    return None

def update_setting(category, key, value):
    """Update a specific setting"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Get old value for history
    cursor.execute(
        "SELECT value FROM settings WHERE category = ? AND key = ?",
        (category, key)
    )
    old_value = cursor.fetchone()
    
    value_str = json.dumps(value)
    
    if old_value:
        cursor.execute(
            "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE category = ? AND key = ?",
            (value_str, category, key)
        )
        # Log change
        cursor.execute(
            "INSERT INTO settings_history (category, key, old_value, new_value) VALUES (?, ?, ?, ?)",
            (category, key, old_value[0], value_str)
        )
    else:
        cursor.execute(
            "INSERT INTO settings (category, key, value) VALUES (?, ?, ?)",
            (category, key, value_str)
        )
    
    conn.commit()
    conn.close()
    
    logger.info(f"Updated setting: {category}.{key} = {value}")

# API Endpoints

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get all current settings"""
    try:
        settings = load_all_settings()
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Save settings from the touchscreen"""
    try:
        settings = request.json
        save_all_settings(settings)
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/<category>/<key>', methods=['GET'])
def get_single_setting(category, key):
    """Get a specific setting"""
    try:
        value = get_setting(category, key)
        if value is not None:
            return jsonify({'success': True, 'value': value})
        return jsonify({'success': False, 'error': 'Setting not found'}), 404
    except Exception as e:
        logger.error(f"Error getting setting: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/<category>/<key>', methods=['PUT'])
def update_single_setting(category, key):
    """Update a specific setting"""
    try:
        value = request.json.get('value')
        update_setting(category, key, value)
        return jsonify({'success': True, 'message': 'Setting updated'})
    except Exception as e:
        logger.error(f"Error updating setting: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/session/start', methods=['POST'])
def start_session():
    """Start a new drying/curing session"""
    try:
        session_type = request.json.get('type', 'full')  # 'drying', 'curing', 'full'
        
        # Update session settings
        update_setting('process', 'session_active', True)
        update_setting('process', 'session_start_time', datetime.now().isoformat())
        update_setting('process', 'session_status', 'running')
        
        # Create session record
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        settings_snapshot = json.dumps(load_all_settings())
        cursor.execute(
            "INSERT INTO sessions (session_type, start_time, status, settings_snapshot) VALUES (?, ?, ?, ?)",
            (session_type, datetime.now().isoformat(), 'running', settings_snapshot)
        )
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Started new session: {session_id}")
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        logger.error(f"Error starting session: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/session/pause', methods=['POST'])
def pause_session():
    """Pause the current session"""
    try:
        update_setting('process', 'session_pause_time', datetime.now().isoformat())
        update_setting('process', 'session_status', 'paused')
        
        logger.info("Session paused")
        return jsonify({'success': True, 'message': 'Session paused'})
    except Exception as e:
        logger.error(f"Error pausing session: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/session/stop', methods=['POST'])
def stop_session():
    """Stop the current session"""
    try:
        # Update settings
        update_setting('process', 'session_active', False)
        update_setting('process', 'session_status', 'stopped')
        
        # Update session record
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE sessions SET end_time = ?, status = ? WHERE status = 'running' OR status = 'paused'",
            (datetime.now().isoformat(), 'completed')
        )
        conn.commit()
        conn.close()
        
        logger.info("Session stopped")
        return jsonify({'success': True, 'message': 'Session stopped'})
    except Exception as e:
        logger.error(f"Error stopping session: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/<format>', methods=['GET'])
def export_data(format):
    """Export data in specified format"""
    try:
        if format == 'csv':
            # Generate CSV export
            settings = load_all_settings()
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['Category', 'Setting', 'Value', 'Updated'])
            
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT category, key, value, updated_at FROM settings ORDER BY category, key")
            
            for row in cursor.fetchall():
                writer.writerow(row)
            
            conn.close()
            
            response = app.response_class(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename=settings_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
            )
            return response
            
        elif format == 'pdf':
            # PDF generation would require additional library like ReportLab
            return jsonify({'success': False, 'error': 'PDF export not yet implemented'}), 501
        
        return jsonify({'success': False, 'error': 'Invalid format'}), 400
        
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/history', methods=['GET'])
def get_settings_history():
    """Get settings change history"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT category, key, old_value, new_value, changed_by, changed_at FROM settings_history ORDER BY changed_at DESC LIMIT 100"
        )
        
        history = []
        for row in cursor.fetchall():
            history.append({
                'category': row[0],
                'key': row[1],
                'old_value': json.loads(row[2]) if row[2] else None,
                'new_value': json.loads(row[3]) if row[3] else None,
                'changed_by': row[4],
                'changed_at': row[5]
            })
        
        conn.close()
        return jsonify({'success': True, 'history': history})
        
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    
    # Run Flask app
    app.run(
        host='0.0.0.0',  # Allow connections from any IP
        port=5000,
        debug=True
    )