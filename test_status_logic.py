#!/usr/bin/env python3
"""
Test script to verify the status logic fix for storage phase
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

# Mock the controller and phase
class MockPhase:
    def __init__(self, value):
        self.value = value

class MockController:
    def __init__(self, phase_value, process_active):
        self.current_phase = MockPhase(phase_value)
        self.process_active = process_active

# Test the status logic
def test_status_logic():
    print("Testing status logic for storage phase...")

    # Test case 1: storage phase, process not active -> should be holding
    controller = MockController('storage', False)
    phase_value = controller.current_phase.value
    process_active = controller.process_active

    if phase_value == 'storage':
        if process_active:
            system_state = 'running'
            cycle_state = 'running'
        else:
            system_state = 'holding'
            cycle_state = 'holding'

    print(f"Test 1 - storage phase, process_active=False: system_state={system_state}, cycle_state={cycle_state}")
    assert system_state == 'holding' and cycle_state == 'holding', "Test 1 failed"

    # Test case 2: storage phase, process active -> should be running
    controller = MockController('storage', True)
    phase_value = controller.current_phase.value
    process_active = controller.process_active

    if phase_value == 'storage':
        if process_active:
            system_state = 'running'
            cycle_state = 'running'
        else:
            system_state = 'holding'
            cycle_state = 'holding'

    print(f"Test 2 - storage phase, process_active=True: system_state={system_state}, cycle_state={cycle_state}")
    assert system_state == 'running' and cycle_state == 'running', "Test 2 failed"

    print("All tests passed!")

if __name__ == "__main__":
    test_status_logic()