
#!/usr/bin/env python3
"""
Cannabis Drying Data Logger
Comprehensive data logging and analysis system

Logs all sensor data, equipment status, and process events for analysis and optimization.
"""

import sqlite3
import json
import logging
import csv
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
import threading
import time

logger = logging.getLogger(__name__)

class EventType(Enum):
    """Types of events to log"""
    PROCESS_START = "process_start"
    PROCESS_STOP = "process_stop"
    PHASE_CHANGE = "phase_change"
    EQUIPMENT_CHANGE = "equipment_change"
    DISTURBANCE_DETECTED = "disturbance_detected"
    ALERT_TRIGGERED = "alert_triggered"
    MANUAL_OVERRIDE = "manual_override"
    SYSTEM_ERROR = "system_error"
    CALIBRATION = "calibration"

@dataclass
class SensorReading:
    """Individual sensor reading"""
    timestamp: datetime
    session_id: str
    sensor_id: str
    zone_name: str
    temperature_f: float
    humidity_percent: float
    dew_point_f: float
    vpd_kpa: float
    water_activity: float

@dataclass
class EquipmentStatus:
    """Equipment status snapshot"""
    timestamp: datetime
    session_id: str
    dehumidifier_percent: float
    humidifier_percent: float
    mini_split_temp_f: float
    erv_percent: float
    exhaust_fan_percent: float
    supply_fan_percent: float

@dataclass
class ProcessEvent:
    """Process event log entry"""
    timestamp: datetime
    session_id: str
    event_type: EventType
    description: str
    data: Dict[str, Any]
    severity: str = "info"  # info, warning, error, critical

