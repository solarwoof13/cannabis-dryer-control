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

# IMPORT GPIO AT MODULE LEVEL - CRITICAL!
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("WARNING: RPi.GPIO not available - running in simulation mode")

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
            if not GPIO_AVAILABLE:
                raise ImportError("GPIO not available")
            
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
        # Track if we need to force-apply states after emergency stop recovery
        self._process_was_inactive = True  # Start as True to force apply on first run
        self._first_active_cycle = True

        # Initialize hardware sync tracking
        self._last_hardware_sync = 0
        self._hardware_sync_interval = 300  # Sync every 5 minutes

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
        
    def force_apply_states(self):
        """Force-apply all current actual_states to GPIO hardware.
        Used after emergency stop recovery to ensure relays match software state."""
        logger.warning("🔄 FORCE APPLYING ALL EQUIPMENT STATES (Post-Emergency Recovery)")
        
        if not self.gpio_initialized:
            logger.error("Cannot force apply - GPIO not initialized")
            return False
        
        success_count = 0
        failed_equipment = []
        
        for equipment, state in self.actual_states.items():
            if equipment in self.gpio_pins:
                result = self._apply_state(equipment, state)
                if result:
                    success_count += 1
                    logger.info(f"✅ Force applied: {equipment} = {state}")
                else:
                    failed_equipment.append(equipment)
                    logger.error(f"❌ Failed to force apply: {equipment} = {state}")
        
        total_equipment = len([eq for eq in self.actual_states.keys() if eq in self.gpio_pins])
        success_rate = success_count / total_equipment if total_equipment > 0 else 0
        
        if failed_equipment:
            logger.critical(f"⚠️  FORCE APPLY PARTIAL FAILURE: {success_count}/{total_equipment} relays applied. Failed: {failed_equipment}")
            logger.critical("Hardware state may not match software state for failed equipment!")
            return False
        else:
            logger.info(f"✅ Force apply complete: {success_count}/{total_equipment} relays applied successfully")
            return True
    
    def sync_hardware_state(self):
        """Read actual GPIO pin states and update actual_states to match hardware.
        Use this when hardware/software state may be out of sync."""
        logger.info("🔍 SYNCING HARDWARE STATE - Reading actual GPIO pin states")
        
        if not self.gpio_initialized:
            logger.error("Cannot sync hardware state - GPIO not initialized")
            return False
        
        if not GPIO_AVAILABLE:
            logger.error("GPIO module not available")
            return False
        
        try:
            import RPi.GPIO as GPIO
            
            synced_count = 0
            for equipment, pin in self.gpio_pins.items():
                try:
                    # Read the actual pin state (Active LOW logic)
                    pin_state = GPIO.input(pin)
                    hardware_state = 'OFF' if pin_state == GPIO.HIGH else 'ON'
                    
                    # Update actual_states to match hardware
                    if self.actual_states[equipment] != hardware_state:
                        logger.warning(f"⚠️  State mismatch for {equipment}: software={self.actual_states[equipment]}, hardware={hardware_state} - syncing to hardware")
                        self.actual_states[equipment] = hardware_state
                        synced_count += 1
                    else:
                        logger.debug(f"✅ {equipment} state matches: {hardware_state}")
                        
                except Exception as e:
                    logger.error(f"Failed to read GPIO pin {pin} for {equipment}: {e}")
            
            logger.info(f"Hardware sync complete: {synced_count} states corrected")
            return True
            
        except Exception as e:
            logger.error(f"Error during hardware sync: {e}")
            return False
    
    def _apply_state(self, equipment, state):
        """Apply the desired state to the equipment (ON/OFF)"""
        logger.info(f"Setting {equipment} to {state} (Control Mode: {self.control_modes[equipment]})")
        
        if equipment not in self.gpio_pins:
            logger.error(f"Invalid equipment: {equipment}")
            return False
        
        if self.control_modes[equipment] == ControlMode.AUTO:
            logger.info(f"  ➡️  {equipment} is in AUTO mode - ignoring manual state set")
            return True  # In AUTO mode, we don't manually control the state
        
        try:
            import RPi.GPIO as GPIO
            
            pin = self.gpio_pins[equipment]
            gpio_state = GPIO.LOW if state == 'ON' else GPIO.HIGH
            
            # Set the GPIO pin to the desired state
            GPIO.output(pin, gpio_state)
            self.actual_states[equipment] = state  # Update the actual state
            logger.info(f"  ➡️  {equipment} set to {state} (GPIO {pin} = {'LOW' if state == 'ON' else 'HIGH'})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set {equipment} to {state}: {e}")
            return False
    
    def set_control_mode(self, equipment, mode):
        """Set the control mode for a specific piece of equipment"""
        logger.info(f"Setting control mode for {equipment} to {mode}")
        
        if equipment not in self.control_modes:
            logger.error(f"Invalid equipment: {equipment}")
            return False
        
        self.control_modes[equipment] = mode
        
        # Immediately apply the current actual state if switching to ON mode
        if mode == ControlMode.ON:
            logger.info(f"  ➡️  Control mode set to ON - applying current state for {equipment}")
            self._apply_state(equipment, self.actual_states[equipment])
        
        return True
    
    def update(self):
        """Main update loop - call this repeatedly in your main program"""
        # Handle Dehumidifier timing
        if self.control_modes['dehum'] == ControlMode.AUTO:
            current_time = time.time()
            
            if self.actual_states['dehum'] == 'ON':
                # Check if we need to turn off the dehumidifier
                if self.dehum_off_start is not None:
                    elapsed = current_time - self.dehum_off_start
                    if elapsed >= self.dehum_min_off_time:
                        logger.info("Dehumidifier ON time exceeded - turning OFF")
                        self._apply_state('dehum', 'OFF')
                        self.dehum_off_start = None  # Reset timer
                else:
                    # Check if we just turned it ON - start the timer
                    if self._apply_state('dehum', 'ON'):
                        self.dehum_off_start = current_time
            
            elif self.actual_states['dehum'] == 'OFF':
                # Check if we need to turn ON the dehumidifier (based on VPD)
                if self.vpd_controller.vpd >= self.vpd_deadband:
                    logger.info("VPD threshold exceeded - turning ON dehumidifier")
                    self._apply_state('dehum', 'ON')
        
        # Handle Humidifier modulation
        if self.control_modes['hum_solenoid'] == ControlMode.AUTO:
            current_time = time.time()
            
            if current_time - self.hum_last_modulation >= self.hum_modulation_period:
                # Time to toggle the humidifier state
                if self.hum_is_on_cycle:
                    logger.info("Humidity cycle complete - turning OFF humidifier")
                    self._apply_state('hum_solenoid', 'OFF')
                else:
                    logger.info("Humidity cycle complete - turning ON humidifier")
                    self._apply_state('hum_solenoid', 'ON')
                
                self.hum_is_on_cycle = not self.hum_is_on_cycle
                self.hum_last_modulation = current_time
        
        # Update VPD controller setpoints based on actual states
        try:
            from software.control.vpd_controller import VPDController
            if isinstance(self.vpd_controller, VPDController):
                if self.actual_states['erv'] == 'ON':
                    self.vpd_controller.erv_setpoint = 1.0  # Example setpoint
                else:
                    self.vpd_controller.erv_setpoint = 0.0
                
                if self.actual_states['supply_fan'] == 'ON':
                    self.vpd_controller.supply_fan_setpoint = 1.0
                else:
                    self.vpd_controller.supply_fan_setpoint = 0.0
                
                if self.actual_states['return_fan'] == 'ON':
                    self.vpd_controller.return_fan_setpoint = 1.0
                else:
                    self.vpd_controller.return_fan_setpoint = 0.0
        except Exception as e:
            logger.debug(f"Could not update VPD controller setpoints: {e}")
        
        # Periodically sync hardware state to prevent drift
        current_time = time.time()
        if current_time - self._last_hardware_sync > self._hardware_sync_interval:
            logger.info("Performing periodic hardware state sync")
            self.sync_hardware_state()
            self._last_hardware_sync = current_time
        
        # Apply states based on control mode (AUTO, ON, OFF)
        force_result = self.force_apply_states()
        
        if not force_result:
            logger.warning("Force apply failed - attempting hardware state sync")
            sync_result = self.sync_hardware_state()
            if sync_result:
                logger.info("Hardware state synced successfully")
            else:
                logger.error("Hardware sync also failed - equipment state unknown")
        
        # Update VPD controller states
        from software.control.vpd_controller import EquipmentState
        for equipment, state in self.actual_states.items():
            self.vpd_controller.equipment_states[equipment] = \
                EquipmentState.ON if state == 'ON' else EquipmentState.OFF
        
        logger.critical(f"✅ FORCE APPLY COMPLETE. Equipment states: {self.actual_states}")
        return