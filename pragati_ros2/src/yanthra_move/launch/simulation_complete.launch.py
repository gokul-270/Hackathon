#!/usr/bin/env python3
"""
Complete Simulation Launch for Pragati Arm with Yanthra Move
=============================================================

Uses MG6010_FLU.urdf from robot_description with:
  - Gazebo native JointPositionController per joint (no ros2_control)
  - Command topics: /joint2_cmd, /joint3_cmd, /joint4_cmd, /joint5_cmd
  - Joint states bridged to /joint_states

Launches:
1. Gazebo Harmonic with MG6010_FLU.urdf
2. ros_gz_bridge for joint commands + clock + joint states
3. Yanthra Move node with 4-position scanning (L1, L2, L3, L4)

Usage:
    ros2 launch yanthra_move simulation_complete.launch.py

    # Move a joint directly (Float64 → Gazebo):
    ros2 topic pub --once /joint3_cmd std_msgs/msg/Float64 "data: -0.5"
    ros2 topic pub --once /joint4_cmd std_msgs/msg/Float64 "data: 0.1"

    # Trigger yanthra_move cycle:
    ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "data: true"
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, IncludeLaunchDescription,
    TimerAction, LogInfo, SetEnvironmentVariable
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # Get package directories
    robot_description_share = get_package_share_directory('robot_description')
    yanthra_move_share = get_package_share_directory('yanthra_move')

    # ── Files ────────────────────────────────────────────────────
    urdf_file = os.path.join(robot_description_share, 'urdf', 'MG6010_FLU.urdf')
    # Gazebo GUI config with ViewAngle plugin (multi-angle view buttons)
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(yanthra_move_share))))  # up to pragati_ros2/
    gui_config = os.path.join(workspace_root, 'config', 'gazebo_gui.config')

    with open(urdf_file, 'r') as f:
        robot_description_content = f.read()

    # ── Launch arguments ─────────────────────────────────────────
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz', default_value='false',
        description='Launch RViz for visualization'
    )

    # ── Environment for Gazebo mesh resolution ───────────────────
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=os.pathsep.join([
            os.path.dirname(robot_description_share),
            robot_description_share,
            os.environ.get('GZ_SIM_RESOURCE_PATH', '')
        ])
    )

    # ══════════════════════════════════════════════════════════════
    # 1. Robot State Publisher
    # ══════════════════════════════════════════════════════════════
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content,
            'use_sim_time': True
        }]
    )

    # ══════════════════════════════════════════════════════════════
    # 2a. Static TF: world → base_link (matches spawn -z 0.1)
    #     Connects robot TF tree to the "world" frame so that
    #     TF lookups like camera_link→world succeed.
    # ══════════════════════════════════════════════════════════════
    static_tf_world = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_world_to_base',
        arguments=['0', '0', '0.1', '0', '0', '0', 'world', 'base_link'],
        parameters=[{'use_sim_time': True}],
        output='screen'
    )

    # ══════════════════════════════════════════════════════════════
    # 2b. Gazebo Harmonic (with GUI)
    # ══════════════════════════════════════════════════════════════
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py'
            ])
        ]),
        launch_arguments={
            'gz_args': f'-r empty.sdf --gui-config "{gui_config}"' if os.path.exists(gui_config)
                        else '-r empty.sdf',
            'on_exit_shutdown': 'true'
        }.items()
    )

    # ══════════════════════════════════════════════════════════════
    # 3. Spawn robot into Gazebo
    # ══════════════════════════════════════════════════════════════
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-topic', 'robot_description',
            '-entity', 'MG6010',
            '-z', '0.1'
        ],
        output='screen'
    )

    # ══════════════════════════════════════════════════════════════
    # 4. ros_gz_bridge: joint commands + clock + joint states
    #    No ros2_control needed — native Gazebo JointPositionController
    # ══════════════════════════════════════════════════════════════
    gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            # Clock: Gazebo → ROS2
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            # Joint commands: ROS2 → Gazebo (Float64 → gz.msgs.Double)
            # Bridge uses /jointN_cmd internally, remapped from production topic names below
            '/joint2_cmd@std_msgs/msg/Float64]gz.msgs.Double',
            '/joint3_cmd@std_msgs/msg/Float64]gz.msgs.Double',
            '/joint4_cmd@std_msgs/msg/Float64]gz.msgs.Double',
            '/joint5_cmd@std_msgs/msg/Float64]gz.msgs.Double',
            # Joint states: Gazebo → ROS2
            '/world/empty/model/MG6010/joint_state@sensor_msgs/msg/JointState[gz.msgs.Model',
        ],
        remappings=[
            ('/world/empty/model/MG6010/joint_state', '/joint_states'),
            # Map production topic names to Gazebo bridge topics
            # yanthra_move publishes to /jointN_position_controller/command (same as production)
            # Bridge internally uses /jointN_cmd which matches URDF plugin <topic> names
            ('/joint3_cmd', '/joint3_position_controller/command'),
            ('/joint4_cmd', '/joint4_position_controller/command'),
            ('/joint5_cmd', '/joint5_position_controller/command'),
        ],
        output='screen'
    )

    # ══════════════════════════════════════════════════════════════
    # 5. Yanthra Move (delayed 5s for Gazebo startup)
    # ══════════════════════════════════════════════════════════════
    yanthra_move_node = TimerAction(
        period=5.0,
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

    # ══════════════════════════════════════════════════════════════
    # 6. Optional RViz
    # ══════════════════════════════════════════════════════════════
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_rviz')),
    )

    # ── Startup info ─────────────────────────────────────────────
    startup_info = LogInfo(
        msg=[
            '\n',
            '╔════════════════════════════════════════════════════════════╗\n',
            '║  Pragati Arm Simulation (Gazebo Native Controllers)        ║\n',
            '╠════════════════════════════════════════════════════════════╣\n',
            '║  URDF: robot_description/urdf/MG6010_FLU.urdf              ║\n',
            '║  Joint controllers: Gazebo JointPositionController         ║\n',
            '║                                                            ║\n',
            '║  Move joints (Float64):                                    ║\n',
            '║    ros2 topic pub --once /joint3_cmd                       ║\n',
            '║        std_msgs/msg/Float64 "data: -0.5"                   ║\n',
            '║    ros2 topic pub --once /joint4_cmd                       ║\n',
            '║        std_msgs/msg/Float64 "data: 0.1"                    ║\n',
            '║                                                            ║\n',
            '║  Trigger yanthra_move cycle:                               ║\n',
            '║    ros2 topic pub --once /start_switch/command             ║\n',
            '║        std_msgs/msg/Bool "data: true"                      ║\n',
            '╚════════════════════════════════════════════════════════════╝\n'
        ]
    )

    return LaunchDescription([
        use_rviz_arg,
        gz_resource_path,
        startup_info,

        # Gazebo + Robot
        robot_state_publisher,
        static_tf_world,
        gazebo,
        spawn_robot,
        gz_bridge,

        # Yanthra Move (delayed)
        yanthra_move_node,

        # Optional
        rviz_node,
    ])

