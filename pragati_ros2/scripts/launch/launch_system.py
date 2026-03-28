#!/usr/bin/env python3

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command

def generate_launch_description():
    # Get the path to the URDF file
    urdf_file = '/home/uday/Downloads/pragati_ros2/pragati_robot_description.urdf'
    
    # Read the URDF file content
    with open(urdf_file, 'r') as f:
        robot_description_content = f.read()
    
    # Create robot state publisher node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[
            {'robot_description': robot_description_content}
        ],
        output='screen'
    )
    
    # Create joint state publisher node
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        output='screen'
    )
    
    # Create yanthra_move node with continuous_operation=false (note: spelling matches the parameter in code)
    yanthra_move_node = Node(
        package='yanthra_move',
        executable='yanthra_move_node',
        name='yanthra_move_node',
        parameters=[{
            'continous_operation': False
        }],
        output='screen'
    )
    
    return LaunchDescription([
        robot_state_publisher_node,
        joint_state_publisher_node,
        yanthra_move_node,
    ])

if __name__ == '__main__':
    generate_launch_description()