#!/usr/bin/env python3
"""
Launch file for Cotton Detection C++ Node with DepthAI Integration

This launch file starts the C++ cotton detection node which runs YOLO
neural detection on the OAK-D Lite's Myriad X VPU via DepthAI.

Usage:
    # With DepthAI camera (default)
    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

    # Simulation mode (synthetic detections, no camera required)
    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true

    # With custom configuration
    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
        config_file:=/path/to/custom_config.yaml

Author: Cotton Detection Team
Date: October 8, 2025
Phase: 3.4 - Features & Quality
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, ExecuteProcess
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.conditions import IfCondition, UnlessCondition
import os


def generate_launch_description():
    """Generate launch description with cotton detection C++ node."""

    # Declare launch arguments
    declare_use_depthai = DeclareLaunchArgument(
        'use_depthai',
        default_value='true',
        description='Enable DepthAI camera integration (OAK-D Lite)',
    )

    declare_simulation_mode = DeclareLaunchArgument(
        'simulation_mode',
        default_value='false',
        description='Run in simulation mode (synthetic detections)',
    )

    declare_debug_output = DeclareLaunchArgument(
        'debug_output', default_value='false', description='Enable debug image output'
    )

    declare_config_file = DeclareLaunchArgument(
        'config_file',
        default_value=PathJoinSubstitution(
            [FindPackageShare('cotton_detection_ros2'), 'config', 'production.yaml']
        ),
        description='Path to YAML configuration file',
    )

    declare_detection_mode = DeclareLaunchArgument(
        'detection_mode',
        default_value='depthai_direct',
        description='Detection mode (only depthai_direct is supported)',
    )

    declare_camera_topic = DeclareLaunchArgument(
        'camera_topic', default_value='/camera/image_raw', description='Input camera image topic'
    )

    declare_model_path = DeclareLaunchArgument(
        'depthai_model_path',
        default_value=PathJoinSubstitution(
            [FindPackageShare('cotton_detection_ros2'), 'models', 'yolov112.blob']
        ),
        description='Path to DepthAI YOLO model blob',
    )

    declare_num_classes = DeclareLaunchArgument(
        'depthai_num_classes',
        default_value='2',
        description='Number of classes in model (1=YOLOv8, 2=YOLOv11)',
    )

    declare_confidence_threshold = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.5',
        description='Detection confidence threshold (0.0-1.0)',
    )

    declare_log_level = DeclareLaunchArgument(
        'log_level', default_value='info', description='Logging level (debug, info, warn, error)'
    )

    declare_auto_pause = DeclareLaunchArgument(
        'auto_pause',
        default_value='false',
        description='Auto-pause camera after detection (thermal management)',
    )

    # Note: publish_fallback_on_zero is controlled solely by config YAML
    # (production.yaml). No launch argument — avoids override confusion.

    # Launch configurations
    use_depthai = LaunchConfiguration('use_depthai')
    simulation_mode = LaunchConfiguration('simulation_mode')
    debug_output = LaunchConfiguration('debug_output')
    config_file = LaunchConfiguration('config_file')
    detection_mode = LaunchConfiguration('detection_mode')
    camera_topic = LaunchConfiguration('camera_topic')
    model_path = LaunchConfiguration('depthai_model_path')
    num_classes = LaunchConfiguration('depthai_num_classes')
    confidence_threshold = LaunchConfiguration('confidence_threshold')
    log_level = LaunchConfiguration('log_level')
    auto_pause = LaunchConfiguration('auto_pause')

    # Cotton Detection C++ Node
    cotton_detection_node = Node(
        package='cotton_detection_ros2',
        executable='cotton_detection_node',
        name='cotton_detection_node',
        output='screen',
        parameters=[
            config_file,
            {
                # DepthAI Configuration
                'depthai.enable': use_depthai,
                'depthai.model_path': model_path,
                'depthai.num_classes': num_classes,
                'depthai.confidence_threshold': confidence_threshold,
                # Detection Configuration
                'detection_mode': detection_mode,
                'camera_topic': camera_topic,
                'enable_debug_output': debug_output,
                # Simulation
                'simulation_mode': simulation_mode,
                # Thermal management
                'depthai.auto_pause_after_detection': auto_pause,
                # Fallback positions — controlled by config YAML (production.yaml),
                # NOT overridden here. Removed launch arg override to avoid
                # contradicting the YAML config file.
                # See: openspec/changes/fix-fallback-on-zero-config/
            },
        ],
        arguments=['--ros-args', '--log-level', log_level],
        remappings=[
            ('camera/image_raw', camera_topic),
        ],
    )

    # Static TF publisher for camera frame (if using DepthAI direct)
    # This will be published by the node itself in Phase 2.2
    # static_tf_publisher = Node(
    #     package='tf2_ros',
    #     executable='static_transform_publisher',
    #     name='camera_to_base_link',
    #     arguments=['0', '0', '0.5', '0', '0', '0', 'base_link', 'camera_link'],
    #     condition=IfCondition(use_depthai)
    # )

    return LaunchDescription(
        [
            # Declare arguments
            declare_use_depthai,
            declare_simulation_mode,
            declare_debug_output,
            declare_config_file,
            declare_detection_mode,
            declare_camera_topic,
            declare_model_path,
            declare_num_classes,
            declare_confidence_threshold,
            declare_log_level,
            declare_auto_pause,
            # Nodes
            cotton_detection_node,
            # static_tf_publisher,  # Uncomment when TF2 support is added
        ]
    )


if __name__ == '__main__':
    generate_launch_description()
