#!/usr/bin/env python3
"""
Vehicle Motor Controller Launch File

Launches mg6010_controller_node with vehicle motor configuration.

Simplified test mapping (6x MG6010 bring-up):
- Steering motors: CAN IDs 1, 2, 3
- Drive motors: CAN IDs 4, 5, 6

Run on Vehicle Controller RPi.
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Get package directory
    pkg_dir = get_package_share_directory('motor_control_ros2')
    
    # Vehicle motors config file
    vehicle_config = os.path.join(pkg_dir, 'config', 'vehicle_motors.yaml')
    
    # Declare launch arguments
    config_file_arg = DeclareLaunchArgument(
        'config_file',
        default_value=vehicle_config,
        description='Path to vehicle motors YAML config file'
    )
    
    can_interface_arg = DeclareLaunchArgument(
        'can_interface',
        default_value='can0',
        description='CAN interface name'
    )
    
    # Motor controller node for vehicle motors
    motor_controller_node = Node(
        package='motor_control_ros2',
        executable='mg6010_controller_node',
        name='vehicle_motor_control',
        namespace='vehicle',
        output='screen',
        parameters=[
            LaunchConfiguration('config_file'),
            {'interface_name': LaunchConfiguration('can_interface')}
        ],
        remappings=[
            # Remap to vehicle namespace
            ('joint_states', '/vehicle/joint_states'),
            ('enable_motors', '/vehicle/enable_motors'),
            ('disable_motors', '/vehicle/disable_motors'),
        ]
    )
    
    return LaunchDescription([
        config_file_arg,
        can_interface_arg,
        motor_controller_node,
    ])
