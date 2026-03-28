#!/usr/bin/env python3
"""
Gazebo launch file for vehicle_control robot with sensors in virtual cotton field.
Uses cotton_field_with_plants.sdf world with IMU, GPS, camera, and odometry bridges.

Usage:
  ros2 launch vehicle_control gazebo_sensors.launch.py                  # Velocity-based kinematics (default)
  ros2 launch vehicle_control gazebo_sensors.launch.py ackermann:=true  # Ackermann geometry steering
"""

import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable, DeclareLaunchArgument, TimerAction
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

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time from Gazebo'
    )

    cotton_detection_arg = DeclareLaunchArgument(
        'cotton_detection',
        default_value='true',
        description='Enable front camera cotton detection'
    )

    # Get the package directory
    pkg_share = get_package_share_directory('vehicle_control')

    # Path to URDF file
    urdf_file = os.path.join(pkg_share, 'urdf', 'vehicle.urdf')

    # Path to GUI config
    gui_config = os.path.join(pkg_share, 'simulation', 'config', 'gazebo_gui.config')

    # Path to world file - cotton field with plants
    world_file = os.path.join(pkg_share, 'worlds', 'cotton_field_with_plants.sdf')

    # Read the URDF file
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    # Set Gazebo resource path for meshes, models, and worlds
    # Include: parent dir (share/), package dir itself, models dir, and worlds dir
    # so that model:// URIs and relative mesh paths both resolve correctly
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=':'.join([
            os.path.join(pkg_share, '..'),
            pkg_share,
            os.path.join(pkg_share, 'models'),
            os.path.join(pkg_share, 'worlds'),
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

    # Start Gazebo with cotton field world (with plants)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            os.path.join(get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')
        ]),
        launch_arguments={
            'gz_args': f'-r "{world_file}" --gui-config "{gui_config}"',
        }.items()
    )

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

    # Bridge for clock, wheel/steering, and sensor topics
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            # Existing topics
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model',
            '/wheel/front/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/wheel/left/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/wheel/right/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/front@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/left@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/right@std_msgs/msg/Float64]gz.msgs.Double',
            # Sensor topics
            '/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/navsat@sensor_msgs/msg/NavSatFix[gz.msgs.NavSat',
            '/front_camera@sensor_msgs/msg/Image[gz.msgs.Image',
            '/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            '/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V',
        ],
        output='screen'
    )

    # RTK GPS Simulator — differential correction pipeline
    rtk_gps_node = Node(
        package='vehicle_control',
        executable='gazebo_rtk_gps_simulator',
        name='rtk_gps_simulator',
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'base_lat': 23.0225,
            'base_lon': 72.5714,
            'base_alt': 53.0,
            'base_world_x': 0.0,
            'base_world_y': 0.0,
            'convergence_time': 30.0,
        }]
    )

    # Kinematics node - CONDITIONAL: velocity-based (default)
    kinematics_node = Node(
        package='vehicle_control',
        executable='gazebo_kinematics_node',
        name='kinematics_node',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=UnlessCondition(LaunchConfiguration('ackermann'))
    )

    # Ackermann steering node - CONDITIONAL: Ackermann geometry
    ackermann_node = Node(
        package='vehicle_control',
        executable='gazebo_ackermann_steering',
        name='ackermann_steering',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('ackermann'))
    )

    # ══════════════════════════════════════════════════════════════
    # Front Camera Cotton Detection Node
    # ══════════════════════════════════════════════════════════════
    # Processes /front_camera images to detect cotton bolls using
    # HSV color detection (simulation) or YOLOv11 blob (real hardware).
    # Model: cotton_detection_ros2/models/yolov112.blob
    # Publishes to: /cotton_detection/result (cotton_detection_ros2/DetectionResult)
    # Service: /cotton_detection/detect (cotton_detection_ros2/CottonDetection)
    cotton_detection_config = os.path.join(
        pkg_share, 'simulation', 'config', 'front_camera_detection.yaml')

    # Resolve model path from cotton_detection_ros2 package (if available)
    try:
        cotton_detection_share = get_package_share_directory('cotton_detection_ros2')
        model_path = os.path.join(cotton_detection_share, 'models', 'yolov112.blob')
    except Exception:
        model_path = ''

    front_camera_cotton_detector = TimerAction(
        period=5.0,  # Delay to allow Gazebo camera to initialize
        actions=[
            Node(
                package='vehicle_control',
                executable='gazebo_front_camera_cotton_detector',
                name='front_camera_cotton_detector',
                output='screen',
                parameters=[
                    cotton_detection_config,
                    {
                        'use_sim_time': LaunchConfiguration('use_sim_time'),
                        'model_path': model_path,
                    }
                ],
                condition=IfCondition(LaunchConfiguration('cotton_detection'))
            )
        ]
    )

    return LaunchDescription([
        ackermann_arg,
        use_sim_time_arg,
        cotton_detection_arg,
        gz_resource_path,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
        rtk_gps_node,
        kinematics_node,
        ackermann_node,
        front_camera_cotton_detector,
    ])
