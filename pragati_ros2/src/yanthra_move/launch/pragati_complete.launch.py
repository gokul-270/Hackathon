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
Pragati Complete Launch File with AUTO-CLEANUP
===============================================
Comprehensive ROS2 launch file for the complete Pragati cotton-picking robot system.
This now matches the COMPLETE ROS1 system structure including ARM client:

- robot_state_publisher (for URDF and TF)
- joint_state_publisher (for joint state publishing)
- mg6010_controller (MG6010 CAN motor control services)
- yanthra_move (contains embedded joint position controllers)
- cotton_detection_node (C++ implementation - Phase 5 default)
- disk_space_monitor (log rotation and disk space management)
- ARM_client (MQTT bridge - launched with 10s delay like ROS1)

FEATURES:
✅ AUTOMATIC CLEANUP: Automatically cleans up previous ROS2 instances before launch
✅ DUPLICATE PREVENTION: Ensures no conflicting nodes exist
✅ SAFE LAUNCH: 3-second delay after cleanup before starting nodes
✅ DAEMON RESTART: Clears stale ROS2 daemon references

The joint position controllers (joint2_position_controller, joint3_position_controller,
joint4_position_controller, joint5_position_controller) are embedded within the
yanthra_move node itself, not separate executables.

Usage:
    ros2 launch yanthra_move pragati_complete.launch.py
    ros2 launch yanthra_move pragati_complete.launch.py enable_arm_client:=false  # Disable ARM client
    ros2 launch yanthra_move pragati_complete.launch.py mqtt_address:=192.168.1.40  # Custom MQTT broker

