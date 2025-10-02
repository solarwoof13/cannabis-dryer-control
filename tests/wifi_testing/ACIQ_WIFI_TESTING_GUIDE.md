# ACiQ Mini-Split WiFi Control Testing Guide

## 🎯 Mission Critical Security Testing Protocol

This guide provides step-by-step testing for WiFi mini-split control **before** integrating into your production cannabis drying system.

---

## ⚠️ SAFETY FIRST: Testing Rules

**DO NOT:**
- Test while the main system is running
- Connect to production network initially
- Skip any testing phases
- Store credentials in plain text
- Test with cannabis product inside

**ALWAYS:**
- Test on isolated network first
- Document all findings
- Keep IR fallback functional
- Monitor for security issues
- Have emergency stop available

---

## 📋 Pre-Testing Checklist

### Hardware Requirements
- [ ] ACiQ ACIQ-K09W-W-HP-115B (or similar model) powered on
- [ ] Raspberry Pi 4 with network access
- [ ] Mobile phone with ACiQ app installed
- [ ] Laptop for network monitoring (optional)
- [ ] Network router with admin access

### Software Requirements
```bash
# Install required packages
pip install paho-mqtt requests scapy

# For network scanning (optional)
sudo apt-get install arp-scan nmap wireshark
```

### Network Setup
- [ ] Separate test WiFi network created (recommended)
- [ ] Mini-split connected to WiFi via ACiQ app
- [ ] Router admin credentials available
- [ ] Firewall rules documented

---

## 🔬 Phase 1: Discovery & Capability Testing

### Step 1.1: Run Discovery Script

```bash
cd ~/cannabis-dryer/

# Copy test script to project directory
# (provided as test_aciq_wifi_discovery.py artifact)

# Run with sudo for best results
sudo python3 test_aciq_wifi_discovery.py
```

**Expected Output:**
- List of devices on network
- Open ports on mini-split
- Available control protocols
- Recommendations

### Step 1.2: Document Findings

Create a test report file:

```bash
# Save to repository
mkdir -p tests/aciq_testing/
cp aciq_discovery_results.json tests/aciq_testing/discovery_results_$(date +%Y%m%d).json
```

**Critical Questions to Answer:**
1. Does device have local MQTT? (Port 1883 open)
2. Does device have local HTTP API? (Port 80/8080 open)
3. What authentication is required?
4. Does it work without internet?

### Step 1.3: Network Traffic Capture (If Local API Found)

If HTTP or MQTT was detected:

```bash
# Install Wireshark if needed
sudo apt-get install wireshark

# Start packet capture
sudo wireshark &

# Filter for mini-split IP (example: 192.168.1.100)
# Apply filter: ip.addr == 192.168.1.100

# Use ACiQ app to:
# 1. Change temperature
# 2. Change mode
# 3. Turn on/off

# Save capture as: tests/aciq_testing/api_capture.pcapng
```

**Analyze Captured Traffic:**
1. Look for HTTP requests (GET/POST)
2. Identify API endpoints
3. Find authentication headers
4. Document request/response format

---

## 🔌 Phase 2: Local Control Testing

### Option A: MQTT Control (Preferred)

If Port 1883 was open in discovery:

```bash
# Test MQTT connection
mosquitto_sub -h <MINI_SPLIT_IP> -t '#' -v

# Try subscribing to common topics:
mosquitto_sub -h <MINI_SPLIT_IP> -t 'aciq/#' -v
mosquitto_sub -h <MINI_SPLIT_IP> -t 'device/#' -v
mosquitto_sub -h <MINI_SPLIT_IP> -t 'status/#' -v
```

**Test Commands:**
```bash
# Try publishing temperature command
mosquitto_pub -h <MINI_SPLIT_IP> -t 'aciq/device/command' -m '{"temperature":68,"mode":"cool"}'

# Monitor for response
mosquitto_sub -h <MINI_SPLIT_IP> -t 'aciq/device/status' -v
```

### Option B: HTTP API Control

If HTTP endpoints were found:

```python
import requests

device_ip = "192.168.1.100"  # Your device IP

# Test GET status
response = requests.get(f"http://{device_ip}/api/status", timeout=5)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

# Test POST control command
response = requests.post(
    f"http://{device_ip}/api/control",
    json={
        "temperature": 68,
        "mode": "cool",
        "fan_speed": "auto"
    },
    timeout=5
)
print(f"Command Status: {response.status_code}")
```

### Option C: Cloud API (Fallback)

If only cloud API is available:

