#!/usr/bin/env python3
"""
Cannabis Drying and Curing Control System - Precision VPD Control
Precision drying with gradual stepping for optimal terpene retention
"""

import time
import json
import logging
import threading
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum
from collections import deque

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MOVE DryingPhase HERE - BEFORE it's used in VPDSetpoint
class DryingPhase(Enum):
    """Drying phase enumeration with precise timing"""
    DRY_INITIAL = "dry_initial"      # Day 1-2: 48 hours
    DRY_MID = "dry_mid"              # Day 3-5: 72 hours  
    DRY_FINAL = "dry_final"          # Day 6-7: 48 hours
    CURE = "cure"                    # Day 8-10: 48-72 hours
    STORAGE = "storage"              # After cure complete
    COMPLETE = "complete"

class EquipmentState(Enum):
    """Equipment state enumeration"""
    OFF = "OFF"
    ON = "ON"
    ERROR = "ERROR"

# NOW VPDSetpoint can use DryingPhase
@dataclass
class VPDSetpoint:
    """Setpoint configuration for each phase"""
    phase: DryingPhase
    temperature_target: float
    temperature_tolerance: float
    dew_point_target: float
    dew_point_tolerance: float
    humidity_min: float
    humidity_max: float
    vpd_min: float
    vpd_max: float
    hours_in_phase: int

@dataclass
class SensorReading:
    """Sensor data structure"""
    temperature: float  # °F
    humidity: float     # %RH
    timestamp: datetime
    sensor_id: str
    
    @property
    def temperature_c(self) -> float:
        """Convert temperature to Celsius"""
        return (self.temperature - 32) * 5/9
    
    @property
    def vpd_kpa(self) -> float:
        """Calculate VPD in kPa using leaf temperature = air temperature"""
        t_leaf = self.temperature_c
        # Saturation vapor pressure at leaf temperature
        svp_leaf = 0.6108 * np.exp((17.27 * t_leaf) / (t_leaf + 237.3))
        # Actual vapor pressure
        avp = svp_leaf * (self.humidity / 100)
        # VPD in kPa
        return svp_leaf - avp
    
    @property
    def dew_point(self) -> float:
        """Calculate dew point in °F"""
        t_c = self.temperature_c
        rh = self.humidity
        # Magnus formula
        a = 17.27
        b = 237.7
        alpha = ((a * t_c) / (b + t_c)) + np.log(rh / 100.0)
        dew_c = (b * alpha) / (a - alpha)
        return (dew_c * 9/5) + 32
    
    @property
    def water_activity(self) -> float:
        """Estimate water activity from RH (simplified model)"""
        # This is a simplified estimation - in production use actual aW meter
        return self.humidity / 100

@dataclass
class ControlSetpoint:
    """Control setpoint configuration for each phase"""
    temp_target: float          # Target temperature °F
    temp_tolerance: float       # ±tolerance °F
    dew_point_target: float     # Target dew point °F
    dew_point_tolerance: float  # ±tolerance °F
    humidity_min: float         # Minimum RH %
    humidity_max: float         # Maximum RH %
    vpd_min: float             # Minimum VPD kPa
    vpd_max: float             # Maximum VPD kPa
    duration_hours: float       # Phase duration in hours
    air_changes_per_hour: int   # Target air changes (6-10)

