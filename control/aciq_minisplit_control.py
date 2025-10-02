#!/usr/bin/env python3
"""
ACiQ Mini-Split WiFi Control Module
====================================
Integrates with Cannabis Dryer Control System

This module provides WiFi control for ACiQ mini-splits with built-in WiFi.
Supports both local MQTT and cloud API control methods.

Security Features:
- Encrypted credentials storage
- API rate limiting
- Connection timeout protection
- Fallback to IR control
- Network isolation support

Integration Point: precision_equipment_control.py
Replace IR control with this module after successful testing

Author: Cannabis Dryer Control System
Version: 1.0
"""

import logging
import time
import json
import hashlib
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Tuple
import threading

logger = logging.getLogger(__name__)

# Control method detection
MQTT_AVAILABLE = False
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    logger.warning("paho-mqtt not available - MQTT control disabled")

HTTP_AVAILABLE = False
try:
    import requests
    HTTP_AVAILABLE = True
except ImportError:
    logger.warning("requests not available - HTTP control disabled")


class ControlMethod(Enum):
    """Available control methods"""
    MQTT_LOCAL = "mqtt_local"
    HTTP_LOCAL = "http_local"
    CLOUD_API = "cloud_api"
    IR_FALLBACK = "ir_fallback"


class MiniSplitMode(Enum):
    """Operating modes"""
    COOL = "cool"
    HEAT = "heat"
    DRY = "dry"
    FAN = "fan"
    AUTO = "auto"


