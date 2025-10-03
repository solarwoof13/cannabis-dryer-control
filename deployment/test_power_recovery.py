#!/usr/bin/env python3
"""Test Power Loss Recovery"""
import json
import time
import requests
from datetime import datetime

BASE = "http://localhost:5000"

def get_status():
    try:
        r = requests.get(f"{BASE}/api/status", timeout=5)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def read_state():
    try:
        with open('data/system_state.json', 'r') as f:
            return json.load(f)
    except:
        return None

print("\n" + "="*60)
print("Power Loss Recovery Test")
print("="*60)

# Start process
print("\n1. Starting process...")
try:
    r = requests.post(f"{BASE}/api/process/start")
    if r.status_code == 200:
        print("✓ Started")
    else:
        print("✗ Failed")
        exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)

# Wait
print("\n2. Running for 30 seconds...")
for i in range(30, 0, -5):
    s = get_status()
    if s:
        print(f"  {i}s | Phase: {s.get('current_phase', '?')}")
    time.sleep(5)

# Save state
print("\n3. Recording state...")
before = read_state()
if before:
    print(f"✓ Active: {before.get('process_active')}")
    print(f"  Phase: {before.get('current_phase')}")
else:
    print("✗ Can't read state")
    exit(1)

# Instruct user
print("\n4. STOP AND RESTART SERVICE NOW:")
print("   sudo systemctl stop cannabis-dryer")
print("   sudo systemctl start cannabis-dryer")
input("\nPress Enter after restarting...")

# Wait for recovery
print("\n5. Waiting for recovery...")
for i in range(30):
    time.sleep(2)
    if get_status():
        print(f"✓ Online after {i*2}s")
        break
else:
    print("✗ Not responding")
    exit(1)

# Verify
time.sleep(3)
print("\n6. Verifying...")
after = read_state()

if after:
    passed = 0
    if after.get('process_active') == before.get('process_active'):
        print("✓ Process state preserved")
        passed += 1
    if after.get('current_phase') == before.get('current_phase'):
        print("✓ Phase preserved")
        passed += 1
    if after.get('process_start_time') == before.get('process_start_time'):
        print("✓ Start time preserved")
        passed += 1
    
    print(f"\nResult: {passed}/3 checks passed")
    if passed == 3:
        print("\n✓✓✓ RECOVERY TEST PASSED ✓✓✓")
    else:
        print("\n⚠ Some checks failed")
else:
    print("✗ Can't verify")

print("\n" + "="*60)