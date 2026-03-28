#!/usr/bin/env python3
# Copyright 2025 Pragati Robotics
# Launch file for ODrive CANSimple ROS2 control - Vehicle Drive Wheels

from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    """Generate launch description for ODrive vehicle drive wheels control node"""
    
    # Get package directory
    pkg_dir = get_package_share_directory('odrive_control_ros2')
    
    # Configuration file path
    config_file = os.path.join(pkg_dir, 'config', 'production.yaml')
    
    # ODrive service node
    odrive_node = Node(
        package='odrive_control_ros2',
        executable='odrive_service_node',
        name='odrive_service_node',
        output='screen',
        parameters=[config_file],
        emulate_tty=True,
    )
    
    return LaunchDescription([
        odrive_node,
    ])
