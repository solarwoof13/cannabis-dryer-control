# IR Testing - Complete Guide

Standalone testing for IR modules before cannabis dryer integration.

---

## 🎯 Goal

Test IR receiver and transmitter modules **independently** before integrating with main system.

---

## 📁 Files in This Directory

```
tests/ir_testing/
├── test_ir_receiver.py          ← Receiver test
├── test_ir_transmitter.py       ← Transmitter test
├── IR_WIRING_GUIDE.md           ← Detailed wiring
├── VISUAL_WIRING_DIAGRAM.txt    ← Quick reference
├── IR_TESTING_README.md         ← This file
└── setup_ir_tests.sh            ← Setup script
```

---

## 🔌 Quick Wiring Reference

### IR Receiver → Raspberry Pi
- VCC → Pin 1 (3.3V)
- GND → Pin 6 (GND)
- DAT → Pin 12 (GPIO 18)

### IR Transmitter → Raspberry Pi
- VCC → Pin 2 (5V)
- GND → Pin 9 (GND)
- DAT → Pin 36 (GPIO 16) ⚠️ **Not GPIO 17!**

---

## 🚀 Quick Start

### 1. Create Files in VS Code

```bash
cd ~/cannabis-dryer
mkdir -p tests/ir_testing
cd tests/ir_testing

# Create all 6 files and copy content
```

### 2. Wire Modules

Follow **VISUAL_WIRING_DIAGRAM.txt** for exact connections.

**Double-check:** Transmitter goes to Pin 36 (GPIO 16), not Pin 11!

### 3. Test Receiver

```bash
python3 test_ir_receiver.py
```

**Expected:**
- Script starts
- Point any TV remote at receiver
- Press buttons
- See HIGH/LOW pulses printed
- "IR RECEIVER IS WORKING!" message

### 4. Test Transmitter

```bash
python3 test_ir_transmitter.py
```

**Expected:**
- Script starts
- Choose test mode (1 or 2)
- Pulses sent
- Verify with phone camera (see purple flash)

---

## ✅ Success Criteria

**Both tests must pass before proceeding!**

| Test | Pass Criteria |
|------|---------------|
| Receiver | Detects remote button presses, prints pulses |
| Transmitter | Visible on phone camera, receiver detects it |

---

## 🔍 Troubleshooting

### Receiver Issues

**No pulses detected:**
1. Check module LED blinks when remote pressed
2. Verify Pin 12 connection (GPIO 18)
3. Check 3.3V at Pin 1
4. Try different remote control
5. Check batteries in remote

**GPIO permission error:**
```bash
sudo python3 test_ir_receiver.py
```

### Transmitter Issues

**No flash on camera:**
1. Check module LED lights during test
2. Verify Pin 36 connection (GPIO 16)
3. Check 5V at Pin 2
4. Point camera directly at IR LED

**Wrong pin?**
- Ensure DAT goes to Pin 36 (physical), NOT Pin 11
- GPIO 16, not GPIO 17!

---

## ⏭️ Next Steps

**After Both Tests Pass:**

1. ✅ Hardware validated
2. ⏭️ Install LIRC: `sudo apt-get install lirc`
3. ⏭️ Learn AC remote codes with `irrecord`
4. ⏭️ Create AC control module
5. ⏭️ Integrate with main system

**DO NOT integrate until tests pass!**

---

## 🚫 Important Notes

- These tests are **completely separate** from main system
- Safe to run while main system is stopped
- Do NOT run simultaneously with main system (GPIO conflicts)
- GPIO 16 chosen specifically to avoid GPIO 17 (dehum fan)

---

## 📞 Help

**Before asking:**
1. Run both test scripts
2. Share terminal output
3. Photo of wiring
4. Confirm Pin 36 for transmitter

**Common fixes:**
- Wrong pin number (Pin 36 vs Pin 11)
- Loose connections
- Need sudo for GPIO access
- Main system still running

---

## 📊 Test Results

Record your results:

```
[ ] Receiver test passes
[ ] Transmitter test passes
[ ] Receiver detects transmitter
[ ] No GPIO errors
[ ] Ready for LIRC setup
```

---

Good luck! Test methodically and don't rush integration. 🚀