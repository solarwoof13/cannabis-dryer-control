#!/usr/bin/env python3
"""
VPD (Vapor Pressure Deficit) Calculation Engine
Cannabis Drying and Curing Control System

Implements research-optimized step-down drying process for maximum terpene retention
and optimal water activity targeting (0.60-0.62 aW).
"""

import math
import logging
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

class DryingPhase(Enum):
    """Precise drying phases based on research optimization"""
    INITIAL_MOISTURE_REMOVAL = "initial_moisture"  # Day 1-2
    MID_DRYING = "mid_drying"                     # Day 3-5
    FINAL_DRY = "final_dry"                       # Day 6-7
    STABILIZATION_CURE = "stabilization"          # Day 8-10

@dataclass
class VPDReading:
    """Represents a VPD calculation result with water activity estimation"""
    vpd_kpa: float
    air_temp_f: float
    dew_point_f: float
    relative_humidity: float
    saturation_pressure_kpa: float
    actual_pressure_kpa: float
    estimated_water_activity: float
    timestamp: datetime

@dataclass
class StepDownProfile:
    """Research-optimized stepped drying profile"""
    phase: DryingPhase
    duration_hours: int
    temp_range_f: Tuple[float, float]    # (min, max)
    dew_point_range_f: Tuple[float, float]
    rh_range_percent: Tuple[float, float]
    vpd_target_kpa: Tuple[float, float]   # (min, max)
    target_water_activity: Tuple[float, float]  # Expected aW range
    notes: str

