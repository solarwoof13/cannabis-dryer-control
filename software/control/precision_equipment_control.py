#!/usr/bin/env python3
"""
Precision Equipment Control Logic for Cannabis Dryer
Implements your exact control specifications
"""

import time
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

class ControlMode(Enum):
    """Control modes for each equipment"""
    AUTO = "AUTO"
    ON = "ON"
    OFF = "OFF"

class PrecisionEquipmentController:
    """
    Equipment control following your exact specifications:
    - Dehumidifier primary control (always on unless humidifying)
    - Humidifier modulation based on VPD/Dew Point
    - Fans always on during operation
    - Storage mode with cycling
    """
    
    def __init__(self, vpd_controller):
        self.vpd_controller = vpd_controller
        
        # Initialize GPIO FIRST
        self.gpio_initialized = False
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # GPIO pin mapping
            self.gpio_pins = {
                'dehum': 17,
                'hum_solenoid': 27,
                'hum_fan': 25,
                'erv': 22,
                'supply_fan': 23,
                'return_fan': 24
            }
            
            # Setup all pins as outputs
            for equipment, pin in self.gpio_pins.items():
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.HIGH)  # Start OFF (HIGH = OFF for active LOW relays)
                logger.info(f"GPIO {pin} initialized for {equipment} (OFF)")
            
            self.gpio_initialized = True
            logger.info("GPIO initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            self.gpio_pins = {}
        
        # Control modes for each equipment (AUTO, ON, OFF)
        self.control_modes = {
            'dehum': ControlMode.AUTO,
            'hum_solenoid': ControlMode.AUTO,
            'hum_fan': ControlMode.AUTO,
            'erv': ControlMode.AUTO,
            'supply_fan': ControlMode.AUTO,
            'return_fan': ControlMode.AUTO,
            'mini_split': ControlMode.AUTO
        }
        
        # Actual states (what the equipment is doing right now)
        self.actual_states = {
            'dehum': 'ON',
            'hum_solenoid': 'OFF',
            'hum_fan': 'ON',
            'erv': 'ON',
            'supply_fan': 'ON',
            'return_fan': 'ON',
            'mini_split': 'ON'
        }
        
        # Timing controls
        self.dehum_off_start = None  # Track when dehum was turned off
        self.dehum_min_off_time = 300  # 5 minutes minimum off time
        
        self.hum_last_toggle = time.time()
        self.hum_cycle_time = 60  # 1 minute on/off in storage
        self.hum_is_on_cycle = True  # Track storage mode cycling
        
        # Modulation parameters for humidifier
        self.hum_modulation_rate = 0.0  # 0-100% duty cycle
        self.hum_modulation_period = 30  # seconds per modulation cycle
        self.hum_last_modulation = time.time()
        
        # VPD and Dew Point deadbands
        self.vpd_deadband = 0.05  # kPa
        self.dew_point_deadband = 0.5  # °F

        # Apply initial states to GPIO hardware
        if self.gpio_initialized:
            for equipment, state in self.actual_states.items():
                if equipment in self.gpio_pins:
                    pin = self.gpio_pins[equipment]
                    gpio_state = GPIO.LOW if state == 'ON' else GPIO.HIGH
                    GPIO.output(pin, gpio_state)
                    logger.info(f"Initial state applied: {equipment} = {state} (GPIO {pin} = {'LOW' if state == 'ON' else 'HIGH'})")

    # ADD THESE METHODS TO: software/control/precision_equipment_control.py
    # Add after the __init__ method and before set_control_mode

    def emergency_stop(self):
        """Emergency stop - immediately turn OFF all equipment"""
        logger.critical("🔴 EMERGENCY STOP ACTIVATED - Turning OFF all equipment")
        
        if not self.gpio_initialized:
            logger.error("GPIO not initialized - cannot execute emergency stop")
            return False
        
        try:
            import RPi.GPIO as GPIO
            
            # Turn off ALL GPIO pins immediately
            for equipment, pin in self.gpio_pins.items():
                GPIO.output(pin, GPIO.HIGH)  # HIGH = OFF (Active LOW relays)
                self.actual_states[equipment] = 'OFF'
                logger.info(f"EMERGENCY STOP: {equipment} = OFF (GPIO {pin} = HIGH)")
            
            # Also update VPD controller states
            from software.control.vpd_controller import EquipmentState
            for equipment in self.actual_states.keys():
                if hasattr(self.vpd_controller, 'equipment_states'):
                    self.vpd_controller.equipment_states[equipment] = EquipmentState.OFF
            
            logger.critical("✓ Emergency stop complete - all equipment OFF")
            return True
            
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
            return False

    def _apply_state(self, equipment: str, state: str):
        """Apply state to actual GPIO/hardware"""
        if not self.gpio_initialized:
            logger.warning(f"GPIO not initialized - cannot apply {equipment} = {state}")
            return False
        
        if equipment not in self.gpio_pins:
            logger.warning(f"Equipment {equipment} not in GPIO pins")
            return False
        
        try:
            import RPi.GPIO as GPIO
            
            pin = self.gpio_pins[equipment]
            
            # Active LOW logic: LOW = ON, HIGH = OFF
            if state == 'ON':
                GPIO.output(pin, GPIO.LOW)
                logger.info(f"{equipment} = ON (GPIO {pin} = LOW)")
            else:  # OFF or any other state
                GPIO.output(pin, GPIO.HIGH)
                logger.info(f"{equipment} = OFF (GPIO {pin} = HIGH)")
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying state for {equipment}: {e}")
            return False

    # OPTIONAL: Add a cleanup method for safe shutdown
    def cleanup(self):
        """Clean up GPIO on shutdown - turn everything OFF"""
        logger.info("Cleaning up GPIO - turning all equipment OFF")
        
        if not self.gpio_initialized:
            return
        
        try:
            import RPi.GPIO as GPIO
            
            # Turn off all relays
            for pin in self.gpio_pins.values():
                GPIO.output(pin, GPIO.HIGH)  # HIGH = OFF
            
            # Cleanup GPIO
            GPIO.cleanup()
            logger.info("GPIO cleanup complete")
            
        except Exception as e:
            logger.error(f"Error during GPIO cleanup: {e}")

    def set_control_mode(self, equipment: str, mode: str):
        """Set control mode for equipment (AUTO/ON/OFF)"""
        if equipment in self.control_modes:
            self.control_modes[equipment] = ControlMode(mode)
            logger.info(f"{equipment} set to {mode} mode")
            
            # If manual ON/OFF, immediately apply
            if mode == "ON":
                self.actual_states[equipment] = 'ON'
                self._apply_state(equipment, 'ON')
            elif mode == "OFF":
                self.actual_states[equipment] = 'OFF'
                self._apply_state(equipment, 'OFF')

    def calculate_automatic_control(self, current_vpd: float, target_vpd_min: float, 
                                    target_vpd_max: float, current_dew_point: float,
                                    target_dew_point: float, current_humidity: float,
                                    phase: str) -> Dict[str, str]:
            """
            Calculate equipment states based on VPD controller setpoints and current conditions.
            Implements your research-optimized control logic.
            
            Args:
                current_vpd: Current VPD in kPa
                target_vpd_min: Minimum target VPD from phase setpoint
                target_vpd_max: Maximum target VPD from phase setpoint
                current_dew_point: Current dew point in °F
                target_dew_point: Target dew point from phase setpoint
                current_humidity: Current relative humidity %
                phase: Current drying phase (dry_initial, dry_mid, dry_final, cure, storage)
                
            Returns:
                Dictionary of equipment names to states ('ON' or 'OFF')
            """
            import time
            
            logger.info(f"Auto control: VPD={current_vpd:.2f} (target {target_vpd_min:.2f}-{target_vpd_max:.2f}), "
                        f"DP={current_dew_point:.1f}°F (target {target_dew_point:.1f}°F), "
                        f"RH={current_humidity:.1f}%, Phase={phase}")
            
            new_states = {}
            
            # === STORAGE MODE (HOLD) ===
            if phase == 'storage':
                logger.info("STORAGE MODE: 1-minute on/off cycling for humidifier")
                # Storage mode: minimal conditioning, just maintain
                new_states['dehum'] = 'OFF'
                new_states['hum_solenoid'] = self._get_storage_hum_state()  # 1 min on/off cycle
                new_states['hum_fan'] = 'ON' if new_states['hum_solenoid'] == 'ON' else 'OFF'
                new_states['erv'] = 'ON'  # Minimal fresh air
                new_states['supply_fan'] = 'ON'
                new_states['return_fan'] = 'ON'
                new_states['mini_split'] = 'ON'  # Temperature control
                return new_states
            
            # === ACTIVE DRYING/CURING PHASES ===
            
            # Calculate VPD target midpoint and error
            vpd_target = (target_vpd_min + target_vpd_max) / 2
            vpd_error = current_vpd - vpd_target
            
            # Calculate dew point error
            dew_error = current_dew_point - target_dew_point
            
            logger.info(f"Control errors: VPD_error={vpd_error:.3f} kPa, DP_error={dew_error:.2f}°F")
            
            # === PRIMARY CONTROL: VPD-BASED ===
            
            # VPD too HIGH (too dry) - Need to add moisture
            if current_vpd > (target_vpd_max + self.vpd_deadband):
                logger.info(f"VPD HIGH ({current_vpd:.2f} > {target_vpd_max:.2f}) - HUMIDIFYING")
                
                # Turn OFF dehumidifier (with minimum off time)
                current_time = time.time()
                if self.dehum_off_start is None:
                    self.dehum_off_start = current_time
                    new_states['dehum'] = 'OFF'
                    logger.info("Dehumidifier turned OFF - starting minimum off timer")
                elif (current_time - self.dehum_off_start) < self.dehum_min_off_time:
                    new_states['dehum'] = 'OFF'
                    remaining = self.dehum_min_off_time - (current_time - self.dehum_off_start)
                    logger.info(f"Dehumidifier OFF - {remaining:.0f}s remaining in minimum off time")
                else:
                    # Minimum off time elapsed - can turn back on if needed
                    if current_vpd < target_vpd_max:
                        new_states['dehum'] = 'ON'
                        self.dehum_off_start = None
                        logger.info("Minimum off time complete - dehumidifier can turn ON if needed")
                    else:
                        new_states['dehum'] = 'OFF'
                
                # Calculate humidifier modulation based on VPD error
                vpd_overshoot = current_vpd - target_vpd_max
                # Scale modulation: 0.1 kPa error = 50% duty, 0.2 kPa = 100%
                self.hum_modulation_rate = min(100.0, (vpd_overshoot / 0.2) * 100.0)
                modulated_state = self._apply_modulation()
                
                new_states['hum_solenoid'] = modulated_state
                new_states['hum_fan'] = 'ON'  # Fan always ON when humidifying
                
                logger.info(f"Humidifier modulation: {self.hum_modulation_rate:.1f}% duty cycle, state={modulated_state}")
            
            # VPD too LOW (too wet) - Need to remove moisture  
            elif current_vpd < (target_vpd_min - self.vpd_deadband):
                logger.info(f"VPD LOW ({current_vpd:.2f} < {target_vpd_min:.2f}) - DEHUMIDIFYING")
                
                # Dehumidifier ON
                new_states['dehum'] = 'ON'
                self.dehum_off_start = None  # Reset timer
                
                # Humidifier OFF
                new_states['hum_solenoid'] = 'OFF'
                new_states['hum_fan'] = 'OFF'
                self.hum_modulation_rate = 0.0
                
                logger.info("Dehumidifier ON, Humidifier OFF")
            
            # VPD in range - MAINTAIN
            else:
                logger.info(f"VPD OK ({current_vpd:.2f} in range {target_vpd_min:.2f}-{target_vpd_max:.2f}) - MAINTAINING")
                
                # Fine-tune based on dew point to stay centered in range
                if dew_error > self.dew_point_deadband:
                    # Dew point too high - light dehumidification
                    new_states['dehum'] = 'ON'
                    new_states['hum_solenoid'] = 'OFF'
                    new_states['hum_fan'] = 'OFF'
                    logger.info(f"Dew point high ({current_dew_point:.1f}°F > {target_dew_point:.1f}°F) - light dehum")
                
                elif dew_error < -self.dew_point_deadband:
                    # Dew point too low - light humidification
                    new_states['dehum'] = 'OFF'
                    self.hum_modulation_rate = 25.0  # Low duty cycle for maintenance
                    new_states['hum_solenoid'] = self._apply_modulation()
                    new_states['hum_fan'] = 'ON' if new_states['hum_solenoid'] == 'ON' else 'OFF'
                    logger.info(f"Dew point low ({current_dew_point:.1f}°F < {target_dew_point:.1f}°F) - light humidification")
                
                else:
                    # Perfect conditions - minimal intervention
                    new_states['dehum'] = 'ON'  # Keep on for stability (your primary control)
                    new_states['hum_solenoid'] = 'OFF'
                    new_states['hum_fan'] = 'OFF'
                    self.hum_modulation_rate = 0.0
                    logger.info("Conditions optimal - minimal intervention")
            
            # === FANS: ALWAYS ON DURING DRYING/CURING ===
            new_states['supply_fan'] = 'ON'
            new_states['return_fan'] = 'ON'
            new_states['erv'] = 'ON'
            
            # === MINI-SPLIT: ALWAYS ON (temperature control via IR - not implemented yet) ===
            new_states['mini_split'] = 'ON'
            
            logger.info(f"Final equipment states: {new_states}")
            
            return new_states

    def _apply_modulation(self) -> str:
        """Apply PWM-style modulation to humidifier"""
        current_time = time.time()
        cycle_position = (current_time - self.hum_last_modulation) / self.hum_modulation_period
        
        if cycle_position > 1.0:
            # Start new cycle
            self.hum_last_modulation = current_time
            cycle_position = 0
        
        # Determine if we should be ON based on duty cycle
        duty_fraction = self.hum_modulation_rate / 100.0
        return 'ON' if cycle_position < duty_fraction else 'OFF'

    def _get_storage_hum_state(self) -> str:
        """Get humidifier state for storage mode (1 min on/off cycling)"""
        current_time = time.time()
        
        if current_time - self.hum_last_toggle > self.hum_cycle_time:
            self.hum_is_on_cycle = not self.hum_is_on_cycle
            self.hum_last_toggle = current_time
        
        return 'ON' if self.hum_is_on_cycle else 'OFF'

    def _apply_state(self, equipment: str, state: str):
        """Apply state to actual GPIO/hardware"""
        if hasattr(self.vpd_controller, 'gpio_controller'):
            self.vpd_controller.gpio_controller.set_device(equipment, state)

    def update_equipment(self):
        """Main update function called from control loop"""
        
        # CRITICAL: Check if process is active before controlling equipment
        if not hasattr(self.vpd_controller, 'process_active'):
            logger.warning("VPD controller has no process_active attribute")
            return
        
        if not self.vpd_controller.process_active:
            logger.debug("Process NOT active - skipping equipment control")
            # Equipment stays in current state (should be OFF after emergency stop)
            return
        
        logger.info(f"Process ACTIVE (phase: {self.vpd_controller.current_phase.value}) - Running equipment control")
        
        # Get current conditions from VPD controller
        try:
            avg_temp, avg_humidity, avg_dew_point, avg_vpd = \
                self.vpd_controller.get_dry_room_conditions()
            logger.info(f"Current conditions: T={avg_temp:.1f}°F, RH={avg_humidity:.1f}%, DP={avg_dew_point:.1f}°F, VPD={avg_vpd:.2f} kPa")
        except Exception as e:
            logger.error(f"Failed to get sensor data: {e}")
            logger.error("Cannot control equipment without sensor data - maintaining current state")
            return
        
        # Get current phase and target setpoint
        try:
            phase = self.vpd_controller.current_phase.value
            setpoint = self.vpd_controller.phase_setpoints[self.vpd_controller.current_phase]
            logger.info(f"Phase: {phase}, Target VPD: {setpoint.vpd_min:.2f}-{setpoint.vpd_max:.2f} kPa, Target DP: {setpoint.dew_point_target:.1f}°F")
        except Exception as e:
            logger.error(f"Failed to get phase setpoint: {e}")
            return
        
        # Calculate what equipment states should be based on automatic control
        auto_states = self.calculate_automatic_control(
            avg_vpd, setpoint.vpd_min, setpoint.vpd_max,
            avg_dew_point, setpoint.dew_point_target,
            avg_humidity, phase
        )
        
        logger.info(f"Calculated auto states: {auto_states}")
        
        # Apply states based on control mode (AUTO, ON, OFF)
        for equipment, mode in self.control_modes.items():
            if mode == ControlMode.AUTO:
                # Use automatic control
                if equipment in auto_states:
                    new_state = auto_states[equipment]
                    if self.actual_states[equipment] != new_state:
                        logger.info(f"Changing {equipment}: {self.actual_states[equipment]} → {new_state} (AUTO mode)")
                        self.actual_states[equipment] = new_state
                        self._apply_state(equipment, new_state)
                    else:
                        logger.debug(f"{equipment}: {new_state} (no change, AUTO mode)")
            
            elif mode == ControlMode.ON:
                # Manual ON override
                if self.actual_states[equipment] != 'ON':
                    logger.info(f"Forcing {equipment} ON (manual override)")
                    self.actual_states[equipment] = 'ON'
                    self._apply_state(equipment, 'ON')
            
            elif mode == ControlMode.OFF:
                # Manual OFF override
                if self.actual_states[equipment] != 'OFF':
                    logger.info(f"Forcing {equipment} OFF (manual override)")
                    self.actual_states[equipment] = 'OFF'
                    self._apply_state(equipment, 'OFF')
        
        # Update VPD controller equipment states for display/status
        from software.control.vpd_controller import EquipmentState
        for equipment, state in self.actual_states.items():
            self.vpd_controller.equipment_states[equipment] = \
                EquipmentState.ON if state == 'ON' else EquipmentState.OFF
        
        logger.info(f"✅ Equipment update complete. Final states: {self.actual_states}")

    def get_status(self) -> Dict:
        """Get current equipment status including modes and states"""
        return {
            'modes': {k: v.value for k, v in self.control_modes.items()},
            'states': self.actual_states.copy(),
            'modulation': {
                'humidifier_duty_cycle': self.hum_modulation_rate,
                'dehum_off_timer': self.dehum_off_start is not None
            }
        }