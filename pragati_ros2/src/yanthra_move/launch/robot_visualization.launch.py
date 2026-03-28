#!/usr/bin/env python3

# Copyright 2025 Pragati Robotics
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
PRAGATI ROBOT VISUALIZATION LAUNCH FILE
=======================================

Essential robot visualization launch file for the Pragati robotic arm system.
Provides RViz2 visualization, robot model display, and TF frame visualization.

Usage:
  ros2 launch yanthra_move robot_visualization.launch.py
  ros2 launch yanthra_move robot_visualization.launch.py use_sim_time:=true
  ros2 launch yanthra_move robot_visualization.launch.py rviz_config:=/path/to/config.rviz
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # Launch configuration variables
    use_sim_time = LaunchConfiguration('use_sim_time')
    rviz_config = LaunchConfiguration('rviz_config')
    
    # Declare launch arguments
    declare_use_sim_time_cmd = DeclareLaunchArgument(
        name='use_sim_time',
        default_value='false',
        description='Use simulation (Gazebo) clock if true')
        
    declare_rviz_config_cmd = DeclareLaunchArgument(
        name='rviz_config',
        default_value='',
        description='Path to RViz config file (optional)')

    # Get robot description
    try:
        robo_desc_share = FindPackageShare(package='robot_description').find('robot_description')
        urdf_file = os.path.join(robo_desc_share, 'urdf', 'MG6010_FLU.urdf')
        
        # Read URDF file content
        with open(urdf_file, 'r') as infp:
            robot_desc = infp.read()
            
        if not robot_desc.strip():
            raise ValueError("URDF file is empty")
            
    except Exception as e:
        print(f"WARNING: Failed to load URDF file: {e}")
        # Use a minimal robot description as fallback
        robot_desc = '''<?xml version="1.0"?>
<robot name="pragati_robot">
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.1 0.1 0.1"/>
      </geometry>
      <material name="blue">
        <color rgba="0 0 1 1"/>
      </material>
    </visual>
  </link>
  <joint name="world_to_base" type="fixed">
    <parent link="world"/>
    <child link="base_link"/>
    <origin xyz="0 0 0" rpy="0 0 0"/>
  </joint>
  <link name="world"/>
</robot>'''

    # Robot State Publisher - publishes robot_description and TF transforms
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_desc,
            'use_sim_time': use_sim_time
        }],
        output='screen'
    )

    # Joint State Publisher - publishes joint positions for RViz
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher', 
        name='joint_state_publisher',
        parameters=[{
            'use_sim_time': use_sim_time
        }],
        output='screen'
    )

    # RViz2 for robot visualization
    rviz_args = []
    
    # Try to find default RViz config if none provided
    try:
        robo_desc_share = get_package_share_directory('robot_description')
        default_rviz_config = os.path.join(robo_desc_share, 'rviz', 'pragati.rviz')
        if not os.path.exists(default_rviz_config):
            default_rviz_config = os.path.join(robo_desc_share, 'rviz', 'display.rviz')
        if os.path.exists(default_rviz_config):
            rviz_args = ['-d', default_rviz_config]
    except:
        pass
    
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=rviz_args,
        parameters=[{
            'use_sim_time': use_sim_time
        }],
        output='screen'
    )

    # Static TF publisher for world frame
    static_tf_world = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='world_tf',
        arguments=['0', '0', '0', '0', '0', '0', 'map', 'world'],
        parameters=[{'use_sim_time': use_sim_time}]
    )

    # Create the launch description
    ld = LaunchDescription()

    # Declare the launch options
    ld.add_action(declare_use_sim_time_cmd)
    ld.add_action(declare_rviz_config_cmd)

    # Add nodes
    ld.add_action(robot_state_publisher_node)
    ld.add_action(joint_state_publisher_node)
    ld.add_action(static_tf_world)
    ld.add_action(rviz_node)

    return ld
