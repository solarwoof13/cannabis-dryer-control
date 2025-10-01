#!/usr/bin/env python3
"""
Test script to verify emergency stop -> hold -> start sequence
"""
import requests
import time
import json

BASE_URL = "http://localhost:5000"

def test_sequence():
    print("Testing Emergency Stop -> Hold -> Start sequence...")

    # Step 1: Start a process
    print("\n1. Starting a process...")
    try:
        response = requests.post(f"{BASE_URL}/api/process/start", json={})
        print(f"Start response: {response.status_code}")
    except Exception as e:
        print(f"Error starting process: {e}")
        return

    time.sleep(3)  # Wait for status update

    # Check status
    response = requests.get(f"{BASE_URL}/api/status")
    status = response.json()
    print(f"After start: cycle_state={status.get('cycle_state')}")

    # Step 2: Emergency stop
    print("\n2. Triggering emergency stop...")
    try:
        response = requests.post(f"{BASE_URL}/api/emergency-stop")
        print(f"Emergency stop response: {response.status_code}")
    except Exception as e:
        print(f"Error emergency stop: {e}")
        return

    time.sleep(3)

    # Check status
    response = requests.get(f"{BASE_URL}/api/status")
    status = response.json()
    print(f"After emergency: cycle_state={status.get('cycle_state')}")

    # Step 3: Go to hold from emergency
    print("\n3. Switching to hold mode from emergency...")
    try:
        response = requests.post(f"{BASE_URL}/api/process/hold")
        print(f"Hold response: {response.status_code}")
    except Exception as e:
        print(f"Error switching to hold: {e}")
        return

    time.sleep(3)

    # Check status
    response = requests.get(f"{BASE_URL}/api/status")
    status = response.json()
    print(f"After hold: cycle_state={status.get('cycle_state')}, process_active={status.get('process_active', 'N/A')}")

    # Step 4: Try to start from hold
    print("\n4. Attempting to start from hold mode...")
    try:
        response = requests.post(f"{BASE_URL}/api/process/start", json={"resume_from_hold": True})
        print(f"Resume from hold response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Resume result: {result}")
        else:
            print(f"Resume failed: {response.text}")
    except Exception as e:
        print(f"Error resuming from hold: {e}")
        return

    time.sleep(3)

    # Check final status
    response = requests.get(f"{BASE_URL}/api/status")
    status = response.json()
    print(f"After resume: cycle_state={status.get('cycle_state')}, process_active={status.get('process_active', 'N/A')}")

    print("\nTest completed!")

if __name__ == "__main__":
    test_sequence()