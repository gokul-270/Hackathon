#!/usr/bin/env python3
"""
Launch file for vehicle_control robot with joystick support

This launch file starts:
1. Gazebo simulator with vehicle_control robot
2. Robot state publisher
3. Kinematics node (velocity -> wheel commands)
4. Joy node (joystick input)
5. Joy teleop node (joystick -> velocity commands)

Usage:
  ros2 launch vehicle_control gazebo_with_joy.launch.py
  
Or without joystick:
  ros2 launch vehicle_control gazebo.launch.py
  
Then control with joystick or publish to /cmd_vel:
  ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # Get package directories
    pkg_vehicle_control = get_package_share_directory('vehicle_control')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    
    # URDF file path
    urdf_file = os.path.join(pkg_vehicle_control, 'urdf', 'vehicle.urdf')
    
    # Path to world file and GUI config
    world_file = os.path.join(pkg_vehicle_control, 'worlds', 'cotton_field.sdf')
    gui_config = os.path.join(pkg_vehicle_control, 'simulation', 'config', 'gazebo_gui.config')
    
    # Read URDF content
    with open(urdf_file, 'r') as f:
        robot_description = f.read()
    
    # Declare launch arguments
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation (Gazebo) clock if true'
    )
    
    use_joystick_arg = DeclareLaunchArgument(
        'use_joystick',
        default_value='true',
        description='Enable joystick control if true'
    )
    
    # Robot State Publisher
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': LaunchConfiguration('use_sim_time')
        }]
    )
    
    # Gazebo Sim
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'),
                'launch',
                'gz_sim.launch.py'
            ])
        ]),
        launch_arguments={
            'gz_args': f'-r "{world_file}" --gui-config "{gui_config}"'
        }.items()
    )
    
    # Spawn robot in Gazebo
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_vehicle_control',
        arguments=[
            '-name', 'vehicle_control',
            '-topic', '/robot_description',
            '-x', '0.0',
            '-y', '0.0',
            '-z', '1.0',
            '-R', '1.5708',
            '-P', '0',
            '-Y', '3.1416'
        ],
        output='screen'
    )
    
    # ROS-Gazebo bridge
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
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
    
    # Kinematics Node (velocity commands -> wheel commands)
    kinematics_node = Node(
        package='vehicle_control',
        executable='gazebo_kinematics_node',
        name='vehicle_control_kinematics',
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'wheel_radius': 0.2875,  # Measured from STL mesh (575mm diameter)
            'front_wheel_position': [1.3, 0.0],
            'left_wheel_position': [0.0, 0.9],
            'right_wheel_position': [0.0, -0.9],
            'max_steering_angle': 1.570796,
            'max_wheel_speed': 20.0
        }]
    )
    
    # Joy Node (joystick driver)
    joy_node = Node(
        package='joy',
        executable='joy_node',
        name='joy_node',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_joystick')),
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'deadzone': 0.1,
            'autorepeat_rate': 20.0
        }]
    )
    
    # Joy Teleop Node (joystick -> cmd_vel)
    joy_teleop = Node(
        package='vehicle_control',
        executable='gazebo_joy_teleop',
        name='joy_teleop',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_joystick')),
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'axis_linear': 1,    # Left stick Y
            'axis_angular': 3,   # Right stick X
            'button_turbo': 0,   # A button
            'button_stop': 1,    # B button
            'max_linear_speed': 0.5,
            'max_angular_speed': 1.0,
            'deadzone': 0.1
        }]
    )
    
    # Set Gazebo resource path for meshes, models, and worlds
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=':'.join([
            os.path.join(pkg_vehicle_control, '..'),
            pkg_vehicle_control,
            os.path.join(pkg_vehicle_control, 'models'),
        ])
    )

    return LaunchDescription([
        use_sim_time_arg,
        use_joystick_arg,
        gz_resource_path,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
        kinematics_node,
        joy_node,
        joy_teleop
    ])
