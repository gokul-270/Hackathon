#!/usr/bin/env python3
"""
MG6010 Motor Controller Launch File

Launches the production motor controller lifecycle node for MG6010 motors.
Provides full motor control including homing, position/velocity/torque control,
and joint_states publishing.

The node uses rclcpp_lifecycle::LifecycleNode. By default, auto_activate=true
causes the node to automatically transition through configure -> activate on
startup. Set auto_activate:=false for manual lifecycle management via
ros2 lifecycle commands.

Usage:
  ros2 launch motor_control_ros2 mg6010_controller.launch.py
  ros2 launch motor_control_ros2 mg6010_controller.launch.py can_interface:=can0
  ros2 launch motor_control_ros2 mg6010_controller.launch.py auto_activate:=false
  ros2 launch motor_control_ros2 mg6010_controller.launch.py enable_pid_tuning:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode, Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    """Generate launch description for MG6010 motor controller."""

    # Declare launch arguments
    declared_arguments = []

    declared_arguments.append(
        DeclareLaunchArgument(
            'can_interface',
            default_value='can0',
            description='CAN interface name (e.g., can0, can1)',
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            'config_file',
            default_value='production.yaml',
            description='Motor configuration YAML file',
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            'simulation_mode',
            default_value='false',
            description='Run with simulated motors (no CAN hardware required)',
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            'auto_activate',
            default_value='true',
            description=(
                'Automatically transition through configure -> activate on startup. '
                'Set to false for manual lifecycle management.'
            ),
        )
    )

    declared_arguments.append(
        DeclareLaunchArgument(
            'enable_pid_tuning', default_value='false', description='Launch PID tuning service node'
        )
    )

    # Get launch arguments
    can_interface = LaunchConfiguration('can_interface')
    config_file_name = LaunchConfiguration('config_file')
    simulation_mode = LaunchConfiguration('simulation_mode')
    auto_activate = LaunchConfiguration('auto_activate')

    # Config file path
    config_file = PathJoinSubstitution(
        [FindPackageShare('motor_control_ros2'), 'config', config_file_name]
    )

    # MG6010 Controller Node (Lifecycle Node)
    # auto_activate is handled inside main() via the auto_activate ROS parameter.
    # We do NOT use the launch LifecycleNode autostart= parameter because that
    # uses external event handlers that would conflict with internal auto-activation.
    mg6010_node = LifecycleNode(
        package='motor_control_ros2',
        executable='mg6010_controller_node',
        name='motor_control',
        namespace='',
        output='screen',
        parameters=[
            config_file,
            {
                'simulation_mode': simulation_mode,
                'auto_activate': auto_activate,
            },
        ],
        arguments=['--ros-args', '--log-level', 'info'],
    )

    # Startup message
    startup_msg = LogInfo(
        msg=[
            '\n',
            '=' * 70,
            '\n',
            'MG6010 Motor Controller (Lifecycle Node)\n',
            '=' * 70,
            '\n',
            'CAN Interface:   ',
            can_interface,
            '\n',
            'Config File:     ',
            config_file_name,
            '\n',
            'Simulation Mode: ',
            simulation_mode,
            '\n',
            'Auto Activate:   ',
            auto_activate,
            '\n',
            '=' * 70,
            '\n',
            'Lifecycle management:\n',
            '  ros2 lifecycle list /motor_control\n',
            '  ros2 lifecycle set /motor_control configure\n',
            '  ros2 lifecycle set /motor_control activate\n',
            '=' * 70,
            '\n',
        ]
    )

    # PID Tuning Service Node (opt-in via enable_pid_tuning:=true)
    pid_tuning_node = Node(
        package='pid_tuning',
        executable='pid_tuning_service',
        name='pid_tuning_service',
        output='screen',
        condition=IfCondition(LaunchConfiguration('enable_pid_tuning')),
    )

    # Nodes to launch
    nodes = [
        startup_msg,
        mg6010_node,
        pid_tuning_node,
    ]

    return LaunchDescription(declared_arguments + nodes)
