#!/usr/bin/env python3
"""
Headless Simulation Launch for Pragati Arm with Yanthra Move
=============================================================

Launches simulation without GUI (headless mode for testing)

Launches:
1. Gazebo Harmonic simulation (headless) with robot
2. Simulation bridge (joint commands → trajectory controller)
3. Yanthra Move node with 4-position scanning (L1, L2, L3, L4)

Usage:
    ros2 launch yanthra_move simulation_headless.launch.py
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
    TimerAction, LogInfo
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Get package directories
    robot_description_share = get_package_share_directory('robot_description')
    yanthra_move_share = get_package_share_directory('yanthra_move')
    
    # Launch arguments
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=os.path.join(robot_description_share, 'worlds', 'default.sdf'),
        description='Path to world file for Gazebo'
    )
    
    # 1. Launch Gazebo simulation (headless) with robot
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            os.path.join(robot_description_share, 'launch', 'gazebo_sim_headless.launch.py')
        ]),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'use_sim_time': 'true'
        }.items()
    )
    
    # 2. Launch simulation bridge (delayed to allow Gazebo to start)
    simulation_bridge_node = TimerAction(
        period=5.0,
        actions=[
            Node(
                package='yanthra_move',
                executable='simulation_bridge',
                name='simulation_bridge',
                output='screen',
                parameters=[{
                    'use_sim_time': True
                }]
            )
        ]
    )
    
    # 3. Launch Yanthra Move with simulation config (delayed)
    yanthra_move_node = TimerAction(
        period=7.0,
        actions=[
            Node(
                package='yanthra_move',
                executable='yanthra_move_node',
                name='yanthra_move',
                output='screen',
                parameters=[
                    os.path.join(yanthra_move_share, 'config', 'simulation.yaml'),
                    {
                        'use_sim_time': True,
                        'simulation_mode': True
                    }
                ]
            )
        ]
    )
    
    # Info messages
    startup_info = LogInfo(
        msg=[
            '\n',
            '╔════════════════════════════════════════════════════════════╗\n',
            '║  Pragati Arm Headless Simulation with Yanthra Move         ║\n',
            '╠════════════════════════════════════════════════════════════╣\n',
            '║  • Gazebo Harmonic (headless) starting...                  ║\n',
            '║  • Simulation bridge (in 5s)                               ║\n',
            '║  • Yanthra Move with 4-position scanning (in 7s)           ║\n',
            '║                                                            ║\n',
            '║  4 Scanning Positions:                                     ║\n',
            '║    L1: -0.075m (left)                                      ║\n',
            '║    L2: -0.025m (left-center)                               ║\n',
            '║    L3: +0.025m (right-center)                              ║\n',
            '║    L4: +0.075m (right) ← NEW POSITION                      ║\n',
            '║                                                            ║\n',
            '║  Monitor with:                                             ║\n',
            '║    ros2 topic echo /joint_states                           ║\n',
            '║    ros2 control list_controllers                           ║\n',
            '╚════════════════════════════════════════════════════════════╝\n'
        ]
    )
    
    return LaunchDescription([
        # Arguments
        world_arg,
        
        # Info
        startup_info,
        
        # Nodes
        gazebo_launch,
        simulation_bridge_node,
        yanthra_move_node,
    ])
