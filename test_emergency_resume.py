#!/usr/bin/env python3
"""
Test script to verify emergency stop and resume functionality
"""
import requests
import time
import json

BASE_URL = "http://localhost:5000"

def test_emergency_stop_resume():
    print("Testing Emergency Stop and Resume functionality...")

    # First, check initial status
    print("\n1. Checking initial status...")
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        status = response.json()
        print(f"Initial state: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
    except Exception as e:
        print(f"Error getting status: {e}")
        return

    # Start a process
    print("\n2. Starting a process...")
    try:
        response = requests.post(f"{BASE_URL}/api/process/start", json={})
        result = response.json()
        print(f"Start result: {result}")
    except Exception as e:
        print(f"Error starting process: {e}")
        return

    time.sleep(2)  # Wait for status update

    # Check status after start
    print("\n3. Checking status after start...")
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        status = response.json()
        print(f"After start: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
    except Exception as e:
        print(f"Error getting status: {e}")

    # Trigger emergency stop
    print("\n4. Triggering emergency stop...")
    try:
        response = requests.post(f"{BASE_URL}/api/emergency-stop")
        result = response.json()
        print(f"Emergency stop result: {result}")
    except Exception as e:
        print(f"Error triggering emergency stop: {e}")
        return

    time.sleep(2)  # Wait for status update

    # Check status after emergency stop
    print("\n5. Checking status after emergency stop...")
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        status = response.json()
        print(f"After emergency stop: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
    except Exception as e:
        print(f"Error getting status: {e}")

    # Resume from emergency
    print("\n6. Resuming from emergency...")
    try:
        response = requests.post(f"{BASE_URL}/api/process/start", json={"resume_from_emergency": True})
        result = response.json()
        print(f"Resume result: {result}")
    except Exception as e:
        print(f"Error resuming from emergency: {e}")
        return

    time.sleep(2)  # Wait for status update

    # Check final status
    print("\n7. Checking final status after resume...")
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        status = response.json()
        print(f"After resume: system_state={status.get('system_state')}, cycle_state={status.get('cycle_state')}")
    except Exception as e:
        print(f"Error getting status: {e}")

    print("\nTest completed!")

if __name__ == "__main__":
    test_emergency_stop_resume()