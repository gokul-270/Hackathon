#!/usr/bin/env python3
# Copyright (c) 2024 Pragati Robotics
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
MG6010-i6 Motor Test Launch File

This launch file provides a simple way to test a single MG6010-i6 motor
using the LK-TECH CAN Protocol V2.35.

Motor Specifications (MG6010E-i6):
  - Rated Voltage: 24V (7.4V-32V supported)
  - Max Torque: 10 N.m
  - CAN Baud Rate: 500kbps (Pragati configuration)
  - CAN ID: 0x140 + motor_id (e.g., 0x141 for motor 1)
  - Protocol: LK-TECH CAN V2.35

Usage:
  # Basic test
  ros2 launch motor_control_ros2 mg6010_test.launch.py
  
  # Custom parameters
  ros2 launch motor_control_ros2 mg6010_test.launch.py can_interface:=can0 baud_rate:=500000 motor_id:=1
  
  # Different test modes
  ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status    # Read status
  ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=position  # Position control
  ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=velocity  # Velocity control
  ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=torque    # Torque control
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    """Generate launch description for MG6010-i6 motor testing."""
    
    # Declare launch arguments
    declared_arguments = []
    
    declared_arguments.append(
        DeclareLaunchArgument(
            'can_interface',
            default_value='can0',
            description='CAN interface name (e.g., can0, can1)'
        )
    )
    
    declared_arguments.append(
        DeclareLaunchArgument(
            'baud_rate',
            default_value='500000',
            description='CAN baud rate in bps (500000 = 500kbps; Pragati default)'
        )
    )
    
    declared_arguments.append(
        DeclareLaunchArgument(
            'motor_id',
            default_value='1',
            description='Motor CAN ID (1-32), CAN ID will be 0x140 + motor_id'
        )
    )
    
    declared_arguments.append(
        DeclareLaunchArgument(
            'test_mode',
            default_value='status',
            description='Test mode: status, position, velocity, torque, on_off'
        )
    )
    
    declared_arguments.append(
        DeclareLaunchArgument(
            'use_config_file',
            default_value='true',
            description='Use YAML config file for parameters'
        )
    )
    
    # Get launch arguments
    can_interface = LaunchConfiguration('can_interface')
    baud_rate = LaunchConfiguration('baud_rate')
    motor_id = LaunchConfiguration('motor_id')
    test_mode = LaunchConfiguration('test_mode')
    use_config_file = LaunchConfiguration('use_config_file')
    
    # Config file path
    config_file = PathJoinSubstitution([
        FindPackageShare('motor_control_ros2'),
        'config',
        'mg6010_test.yaml'
    ])
    
    # MG6010 Test Node
    mg6010_test_node = Node(
        package='motor_control_ros2',
        executable='mg6010_test_node',
        name='mg6010_test',
        output='screen',
        parameters=[{
            'interface_name': can_interface,
            'baud_rate': baud_rate,
            'node_id': motor_id,
            'mode': test_mode,
        }],
        arguments=['--ros-args', '--log-level', 'info'],
    )
    
    # Startup message
    startup_msg = LogInfo(
        msg=[
            '\n',
            '=' * 70, '\n',
            'MG6010-i6 Motor Test Launch\n',
            '=' * 70, '\n',
            'CAN Interface: ', can_interface, '\n',
            'Baud Rate:     ', baud_rate, ' bps\n',
            'Motor ID:      ', motor_id, ' (CAN ID: 0x140 + ', motor_id, ')\n',
            'Test Mode:     ', test_mode, '\n',
            '=' * 70, '\n',
            'Make sure:\n',
            '  1. CAN interface is configured: sudo ip link set ', can_interface, 
                ' type can bitrate ', baud_rate, '\n',
            '  2. CAN interface is up: sudo ip link set ', can_interface, ' up\n',
            '  3. Motor is powered on (24V)\n',
            '  4. CAN bus is properly terminated (120Ω resistors)\n',
            '=' * 70, '\n'
        ]
    )
    
    # Nodes to launch
    nodes = [
        startup_msg,
        mg6010_test_node,
    ]
    
    return LaunchDescription(declared_arguments + nodes)
