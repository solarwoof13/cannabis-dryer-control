# Cannabis Dryer Control System - Wiring Diagram

## Equipment Connections

### GPIO Pin Assignments (Raspberry Pi 4)

| GPIO Pin | Equipment | Relay Type | Wire Color | Notes |
|----------|-----------|------------|------------|-------|
| GPIO 17 | Dehumidifier | Power Relay (120V) | Red | High current |
| GPIO 27 | Humidifier Solenoid | Control Relay (24V) | Blue | Water valve |
| GPIO 22 | ERV | Control Relay | Green | Energy Recovery Ventilator |
| GPIO 23 | Supply Fan | Power Relay (120V) | Yellow | 400 CFM |
| GPIO 24 | Return Fan | Power Relay (120V) | Orange | 400 CFM |

### GPIO Control Logic
- **Active LOW**: Relay activates when GPIO goes LOW (0V)
- **Default HIGH**: Initialize all GPIOs as HIGH (3.3V) = OFF
- This is fail-safe: if Pi crashes, all relays turn OFF

## I2C Sensor Network (SparkFun Qwiic)

| Sensor Location | I2C Address | Cable Length | Notes |
|-----------------|-------------|--------------|-------|
| Dry Zone 1 | 0x38 | ~20ft | Front left of container |
| Dry Zone 2 | 0x39 | ~25ft | Front right of container |
| Dry Zone 3 | 0x3A | ~30ft | Back left of container |
| Dry Zone 4 | 0x3B | ~35ft | Back right of container |
| Air Room | 0x3C | ~5ft | Equipment room |
| Supply Duct | 0x3D | ~10ft | After all conditioning |

### I2C Bus Wiring
- **SDA**: Pin 3 (GPIO 2) - Data line
- **SCL**: Pin 5 (GPIO 3) - Clock line
- **VCC**: Pin 1 (3.3V)
- **GND**: Pin 9 (Ground)

## Relay Board: SunFounder 8-Channel Relay Shield

### Relay Channel Assignments

| Channel | GPIO Pin | Equipment | Voltage | Control Type | Notes |
|---------|----------|-----------|---------|--------------|-------|
| IN1 | GPIO 17 | Dehumidifier | 120V AC | Power ON/OFF | High current device |
| IN2 | GPIO 27 | Humidifier Solenoid | 24V DC | Control | Water valve control |
| IN3 | GPIO 22 | ERV | 120V AC | Power ON/OFF | Energy Recovery Ventilator |
| IN4 | GPIO 23 | Supply Fan | 120V AC | Power ON/OFF | 400 CFM fan |
| IN5 | GPIO 24 | Return Fan | 120V AC | Power ON/OFF | 400 CFM fan |
| IN6 | GPIO 25 | Humidifier Fan | 12-24V DC | Control | Low voltage fan |
| IN7 | - | Spare | - | - | Future use |
| IN8 | - | Spare | - | - | Future use |

### Relay Board Power Configuration
- **JD-VCC**: Connect to separate 5V power supply (NOT from Pi)
- **VCC**: Connect to Pi's 5V (powers optocouplers only)
- **GND**: Connect to Pi's GND AND external supply GND (common ground)
- **Remove JD-VCC jumper** to isolate Pi from relay coils

### Wiring Safety Notes
⚠️ **CRITICAL**: This relay board is rated for:
- Max 10A at 250VAC per channel
- Max 10A at 30VDC per channel
- Your 120V devices should not exceed 10A each

⚠️ **Power Isolation**: 
- Remove the JD-VCC jumper to isolate Pi from high voltage
- Use separate 5V 2A+ supply for JD-VCC
- This prevents high voltage issues from damaging the Pi


### Power Requirements
- Raspberry Pi: 5V 3A USB-C
- Relay Board: 5V via GPIO or separate supply
- Sensors: 3.3V from Pi (via Qwiic bus)

### Mini-Split IR Control
- **Option 1**: IR LED on GPIO pin (not yet assigned)
- **Option 2**: Arduino Uno with IR shield (Serial to Pi)
- **Option 3**: USB IR Blaster

## Safety Notes
⚠️ **WARNING**: 120V equipment must use proper rated relays
⚠️ Always use proper fuses/breakers for high voltage lines
⚠️ Ensure proper grounding of all equipment
⚠️ Keep low voltage (GPIO/I2C) separated from high voltage wiring

## Container Layout