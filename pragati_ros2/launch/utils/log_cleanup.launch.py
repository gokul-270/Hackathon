#!/usr/bin/env python3
"""
Log Cleanup Launch Component for Pragati ROS2
============================================

This launch file provides automatic log cleanup functionality that can be
integrated into other launch files to maintain clean log directories.

Usage:
    # Include in other launch files
    from launch.include import IncludeLaunchDescription
    from launch.launch_description_sources import PythonLaunchDescriptionSource
    
    IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            get_package_share_directory('pragati_complete'),
            '/launch/utils/log_cleanup.launch.py'
        ])
    )

Author: Generated for Pragati ROS2 Project  
Date: 2025-09-18
"""

import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch.conditions import IfCondition
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    """Generate launch description with log cleanup functionality."""
    
    # Declare launch arguments
    enable_log_cleanup = DeclareLaunchArgument(
        'enable_log_cleanup',
        default_value='true',
        description='Enable automatic log cleanup on startup'
    )
    
    cleanup_delay = DeclareLaunchArgument(
        'log_cleanup_delay',
        default_value='30.0',
        description='Delay before running log cleanup (seconds)'
    )
    
    max_log_age_days = DeclareLaunchArgument(
        'max_log_age_days',
        default_value='7',
        description='Maximum age of log files before cleanup (days)'
    )
    
    max_log_size_mb = DeclareLaunchArgument(
        'max_log_size_mb', 
        default_value='100',
        description='Maximum total size of logs before cleanup (MB)'
    )
    
    verbose_cleanup = DeclareLaunchArgument(
        'verbose_log_cleanup',
        default_value='false',
        description='Enable verbose output for log cleanup'
    )
    
    # Get the project root directory
    # This assumes the launch file is in PROJECT_ROOT/launch/utils/
    current_file = os.path.abspath(__file__) if '__file__' in globals() else os.path.abspath('launch/utils/log_cleanup.launch.py')
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    
    # Log cleanup action
    log_cleanup_action = TimerAction(
        period=LaunchConfiguration('log_cleanup_delay'),
        actions=[
            ExecuteProcess(
                cmd=[
                    'python3',
                    os.path.join(project_root, 'scripts', 'utils', 'log_manager.py'),
                    '--project-root', project_root,
                    '--max-age-days', LaunchConfiguration('max_log_age_days'),
                    '--max-size-mb', LaunchConfiguration('max_log_size_mb'),
                    PythonExpression([
                        "'--verbose' if '", LaunchConfiguration('verbose_log_cleanup'), "' == 'true' else ''"
                    ])
                ],
                name='log_cleanup',
                output='log',
                condition=IfCondition(LaunchConfiguration('enable_log_cleanup'))
            )
        ]
    )
    
    # Environment setup action to ensure ROS logs go to project directory
    setup_ros_logging = ExecuteProcess(
        cmd=[
            'bash', '-c', 
            f'export ROS_LOG_DIR={project_root}/logs && echo "ROS2 logs redirected to project directory: $ROS_LOG_DIR"'
        ],
        name='setup_ros_logging',
        output='screen'
    )
    
    return LaunchDescription([
        # Arguments
        enable_log_cleanup,
        cleanup_delay,
        max_log_age_days,
        max_log_size_mb,
        verbose_cleanup,
        
        # Actions
        setup_ros_logging,
        log_cleanup_action,
    ])


if __name__ == '__main__':
    generate_launch_description()