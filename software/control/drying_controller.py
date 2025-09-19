#!/usr/bin/env python3
"""
Cannabis Drying Controller
Implements automated control based on VPD calculations

Controls equipment to maintain precise drying conditions using VPD targets.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from vpd_calculator import VPDCalculator, VPDReading, DryingProfile

logger = logging.getLogger(__name__)

class DryingPhase(Enum):
    """Drying process phases"""
    STARTUP = "startup"
    DRYING = "drying"
    CURING = "curing"
    STORAGE = "storage"
    FINISHED = "finished"

class EquipmentState(Enum):
    """Equipment operational states"""
    OFF = "off"
    IDLE = "idle"
    ON = "on"
    AUTO = "auto"
    ERROR = "error"

@dataclass
class ControlAction:
    """Represents a control action to be taken"""
    equipment: str
    action: str
    value: Optional[float] = None
    reason: str = ""
    priority: int = 1  # 1=low, 5=critical

@dataclass
class DryingSession:
    """Represents a complete drying/curing session"""
    session_id: str
    start_time: datetime
    total_duration_days: int
    drying_days: int
    curing_days: int
    profiles: List[str]
    current_phase: DryingPhase
    target_water_activity: float = 0.62

class CannabisController:
    """
    Main controller for cannabis drying system.
    
    Implements precise VPD control similar to commercial systems but with
    open-source algorithms and enhanced flexibility.
    """
    
    def __init__(self):
        """Initialize the cannabis drying controller"""
        self.vpd_calc = VPDCalculator()
        self.current_session: Optional[DryingSession] = None
        self.equipment_states: Dict[str, EquipmentState] = {}
        self.control_history: List[ControlAction] = []
        self.vpd_history: List[VPDReading] = []
        
        # Control parameters
        self.control_tolerance = 0.05  # kPa tolerance for VPD
        self.max_adjustments_per_hour = 4
        self.last_adjustment_time = datetime.now()
        
        # Equipment definitions
        self.equipment = {
            "dehumidifier": {"type": "dehumidification", "power_range": (0, 100)},
            "humidifier": {"type": "humidification", "power_range": (0, 100)},
            "mini_split": {"type": "temperature", "temp_range": (60, 80)},
            "erv": {"type": "air_exchange", "power_range": (0, 100)},
            "exhaust_fan": {"type": "air_circulation", "power_range": (0, 100)},
            "supply_fan": {"type": "air_circulation", "power_range": (0, 100)}
        }
        
        # Initialize equipment states
        for equipment in self.equipment.keys():
            self.equipment_states[equipment] = EquipmentState.IDLE
        
        logger.info("Cannabis Controller initialized")
    
    def start_drying_session(self, session_config: Dict) -> DryingSession:
        """
        Start a new drying session.
        
        Args:
            session_config: Configuration dictionary with session parameters
            
        Returns:
            DryingSession object
        """
        session = DryingSession(
            session_id=session_config.get("session_id", f"session_{int(time.time())}"),
            start_time=datetime.now(),
            total_duration_days=session_config.get("total_days", 8),
            drying_days=session_config.get("drying_days", 4),
            curing_days=session_config.get("curing_days", 4),
            profiles=session_config.get("profiles", ["cannatrol_dry", "cannatrol_cure"]),
            current_phase=DryingPhase.STARTUP,
            target_water_activity=session_config.get("target_water_activity", 0.62)
        )
        
        self.current_session = session
        logger.info(f"Started drying session: {session.session_id}")
        return session
    
    def get_current_phase_profile(self) -> str:
        """Get the appropriate profile for the current drying phase"""
        if not self.current_session:
            return "cannatrol_dry"  # Default
        
        elapsed_time = datetime.now() - self.current_session.start_time
        elapsed_days = elapsed_time.days
        
        if elapsed_days == 0:
            self.current_session.current_phase = DryingPhase.STARTUP
            return "gentle_start"  # Gentle start for first hours
        elif elapsed_days <= self.current_session.drying_days:
            self.current_session.current_phase = DryingPhase.DRYING
            if elapsed_days <= 2:
                return "cannatrol_dry"
            else:
                return "finish_dry"  # More aggressive finish
        elif elapsed_days <= (self.current_session.drying_days + self.current_session.curing_days):
            self.current_session.current_phase = DryingPhase.CURING
            return "cannatrol_cure"
        else:
            self.current_session.current_phase = DryingPhase.STORAGE
            return "cannatrol_storage"
    
    def analyze_current_conditions(self, sensor_readings: Dict) -> VPDReading:
        """
        Analyze current environmental conditions from sensor readings.
        
        Args:
            sensor_readings: Dict with sensor data from all zones
            
        Returns:
            VPDReading with averaged/calculated conditions
        """
        # Average the drying room sensors (zones 1-4)
        drying_temps = []
        drying_humidities = []
        
        for zone in range(1, 5):
            sensor_key = f"zone_{zone}"
            if sensor_key in sensor_readings:
                drying_temps.append(sensor_readings[sensor_key]["temperature"])
                drying_humidities.append(sensor_readings[sensor_key]["humidity"])
        
        if not drying_temps:
            # Fallback to any available sensor
            first_sensor = next(iter(sensor_readings.values()))
            avg_temp = first_sensor["temperature"]
            avg_humidity = first_sensor["humidity"]
        else:
            avg_temp = sum(drying_temps) / len(drying_temps)
            avg_humidity = sum(drying_humidities) / len(drying_humidities)
        
        # Calculate VPD from averaged conditions
        vpd_reading = self.vpd_calc.calculate_vpd_from_rh(avg_temp, avg_humidity)
        
        # Store in history
        self.vpd_history.append(vpd_reading)
        
        # Keep only last 1000 readings
        if len(self.vpd_history) > 1000:
            self.vpd_history = self.vpd_history[-1000:]
        
        return vpd_reading
    
    def generate_control_actions(self, vpd_reading: VPDReading) -> List[ControlAction]:
        """
        Generate control actions based on current VPD and target conditions.
        
        Args:
            vpd_reading: Current VPD reading
            
        Returns:
            List of ControlAction objects
        """
        actions = []
        
        # Get current phase and target profile
        current_profile = self.get_current_phase_profile()
        
        # Get VPD recommendations
        recommendations = self.vpd_calc.get_vpd_adjustment_recommendation(
            vpd_reading, current_profile
        )
        
        if recommendations["in_range"]:
            # Conditions are good - maintain current state
            actions.append(ControlAction(
                equipment="system",
                action="maintain",
                reason="VPD within target range",
                priority=1
            ))
            return actions
        
        vpd_diff = recommendations["vpd_difference"]
        
        if vpd_diff < -0.1:  # VPD too low (too wet)
            # Need to increase drying power
            actions.extend([
                ControlAction(
                    equipment="dehumidifier",
                    action="increase_power",
                    value=min(100, self._get_current_power("dehumidifier") + 10),
                    reason="VPD too low - increase dehumidification",
                    priority=3
                ),
                ControlAction(
                    equipment="exhaust_fan",
                    action="increase_speed",
                    value=min(100, self._get_current_power("exhaust_fan") + 5),
                    reason="VPD too low - increase air circulation",
                    priority=2
                )
            ])
            
            # If humidifier is running, reduce it
            if self.equipment_states["humidifier"] == EquipmentState.ON:
                actions.append(ControlAction(
                    equipment="humidifier",
                    action="reduce_power",
                    value=max(0, self._get_current_power("humidifier") - 10),
                    reason="VPD too low - reduce humidification",
                    priority=3
                ))
        
        elif vpd_diff > 0.1:  # VPD too high (too dry)
            # Need to reduce drying power or add humidity
            actions.extend([
                ControlAction(
                    equipment="dehumidifier",
                    action="reduce_power",
                    value=max(0, self._get_current_power("dehumidifier") - 10),
                    reason="VPD too high - reduce dehumidification",
                    priority=3
                ),
                ControlAction(
                    equipment="humidifier",
                    action="increase_power",
                    value=min(100, self._get_current_power("humidifier") + 15),
                    reason="VPD too high - add humidity",
                    priority=3
                )
            ])
        
        # Temperature adjustments if needed
        profile = self.vpd_calc.profiles[current_profile]
        temp_diff = vpd_reading.air_temp_f - profile.target_temp_f
        
        if abs(temp_diff) > 2.0:  # More than 2°F off target
            if temp_diff > 0:  # Too hot
                actions.append(ControlAction(
                    equipment="mini_split",
                    action="decrease_temp",
                    value=profile.target_temp_f,
                    reason=f"Temperature {temp_diff:.1f}°F above target",
                    priority=4
                ))
            else:  # Too cold
                actions.append(ControlAction(
                    equipment="mini_split",
                    action="increase_temp", 
                    value=profile.target_temp_f,
                    reason=f"Temperature {abs(temp_diff):.1f}°F below target",
                    priority=4
                ))
        
        return actions
    
    def _get_current_power(self, equipment: str) -> float:
        """Get current power level for equipment (0-100)"""
        # This would interface with actual hardware
        # For now, return a simulated value
        return 50.0  # Default middle power
    
    def execute_control_actions(self, actions: List[ControlAction]) -> Dict:
        """
        Execute a list of control actions.
        
        Args:
            actions: List of ControlAction objects
            
        Returns:
            Dictionary with execution results
        """
        results = {"executed": [], "failed": [], "skipped": []}
        
        # Check if we're within rate limiting
        time_since_last = datetime.now() - self.last_adjustment_time
        if time_since_last < timedelta(minutes=15):
            recent_adjustments = len([a for a in self.control_history 
                                    if (datetime.now() - a.timestamp if hasattr(a, 'timestamp') else timedelta(0)) < timedelta(hours=1)])
            if recent_adjustments >= self.max_adjustments_per_hour:
                logger.warning("Rate limit reached - skipping adjustments")
                return {"error": "Rate limit reached"}
        
        # Sort by priority (highest first)
        sorted_actions = sorted(actions, key=lambda x: x.priority, reverse=True)
        
        for action in sorted_actions:
            try:
                # Execute the action (interface with hardware here)
                success = self._execute_single_action(action)
                
                if success:
                    results["executed"].append(action)
                    # Add timestamp to action for history
                    action.timestamp = datetime.now()
                    self.control_history.append(action)
                    logger.info(f"Executed: {action.equipment} - {action.action}")
                else:
                    results["failed"].append(action)
                    logger.error(f"Failed: {action.equipment} - {action.action}")
                    
            except Exception as e:
                results["failed"].append(action)
                logger.error(f"Error executing {action.equipment} - {action.action}: {e}")
        
        if results["executed"]:
            self.last_adjustment_time = datetime.now()
        
        return results
    
    def _execute_single_action(self, action: ControlAction) -> bool:
        """
        Execute a single control action.
        This is where you'd interface with actual hardware.
        
        Args:
            action: ControlAction to execute
            
        Returns:
            True if successful, False otherwise
        """
        # This is where hardware interface code would go
        # For development, just simulate success
        
        equipment = action.equipment
        action_type = action.action
        
        if equipment not in self.equipment and equipment != "system":
            return False
        
        # Simulate equipment response
        if action_type == "maintain":
            return True
        elif "increase" in action_type:
            self.equipment_states[equipment] = EquipmentState.ON
            return True
        elif "reduce" in action_type or "decrease" in action_type:
            if action.value == 0:
                self.equipment_states[equipment] = EquipmentState.IDLE
            else:
                self.equipment_states[equipment] = EquipmentState.ON
            return True
        
        return True  # Default success for simulation
    
    def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        status = {
            "session": self.current_session.__dict__ if self.current_session else None,
            "equipment_states": {k: v.value for k, v in self.equipment_states.items()},
            "current_phase": self.current_session.current_phase.value if self.current_session else "idle",
            "vpd_history_count": len(self.vpd_history),
            "last_vpd": self.vpd_history[-1].__dict__ if self.vpd_history else None,
            "control_actions_today": len([a for a in self.control_history 
                                        if hasattr(a, 'timestamp') and 
                                        (datetime.now() - a.timestamp).days == 0])
        }
        
        if self.current_session:
            elapsed = datetime.now() - self.current_session.start_time
            status["elapsed_time"] = str(elapsed)
            status["progress_percent"] = min(100, (elapsed.total_seconds() / 
                                                 (self.current_session.total_duration_days * 24 * 3600)) * 100)
        
        return status
    
    def emergency_stop(self) -> None:
        """Emergency stop - shut down all equipment"""
        logger.critical("EMERGENCY STOP ACTIVATED")
        
        for equipment in self.equipment.keys():
            self.equipment_states[equipment] = EquipmentState.OFF
            # Here you would actually shut down hardware
        
        if self.current_session:
            self.current_session.current_phase = DryingPhase.FINISHED

# Example usage
if __name__ == "__main__":
    # Initialize controller
    controller = CannabisController()
    
    print("=== Cannabis Drying Controller Demo ===\n")
    
    # Start a session
    session_config = {
        "session_id": "demo_session",
        "total_days": 8,
        "drying_days": 4,
        "curing_days": 4
    }
    
    session = controller.start_drying_session(session_config)
    print(f"Started session: {session.session_id}")
    
    # Simulate sensor readings
    sensor_readings = {
        "zone_1": {"temperature": 68.5, "humidity": 61.0},
        "zone_2": {"temperature": 68.2, "humidity": 60.5},
        "zone_3": {"temperature": 68.8, "humidity": 61.5},
        "zone_4": {"temperature": 68.3, "humidity": 60.8},
        "air_room": {"temperature": 69.1, "humidity": 58.2},
        "supply_duct": {"temperature": 67.9, "humidity": 59.5}
    }
    
    # Analyze conditions
    vpd_reading = controller.analyze_current_conditions(sensor_readings)
    print(f"\nCurrent Conditions:")
    print(f"VPD: {vpd_reading.vpd_kpa:.2f} kPa")
    print(f"Temperature: {vpd_reading.air_temp_f:.1f}°F")
    print(f"Dew Point: {vpd_reading.dew_point_f:.1f}°F")
    print(f"Humidity: {vpd_reading.relative_humidity:.1f}%")
    
    # Generate control actions
    actions = controller.generate_control_actions(vpd_reading)
    print(f"\nControl Actions ({len(actions)}):")
    for action in actions:
        print(f"  - {action.equipment}: {action.action} (Priority: {action.priority})")
        print(f"    Reason: {action.reason}")
    
    # Execute actions
    results = controller.execute_control_actions(actions)
    print(f"\nExecution Results:")
    print(f"  Executed: {len(results['executed'])}")
    print(f"  Failed: {len(results['failed'])}")
    
    # System status
    status = controller.get_system_status()
    print(f"\nSystem Status:")
    print(f"  Phase: {status['current_phase']}")
    print(f"  Equipment States: {status['equipment_states']}")