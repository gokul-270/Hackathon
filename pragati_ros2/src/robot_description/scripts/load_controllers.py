#!/usr/bin/env python3
"""
Helper script to wait for controller_manager and then load controllers
"""
import sys
import time
import subprocess

def wait_for_controller_manager(timeout=30):
    """Wait for controller_manager to be available"""
    print("Waiting for controller_manager to be ready...")
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        try:
            result = subprocess.run(
                ['ros2', 'control', 'list_controllers'],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                print("✓ Controller manager is ready!")
                return True
        except (subprocess.TimeoutExpired, Exception):
            pass
        
        time.sleep(0.5)
    
    print("✗ Timeout waiting for controller_manager")
    return False

def load_controller(controller_name):
    """Load and activate a controller"""
    print(f"Loading controller: {controller_name}")
    result = subprocess.run(
        ['ros2', 'control', 'load_controller', '--set-state', 'active', controller_name],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✓ Successfully loaded {controller_name}")
        return True
    else:
        print(f"✗ Failed to load {controller_name}")
        print(f"  Error: {result.stderr}")
        return False

if __name__ == '__main__':
    # Wait for controller manager
    if not wait_for_controller_manager():
        sys.exit(1)
    
    # Load controllers
    success = True
    
    # Load joint state broadcaster first
    if load_controller('joint_state_broadcaster'):
        time.sleep(1)
        # Then load trajectory controller
        if not load_controller('joint_trajectory_controller'):
            success = False
    else:
        success = False
    
    sys.exit(0 if success else 1)
