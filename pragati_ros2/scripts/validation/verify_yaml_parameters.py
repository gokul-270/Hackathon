#!/usr/bin/env python3
"""
Parameter Verification Script
Tests if YAML parameter changes are properly reflected in the ROS2 system
"""

import rclpy
from rclpy.node import Node
import yaml
import os
import sys
from pathlib import Path

class ParameterVerifier(Node):
    def __init__(self):
        super().__init__('parameter_verifier')

        # Declare parameters that should be loaded from YAML
        self.declare_parameter('PRAGATI_INSTALL_DIR', '.')
        self.declare_parameter('YanthraLabCalibrationTesting', False)
        self.declare_parameter('trigger_camera', True)
        self.declare_parameter('global_vaccum_motor', True)
        self.declare_parameter('end_effector_enable', True)
        self.declare_parameter('simulation_mode', False)
        self.declare_parameter('continuous_operation', False)
        self.declare_parameter('save_logs', False)
        self.declare_parameter('EndEffectorDropConveyor', False)
        self.declare_parameter('delays/picking', 0.2)

        # Test parameters from different config files
        self.declare_parameter('joint2_init/min', 0.01)
        self.declare_parameter('joint2_init/max', 0.85)
        self.declare_parameter('joint3_init/park_position', 0.1)
        self.declare_parameter('joint4_init/park_position', -0.65)
        self.declare_parameter('joint5_init/end_effector_len', 0.085)

    def verify_parameters(self):
        """Verify that parameters are loaded correctly"""
        self.get_logger().info("🔍 PARAMETER VERIFICATION START")

        # Test basic parameters
        install_dir = self.get_parameter('PRAGATI_INSTALL_DIR').value
        simulation_mode = self.get_parameter('simulation_mode').value
        trigger_camera = self.get_parameter('trigger_camera').value
        continuous_op = self.get_parameter('continuous_operation').value
        picking_delay = self.get_parameter('delays/picking').value

        self.get_logger().info(f"PRAGATI_INSTALL_DIR: {install_dir}")
        self.get_logger().info(f"simulation_mode: {simulation_mode}")
        self.get_logger().info(f"trigger_camera: {trigger_camera}")
        self.get_logger().info(f"continuous_operation: {continuous_op}")
        self.get_logger().info(f"picking_delay: {picking_delay}")

        # Test joint parameters
        joint2_min = self.get_parameter('joint2_init/min').value
        joint2_max = self.get_parameter('joint2_init/max').value
        joint3_park = self.get_parameter('joint3_init/park_position').value
        joint4_park = self.get_parameter('joint4_init/park_position').value
        ee_len = self.get_parameter('joint5_init/end_effector_len').value

        self.get_logger().info(f"joint2_init/min: {joint2_min}")
        self.get_logger().info(f"joint2_init/max: {joint2_max}")
        self.get_logger().info(f"joint3_init/park_position: {joint3_park}")
        self.get_logger().info(f"joint4_init/park_position: {joint4_park}")
        self.get_logger().info(f"joint5_init/end_effector_len: {ee_len}")

        # Get all parameters
        all_params = self._parameters
        self.get_logger().info(f"Total parameters loaded: {len(all_params)}")

        return True

def load_yaml_config(config_file):
    """Load and display YAML config content"""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        print(f"\n📄 YAML CONFIG: {config_file}")
        print("=" * 50)
        yaml.dump(config, sys.stdout, default_flow_style=False)
        print("=" * 50)
        return config
    except Exception as e:
        print(f"❌ Error loading {config_file}: {e}")
        return None

def main():
    # Find config files - try multiple possible locations
    possible_config_dirs = [
        Path(__file__).parent.parent.parent / "src" / "yanthra_move" / "config",
        Path(__file__).parent.parent.parent / "config",
        Path("/home/uday/Downloads/pragati_ros2/src/yanthra_move/config"),
        Path("/home/uday/Downloads/pragati_ros2/config")
    ]

    config_dir = None
    for possible_dir in possible_config_dirs:
        if possible_dir.exists():
            config_dir = possible_dir
            break

    if not config_dir:
        print("❌ Config directory not found in any of the expected locations")
        return

    print(f"✅ Found config directory: {config_dir}")
    print("🔍 PARAMETER VERIFICATION TOOL")
    print("=" * 50)

    # Load and display config files
    config_files = [
        config_dir / "production.yaml",  # This is what the launch file uses
        config_dir / "yanthra_move_picking_ros2.yaml",
        config_dir / "simulation.yaml"
    ]

    for config_file in config_files:
        if config_file.exists():
            load_yaml_config(config_file)

    # Initialize ROS2 and test parameter loading like the launch file does
    rclpy.init()

    try:
        # Create node with parameters loaded from YAML (like launch file)
        import rclpy.parameter
        from rclpy.parameter import Parameter

        # Load parameters from production.yaml (same as launch file)
        production_config = config_dir / "production.yaml"
        if production_config.exists():
            print(f"\n🔧 Loading parameters from: {production_config}")

            # Read YAML file
            with open(production_config, 'r') as f:
                yaml_params = yaml.safe_load(f)

            # Extract yanthra_move parameters
            if 'yanthra_move' in yaml_params and 'ros__parameters' in yaml_params['yanthra_move']:
                ros_params = yaml_params['yanthra_move']['ros__parameters']
                print(f"📊 Found {len(ros_params)} parameters in YAML")

                # Create parameter list for node
                param_list = []
                for key, value in ros_params.items():
                    param_list.append(Parameter(key, rclpy.parameter.Parameter.Type.from_parameter_value(value), value))

                # Create node with parameters
                verifier = ParameterVerifier(parameter_overrides=param_list)
            else:
                print("❌ No yanthra_move.ros__parameters found in YAML")
                verifier = ParameterVerifier()
        else:
            print(f"❌ Production config not found: {production_config}")
            verifier = ParameterVerifier()

        verifier.verify_parameters()

        # Keep node alive briefly to allow parameter server to load
        rclpy.spin_once(verifier, timeout_sec=1.0)

        verifier.verify_parameters()

    except Exception as e:
        print(f"❌ Error during parameter verification: {e}")
        import traceback
        traceback.print_exc()
    finally:
        rclpy.shutdown()

if __name__ == '__main__':
    main()