#!/usr/bin/env python3
"""
Launch file to view MG6010 robot in RViz2.
This allows you to visualize the robot model and check mesh loading.
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Get package directory
    pkg_robot_description = get_package_share_directory('robot_description')
    
    # URDF file path - using MG6010_FLU.urdf
    default_urdf = os.path.join(pkg_robot_description, 'urdf', 'MG6010_FLU.urdf')
    
    # RViz config file path
    rviz_config = os.path.join(pkg_robot_description, 'config', 'view_robot.rviz')
    
    # Launch arguments
    urdf_file_arg = DeclareLaunchArgument(
        'urdf_file',
        default_value=default_urdf,
        description='Path to the URDF file to load'
    )
    
    use_gui_arg = DeclareLaunchArgument(
        'use_gui',
        default_value='true',
        description='Whether to start joint_state_publisher_gui'
    )
    
    # Robot description parameter - read URDF file
    robot_description_content = ParameterValue(
        Command(['cat ', LaunchConfiguration('urdf_file')]),
        value_type=str
    )
    
    # Robot State Publisher node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content,
            'use_sim_time': False,
        }]
    )
    
    # Joint State Publisher GUI node - for moving joints interactively
    joint_state_publisher_gui_node = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
    )
    
    # RViz2 node
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config] if os.path.exists(rviz_config) else [],
    )
    
    return LaunchDescription([
        urdf_file_arg,
        use_gui_arg,
        robot_state_publisher_node,
        joint_state_publisher_gui_node,
        rviz_node,
    ])
