# IR Receiver & Transmitter Wiring Guide
## DORHEA 38kHz IR Modules - Complete Instructions

---

## 📦 Your Modules

**DORHEA Digital 38kHz IR Receiver and Transmitter**

### IR Receiver Specs:
- Working voltage: 5V (but works at 3.3V)
- Receiver chip: 1838
- Has indicator LED
- Pins: **DAT, VCC, GND**

### IR Transmitter Specs:
- Supply voltage: 5V (required)
- Wavelength: 940nm
- Range: ~1.3 meters
- Pins: **DAT, VCC, GND**

---

## 🔌 Wiring Instructions

### IR RECEIVER Wiring (Try 3.3V First)

```
IR Receiver Module          Raspberry Pi 4
==================          ===============
VCC -----------------------> Pin 1 (3.3V)    ← Try this first!
GND -----------------------> Pin 6 (GND)
DAT -----------------------> Pin 12 (GPIO 18)
```

**If 3.3V doesn't work well, use 5V with voltage divider** (see below)

---

### IR TRANSMITTER Wiring

```
IR Transmitter Module       Raspberry Pi 4
=====================       ===============
VCC -----------------------> Pin 2 (5V)      ← Must use 5V
GND -----------------------> Pin 9 (GND)
DAT -----------------------> Pin 36 (GPIO 16) ← Using GPIO 16, not 17!
```

**Note:** GPIO 17 is already used by dehum fan in your main system.

---

## 📍 Pin Map Visual

```
Raspberry Pi GPIO Header:
    
    Pin 1  (3.3V)   [VCC-RX] [ ] Pin 2  (5V) [VCC-TX]
    Pin 3           [ ] [ ] Pin 4
    Pin 5           [ ] [GND-RX] Pin 6
    Pin 7           [ ] [ ] Pin 8
    Pin 9  (GND)    [GND-TX] [ ] Pin 10
    Pin 11          [ ] [DAT-RX] Pin 12 (GPIO 18)
    Pin 13          [ ] [ ] Pin 14
    ...
    Pin 35          [ ] [DAT-TX] Pin 36 (GPIO 16)
```

---

## 🛡️ Voltage Divider (Only if 3.3V doesn't work)

If receiver doesn't work at 3.3V, use 5V with voltage divider:

### Required Parts:
- 1x 2kΩ resistor
- 1x 1kΩ resistor
- Small breadboard

### Circuit:

```
Receiver DAT → [2kΩ] → [Junction] → GPIO 18
                           |
                        [1kΩ]
                           |
                         GND
```

This divides 5V down to ~1.67V (safe for Pi)

---

## ⚡ Quick Reference

| Module | Pin | Wire To | GPIO | Notes |
|--------|-----|---------|------|-------|
| **Receiver** | VCC | Pin 1 | - | 3.3V (try first) |
| Receiver | GND | Pin 6 | - | Ground |
| Receiver | DAT | Pin 12 | GPIO 18 | Input signal |
| **Transmitter** | VCC | Pin 2 | - | 5V required |
| Transmitter | GND | Pin 9 | - | Ground |
| Transmitter | DAT | Pin 36 | **GPIO 16** | Output signal |

---

## ⚠️ Safety Checks

Before powering on:

- [ ] Receiver VCC to Pin 1 (3.3V) or Pin 2 (5V with divider)
- [ ] Receiver GND to Pin 6
- [ ] Receiver DAT to Pin 12
- [ ] Transmitter VCC to Pin 2 (5V)
- [ ] Transmitter GND to Pin 9
- [ ] Transmitter DAT to Pin 36 (GPIO 16)
- [ ] No wires touching other pins
- [ ] All connections secure

---

## 🧪 Testing

Once wired:

```bash
cd ~/cannabis-dryer/tests/ir_testing

# Test receiver
python3 test_ir_receiver.py

# Test transmitter (new terminal)
python3 test_ir_transmitter.py
```

---

## 🔍 Troubleshooting

**Receiver not detecting:**
- Check if LED on module blinks when remote pressed
- Verify Pin 12 connection
- Try different remote
- Check power at VCC pin

**Transmitter not working:**
- Check module LED lights during test
- View through phone camera (should see purple flash)
- Verify 5V at VCC pin
- Check Pin 36 connection

**GPIO errors:**
- Run with `sudo`
- Or: `sudo usermod -a -G gpio pi` (then logout/login)

---

Ready to test! 🚀