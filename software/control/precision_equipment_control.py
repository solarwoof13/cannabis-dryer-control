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
from software.control.tuya_minisplit_control import create_controller as create_minisplit_controller

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

        # Initialize mini-split WiFi control
        try:
            self.minisplit_controller = create_minisplit_controller()
            logger.info("Mini-split WiFi control initialized")
        except Exception as e:
            logger.error(f"Failed to initialize mini-split WiFi control: {e}")
            self.minisplit_controller = None

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
        logger.info(f"Setting {equipment} to {state}")
        
        if equipment not in self.gpio_pins:
            logger.debug(f"No GPIO pin for {equipment} (OK for mini_split)")
            # Still update actual_states even for equipment without GPIO pins
            self.actual_states[equipment] = state
            return True  # Not an error for equipment without GPIO pins
        
        try:
            import RPi.GPIO as GPIO
            
            pin = self.gpio_pins[equipment]
            gpio_state = GPIO.LOW if state == 'ON' else GPIO.HIGH
            
            # Set the GPIO pin to the desired state
            GPIO.output(pin, gpio_state)
            logger.info(f"  ➡️  {equipment} set to {state} (GPIO {pin} = {'LOW' if state == 'ON' else 'HIGH'})")
            
            # CRITICAL: Update actual_states when GPIO operation succeeds
            self.actual_states[equipment] = state
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
    
    def update_equipment(self):
        """Main equipment control update - call this repeatedly"""
        logger.info("🔄 update_equipment() called")
        
        # Track if process just became active (recovering from emergency stop)
        current_process_active = self.vpd_controller.process_active
        logger.info(f"Process active: {current_process_active}, Phase: {self.vpd_controller.current_phase}")
        
        if not current_process_active:
            logger.debug("Process NOT active - skipping equipment control")
            self._process_was_inactive = True  # Remember we were inactive
            self._first_active_cycle = True
            # Equipment stays in current state (should be OFF after emergency stop)
            return
        
        # Detect transition from inactive to active (recovery from emergency stop)
        if self._process_was_inactive and current_process_active:
            logger.critical("🔄 PROCESS REACTIVATED - Recovering from emergency stop")
            self._process_was_inactive = False
        
        logger.info(f"Process ACTIVE - Running equipment control")
        
        # Get current conditions - USE SAME LOGIC AS API STATUS FOR CONSISTENCY
        current_vpd = None
        supply_temp = None
        supply_humidity = None
        
        # Use supply air conditions only, with same fallback logic as API
        if hasattr(self.vpd_controller, 'get_supply_air_conditions'):
            try:
                supply_temp, supply_humidity, supply_dew_point, supply_vpd = self.vpd_controller.get_supply_air_conditions()
                if supply_vpd is not None and supply_temp is not None and supply_humidity is not None:
                    current_vpd = supply_vpd
                    logger.info(f"Equipment control using supply air: VPD={current_vpd:.3f}, T={supply_temp:.1f}°F, RH={supply_humidity:.1f}%")
                else:
                    logger.warning("Supply air conditions returned None values")
            except Exception as e:
                logger.warning(f"Supply air sensors not available for equipment control: {e}")
        
        # Same fallback logic as API status
        if current_vpd is None and hasattr(self.vpd_controller, 'last_vpd') and self.vpd_controller.last_vpd is not None:
            current_vpd = self.vpd_controller.last_vpd
            if hasattr(self.vpd_controller, 'last_temp') and self.vpd_controller.last_temp is not None:
                supply_temp = self.vpd_controller.last_temp
            if hasattr(self.vpd_controller, 'last_humidity') and self.vpd_controller.last_humidity is not None:
                supply_humidity = self.vpd_controller.last_humidity
            logger.info(f"Equipment control using cached values: VPD={current_vpd:.3f}")
        
        # Final fallback
        if current_vpd is None:
            current_vpd = 0.75
            logger.warning("No VPD data available for equipment control, using default 0.75 kPa")
        
        if supply_temp is None:
            supply_temp = 68.0
        if supply_humidity is None:
            supply_humidity = 60.0
        
        # Get current phase and target setpoint
        try:
            phase = self.vpd_controller.current_phase.value
            setpoint = self.vpd_controller.phase_setpoints[self.vpd_controller.current_phase]
            logger.info(f"Phase: {phase}, Target VPD: {setpoint.vpd_min:.2f}-{setpoint.vpd_max:.2f} kPa, Target DP: {setpoint.dew_point_target:.1f}°F")
        except Exception as e:
            logger.error(f"Failed to get phase setpoint: {e}")
            return
        
        # Update mini-split temperature based on VPD controller setpoint
        if self.minisplit_controller and hasattr(self.vpd_controller, 'mini_split_setpoint'):
            target_temp = self.vpd_controller.mini_split_setpoint
            # Only send command if temperature changed significantly (0.5°F threshold)
            if not hasattr(self, '_last_minisplit_temp') or abs(target_temp - self._last_minisplit_temp) >= 0.5:
                logger.info(f"Mini-split setpoint changed: {getattr(self, '_last_minisplit_temp', 'N/A')} → {target_temp}°F")
                success = self.minisplit_controller.set_temperature(target_temp, 'cool')
                if success:
                    self._last_minisplit_temp = target_temp
                    logger.info(f"✓ Mini-split set to {target_temp}°F via WiFi")
                else:
                    logger.warning(f"Failed to set mini-split to {target_temp}°F")

        # Calculate what equipment states should be based on automatic control
        auto_states = self.calculate_automatic_control(
            current_vpd, setpoint.vpd_min, setpoint.vpd_max,
            55.0, setpoint.dew_point_target,  # Use default dew point for now
            supply_humidity, phase
        )
        
        logger.info(f"Calculated auto states: {auto_states}")
        logger.info(f"Current actual states: {self.actual_states}")
        
        # CRITICAL FIX: Force apply ALL states on first cycle after process restart
        if self._first_active_cycle:
            logger.critical("⚡ FIRST ACTIVE CYCLE - FORCE APPLYING ALL STATES ⚡")
            self._first_active_cycle = False
            
            # Update actual_states to the calculated auto_states
            for equipment, mode in self.control_modes.items():
                if mode == ControlMode.AUTO and equipment in auto_states:
                    self.actual_states[equipment] = auto_states[equipment]
                elif mode == ControlMode.ON:
                    self.actual_states[equipment] = 'ON'
                elif mode == ControlMode.OFF:
                    self.actual_states[equipment] = 'OFF'
            
            # Force apply all states to GPIO
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
        
        # Periodic hardware state sync to prevent drift
        current_time = time.time()
        if current_time - self._last_hardware_sync > self._hardware_sync_interval:
            logger.info("Performing periodic hardware state sync")
            self.sync_hardware_state()
            self._last_hardware_sync = current_time
        
        # Apply states based on control mode (AUTO, ON, OFF)
        for equipment, mode in self.control_modes.items():
            if mode == ControlMode.AUTO:
                # Use automatic control
                if equipment in auto_states:
                    new_state = auto_states[equipment]
                    if self.actual_states[equipment] != new_state:
                        logger.info(f"Changing {equipment}: {self.actual_states[equipment]} → {new_state} (AUTO mode)")
                        # Only update actual_states if hardware control succeeds
                        if self._apply_state(equipment, new_state):
                            self.actual_states[equipment] = new_state
                            logger.info(f"✅ {equipment} state updated to {new_state}")
                        else:
                            logger.error(f"❌ Failed to apply {equipment} = {new_state} - keeping current state")
            
            elif mode == ControlMode.ON:
                # Manual ON override
                if self.actual_states[equipment] != 'ON':
                    logger.info(f"Forcing {equipment} ON (manual override)")
                    if self._apply_state(equipment, 'ON'):
                        self.actual_states[equipment] = 'ON'
                        logger.info(f"✅ {equipment} forced ON")
                    else:
                        logger.error(f"❌ Failed to force {equipment} ON")
            
            elif mode == ControlMode.OFF:
                # Manual OFF override
                if self.actual_states[equipment] != 'OFF':
                    logger.info(f"Forcing {equipment} OFF (manual override)")
                    if self._apply_state(equipment, 'OFF'):
                        self.actual_states[equipment] = 'OFF'
                        logger.info(f"✅ {equipment} forced OFF")
                    else:
                        logger.error(f"❌ Failed to force {equipment} OFF")
        
        # Update VPD controller equipment states for display/status
        from software.control.vpd_controller import EquipmentState
        for equipment, state in self.actual_states.items():
            self.vpd_controller.equipment_states[equipment] = \
                EquipmentState.ON if state == 'ON' else EquipmentState.OFF
    
    def calculate_automatic_control(self, current_vpd, target_vpd_min, target_vpd_max, 
                                   current_dew_point, target_dew_point, current_humidity, phase):
        """Calculate automatic equipment states based on current conditions"""
        new_states = {
            'dehum': 'OFF',
            'hum_solenoid': 'OFF', 
            'hum_fan': 'OFF',
            'erv': 'OFF',
            'supply_fan': 'ON',  # Always ON during active phases
            'return_fan': 'ON',  # Always ON during active phases
            'mini_split': 'ON'   # Always ON for temperature control
        }
        
        # Handle different phases
        if phase == 'storage':
            # STORAGE MODE: Monitor humidity, cycle equipment
            logger.info(f"STORAGE MODE: Checking humidity {current_humidity:.1f}%")
            if current_humidity > 65:  # Too humid
                new_states['dehum'] = 'ON'
                new_states['hum_solenoid'] = 'OFF'
                new_states['hum_fan'] = 'OFF'
                logger.info(f"STORAGE: Dehumidifier ON (RH {current_humidity:.1f}% > 65%)")
            elif current_humidity < 55:  # Too dry
                new_states['hum_solenoid'] = 'ON'
                new_states['hum_fan'] = 'ON'
                new_states['dehum'] = 'OFF'
                logger.info(f"STORAGE: Humidifier ON (RH {current_humidity:.1f}% < 55%)")
            else:
                # Humidity OK - everything off
                new_states['dehum'] = 'OFF'
                new_states['hum_solenoid'] = 'OFF'
                new_states['hum_fan'] = 'OFF'
                logger.info(f"STORAGE: Humidity OK (RH {current_humidity:.1f}% in 55-65%) - setting hum_fan OFF")
            
            # Mini-split stays on for temperature, fans stay on for circulation
            return new_states
        
        # ACTIVE DRYING/CURING PHASES - ERV should be ON for air exchange
        new_states['erv'] = 'ON'  # Enable ERV for air exchange during active drying
        new_states['hum_fan'] = 'ON'  # Humidifier fan always ON during active phases
        
        # Calculate VPD target midpoint and error
        vpd_target = (target_vpd_min + target_vpd_max) / 2
        vpd_error = current_vpd - vpd_target
        
        # Calculate dew point error
        dew_error = current_dew_point - target_dew_point
        
        logger.info(f"Control errors: VPD_error={vpd_error:.3f} kPa, DP_error={dew_error:.2f}°F")
        
        # PRIMARY CONTROL: VPD-BASED
        
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
            # hum_fan stays ON during active phases
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
                # hum_fan stays ON during active phases
                logger.info(f"Dew point low ({current_dew_point:.1f}°F < {target_dew_point:.1f}°F) - light humidification")
            
            else:
                # Perfect conditions - minimal intervention
                new_states['dehum'] = 'ON'  # Keep on for stability (your primary control)
                new_states['hum_solenoid'] = 'OFF'
                # hum_fan stays ON during active phases
                self.hum_modulation_rate = 0.0
                logger.info("Conditions optimal - minimal intervention")
        
        return new_states
    
    def _apply_modulation(self):
        """Apply duty cycle modulation to humidifier"""
        if self.hum_modulation_rate >= 100.0:
            return 'ON'
        elif self.hum_modulation_rate <= 0.0:
            return 'OFF'
        else:
            # Simple duty cycle - could be improved with PWM
            # For now, just threshold at 50%
            return 'ON' if self.hum_modulation_rate >= 50.0 else 'OFF'