NOTE: This launch file now automatically performs cleanup - no manual cleanup_ros2.sh needed!
"""

import os
import subprocess
import sys
import time
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    TimerAction,
    SetEnvironmentVariable,
    LogInfo,
    IncludeLaunchDescription,
    RegisterEventHandler,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit, OnShutdown
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
    Command,
    NotSubstitution,
    LaunchLogDir,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue
from launch.launch_description_sources import PythonLaunchDescriptionSource

# =============================================================================
# Task 1.1: Module-level process pattern constants
# These are used by cleanup_previous_instances() and _wait_for_processes_exit()
# =============================================================================

# Short names (<=15 chars) -- pkill -x exact match
_SHORT_PROCESS_PATTERNS = [
    "mg6010_controller",  # truncated to 15 chars for pkill -x
    "yanthra_move_nod",  # truncated
    "cotton_detection",  # truncated
]

# Long names -- pkill -f pattern match against full command line
_LONG_PROCESS_PATTERNS = [
    "lib/robot_state_publisher",
    "lib/joint_state_publisher",
    "lib/cotton_detection_ros2/cotton_detection_node",
    "lib/yanthra_move/yanthra_move_node",
    "lib/motor_control_ros2/mg6010_controller_node",
    r"python.*ARM_client\.py",
]


# =============================================================================
# Task 5.2 / 5.4: ARM_client restart state (mutable dict for closure access)
# =============================================================================
_arm_client_restart_state = {
    "timestamps": [],  # monotonic timestamps of recent restarts
    "shutting_down": False,  # set True by OnShutdown handler
}

# Restart policy constants
_ARM_CLIENT_MAX_RESTARTS = 5  # max restarts within the window
_ARM_CLIENT_RESTART_WINDOW_S = 60  # rolling window in seconds
_ARM_CLIENT_RESTART_DELAY_S = 5.0  # delay before relaunch


# =============================================================================
# Task 1.2: Poll-based process exit verification helper
# =============================================================================
def _wait_for_processes_exit(patterns, timeout_s=3, poll_interval_s=0.25):
    """Poll pgrep until all target processes exit or timeout expires.

    Args:
        patterns: list of (pkill_flag, pattern) tuples, e.g. ('-x', 'mg6010_controller')
        timeout_s: maximum seconds to wait before returning survivors
        poll_interval_s: seconds between pgrep polls

    Returns:
        list of surviving (flag, pattern) tuples (empty list = all exited cleanly)
    """
    deadline = time.time() + timeout_s
    surviving = list(patterns)

    while surviving and time.time() < deadline:
        time.sleep(poll_interval_s)
        still_alive = []
        for flag, pattern in surviving:
            try:
                result = subprocess.run(
                    ["pgrep", flag, pattern],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    still_alive.append((flag, pattern))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        surviving = still_alive

    return surviving


# =============================================================================
# Task 2.1, 2.3: CAN socket release verification helper
# =============================================================================
def _check_can_socket_released(interface="can0", timeout_s=2, poll_interval_s=0.25):
    """Check that the CAN socket on `interface` has been released by all processes.

    Tries /proc/net/can/raw first (kernel config dependent), falls back to
    `ss -f can`.  If neither is available, logs a debug message and returns
    True (skip check, proceed regardless).

    Args:
        interface: CAN interface name to check (default 'can0')
        timeout_s: maximum seconds to wait for socket release
        poll_interval_s: seconds between polls

    Returns:
        True if socket is released (or check not available), False if persists
        after timeout (caller should log warning and proceed anyway).
    """

    def _has_can_socket():
        # Primary: /proc/net/can/raw
        proc_path = "/proc/net/can/raw"
        if os.path.exists(proc_path):
            try:
                with open(proc_path) as f:
                    content = f.read()
                return interface in content
            except OSError:
                pass

        # Fallback: ss -f can
        try:
            result = subprocess.run(
                ["ss", "-f", "can"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return interface in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Task 2.3: neither method available -- skip check
            print(
                f"DEBUG: CAN socket check skipped -- /proc/net/can/raw not found "
                f"and 'ss' not available on this system"
            )
            return False  # Treat as released (skip check)

        return False

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _has_can_socket():
            return True  # Released
        time.sleep(poll_interval_s)

    return False  # Still holds socket after timeout


def cleanup_previous_instances():
    """Automatically cleanup any previous ROS2 instances to prevent duplicate nodes.

    Task 1.3-1.5: Uses poll-based exit verification + SIGKILL escalation.
    Task 2.2: Verifies CAN socket release after mg6010_controller_node exits.
    """
    print("🧹 AUTO-CLEANUP: Ensuring clean launch environment...")

    # Stop ROS2 daemon first
    try:
        subprocess.run(["ros2", "daemon", "stop"], capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Task 1.5: Fast path -- check if any processes exist at all
    all_patterns = [("-x", p) for p in _SHORT_PROCESS_PATTERNS] + [
        ("-f", p) for p in _LONG_PROCESS_PATTERNS
    ]

    any_running = False
    for flag, pattern in all_patterns:
        try:
            result = subprocess.run(["pgrep", flag, pattern], capture_output=True, timeout=2)
            if result.returncode == 0:
                any_running = True
                break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Task 5.3: Track whether any stale processes were found for fast-path sleep skip
    clean_start = not any_running

    if not any_running:
        print("✅ AUTO-CLEANUP: No stale processes found -- fast path (<2s)")
    else:
        # Send SIGTERM to all target processes
        for process in _SHORT_PROCESS_PATTERNS:
            try:
                subprocess.run(["pkill", "-x", process], capture_output=True, timeout=3)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        for pattern in _LONG_PROCESS_PATTERNS:
            try:
                subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=3)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Task 1.2 + 1.4: Wait for processes to exit via polling (replaces time.sleep(0.5))
        sigterm_patterns = [("-x", p) for p in _SHORT_PROCESS_PATTERNS] + [
            ("-f", p) for p in _LONG_PROCESS_PATTERNS
        ]
        survivors = _wait_for_processes_exit(sigterm_patterns, timeout_s=3, poll_interval_s=0.25)

        # Task 1.3: SIGKILL escalation for survivors
        if survivors:
            survivor_names = [p for _f, p in survivors]
            print(
                f"⚠️  AUTO-CLEANUP: {len(survivors)} process(es) survived SIGTERM, "
                f"escalating to SIGKILL: {survivor_names}"
            )
            for flag, pattern in survivors:
                try:
                    subprocess.run(
                        ["pkill", "-9", flag, pattern],
                        capture_output=True,
                        timeout=3,
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
            # Give SIGKILL 2s to take effect
            kill_survivors = _wait_for_processes_exit(survivors, timeout_s=2, poll_interval_s=0.25)
            if kill_survivors:
                kill_names = [p for _f, p in kill_survivors]
                print(f"⚠️  AUTO-CLEANUP: Processes still alive after SIGKILL: {kill_names}")

        print("✅ AUTO-CLEANUP: Process cleanup complete")

    # Task 2.2: Verify CAN socket released after mg6010_controller_node exits
    # Task 5.2: Skip CAN check entirely when can0 interface doesn't exist
    if not os.path.exists("/sys/class/net/can0"):
        print("ℹ️  AUTO-CLEANUP: Skipping CAN check — no can0 interface")
    else:
        released = _check_can_socket_released(interface="can0", timeout_s=2)
        if not released:
            print(
                "⚠️  AUTO-CLEANUP: CAN socket on can0 still held after mg6010_controller_node "
                "exit -- proceeding anyway (bind may retry)"
            )

    # Restart ROS2 daemon
    try:
        subprocess.run(["ros2", "daemon", "start"], capture_output=True, timeout=10)
        if not clean_start:
            time.sleep(0.1)  # reduced from 0.5s — daemon ready by then
        # Task 5.3: skip sleep entirely on clean_start (no stale processes found)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("✅ AUTO-CLEANUP: Environment ready for safe launch")


def generate_launch_description():
    # Guard cleanup against non-launch invocations (--show-args, --help, -h)
    # and launch_testing / CI invocations (env var or CLI arg)
    _non_launch_flags = {"--show-args", "--help", "-h"}
    _skip_cleanup = os.environ.get("PRAGATI_SKIP_CLEANUP", "") == "1" or any(
        arg == "skip_cleanup:=true" for arg in sys.argv
    )
    if _skip_cleanup:
        print("ℹ️  AUTO-CLEANUP: Skipped (PRAGATI_SKIP_CLEANUP or skip_cleanup:=true)")
    elif any(flag in sys.argv for flag in _non_launch_flags):
        print("ℹ️  AUTO-CLEANUP: Skipped (non-launch invocation detected)")
    else:
        # AUTOMATIC CLEANUP: Prevent duplicate nodes and ensure clean launch
        cleanup_previous_instances()

    # Launch configuration variables
    output_log = LaunchConfiguration("output_log")
    use_sim_time = LaunchConfiguration("use_sim_time")
    use_simulation = LaunchConfiguration("use_simulation")
    continuous_operation = LaunchConfiguration("continuous_operation")
    enable_arm_client = LaunchConfiguration("enable_arm_client")
    enable_cotton_detection = LaunchConfiguration("enable_cotton_detection")
    use_preloaded_centroids_arg = LaunchConfiguration("use_preloaded_centroids")
    mqtt_address = LaunchConfiguration("mqtt_address")
    arm_id = LaunchConfiguration("arm_id")  # Task 4.5
    log_directory = LaunchConfiguration("log_directory")
    can_interface = LaunchConfiguration("can_interface")
    can_bitrate = LaunchConfiguration("can_bitrate")
    offline_mode = LaunchConfiguration("offline_mode")
    offline_image_path = LaunchConfiguration("offline_image_path")
    log_level = LaunchConfiguration("log_level")
    enable_j5_collision_avoidance = LaunchConfiguration("enable_j5_collision_avoidance")

    # Rosbag2 recording configuration
    enable_bag_recording = LaunchConfiguration("enable_bag_recording")
    bag_profile = LaunchConfiguration("bag_profile")

    # Declare the launch arguments
    declare_output_log_cmd = DeclareLaunchArgument(
        name="output_log",
        default_value="screen",
        description="Output log type (screen or log)",
    )

    declare_use_sim_time_cmd = DeclareLaunchArgument(
        name="use_sim_time",
        default_value="false",
        description="Use simulation (Gazebo) clock if true",
    )

    declare_use_simulation_cmd = DeclareLaunchArgument(
        name="use_simulation",
        default_value="false",
        description="Use simulation mode instead of hardware",
    )

    declare_continuous_operation_cmd = DeclareLaunchArgument(
        name="continuous_operation",
        default_value="true",
        description="Enable continuous operation mode (true) or single-cycle mode (false)",
    )

    # j4_multiposition is controlled solely by production.yaml (joint4_multiposition/enabled)
    # Edit the YAML to change it — no launch argument override needed.

    declare_enable_arm_client_cmd = DeclareLaunchArgument(
        name="enable_arm_client",
        default_value="true",
        description="Enable ARM Client MQTT bridge (matches ROS-1 behavior)",
    )

    declare_enable_cotton_detection_cmd = DeclareLaunchArgument(
        name="enable_cotton_detection",
        default_value="true",
        description="Enable Cotton Detection with ArUco marker tracking",
    )
    declare_use_preloaded_centroids_cmd = DeclareLaunchArgument(
        name="use_preloaded_centroids",
        default_value="false",
        description="Use preloaded centroids from centroid.txt (only used when enable_cotton_detection=false)",
    )

    declare_mqtt_address_cmd = DeclareLaunchArgument(
        name="mqtt_address",
        default_value="10.42.0.10",
        description="MQTT broker address for ARM client",
    )

    # Task 4.5: arm_id launch argument (passed to ARM_client.py --client-id)
    declare_arm_id_cmd = DeclareLaunchArgument(
        name="arm_id",
        default_value="arm1",
        description="ARM client identifier, used as MQTT client_id and topic suffix",
    )

    declare_offline_mode_cmd = DeclareLaunchArgument(
        name="offline_mode",
        default_value="false",
        description="Enable offline image detection mode",
    )

    declare_offline_image_path_cmd = DeclareLaunchArgument(
        name="offline_image_path",
        default_value="",
        description="Path to offline image for detection",
    )

    # Rosbag2 recording arguments
    declare_enable_bag_recording_cmd = DeclareLaunchArgument(
        name="enable_bag_recording",
        default_value="false",
        description="Enable rosbag2 recording at launch",
    )

    declare_bag_profile_cmd = DeclareLaunchArgument(
        name="bag_profile",
        default_value="standard",
        description="Recording profile: minimal, standard, debug",
    )

    # EE timing configuration
    use_dynamic_ee_prestart = LaunchConfiguration("use_dynamic_ee_prestart")
    declare_use_dynamic_ee_prestart_cmd = DeclareLaunchArgument(
        name="use_dynamic_ee_prestart",
        default_value="true",
        description="Enable dynamic EE prestart (EE spans L5 motion) vs sequential (EE after J5)",
    )

    declare_log_directory_cmd = DeclareLaunchArgument(
        name="log_directory",
        default_value=os.path.expanduser("~/.ros/logs"),
        description="Directory for rotating log files (Tier 3.1)",
    )

    declare_can_interface_cmd = DeclareLaunchArgument(
        name="can_interface",
        default_value="can0",
        description="CAN interface name for MG6010 motors",
    )

    declare_can_bitrate_cmd = DeclareLaunchArgument(
        name="can_bitrate",
        default_value="500000",
        description="CAN bitrate for MG6010 motors (500000 = 500 kbps)",
    )

    declare_skip_cleanup_cmd = DeclareLaunchArgument(
        name="skip_cleanup",
        default_value="false",
        description="Skip cleanup_previous_instances() (set true for launch_testing/CI)",
    )

    declare_log_level_cmd = DeclareLaunchArgument(
        name="log_level",
        default_value="info",
        description="Log level for yanthra_move node (debug, info, warn, error, fatal)",
    )

    declare_use_rviz_cmd = DeclareLaunchArgument(
        name="use_rviz",
        default_value="false",
        description="Launch RViz2 for robot visualization (simulation debugging)",
    )

    declare_enable_j5_collision_avoidance_cmd = DeclareLaunchArgument(
        name="enable_j5_collision_avoidance",
        default_value="true",
        description="Enable J5 collision avoidance for two-arm setups (J5 clamped by J3 tilt angle)",
    )

    urdf_path = LaunchConfiguration("urdf_path")

    # Get robot description share directory
    robo_desc_share = FindPackageShare(package="robot_description")

    # Default URDF file path using PathJoinSubstitution
    default_urdf_path = PathJoinSubstitution([robo_desc_share, "urdf", "MG6010_FLU.urdf"])

    # Declare URDF path argument
    declare_urdf_path_cmd = DeclareLaunchArgument(
        name="urdf_path",
        default_value=default_urdf_path,
        description="Path to URDF file for robot description",
    )

    # Use Command substitution for URDF loading (ROS 2 best practice)
    # This processes the URDF at launch time and handles large files efficiently
    # Wrap in ParameterValue to properly handle as string parameter
    robot_description = ParameterValue(Command(["cat ", urdf_path]), value_type=str)

    # Get yanthra_move config - use our fixed ROS1-equivalent parameters
    pkg_share = FindPackageShare(package="yanthra_move").find("yanthra_move")
    config_file = os.path.join(pkg_share, "config", "production.yaml")

    # Get MG6010 config - use three-motor configuration
    # Use three-motor config for production
    mg6010_pkg_path = FindPackageShare("motor_control_ros2").find("motor_control_ros2")
    mg6010_config_path = os.path.join(mg6010_pkg_path, "config", "production.yaml")

    print(f"ℹ️ MG6010 package path: {mg6010_pkg_path}")
    print(f"ℹ️ MG6010 config file: {mg6010_config_path}")
    print(f"ℹ️ Config file exists: {os.path.exists(mg6010_config_path)}")

    # Use PathJoinSubstitution for the launch system - three-motor config
    mg6010_config_file = PathJoinSubstitution(
        [FindPackageShare("motor_control_ros2"), "config", "production.yaml"]
    )

    # --- Rosbag2 recording setup ---
    # Load bag profiles and build topic list for the selected profile
    import yaml as _yaml
    from datetime import datetime as _dt
    import shutil as _shutil

    _bag_profiles_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "..",
        "web_dashboard",
        "config",
        "bag_profiles.yaml",
    )
    _bag_profiles = {}
    if os.path.exists(_bag_profiles_path):
        try:
            with open(_bag_profiles_path) as _f:
                _bag_profiles = _yaml.safe_load(_f).get("profiles", {})
        except Exception as _e:
            print(f"Warning: Failed to load bag_profiles.yaml: {_e}")

    # Resolve bag profile topics at launch-time (not via substitution)
    _bag_profile_name = "standard"
    for _i, _arg in enumerate(sys.argv):
        if _arg.startswith("bag_profile:="):
            _bag_profile_name = _arg.split(":=", 1)[1]
    _bag_topics = _bag_profiles.get(_bag_profile_name, _bag_profiles.get("standard", {})).get(
        "topics", []
    )

    _bags_dir = os.path.expanduser(os.environ.get("PRAGATI_BAG_DIR", "~/bags"))
    os.makedirs(_bags_dir, exist_ok=True)

    # Bag retention rotation — delete bags older than 7 days at launch
    _bag_retention_days = 7
    try:
        _now = time.time()
        for _entry in os.scandir(_bags_dir):
            if _entry.is_dir() and (_now - _entry.stat().st_mtime) > (_bag_retention_days * 86400):
                _shutil.rmtree(_entry.path, ignore_errors=True)
                print(f"Bag retention: removed old bag {_entry.name}")
    except Exception as _e:
        print(f"Warning: Bag retention cleanup failed: {_e}")

    _bag_output_dir = os.path.join(
        _bags_dir,
        f"trial_{_dt.now():%Y%m%d_%H%M%S}_{_bag_profile_name}",
    )
    _bag_record_cmd = [
        "ros2",
        "bag",
        "record",
        "--storage",
        "mcap",
        "--max-cache-size",
        "100000000",
        "--output",
        _bag_output_dir,
    ] + _bag_topics

    bag_record_process = ExecuteProcess(
        cmd=_bag_record_cmd,
        name="rosbag2_recorder",
        output="screen",
        condition=IfCondition(enable_bag_recording),
    )

    # 1. Robot State Publisher (publishes robot_description and TF transforms)
    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[{"robot_description": robot_description, "use_sim_time": use_sim_time}],
        output=output_log,
    )

    # 2. Joint State Publisher (fills in joints not managed by motor_control)
    #    When motor_control runs in simulation_mode, it publishes joint3/4/5
    #    positions from its physics simulator on /motor_joint_states.
    #    joint_state_publisher merges that via source_list and fills in joint2.
    #    When motor_control is in hardware mode with no CAN, it still publishes
    #    (empty or zero), so the merge is always valid.
    joint_state_publisher_node = Node(
        package="joint_state_publisher",
        executable="joint_state_publisher",
        name="joint_state_publisher",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "source_list": ["/motor_joint_states"],
            }
        ],
        output=output_log,
    )

    # 2b. RViz2 (optional, for simulation visualization/debugging)
    rviz_config_path = PathJoinSubstitution(
        [
            FindPackageShare("robot_description"),
            "config",
            "view_robot.rviz",
        ]
    )
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config_path],
        output="screen",
        condition=IfCondition(LaunchConfiguration("use_rviz")),
    )

    # 3. MG6010 Motor Controller Node (three motors with ROS 2 interface)
    # Production motor controller with multi-motor support
    mg6010_controller_node = Node(
        package="motor_control_ros2",
        executable="mg6010_controller_node",
        name="motor_control",
        parameters=[
            mg6010_config_file,
            {
                "interface_name": can_interface,
                "baud_rate": can_bitrate,
                "simulation_mode": use_simulation,
            },
        ],
        remappings=[
            # Remap so joint_state_publisher merges motor positions via source_list.
            # This prevents two publishers fighting over /joint_states and lets JSP
            # fill in joint2 (which motor_control doesn't manage).
            ("joint_states", "/motor_joint_states"),
        ],
        output=output_log,
    )

    # 4. Main Yanthra Move Node
    # This node contains the embedded joint position controllers:
    # - joint2_position_controller
    # - joint3_position_controller
    # - joint4_position_controller
    # - joint5_position_controller
    # - arm_controller functionality
    # FIXED: Topic naming corrected in joint_move.h to use position_controller convention
    # DELAYED: 7 seconds to allow motor homing to complete (~6s)
    yanthra_move_node = Node(
        package="yanthra_move",
        executable="yanthra_move_node",
        name="yanthra_move",
        ros_arguments=["--log-level", log_level],
        parameters=[
            config_file,
            {
                "simulation_mode": use_simulation,
                "use_simulation": use_simulation,  # must match simulation_mode; was missing — caused initializeGPIO() to skip on hardware
                "continuous_operation": continuous_operation,
                # joint4_multiposition/enabled: controlled by production.yaml (no launch arg override)
                # To change: edit src/yanthra_move/config/production.yaml -> joint4_multiposition/enabled
                "skip_homing": True,  # MG6010 controller pre-homes motors
                "YanthraLabCalibrationTesting": NotSubstitution(
                    enable_cotton_detection
                ),  # Enable ArUco calibration mode when cotton detection is OFF
                "use_preloaded_centroids": use_preloaded_centroids_arg,  # Load from centroid.txt or run live ArUco (when in calibration mode)
                "delays/use_dynamic_ee_prestart": use_dynamic_ee_prestart,  # EE timing mode
                "j5_collision_avoidance/enabled": enable_j5_collision_avoidance,  # Two-arm J5 collision limit
            },
        ],
        output=output_log,
    )

    # 5. ARM Client MQTT Bridge (launched after main system with delay - matches ROS-1)
    # This replicates the ROS-1 behavior where ARM client was started separately
    # via shell scripts with a delay to ensure ROS system is ready
    # ARM client script is in workspace root/launch/
    pkg_path = FindPackageShare("yanthra_move").find("yanthra_move")
    # pkg_path = /home/ubuntu/pragati_ros2/install/share/yanthra_move
    # Go up 3 levels: share -> install -> workspace_root (pragati_ros2)
    install_path = os.path.dirname(os.path.dirname(pkg_path))  # install/
    workspace_path = os.path.dirname(install_path)  # workspace root (pragati_ros2)
    arm_client_script = os.path.join(workspace_path, "launch", "ARM_client.py")

    print(f"ℹ️ ARM Client script path: {arm_client_script}")
    print(f"ℹ️ ARM Client script exists: {os.path.exists(arm_client_script)}")

    # =========================================================================
    # Task 5.1-5.4: ARM_client respawn with rate limiting
    # =========================================================================

    def _make_arm_client_execute():
        """Create an ExecuteProcess for ARM_client with current launch args."""
        return ExecuteProcess(
            cmd=[
                "python3",
                "-u",
                arm_client_script,
                "--mqtt-address",
                mqtt_address,
                "--client-id",
                arm_id,
            ],
            name="arm_client_process",
            output=output_log,
            condition=IfCondition(enable_arm_client),
        )

    def _on_arm_client_exit(event, context):
        """Handle ARM_client process exit with conditional respawn.

        Task 5.1: Schedules a TimerAction with 5s delay to relaunch on non-zero exit.
        Task 5.2: Enforces 5-per-60s restart limit.
        Task 5.3: Logs WARN on each restart with exit code and count.
        Task 5.4: Skips restart if shutting down or exit code was 0.
        """
        returncode = event.returncode

        # Task 5.4: Clean exit (code 0) — do not restart
        if returncode == 0:
            print(
                "[INFO] [pragati_complete.launch]: "
                "ARM_client exited cleanly (code 0) — not restarting"
            )
            return []

        # Task 5.4: Launch system is shutting down — do not restart
        if _arm_client_restart_state["shutting_down"]:
            print(
                "[INFO] [pragati_complete.launch]: "
                "ARM_client exited (code {}) during shutdown — not restarting".format(returncode)
            )
            return []

        # Task 5.2: Prune restart timestamps outside the rolling window
        now = time.monotonic()
        window_start = now - _ARM_CLIENT_RESTART_WINDOW_S
        _arm_client_restart_state["timestamps"] = [
            t for t in _arm_client_restart_state["timestamps"] if t > window_start
        ]

        recent_count = len(_arm_client_restart_state["timestamps"])

        # Task 5.2: Check rate limit
        if recent_count >= _ARM_CLIENT_MAX_RESTARTS:
            print(
                "[ERROR] [pragati_complete.launch]: "
                "ARM_client restart limit exceeded ({} restarts in {}s) — "
                "stopping restarts. Check ~/pragati_ros2/logs/ for arm_client_*.log".format(
                    _ARM_CLIENT_MAX_RESTARTS, _ARM_CLIENT_RESTART_WINDOW_S
                )
            )
            return []

        # Record this restart
        _arm_client_restart_state["timestamps"].append(now)
        restart_num = recent_count + 1

        # Task 5.3: Log WARN with exit code and restart count
        print(
            "[WARN] [pragati_complete.launch]: "
            "ARM_client exited with code {} — restarting in {}s "
            "(restart {}/{} in {}s window)".format(
                returncode,
                int(_ARM_CLIENT_RESTART_DELAY_S),
                restart_num,
                _ARM_CLIENT_MAX_RESTARTS,
                _ARM_CLIENT_RESTART_WINDOW_S,
            )
        )

        # Task 5.1: Schedule relaunch after delay
        new_process = _make_arm_client_execute()
        new_exit_handler = RegisterEventHandler(
            OnProcessExit(
                target_action=new_process,
                on_exit=_on_arm_client_exit,
            )
        )
        return [
            TimerAction(
                period=_ARM_CLIENT_RESTART_DELAY_S,
                actions=[new_process, new_exit_handler],
            )
        ]

    # Initial ARM_client ExecuteProcess (extracted from TimerAction for event handling)
    arm_client_execute = _make_arm_client_execute()

    # Task 5.1: Register exit handler for the initial process
    arm_client_exit_handler = RegisterEventHandler(
        OnProcessExit(
            target_action=arm_client_execute,
            on_exit=_on_arm_client_exit,
        )
    )

    # ARM client launched with 5s delay (optimized from 10s)
    # Logs are written to ~/pragati_ros2/logs/arm_client_<arm_id>_*.log for debugging
    arm_client_process = TimerAction(
        period=5.0,  # 5 second delay (optimized from 10s)
        actions=[arm_client_execute, arm_client_exit_handler],
    )

    # 6. Disk Space Monitor (Tier 3.1 - Log Rotation & Disk Space Protection)
    # TEMPORARILY DISABLED - executable not available
    # disk_space_monitor_node = Node(
    #     package='common_utils',
    #     executable='disk_space_monitor',
    #     name='disk_space_monitor',
    #     parameters=[{
    #         'log_directory': log_directory,
    #         'monitor_interval_sec': 60,
    #         'warning_threshold_gb': 2.0,
    #         'critical_threshold_gb': 1.0,
    #         'max_log_age_days': 7,
    #         'max_image_age_days': 3
    #     }],
    #     output=output_log
    # )

    # 7. Vision System: Cotton Detection OR ArUco Pattern Finder
    # When cotton detection is enabled: use full cotton detection with DepthAI
    # When cotton detection is disabled: use aruco pattern finder only

    cotton_detection_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [
                PathJoinSubstitution(
                    [
                        FindPackageShare("cotton_detection_ros2"),
                        "launch",
                        "cotton_detection_cpp.launch.py",
                    ]
                )
            ]
        ),
        launch_arguments={
            "simulation_mode": use_simulation,
        }.items(),
    )

    # Note: ArUco pattern finder is a standalone tool, not a ROS2 node
    # When cotton detection is disabled, vision features are not available
    # Users can run aruco_finder_oakd manually if needed

    # Cleanup is handled automatically in the generate_launch_description() function
    # No external cleanup script needed

    # Create the launch description and populate
    ld = LaunchDescription()
    # Route all node log files into the same per-run directory as launch.log
    # (launch always creates a unique run folder; LaunchLogDir() returns that folder)
    set_ros_log_dir_cmd = SetEnvironmentVariable(
        name="ROS_LOG_DIR",
        value=LaunchLogDir(),
    )

    # Declare the launch options
    ld.add_action(set_ros_log_dir_cmd)

    ld.add_action(declare_output_log_cmd)
    ld.add_action(declare_use_sim_time_cmd)
    ld.add_action(declare_use_simulation_cmd)
    ld.add_action(declare_continuous_operation_cmd)
    ld.add_action(declare_enable_arm_client_cmd)
    ld.add_action(declare_enable_cotton_detection_cmd)
    ld.add_action(declare_use_preloaded_centroids_cmd)
    ld.add_action(declare_mqtt_address_cmd)
    ld.add_action(declare_arm_id_cmd)  # Task 4.5
    ld.add_action(declare_log_directory_cmd)
    ld.add_action(declare_can_interface_cmd)
    ld.add_action(declare_can_bitrate_cmd)
    ld.add_action(declare_urdf_path_cmd)
    ld.add_action(declare_offline_mode_cmd)
    ld.add_action(declare_offline_image_path_cmd)
    ld.add_action(declare_use_dynamic_ee_prestart_cmd)
    ld.add_action(declare_enable_bag_recording_cmd)
    ld.add_action(declare_bag_profile_cmd)
    ld.add_action(declare_skip_cleanup_cmd)
    ld.add_action(declare_log_level_cmd)
    ld.add_action(declare_use_rviz_cmd)
    ld.add_action(declare_enable_j5_collision_avoidance_cmd)

    # Cleanup is handled automatically at the beginning of generate_launch_description()

    # Wait a moment after cleanup before starting nodes (optimized delay)
    delayed_nodes = TimerAction(
        period=0.3,  # 300ms delay after cleanup (optimized from 1s)
        actions=[
            robot_state_publisher_node,
            joint_state_publisher_node,
            mg6010_controller_node,  # Three-motor controller (joints 3, 4, 5)
            # disk_space_monitor_node,  # Tier 3.1 - DISABLED (executable not available)
        ],
    )

    # Add delayed nodes after cleanup
    ld.add_action(delayed_nodes)

    # RViz2 (conditional - only when use_rviz:=true)
    ld.add_action(rviz_node)

    # Yanthra Move with additional delay to allow motor homing (7s total: 0.3s + 6.7s)
    yanthra_move_delayed = TimerAction(
        period=7.0,  # 7 second delay to allow motor homing to complete
        actions=[yanthra_move_node],
    )
    ld.add_action(yanthra_move_delayed)

    # Conditionally add cotton detection OR aruco pattern finder based on parameter
    cotton_detection_delayed = TimerAction(
        period=0.3,
        actions=[cotton_detection_launch],
        condition=IfCondition(enable_cotton_detection),
    )
    ld.add_action(cotton_detection_delayed)

    # Rosbag2 recorder (conditional on enable_bag_recording)
    ld.add_action(bag_record_process)

    # Add ARM client with delay (matches ROS-1 launcher.sh timing)
    ld.add_action(arm_client_process)

    # Task 5.4: Register shutdown handler to suppress restarts during teardown
    def _on_launch_shutdown(event, context):
        _arm_client_restart_state["shutting_down"] = True
        return []

    ld.add_action(RegisterEventHandler(OnShutdown(on_shutdown=_on_launch_shutdown)))

    return ld
