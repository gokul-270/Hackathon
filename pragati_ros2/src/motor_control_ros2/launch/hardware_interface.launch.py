# Copyright (c) 2024 Open Source Robotics Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http:// www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Launch file for MG6010 hardware interface with ROS2 Control
This launch file demonstrates the complete low-level hardware interface integration
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # Declare arguments
    declared_arguments = []
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_sim",
            default_value="false",
            description="Start robot in Gazebo simulation",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_mock_hardware",
            default_value="false",
            description="Start robot with "\
                   "mock hardware mirroring command to its states",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "slowdown",
            default_value="3.0",
            description="Slowdown factor of the RRbot"
        )
    )

    # Initialize Arguments
    use_sim = LaunchConfiguration("use_sim")
    use_mock_hardware = LaunchConfiguration("use_mock_hardware")
    slowdown = LaunchConfiguration("slowdown")

    # Get URDF via xacro
    robot_description_content = Command(
        [
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ",
            PathJoinSubstitution(
                [
                    FindPackageShare("robot_description"),
                    "urdf",
                    "robot.urdf.xacro",
                ]
            ),
            " ",
            "use_sim:=",
            use_sim,
            " ",
            "use_mock_hardware:=",
            use_mock_hardware,
            " ",
            "slowdown:=",
            slowdown,
        ]
    )

    robot_description = {"robot_description": robot_description_content}

    # Hardware interface configuration
    hardware_config_file = PathJoinSubstitution(
        [
            FindPackageShare("motor_control_ros2"),
            "config",
            "hardware_interface.yaml",
        ]
    )

    # Controller manager configuration
    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_description, hardware_config_file],
        output="both",
        remappings=[
            ("~/robot_description", "/robot_description"),
        ],
    )

    # Robot state publisher
    robot_state_pub_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="both",
        parameters=[robot_description],
    )

    # Joint state broadcaster spawner
    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "--controller-manager", "/controller_manager"],
    )

    # Position controller spawner
    position_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["position_controller", "--controller-manager", "/controller_manager"],
    )

    # Delay position controller start after joint state broadcaster
    delay_position_controller_spawner_after_joint_state_broadcaster_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[position_controller_spawner],
        )
    )

    # MG6010 motor control node (using test node for production)
    mg6010_controller_node = Node(
        package="motor_control_ros2",
        executable="mg6010_test_node",
        name="mg6010_controller",
        output="screen",
        parameters=[{
            'interface_name': 'can0',
            'baud_rate': 500000,
            'node_id': 1,
            'mode': 'status'
        }],
    )

    nodes = [
        control_node,
        robot_state_pub_node,
        joint_state_broadcaster_spawner,
        delay_position_controller_spawner_after_joint_state_broadcaster_spawner,
        mg6010_controller_node,
    ]

    return LaunchDescription(declared_arguments + nodes)
