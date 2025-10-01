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
        Calculate equipment states based on your exact logic
        """
        new_states = {}
        
        # Check if we're in storage/complete phase
        is_storage = phase in ['storage', 'complete']
        
        # FANS - Always ON during dry/cure, controlled in storage
        if not is_storage:
            # During drying and curing - fans always ON
            new_states['supply_fan'] = 'ON'
            new_states['return_fan'] = 'ON'
            new_states['erv'] = 'ON'
            new_states['hum_fan'] = 'ON'
        else:
            # Storage mode - only supply and return fans ON
            new_states['supply_fan'] = 'ON'
            new_states['return_fan'] = 'ON'
            new_states['erv'] = 'OFF'
            new_states['hum_fan'] = 'OFF'  # Only on when humidifying
        
        # Calculate VPD and Dew Point errors
        vpd_error = current_vpd - ((target_vpd_min + target_vpd_max) / 2)
        dew_point_error = current_dew_point - target_dew_point
        
        # DEHUMIDIFIER CONTROL (Your spec: always ON unless actively humidifying)
        if not is_storage:
            # Normal operation - dehum is default ON
            if vpd_error > self.vpd_deadband or dew_point_error < -self.dew_point_deadband:
                # VPD too high or dew point too low - need humidification
                # Check if we've been trying to humidify for 5 minutes
                if self.dehum_off_start is None:
                    self.dehum_off_start = time.time()
                    new_states['dehum'] = 'ON'  # Keep on initially
                elif time.time() - self.dehum_off_start > self.dehum_min_off_time:
                    # Been trying for 5 minutes - turn off dehum to allow humidification
                    new_states['dehum'] = 'OFF'
                    new_states['hum_solenoid'] = 'ON'
                    logger.info("Dehumidifier OFF after 5 min - allowing humidification")
                else:
                    # Still waiting the 5 minutes
                    new_states['dehum'] = 'ON'
                    new_states['hum_solenoid'] = 'OFF'
            else:
                # VPD and dew point OK - dehum stays ON as default
                new_states['dehum'] = 'ON'
                new_states['hum_solenoid'] = 'OFF'
                self.dehum_off_start = None  # Reset timer
        else:
            # Storage mode - use as needed
            if current_humidity > 65:
                new_states['dehum'] = 'ON'
                new_states['hum_solenoid'] = 'OFF'
                new_states['hum_fan'] = 'OFF'
            elif current_humidity < 58:
                new_states['dehum'] = 'OFF'
                # Cycle humidifier 1 min on/off
                new_states['hum_fan'] = 'ON'
                new_states['hum_solenoid'] = self._get_storage_hum_state()
            else:
                new_states['dehum'] = 'OFF'
                new_states['hum_solenoid'] = 'OFF'
                new_states['hum_fan'] = 'OFF'
        
        # HUMIDIFIER MODULATION (when approaching target)
        if not is_storage and new_states.get('hum_solenoid') == 'ON':
            # Calculate modulation rate based on how close we are
            if vpd_error > 0.2:  # Far from target
                self.hum_modulation_rate = 100  # Full on
            elif vpd_error > 0.1:
                self.hum_modulation_rate = 70
            elif vpd_error > self.vpd_deadband:
                self.hum_modulation_rate = 40
            else:
                self.hum_modulation_rate = 20  # Gentle approach
            
            # Apply modulation
            modulated_state = self._apply_modulation()
            new_states['hum_solenoid'] = modulated_state
        
        # Mini-split always ON (temperature controlled via IR)
        new_states['mini_split'] = 'ON'
        
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
        # Get current conditions
        try:
            avg_temp, avg_humidity, avg_dew_point, avg_vpd = \
                self.vpd_controller.get_dry_room_conditions()
        except:
            logger.error("No sensor data available")
            return
        
        # Get current phase and targets
        phase = self.vpd_controller.current_phase.value
        setpoint = self.vpd_controller.phase_setpoints[self.vpd_controller.current_phase]
        
        # Calculate automatic control for AUTO mode equipment
        auto_states = self.calculate_automatic_control(
            avg_vpd, setpoint.vpd_min, setpoint.vpd_max,
            avg_dew_point, setpoint.dew_point_target,
            avg_humidity, phase
        )
        
        # Apply states based on control mode
        for equipment, mode in self.control_modes.items():
            if mode == ControlMode.AUTO:
                # Use automatic control
                if equipment in auto_states:
                    new_state = auto_states[equipment]
                    if self.actual_states[equipment] != new_state:
                        self.actual_states[equipment] = new_state
                        self._apply_state(equipment, new_state)
                        logger.info(f"{equipment}: {new_state} (AUTO mode)")
            elif mode == ControlMode.ON:
                # Manual ON
                if self.actual_states[equipment] != 'ON':
                    self.actual_states[equipment] = 'ON'
                    self._apply_state(equipment, 'ON')
            elif mode == ControlMode.OFF:
                # Manual OFF
                if self.actual_states[equipment] != 'OFF':
                    self.actual_states[equipment] = 'OFF'
                    self._apply_state(equipment, 'OFF')
        
        # Update VPD controller equipment states for display
        from software.control.vpd_controller import EquipmentState
        for equipment, state in self.actual_states.items():
            self.vpd_controller.equipment_states[equipment] = \
                EquipmentState.ON if state == 'ON' else EquipmentState.OFF

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