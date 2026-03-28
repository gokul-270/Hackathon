#!/usr/bin/env python3
"""
Simple RViz launch file for viewing MG6010 robot.
Uses MG6010_FLU.urdf with package://robot_description/meshes/
"""

import os
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Get package directory
    pkg_dir = get_package_share_directory('robot_description')
    
    # URDF file path
    urdf_file = os.path.join(pkg_dir, 'urdf', 'MG6010_FLU.urdf')
    
    # Read URDF content directly
    with open(urdf_file, 'r') as f:
        robot_description_content = f.read()
    
    # RViz config file
    rviz_config = os.path.join(pkg_dir, 'config', 'view_robot.rviz')
    
    # Robot State Publisher
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content,
            'use_sim_time': False,
        }]
    )
    
    # Joint State Publisher GUI - for interactive joint control
    joint_state_publisher_gui = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
    )
    
    # RViz
    rviz_args = ['-d', rviz_config] if os.path.exists(rviz_config) else []
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=rviz_args,
    )
    
    return LaunchDescription([
        robot_state_publisher,
        joint_state_publisher_gui,
        rviz,
    ])
