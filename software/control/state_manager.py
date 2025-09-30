import json
import os
from datetime import datetime
from pathlib import Path

class StateManager:
    """Manages persistent state for power loss recovery"""
    
    def __init__(self, state_file='/home/mikejames/cannabis-dryer/system_state.json'):
        self.state_file = Path(state_file)
        self.state = self.load_state()
    
    def load_state(self):
        """Load saved state or return defaults"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    # Convert ISO strings back to datetime
                    if state.get('process_start_time'):
                        state['process_start_time'] = datetime.fromisoformat(state['process_start_time'])
                    if state.get('phase_start_time'):
                        state['phase_start_time'] = datetime.fromisoformat(state['phase_start_time'])
                    return state
            except Exception as e:
                print(f"Error loading state: {e}")
        
        # Default state - everything off
        return {
            'process_active': False,
            'current_phase': 'idle',
            'process_start_time': None,
            'phase_start_time': None,
            'equipment_states': {
                'dehum': 'OFF',
                'hum_solenoid': 'OFF',
                'hum_fan': 'OFF',
                'erv': 'OFF',
                'supply_fan': 'OFF',
                'return_fan': 'OFF'
            }
        }
    
    def save_state(self, state):
        """Save current state to file"""
        save_data = state.copy()
        # Convert datetime to ISO strings for JSON
        if save_data.get('process_start_time'):
            save_data['process_start_time'] = save_data['process_start_time'].isoformat()
        if save_data.get('phase_start_time'):
            save_data['phase_start_time'] = save_data['phase_start_time'].isoformat()
        
        with open(self.state_file, 'w') as f:
            json.dump(save_data, f, indent=2)