#!/usr/bin/env python3
"""
Gazebo Headless Simulation Launch for MG6010 Robot
(Server-only, no GUI - useful for testing and debugging)

Usage:
    ros2 launch robot_description gazebo_sim_headless.launch.py
"""

import os
import re
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
    SetEnvironmentVariable
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import xacro


def generate_launch_description():
    # Get package directory
    pkg_share = get_package_share_directory('robot_description')
    
    # Paths to files
    urdf_file = os.path.join(pkg_share, 'urdf', 'MG6010_gazebo.xacro')
    world_file = os.path.join(pkg_share, 'worlds', 'default.sdf')
    
    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    world = LaunchConfiguration('world', default=world_file)
    
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true', description='Use simulation time'
    )
    declare_world = DeclareLaunchArgument(
        'world', default_value=world_file, description='Path to world file'
    )
    
    # Process URDF/Xacro
    robot_description_content = xacro.process_file(urdf_file).toxml()
    
    # Fix mesh paths for Gazebo Harmonic (convert package:// to file://)
    def fix_mesh_paths(urdf_content, pkg_path):
        """Replace package://robot_description/ with file://absolute/path/"""
        pattern = r'package://robot_description/(meshes/[^"]+)'
        def replace_path(match):
            relative_path = match.group(1)
            absolute_path = os.path.join(pkg_path, relative_path)
            return f'file://{absolute_path}'
        return re.sub(pattern, replace_path, urdf_content)
    
    robot_description_content = fix_mesh_paths(robot_description_content, pkg_share)
    robot_description = {'robot_description': robot_description_content}
    
    # Set resource paths for Gazebo
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=[
            pkg_share, os.pathsep,
            os.path.dirname(pkg_share), os.pathsep,
            os.environ.get('GZ_SIM_RESOURCE_PATH', '')
        ]
    )
    
    ign_resource_path = SetEnvironmentVariable(
        name='IGN_GAZEBO_RESOURCE_PATH',
        value=[
            pkg_share, os.pathsep,
            os.path.dirname(pkg_share), os.pathsep,
            os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')
        ]
    )
    
    # Robot State Publisher
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[robot_description, {'use_sim_time': use_sim_time}]
    )
    
    # Gazebo Server Only (headless)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'),
                'launch',
                'gz_sim.launch.py'
            ])
        ]),
        launch_arguments={
            'gz_args': ['-r -v 4 -s ', world],  # -s = server only
            'on_exit_shutdown': 'true'
        }.items()
    )
    
    # Spawn Robot
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', 'MG6010',
            '-topic', 'robot_description',
            '-z', '0.5',
        ],
        output='screen'
    )
    
    # ROS-Gazebo Bridges
    gz_ros_bridge_clock = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
        output='screen'
    )
    
    gz_ros_bridge_imu = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/imu@sensor_msgs/msg/Imu[gz.msgs.IMU'],
        output='screen'
    )
    
    return LaunchDescription([
        gz_resource_path,
        ign_resource_path,
        declare_use_sim_time,
        declare_world,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        gz_ros_bridge_clock,
        gz_ros_bridge_imu,
    ])