```python
import requests

# Login to ACiQ cloud
response = requests.post(
    "https://api.aciq.com/auth/login",
    json={
        "username": "your_aciq_email@example.com",
        "password": "your_aciq_password"
    }
)

if response.status_code == 200:
    token = response.json()['token']
    print(f"Authenticated: {token[:20]}...")
    
    # Get devices
    devices = requests.get(
        "https://api.aciq.com/devices",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Devices: {devices.json()}")
```

**⚠️ Security Warning:**
- Cloud API requires internet access
- Data leaves your local network
- Third-party dependency
- Potential latency issues

---

## ⚙️ Phase 3: Integration Testing

### Step 3.1: Create Configuration File

```bash
mkdir -p ~/cannabis-dryer/software/config/
```

Create `software/config/aciq_config.json`:

```json
{
  "enabled": true,
  "control_method": "mqtt_local",
  "device_ip": "192.168.1.100",
  "device_id": "aciq_minisplit_001",
  
  "mqtt": {
    "broker": "192.168.1.100",
    "port": 1883,
    "username": "",
    "password": "",
    "topic_prefix": "aciq",
    "use_tls": false
  },
  
  "http": {
    "base_url": "http://192.168.1.100",
    "api_key": "",
    "use_https": false,
    "verify_ssl": false
  },
  
  "cloud": {
    "api_url": "https://api.aciq.com",
    "username": "",
    "password": "",
    "app_token": ""
  },
  
  "limits": {
    "temp_min": 60,
    "temp_max": 75,
    "max_commands_per_minute": 10
  },
  
  "ir_fallback": {
    "enabled": true,
    "gpio_pin": 18
  },
  
  "encrypted": false
}
```

**Update values based on your discovery results!**

### Step 3.2: Test Control Module Standalone

```bash
cd ~/cannabis-dryer/software/control/

# Copy integration module
# (provided as aciq_minisplit_control.py artifact)

# Test it standalone
python3 aciq_minisplit_control.py
```

**Expected Output:**
```
ACiQ Mini-Split Controller Test
==================================================

Initializing MQTT local control...
✓ MQTT local control initialized

Control Method: ControlMethod.MQTT_LOCAL
Connected: True

Testing temperature control...
Set to 68°F: ✓

Current Status:
  connected: True
  control_method: mqtt_local
  setpoint_f: 68.0
  actual_temp_f: 67.5
  mode: cool
  fan_speed: auto
  is_running: True
```

### Step 3.3: Measure Performance

Create a test script to measure response times:

```python
#!/usr/bin/env python3
import time
from software.control.aciq_minisplit_control import ACiQMiniSplitController

controller = ACiQMiniSplitController()

# Test latency
temperatures = [68, 69, 68, 70, 68]
latencies = []

for temp in temperatures:
    start = time.time()
    success = controller.set_temperature(temp, 'cool')
    latency = time.time() - start
    
    if success:
        latencies.append(latency)
        print(f"Set {temp}°F in {latency:.3f}s")
    
    time.sleep(6)  # Respect rate limiting

# Statistics
avg_latency = sum(latencies) / len(latencies)
max_latency = max(latencies)

print(f"\nAverage latency: {avg_latency:.3f}s")
print(f"Maximum latency: {max_latency:.3f}s")
print(f"Success rate: {len(latencies)/len(temperatures)*100:.1f}%")

controller.shutdown()
```

**Acceptable Performance:**
- Average latency: < 2 seconds (MQTT/HTTP local)
- Average latency: < 5 seconds (Cloud API)
- Success rate: > 95%
- No missed commands

---

## 🔐 Phase 4: Security Hardening

### Step 4.1: Network Isolation

**Recommended Network Architecture:**

```
Internet Router
    │
    ├─── Production VLAN (192.168.1.0/24)
    │    └─── Raspberry Pi (192.168.1.184)
    │
    └─── HVAC VLAN (192.168.2.0/24)
         ├─── Mini-Split (192.168.2.100)
         └─── Other HVAC devices
```

**Implementation:**
```bash
# On your router, create VLAN rules:
# 1. Allow Pi → Mini-Split (specific ports only)
# 2. Block Mini-Split → Internet (if using local control)
# 3. Block Mini-Split → other devices
# 4. Log all HVAC traffic
```

### Step 4.2: Firewall Rules

On the Raspberry Pi:

```bash
# Allow outgoing to mini-split only
sudo iptables -A OUTPUT -d 192.168.2.100 -p tcp --dport 1883 -j ACCEPT
sudo iptables -A OUTPUT -d 192.168.2.100 -p tcp --dport 80 -j ACCEPT

# Block all other HVAC subnet access
sudo iptables -A OUTPUT -d 192.168.2.0/24 -j DROP

# Save rules
sudo iptables-save > /etc/iptables/rules.v4
```

### Step 4.3: Credential Encryption

