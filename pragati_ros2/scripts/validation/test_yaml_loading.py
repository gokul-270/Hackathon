#!/usr/bin/env python3
"""
Simple Parameter Test Script
Tests if yanthra_move_system loads YAML parameters correctly
"""

import subprocess
import time
import os
import yaml
from pathlib import Path

def load_yaml_config(config_file):
    """Load YAML config and return parameters"""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"❌ Error loading {config_file}: {e}")
        return None

def test_parameter_loading():
    """Test if parameters are loaded correctly by launching yanthra_move_system"""

    print("🔍 TESTING YAML PARAMETER LOADING")
    print("=" * 50)

    # Find config directory
    config_dir = Path("/home/uday/Downloads/pragati_ros2/src/yanthra_move/config")
    if not config_dir.exists():
        print("❌ Config directory not found")
        return False

    # Load production.yaml (what launch file uses)
    production_config = config_dir / "production.yaml"
    if not production_config.exists():
        print(f"❌ Production config not found: {production_config}")
        return False

    yaml_config = load_yaml_config(production_config)
    if not yaml_config:
        return False

    # Extract expected parameters
    expected_params = yaml_config.get('yanthra_move', {}).get('ros__parameters', {})
    print(f"📄 Loaded {len(expected_params)} parameters from YAML")

    # Key parameters to check
    key_checks = {
        'simulation_mode': expected_params.get('simulation_mode'),
        'continuous_operation': expected_params.get('continuous_operation'),
        'trigger_camera': expected_params.get('trigger_camera'),
        'global_vaccum_motor': expected_params.get('global_vaccum_motor'),
        'end_effector_enable': expected_params.get('end_effector_enable'),
        'joint3_init/park_position': expected_params.get('joint3_init', {}).get('park_position'),
        'joint4_init/park_position': expected_params.get('joint4_init', {}).get('park_position'),
        'joint5_init/end_effector_len': expected_params.get('joint5_init', {}).get('end_effector_len'),
    }

    print("\n📊 Expected parameter values from YAML:")
    for param, expected in key_checks.items():
        print(f"  {param}: {expected}")

    # Launch yanthra_move_system with production.yaml
    print("\n🚀 Launching yanthra_move_system with production.yaml...")
    print(f"Command: ros2 run yanthra_move yanthra_move_system --ros-args --params-file {production_config}")

    try:
        # Start the process
        cmd = [
            'ros2', 'run', 'yanthra_move', 'yanthra_move_system',
            '--ros-args', '--params-file', str(production_config)
        ]

        print(f"Running: {' '.join(cmd)}")

        # Start process
        process = subprocess.Popen(
            cmd,
            cwd='/home/uday/Downloads/pragati_ros2',
            env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Monitor output for parameter loading
        loaded_params = {}
        timeout = 15  # 15 seconds timeout
        start_time = time.time()

        print("\n📝 Monitoring parameter loading...")

        while time.time() - start_time < timeout:
            if process.poll() is not None:
                break

            # Read output
            output = process.stdout.readline()
            if output:
                print(output.strip())

                # Look for parameter loading messages
                if 'Loaded' in output and ':' in output:
                    # Extract parameter values from log messages
                    if 'simulation_mode' in output:
                        loaded_params['simulation_mode'] = 'true' in output.lower()
                    elif 'continuous_operation' in output:
                        loaded_params['continuous_operation'] = 'true' in output.lower()
                    elif 'trigger_camera' in output:
                        loaded_params['trigger_camera'] = 'true' in output.lower()
                    elif 'global_vaccum_motor' in output:
                        loaded_params['global_vaccum_motor'] = 'true' in output.lower()
                    elif 'end_effector_enable' in output:
                        loaded_params['end_effector_enable'] = 'true' in output.lower()

        # Terminate the process
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

        print("\n🔍 VERIFICATION RESULTS:")
        print("=" * 30)

        # Check if parameters match
        issues = []
        for param, expected in key_checks.items():
            if param in loaded_params:
                actual = loaded_params[param]
                if actual == expected:
                    print(f"✅ {param}: {actual}")
                else:
                    print(f"❌ {param}: expected {expected}, got {actual}")
                    issues.append(f"{param}: expected {expected}, got {actual}")
            else:
                print(f"❓ {param}: not found in logs")
                issues.append(f"{param}: not found in output")

        if issues:
            print("\n❌ PARAMETER LOADING ISSUES:")
            for issue in issues:
                print(f"  - {issue}")
            print("\n💡 YAML parameters are NOT being loaded correctly!")
            return False
        else:
            print("\n✅ All parameters loaded correctly from YAML!")
            return True

    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

if __name__ == '__main__':
    success = test_parameter_loading()
    exit(0 if success else 1)