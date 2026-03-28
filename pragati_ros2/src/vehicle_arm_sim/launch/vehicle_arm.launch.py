#!/usr/bin/env python3
"""
Launch file for vehicle_arm_sim: vehicle + arm integration simulation.

Loads a merged URDF (vehicle + arm), spawns it in Gazebo, and bridges
the essential ROS 2 topics.

If urdf/saved/ contains any .urdf files the most recently modified one
is used automatically; otherwise the default urdf/vehicle_arm_merged.urdf
is loaded.

Usage:
  ros2 launch vehicle_arm_sim vehicle_arm.launch.py
  ros2 launch vehicle_arm_sim vehicle_arm.launch.py headless:=true
"""

import os
import glob
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from launch import LaunchDescription
from launch.actions import (
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    DeclareLaunchArgument,
    OpaqueFunction,
    ExecuteProcess,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def _ensure_single_root(urdf_string: str) -> str:
    """Re-insert vehicle_to_arm joint if arm_base_link is a dangling root.

    The web editor can accidentally delete the joint that connects the arm
    to the vehicle, leaving two root links.  Gazebo's URDF→SDF converter
    rejects multi-root URDFs, so this function detects the problem and
    inserts a fixed joint to reconnect them.
    """
    try:
        root = ET.fromstring(urdf_string)
    except ET.ParseError:
        return urdf_string  # don't touch malformed XML

    links = {l.get('name') for l in root.findall('link')}
    children = set()
    for j in root.findall('joint'):
        c = j.find('child')
        if c is not None:
            children.add(c.get('link'))
    root_links = links - children

    # Only auto-repair the specific known case: arm_base_link + base-v1
    if 'arm_base_link' in root_links and 'base-v1' in root_links:
        print(
            '[vehicle_arm.launch.py] WARNING: Multi-root URDF detected '
            f'(roots: {root_links}). Re-inserting vehicle_to_arm joint.'
        )
        joint = ET.SubElement(root, 'joint', {
            'name': 'vehicle_to_arm',
            'type': 'fixed',
        })
        ET.SubElement(joint, 'origin', {
            'xyz': '0.65 0.0 1.1',
            'rpy': '-1.5708 0.0 0.0',
        })
        ET.SubElement(joint, 'parent', {'link': 'base-v1'})
        ET.SubElement(joint, 'child', {'link': 'arm_base_link'})
        return ET.tostring(root, encoding='unicode', xml_declaration=True)

    return urdf_string


def _urdf_to_sdf(urdf_string: str) -> str:
    """Convert URDF to SDF using the offline ``gz sdf -p`` tool.

    Gazebo Harmonic's internal URDF parser can produce duplicate link/joint
    names when collapsing fixed joints, causing the model to fail silently.
    The offline ``gz sdf -p`` converter handles this correctly, so we
    pre-convert here and spawn SDF instead of raw URDF.

    Returns the SDF string on success, or an empty string on failure.
    """
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.urdf', mode='w', delete=False
        ) as tmp:
            tmp.write(urdf_string)
            tmp_path = tmp.name

        result = subprocess.run(
            ['gz', 'sdf', '-p', tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        os.unlink(tmp_path)

        if result.returncode == 0 and result.stdout.strip():
            print(
                '[vehicle_arm.launch.py] URDF→SDF conversion successful '
                f'({len(result.stdout)} bytes)'
            )
            return result.stdout
        else:
            print(
                '[vehicle_arm.launch.py] WARNING: URDF→SDF conversion failed '
                f'(rc={result.returncode}): {result.stderr[:500]}'
            )
            return ''
    except Exception as exc:  # noqa: BLE001
        print(f'[vehicle_arm.launch.py] WARNING: URDF→SDF conversion error: {exc}')
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return ''


def generate_launch_description():
    # ------------------------------------------------------------------ #
    # Launch arguments
    # ------------------------------------------------------------------ #
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time from Gazebo',
    )

    headless_arg = DeclareLaunchArgument(
        'headless',
        default_value='false',
        description='Run Gazebo without GUI (server-only mode)',
    )

    urdf_file_arg = DeclareLaunchArgument(
        'urdf_file',
        default_value='',
        description='Explicit URDF file path (overrides auto-detection)',
    )

    # ------------------------------------------------------------------ #
    # Package paths
    # ------------------------------------------------------------------ #
    pkg_share = get_package_share_directory('vehicle_arm_sim')

    # ------------------------------------------------------------------ #
    # URDF selection: explicit arg > editor session file > saved/ > default
    # ------------------------------------------------------------------ #
    urdf_file = None

    # 1. Explicit path via environment variable (set by launch_web_ui.sh)
    explicit_path = os.environ.get('VEHICLE_ARM_URDF_FILE', '')
    if explicit_path and os.path.isfile(explicit_path):
        urdf_file = explicit_path

    # 2. Editor session file (persisted by the web editor backend)
    if not urdf_file:
        editor_session = os.path.expanduser(
            '~/.vehicle_arm_sim/latest_editor.urdf'
        )
        if os.path.isfile(editor_session):
            urdf_file = editor_session

    # 3. Saved directory under source package
    if not urdf_file:
        # Check the source tree's saved dir (backend writes here)
        _this_file = os.path.abspath(__file__)
        _src_pkg = os.path.dirname(os.path.dirname(_this_file))
        src_saved_dir = os.path.join(_src_pkg, 'urdf', 'saved')
        src_saved = sorted(
            glob.glob(os.path.join(src_saved_dir, '*.urdf')),
            key=os.path.getmtime,
        ) if os.path.isdir(src_saved_dir) else []
        if src_saved:
            urdf_file = src_saved[-1]

    # 4. Saved directory under install (ament share)
    if not urdf_file:
        saved_dir = os.path.join(pkg_share, 'urdf', 'saved')
        saved_urdfs = sorted(
            glob.glob(os.path.join(saved_dir, '*.urdf')),
            key=os.path.getmtime,
        ) if os.path.isdir(saved_dir) else []
        if saved_urdfs:
            urdf_file = saved_urdfs[-1]

    # 5. Default merged URDF
    if not urdf_file:
        urdf_file = os.path.join(pkg_share, 'urdf', 'vehicle_arm_merged.urdf')

    # Read the URDF into a string for robot_description
    with open(urdf_file, 'r') as fh:
        robot_desc = fh.read()

    # ------------------------------------------------------------------ #
    # Auto-repair multi-root URDFs: if "arm_base_link" is a dangling root
    # (vehicle_to_arm joint was deleted in the editor), re-insert it so
    # Gazebo's URDF→SDF converter doesn't reject the file.
    # ------------------------------------------------------------------ #
    robot_desc = _ensure_single_root(robot_desc)

    # ------------------------------------------------------------------ #
    # Pre-convert URDF → SDF to avoid Gazebo's buggy internal URDF parser
    # which creates duplicate link/joint names during fixed-joint collapse.
    # ------------------------------------------------------------------ #
    sdf_string = _urdf_to_sdf(robot_desc)
    use_sdf = bool(sdf_string)

    # World file
    world_file = os.path.join(pkg_share, 'worlds', 'empty_world.sdf')

    # ------------------------------------------------------------------ #
    # Environment: let Gazebo find meshes / models inside the package
    # ------------------------------------------------------------------ #
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=':'.join([
            os.path.join(pkg_share, '..'),
            pkg_share,
            os.path.join(pkg_share, 'meshes'),
        ]),
    )

    # ------------------------------------------------------------------ #
    # Robot State Publisher
    # ------------------------------------------------------------------ #
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_desc}],
    )

    # ------------------------------------------------------------------ #
    # Gazebo (server + optional GUI)
    # ------------------------------------------------------------------ #
    def launch_gazebo(context):
        headless = context.launch_configurations.get('headless', 'false')

        # Always launch the physics server separately with -s
        server = IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                os.path.join(
                    get_package_share_directory('ros_gz_sim'),
                    'launch', 'gz_sim.launch.py',
                )
            ]),
            launch_arguments={
                'gz_args': f'-s -r "{world_file}"',
            }.items(),
        )

        actions = [server]

        if headless != 'true':
            # Sanitise the environment so VS Code snap libraries do not
            # clash with the host glibc (same pattern as vehicle_control).
            snap_vars_to_unset = [
                'GTK_PATH',
                'GTK_EXE_PREFIX',
                'GTK_IM_MODULE_FILE',
                'GIO_MODULE_DIR',
                'GSETTINGS_SCHEMA_DIR',
                'LOCPATH',
                'GDK_BACKEND',
                'LD_PRELOAD',
                'GTK_PATH_VSCODE_SNAP_ORIG',
                'GTK_EXE_PREFIX_VSCODE_SNAP_ORIG',
                'GTK_IM_MODULE_FILE_VSCODE_SNAP_ORIG',
                'GIO_MODULE_DIR_VSCODE_SNAP_ORIG',
                'GSETTINGS_SCHEMA_DIR_VSCODE_SNAP_ORIG',
                'LOCPATH_VSCODE_SNAP_ORIG',
                'GDK_BACKEND_VSCODE_SNAP_ORIG',
            ]

            current_ld = os.environ.get('LD_LIBRARY_PATH', '')
            clean_ld = ':'.join(
                p for p in current_ld.split(':')
                if p and '/snap/' not in p
            )

            env_cmd = ['env']
            for var in snap_vars_to_unset:
                env_cmd += ['-u', var]
            env_cmd += [
                f'LD_LIBRARY_PATH={clean_ld}',
                'gz', 'sim', '-g',
            ]

            gui = ExecuteProcess(cmd=env_cmd, output='screen')
            actions.append(TimerAction(period=2.0, actions=[gui]))

        return actions

    gazebo = OpaqueFunction(function=launch_gazebo)

    # ------------------------------------------------------------------ #
    # Spawn the robot model — pre-converted SDF avoids Gazebo's internal
    # URDF parser which creates duplicate link/joint names when collapsing
    # fixed joints.  Falls back to raw URDF if conversion failed.
    # ------------------------------------------------------------------ #
    if use_sdf:
        spawn_args = [
            '-name', 'vehicle_arm',
            '-string', sdf_string,
            '-x', '0',
            '-y', '0',
            '-z', '1.0',
            '-R', '1.5708',
            '-P', '0',
            '-Y', '0',
        ]
    else:
        spawn_args = [
            '-name', 'vehicle_arm',
            '-string', robot_desc,
            '-x', '0',
            '-y', '0',
            '-z', '1.0',
            '-R', '1.5708',
            '-P', '0',
            '-Y', '0',
        ]

    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=spawn_args,
        output='screen',
    )

    # ------------------------------------------------------------------ #
    # ROS <-> Gazebo bridge
    # ------------------------------------------------------------------ #
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            # Clock
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            # Joint states
            '/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model',
            # Velocity command
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            # Wheel velocity commands
            '/wheel/front/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/wheel/left/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            '/wheel/right/velocity@std_msgs/msg/Float64]gz.msgs.Double',
            # Steering commands
            '/steering/front@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/left@std_msgs/msg/Float64]gz.msgs.Double',
            '/steering/right@std_msgs/msg/Float64]gz.msgs.Double',
            # Odometry
            '/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            # IMU
            '/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
            # Front camera
            '/front_camera@sensor_msgs/msg/Image[gz.msgs.Image',
        ],
        output='screen',
    )

    # ------------------------------------------------------------------ #
    # Assemble the launch description
    # ------------------------------------------------------------------ #
    return LaunchDescription([
        use_sim_time_arg,
        headless_arg,
        urdf_file_arg,
        gz_resource_path,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
    ])