**Never store plain text passwords in production!**

```python
# Install cryptography
pip install cryptography

# Generate encryption key (ONE TIME)
from cryptography.fernet import Fernet
key = Fernet.generate_key()

# Save key securely (NOT in git)
with open('/home/mikejames/.aciq_key', 'wb') as f:
    f.write(key)

# Encrypt your config
import json
from cryptography.fernet import Fernet

# Load key
with open('/home/mikejames/.aciq_key', 'rb') as f:
    key = f.read()

cipher = Fernet(key)

# Encrypt sensitive fields
config = json.load(open('software/config/aciq_config.json'))
config['mqtt']['password'] = cipher.encrypt(b'your_password').decode()
config['cloud']['password'] = cipher.encrypt(b'your_cloud_pwd').decode()
config['encrypted'] = True

# Save encrypted config
with open('software/config/aciq_config.json', 'w') as f:
    json.dump(config, f, indent=2)
```

### Step 4.4: Rate Limiting

The module includes built-in rate limiting:
- Max 10 commands per minute
- Min 5 seconds between commands
- Automatic queue management

**Monitor for abuse:**
```bash
# Check logs for rate limit violations
grep "Rate limit" ~/cannabis-dryer/logs/dryer_control.log
```

### Step 4.5: Access Logging

Enable detailed access logging:

```python
# In your main system logger config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/aciq_access.log'),
        logging.StreamHandler()
    ]
)
```

**Review logs daily for:**
- Failed authentication attempts
- Unusual command patterns
- Connection drops
- Rate limit violations

---

## 🔗 Phase 5: Production Integration

### Step 5.1: Update Hardware Interface

Edit `software/control/precision_equipment_control.py`:

```python
# Add import at top of file
from software.control.aciq_minisplit_control import MiniSplitAdapter

# In PrecisionEquipmentController.__init__():

# Replace or add mini-split control
try:
    self.minisplit = MiniSplitAdapter()
    logger.info("Mini-split WiFi control initialized")
except Exception as e:
    logger.error(f"Failed to initialize mini-split WiFi: {e}")
    logger.info("Falling back to IR control")
    # Keep your existing IR control as fallback
```

### Step 5.2: Update Control Logic

In the equipment control logic, use the WiFi controller:

```python
def _apply_state(self, equipment, state):
    """Apply the desired state to equipment"""
    
    if equipment == 'mini_split':
        # Use WiFi control
        temp = self.vpd_controller.mini_split_setpoint
        mode = 'cool'  # or determine from your logic
        
        success = self.minisplit.set_temperature(temp, mode)
        
        if success:
            logger.info(f"✓ Mini-split set to {temp}°F via WiFi")
        else:
            logger.warning("WiFi control failed, check connection")
        
        return success
    
    # Existing GPIO relay logic for other equipment...
```

### Step 5.3: Add to Requirements

Update `requirements.txt`:

```bash
echo "paho-mqtt==1.6.1" >> requirements.txt
echo "cryptography==41.0.0" >> requirements.txt
```

### Step 5.4: Deployment Checklist

- [ ] All discovery tests passed
- [ ] Local control working reliably
- [ ] Performance metrics acceptable
- [ ] Security hardening complete
- [ ] Credentials encrypted
- [ ] Firewall rules configured
- [ ] Backup/fallback tested
- [ ] Logging enabled
- [ ] Team trained on new system
- [ ] Documentation updated

### Step 5.5: Gradual Rollout

**Week 1: Parallel Operation**
- Run WiFi control alongside IR
- Compare both methods
- Monitor for discrepancies
- Log all failures

**Week 2: Primary WiFi**
- Make WiFi primary control
- Keep IR as fallback
- Monitor closely
- Be ready to revert

**Week 3+: WiFi Only**
- Disable IR if WiFi stable
- Continue monitoring
- Document any issues
- Optimize as needed

---

## 🚨 Troubleshooting

### Issue: Device Not Found in Discovery

**Symptoms:**
- Network scan finds no devices
- Mini-split IP unknown

**Solutions:**
1. Check mini-split is powered on
2. Verify WiFi connection in ACiQ app
3. Check router's connected devices list
4. Try `sudo arp-scan --localnet`
5. Look for device MAC in router logs

### Issue: MQTT Connection Fails

**Symptoms:**
- Port 1883 open but can't connect
- "Connection refused" errors

**Solutions:**
1. Check MQTT broker is running: `sudo systemctl status mosquitto`
2. Verify no authentication required: `mosquitto_sub -h <IP> -t '#' -v`
3. Try different topic names
4. Check mini-split firmware version
5. Contact ACiQ support for MQTT documentation

### Issue: High Latency