# Now your PrecisionVPDController class continues as-is...
class PrecisionVPDController:
    """Precision VPD-based control system mimicking Cannatrol approach"""
    
    def __init__(self):
        self.current_phase = DryingPhase.DRY_INITIAL
        self.phase_start_time = datetime.now()
        self.sensor_readings: Dict[str, SensorReading] = {}
        self.process_start_time = None  
        self.process_active = False      
        self.phase = self.current_phase  # Compatibility alias    
        
        # Equipment states - matching your actual equipment
        self.equipment_states = {
            'mini_split': EquipmentState.ON,      # Always on for temp control
            'dehum': EquipmentState.OFF,          # ON/OFF relay control
            'hum_fan': EquipmentState.ON,         # Almost always ON
            'hum_solenoid': EquipmentState.OFF,   # ON when humidification needed
            'supply_fan': EquipmentState.ON,      # Always ON during operation
            'return_fan': EquipmentState.ON,      # Tied to supply fan
            'erv': EquipmentState.ON              # ON during dry/cure
        }

        # Initialize real sensors
        try:
            from software.control.sensor_manager import SensorManager
            self.sensor_manager = SensorManager()
            self.hardware_mode = True
            logger.info("Hardware sensors initialized")
        except Exception as e:
            logger.warning(f"No hardware sensors found: {e}, running in simulation mode")
            self.sensor_manager = None
            self.hardware_mode = False
        
        # Mini-split temperature setpoint (controlled via IR)
        self.mini_split_setpoint = 68.0  # °F
        
        # Research-optimized control parameters for each phase
        self.phase_setpoints = {
            DryingPhase.DRY_INITIAL: ControlSetpoint(
                temp_target=68, temp_tolerance=1,
                dew_point_target=55, dew_point_tolerance=1,
                humidity_min=60, humidity_max=65,
                vpd_min=0.7, vpd_max=0.8,
                duration_hours=48,
                air_changes_per_hour=8
            ),
            DryingPhase.DRY_MID: ControlSetpoint(
                temp_target=67, temp_tolerance=1,
                dew_point_target=53, dew_point_tolerance=1,
                humidity_min=55, humidity_max=60,
                vpd_min=0.8, vpd_max=0.9,
                duration_hours=72,
                air_changes_per_hour=8
            ),
            DryingPhase.DRY_FINAL: ControlSetpoint(
                temp_target=65.5, temp_tolerance=0.5,
                dew_point_target=51, dew_point_tolerance=1,
                humidity_min=50, humidity_max=55,
                vpd_min=0.85, vpd_max=0.95,
                duration_hours=48,
                air_changes_per_hour=6
            ),
            DryingPhase.CURE: ControlSetpoint(
                temp_target=64, temp_tolerance=1,
                dew_point_target=51, dew_point_tolerance=1,
                humidity_min=55, humidity_max=60,
                vpd_min=0.7, vpd_max=0.8,
                duration_hours=72,
                air_changes_per_hour=6
            ),
            DryingPhase.STORAGE: ControlSetpoint(
                temp_target=65, temp_tolerance=1,
                dew_point_target=52, dew_point_tolerance=1,
                humidity_min=60, humidity_max=65,
                vpd_min=0.65, vpd_max=0.85,
                duration_hours=0,  # Indefinite
                air_changes_per_hour=4
            )
        }
        
        # Control parameters
        self.hysteresis = {
            'temperature': 1.0,  # °F
            'humidity': 2.0,     # %RH
            'dew_point': 1.0     # °F
        }
        
        # Timing parameters
        self.last_control_time = time.time()
        self.min_cycle_time = 120  # 2 minutes minimum between state changes
        self.last_dehum_change = time.time()
        self.dehum_min_cycle = 300  # 5 minutes for dehumidifier
        
        # ERV cycling (for fresh air exchange)
        self.erv_cycle_minutes = 60  # Run continuously during dry/cure
        self.erv_on_minutes = 60     # Always on
        
        # Safety limits
        self.emergency_temp_max = 75
        self.emergency_temp_min = 60
        self.emergency_humidity_max = 70
        self.emergency_humidity_min = 40
        
        # Sensor variance monitoring
        self.max_sensor_variance = 2.0  # °F max difference between sensors
        
        # Water activity tracking
        self.estimated_water_activity = 0.85  # Starting estimate
        self.target_water_activity = 0.61     # Target 0.60-0.62
        
    def update_sensor_reading(self, sensor_id: str, temperature: float, humidity: float):
        """Update sensor reading"""
        self.sensor_readings[sensor_id] = SensorReading(
            temperature=temperature,
            humidity=humidity,
            timestamp=datetime.now(),
            sensor_id=sensor_id
        )
        logger.debug(f"Sensor {sensor_id}: {temperature:.1f}°F, {humidity:.1f}%RH, "
                    f"DP: {self.sensor_readings[sensor_id].dew_point:.1f}°F, "
                    f"VPD: {self.sensor_readings[sensor_id].vpd_kpa:.2f}kPa")
    
    def get_dry_room_conditions(self) -> Tuple[float, float, float, float]:
        """Get average conditions from drying room sensors only"""
        readings = []
        
        for sensor_id, reading in self.sensor_readings.items():
            # Skip if it's not a dry room sensor
            if not sensor_id.startswith('dry'):
                continue
                
            # Check what type the reading actually is
            if isinstance(reading, str):
                logger.error(f"Sensor {sensor_id} contains string instead of SensorReading object: {reading}")
                continue
                
            if reading is None:
                logger.warning(f"Sensor {sensor_id} has None value")
                continue
                
            # Only add if it has the required attributes
            if hasattr(reading, 'temperature') and hasattr(reading, 'humidity'):
                readings.append(reading)
            else:
                logger.error(f"Sensor {sensor_id} missing temperature or humidity attributes")
        
        if not readings:
            raise ValueError("No valid dry room sensor data available")
        
        avg_temp = np.mean([r.temperature for r in readings])
        avg_humidity = np.mean([r.humidity for r in readings])
        avg_dew_point = np.mean([r.dew_point for r in readings if hasattr(r, 'dew_point')])
        avg_vpd = np.mean([r.vpd_kpa for r in readings if hasattr(r, 'vpd_kpa')])
        
        return avg_temp, avg_humidity, avg_dew_point, avg_vpd
    
    def check_phase_transition(self):
        """Check if it's time to transition to next phase"""
        current_setpoint = self.phase_setpoints[self.current_phase]
        elapsed_hours = (datetime.now() - self.phase_start_time).total_seconds() / 3600
        
        # Check water activity for early transition
        if self.estimated_water_activity <= self.target_water_activity and \
           self.current_phase in [DryingPhase.DRY_FINAL, DryingPhase.CURE]:
            logger.info(f"Target water activity reached: {self.estimated_water_activity:.3f}")
            self.current_phase = DryingPhase.COMPLETE
            return
        
        if elapsed_hours >= current_setpoint.duration_hours and \
           current_setpoint.duration_hours > 0:
            # Transition to next phase
            transitions = {
                DryingPhase.DRY_INITIAL: DryingPhase.DRY_MID,
                DryingPhase.DRY_MID: DryingPhase.DRY_FINAL,
                DryingPhase.DRY_FINAL: DryingPhase.CURE,
                DryingPhase.CURE: DryingPhase.STORAGE
            }
            
            if self.current_phase in transitions:
                old_phase = self.current_phase
                self.current_phase = transitions[self.current_phase]
                self.phase_start_time = datetime.now()
                
                # Special handling for cure → storage transition
                if self.current_phase == DryingPhase.STORAGE:
                    logger.info("="*60)
                    logger.info("🎉 CURE COMPLETE - BATCH READY FOR PACKAGING!")
                    logger.info(f"Final water activity estimate: ~{self.estimated_water_activity:.3f}")
                    logger.info("System entering STORAGE/IDLE mode")
                    logger.info("- Most equipment will shut down")
                    logger.info("- Occasional ventilation will maintain conditions")
                    logger.info("- Remove product and start new batch when ready")
                    logger.info("="*60)
                else:
                    logger.info(f"Phase transition: {old_phase.value} → {self.current_phase.value}")
                
                # Update mini-split setpoint for new phase
                self.mini_split_setpoint = self.phase_setpoints[self.current_phase].temp_target
                logger.info(f"Mini-split setpoint: {self.mini_split_setpoint}°F")
    
    def calculate_linear_transition(self) -> ControlSetpoint:
        """Calculate smoothly transitioning setpoint between phases"""
        self.check_phase_transition()
        
        current_setpoint = self.phase_setpoints[self.current_phase]
        elapsed_hours = (datetime.now() - self.phase_start_time).total_seconds() / 3600
        
        # Smooth transition over first 4 hours of new phase
        transition_period = 4.0
        
        if elapsed_hours < transition_period and self.current_phase != DryingPhase.DRY_INITIAL:
            # Get previous phase setpoint
            prev_phases = {
                DryingPhase.DRY_MID: DryingPhase.DRY_INITIAL,
                DryingPhase.DRY_FINAL: DryingPhase.DRY_MID,
                DryingPhase.CURE: DryingPhase.DRY_FINAL,
                DryingPhase.STORAGE: DryingPhase.CURE
            }
            
            if self.current_phase in prev_phases:
                prev_setpoint = self.phase_setpoints[prev_phases[self.current_phase]]
                ratio = elapsed_hours / transition_period
                
                # Linear interpolation for smooth transition
                return ControlSetpoint(
                    temp_target=prev_setpoint.temp_target + 
                               (current_setpoint.temp_target - prev_setpoint.temp_target) * ratio,
                    temp_tolerance=current_setpoint.temp_tolerance,
                    dew_point_target=prev_setpoint.dew_point_target + 
                                    (current_setpoint.dew_point_target - prev_setpoint.dew_point_target) * ratio,
                    dew_point_tolerance=current_setpoint.dew_point_tolerance,
                    humidity_min=prev_setpoint.humidity_min + 
                                (current_setpoint.humidity_min - prev_setpoint.humidity_min) * ratio,
                    humidity_max=prev_setpoint.humidity_max + 
                                (current_setpoint.humidity_max - prev_setpoint.humidity_max) * ratio,
                    vpd_min=current_setpoint.vpd_min,
                    vpd_max=current_setpoint.vpd_max,
                    duration_hours=current_setpoint.duration_hours,
                    air_changes_per_hour=current_setpoint.air_changes_per_hour
                )
        
        return current_setpoint
    
    def get_system_status(self):
        """Get complete system status for API - handles dict or object sensor data"""
        
        # Initialize with defaults
        if not hasattr(self, 'current_phase'):
            self.current_phase = DryingPhase.DRY_INITIAL
        
        if not hasattr(self, 'sensor_readings'):
            self.sensor_readings = []
        
        if not hasattr(self, 'process_start_time'):
            self.process_start_time = None
        
        if not hasattr(self, 'process_active'):
            self.process_active = False
        
        if not hasattr(self, 'equipment_states'):
            self.equipment_states = {}
        
        # Get current phase and setpoints
        current_phase = self.current_phase
        phase_settings = self.phase_setpoints.get(current_phase, self.phase_setpoints[DryingPhase.DRY_INITIAL])
        
        # Get sensor averages
        avg_temp = 68.0
        avg_humidity = 60.0
        avg_vpd = 0.75
        
        # Handle sensor readings whether they're dicts, objects, or strings
        if self.sensor_readings and len(self.sensor_readings) > 0:
            temps = []
            humids = []
            vpds = []
            
            for sensor_name, reading in self.sensor_readings.items():
                # Skip if reading is None or a string
                if reading is None or isinstance(reading, str):
                    continue
                    
                # Handle dictionary format
                if isinstance(reading, dict):
                    if 'temperature' in reading and reading['temperature'] is not None:
                        temps.append(float(reading['temperature']))
                    if 'humidity' in reading and reading['humidity'] is not None:
                        humids.append(float(reading['humidity']))
                    if 'vpd_kpa' in reading and reading['vpd_kpa'] is not None:
                        vpds.append(float(reading['vpd_kpa']))
                # Handle object format (SensorReading objects)
                else:
                    if hasattr(reading, 'temperature') and reading.temperature is not None:
                        temps.append(float(reading.temperature))
                    if hasattr(reading, 'humidity') and reading.humidity is not None:
                        humids.append(float(reading.humidity))
                    if hasattr(reading, 'vpd_kpa') and reading.vpd_kpa is not None:
                        vpds.append(float(reading.vpd_kpa))
            
            # Calculate averages
            if temps:
                avg_temp = sum(temps) / len(temps)
            if humids:
                avg_humidity = sum(humids) / len(humids)
            if vpds:
                avg_vpd = sum(vpds) / len(vpds)
            elif temps and humids:
                # Calculate VPD if we have temp and humidity but no VPD values
                temp_c = (avg_temp - 32) * 5/9
                svp = 0.6108 * (2.71828 ** ((17.27 * temp_c) / (temp_c + 237.3)))
                avp = svp * (avg_humidity / 100)
                avg_vpd = svp - avp
        
        # Calculate process time
        elapsed_hours = 0
        current_day = 1
        if self.process_start_time:
            elapsed = datetime.now() - self.process_start_time
            elapsed_hours = elapsed.total_seconds() / 3600
            current_day = elapsed.days + 1
        
        # Build response
        status = {
            'current_phase': current_phase.value if hasattr(current_phase, 'value') else str(current_phase),
            'current_day': current_day,
            'elapsed_hours': elapsed_hours,
            'current_vpd': float(avg_vpd),
            'vpd_target_min': float(phase_settings.vpd_min),
            'vpd_target_max': float(phase_settings.vpd_max),
            'current_temp': float(avg_temp),
            'current_humidity': float(avg_humidity),
            'temp_target': float(phase_settings.temp_target),
            'humidity_min': float(phase_settings.humidity_min),
            'humidity_max': float(phase_settings.humidity_max),
            'dew_point_target': float(phase_settings.dew_point_target),
            'process_active': self.process_active,
            'timestamp': datetime.now().isoformat()
        }
        
        # Add equipment states if they exist
        if self.equipment_states:
            try:
                status['equipment_states'] = {k: v.value if hasattr(v, 'value') else str(v) 
                                            for k, v in self.equipment_states.items()}
            except:
                status['equipment_states'] = {}
        
        return status

    def calculate_control_action(self) -> Dict[str, EquipmentState]:
        """Calculate equipment control based on dew point and VPD targets"""
        avg_temp, avg_humidity, avg_dew_point, avg_vpd = self.get_dry_room_conditions()
        setpoint = self.calculate_linear_transition()
        
        # Update water activity estimate
        self.estimated_water_activity = avg_humidity / 100 * 0.95  # Simplified model
        
        # Emergency checks first
        if avg_temp > self.emergency_temp_max or avg_temp < self.emergency_temp_min:
            logger.warning(f"Emergency temperature: {avg_temp:.1f}°F")
            return self._emergency_control(avg_temp, avg_humidity)
        
        if avg_humidity > self.emergency_humidity_max or avg_humidity < self.emergency_humidity_min:
            logger.warning(f"Emergency humidity: {avg_humidity:.1f}%")
            return self._emergency_control(avg_temp, avg_humidity)
        
        new_states = self.equipment_states.copy()
        
        # Storage/Complete mode - minimal equipment operation
        if self.current_phase == DryingPhase.STORAGE:
            # Minimal operation - just occasional ventilation
            new_states['mini_split'] = EquipmentState.ON  # Maintain temperature
            new_states['supply_fan'] = EquipmentState.OFF
            new_states['return_fan'] = EquipmentState.OFF
            new_states['hum_fan'] = EquipmentState.OFF
            new_states['hum_solenoid'] = EquipmentState.OFF
            new_states['dehum'] = EquipmentState.OFF
            
            # Cycle ERV occasionally for fresh air
            current_minute = datetime.now().minute
            if current_minute % 30 < 5:  # 5 minutes every 30 minutes
                new_states['erv'] = EquipmentState.ON
                new_states['supply_fan'] = EquipmentState.ON
                new_states['return_fan'] = EquipmentState.ON
            else:
                new_states['erv'] = EquipmentState.OFF
            
            return new_states
        
        # Normal operation for active drying/curing phases
        # Core airflow equipment - always running during operation
        new_states['supply_fan'] = EquipmentState.ON
        new_states['return_fan'] = EquipmentState.ON
        new_states['hum_fan'] = EquipmentState.ON
        
        # ERV for fresh air exchange - continuous during dry/cure
        if self.current_phase in [DryingPhase.DRY_INITIAL, DryingPhase.DRY_MID, 
                                  DryingPhase.DRY_FINAL, DryingPhase.CURE]:
            new_states['erv'] = EquipmentState.ON
        else:
            new_states['erv'] = EquipmentState.OFF
        
        # Temperature control via mini-split (always on, IR controlled)
        new_states['mini_split'] = EquipmentState.ON
        # Note: Actual temperature setpoint sent via IR based on self.mini_split_setpoint
        
        # Humidity control based on dew point and RH targets
        dew_point_error = avg_dew_point - setpoint.dew_point_target
        
        # Dehumidifier control
        if avg_humidity > setpoint.humidity_max + self.hysteresis['humidity'] or \
           dew_point_error > setpoint.dew_point_tolerance:
            if time.time() - self.last_dehum_change > self.dehum_min_cycle:
                new_states['dehum'] = EquipmentState.ON
                new_states['hum_solenoid'] = EquipmentState.OFF
                logger.info(f"Dehumidification needed: RH={avg_humidity:.1f}%, DP={avg_dew_point:.1f}°F")
        elif avg_humidity < setpoint.humidity_max - self.hysteresis['humidity']:
            if self.equipment_states['dehum'] == EquipmentState.ON:
                if time.time() - self.last_dehum_change > self.dehum_min_cycle:
                    new_states['dehum'] = EquipmentState.OFF
        
        # Humidifier solenoid control
        if avg_humidity < setpoint.humidity_min - self.hysteresis['humidity'] or \
           dew_point_error < -setpoint.dew_point_tolerance:
            new_states['hum_solenoid'] = EquipmentState.ON
            new_states['dehum'] = EquipmentState.OFF
            logger.info(f"Humidification needed: RH={avg_humidity:.1f}%, DP={avg_dew_point:.1f}°F")
        elif avg_humidity > setpoint.humidity_min + self.hysteresis['humidity']:
            new_states['hum_solenoid'] = EquipmentState.OFF
        
        # VPD boundary checking
        if avg_vpd < setpoint.vpd_min:
            logger.debug(f"VPD low ({avg_vpd:.2f}), may need dehumidification")
        elif avg_vpd > setpoint.vpd_max:
            logger.debug(f"VPD high ({avg_vpd:.2f}), may need humidification")
        
        return new_states
    
    def _emergency_control(self, temp: float, humidity: float) -> Dict[str, EquipmentState]:
        """Emergency control mode"""
        states = self.equipment_states.copy()
        
        # Keep air circulation going
        states['supply_fan'] = EquipmentState.ON
        states['return_fan'] = EquipmentState.ON
        states['erv'] = EquipmentState.ON
        
        if temp > self.emergency_temp_max:
            # Too hot - maximum cooling
            states['mini_split'] = EquipmentState.ON  # Will need lower setpoint via IR
            states['dehum'] = EquipmentState.OFF  # Dehum generates heat
            states['hum_solenoid'] = EquipmentState.ON  # Evaporative cooling
        elif temp < self.emergency_temp_min:
            # Too cold
            states['mini_split'] = EquipmentState.ON  # Will need higher setpoint via IR
            states['dehum'] = EquipmentState.ON  # Generates some heat
            
        if humidity > self.emergency_humidity_max:
            states['dehum'] = EquipmentState.ON
            states['hum_solenoid'] = EquipmentState.OFF
        elif humidity < self.emergency_humidity_min:
            states['hum_solenoid'] = EquipmentState.ON
            states['dehum'] = EquipmentState.OFF
            
        return states
    
    def update_equipment_states(self, new_states: Dict[str, EquipmentState]):
        """Update equipment states with proper timing control"""
        current_time = time.time()
        
        # Check minimum cycle time for most equipment
        if current_time - self.last_control_time < self.min_cycle_time:
            return  # Too soon for general changes
        
        changes_made = False
        
        for equipment, new_state in new_states.items():
            if self.equipment_states[equipment] != new_state:
                # Special timing for dehumidifier
                if equipment == 'dehum':
                    if current_time - self.last_dehum_change < self.dehum_min_cycle:
                        continue  # Skip dehumidifier change
                    self.last_dehum_change = current_time
                
                logger.info(f"{equipment}: {self.equipment_states[equipment].value} → {new_state.value}")
                self.equipment_states[equipment] = new_state
                changes_made = True
        
        if changes_made:
            self.last_control_time = current_time
    
    def get_system_status(self) -> dict:
        """Get comprehensive system status"""
        avg_temp, avg_humidity, avg_dew_point, avg_vpd = self.get_dry_room_conditions()
        setpoint = self.calculate_linear_transition()
        
        # Calculate total progress through entire cycle
        phase_hours = {
            DryingPhase.DRY_INITIAL: 0,
            DryingPhase.DRY_MID: 48,
            DryingPhase.DRY_FINAL: 48 + 72,
            DryingPhase.CURE: 48 + 72 + 48,
            DryingPhase.STORAGE: 48 + 72 + 48 + 72,
            DryingPhase.COMPLETE: 48 + 72 + 48 + 72
        }
        
        elapsed_in_phase = (datetime.now() - self.phase_start_time).total_seconds() / 3600
        total_elapsed = phase_hours.get(self.current_phase, 0) + elapsed_in_phase
        total_cycle_hours = 48 + 72 + 48 + 72  # Total dry + cure time
        progress = min(100, (total_elapsed / total_cycle_hours) * 100)
        
        return {
            'phase': self.current_phase.value,
            'phase_description': self._get_phase_description(),
            'progress': round(progress, 1),
            'elapsed_hours': round(elapsed_in_phase, 1),
            'total_elapsed_hours': round(total_elapsed, 1),
            'temperature': round(avg_temp, 1),
            'humidity': round(avg_humidity, 1),
            'dew_point': round(avg_dew_point, 1),
            'vpd_current': round(avg_vpd, 2),
            'vpd_target': f"{setpoint.vpd_min:.1f}-{setpoint.vpd_max:.1f}",
            'temp_setpoint': round(self.mini_split_setpoint, 1),
            'dew_point_target': round(setpoint.dew_point_target, 1),
            'water_activity_estimate': round(self.estimated_water_activity, 3),
            'equipment': {k: v.value for k, v in self.equipment_states.items()},
            'sensors': {
                sensor_id: {
                    'temperature': round(reading.temperature, 1),
                    'humidity': round(reading.humidity, 1),
                    'dew_point': round(reading.dew_point, 1),
                    'vpd': round(reading.vpd_kpa, 2)
                }
                for sensor_id, reading in self.sensor_readings.items()
            },
            'setpoints': {
                'temperature': f"{setpoint.temp_target:.1f}±{setpoint.temp_tolerance:.1f}°F",
                'dew_point': f"{setpoint.dew_point_target:.1f}±{setpoint.dew_point_tolerance:.1f}°F",
                'humidity': f"{setpoint.humidity_min:.0f}-{setpoint.humidity_max:.0f}%",
                'vpd': f"{setpoint.vpd_min:.1f}-{setpoint.vpd_max:.1f} kPa"
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_phase_description(self) -> str:
        """Get human-readable phase description"""
        descriptions = {
            DryingPhase.DRY_INITIAL: "Initial moisture removal (Day 1-2)",
            DryingPhase.DRY_MID: "Mid-drying phase (Day 3-5)",
            DryingPhase.DRY_FINAL: "Final drying (Day 6-7)",
            DryingPhase.CURE: "Curing/Stabilization (Day 8-10)",
            DryingPhase.STORAGE: "COMPLETE - Idle/Storage mode (remove product)",
            DryingPhase.COMPLETE: "Process complete - aW target reached"
        }
        return descriptions.get(self.current_phase, "Unknown phase")
    
    def run_control_loop(self):
        """Main control loop"""
        logger.info("Starting Precision VPD Control System")
        logger.info(f"Initial phase: {self._get_phase_description()}")
        
        while True:
            try:
                # Read sensors and update readings FIRST!
                if self.hardware_mode and self.sensor_manager:
                    readings = self.sensor_manager.read_all_sensors()
                    for sensor_id, reading in readings.items():
                        if reading and reading.get('status') == 'ok':
                            self.update_sensor_reading(
                                sensor_id,
                                reading['temperature'],
                                reading['humidity']
                            )
                
                # THEN calculate control action
                new_states = self.calculate_control_action()
                
                # Update equipment states
                self.update_equipment_states(new_states)
                
                # Log status
                status = self.get_system_status()
                logger.info(f"[{status['phase']}] Progress: {status['progress']:.1f}% | "
                        f"Temp: {status['temperature']}°F | RH: {status['humidity']}% | "
                        f"DP: {status['dew_point']}°F | VPD: {status['vpd_current']} kPa | "
                        f"aW: ~{status['water_activity_estimate']:.3f}")
                
                # Sleep before next iteration
                time.sleep(10)  # Run control loop every 10 seconds
                
            except Exception as e:
                logger.error(f"Control loop error: {e}")
                time.sleep(5)

    def get_system_status(self):
        """Get complete system status for API"""
        
        # Get current phase and setpoints
        current_phase = self.current_phase
        phase_settings = self.phase_setpoints.get(current_phase, self.phase_setpoints[DryingPhase.DRY_INITIAL])
        
        # Get sensor averages
        avg_temp = 68.0
        avg_humidity = 60.0
        avg_vpd = 0.75
        
        if self.sensor_readings:
            temps = [r.temperature for r in self.sensor_readings.values() if hasattr(r, 'temperature') and r.temperature]
            humids = [r.humidity for r in self.sensor_readings.values() if hasattr(r, 'humidity') and r.humidity]
            vpds = [r.vpd_kpa for r in self.sensor_readings.values() if hasattr(r, 'vpd_kpa') and r.vpd_kpa]
            
            if temps:
                avg_temp = sum(temps) / len(temps)
            if humids:
                avg_humidity = sum(humids) / len(humids)
            if vpds:
                avg_vpd = sum(vpds) / len(vpds)
        
        # Calculate process time
        elapsed_hours = 0
        current_day = 1
        if self.process_start_time:
            elapsed = datetime.now() - self.process_start_time
            elapsed_hours = elapsed.total_seconds() / 3600
            current_day = elapsed.days + 1
        
        return {
            'current_phase': current_phase.value,
            'current_day': current_day,
            'elapsed_hours': elapsed_hours,
            'current_vpd': float(avg_vpd),
            'vpd_target_min': float(phase_settings.vpd_min),
            'vpd_target_max': float(phase_settings.vpd_max),
            'current_temp': float(avg_temp),
            'current_humidity': float(avg_humidity),
            'temp_target': float(phase_settings.temp_target),
            'humidity_min': float(phase_settings.humidity_min),
            'humidity_max': float(phase_settings.humidity_max),
            'dew_point_target': float(phase_settings.dew_point_target),
            'process_active': self.process_active,
            'equipment_states': {k: v.value for k, v in self.equipment_states.items()},
            'timestamp': datetime.now().isoformat()
        }

# Simulation mode for testing without hardware
class SimulationMode:
    """Simulate sensor readings and environmental response"""
    
    def __init__(self, controller: PrecisionVPDController):
        self.controller = controller
        # Start with typical initial conditions
        self.room_temp = 70.0
        self.room_humidity = 63.0
        self.supply_temp = 68.0
        self.supply_humidity = 60.0
        
    def generate_readings(self):
        """Generate simulated sensor readings with realistic responses"""
        import random
        
        # Simulate equipment effects on environment
        equipment = self.controller.equipment_states
        
        # Temperature effects
        if equipment['mini_split'] == EquipmentState.ON:
            # Mini-split gradually moves temp toward setpoint
            temp_error = self.room_temp - self.controller.mini_split_setpoint
            self.room_temp -= temp_error * 0.02  # Slow convergence
        
        # Humidity effects
        if equipment['dehum'] == EquipmentState.ON:
            self.room_humidity -= random.uniform(0.1, 0.3)
            self.room_temp += random.uniform(0.01, 0.05)  # Dehum adds slight heat
            
        if equipment['hum_solenoid'] == EquipmentState.ON:
            self.room_humidity += random.uniform(0.2, 0.4)
            self.room_temp -= random.uniform(0.01, 0.03)  # Evaporative cooling
        
        # ERV effects (fresh air exchange)
        if equipment['erv'] == EquipmentState.ON:
            # Pulls conditions slightly toward ambient (assumed 70°F, 50% RH)
            self.room_temp += (70 - self.room_temp) * 0.005
            self.room_humidity += (50 - self.room_humidity) * 0.005
        
        # Natural drift and variation
        self.room_temp += random.uniform(-0.1, 0.1)
        self.room_humidity += random.uniform(-0.2, 0.2)
        
        # Keep within reasonable bounds
        self.room_temp = max(60, min(80, self.room_temp))
        self.room_humidity = max(35, min(75, self.room_humidity))
        
        # Update dry room sensors with slight variations
        for i in range(1, 5):
            self.controller.update_sensor_reading(
                f'dry_{i}',
                self.room_temp + random.uniform(-1, 1),
                self.room_humidity + random.uniform(-2, 2)
            )
        
        # Air room sensor (equipment room)
        self.controller.update_sensor_reading(
            'air_room',
            self.room_temp + random.uniform(-0.5, 0.5),
            self.room_humidity + random.uniform(-1, 1)
        )
        
        # Supply duct sensor (conditioned air)
        self.supply_temp = 0.8 * self.supply_temp + 0.2 * self.room_temp
        self.supply_humidity = 0.8 * self.supply_humidity + 0.2 * self.room_humidity
        self.controller.update_sensor_reading(
            'supply_duct',
            self.supply_temp + random.uniform(-0.5, 0.5),
            self.supply_humidity + random.uniform(-1, 1)
        )