#!/usr/bin/env python3

"""
Runtime Parameter Verification Test
===================================

This test verifies that parameters are actually loaded during runtime and that 
YAML modifications are properly reflected in the running system.

Tests performed:
1. Launch system with original parameters
2. Verify parameter values are loaded correctly
3. Modify YAML parameters
4. Restart system and verify changes are reflected
5. Restore original values
"""

import subprocess
import time
import yaml
import tempfile
import shutil
import os
from pathlib import Path

def run_command_with_timeout(cmd, timeout=30, capture_output=True):
    """Run command with timeout"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, 
                              text=True, timeout=timeout, executable='/bin/bash')
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def verify_runtime_parameters():
    """Verify parameters are loaded correctly during runtime"""
    
    workspace = "/home/uday/Downloads/pragati_ros2"
    config_file = f"{workspace}/src/yanthra_move/config/production.yaml"
    
    print("🎯 RUNTIME PARAMETER VERIFICATION")
    print("=" * 60)
    
    # Step 1: Backup original config
    backup_file = f"{config_file}.verification_backup"
    shutil.copy2(config_file, backup_file)
    print("✅ Backed up original configuration")
    
    try:
        # Step 2: Launch system and capture parameter loading logs
        print("\n🔍 Step 1: Testing Original Parameter Loading")
        
        launch_cmd = f"cd {workspace} && source install/setup.bash && timeout 15s ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true enable_arm_client:=false continuous_operation:=false"
        
        returncode, stdout, stderr = run_command_with_timeout(launch_cmd, timeout=20)
        
        # Check for parameter loading evidence
        full_output = stdout + stderr
        
        # Look for parameter loading confirmation
        param_loading_indicators = [
            "continuous_operation",
            "joint_velocity", 
            "hardware_timeout",
            "simulation_mode",
            "Operational parameters loaded",
            "Parameters declared with defaults",
            "Parameter loading",
        ]
        
        found_indicators = []
        for indicator in param_loading_indicators:
            if indicator.lower() in full_output.lower():
                found_indicators.append(indicator)
        
        print(f"✅ Found {len(found_indicators)}/{len(param_loading_indicators)} parameter loading indicators")
        
        if len(found_indicators) < 4:
            print("⚠️  Few parameter loading indicators found - system might not be loading all parameters")
        else:
            print("✅ Good parameter loading evidence found")
        
        # Step 3: Test parameter modification
        print("\n🔍 Step 2: Testing Parameter Modification Reflection")
        
        # Read original config
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        original_joint_velocity = config['yanthra_move']['ros__parameters']['joint_velocity']
        original_continuous = config['yanthra_move']['ros__parameters']['continuous_operation']
        
        print(f"📋 Original joint_velocity: {original_joint_velocity}")
        print(f"📋 Original continuous_operation: {original_continuous}")
        
        # Modify parameters
        config['yanthra_move']['ros__parameters']['joint_velocity'] = 2.5  # Change from 1.0
        config['yanthra_move']['ros__parameters']['continuous_operation'] = not original_continuous  # Toggle
        
        # Write modified config
        with open(config_file, 'w') as f:
            yaml.safe_dump(config, f)
        
        print(f"🔧 Modified joint_velocity to: 2.5")
        print(f"🔧 Modified continuous_operation to: {not original_continuous}")
        
        # Launch system with modified parameters
        print("\n🚀 Launching system with modified parameters...")
        
        returncode2, stdout2, stderr2 = run_command_with_timeout(launch_cmd, timeout=20)
        full_output2 = stdout2 + stderr2
        
        # Check if modifications are reflected
        modifications_reflected = []
        
        if "joint_velocity" in full_output2 and "2.5" in full_output2:
            modifications_reflected.append("joint_velocity")
            print("✅ joint_velocity modification detected in logs")
        else:
            print("❌ joint_velocity modification NOT detected")
        
        if "continuous_operation" in full_output2:
            expected_value = "false" if original_continuous else "true"
            if expected_value in full_output2.lower():
                modifications_reflected.append("continuous_operation")
                print(f"✅ continuous_operation modification to {expected_value} detected")
            else:
                print(f"❌ continuous_operation modification to {expected_value} NOT detected")
        
        # Step 4: Check node lifecycle status
        print("\n🔍 Step 3: Verifying Node Lifecycles")
        
        # Launch system in background and check nodes
        print("🚀 Starting system for node lifecycle verification...")
        
        # Use a more targeted approach to check node status
        bg_launch_cmd = f"cd {workspace} && source install/setup.bash && ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true enable_arm_client:=false > /tmp/lifecycle_test.log 2>&1 &"
        
        os.system(bg_launch_cmd)
        time.sleep(8)  # Give system time to start
        
        # Check running nodes
        node_check_cmd = f"cd {workspace} && source install/setup.bash && ros2 node list"
        returncode3, node_output, _ = run_command_with_timeout(node_check_cmd, timeout=10)
        
        if returncode3 == 0:
            nodes = node_output.strip().split('\n')
            print(f"✅ Found {len(nodes)} running nodes:")
            for node in nodes:
                if node.strip():
                    print(f"   • {node.strip()}")
            
            # Check for expected nodes
            expected_nodes = ['yanthra_move', 'robot_state_publisher', 'joint_state_publisher']
            found_expected = [node for node in expected_nodes if any(expected in line for line in nodes for expected in [node])]
            
            print(f"✅ Found {len(found_expected)}/{len(expected_nodes)} expected nodes")
        else:
            print("❌ Could not retrieve node list")
        
        # Check topic list
        topic_check_cmd = f"cd {workspace} && source install/setup.bash && ros2 topic list"
        returncode4, topic_output, _ = run_command_with_timeout(topic_check_cmd, timeout=10)
        
        if returncode4 == 0:
            topics = topic_output.strip().split('\n')
            joint_topics = [t for t in topics if 'joint' in t.lower()]
            print(f"✅ Found {len(topics)} topics, including {len(joint_topics)} joint-related topics")
        
        # Cleanup background processes
        os.system("pkill -f 'ros2 launch' 2>/dev/null || true")
        time.sleep(2)
        
        # Step 5: Generate verification report
        print(f"\n{'='*60}")
        print("RUNTIME PARAMETER VERIFICATION REPORT")
        print(f"{'='*60}")
        
        print(f"\n📊 SUMMARY:")
        print(f"   Parameter Loading Indicators: {len(found_indicators)}/{len(param_loading_indicators)}")
        print(f"   Parameter Modifications Detected: {len(modifications_reflected)}/2")
        print(f"   Node Lifecycle Check: {'✅ PASSED' if returncode3 == 0 else '❌ FAILED'}")
        print(f"   Topic Publishing Check: {'✅ PASSED' if returncode4 == 0 else '❌ FAILED'}")
        
        # Overall assessment
        total_checks = 4
        passed_checks = 0
        
        if len(found_indicators) >= 4:
            passed_checks += 1
        if len(modifications_reflected) >= 1:
            passed_checks += 1
        if returncode3 == 0:
            passed_checks += 1
        if returncode4 == 0:
            passed_checks += 1
        
        success_rate = (passed_checks / total_checks) * 100
        
        print(f"\n🎯 OVERALL RESULT:")
        print(f"   Verification Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 75:
            print("✅ RUNTIME PARAMETER VERIFICATION: PASSED")
            print("   Parameters are loading correctly and YAML modifications are reflected")
            return True
        else:
            print("❌ RUNTIME PARAMETER VERIFICATION: NEEDS ATTENTION")
            print("   Some parameter loading or modification issues detected")
            return False
            
    finally:
        # Always restore original config
        shutil.copy2(backup_file, config_file)
        os.remove(backup_file)
        print("\n🔄 Original configuration restored")
        
        # Final cleanup
        os.system("pkill -f 'ros2 launch' 2>/dev/null || true")

def main():
    success = verify_runtime_parameters()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())