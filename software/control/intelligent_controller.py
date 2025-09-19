#!/usr/bin/env python3
"""
Intelligent Cannabis Drying Controller
Disturbance-aware control system for trichome preservation

Implements smart disturbance detection and graduated equipment response
to prevent trichome damage from environmental fluctuations.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Deque
from dataclasses import dataclass
from enum import Enum
from collections import deque
import statistics

from vpd_calculator import ResearchOptimizedVPD, VPDReading, DryingPhase

logger = logging.getLogger(__name__)

class DisturbanceLevel(Enum):
    """Environmental disturbance severity levels"""
    STABLE = "stable"           # Normal operation
    MINOR = "minor"            # Small fluctuations
    MODERATE = "moderate"      # Noticeable changes (door opening)
    MAJOR = "major"            # Large disturbance (extended door open)
    CRITICAL = "critical"      # Emergency conditions

class EquipmentResponse(Enum):
    """Equipment response strategies"""
    IMMEDIATE = "immediate"     # React instantly (safety only)
    GRADUATED = "graduated"    # Slow ramp to target
    DELAYED = "delayed"        # Wait and observe
    SUSPENDED = "suspended"    # Hold current settings

@dataclass
class SensorTrend:
    """Tracks sensor reading trends for disturbance detection"""
    current_value: float
    previous_value: float
    rate_of_change: float      # Units per minute
    stability_score: float     # 0-1 (1 = perfectly stable)
    disturbance_detected: bool

@dataclass
class DisturbanceEvent:
    """Records environmental disturbance events"""
    timestamp: datetime
    duration_minutes: float
    severity: DisturbanceLevel
    affected_parameters: List[str]  # temp, humidity, etc.
    recovery_time_minutes: Optional[float] = None

@dataclass
class GraduatedAction:
    """Equipment action with graduated response"""
    equipment: str
    target_setting: float
    current_setting: float
    step_size: float          # How much to adjust per cycle
    max_rate_per_minute: float # Maximum change rate
    response_strategy: EquipmentResponse
    priority: int
    reason: str

class IntelligentController:
    """
    Intelligent controller with disturbance detection and trichome protection.
    
    Key features:
    - Detects environmental disturbances (door opening, equipment failures)
    - Graduated equipment response to prevent overcorrection
    - Trichome-protective control algorithms
    - Historical trend analysis for smart decision making
    """
    
    def __init__(self):
        """Initialize intelligent controller"""
        self.vpd_calc = ResearchOptimizedVPD()
        
        # Sensor trend tracking (rolling windows)
        self.sensor_history: Dict[str, Deque[VPDReading]] = {
            "zone_1": deque(maxlen=20),  # Last 20 readings per zone
            "zone_2": deque(maxlen=20),
            "zone_3": deque(maxlen=20), 
            "zone_4": deque(maxlen=20),
            "air_room": deque(maxlen=20),
            "supply_duct": deque(maxlen=20),
            "average": deque(maxlen=20)
        }
        
        # Disturbance detection parameters
        self.disturbance_thresholds = {
            "temperature_change_per_minute": 2.0,   # °F/min indicates disturbance
            "humidity_change_per_minute": 5.0,      # %RH/min indicates disturbance
            "vpd_change_per_minute": 0.1,           # kPa/min indicates disturbance
            "zone_variance_threshold": 3.0,         # °F variance between zones
            "stability_window_minutes": 10,         # Time window for stability analysis
            "recovery_timeout_minutes": 15         # Max time to wait for recovery
        }
        
        # Equipment response settings
        self.equipment_constraints = {
            "dehumidifier": {
                "max_change_per_minute": 5.0,       # % power per minute
                "overshoot_protection": 0.8,        # Don't go full power immediately
                "response_delay_minutes": 3.0       # Wait before major changes
            },
            "humidifier": {
                "max_change_per_minute": 3.0,       # % power per minute  
                "overshoot_protection": 0.7,        # More conservative than dehumid
                "response_delay_minutes": 2.0       # Faster response for dryness
            },
            "mini_split": {
                "max_change_per_minute": 0.5,       # °F per minute
                "overshoot_protection": 0.9,        # Temperature is critical
                "response_delay_minutes": 5.0       # HVAC is slow to respond anyway
            },
            "exhaust_fan": {
                "max_change_per_minute": 10.0,      # % power per minute
                "overshoot_protection": 1.0,        # Fans can change quickly
                "response_delay_minutes": 1.0       # Fast air movement response
            },
            "supply_fan": {
                "max_change_per_minute": 10.0,      # % power per minute
                "overshoot_protection": 1.0,
                "response_delay_minutes": 1.0
            },
            "erv": {
                "max_change_per_minute": 8.0,       # % power per minute
                "overshoot_protection": 0.8,        # Conservative with fresh air
                "response_delay_minutes": 2.0
            }
        }
        
        # Current equipment settings and states
        self.current_settings = {
            "dehumidifier": 0.0,
            "humidifier": 0.0,
            "mini_split": 68.0,
            "erv": 25.0,
            "exhaust_fan": 40.0,
            "supply_fan": 40.0
        }
        
        self.pending_actions: List[GraduatedAction] = []
        self.disturbance_history: List[DisturbanceEvent] = []
        self.last_control_update = datetime.now()
        
        # Tightened tolerances for trichome protection
        self.precision_tolerances = {
            "temperature_f": 0.3,        # ±0.3°F (tighter than 0.5°F)
            "dew_point_f": 0.2,          # ±0.2°F (tighter than 0.3°F) 
            "humidity_percent": 1.0,     # ±1% RH (very tight)
            "adjustment_deadband": 0.05  # Smaller deadband for precision
        }
        
        logger.info("Intelligent Controller initialized with trichome protection")
    
    def analyze_sensor_trends(self, sensor_readings: Dict) -> Dict[str, SensorTrend]:
        """
        Analyze sensor trends to detect environmental disturbances.
        
        Args:
            sensor_readings: Current sensor data from all zones
            
        Returns:
            Dictionary of sensor trends for each zone
        """
        trends = {}
        current_time = datetime.now()
        
        # Process each sensor zone
        for zone, reading_data in sensor_readings.items():
            if zone not in self.sensor_history:
                self.sensor_history[zone] = deque(maxlen=20)
            
            # Convert to VPDReading format
            vpd_reading = self.vpd_calc.calculate_vpd_from_conditions(
                reading_data["temperature"], 
                reading_data["humidity"]
            )
            vpd_reading.timestamp = current_time
            
            # Add to history
            history = self.sensor_history[zone]
            history.append(vpd_reading)
            
            # Need at least 2 readings for trend analysis
            if len(history) < 2:
                trends[zone] = SensorTrend(
                    current_value=vpd_reading.air_temp_f,
                    previous_value=vpd_reading.air_temp_f,
                    rate_of_change=0.0,
                    stability_score=1.0,
                    disturbance_detected=False
                )
                continue
            
            # Calculate trends for temperature (most critical for trichomes)
            current_temp = vpd_reading.air_temp_f
            previous_temp = history[-2].air_temp_f if len(history) >= 2 else current_temp
            
            # Time difference in minutes
            time_diff = (current_time - history[-2].timestamp).total_seconds() / 60
            if time_diff == 0:
                time_diff = 0.1  # Prevent division by zero
            
            # Rate of change per minute
            temp_rate = (current_temp - previous_temp) / time_diff
            
            # Calculate stability score (last 10 readings)
            recent_temps = [r.air_temp_f for r in list(history)[-10:]]
            if len(recent_temps) >= 3:
                temp_std = statistics.stdev(recent_temps)
                stability_score = max(0.0, 1.0 - (temp_std / 2.0))  # Normalize
            else:
                stability_score = 1.0
            
            # Detect disturbance
            disturbance_detected = (
                abs(temp_rate) > self.disturbance_thresholds["temperature_change_per_minute"] or
                stability_score < 0.7
            )
            
            trends[zone] = SensorTrend(
                current_value=current_temp,
                previous_value=previous_temp,
                rate_of_change=temp_rate,
                stability_score=stability_score,
                disturbance_detected=disturbance_detected
            )
        
        return trends
    
    def detect_environmental_disturbance(self, trends: Dict[str, SensorTrend]) -> DisturbanceLevel:
        """
        Determine overall environmental disturbance level.
        
        Args:
            trends: Sensor trend analysis results
            
        Returns:
            Overall disturbance level
        """
        if not trends:
            return DisturbanceLevel.STABLE
        
        # Count zones with disturbances
        disturbed_zones = sum(1 for trend in trends.values() if trend.disturbance_detected)
        total_zones = len(trends)
        
        # Average stability score
        avg_stability = statistics.mean(trend.stability_score for trend in trends.values())
        
        # Maximum rate of change
        max_rate = max(abs(trend.rate_of_change) for trend in trends.values())
        
        # Determine disturbance level
        if disturbed_zones == 0 and avg_stability > 0.9:
            return DisturbanceLevel.STABLE
        elif disturbed_zones <= 1 and avg_stability > 0.7:
            return DisturbanceLevel.MINOR
        elif disturbed_zones <= 2 or max_rate > 3.0:
            return DisturbanceLevel.MODERATE
        elif disturbed_zones > 2 or max_rate > 5.0:
            return DisturbanceLevel.MAJOR
        else:
            return DisturbanceLevel.CRITICAL
    
    def generate_graduated_actions(self, vpd_reading: VPDReading, 
                                 disturbance_level: DisturbanceLevel,
                                 start_time: datetime) -> List[GraduatedAction]:
        """
        Generate graduated equipment actions based on conditions and disturbance level.
        
        Args:
            vpd_reading: Current average environmental reading
            disturbance_level: Current environmental disturbance level
            start_time: Process start time
            
        Returns:
            List of graduated actions
        """
        actions = []
        
        # Get current phase targets
        current_phase = self.vpd_calc.get_current_phase_from_elapsed_time(start_time)
        phase_progress = self.vpd_calc.calculate_phase_progress(start_time, current_phase)
        target_temp, target_dew, target_rh = self.vpd_calc.get_phase_target_conditions(
            current_phase, phase_progress
        )
        
        # Calculate deviations
        temp_deviation = vpd_reading.air_temp_f - target_temp
        rh_deviation = vpd_reading.relative_humidity - target_rh
        
        # Determine response strategy based on disturbance level
        if disturbance_level in [DisturbanceLevel.STABLE, DisturbanceLevel.MINOR]:
            response_strategy = EquipmentResponse.GRADUATED
            priority_multiplier = 1.0
        elif disturbance_level == DisturbanceLevel.MODERATE:
            response_strategy = EquipmentResponse.DELAYED
            priority_multiplier = 0.5  # Reduce response strength
        elif disturbance_level == DisturbanceLevel.MAJOR:
            response_strategy = EquipmentResponse.SUSPENDED
            priority_multiplier = 0.2  # Minimal response
        else:  # CRITICAL
            response_strategy = EquipmentResponse.IMMEDIATE
            priority_multiplier = 2.0  # Emergency response
        
        # Temperature control with graduated response
        if abs(temp_deviation) > self.precision_tolerances["temperature_f"]:
            current_temp_setting = self.current_settings["mini_split"]
            
            # Calculate conservative adjustment
            adjustment = temp_deviation * 0.6 * priority_multiplier  # Conservative factor
            new_temp_setting = current_temp_setting - adjustment
            
            # Apply equipment constraints
            constraints = self.equipment_constraints["mini_split"]
            max_change = constraints["max_change_per_minute"] * 5  # 5-minute window
            adjustment = max(-max_change, min(max_change, adjustment))
            
            new_temp_setting = max(60, min(80, current_temp_setting - adjustment))
            
            if abs(new_temp_setting - current_temp_setting) >= self.precision_tolerances["adjustment_deadband"]:
                actions.append(GraduatedAction(
                    equipment="mini_split",
                    target_setting=new_temp_setting,
                    current_setting=current_temp_setting,
                    step_size=abs(adjustment) / 10,  # 10 steps to reach target
                    max_rate_per_minute=constraints["max_change_per_minute"],
                    response_strategy=response_strategy,
                    priority=5,
                    reason=f"Temperature {temp_deviation:+.2f}°F from target, disturbance: {disturbance_level.value}"
                ))
        
        # Humidity control with disturbance awareness
        if abs(rh_deviation) > self.precision_tolerances["humidity_percent"]:
            
            if rh_deviation > 0:  # Too humid
                current_dehumid = self.current_settings["dehumidifier"]
                constraints = self.equipment_constraints["dehumidifier"]
                
                # Scale response based on disturbance level
                adjustment = min(25, abs(rh_deviation) * 3 * priority_multiplier)
                new_setting = min(100, current_dehumid + adjustment)
                
                # Apply overshoot protection during disturbances
                if disturbance_level != DisturbanceLevel.STABLE:
                    new_setting *= constraints["overshoot_protection"]
                
                actions.append(GraduatedAction(
                    equipment="dehumidifier",
                    target_setting=new_setting,
                    current_setting=current_dehumid,
                    step_size=adjustment / 8,  # Gradual steps
                    max_rate_per_minute=constraints["max_change_per_minute"],
                    response_strategy=response_strategy,
                    priority=4,
                    reason=f"RH {rh_deviation:+.1f}% above target"
                ))
                
            else:  # Too dry
                current_humid = self.current_settings["humidifier"]
                constraints = self.equipment_constraints["humidifier"]
                
                adjustment = min(20, abs(rh_deviation) * 4 * priority_multiplier)
                new_setting = min(100, current_humid + adjustment)
                
                # More conservative humidification during disturbances
                if disturbance_level != DisturbanceLevel.STABLE:
                    new_setting *= constraints["overshoot_protection"]
                
                actions.append(GraduatedAction(
                    equipment="humidifier",
                    target_setting=new_setting,
                    current_setting=current_humid,
                    step_size=adjustment / 6,
                    max_rate_per_minute=constraints["max_change_per_minute"],
                    response_strategy=response_strategy,
                    priority=4,
                    reason=f"RH {rh_deviation:+.1f}% below target"
                ))
        
        # Air circulation adjustments (help with recovery)
        if disturbance_level in [DisturbanceLevel.MODERATE, DisturbanceLevel.MAJOR]:
            # Temporarily increase circulation to help stabilize
            for fan in ["exhaust_fan", "supply_fan"]:
                current_speed = self.current_settings[fan]
                if current_speed < 60:
                    new_speed = min(70, current_speed + 15)
                    actions.append(GraduatedAction(
                        equipment=fan,
                        target_setting=new_speed,
                        current_setting=current_speed,
                        step_size=5.0,
                        max_rate_per_minute=self.equipment_constraints[fan]["max_change_per_minute"],
                        response_strategy=EquipmentResponse.GRADUATED,
                        priority=2,
                        reason=f"Increase circulation during {disturbance_level.value} disturbance"
                    ))
        
        return actions
    
    def execute_graduated_actions(self, actions: List[GraduatedAction]) -> Dict:
        """
        Execute graduated actions with intelligent timing and ramping.
        
        Args:
            actions: List of graduated actions to execute
            
        Returns:
            Execution results
        """
        results = {"executed": [], "delayed": [], "suspended": [], "failed": []}
        current_time = datetime.now()
        
        for action in actions:
            try:
                # Check response strategy
                if action.response_strategy == EquipmentResponse.SUSPENDED:
                    results["suspended"].append(action)
                    logger.info(f"Suspended action for {action.equipment} due to disturbance")
                    continue
                
                elif action.response_strategy == EquipmentResponse.DELAYED:
                    # Check if enough time has passed
                    equipment_constraints = self.equipment_constraints[action.equipment]
                    delay_required = timedelta(minutes=equipment_constraints["response_delay_minutes"])
                    
                    if current_time - self.last_control_update < delay_required:
                        results["delayed"].append(action)
                        logger.info(f"Delayed action for {action.equipment} - waiting for stability")
                        continue
                
                # Execute graduated change
                setting_change = min(action.step_size, 
                                   abs(action.target_setting - action.current_setting))
                
                if action.target_setting > action.current_setting:
                    new_setting = action.current_setting + setting_change
                else:
                    new_setting = action.current_setting - setting_change
                
                # Update current setting
                self.current_settings[action.equipment] = new_setting
                
                # Here you would interface with actual hardware
                success = self._execute_equipment_change(action.equipment, new_setting)
                
                if success:
                    results["executed"].append(action)
                    logger.info(f"Executed graduated change: {action.equipment} → {new_setting:.1f}")
                else:
                    results["failed"].append(action)
                    
            except Exception as e:
                results["failed"].append(action)
                logger.error(f"Failed to execute action for {action.equipment}: {e}")
        
        if results["executed"]:
            self.last_control_update = current_time
        
        return results
    
    def _execute_equipment_change(self, equipment: str, setting: float) -> bool:
        """Execute actual equipment change (hardware interface point)"""
        # This is where you'd interface with relays, IR controllers, etc.
        # For now, simulate success
        logger.debug(f"Hardware command: {equipment} set to {setting}")
        return True
    
    def get_trichome_protection_status(self) -> Dict:
        """Get status of trichome protection measures"""
        recent_disturbances = [d for d in self.disturbance_history 
                              if (datetime.now() - d.timestamp).total_seconds() < 3600]  # Last hour
        
        return {
            "precision_tolerances": self.precision_tolerances,
            "recent_disturbances_count": len(recent_disturbances),
            "current_settings": self.current_settings.copy(),
            "pending_actions_count": len(self.pending_actions),
            "trichome_protection_active": True,
            "last_control_update": self.last_control_update.isoformat()
        }

# Example usage and testing
if __name__ == "__main__":
    print("=== Intelligent Cannabis Controller Demo ===\n")
    
    # Initialize controller
    controller = IntelligentController()
    print("✅ Intelligent Controller initialized")
    
    # Simulate normal conditions
    print("\n📊 Testing Stable Conditions:")
    stable_readings = {
        "zone_1": {"temperature": 67.8, "humidity": 58.5},
        "zone_2": {"temperature": 67.9, "humidity": 58.3},
        "zone_3": {"temperature": 67.7, "humidity": 58.7},
        "zone_4": {"temperature": 67.8, "humidity": 58.4}
    }
    
    trends = controller.analyze_sensor_trends(stable_readings)
    disturbance = controller.detect_environmental_disturbance(trends)
    print(f"Disturbance Level: {disturbance.value}")
    
    # Simulate door opening (major disturbance)
    print("\n🚪 Testing Door Opening Scenario:")
    door_open_readings = {
        "zone_1": {"temperature": 65.2, "humidity": 45.8},  # Sudden change
        "zone_2": {"temperature": 66.1, "humidity": 48.3},
        "zone_3": {"temperature": 67.9, "humidity": 58.1},  # Less affected
        "zone_4": {"temperature": 67.5, "humidity": 56.9}
    }
    
    # Add to history to simulate progression
    time.sleep(0.1)  # Small delay for timestamp difference
    trends = controller.analyze_sensor_trends(door_open_readings)
    disturbance = controller.detect_environmental_disturbance(trends)
    print(f"Disturbance Level: {disturbance.value}")
    
    # Show trichome protection status
    protection_status = controller.get_trichome_protection_status()
    print(f"\n🛡️  Trichome Protection Status:")
    print(f"Temperature Tolerance: ±{protection_status['precision_tolerances']['temperature_f']}°F")
    print(f"Humidity Tolerance: ±{protection_status['precision_tolerances']['humidity_percent']}%")
    print(f"Recent Disturbances: {protection_status['recent_disturbances_count']}")
    
    print(f"\n⚙️  Equipment Response Strategy:")
    print(f"- Graduated response with overshoot protection")
    print(f"- Disturbance-aware delay mechanisms") 
    print(f"- Trichome-protective precision tolerances")
    print(f"- Intelligent trend analysis and stability scoring")
    
    print("\n✅ System ready for trichome-safe cannabis processing!")