@dataclass
class ProcessSummary:
    """Summary of entire drying process"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    total_duration_hours: float
    phases_completed: List[str]
    final_water_activity: Optional[float]
    avg_temperature: float
    avg_humidity: float
    avg_vpd: float
    disturbances_count: int
    equipment_adjustments_count: int
    trichome_protection_violations: int
    quality_score: Optional[float]
    notes: str = ""

class DataLogger:
    """
    Comprehensive data logging system for cannabis drying process.
    
    Features:
    - SQLite database for reliable storage
    - Real-time logging of all sensor data
    - Equipment status tracking
    - Event logging (phase changes, alerts, etc.)
    - CSV export capabilities
    - Data analysis and reporting
    - Process optimization insights
    """
    
    def __init__(self, db_path: str = "cannabis_dryer_data.db"):
        """Initialize data logger with database"""
        self.db_path = db_path
        self.current_session_id: Optional[str] = None
        self.logging_active = False
        self.logging_thread = None
        
        # Create database and tables
        self._initialize_database()
        
        # Logging intervals
        self.sensor_log_interval = 60  # Log sensor data every 60 seconds
        self.equipment_log_interval = 120  # Log equipment status every 2 minutes
        
        logger.info(f"Data logger initialized with database: {db_path}")
    
    def _initialize_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    sensor_id TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    temperature_f REAL NOT NULL,
                    humidity_percent REAL NOT NULL,
                    dew_point_f REAL NOT NULL,
                    vpd_kpa REAL NOT NULL,
                    water_activity REAL NOT NULL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS equipment_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dehumidifier_percent REAL NOT NULL,
                    humidifier_percent REAL NOT NULL,
                    mini_split_temp_f REAL NOT NULL,
                    erv_percent REAL NOT NULL,
                    exhaust_fan_percent REAL NOT NULL,
                    supply_fan_percent REAL NOT NULL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS process_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    data TEXT NOT NULL,
                    severity TEXT NOT NULL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS process_summaries (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    total_duration_hours REAL,
                    phases_completed TEXT NOT NULL,
                    final_water_activity REAL,
                    avg_temperature REAL NOT NULL,
                    avg_humidity REAL NOT NULL,
                    avg_vpd REAL NOT NULL,
                    disturbances_count INTEGER NOT NULL,
                    equipment_adjustments_count INTEGER NOT NULL,
                    trichome_protection_violations INTEGER NOT NULL,
                    quality_score REAL,
                    notes TEXT
                )
            ''')
            
            conn.commit()
    
    def start_session(self, session_id: str, initial_conditions: Dict[str, Any]) -> bool:
        """Start a new drying session"""
        try:
            self.current_session_id = session_id
            
            # Log session start event
            self.log_event(
                event_type=EventType.PROCESS_START,
                description=f"Started drying session: {session_id}",
                data=initial_conditions,
                severity="info"
            )
            
            # Create initial process summary
            summary = ProcessSummary(
                session_id=session_id,
                start_time=datetime.now(),
                end_time=None,
                total_duration_hours=0.0,
                phases_completed=[],
                final_water_activity=None,
                avg_temperature=0.0,
                avg_humidity=0.0,
                avg_vpd=0.0,
                disturbances_count=0,
                equipment_adjustments_count=0,
                trichome_protection_violations=0,
                quality_score=None,
                notes=f"Session started with conditions: {initial_conditions}"
            )
            
            self._save_process_summary(summary)
            
            # Start logging thread
            self.logging_active = True
            self.logging_thread = threading.Thread(target=self._logging_loop, daemon=True)
            self.logging_thread.start()
            
            logger.info(f"Started data logging for session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            return False
    
    def end_session(self, final_conditions: Dict[str, Any], notes: str = "") -> bool:
        """End current drying session"""
        try:
            if not self.current_session_id:
                logger.warning("No active session to end")
                return False
            
            # Stop logging
            self.logging_active = False
            
            # Log session end event
            self.log_event(
                event_type=EventType.PROCESS_STOP,
                description=f"Ended drying session: {self.current_session_id}",
                data=final_conditions,
                severity="info"
            )
            
            # Update process summary
            summary = self.get_process_summary(self.current_session_id)
            if summary:
                summary.end_time = datetime.now()
                summary.total_duration_hours = (summary.end_time - summary.start_time).total_seconds() / 3600
                summary.final_water_activity = final_conditions.get("water_activity")
                summary.quality_score = self._calculate_quality_score(self.current_session_id)
                summary.notes += f"\nSession ended: {notes}"
                
                self._save_process_summary(summary)
            
            session_id = self.current_session_id
            self.current_session_id = None
            
            logger.info(f"Ended data logging for session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
            return False
    
    def log_sensor_reading(self, sensor_data: Dict[str, Any]):
        """Log sensor reading to database"""
        try:
            if not self.current_session_id:
                return
            
            timestamp = datetime.now()
            
            # Log each sensor zone
            for zone_name, data in sensor_data.items():
                if isinstance(data, dict) and "temperature" in data and "humidity" in data:
                    # Calculate additional metrics
                    if not hasattr(self, '_vpd_calc'):
                        from vpd_calculator import ResearchOptimizedVPD
                        self._vpd_calc = ResearchOptimizedVPD()
                    calc = self._vpd_calc
                    vpd_reading = calc.calculate_vpd_from_conditions(
                        data["temperature"], data["humidity"]
                    )
                    
                    reading = SensorReading(
                        timestamp=timestamp,
                        session_id=self.current_session_id,
                        sensor_id=data.get("sensor_id", f"sensor_{zone_name}"),
                        zone_name=zone_name,
                        temperature_f=data["temperature"],
                        humidity_percent=data["humidity"],
                        dew_point_f=vpd_reading.dew_point_f,
                        vpd_kpa=vpd_reading.vpd_kpa,
                        water_activity=vpd_reading.estimated_water_activity
                    )
                    
                    self._save_sensor_reading(reading)
            
        except Exception as e:
            logger.error(f"Failed to log sensor reading: {e}")
    
    def log_equipment_status(self, equipment_data: Dict[str, float]):
        """Log equipment status to database"""
        try:
            if not self.current_session_id:
                return
            
            status = EquipmentStatus(
                timestamp=datetime.now(),
                session_id=self.current_session_id,
                dehumidifier_percent=equipment_data.get("dehumidifier", 0.0),
                humidifier_percent=equipment_data.get("humidifier", 0.0),
                mini_split_temp_f=equipment_data.get("mini_split", 68.0),
                erv_percent=equipment_data.get("erv", 0.0),
                exhaust_fan_percent=equipment_data.get("exhaust_fan", 0.0),
                supply_fan_percent=equipment_data.get("supply_fan", 0.0)
            )
            
            self._save_equipment_status(status)
            
        except Exception as e:
            logger.error(f"Failed to log equipment status: {e}")
    
    def log_event(self, event_type: EventType, description: str, 
                  data: Dict[str, Any], severity: str = "info"):
        """Log process event"""
        try:
            event = ProcessEvent(
                timestamp=datetime.now(),
                session_id=self.current_session_id or "system",
                event_type=event_type,
                description=description,
                data=data,
                severity=severity
            )
            
            self._save_process_event(event)
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
    
    def get_session_data(self, session_id: str, start_time: Optional[datetime] = None, 
                        end_time: Optional[datetime] = None) -> Dict[str, List]:
        """Get all data for a session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build time filter
                time_filter = "session_id = ?"
                params = [session_id]
                
                if start_time:
                    time_filter += " AND timestamp >= ?"
                    params.append(start_time.isoformat())
                
                if end_time:
                    time_filter += " AND timestamp <= ?"
                    params.append(end_time.isoformat())
                
                # Get sensor readings
                sensor_data = conn.execute(f'''
                    SELECT * FROM sensor_readings 
                    WHERE {time_filter} 
                    ORDER BY timestamp
                ''', params).fetchall()
                
                # Get equipment status
                equipment_data = conn.execute(f'''
                    SELECT * FROM equipment_status 
                    WHERE {time_filter} 
                    ORDER BY timestamp
                ''', params).fetchall()
                
                # Get events
                event_data = conn.execute(f'''
                    SELECT * FROM process_events 
                    WHERE {time_filter} 
                    ORDER BY timestamp
                ''', params).fetchall()
                
                return {
                    "sensors": [dict(row) for row in sensor_data],
                    "equipment": [dict(row) for row in equipment_data],
                    "events": [dict(row) for row in event_data]
                }
                
        except Exception as e:
            logger.error(f"Failed to get session data: {e}")
            return {"sensors": [], "equipment": [], "events": []}
    
    def get_process_summary(self, session_id: str) -> Optional[ProcessSummary]:
        """Get process summary for session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    'SELECT * FROM process_summaries WHERE session_id = ?', 
                    (session_id,)
                ).fetchone()
                
                if row:
                    data = dict(row)
                    data['start_time'] = datetime.fromisoformat(data['start_time'])
                    if data['end_time']:
                        data['end_time'] = datetime.fromisoformat(data['end_time'])
                    data['phases_completed'] = json.loads(data['phases_completed'])
                    return ProcessSummary(**data)
                
        except Exception as e:
            logger.error(f"Failed to get process summary: {e}")
        
        return None
    
    def export_session_csv(self, session_id: str, export_dir: str = "exports") -> str:
        """Export session data to CSV files"""
        try:
            os.makedirs(export_dir, exist_ok=True)
            
            session_data = self.get_session_data(session_id)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Export sensor data
            sensor_file = os.path.join(export_dir, f"sensors_{session_id}_{timestamp}.csv")
            with open(sensor_file, 'w', newline='') as f:
                if session_data["sensors"]:
                    writer = csv.DictWriter(f, fieldnames=session_data["sensors"][0].keys())
                    writer.writeheader()
                    writer.writerows(session_data["sensors"])
            
            # Export equipment data
            equipment_file = os.path.join(export_dir, f"equipment_{session_id}_{timestamp}.csv")
            with open(equipment_file, 'w', newline='') as f:
                if session_data["equipment"]:
                    writer = csv.DictWriter(f, fieldnames=session_data["equipment"][0].keys())
                    writer.writeheader()
                    writer.writerows(session_data["equipment"])
            
            # Export events
            events_file = os.path.join(export_dir, f"events_{session_id}_{timestamp}.csv")
            with open(events_file, 'w', newline='') as f:
                if session_data["events"]:
                    writer = csv.DictWriter(f, fieldnames=session_data["events"][0].keys())
                    writer.writeheader()
                    writer.writerows(session_data["events"])
            
            logger.info(f"Exported session {session_id} to CSV files in {export_dir}")
            return export_dir
            
        except Exception as e:
            logger.error(f"Failed to export session data: {e}")
            return ""
    
    def get_analytics_data(self, session_id: str) -> Dict[str, Any]:
        """Get analytics data for charts and graphs"""
        try:
            session_data = self.get_session_data(session_id)
            
            # Process sensor data for charts
            sensor_readings = session_data["sensors"]
            equipment_readings = session_data["equipment"]
            
            # Group by timestamp for charts
            chart_data = {}
            
            for reading in sensor_readings:
                timestamp = reading["timestamp"]
                if timestamp not in chart_data:
                    chart_data[timestamp] = {
                        "timestamp": timestamp,
                        "temperatures": [],
                        "humidities": [],
                        "vpds": [],
                        "water_activities": []
                    }
                
                chart_data[timestamp]["temperatures"].append(reading["temperature_f"])
                chart_data[timestamp]["humidities"].append(reading["humidity_percent"])
                chart_data[timestamp]["vpds"].append(reading["vpd_kpa"])
                chart_data[timestamp]["water_activities"].append(reading["water_activity"])
            
            # Calculate averages for each timestamp
            analytics = {
                "timestamps": [],
                "avg_temperatures": [],
                "avg_humidities": [],
                "avg_vpds": [],
                "avg_water_activities": [],
                "equipment_changes": []
            }
            
            for timestamp in sorted(chart_data.keys()):
                data = chart_data[timestamp]
                analytics["timestamps"].append(timestamp)
                analytics["avg_temperatures"].append(statistics.mean(data["temperatures"]))
                analytics["avg_humidities"].append(statistics.mean(data["humidities"]))
                analytics["avg_vpds"].append(statistics.mean(data["vpds"]))
                analytics["avg_water_activities"].append(statistics.mean(data["water_activities"]))
            
            # Add equipment changes
            for equipment in equipment_readings:
                analytics["equipment_changes"].append({
                    "timestamp": equipment["timestamp"],
                    "dehumidifier": equipment["dehumidifier_percent"],
                    "humidifier": equipment["humidifier_percent"],
                    "temperature_setting": equipment["mini_split_temp_f"]
                })
            
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get analytics data: {e}")
            return {}
    
    def _save_sensor_reading(self, reading: SensorReading):
        """Save sensor reading to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO sensor_readings 
                (timestamp, session_id, sensor_id, zone_name, temperature_f, 
                 humidity_percent, dew_point_f, vpd_kpa, water_activity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                reading.timestamp.isoformat(),
                reading.session_id,
                reading.sensor_id,
                reading.zone_name,
                reading.temperature_f,
                reading.humidity_percent,
                reading.dew_point_f,
                reading.vpd_kpa,
                reading.water_activity
            ))
    
    def _save_equipment_status(self, status: EquipmentStatus):
        """Save equipment status to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO equipment_status 
                (timestamp, session_id, dehumidifier_percent, humidifier_percent,
                 mini_split_temp_f, erv_percent, exhaust_fan_percent, supply_fan_percent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                status.timestamp.isoformat(),
                status.session_id,
                status.dehumidifier_percent,
                status.humidifier_percent,
                status.mini_split_temp_f,
                status.erv_percent,
                status.exhaust_fan_percent,
                status.supply_fan_percent
            ))
    
    def _save_process_event(self, event: ProcessEvent):
        """Save process event to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO process_events 
                (timestamp, session_id, event_type, description, data, severity)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                event.timestamp.isoformat(),
                event.session_id,
                event.event_type.value,
                event.description,
                json.dumps(event.data),
                event.severity
            ))
    
    def _save_process_summary(self, summary: ProcessSummary):
        """Save or update process summary"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO process_summaries
                (session_id, start_time, end_time, total_duration_hours, phases_completed,
                 final_water_activity, avg_temperature, avg_humidity, avg_vpd,
                 disturbances_count, equipment_adjustments_count, trichome_protection_violations,
                 quality_score, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                summary.session_id,
                summary.start_time.isoformat(),
                summary.end_time.isoformat() if summary.end_time else None,
                summary.total_duration_hours,
                json.dumps(summary.phases_completed),
                summary.final_water_activity,
                summary.avg_temperature,
                summary.avg_humidity,
                summary.avg_vpd,
                summary.disturbances_count,
                summary.equipment_adjustments_count,
                summary.trichome_protection_violations,
                summary.quality_score,
                summary.notes
            ))
    
    def _calculate_quality_score(self, session_id: str) -> float:
        """Calculate quality score based on process data"""
        try:
            session_data = self.get_session_data(session_id)
            
            # Factors for quality scoring
            stability_score = 0.0  # How stable conditions were
            efficiency_score = 0.0  # How efficiently it reached targets
            protection_score = 0.0  # How well trichomes were protected
            
            # Calculate stability (lower variance = higher score)
            sensor_data = session_data["sensors"]
            if sensor_data:
                temps = [r["temperature_f"] for r in sensor_data]
                humids = [r["humidity_percent"] for r in sensor_data]
                
                temp_variance = statistics.variance(temps) if len(temps) > 1 else 0
                humid_variance = statistics.variance(humids) if len(humids) > 1 else 0
                
                # Lower variance = higher stability score (0-40 points)
                stability_score = max(0, 40 - (temp_variance * 2 + humid_variance * 0.5))
            
            # Calculate efficiency based on time to target (0-30 points)
            efficiency_score = 25.0  # Default reasonable score
            
            # Calculate protection score based on violations (0-30 points)
            events_data = session_data["events"]
            violations = len([e for e in events_data if e["severity"] in ["warning", "error"]])
            protection_score = max(0, 30 - violations * 2)
            
            total_score = stability_score + efficiency_score + protection_score
            return min(100.0, max(0.0, total_score))
            
        except Exception as e:
            logger.error(f"Failed to calculate quality score: {e}")
            return 75.0  # Default score
    
    def _logging_loop(self):
        """Background logging loop"""
        last_sensor_log = datetime.now() - timedelta(seconds=self.sensor_log_interval)
        last_equipment_log = datetime.now() - timedelta(seconds=self.equipment_log_interval)
        
        while self.logging_active:
            try:
                current_time = datetime.now()
                
                # This would normally get real data from your system
                # For now, we'll wait for external calls to log_sensor_reading() and log_equipment_status()
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Logging loop error: {e}")
                time.sleep(30)

# Example usage and testing
if __name__ == "__main__":
    print("=== Cannabis Drying Data Logger Demo ===\n")
    
    # Initialize logger
    data_logger = DataLogger("demo_cannabis_data.db")
    
    # Start a demo session
    session_id = f"demo_session_{int(time.time())}"
    initial_conditions = {
        "target_temperature": 68.0,
        "target_humidity": 58.0,
        "target_vpd": 1.1,
        "batch_size": "5 lbs",
        "strain": "Demo Strain"
    }
    
    print(f"Starting session: {session_id}")
    data_logger.start_session(session_id, initial_conditions)
    
    # Simulate some data logging
    import random
    for i in range(5):
        # Simulate sensor readings
        sensor_data = {
            "zone_1": {"temperature": 68.0 + random.uniform(-0.5, 0.5), "humidity": 58.0 + random.uniform(-2, 2)},
            "zone_2": {"temperature": 68.1 + random.uniform(-0.3, 0.3), "humidity": 58.2 + random.uniform(-1.5, 1.5)},
            "zone_3": {"temperature": 67.9 + random.uniform(-0.4, 0.4), "humidity": 57.8 + random.uniform(-1.8, 1.8)},
            "zone_4": {"temperature": 68.0 + random.uniform(-0.2, 0.2), "humidity": 58.1 + random.uniform(-1.2, 1.2)}
        }
        
        data_logger.log_sensor_reading(sensor_data)
        
        # Simulate equipment status
        equipment_data = {
            "dehumidifier": 45.0 + random.uniform(-5, 5),
            "humidifier": 0.0,
            "mini_split": 68.0,
            "erv": 25.0,
            "exhaust_fan": 40.0,
            "supply_fan": 40.0
        }
        
        data_logger.log_equipment_status(equipment_data)
        
        # Log some events
        if i == 2:
            data_logger.log_event(
                EventType.PHASE_CHANGE,
                "Moved to mid-drying phase",
                {"previous_phase": "initial_moisture", "new_phase": "mid_drying"},
                "info"
            )
        
        time.sleep(1)  # Wait 1 second between readings
    
    # End session
    final_conditions = {"final_water_activity": 0.61, "final_vpd": 1.05}
    data_logger.end_session(final_conditions, "Demo session completed successfully")
    
    # Show summary
    summary = data_logger.get_process_summary(session_id)
    if summary:
        print(f"\nSession Summary:")
        print(f"Duration: {summary.total_duration_hours:.2f} hours")
        print(f"Average Temperature: {summary.avg_temperature:.1f}°F")
        print(f"Average Humidity: {summary.avg_humidity:.1f}%")
        print(f"Quality Score: {summary.quality_score:.1f}/100")
    
    # Export data
    export_path = data_logger.export_session_csv(session_id)
    if export_path:
        print(f"\nData exported to: {export_path}")
    
    print("\n✅ Data logging demo complete!")