**Symptoms:**
- Commands take >5 seconds
- Timeouts occur frequently

**Solutions:**
1. Check network congestion
2. Verify Pi CPU not overloaded
3. Test with WiFi analyzer for interference
4. Move router/Pi closer to mini-split
5. Reduce command frequency
6. Check for cloud API dependency

### Issue: Authentication Failures

**Symptoms:**
- 401/403 HTTP errors
- MQTT connection rejected

**Solutions:**
1. Verify credentials in config
2. Check API key is current
3. Re-authenticate with ACiQ app
4. Verify device ID matches
5. Check for IP address changes

### Issue: Commands Not Applied

**Symptoms:**
- No errors but temperature doesn't change
- Device status doesn't update

**Solutions:**
1. Check mini-split is in remote mode (not local)
2. Verify no physical controls override
3. Check temperature is within device limits
4. Ensure mini-split power is on
5. Test with ACiQ app to verify hardware

---

## 📊 Monitoring & Maintenance

### Daily Checks

```bash
# Check if mini-split is responding
python3 -c "from software.control.aciq_minisplit_control import ACiQMiniSplitController; \
c = ACiQMiniSplitController(); print(c.get_status())"

# Review access logs
tail -50 logs/aciq_access.log | grep ERROR
```

### Weekly Checks

- Review command success rate
- Check for rate limit violations
- Verify credentials still valid
- Test IR fallback manually
- Update firmware if available

### Monthly Checks

- Full security audit
- Rotate API keys/passwords
- Review network logs
- Performance benchmarking
- Backup configuration

---

## 📝 Testing Log Template

Use this template to document your testing:

```markdown
# ACiQ WiFi Testing Log

## Test Date: YYYY-MM-DD
## Tester: Your Name

### Discovery Phase
- [ ] Network scan completed
- [ ] Device found at IP: _______________
- [ ] Open ports detected: _______________
- [ ] Control method available: _______________

### Capability Testing
- [ ] MQTT tested: PASS / FAIL
- [ ] HTTP API tested: PASS / FAIL
- [ ] Cloud API tested: PASS / FAIL
- [ ] Average latency: _______________ seconds
- [ ] Success rate: _______________ %

### Security Testing
- [ ] Network isolation configured
- [ ] Firewall rules applied
- [ ] Credentials encrypted
- [ ] Access logging enabled
- [ ] Rate limiting verified

### Integration Testing
- [ ] Config file created
- [ ] Module tested standalone
- [ ] Integrated with main system
- [ ] Parallel operation successful
- [ ] IR fallback tested

### Production Readiness
- [ ] All tests passed
- [ ] Documentation complete
- [ ] Team trained
- [ ] Rollback plan ready
- [ ] Approved for deployment

### Notes:
[Add any additional observations or issues here]

### Recommendations:
[List any improvements or concerns]
```

---

## 🎓 Best Practices Summary

1. **Always test on isolated network first**
2. **Keep IR fallback functional**
3. **Never store credentials in plain text**
4. **Monitor logs regularly**
5. **Use rate limiting**
6. **Implement network isolation**
7. **Document everything**
8. **Have emergency procedures ready**
9. **Test backup systems**
10. **Keep firmware updated**

---

## 📞 Support Resources

### If Local Control Not Possible

If discovery shows only cloud API available:

1. **Contact ACiQ Support:**
   - Ask about local API documentation
   - Request MQTT broker credentials
   - Inquire about API SDK

2. **Alternative Solutions:**
   - Use cloud API with internet failover
   - Keep IR control as primary
   - Consider different mini-split model

3. **Community Resources:**
   - Home Assistant forums
   - Reddit r/homeautomation
   - GitHub smart home projects

### Emergency Contacts

- **System Admin:** [Your contact]
- **Network Admin:** [Your contact]
- **ACiQ Support:** [ACiQ contact info]
- **Integration Developer:** [Developer contact]

---

## ✅ Final Pre-Production Checklist

Before deploying to production with cannabis product:

- [ ] All 5 testing phases completed successfully
- [ ] Security audit passed
- [ ] Performance meets requirements (< 2s latency, >95% success)
- [ ] Backup systems tested and ready
- [ ] Team trained on new system
- [ ] Emergency procedures documented
- [ ] Network monitoring configured
- [ ] Credentials secured and backed up
- [ ] Configuration backed up to GitHub
- [ ] Rollback plan tested
- [ ] Insurance/compliance reviewed
- [ ] Final approval from stakeholders

---

**Document Version:** 1.0  
**Last Updated:** $(date)  
**Next Review:** [3 months from deployment]  

**REMEMBER: Security and reliability are MISSION CRITICAL for the cannabis industry. Never skip testing phases!**