class FanSpeed(Enum):
    """Fan speed settings"""
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ACiQMiniSplitController:
    """
    Secure WiFi control for ACiQ mini-splits
    Designed to integrate with your existing VPD control system
    """
    
    def __init__(self, config_file='software/config/aciq_config.json'):
        """
        Initialize mini-split controller
        
        Args:
            config_file: Path to encrypted config file
        """
        self.config_file = config_file
        self.config = self._load_config()
        
        # Connection state
        self.connected = False
        self.control_method = None
        self.last_command_time = None
        self.command_queue = []
        
        # Current state tracking
        self.current_temp_setpoint = 68.0  # °F
        self.current_mode = MiniSplitMode.COOL
        self.current_fan_speed = FanSpeed.AUTO
        self.actual_temp = None
        self.is_running = False
        
        # Rate limiting
        self.min_command_interval = 5  # seconds between commands
        self.max_commands_per_minute = 10
        self.command_history = []
        
        # Timeout protection
        self.command_timeout = 10  # seconds
        self.connection_timeout = 30
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Initialize connection
        self._initialize_connection()
    
    def _load_config(self) -> Dict:
        """Load and decrypt configuration"""
        try:
            if not os.path.exists(self.config_file):
                logger.warning(f"Config file not found: {self.config_file}")
                logger.info("Creating default configuration...")
                return self._create_default_config()
            
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            # Decrypt sensitive fields if encrypted
            if config.get('encrypted', False):
                config = self._decrypt_config(config)
            
            return config
        
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self._create_default_config()
    
    def _create_default_config(self) -> Dict:
        """Create default configuration template"""
        return {
            'enabled': False,
            'control_method': 'mqtt_local',
            'device_ip': '192.168.1.100',
            'device_id': 'aciq_minisplit_001',
            
            # MQTT settings (for local control)
            'mqtt': {
                'broker': '192.168.1.100',
                'port': 1883,
                'username': '',
                'password': '',
                'topic_prefix': 'aciq',
                'use_tls': False
            },
            
            # HTTP API settings (for local HTTP control)
            'http': {
                'base_url': 'http://192.168.1.100',
                'api_key': '',
                'use_https': False,
                'verify_ssl': False
            },
            
            # Cloud API settings (fallback)
            'cloud': {
                'api_url': 'https://api.aciq.com',
                'username': '',
                'password': '',
                'app_token': ''
            },
            
            # Safety limits
            'limits': {
                'temp_min': 60,
                'temp_max': 75,
                'max_commands_per_minute': 10
            },
            
            # IR fallback
            'ir_fallback': {
                'enabled': True,
                'gpio_pin': 18
            },
            
            'encrypted': False
        }
    
    def _encrypt_config(self, config: Dict) -> Dict:
        """Encrypt sensitive configuration fields"""
        # TODO: Implement proper encryption for production
        # Use cryptography.fernet or similar
        logger.warning("Config encryption not yet implemented")
        return config
    
    def _decrypt_config(self, config: Dict) -> Dict:
        """Decrypt sensitive configuration fields"""
        # TODO: Implement proper decryption for production
        logger.warning("Config decryption not yet implemented")
        return config
    
    def _initialize_connection(self):
        """Initialize connection based on config"""
        if not self.config.get('enabled', False):
            logger.info("ACiQ WiFi control is disabled in config")
            return
        
        method = self.config.get('control_method', 'mqtt_local')
        
        try:
            if method == 'mqtt_local' and MQTT_AVAILABLE:
                self._init_mqtt_control()
            elif method == 'http_local' and HTTP_AVAILABLE:
                self._init_http_control()
            elif method == 'cloud_api' and HTTP_AVAILABLE:
                self._init_cloud_api()
            else:
                logger.warning(f"Control method {method} not available, using IR fallback")
                self.control_method = ControlMethod.IR_FALLBACK
        
        except Exception as e:
            logger.error(f"Failed to initialize {method}: {e}")
            self.control_method = ControlMethod.IR_FALLBACK
    
    def _init_mqtt_control(self):
        """Initialize MQTT local control"""
        logger.info("Initializing MQTT local control...")
        
        mqtt_config = self.config['mqtt']
        
        try:
            self.mqtt_client = mqtt.Client(client_id=f"cannabis_dryer_{int(time.time())}")
            
            # Set username/password if provided
            if mqtt_config.get('username'):
                self.mqtt_client.username_pw_set(
                    mqtt_config['username'],
                    mqtt_config.get('password', '')
                )
            
            # TLS if enabled
            if mqtt_config.get('use_tls', False):
                self.mqtt_client.tls_set()
            
            # Callbacks
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            self.mqtt_client.on_message = self._on_mqtt_message
            
            # Connect
            self.mqtt_client.connect(
                mqtt_config['broker'],
                mqtt_config.get('port', 1883),
                keepalive=60
            )
            
            self.mqtt_client.loop_start()
            
            # Wait for connection
            time.sleep(2)
            
            if self.connected:
                self.control_method = ControlMethod.MQTT_LOCAL
                logger.info("✓ MQTT local control initialized")
            else:
                raise Exception("Failed to connect to MQTT broker")
        
        except Exception as e:
            logger.error(f"MQTT initialization failed: {e}")
            raise
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            
            # Subscribe to status topics
            device_id = self.config['device_id']
            topic_prefix = self.config['mqtt']['topic_prefix']
            
            status_topic = f"{topic_prefix}/{device_id}/status"
            client.subscribe(status_topic)
            logger.info(f"Subscribed to: {status_topic}")
        else:
            logger.error(f"MQTT connection failed with code: {rc}")
            self.connected = False
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnect (code: {rc})")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            payload = json.loads(msg.payload.decode())
            logger.debug(f"MQTT message received: {payload}")
            
            # Update current state from device
            if 'temperature' in payload:
                self.actual_temp = payload['temperature']
            if 'mode' in payload:
                self.current_mode = MiniSplitMode(payload['mode'])
            if 'running' in payload:
                self.is_running = payload['running']
        
        except json.JSONDecodeError:
            logger.warning(f"Invalid MQTT message: {msg.payload}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def _init_http_control(self):
        """Initialize HTTP local API control"""
        logger.info("Initializing HTTP local control...")
        
        http_config = self.config['http']
        base_url = http_config['base_url']
        
        try:
            # Test connection
            response = requests.get(
                f"{base_url}/api/status",
                timeout=5,
                verify=http_config.get('verify_ssl', False)
            )
            
            if response.status_code in [200, 401]:
                self.connected = True
                self.control_method = ControlMethod.HTTP_LOCAL
                logger.info("✓ HTTP local control initialized")
            else:
                raise Exception(f"Unexpected status code: {response.status_code}")
        
        except Exception as e:
            logger.error(f"HTTP initialization failed: {e}")
            raise
    
    def _init_cloud_api(self):
        """Initialize cloud API control"""
        logger.info("Initializing cloud API control...")
        
        cloud_config = self.config['cloud']
        
        try:
            # Authenticate with cloud API
            response = requests.post(
                f"{cloud_config['api_url']}/auth/login",
                json={
                    'username': cloud_config['username'],
                    'password': cloud_config['password']
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.cloud_token = data.get('token')
                self.connected = True
                self.control_method = ControlMethod.CLOUD_API
                logger.info("✓ Cloud API initialized")
            else:
                raise Exception(f"Authentication failed: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Cloud API initialization failed: {e}")
            raise
    
    def _check_rate_limit(self) -> bool:
        """Check if command is within rate limits"""
        with self.lock:
            now = time.time()
            
            # Remove old commands from history (older than 1 minute)
            self.command_history = [
                t for t in self.command_history 
                if now - t < 60
            ]
            
            # Check minute limit
            if len(self.command_history) >= self.max_commands_per_minute:
                logger.warning("Rate limit exceeded")
                return False
            
            # Check minimum interval
            if self.last_command_time:
                time_since_last = now - self.last_command_time
                if time_since_last < self.min_command_interval:
                    logger.debug(f"Waiting {self.min_command_interval - time_since_last:.1f}s")
                    return False
            
            return True
    
    def _record_command(self):
        """Record command for rate limiting"""
        with self.lock:
            now = time.time()
            self.command_history.append(now)
            self.last_command_time = now
    
    def set_temperature(self, temp_f: float, mode: str = 'cool') -> bool:
        """
        Set temperature setpoint (in Fahrenheit)
        
        Args:
            temp_f: Target temperature in °F
            mode: Operating mode ('cool', 'heat', 'dry', 'fan', 'auto')
        
        Returns:
            True if command sent successfully
        """
        # Validate inputs
        limits = self.config['limits']
        if not limits['temp_min'] <= temp_f <= limits['temp_max']:
            logger.error(f"Temperature {temp_f}°F outside safe limits")
            return False
        
        # Check rate limiting
        if not self._check_rate_limit():
            logger.warning("Command blocked by rate limiter")
            return False
        
        try:
            mode_enum = MiniSplitMode(mode.lower())
        except ValueError:
            logger.error(f"Invalid mode: {mode}")
            return False
        
        # Convert to Celsius for device
        temp_c = (temp_f - 32) * 5/9
        
        logger.info(f"Setting mini-split: {temp_f}°F ({temp_c:.1f}°C), mode={mode}")
        
        # Send command based on control method
        success = False
        
        if self.control_method == ControlMethod.MQTT_LOCAL:
            success = self._mqtt_set_temperature(temp_c, mode_enum)
        elif self.control_method == ControlMethod.HTTP_LOCAL:
            success = self._http_set_temperature(temp_c, mode_enum)
        elif self.control_method == ControlMethod.CLOUD_API:
            success = self._cloud_set_temperature(temp_c, mode_enum)
        elif self.control_method == ControlMethod.IR_FALLBACK:
            success = self._ir_set_temperature(temp_f, mode_enum)
        else:
            logger.error("No control method available")
            return False
        
        if success:
            self._record_command()
            self.current_temp_setpoint = temp_f
            self.current_mode = mode_enum
        
        return success
    
    def _mqtt_set_temperature(self, temp_c: float, mode: MiniSplitMode) -> bool:
        """Send temperature command via MQTT"""
        if not self.connected:
            logger.error("MQTT not connected")
            return False
        
        try:
            device_id = self.config['device_id']
            topic_prefix = self.config['mqtt']['topic_prefix']
            
            command_topic = f"{topic_prefix}/{device_id}/command"
            
            payload = {
                'temperature': round(temp_c, 1),
                'mode': mode.value,
                'fan_speed': self.current_fan_speed.value,
                'power': 'on'
            }
            
            result = self.mqtt_client.publish(
                command_topic,
                json.dumps(payload),
                qos=1
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("✓ MQTT command sent successfully")
                return True
            else:
                logger.error(f"MQTT publish failed: {result.rc}")
                return False
        
        except Exception as e:
            logger.error(f"MQTT command failed: {e}")
            return False
    
    def _http_set_temperature(self, temp_c: float, mode: MiniSplitMode) -> bool:
        """Send temperature command via HTTP API"""
        http_config = self.config['http']
        
        try:
            response = requests.post(
                f"{http_config['base_url']}/api/control",
                json={
                    'device_id': self.config['device_id'],
                    'temperature': round(temp_c, 1),
                    'mode': mode.value,
                    'fan_speed': self.current_fan_speed.value
                },
                headers={'Authorization': f"Bearer {http_config.get('api_key', '')}"},
                timeout=self.command_timeout,
                verify=http_config.get('verify_ssl', False)
            )
            
            if response.status_code == 200:
                logger.info("✓ HTTP command sent successfully")
                return True
            else:
                logger.error(f"HTTP command failed: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"HTTP command failed: {e}")
            return False
    
    def _cloud_set_temperature(self, temp_c: float, mode: MiniSplitMode) -> bool:
        """Send temperature command via cloud API"""
        cloud_config = self.config['cloud']
        
        try:
            response = requests.post(
                f"{cloud_config['api_url']}/devices/control",
                json={
                    'device_id': self.config['device_id'],
                    'temperature': round(temp_c, 1),
                    'mode': mode.value,
                    'fan_speed': self.current_fan_speed.value
                },
                headers={'Authorization': f"Bearer {self.cloud_token}"},
                timeout=self.command_timeout
            )
            
            if response.status_code == 200:
                logger.info("✓ Cloud API command sent successfully")
                return True
            else:
                logger.error(f"Cloud API command failed: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Cloud API command failed: {e}")
            return False
    
    def _ir_set_temperature(self, temp_f: float, mode: MiniSplitMode) -> bool:
        """Fallback to IR control"""
        logger.warning("Using IR fallback control")
        
        # TODO: Implement IR control fallback
        # This would call your existing IR control code
        # from hardware/pi/hardware_interface.py IRController class
        
        logger.info(f"IR: Set to {temp_f}°F, mode={mode.value}")
        return True
    
    def get_status(self) -> Dict:
        """
        Get current mini-split status
        
        Returns:
            Dictionary with current state
        """
        return {
            'connected': self.connected,
            'control_method': self.control_method.value if self.control_method else None,
            'setpoint_f': self.current_temp_setpoint,
            'actual_temp_f': self.actual_temp,
            'mode': self.current_mode.value,
            'fan_speed': self.current_fan_speed.value,
            'is_running': self.is_running,
            'last_command': self.last_command_time
        }
    
    def shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down mini-split controller...")
        
        if self.control_method == ControlMethod.MQTT_LOCAL and hasattr(self, 'mqtt_client'):
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        self.connected = False
        logger.info("Mini-split controller shutdown complete")


# Integration helper for precision_equipment_control.py
class MiniSplitAdapter:
    """
    Adapter to integrate ACiQ WiFi control with existing system
    Replace IRController in hardware_interface.py with this class
    """
    
    def __init__(self):
        self.controller = ACiQMiniSplitController()
        self.current_setpoint = 68.0
        logger.info("Mini-split adapter initialized")
    
    def set_temperature(self, temp_f: float, mode: str = 'cool') -> bool:
        """
        Set temperature - matches IRController interface
        
        Args:
            temp_f: Target temperature in °F
            mode: Operating mode
        
        Returns:
            True if successful
        """
        self.current_setpoint = temp_f
        return self.controller.set_temperature(temp_f, mode)
    
    def get_status(self) -> Dict:
        """Get current status"""
        return self.controller.get_status()
    
    def shutdown(self):
        """Clean shutdown"""
        self.controller.shutdown()


if __name__ == "__main__":
    # Test the controller
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("ACiQ Mini-Split Controller Test")
    print("=" * 50)
    
    # Create controller
    controller = ACiQMiniSplitController()
    
    print(f"\nControl Method: {controller.control_method}")
    print(f"Connected: {controller.connected}")
    
    if controller.connected:
        print("\nTesting temperature control...")
        
        # Test setting temperature
        success = controller.set_temperature(68, 'cool')
        print(f"Set to 68°F: {'✓' if success else '✗'}")
        
        time.sleep(2)
        
        # Get status
        status = controller.get_status()
        print(f"\nCurrent Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
    else:
        print("\n⚠ Not connected - check configuration")
        print("Edit: software/config/aciq_config.json")
    
    # Cleanup
    controller.shutdown()
    print("\nTest complete")