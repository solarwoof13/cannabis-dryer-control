#!/usr/bin/env python3
"""
Main entry point for Cannabis Dryer Control System
"""

import sys
import threading
import logging
import time
import os
import platform
from software.control.vpd_controller import PrecisionVPDController, SimulationMode
from software.control.api_server import app, socketio, init_controller, start_background_tasks
from software.control.precision_equipment_control import PrecisionEquipmentController


# Setup logging FIRST (before any logger calls)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/dryer_control.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration - SET THIS BASED ON YOUR ENVIRONMENT
SIMULATION_MODE = False  # Set to True ONLY for testing without sensors

# Detect if running on Raspberry Pi
def is_raspberry_pi():
    """Check if running on Raspberry Pi hardware"""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Raspberry Pi' in f.read()
    except:
        # Also check by CPU architecture
        return platform.machine() in ['armv7l', 'aarch64']

def main():
    """Start the complete system"""
    print("="*60)
    print("Cannabis Dryer Control System")
    print("="*60)
    
    # Platform detection and safety check
    is_pi = is_raspberry_pi()
    
    if is_pi:
        logger.info("Running on Raspberry Pi - Production Mode")
        if SIMULATION_MODE:
            logger.error("WARNING: Simulation mode enabled on Raspberry Pi!")
            print("\n" + "!"*60)
            print("WARNING: Simulation mode should NEVER be used in production!")
            print("!"*60)
            response = input("Are you sure you want to continue with SIMULATED data? (yes/no): ")
            if response.lower() != 'yes':
                logger.info("Exiting for safety. Set SIMULATION_MODE=False for production.")
                print("Exiting for safety. Set SIMULATION_MODE=False for production use.")
                sys.exit(1)
    else:
        logger.info("Running on development machine")
        if not SIMULATION_MODE:
            print("Note: Not on Raspberry Pi - you may want to enable SIMULATION_MODE for testing")
    
    # Initialize the VPD controller
    logger.info("Initializing VPD Controller...")
    controller = PrecisionVPDController()
    equipment_controller = PrecisionEquipmentController(controller)
    logger.info(f"Equipment controller created: {equipment_controller}")

    # STATE RECOVERY CODE GOES HERE (Step 2)
    from software.control.state_manager import StateManager
    from software.control.vpd_controller import DryingPhase
    from datetime import datetime
    
    state_manager = StateManager()
    saved_state = state_manager.load_state()
    
    if saved_state['process_active']:
        # We were in the middle of a process
        logger.warning("RECOVERING FROM POWER LOSS/RESTART")
        logger.info(f"Previous state: Phase={saved_state['current_phase']}")
        
        # Restore the process state
        controller.process_active = True
        controller.current_phase = DryingPhase(saved_state['current_phase'])
        controller.process_start_time = saved_state['process_start_time']
        controller.phase_start_time = saved_state['phase_start_time']
        
        # Calculate where we are in the process
        if controller.process_start_time:
            elapsed = datetime.now() - controller.process_start_time
            total_hours = elapsed.total_seconds() / 3600
            logger.info(f"Process has been running for {total_hours:.1f} hours")
        
        # Resume equipment states
        for equipment, state in saved_state['equipment_states'].items():
            equipment_controller.actual_states[equipment] = state
    else:
        logger.info("Starting fresh - no previous process running")
    
    # Check hardware mode vs simulation
    if controller.hardware_mode and not SIMULATION_MODE:
        print("Running with REAL SENSORS")
        logger.info(f"Hardware mode: Found {len(controller.sensor_manager.sensors)} sensors")
    else:
        print("Running in SIMULATION mode")
        logger.warning("SIMULATION MODE - Using fake sensor data")
        
        # Initialize simulator for fake data
        simulator = SimulationMode(controller)
        
        # Start simulator in background thread
        def run_simulator():
            while True:
                simulator.generate_readings()
                time.sleep(2)
        
        sim_thread = threading.Thread(target=run_simulator, daemon=True)
        sim_thread.start()
        logger.info("Simulation thread started")
    
    # Enhanced control loop with equipment controller
    def enhanced_control_loop():
        while True:
            try:
                logger.info("Control loop iteration starting...")
                # Let the VPD controller read sensors and calculate
                if controller.hardware_mode and controller.sensor_manager:
                    readings = controller.sensor_manager.read_all_sensors()
                    for sensor_id, reading in readings.items():
                        if reading and reading.get('status') == 'ok':
                            controller.update_sensor_reading(
                                sensor_id,
                                reading['temperature'],
                                reading['humidity']
                            )
                
                # Now update equipment using your precise control logic
                try:
                    equipment_controller.update_equipment()
                    logger.info(f"Equipment states: {equipment_controller.actual_states}")
                except Exception as e:
                    logger.error(f"Equipment control failed: {e}")
                    # Continue running - don't crash the main loop
                
                # Save state for power recovery
                try:
                    current_phase = controller.current_phase.value if hasattr(controller.current_phase, 'value') else str(controller.current_phase)
                    state_manager.save_state({
                        'process_active': getattr(controller, 'process_active', False),
                        'current_phase': current_phase,
                        'process_start_time': getattr(controller, 'process_start_time', None),
                        'phase_start_time': getattr(controller, 'phase_start_time', None),
                        'equipment_states': equipment_controller.actual_states
                    })
                except Exception as e:
                    logger.error(f"Failed to save state: {e}")

                # Log status
                status = controller.get_system_status()
                logger.info(f"VPD: {status.get('current_vpd', 0):.2f} | "
                        f"Temp: {status.get('current_temp', 0):.1f}°F | "
                        f"RH: {status.get('current_humidity', 0):.1f}%")
                
                time.sleep(10)
            except Exception as e:
                logger.error(f"Control loop error: {e}")
                time.sleep(5)

    control_thread = threading.Thread(target=enhanced_control_loop, daemon=True)
    control_thread.start()
    logger.info("Control loop thread started")
    
    # Initialize Flask with BOTH controllers
    init_controller(controller, equipment_controller)
    
    # Start background tasks for web interface
    start_background_tasks()
    
    print("------------------------------------------------------------")
    print("Starting web interface on http://localhost:5001")
    if is_pi:
        print("Access from network: http://<pi-ip-address>:5001")
    print("Open your browser to see the dashboard")
    print("Press Ctrl+C to stop the system")
    print("------------------------------------------------------------")
    
    # Start Flask web server
    try:
        if is_pi:
            # On Raspberry Pi - production mode
            logger.info("Starting production web server on port 5001")
            socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
        else:
            # On development machine
            logger.info("Starting development web server on port 5001")
            socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
    except Exception as e:
        logger.error(f"Failed to start web server: {e}")
        raise

if __name__ == "__main__":
    try:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Start the main application
        main()
        
    except KeyboardInterrupt:
        print("\n" + "="*60)
        print("Shutting down gracefully...")
        print("="*60)
        logger.info("System shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFATAL ERROR: {e}")
        print("Check logs/dryer_control.log for details")
        sys.exit(1)