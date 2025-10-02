#!/usr/bin/env python3
"""
ACiQ Mini-Split WiFi Discovery & Testing Script
================================================
STANDALONE TEST - Does NOT interfere with main system

Run this FIRST to determine if WiFi control is possible
before integrating into the main cannabis dryer control system.

Security Features:
- Local network scanning only
- No credentials stored
- Network isolation testing
- API endpoint discovery

Author: Cannabis Dryer Control System
Version: 1.0
"""

import socket
import subprocess
import requests
import json
import time
import sys
from datetime import datetime

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


class ACiQDiscovery:
    """Discover and test ACiQ mini-split WiFi capabilities"""
    
    def __init__(self):
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'device_found': False,
            'device_ip': None,
            'open_ports': [],
            'local_api': False,
            'cloud_required': None,
            'mqtt_available': False,
            'http_endpoints': [],
            'recommendations': []
        }
    
    def get_local_network_range(self):
        """Get local network range for scanning"""
        try:
            # Get local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            # Convert to network range (assumes /24)
            network_parts = local_ip.rsplit('.', 1)
            network_range = f"{network_parts[0]}.0/24"
            
            print_info(f"Your local IP: {local_ip}")
            print_info(f"Scanning network: {network_range}")
            return network_range
        except Exception as e:
            print_error(f"Failed to determine network range: {e}")
            return None
    
    def scan_network_for_devices(self, network_range):
        """
        Scan network for potential ACiQ devices
        Uses arp-scan (if available) or manual ping sweep
        """
        print_header("PHASE 1: Network Device Discovery")
        
        devices = []
        
        # Try arp-scan first (requires sudo)
        try:
            print_info("Attempting fast scan with arp-scan...")
            result = subprocess.run(
                ['sudo', 'arp-scan', '--localnet'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print_success("arp-scan completed")
                # Parse arp-scan output
                for line in result.stdout.split('\n'):
                    if '\t' in line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            ip = parts[0].strip()
                            mac = parts[1].strip()
                            vendor = parts[2].strip() if len(parts) > 2 else "Unknown"
                            
                            # Look for potential IoT device indicators
                            if any(keyword in vendor.lower() for keyword in 
                                   ['aciq', 'gree', 'midea', 'espressif', 'realtek']):
                                devices.append({'ip': ip, 'mac': mac, 'vendor': vendor})
                                print_success(f"Found potential device: {ip} ({vendor})")
            else:
                print_warning("arp-scan failed, falling back to manual scan")
        
        except FileNotFoundError:
            print_warning("arp-scan not installed")
            print_info("Install with: sudo apt-get install arp-scan")
        except subprocess.TimeoutExpired:
            print_warning("arp-scan timed out")
        except Exception as e:
            print_warning(f"arp-scan error: {e}")
        
        # Fallback: Manual network scan
        if not devices:
            print_info("Performing manual network scan (this may take a few minutes)...")
            network_base = network_range.split('/')[0].rsplit('.', 1)[0]
            
            for i in range(1, 255):
                ip = f"{network_base}.{i}"
                
                # Quick ping test with short timeout
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', ip],
                    capture_output=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    devices.append({'ip': ip, 'mac': 'unknown', 'vendor': 'unknown'})
                    print(f"  Found active device: {ip}")
                    
                # Progress indicator
                if i % 50 == 0:
                    print(f"  Scanned {i}/254 addresses...")
        
        print_info(f"Found {len(devices)} active devices on network")
        return devices
    
    def test_device_ports(self, ip_address):
        """Test common IoT and HVAC control ports"""
        print_header(f"PHASE 2: Port Scanning {ip_address}")
        
        # Common ports for IoT HVAC systems
        test_ports = {
            80: 'HTTP',
            443: 'HTTPS',
            8080: 'HTTP Alt',
            8081: 'HTTP Alt 2',
            8443: 'HTTPS Alt',
            1883: 'MQTT',
            8883: 'MQTT SSL',
            5000: 'API',
            6668: 'Proprietary',
            7000: 'Control',
            502: 'Modbus TCP'
        }
        
        open_ports = []
        
        for port, service in test_ports.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip_address, port))
            
            if result == 0:
                open_ports.append({'port': port, 'service': service})
                print_success(f"Port {port} OPEN ({service})")
            else:
                print(f"  Port {port} closed ({service})")
            
            sock.close()
        
        self.test_results['open_ports'] = open_ports
        return open_ports
    
    def test_http_endpoints(self, ip_address, open_ports):
        """Test HTTP/HTTPS endpoints for API discovery"""
        print_header("PHASE 3: HTTP API Discovery")
        
        http_ports = [p['port'] for p in open_ports if p['port'] in [80, 443, 8080, 8081, 8443]]
        
        if not http_ports:
            print_warning("No HTTP ports found - device may require cloud API")
            return []
        
        endpoints_found = []
        
        # Common API endpoints for smart home devices
        test_paths = [
            '/',
            '/api',
            '/api/status',
            '/api/device',
            '/api/v1',
            '/status',
            '/device',
            '/local',
            '/control'
        ]
        
        for port in http_ports:
            protocol = 'https' if port in [443, 8443] else 'http'
            base_url = f"{protocol}://{ip_address}:{port}"
            
            print_info(f"Testing {base_url}...")
            
            for path in test_paths:
                url = f"{base_url}{path}"
                
                try:
                    response = requests.get(
                        url,
                        timeout=3,
                        verify=False  # Ignore SSL cert warnings for local devices
                    )
                    
                    if response.status_code in [200, 401, 403]:
                        endpoints_found.append({
                            'url': url,
                            'status': response.status_code,
                            'content_type': response.headers.get('Content-Type', 'unknown')
                        })
                        print_success(f"Endpoint found: {url} (Status: {response.status_code})")
                        
                        # Try to parse JSON response
                        try:
                            data = response.json()
                            print_info(f"  Response preview: {str(data)[:100]}...")
                        except:
                            pass
                
                except requests.exceptions.Timeout:
                    pass
                except requests.exceptions.ConnectionError:
                    pass
                except Exception as e:
                    pass
        
        self.test_results['http_endpoints'] = endpoints_found
        return endpoints_found
    
    def test_mqtt_broker(self, ip_address):
        """Test if device has MQTT broker running"""
        print_header("PHASE 4: MQTT Broker Detection")
        
        try:
            import paho.mqtt.client as mqtt
            
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    print_success(f"MQTT broker detected at {ip_address}")
                    self.test_results['mqtt_available'] = True
                else:
                    print_warning(f"MQTT connection failed with code: {rc}")
            
            client = mqtt.Client()
            client.on_connect = on_connect
            
            try:
                client.connect(ip_address, 1883, 10)
                client.loop_start()
                time.sleep(3)
                client.loop_stop()
                client.disconnect()
            except Exception as e:
                print_warning(f"MQTT not available: {e}")
                self.test_results['mqtt_available'] = False
        
        except ImportError:
            print_warning("paho-mqtt not installed")
            print_info("Install with: pip install paho-mqtt")
            self.test_results['mqtt_available'] = False
    
    def analyze_results(self):
        """Analyze test results and provide recommendations"""
        print_header("PHASE 5: Analysis & Recommendations")
        
        if not self.test_results['device_found']:
            print_error("ACiQ device not found on network")
            print_info("Recommendations:")
            print("  1. Ensure mini-split is powered on")
            print("  2. Complete WiFi setup using ACiQ mobile app")
            print("  3. Verify device is on same network as Pi")
            print("  4. Check router for connected devices")
            return
        
        print_success(f"Device found at: {self.test_results['device_ip']}")
        print()
        
        # Determine control method
        if self.test_results['mqtt_available']:
            print_success("RECOMMENDED: MQTT Local Control")
            print_info("Your ACiQ supports local MQTT - this is the BEST option!")
            print_info("Benefits:")
            print("  ✓ No cloud dependency")
            print("  ✓ <100ms latency")
            print("  ✓ Works offline")
            print("  ✓ More secure")
            self.test_results['recommendations'].append('mqtt_local')
        
        elif self.test_results['http_endpoints']:
            print_success("VIABLE: HTTP Local API")
            print_info("Device has local HTTP endpoints")
            print_info("Next steps:")
            print("  1. Capture API traffic with Wireshark")
            print("  2. Reverse engineer authentication")
            print("  3. Implement HTTP control module")
            self.test_results['recommendations'].append('http_local')
        
        elif self.test_results['open_ports']:
            print_warning("Device found but protocol unclear")
            print_info("Detected open ports: " + ", ".join([str(p['port']) for p in self.test_results['open_ports']]))
            print_info("Recommendations:")
            print("  1. Check ACiQ app for local control toggle")
            print("  2. Update mini-split firmware")
            print("  3. Consider cloud API as fallback")
            self.test_results['recommendations'].append('further_investigation')
        
        else:
            print_warning("No local control protocols detected")
            print_info("Device likely requires cloud API")
            print_info("Options:")
            print("  1. Use ACiQ cloud API (requires internet)")
            print("  2. Keep existing IR control")
            print("  3. Contact ACiQ for local API documentation")
            self.test_results['recommendations'].append('cloud_api')
        
        # Security recommendations
        print()
        print_info("Security Recommendations:")
        if self.test_results['mqtt_available']:
            print("  • Change default MQTT credentials")
            print("  • Enable MQTT authentication")
            print("  • Use TLS for MQTT connections")
        if self.test_results['http_endpoints']:
            print("  • Implement API key authentication")
            print("  • Use HTTPS where available")
        print("  • Isolate HVAC devices on separate VLAN")
        print("  • Disable internet access for mini-split if using local control")
        print("  • Monitor for unauthorized access attempts")
    
    def save_results(self, filename='aciq_discovery_results.json'):
        """Save test results to file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.test_results, f, indent=2)
            print_success(f"Results saved to: {filename}")
        except Exception as e:
            print_error(f"Failed to save results: {e}")
    
    def run_full_discovery(self):
        """Run complete discovery process"""
        print_header("ACiQ Mini-Split WiFi Discovery")
        print_info("This script will:")
        print("  1. Scan your local network for devices")
        print("  2. Test network ports and protocols")
        print("  3. Determine if WiFi control is possible")
        print("  4. Provide integration recommendations")
        print()
        print_warning("This is a STANDALONE test - safe to run")
        print()
        
        input("Press Enter to begin discovery...")
        
        # Phase 1: Network scan
        network_range = self.get_local_network_range()
        if not network_range:
            print_error("Cannot determine network range")
            return
        
        devices = self.scan_network_for_devices(network_range)
        
        if not devices:
            print_error("No devices found on network")
            return
        
        # Let user select device to test
        print()
        print_info("Select a device to test:")
        for idx, device in enumerate(devices, 1):
            print(f"  {idx}. {device['ip']} - {device.get('vendor', 'Unknown')}")
        
        try:
            choice = int(input("\nEnter device number: ")) - 1
            if 0 <= choice < len(devices):
                selected_device = devices[choice]
                self.test_results['device_found'] = True
                self.test_results['device_ip'] = selected_device['ip']
            else:
                print_error("Invalid selection")
                return
        except ValueError:
            print_error("Invalid input")
            return
        
        # Phase 2-4: Test selected device
        ip = selected_device['ip']
        open_ports = self.test_device_ports(ip)
        
        if open_ports:
            self.test_http_endpoints(ip, open_ports)
            self.test_mqtt_broker(ip)
        
        # Phase 5: Analysis
        self.analyze_results()
        
        # Save results
        print()
        self.save_results()
        
        print()
        print_header("Discovery Complete")
        print_info("Next steps:")
        print("  1. Review aciq_discovery_results.json")
        print("  2. If local control found, implement integration module")
        print("  3. If cloud API required, capture app traffic with Wireshark")
        print("  4. Share results with development team")


def main():
    """Main entry point"""
    try:
        discovery = ACiQDiscovery()
        discovery.run_full_discovery()
    except KeyboardInterrupt:
        print()
        print_warning("Discovery interrupted by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Check if running as root (needed for arp-scan)
    if subprocess.run(['id', '-u'], capture_output=True).stdout.decode().strip() != '0':
        print_warning("Not running as root - some features may not work")
        print_info("For best results, run with: sudo python3 test_aciq_wifi_discovery.py")
        print()
        proceed = input("Continue anyway? (y/n): ")
        if proceed.lower() != 'y':
            sys.exit(0)
    
    main()