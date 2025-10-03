#!/usr/bin/env python3
"""
Tuya Mini-Split WiFi Control Module
Local control via Tuya protocol - no cloud dependency
"""

import logging
import tinytuya
import time
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class TuyaMiniSplitController:
    """
    Local WiFi control for ACiQ mini-split
    Integrates with Cannabis Dryer VPD control system
    """
    
    def __init__(self, device_id: str, ip_address: str, local_key: str):
        """
        Initialize controller
        
        Args:
            device_id: Tuya device ID
            ip_address: Local IP address
            local_key: Local encryption key
        """
        self.device = tinytuya.OutletDevice(
            dev_id=device_id,
            address=ip_address,
            local_key=local_key,
            version=3.5
        )
        
        # Data Point mappings from device
        self.DP_POWER = 1
        self.DP_TEMP_SET_F = 24  # Temperature in Fahrenheit (scale: 680 = 68.0°F)
        self.DP_TEMP_CURRENT_F = 23
        self.DP_MODE = 4
        
        self.temp_scale = 10  # Scale factor for temperature
        self.last_command_time = None
        self.min_command_interval = 5  # Seconds between commands
        
        logger.info(f"Tuya mini-split initialized at {ip_address}")
    
    def set_temperature(self, temp_f: float, mode: str = 'cool') -> bool:
        """
        Set mini-split temperature
        
        Args:
            temp_f: Target temperature in Fahrenheit (60-75°F)
            mode: Operating mode ('cool', 'heat', 'dry', 'auto')
        
        Returns:
            bool: True if command sent successfully
        """
        # Validate temperature range
        if not 60 <= temp_f <= 75:
            logger.error(f"Temperature {temp_f}°F outside safe range (60-75°F)")
            return False
        
        # Rate limiting
        current_time = time.time()
        if self.last_command_time:
            elapsed = current_time - self.last_command_time
            if elapsed < self.min_command_interval:
                logger.debug(f"Rate limited: {self.min_command_interval - elapsed:.1f}s remaining")
                return False
        
        try:
            # Convert temperature (68.0°F → 680)
            temp_value = int(temp_f * self.temp_scale)
            
            # Map mode to Tuya protocol
            mode_map = {
                'cool': 'cold',
                'heat': 'hot',
                'dry': 'wet',
                'fan': 'wind',
                'auto': 'auto'
            }
            tuya_mode = mode_map.get(mode.lower(), 'cold')
            
            logger.info(f"Setting mini-split: {temp_f}°F, mode={tuya_mode}")
            
            # Send commands with delays for reliability
            self.device.set_value(self.DP_POWER, True)
            time.sleep(0.3)
            
            self.device.set_value(self.DP_TEMP_SET_F, temp_value)
            time.sleep(0.3)
            
            self.device.set_value(self.DP_MODE, tuya_mode)
            
            self.last_command_time = current_time
            logger.info(f"✓ Mini-split command sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set mini-split temperature: {e}")
            return False
    
    def get_status(self) -> Optional[Dict]:
        """
        Get current mini-split status
        
        Returns:
            Dict with status info, or None if failed
        """
        try:
            data = self.device.status()
            
            if 'dps' not in data:
                logger.warning("No status data received from mini-split")
                return None
            
            dps = data['dps']
            
            # Extract and convert values
            power = dps.get(self.DP_POWER, False)
            temp_set_raw = dps.get(self.DP_TEMP_SET_F, 680)
            temp_current = dps.get(self.DP_TEMP_CURRENT_F, 68)
            mode = dps.get(self.DP_MODE, 'auto')
            
            # Convert setpoint (680 → 68.0°F)
            temp_setpoint = temp_set_raw / self.temp_scale
            
            return {
                'power': power,
                'setpoint_f': temp_setpoint,
                'current_temp_f': temp_current,
                'mode': mode,
                'connected': True
            }
            
        except Exception as e:
            logger.error(f"Failed to get mini-split status: {e}")
            return {'connected': False}
    
    def turn_on(self) -> bool:
        """Turn mini-split on"""
        try:
            self.device.set_value(self.DP_POWER, True)
            logger.info("Mini-split powered ON")
            return True
        except Exception as e:
            logger.error(f"Failed to turn on mini-split: {e}")
            return False
    
    def turn_off(self) -> bool:
        """Turn mini-split off"""
        try:
            self.device.set_value(self.DP_POWER, False)
            logger.info("Mini-split powered OFF")
            return True
        except Exception as e:
            logger.error(f"Failed to turn off mini-split: {e}")
            return False


# Factory function for easy initialization with your device
def create_controller() -> TuyaMiniSplitController:
    """
    Create mini-split controller with your device credentials
    
    Returns:
        Initialized TuyaMiniSplitController
    """
    return TuyaMiniSplitController(
        device_id='ebd8ae0d1783ca14a68erz',
        ip_address='192.168.1.175',
        local_key='*pwzsT>UD+?-+6xu'
    )


if __name__ == "__main__":
    # Test script
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("Tuya Mini-Split WiFi Control Test")
    print("=" * 50)
    
    controller = create_controller()
    
    # Get current status
    print("\nCurrent Status:")
    status = controller.get_status()
    if status:
        for key, value in status.items():
            print(f"  {key}: {value}")
    
    # Test setting temperature
    print("\nSetting temperature to 68°F...")
    success = controller.set_temperature(68, 'cool')
    print(f"Result: {'Success' if success else 'Failed'}")
    
    time.sleep(3)
    
    # Get updated status
    print("\nUpdated Status:")
    status = controller.get_status()
    if status:
        for key, value in status.items():
            print(f"  {key}: {value}")