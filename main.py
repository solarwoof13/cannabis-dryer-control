#!/usr/bin/env python3
"""
Main entry point for Cannabis Dryer Control System
"""

import sys
import threading
import logging
import time
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
    
    # Initialize the VPD controller
    controller = PrecisionVPDController()
    
    # Always run in simulation mode on Mac
    print("Running in SIMULATION mode")
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
    
    # Start the web server
    print("-"*60)
    print("Starting web interface on http://localhost:5000")
    print("Open your browser to see the dashboard")
    print("-"*60)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    main()