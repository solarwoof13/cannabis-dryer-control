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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/dryer_control.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Start the complete system"""
    print("="*60)
    print("Cannabis Dryer Control System")
    print("="*60)
    
    # Detect if running on Raspberry Pi
    is_pi = platform.machine() in ['armv7l', 'aarch64'] or os.path.exists('/sys/firmware/devicetree/base/model')
    
    # Initialize the VPD controller
    controller = PrecisionVPDController()
    
    # Check if we have hardware or need simulation
    if controller.hardware_mode:
        print("Running with REAL SENSORS")
        print(f"Found {len(controller.sensor_manager.sensors)} sensors")
    else:
        print("Running in SIMULATION mode")
    
    # Initialize simulator (runs but doesn't generate fake data if hardware is present)
    simulator = SimulationMode(controller)
    
    # Start simulator in background
    def run_simulator():
        while True:
            simulator.generate_readings()
            time.sleep(2)
    
    sim_thread = threading.Thread(target=run_simulator, daemon=True)
    sim_thread.start()
    
    # Start control loop in background
    control_thread = threading.Thread(target=controller.run_control_loop, daemon=True)
    control_thread.start()
    
    # Initialize Flask with the controller
    init_controller(controller)
    
    # Start background tasks
    start_background_tasks()
    
    print("------------------------------------------------------------")
    print("Starting web interface on http://localhost:5000")
    print("Open your browser to see the dashboard")
    print("------------------------------------------------------------")
    
    # Start Flask with appropriate settings based on platform
    if is_pi:
        # On Raspberry Pi, allow unsafe werkzeug for development
        # For production, consider using gunicorn or eventlet server
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    else:
        # On development machine (Mac/Windows/Linux desktop)
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)