class ResearchOptimizedVPD:
    """
    Research-optimized VPD calculator implementing step-down drying process.
    
    Based on cannabis research showing:
    - Terpene retention >90% at 60-70°F with controlled RH stepping
    - Water activity 0.60-0.62 for optimal microbial safety
    - VPD 0.7-1.0 kPa for balanced moisture removal
    - 8-10 day total process for maximum quality
    """
    
    def __init__(self):
        """Initialize with research-optimized step-down profiles"""
        self.step_profiles = self._create_research_profiles()
        logger.info("Research-Optimized VPD Calculator initialized")
    
    def _create_research_profiles(self) -> Dict[DryingPhase, StepDownProfile]:
        """Create research-based step-down profiles for optimal cannabis drying"""
        return {
            DryingPhase.INITIAL_MOISTURE_REMOVAL: StepDownProfile(
                phase=DryingPhase.INITIAL_MOISTURE_REMOVAL,
                duration_hours=48,
                temp_range_f=(68.0, 68.0),        # Constant 68°F
                dew_point_range_f=(54.0, 56.0),   # 54-56°F dew point
                rh_range_percent=(60.0, 65.0),    # 60-65% RH
                vpd_target_kpa=(0.7, 0.8),       # Gentle start
                target_water_activity=(0.75, 0.85), # Initial high aW
                notes="Higher RH prevents case hardening, preserves >90% monoterpenes"
            ),
            
            DryingPhase.MID_DRYING: StepDownProfile(
                phase=DryingPhase.MID_DRYING,
                duration_hours=72,
                temp_range_f=(66.0, 68.0),        # Step down temp slightly
                dew_point_range_f=(52.0, 54.0),   # Lower dew point
                rh_range_percent=(55.0, 60.0),    # 55-60% RH
                vpd_target_kpa=(0.8, 0.9),       # Increase drying power
                target_water_activity=(0.65, 0.75), # Target aW reduction
                notes="Controlled moisture pull, preserves sesquiterpenes and cannabinoids"
            ),
            
            DryingPhase.FINAL_DRY: StepDownProfile(
                phase=DryingPhase.FINAL_DRY,
                duration_hours=48,
                temp_range_f=(65.0, 66.0),        # Cooler for terpenes
                dew_point_range_f=(50.0, 52.0),   # Lower dew point
                rh_range_percent=(50.0, 55.0),    # 50-55% RH
                vpd_target_kpa=(0.9, 1.0),       # Maximum safe drying
                target_water_activity=(0.60, 0.65), # Near target aW
                notes="Final moisture removal, >80% terpene retention, prevent over-drying"
            ),
            
            DryingPhase.STABILIZATION_CURE: StepDownProfile(
                phase=DryingPhase.STABILIZATION_CURE,
                duration_hours=60,  # 48-72 hours flexible
                temp_range_f=(63.0, 65.0),        # Coolest for curing
                dew_point_range_f=(50.0, 52.0),   # Stable dew point
                rh_range_percent=(55.0, 60.0),    # Stabilization RH
                vpd_target_kpa=(0.7, 0.8),       # Gentle cure
                target_water_activity=(0.60, 0.62), # Target aW achieved
                notes="Stabilization cure, equalize moisture, preserve potency"
            )
        }
    
    def celsius_to_fahrenheit(self, celsius: float) -> float:
        """Convert Celsius to Fahrenheit"""
        return (celsius * 9/5) + 32
    
    def fahrenheit_to_celsius(self, fahrenheit: float) -> float:
        """Convert Fahrenheit to Celsius"""
        return (fahrenheit - 32) * 5/9
    
    def saturation_vapor_pressure_kpa(self, temp_celsius: float) -> float:
        """
        Calculate saturation vapor pressure using Magnus-Tetens formula.
        High precision for research-grade control.
        """
        # Magnus-Tetens coefficients for maximum accuracy
        a = 17.27
        b = 237.7
        
        exponent = (a * temp_celsius) / (b + temp_celsius)
        svp_kpa = 0.6108 * math.exp(exponent)
        
        return svp_kpa
    
    def calculate_water_activity_precise(self, relative_humidity: float, temperature_f: float) -> float:
        """
        Calculate water activity using equilibrium relative humidity (ERH) models.
        Based on cannabis research: aW ≈ RH/100 at equilibrium with correction factors.
        
        Args:
            relative_humidity: RH as percentage (0-100)
            temperature_f: Temperature in Fahrenheit
            
        Returns:
            Estimated water activity (0.0 - 1.0)
        """
        rh_decimal = relative_humidity / 100
        
        # Cannabis-specific correction factors based on research
        # Temperature correction (slightly lower aW at higher temps)
        temp_correction = 1.0 - ((temperature_f - 65) * 0.002)
        
        # Cannabis matrix correction (plant material holds slightly less water than pure equilibrium)
        matrix_correction = 0.95
        
        estimated_aw = rh_decimal * temp_correction * matrix_correction
        
        # Clamp to realistic range
        return max(0.3, min(1.0, estimated_aw))
    
    def calculate_vpd_from_conditions(self, air_temp_f: float, relative_humidity: float) -> VPDReading:
        """
        Calculate comprehensive VPD reading from temperature and humidity.
        Includes precise water activity estimation.
        """
        # Convert to Celsius for calculations
        air_temp_c = self.fahrenheit_to_celsius(air_temp_f)
        
        # Calculate saturation vapor pressure
        svp_kpa = self.saturation_vapor_pressure_kpa(air_temp_c)
        
        # Calculate actual vapor pressure from RH
        avp_kpa = svp_kpa * (relative_humidity / 100)
        
        # Calculate VPD
        vpd_kpa = svp_kpa - avp_kpa
        
        # Calculate dew point (reverse Magnus-Tetens)
        if avp_kpa > 0:
            ln_ratio = math.log(avp_kpa / 0.6108)
            dew_point_c = (237.7 * ln_ratio) / (17.27 - ln_ratio)
            dew_point_f = self.celsius_to_fahrenheit(dew_point_c)
        else:
            dew_point_f = air_temp_f
        
        # Calculate precise water activity
        water_activity = self.calculate_water_activity_precise(relative_humidity, air_temp_f)
        
        return VPDReading(
            vpd_kpa=vpd_kpa,
            air_temp_f=air_temp_f,
            dew_point_f=dew_point_f,
            relative_humidity=relative_humidity,
            saturation_pressure_kpa=svp_kpa,
            actual_pressure_kpa=avp_kpa,
            estimated_water_activity=water_activity,
            timestamp=datetime.now()
        )
    
    def get_current_phase_from_elapsed_time(self, start_time: datetime) -> DryingPhase:
        """
        Determine current drying phase based on elapsed time since start.
        
        Args:
            start_time: When the drying process started
            
        Returns:
            Current DryingPhase
        """
        elapsed = datetime.now() - start_time
        elapsed_hours = elapsed.total_seconds() / 3600
        
        cumulative_hours = 0
        for phase in [DryingPhase.INITIAL_MOISTURE_REMOVAL, DryingPhase.MID_DRYING, 
                     DryingPhase.FINAL_DRY, DryingPhase.STABILIZATION_CURE]:
            
            profile = self.step_profiles[phase]
            cumulative_hours += profile.duration_hours
            
            if elapsed_hours <= cumulative_hours:
                return phase
        
        # Process complete
        return DryingPhase.STABILIZATION_CURE
    
    def get_phase_target_conditions(self, phase: DryingPhase, 
                                   phase_progress: float = 0.5) -> Tuple[float, float, float]:
        """
        Get target conditions for a specific phase with linear interpolation.
        
        Args:
            phase: Current drying phase
            phase_progress: Progress within phase (0.0 to 1.0)
            
        Returns:
            Tuple of (target_temp_f, target_dew_point_f, target_rh_percent)
        """
        if phase not in self.step_profiles:
            phase = DryingPhase.INITIAL_MOISTURE_REMOVAL
        
        profile = self.step_profiles[phase]
        
        # Linear interpolation within ranges based on phase progress
        temp_min, temp_max = profile.temp_range_f
        dew_min, dew_max = profile.dew_point_range_f
        rh_min, rh_max = profile.rh_range_percent
        
        # For most phases, step down over time (start high, end low)
        if phase in [DryingPhase.INITIAL_MOISTURE_REMOVAL, DryingPhase.MID_DRYING]:
            # Step down: start at max, end at min
            target_temp = temp_max - (phase_progress * (temp_max - temp_min))
            target_dew = dew_max - (phase_progress * (dew_max - dew_min))
            target_rh = rh_max - (phase_progress * (rh_max - rh_min))
        else:
            # Stable or slight variation
            target_temp = temp_min + (phase_progress * (temp_max - temp_min))
            target_dew = dew_min + (phase_progress * (dew_max - dew_min))
            target_rh = rh_min + (phase_progress * (rh_max - rh_min))
        
        return target_temp, target_dew, target_rh
    
    def calculate_phase_progress(self, start_time: datetime, phase: DryingPhase) -> float:
        """Calculate progress within current phase (0.0 to 1.0)"""
        elapsed = datetime.now() - start_time
        elapsed_hours = elapsed.total_seconds() / 3600
        
        # Calculate cumulative hours to start of current phase
        cumulative_hours = 0
        phases_order = [DryingPhase.INITIAL_MOISTURE_REMOVAL, DryingPhase.MID_DRYING, 
                       DryingPhase.FINAL_DRY, DryingPhase.STABILIZATION_CURE]
        
        for p in phases_order:
            if p == phase:
                break
            cumulative_hours += self.step_profiles[p].duration_hours
        
        # Calculate progress within current phase
        phase_elapsed = elapsed_hours - cumulative_hours
        phase_duration = self.step_profiles[phase].duration_hours
        
        return max(0.0, min(1.0, phase_elapsed / phase_duration))
    
    def get_step_down_recommendations(self, vpd_reading: VPDReading, 
                                    start_time: datetime) -> Dict:
        """
        Get step-down control recommendations based on current phase and progress.
        
        Args:
            vpd_reading: Current environmental reading
            start_time: When drying process started
            
        Returns:
            Dictionary with detailed step-down recommendations
        """
        current_phase = self.get_current_phase_from_elapsed_time(start_time)
        phase_progress = self.calculate_phase_progress(start_time, current_phase)
        
        # Get target conditions for current phase and progress
        target_temp, target_dew, target_rh = self.get_phase_target_conditions(
            current_phase, phase_progress
        )
        
        # Get profile for context
        profile = self.step_profiles[current_phase]
        
        # Calculate deviations
        temp_deviation = vpd_reading.air_temp_f - target_temp
        dew_deviation = vpd_reading.dew_point_f - target_dew
        rh_deviation = vpd_reading.relative_humidity - target_rh
        vpd_in_range = (profile.vpd_target_kpa[0] <= vpd_reading.vpd_kpa <= 
                       profile.vpd_target_kpa[1])
        aw_in_range = (profile.target_water_activity[0] <= vpd_reading.estimated_water_activity <= 
                      profile.target_water_activity[1])
        
        recommendations = {
            "phase": current_phase.value,
            "phase_progress_percent": phase_progress * 100,
            "duration_remaining_hours": profile.duration_hours * (1 - phase_progress),
            "current_conditions": {
                "temperature_f": vpd_reading.air_temp_f,
                "dew_point_f": vpd_reading.dew_point_f,
                "relative_humidity": vpd_reading.relative_humidity,
                "vpd_kpa": vpd_reading.vpd_kpa,
                "water_activity": vpd_reading.estimated_water_activity
            },
            "target_conditions": {
                "temperature_f": target_temp,
                "dew_point_f": target_dew,
                "relative_humidity": target_rh,
                "vpd_range_kpa": profile.vpd_target_kpa,
                "water_activity_range": profile.target_water_activity
            },
            "deviations": {
                "temperature_f": temp_deviation,
                "dew_point_f": dew_deviation,
                "relative_humidity": rh_deviation
            },
            "status_flags": {
                "vpd_in_range": vpd_in_range,
                "water_activity_in_range": aw_in_range,
                "temperature_in_range": abs(temp_deviation) <= 1.0,
                "humidity_in_range": abs(rh_deviation) <= 2.0
            },
            "equipment_actions": [],
            "phase_notes": profile.notes
        }
        
        # Generate equipment recommendations
        if abs(temp_deviation) > 0.5:
            if temp_deviation > 0:
                recommendations["equipment_actions"].append({
                    "equipment": "mini_split",
                    "action": "decrease_temperature",
                    "amount": min(2.0, abs(temp_deviation)),
                    "priority": "high"
                })
            else:
                recommendations["equipment_actions"].append({
                    "equipment": "mini_split", 
                    "action": "increase_temperature",
                    "amount": min(2.0, abs(temp_deviation)),
                    "priority": "high"
                })
        
        if abs(rh_deviation) > 2.0:
            if rh_deviation > 0:  # Too humid
                recommendations["equipment_actions"].append({
                    "equipment": "dehumidifier",
                    "action": "increase_power",
                    "amount": min(20, abs(rh_deviation) * 2),
                    "priority": "medium"
                })
            else:  # Too dry
                recommendations["equipment_actions"].append({
                    "equipment": "humidifier",
                    "action": "increase_power", 
                    "amount": min(15, abs(rh_deviation) * 2),
                    "priority": "medium"
                })
        
        return recommendations
    
    def get_all_phase_profiles(self) -> Dict[DryingPhase, StepDownProfile]:
        """Get all step-down profiles for reference"""
        return self.step_profiles.copy()
    
    def estimate_completion_time(self, start_time: datetime) -> datetime:
        """Estimate when the entire drying process will complete"""
        total_hours = sum(profile.duration_hours for profile in self.step_profiles.values())
        return start_time + timedelta(hours=total_hours)

