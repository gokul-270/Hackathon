#!/usr/bin/env python3
"""
Gazebo Simulation Launch for MG6010 Robot

This launch file:
1. Starts Gazebo Harmonic with a custom world
2. Spawns the MG6010 robot with ros2_control
3. Loads and starts all controllers
4. Publishes robot state to TF

Usage:
    ros2 launch robot_description gazebo_sim.launch.py
    
Arguments:
    world - Path to world file (default: empty.sdf)
    use_sim_time - Use simulation time (default: true)
    x, y, z - Initial spawn position
    roll, pitch, yaw - Initial spawn orientation
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
    RegisterEventHandler, TimerAction, SetEnvironmentVariable
)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import xacro


def generate_launch_description():
    # Get package directory
    pkg_share = get_package_share_directory('robot_description')
    
    # Paths to files
    urdf_file = os.path.join(pkg_share, 'urdf', 'MG6010_FLU.urdf')  # Use simple URDF like MG6010
    world_file = os.path.join(pkg_share, 'worlds', 'default.sdf')
    controller_config = os.path.join(pkg_share, 'config', 'controllers.yaml')
    
    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    world = LaunchConfiguration('world', default=world_file)
    x = LaunchConfiguration('x', default='0.0')
    y = LaunchConfiguration('y', default='0.0')
    z = LaunchConfiguration('z', default='0.5')
    roll = LaunchConfiguration('roll', default='0.0')
    pitch = LaunchConfiguration('pitch', default='0.0')
    yaw = LaunchConfiguration('yaw', default='0.0')
    
    # Declare launch arguments
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time'
    )
    
    declare_world = DeclareLaunchArgument(
        'world',
        default_value=world_file,
        description='Path to world file'
    )
    
    declare_x = DeclareLaunchArgument('x', default_value='0.0', description='X position')
    declare_y = DeclareLaunchArgument('y', default_value='0.0', description='Y position')
    declare_z = DeclareLaunchArgument('z', default_value='0.5', description='Z position')
    declare_roll = DeclareLaunchArgument('roll', default_value='0.0', description='Roll angle')
    declare_pitch = DeclareLaunchArgument('pitch', default_value='0.0', description='Pitch angle')
    declare_yaw = DeclareLaunchArgument('yaw', default_value='0.0', description='Yaw angle')
    
    # Process URDF (read file directly, not xacro)
    with open(urdf_file, 'r') as f:
        robot_description_content = f.read()
    robot_description = {'robot_description': robot_description_content}
    
    # Set GZ_SIM_RESOURCE_PATH for Gazebo to find meshes
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=os.pathsep.join([
            os.path.dirname(pkg_share),  # Parent dir for package:// URIs
            pkg_share,
            os.environ.get('GZ_SIM_RESOURCE_PATH', '')
        ])
    )
    
    # ==================== NODES ====================
    
    # Robot State Publisher
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[robot_description, {'use_sim_time': use_sim_time}]
    )
    
    # Gazebo Harmonic (gz-sim)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'),
                'launch',
                'gz_sim.launch.py'
            ])
        ]),
        launch_arguments={
            'gz_args': ['-r -v 4 ', world],
            'on_exit_shutdown': 'true'
        }.items()
    )
    
    # Spawn Robot in Gazebo
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', 'MG6010',
            '-topic', 'robot_description',
            '-x', x,
            '-y', y,
            '-z', z,
            '-R', roll,
            '-P', pitch,
            '-Y', yaw,
        ],
        output='screen'
    )
    
    # ROS-Gazebo Bridge for Clock
    gz_ros_bridge_clock = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
        output='screen'
    )
    
    # ROS-Gazebo Bridge for IMU
    gz_ros_bridge_imu = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['/imu@sensor_msgs/msg/Imu[gz.msgs.IMU'],
        output='screen'
    )
    
    # Note: Camera bridge removed temporarily due to sensor rendering issues
    
    # ==================== CONTROLLERS ====================
    # Note: Controllers are now auto-started via controllers.yaml
    # No need for manual loading commands
    
    # ==================== LAUNCH DESCRIPTION ====================
    
    return LaunchDescription([
        # Environment
        gz_resource_path,
        
        # Arguments
        declare_use_sim_time,
        declare_world,
        declare_x,
        declare_y,
        declare_z,
        declare_roll,
        declare_pitch,
        declare_yaw,
        
        # Nodes
        robot_state_publisher,
        gazebo,
        spawn_robot,
        gz_ros_bridge_clock,
        gz_ros_bridge_imu,
    ])
