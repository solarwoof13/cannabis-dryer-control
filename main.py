#!/usr/bin/env python3
"""
Cannabis Dryer Control System
Main application entry point

Controls environmental conditions for precise cannabis drying using VPD.
"""

import sys
import os
import logging
import time
from datetime import datetime

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def setup_logging():
    """Configure logging for the application"""
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/dryer_control.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized")
    return logger

def check_system_requirements():
    """Check if we're running on supported hardware"""
    try:
        import RPi.GPIO as GPIO
        return True, "Running on Raspberry Pi"
    except ImportError:
        return False, "Running in development mode (no GPIO access)"

def main():
    """Main application function"""
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("Cannabis Dryer Control System Starting")
    logger.info(f"System startup time: {datetime.now()}")
    logger.info("=" * 50)
    
    # Check system requirements
    is_pi, system_msg = check_system_requirements()
    logger.info(system_msg)
    
    try:
        # Import system components (will create these files next)
        if is_pi:
            logger.info("Initializing hardware components...")
            # TODO: Initialize actual hardware
            # from software.control.sensor_manager import SensorManager
            # from software.control.equipment_controller import EquipmentController
            # sensor_manager = SensorManager()
            # equipment_controller = EquipmentController()
        else:
            logger.info("Running in simulation mode...")
        
        # Start the web interface
        logger.info("Starting web interface...")
        # TODO: Start Flask web server
        # from software.gui.web_interface import start_web_server
        # start_web_server()
        
        # For now, just run a simple loop
        logger.info("System running. Press Ctrl+C to exit.")
        while True:
            logger.info(f"System heartbeat: {datetime.now()}")
            time.sleep(60)  # Log every minute
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"System startup failed: {e}")
        logger.exception("Full error details:")
        sys.exit(1)
    finally:
        logger.info("Cannabis Dryer Control System shutting down")

if __name__ == "__main__":
    main()