import socket
import requests
from scapy.all import ARP, Ether, srp

def find_aciq_on_network(network_range="192.168.1.0/24"):
    """
    Scan network for ACiQ device
    """
    print("[*] Scanning network for ACiQ mini-split...")
    
    # Create ARP packet
    arp = ARP(pdst=network_range)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether/arp
    
    result = srp(packet, timeout=3, verbose=0)[0]
    
    devices = []
    for sent, received in result:
        devices.append({'ip': received.psrc, 'mac': received.hwsrc})
    
    return devices

def test_local_api(ip_address):
    """
    Test if device has local API endpoints
    Common IoT device ports: 80, 443, 8080, 6668, 1883 (MQTT)
    """
    common_ports = [80, 443, 8080, 6668, 1883]
    open_ports = []
    
    for port in common_ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip_address, port))
        if result == 0:
            open_ports.append(port)
            print(f"[+] Port {port} is OPEN on {ip_address}")
        sock.close()
    
    return open_ports

if __name__ == "__main__":
    devices = find_aciq_on_network()
    print(f"\n[*] Found {len(devices)} devices on network")
    
    # Test each device
    for device in devices:
        print(f"\n[*] Testing {device['ip']} ({device['mac']})")
        open_ports = test_local_api(device['ip'])