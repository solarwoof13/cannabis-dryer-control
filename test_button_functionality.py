#!/usr/bin/env python3
"""
Test script to verify button functionality and state transitions
"""

import requests
import time
import json

BASE_URL = 'http://localhost:5000'

def test_button_sequence():
    """Test the complete button sequence: start -> emergency stop -> resume -> hold -> resume"""

    print("="*60)
    print("Testing Button Functionality and State Transitions")
    print("="*60)

    try:
        # Step 1: Check initial status
        print("\n1. Checking initial status...")
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"Initial state: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
        else:
            print(f"Failed to get status: {response.status_code}")
            return

        # Step 2: Start process
        print("\n2. Starting process...")
        response = requests.post(f"{BASE_URL}/api/session/start")
        if response.status_code == 200:
            result = response.json()
            print(f"Start result: {result}")
        else:
            print(f"Failed to start: {response.status_code} - {response.text}")
            return

        time.sleep(2)

        # Step 3: Check status after start
        print("\n3. Checking status after start...")
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"After start: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
        else:
            print(f"Failed to get status: {response.status_code}")

        time.sleep(5)  # Let it run for a bit

        # Step 4: Emergency stop
        print("\n4. Triggering emergency stop...")
        response = requests.post(f"{BASE_URL}/api/emergency-stop")
        if response.status_code == 200:
            result = response.json()
            print(f"Emergency stop result: {result}")
        else:
            print(f"Failed emergency stop: {response.status_code} - {response.text}")

        time.sleep(2)

        # Step 5: Check status after emergency stop
        print("\n5. Checking status after emergency stop...")
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"After emergency: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
        else:
            print(f"Failed to get status: {response.status_code}")

        # Step 6: Resume from emergency
        print("\n6. Resuming from emergency...")
        response = requests.post(f"{BASE_URL}/api/process/start",
                               json={'resume_from_emergency': True})
        if response.status_code == 200:
            result = response.json()
            print(f"Resume result: {result}")
        else:
            print(f"Failed to resume: {response.status_code} - {response.text}")

        time.sleep(2)

        # Step 7: Check status after resume
        print("\n7. Checking status after resume...")
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"After resume: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
        else:
            print(f"Failed to get status: {response.status_code}")

        time.sleep(5)  # Let it run

        # Step 8: Hold process
        print("\n8. Putting process on hold...")
        response = requests.post(f"{BASE_URL}/api/process/hold")
        if response.status_code == 200:
            result = response.json()
            print(f"Hold result: {result}")
        else:
            print(f"Failed to hold: {response.status_code} - {response.text}")

        time.sleep(2)

        # Step 9: Check status after hold
        print("\n9. Checking status after hold...")
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"After hold: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
        else:
            print(f"Failed to get status: {response.status_code}")

        # Step 10: Resume from hold
        print("\n10. Resuming from hold...")
        response = requests.post(f"{BASE_URL}/api/process/start",
                               json={'resume_from_hold': True})
        if response.status_code == 200:
            result = response.json()
            print(f"Resume from hold result: {result}")
        else:
            print(f"Failed to resume from hold: {response.status_code} - {response.text}")

        time.sleep(2)

        # Step 11: Final status check
        print("\n11. Final status check...")
        response = requests.get(f"{BASE_URL}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"Final state: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
        else:
            print(f"Failed to get status: {response.status_code}")

        # Step 12: Check equipment debug info
        print("\n12. Checking equipment debug info...")
        response = requests.get(f"{BASE_URL}/api/debug/equipment")
        if response.status_code == 200:
            debug = response.json()
            print(f"Equipment states: {json.dumps(debug, indent=2)}")
        else:
            print(f"Failed to get equipment debug: {response.status_code}")

        print("\n" + "="*60)
        print("Button functionality test complete!")
        print("="*60)

    except Exception as e:
        print(f"Test failed with error: {e}")

if __name__ == '__main__':
    test_button_sequence()