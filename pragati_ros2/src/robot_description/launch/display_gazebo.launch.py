#!/usr/bin/env python3
"""
Display MG6010 Robot in RViz with Gazebo Simulation

Launches both Gazebo simulation and RViz for visualization

Usage:
    ros2 launch robot_description display_gazebo.launch.py
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('robot_description')
    
    # Include Gazebo simulation launch
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            os.path.join(pkg_share, 'launch', 'gazebo_sim.launch.py')
        ])
    )
    
    # RViz configuration file
    rviz_config_file = os.path.join(pkg_share, 'config', 'robot_view.rviz')
    
    # RViz Node
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file] if os.path.exists(rviz_config_file) else []
    )
    
    return LaunchDescription([
        gazebo_launch,
        rviz_node,
    ])
