#!/usr/bin/env python3
"""
Gazebo launch file for vehicle_control robot with Gazebo Harmonic
Includes ViewAngle plugin for preset camera views

Usage:
  ros2 launch vehicle_control gazebo.launch.py                  # With GUI (default)
  ros2 launch vehicle_control gazebo.launch.py headless:=true   # Server-only, no GUI
  ros2 launch vehicle_control gazebo.launch.py ackermann:=true  # Ackermann geometry steering
"""

import os
from launch import LaunchDescription
from launch.actions import (
    IncludeLaunchDescription, SetEnvironmentVariable,
    DeclareLaunchArgument, OpaqueFunction, ExecuteProcess, TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Declare launch arguments
    ackermann_arg = DeclareLaunchArgument(
        'ackermann',
        default_value='false',
        description='Use Ackermann steering instead of velocity-based kinematics'
    )
    
    world_arg = DeclareLaunchArgument(
        'world',
        default_value='empty',
        description='World to load: empty or cotton_field'
    )
    
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time from Gazebo'
    )
    
    headless_arg = DeclareLaunchArgument(
        'headless',
        default_value='false',
        description='Run Gazebo without GUI (server-only mode)'
    )
    
    # Get the package directory
    pkg_share = get_package_share_directory('vehicle_control')
    
    # Path to URDF file
    urdf_file = os.path.join(pkg_share, 'urdf', 'vehicle.urdf')
    
    # Path to GUI config
    gui_config = os.path.join(pkg_share, 'simulation', 'config', 'gazebo_gui.config')
    
    # Path to world file
    world_name = LaunchConfiguration('world')
    world_file = os.path.join(pkg_share, 'worlds', 'cotton_field.sdf')
    
    # Read the URDF file
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    # Set Gazebo resource path for meshes and models
    # Include: parent dir (share/), package dir, and models dir
    # so that model:// URIs and relative mesh paths both resolve correctly
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=':'.join([
            os.path.join(pkg_share, '..'),
            pkg_share,
            os.path.join(pkg_share, 'models'),
        ])
    )

    # Robot State Publisher
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_desc}]
    )

    # Start Gazebo server + optional GUI
    # The server always runs with -s (server-only) so it won't be killed if the
    # GUI crashes (VS Code snap injects a broken libpthread that crashes the GUI
    # process; when server and GUI live in the same process the crash is fatal).
    # The GUI is launched as a separate process with a wrapper that sanitises the
    # environment to avoid the snap/glibc conflict.
    def launch_gazebo(context):
        headless = context.launch_configurations.get('headless', 'false')

        # Always launch the physics server separately with -s
        server = IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(get_package_share_directory('ros_gz_sim'),
                             'launch', 'gz_sim.launch.py')
            ]),
            launch_arguments={
                'gz_args': f'-s -r "{world_file}"',
            }.items()
        )

        actions = [server]

        if headless != 'true':
            # VS Code is installed as a snap and injects environment
            # variables (GTK_PATH, GTK_EXE_PREFIX, GIO_MODULE_DIR, etc.)
            # that point into /snap/code/…  The GTK modules at that path
            # carry RPATH entries to snap's core20 glibc, which conflicts
            # fatally with the host glibc (symbol lookup error on
            # libpthread.so).  We unset every snap-injected variable and
            # clean LD_LIBRARY_PATH / LD_PRELOAD to avoid the conflict.
            snap_vars_to_unset = [
                'GTK_PATH',
                'GTK_EXE_PREFIX',
                'GTK_IM_MODULE_FILE',
                'GIO_MODULE_DIR',
                'GSETTINGS_SCHEMA_DIR',
                'LOCPATH',
                'GDK_BACKEND',
                'LD_PRELOAD',
                # Also unset the _VSCODE_SNAP_ORIG backup copies
                'GTK_PATH_VSCODE_SNAP_ORIG',
                'GTK_EXE_PREFIX_VSCODE_SNAP_ORIG',
                'GTK_IM_MODULE_FILE_VSCODE_SNAP_ORIG',
                'GIO_MODULE_DIR_VSCODE_SNAP_ORIG',
                'GSETTINGS_SCHEMA_DIR_VSCODE_SNAP_ORIG',
                'LOCPATH_VSCODE_SNAP_ORIG',
                'GDK_BACKEND_VSCODE_SNAP_ORIG',
            ]

            # Build a clean LD_LIBRARY_PATH without any snap paths
            current_ld = os.environ.get('LD_LIBRARY_PATH', '')
            clean_ld = ':'.join(
                p for p in current_ld.split(':')
                if p and '/snap/' not in p
            )

            # env -u VAR1 -u VAR2 … unsets each listed variable while
            # keeping the rest of the inherited environment intact.
            env_cmd = ['env']
            for var in snap_vars_to_unset:
                env_cmd += ['-u', var]
            env_cmd += [
                f'LD_LIBRARY_PATH={clean_ld}',
                'gz', 'sim', '-g', '--gui-config', gui_config,
            ]

            gui = ExecuteProcess(
                cmd=env_cmd,
                output='screen',
            )
            # Small delay so the server has time to start before the GUI
            # tries to connect.
            actions.append(TimerAction(period=2.0, actions=[gui]))

        return actions

    gazebo = OpaqueFunction(function=launch_gazebo)

    # Spawn the robot
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name', 'vehicle_control',
            '-topic', '/robot_description',
            '-x', '-10',
            '-y', '0.9', 
            '-z', '1.0',
            '-R', '1.5708',
            '-P', '0',
            '-Y', '0',
        ],
        output='screen'
    )

    # Bridge for clock and wheel/steering topics
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model',
            '/wheel/front/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/wheel/left/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/wheel/right/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/front@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/left@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/right@std_msgs/msg/Float64]gz.msgs.Double',
        ],
        output='screen'
    )

    # Kinematics node - CONDITIONAL: velocity-based (default)
    # Note: use_sim_time disabled — GZ→ROS clock bridge is unreliable on this system
    kinematics_node = Node(
        package='vehicle_control',
        executable='gazebo_kinematics_node',
        name='kinematics_node',
        output='screen',
        parameters=[{'use_sim_time': False}],
        condition=UnlessCondition(LaunchConfiguration('ackermann'))
    )

    # Ackermann steering node - CONDITIONAL: Ackermann geometry
    ackermann_node = Node(
        package='vehicle_control',
        executable='gazebo_ackermann_steering',
        name='ackermann_steering',
        output='screen',
        parameters=[{'use_sim_time': False}],
        condition=IfCondition(LaunchConfiguration('ackermann'))
    )

    return LaunchDescription([
        ackermann_arg,
        world_arg,
        use_sim_time_arg,
        headless_arg,
        gz_resource_path,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
        kinematics_node,
        ackermann_node,
    ])
