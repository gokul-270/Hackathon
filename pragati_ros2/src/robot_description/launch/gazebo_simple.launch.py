#!/usr/bin/env python3
"""
Simple Gazebo Launch for robot_description package
Exact replica of MG6010's working gazebo_with_views.launch.py
Uses MG6010_FLU.urdf
"""

import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Get the package directory
    pkg_share = get_package_share_directory('robot_description')
    
    # Path to URDF file - using FLU version
    urdf_file = os.path.join(pkg_share, 'urdf', 'MG6010_FLU.urdf')
    
    # Read the URDF file
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    # Set Gazebo resource path for meshes
    # This points to parent directory so package://robot_description/meshes/ works
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=os.path.join(pkg_share, '..')
    )

    # Robot State Publisher
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_desc}]
    )

    # Start Gazebo
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            os.path.join(get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')
        ]),
        launch_arguments={
            'gz_args': '-r empty.sdf',
        }.items()
    )

    # Spawn the robot
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', 'mg6010',
            '-topic', '/robot_description',
            '-x', '0',
            '-y', '0', 
            '-z', '0.1',
        ],
        output='screen'
    )

    # Bridge for clock
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
        output='screen'
    )

    return LaunchDescription([
        gz_resource_path,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
    ])
