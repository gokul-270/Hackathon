#!/usr/bin/env python3

"""
Launch file for Cotton Detection ROS2 Wrapper (Phase 1)

This launch file starts the ROS2 Python wrapper node that integrates
with the existing OakDTools/CottonDetect.py script.

Usage:
    ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

Parameters:
    - usb_mode: USB connection mode (usb2/usb3), default: usb2
    - blob_path: Path to YOLO blob file, default: yolov8v2.blob
    - confidence_threshold: Detection confidence threshold, default: 0.5
    - output_dir: Directory for output files, default: /tmp/cotton_detection
    - camera_frame: Camera optical frame ID, default: oak_rgb_camera_optical_frame
"""

import os
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Generate launch description for Cotton Detection ROS2 Wrapper."""
    
    # Declare launch arguments
    usb_mode_arg = DeclareLaunchArgument(
        'usb_mode',
        default_value='usb2',
        description='USB connection mode for OAK-D Lite (usb2 recommended for bandwidth)'
    )
    
    blob_path_arg = DeclareLaunchArgument(
        'blob_path',
        default_value='yolov8v2.blob',
        description='YOLO blob file name (relative to models directory)'
    )
    
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.5',
        description='Detection confidence threshold (0.0-1.0)'
    )
    
    iou_threshold_arg = DeclareLaunchArgument(
        'iou_threshold',
        default_value='0.5',
        description='IoU threshold for detection (0.0-1.0)'
    )
    
    output_dir_arg = DeclareLaunchArgument(
        'output_dir',
        default_value='/home/ubuntu/pragati_ros2/data/outputs',
        description='Output directory for cotton detection results (Phase 1 file-based integration)'
    )
    
    input_dir_arg = DeclareLaunchArgument(
        'input_dir',
        default_value='/home/ubuntu/pragati_ros2/data/inputs',
        description='Input directory for image captures'
    )
    
    camera_frame_arg = DeclareLaunchArgument(
        'camera_frame',
        default_value='oak_rgb_camera_optical_frame',
        description='Camera optical frame ID for TF tree'
    )
    
    publish_debug_image_arg = DeclareLaunchArgument(
        'publish_debug_image',
        default_value='true',
        description='Publish annotated debug images'
    )
    
    publish_pointcloud_arg = DeclareLaunchArgument(
        'publish_pointcloud',
        default_value='false',
        description='Publish point cloud data (not implemented in Phase 1)'
    )
    
    simulation_mode_arg = DeclareLaunchArgument(
        'simulation_mode',
        default_value='false',
        description='Run in simulation mode without hardware (generates synthetic detections for testing)'
    )
    
    # Get package share directory
    package_share = FindPackageShare('cotton_detection_ros2')
    
    # Cotton Detection ROS2 Wrapper Node
    wrapper_node = Node(
        package='cotton_detection_ros2',
        executable='cotton_detect_ros2_wrapper.py',
        name='cotton_detect_wrapper',
        output='screen',
        parameters=[{
            # Model configuration
            'blob_path': LaunchConfiguration('blob_path'),
            'confidence_threshold': LaunchConfiguration('confidence_threshold'),
            'iou_threshold': LaunchConfiguration('iou_threshold'),
            
            # Camera configuration
            'usb_mode': LaunchConfiguration('usb_mode'),
            'rgb_resolution': '1080p',
            'mono_resolution': '400p',
            
            # Stereo configuration (matching ROS1 CottonDetect.py)
            'stereo_preset': 'HIGH_ACCURACY',
            'median_filter': '7x7',
            'confidence_threshold_stereo': 255,
            'lr_check': True,
            'extended_disparity': True,
            'subpixel': False,
            
            # Output configuration
            'output_dir': LaunchConfiguration('output_dir'),
            'input_dir': LaunchConfiguration('input_dir'),
            'enable_file_output': True,  # Required for Phase 1
            'enable_pcd_output': False,
            
            # ROS2 interface configuration
            'camera_frame': LaunchConfiguration('camera_frame'),
            'publish_debug_image': LaunchConfiguration('publish_debug_image'),
            'publish_pointcloud': LaunchConfiguration('publish_pointcloud'),
            
            # Testing configuration
            'simulation_mode': LaunchConfiguration('simulation_mode'),
        }],
        remappings=[
            # Remap to standard topic names if needed
            ('/cotton_detection/results', '/cotton_detection/results'),
        ]
    )
    
    # Info messages
    info_msg = LogInfo(
        msg=[
            '\\n',
            '=' * 80, '\\n',
            'Cotton Detection ROS2 Wrapper (Phase 1) Starting...', '\\n',
            '=' * 80, '\\n',
            'Configuration:', '\\n',
            '  USB Mode: ', LaunchConfiguration('usb_mode'), '\\n',
            '  YOLO Blob: ', LaunchConfiguration('blob_path'), '\\n',
            '  Confidence Threshold: ', LaunchConfiguration('confidence_threshold'), '\\n',
            '  Output Directory: ', LaunchConfiguration('output_dir'), '\\n',
            '  Camera Frame: ', LaunchConfiguration('camera_frame'), '\\n',
            '=' * 80, '\\n',
            'Services:', '\\n',
            '  /cotton_detection/detect (CottonDetection)', '\\n',
            '  /cotton_detection/calibrate (CottonDetection - optional)', '\n',
            'Topics:', '\\n',
            '  /cotton_detection/results (Detection3DArray)', '\\n',
            '  /cotton_detection/debug_image (Image - optional)', '\\n',
            '=' * 80, '\\n',
            'Usage:', '\\n',
            '  ros2 service call /cotton_detection/detect ', 
            'cotton_detection_ros2/srv/CottonDetection \\"{detect_command: 1}\\"', '\\n',
            '  ros2 topic echo /cotton_detection/results', '\\n',
            '=' * 80, '\\n',
        ]
    )
    
    return LaunchDescription([
        # Launch arguments
        usb_mode_arg,
        blob_path_arg,
        confidence_threshold_arg,
        iou_threshold_arg,
        output_dir_arg,
        input_dir_arg,
        camera_frame_arg,
        publish_debug_image_arg,
        publish_pointcloud_arg,
        simulation_mode_arg,
        
        # Info message
        info_msg,
        
        # Nodes
        wrapper_node,
    ])
