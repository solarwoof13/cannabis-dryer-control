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
SIMULATION_MODE = True  # Set to True ONLY for testing without sensors

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
    
    # Start control loop in background thread
    control_thread = threading.Thread(target=controller.run_control_loop, daemon=True)
    control_thread.start()
    logger.info("Control loop thread started")
    
    # Initialize Flask with the controller
    init_controller(controller)
    
    # Start background tasks for web interface
    start_background_tasks()
    
    print("------------------------------------------------------------")
    print("Starting web interface on http://localhost:5000")
    if is_pi:
        print("Access from network: http://<pi-ip-address>:5000")
    print("Open your browser to see the dashboard")
    print("Press Ctrl+C to stop the system")
    print("------------------------------------------------------------")
    
    # Start Flask web server
    try:
        if is_pi:
            # On Raspberry Pi - production mode
            logger.info("Starting production web server on port 5000")
            socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
        else:
            # On development machine
            logger.info("Starting development web server on port 5000")
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