# Example usage and testing
if __name__ == "__main__":
    # Initialize research-optimized calculator
    calc = ResearchOptimizedVPD()
    
    print("=== Research-Optimized Cannabis VPD Calculator ===\n")
    
    # Simulate start time (2 days ago for testing)
    start_time = datetime.now() - timedelta(days=2, hours=4)
    
    print("📊 Step-Down Profile Overview:")
    for phase, profile in calc.get_all_phase_profiles().items():
        print(f"\n{phase.value.upper()}:")
        print(f"  Duration: {profile.duration_hours} hours")
        print(f"  Temperature: {profile.temp_range_f[0]}-{profile.temp_range_f[1]}°F")
        print(f"  Dew Point: {profile.dew_point_range_f[0]}-{profile.dew_point_range_f[1]}°F")
        print(f"  RH: {profile.rh_range_percent[0]}-{profile.rh_range_percent[1]}%")
        print(f"  VPD Target: {profile.vpd_target_kpa[0]}-{profile.vpd_target_kpa[1]} kPa")
        print(f"  Water Activity: {profile.target_water_activity[0]}-{profile.target_water_activity[1]}")
    
    print(f"\n🎯 Current Phase Analysis:")
    current_phase = calc.get_current_phase_from_elapsed_time(start_time)
    phase_progress = calc.calculate_phase_progress(start_time, current_phase)
    print(f"Current Phase: {current_phase.value}")
    print(f"Phase Progress: {phase_progress*100:.1f}%")
    
    # Get current target conditions
    target_temp, target_dew, target_rh = calc.get_phase_target_conditions(current_phase, phase_progress)
    print(f"Current Targets: {target_temp:.1f}°F, {target_dew:.1f}°F dew, {target_rh:.1f}% RH")
    
    # Test with simulated sensor data
    print(f"\n🌡️  Testing with Simulated Conditions:")
    test_reading = calc.calculate_vpd_from_conditions(67.5, 58.2)
    print(f"Test Conditions: {test_reading.air_temp_f}°F, {test_reading.relative_humidity}% RH")
    print(f"Calculated VPD: {test_reading.vpd_kpa:.3f} kPa")
    print(f"Dew Point: {test_reading.dew_point_f:.1f}°F")
    print(f"Water Activity: {test_reading.estimated_water_activity:.3f}")
    
    # Get step-down recommendations
    print(f"\n⚙️  Step-Down Recommendations:")
    recommendations = calc.get_step_down_recommendations(test_reading, start_time)
    print(f"Status: VPD in range = {recommendations['status_flags']['vpd_in_range']}")
    print(f"Water Activity in range = {recommendations['status_flags']['water_activity_in_range']}")
    print(f"Equipment Actions: {len(recommendations['equipment_actions'])}")
    for action in recommendations['equipment_actions']:
        print(f"  - {action['equipment']}: {action['action']} ({action['priority']} priority)")
    
    # Completion estimate
    completion = calc.estimate_completion_time(start_time)
    print(f"\n⏰ Estimated Completion: {completion.strftime('%Y-%m-%d %H:%M')}")