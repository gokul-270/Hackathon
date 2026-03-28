#!/usr/bin/env python3

import subprocess
import time
import sys
import signal
import os

def test_parameter_loading():
    """Test that parameters are loaded correctly from YAML files"""
    
    print("🧪 Testing parameter loading from YAML files...")
    print("=" * 60)
    
    # Change to ROS2 workspace
    os.chdir("/home/uday/Downloads/pragati_ros2")
    
    # Source the workspace
    env = os.environ.copy()
    env['BASH_ENV'] = '/home/uday/Downloads/pragati_ros2/install/setup.bash'
    
    # Test 1: ODrive Service Node parameter loading
    print("\n1. Testing ODrive Service Node parameter loading...")
    
    try:
        # Start the node with a timeout
        cmd = [
            "bash", "-c", 
            "source install/setup.bash && timeout 10s ros2 run odrive_control_ros2 odrive_service_node --ros-args --params-file src/odrive_control_ros2/config/production.yaml"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        
        output = result.stdout + result.stderr
        print("Output snippet:")
        
        # Look for parameter loading evidence
        lines = output.split('\n')
        param_lines = [line for line in lines if any(keyword in line.lower() for keyword in 
                      ['parameter', 'loaded', 'joint2', 'joint3', 'joint4', 'joint5', 'odrive', 'transmission_factor'])]
        
        for line in param_lines[:10]:  # Show first 10 relevant lines
            print(f"  {line}")
        
        # Check for specific parameter values from YAML
        yaml_values_found = []
        if "125.23664" in output:  # joint2.transmission_factor
            yaml_values_found.append("joint2.transmission_factor = 125.23664")
        if "0.870047022" in output:  # joint3.transmission_factor  
            yaml_values_found.append("joint3.transmission_factor = 0.870047022")
        if "35.0" in output and "PGain" in output:  # p_gain values
            yaml_values_found.append("p_gain values from YAML")
        if "0.000549" in output:  # v_gain values
            yaml_values_found.append("v_gain values from YAML")
            
        if yaml_values_found:
            print(f"✅ YAML values detected in output:")
            for value in yaml_values_found:
                print(f"  - {value}")
        else:
            print("❌ No specific YAML parameter values found in output")
            
    except subprocess.TimeoutExpired:
        print("⏰ Node startup timeout - this is expected for testing")
    except Exception as e:
        print(f"❌ Error testing ODrive node: {e}")
    
    print("\n" + "=" * 60)
    
    # Test 2: YanthraMove parameter loading  
    print("\n2. Testing YanthraMove parameter loading...")
    
    try:
        cmd = [
            "bash", "-c",
            "source install/setup.bash && timeout 10s ros2 run yanthra_move yanthra_move_node --ros-args --params-file src/yanthra_move/config/production.yaml"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        
        output = result.stdout + result.stderr  
        print("Output snippet:")
        
        lines = output.split('\n')
        param_lines = [line for line in lines if any(keyword in line.lower() for keyword in 
                      ['parameter', 'loaded', 'joint', 'park_position', 'continuous_operation'])]
        
        for line in param_lines[:10]:
            print(f"  {line}")
            
        # Check for specific YAML values
        yanthra_values_found = []
        if "3.33" in output or "3.330" in output:  # joint3_init.park_position
            yanthra_values_found.append("joint3_init.park_position = 3.33")
        if "4.44" in output or "4.440" in output:  # joint4_init.park_position  
            yanthra_values_found.append("joint4_init.park_position = 4.44")
        if "continuous_operation" in output.lower() and "true" in output.lower():
            yanthra_values_found.append("continuous_operation = true")
        if "0.200" in output:  # delays.picking
            yanthra_values_found.append("delays.picking = 0.200")
        if "park_position: 3" in output:  # Alternative format
            yanthra_values_found.append("joint3_init/park_position from YAML")
        if "park_position: 4" in output:  # Alternative format
            yanthra_values_found.append("joint4_init/park_position from YAML")
            
        if yanthra_values_found:
            print(f"✅ YAML values detected in output:")
            for value in yanthra_values_found:
                print(f"  - {value}")
        else:
            print("❌ No specific YAML parameter values found in output")
            
    except subprocess.TimeoutExpired:
        print("⏰ Node startup timeout - this is expected for testing")
    except Exception as e:
        print(f"❌ Error testing YanthraMove node: {e}")
    
    print("\n" + "=" * 60)
    print("🏁 Parameter loading test completed!")
    print("\nIf you see YAML values in the outputs above, the fix is working correctly.")
    print("The nodes should now use YAML config values instead of hard-coded defaults.")

if __name__ == "__main__":
    test_parameter_loading()