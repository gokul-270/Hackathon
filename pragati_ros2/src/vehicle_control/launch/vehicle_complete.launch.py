#!/usr/bin/env python3

# Copyright 2025 Pragati Robotics
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Vehicle Complete Launch File
============================
Comprehensive ROS2 launch file for the Pragati vehicle control system.

Launches:
- mg6010_controller_node (motor_control_ros2) - CAN motor driver for 3 steering motors
- odrive_service_node (odrive_control_ros2) - CAN motor driver for 3 ODrive drive wheels
- vehicle_control_node (vehicle_control) - State machine, GPIO, safety management

Motor Configuration:
- 3x MG6010E-i6 steering motors via motor_control_ros2 (CAN IDs 1,2,3)
- 3x ODrive Pro drive motors via odrive_control_ros2 (CAN node IDs 0,1,2)
- Both controllers share can0 bus with non-overlapping arbitration ID ranges

Usage:
    ros2 launch vehicle_control vehicle_complete.launch.py
    ros2 launch vehicle_control vehicle_complete.launch.py can_interface:=can1
    ros2 launch vehicle_control vehicle_complete.launch.py use_sim_time:=true
    ros2 launch vehicle_control vehicle_complete.launch.py vehicle_control_delay:=30.0

This runs on the Vehicle Controller RPi (separate from Arm Controllers).
"""

import os
import subprocess
import time
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction, LogInfo, SetEnvironmentVariable, OpaqueFunction, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, LaunchLogDir
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def cleanup_previous_instances():
    """Automatically cleanup any previous ROS2 instances to prevent duplicate nodes.

    NOTE: Uses -x flag for exact match to avoid killing current launch process.
    """
    print("🧹 AUTO-CLEANUP: Ensuring clean launch environment...")

    # Stop ROS2 daemon first
    try:
        subprocess.run(['ros2', 'daemon', 'stop'], capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Kill any existing vehicle-related ROS2 processes
    # Note: pkill -x has 15-char limit, use -f with lib/ path for long names
    long_processes = [
        'lib/vehicle_control/vehicle_control_node',
        'lib/motor_control_ros2/mg6010_controller_node',
        'lib/odrive_control_ros2/odrive_service_node',
    ]
    for pattern in long_processes:
        try:
            subprocess.run(['pkill', '-f', pattern], capture_output=True, timeout=3)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Kill vehicle MQTT bridge script specifically (avoid matching launch file)
    try:
        subprocess.run(['pkill', '-f', r'python.*vehicle_mqtt_bridge\.py'], capture_output=True, timeout=3)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Wait for processes to terminate
    time.sleep(0.5)

    # Restart ROS2 daemon
    try:
        subprocess.run(['ros2', 'daemon', 'start'], capture_output=True, timeout=10)
        time.sleep(0.5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("✅ AUTO-CLEANUP: Environment ready for safe launch")


def generate_launch_description():
    # AUTOMATIC CLEANUP: Prevent duplicate nodes and ensure clean launch
    cleanup_previous_instances()

    # Launch configuration variables
    use_sim_time = LaunchConfiguration('use_sim_time')
    can_interface = LaunchConfiguration('can_interface')
    output_log = LaunchConfiguration('output_log')
    vehicle_control_delay = LaunchConfiguration('vehicle_control_delay')
    enable_vehicle_mqtt_bridge = LaunchConfiguration('enable_vehicle_mqtt_bridge')

    # Ensure node log files go into the same per-run directory as launch.log
    # (launch creates a unique run folder; this points ROS_LOG_DIR at it for all nodes)
    set_ros_log_dir_cmd = SetEnvironmentVariable(
        name='ROS_LOG_DIR',
        value=LaunchLogDir(),
    )

    # Declare launch arguments
    declare_use_sim_time_cmd = DeclareLaunchArgument(
        name='use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )

    declare_can_interface_cmd = DeclareLaunchArgument(
        name='can_interface',
        default_value='can0',
        description='CAN interface name for vehicle motors'
    )

    declare_output_log_cmd = DeclareLaunchArgument(
        name='output_log',
        default_value='screen',
        description='Output log type (screen or log)'
    )

    declare_vehicle_control_delay_cmd = DeclareLaunchArgument(
        name='vehicle_control_delay',
        default_value='25.0',
        description='Seconds to delay vehicle_control_node startup to allow motor homing/initialization'
    )

    declare_enable_vehicle_mqtt_bridge_cmd = DeclareLaunchArgument(
        name='enable_vehicle_mqtt_bridge',
        default_value='true',
        description='Enable Vehicle MQTT bridge (scripts/vehicle_mqtt_bridge.py)'
    )

    # Get config file paths
    motor_control_pkg = get_package_share_directory('motor_control_ros2')
    vehicle_control_pkg = get_package_share_directory('vehicle_control')

    # Motor control config (CAN motor driver)
    motor_config_file = os.path.join(motor_control_pkg, 'config', 'vehicle_motors.yaml')

    # Vehicle control config (state machine, GPIO)
    vehicle_config_file = os.path.join(vehicle_control_pkg, 'config', 'production.yaml')

    print(f"ℹ️ Motor config: {motor_config_file}")
    print(f"ℹ️ Motor config exists: {os.path.exists(motor_config_file)}")
    print(f"ℹ️ Vehicle config: {vehicle_config_file}")
    print(f"ℹ️ Vehicle config exists: {os.path.exists(vehicle_config_file)}")

    # Use PathJoinSubstitution for launch system
    motor_config = PathJoinSubstitution([
        FindPackageShare('motor_control_ros2'),
        'config',
        'vehicle_motors.yaml'
    ])

    vehicle_config = PathJoinSubstitution([
        FindPackageShare('vehicle_control'),
        'config',
        'production.yaml'
    ])

    odrive_config = PathJoinSubstitution([
        FindPackageShare('odrive_control_ros2'),
        'config',
        'production.yaml'
    ])

    # 1. Motor Controller Node (CAN driver for 6 vehicle motors)
    # This handles low-level CAN communication with MG6010/MG6012 motors
    motor_controller_node = Node(
        package='motor_control_ros2',
        executable='mg6010_controller_node',
        name='vehicle_motor_control',
        namespace='vehicle',
        output=output_log,
        parameters=[
            motor_config,
            {'interface_name': can_interface}
        ],
        remappings=[
            # Vehicle namespace for motor topics/services
            ('joint_states', '/vehicle/joint_states'),
            ('enable_motors', '/vehicle/enable_motors'),
            ('disable_motors', '/vehicle/disable_motors'),
        ]
    )

    # 2. ODrive Service Node (CAN driver for ODrive drive wheel motors)
    odrive_node = Node(
        package='odrive_control_ros2',
        executable='odrive_service_node',
        name='odrive_service_node',
        output=output_log,
        parameters=[
            odrive_config,
            {'interface_name': can_interface}
        ],
        emulate_tty=True,
        remappings=[
            # Publish drive wheel joint states into the vehicle namespace so that
            # vehicle_control_node (subscribed to /vehicle/joint_states) receives them.
            ('/joint_states', '/vehicle/joint_states'),
        ],
    )

    # 3. Vehicle Control Node (state machine, GPIO, safety)
    # This handles high-level vehicle logic
    vehicle_control_node = Node(
        package='vehicle_control',
        executable='vehicle_control_node',
        name='vehicle_control_node',
        namespace='vehicle',
        output=output_log,
        parameters=[
            vehicle_config,
            {'use_sim_time': use_sim_time}
        ],
        remappings=[
            # Connect to motor controller topics
            ('/cmd_vel', '/vehicle/cmd_vel'),
        ]
    )

    # 3. Vehicle MQTT Bridge (ROS2 ↔ MQTT) - launched as a Python process (not a packaged node)
    # Script is installed into the package share directory via data_files in setup.py.
    vehicle_mqtt_bridge_script = os.path.join(
        vehicle_control_pkg, 'scripts', 'vehicle_mqtt_bridge.py'
    )

    # Task 1.2: Log resolved bridge script path at INFO level before launching
    print(
        f"[INFO] [vehicle_complete.launch]: "
        f"Vehicle MQTT bridge script: {vehicle_mqtt_bridge_script} "
        f"(exists={os.path.exists(vehicle_mqtt_bridge_script)})"
    )

    # Task 1.3: Track launch time for early-exit detection
    _bridge_launch_time = time.monotonic()

    def _on_bridge_exit(event, context):
        """Log ERROR if bridge process exits within 10 seconds (likely startup failure)."""
        elapsed = time.monotonic() - _bridge_launch_time
        if elapsed < 10.0:
            print(
                f"[ERROR] [vehicle_complete.launch]: "
                f"Vehicle MQTT bridge exited after {elapsed:.1f}s "
                f"(script={vehicle_mqtt_bridge_script}). "
                f"Check that the script exists and all imports are satisfied."
            )
        return []

    bridge_execute = ExecuteProcess(
        cmd=['python3', vehicle_mqtt_bridge_script],
        name='vehicle_mqtt_bridge_process',
        output=output_log,
        condition=IfCondition(enable_vehicle_mqtt_bridge),
    )

    bridge_exit_handler = RegisterEventHandler(
        OnProcessExit(
            target_action=bridge_execute,
            on_exit=_on_bridge_exit,
        )
    )

    vehicle_mqtt_bridge_process = TimerAction(
        period=5.0,
        actions=[bridge_execute, bridge_exit_handler],
    )

    # Create launch description
    ld = LaunchDescription()

    # Declare launch arguments
    ld.add_action(declare_use_sim_time_cmd)
    # Route all node logs to the launch log directory
    ld.add_action(set_ros_log_dir_cmd)

    ld.add_action(declare_can_interface_cmd)
    ld.add_action(declare_output_log_cmd)
    ld.add_action(declare_vehicle_control_delay_cmd)
    ld.add_action(declare_enable_vehicle_mqtt_bridge_cmd)

    # Log startup info
    ld.add_action(LogInfo(msg='🚗 Starting Vehicle Complete Launch...'))
    ld.add_action(LogInfo(msg='   Motor Controller: motor_control_ros2 (vehicle_motors.yaml)'))
    ld.add_action(LogInfo(msg='   ODrive Service:   odrive_control_ros2 (production.yaml)'))
    ld.add_action(LogInfo(msg='   Vehicle Control:  vehicle_control (production.yaml)'))

    # Launch motor controller and ODrive node together (with small delay after cleanup)
    motor_and_odrive_delayed = TimerAction(
        period=0.3,
        actions=[motor_controller_node, odrive_node]
    )
    ld.add_action(motor_and_odrive_delayed)

    # Launch vehicle control after motor controller is ready
    # NOTE: TimerAction period does not reliably accept LaunchConfiguration directly across distros.
    # Use OpaqueFunction to evaluate the launch argument at runtime and create the TimerAction.
    def _delayed_vehicle_control(context, *args, **kwargs):
        delay_s = float(vehicle_control_delay.perform(context))
        return [TimerAction(period=delay_s, actions=[vehicle_control_node])]

    ld.add_action(OpaqueFunction(function=_delayed_vehicle_control))

    # Launch Vehicle MQTT bridge (delayed, similar to ARM_client in pragati_complete.launch.py)
    ld.add_action(vehicle_mqtt_bridge_process)

    ld.add_action(LogInfo(msg='✅ Vehicle launch complete'))

    return ld
