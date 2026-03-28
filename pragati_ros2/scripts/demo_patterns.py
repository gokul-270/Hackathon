#!/usr/bin/env python3
"""
Gazebo Demo Patterns — motion pattern library, video capture, and orchestrator.

Provides composable motion pattern functions for validating Pragati's
three-wheeled omnidirectional robot in Gazebo Harmonic simulation.

Usage:
    python3 scripts/demo_patterns.py                  # run all patterns
    python3 scripts/demo_patterns.py --field           # field ops only
    python3 scripts/demo_patterns.py --geometric       # geometric only
    python3 scripts/demo_patterns.py --stress          # stress tests only
    python3 scripts/demo_patterns.py --letters         # letter patterns (P,D,8,O,S,L,U,Z)
    python3 scripts/demo_patterns.py --only letter_P letter_L circle  # specific patterns
    python3 scripts/demo_patterns.py --record          # per-pattern video (overhead camera)
    python3 scripts/demo_patterns.py --pause 3.0       # 3s between patterns
    python3 scripts/demo_patterns.py --speed-scale 0.5 # half speed
"""

import argparse
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from typing import List, Tuple

import rclpy
from geometry_msgs.msg import Twist
from rclpy.parameter import Parameter


# ---------------------------------------------------------------------------
# 1. Primitive Motion Patterns
#    Each returns list[tuple[Twist, float]] — (message, duration_seconds).
#    The orchestrator's execute_pattern() handles actual publishing at 10Hz.
# ---------------------------------------------------------------------------

def _twist(linear_x: float = 0.0, angular_z: float = 0.0) -> Twist:
    """Create a Twist message with the given velocities."""
    msg = Twist()
    msg.linear.x = linear_x
    msg.angular.z = angular_z
    return msg


def straight(speed: float = 0.3, duration: float = 3.0) -> List[Tuple[Twist, float]]:
    """Drive straight at *speed* m/s for *duration* seconds."""
    return [(_twist(linear_x=speed), duration)]


def arc(speed: float = 0.3, radius: float = 1.0, duration: float = 3.0) -> List[Tuple[Twist, float]]:
    """Drive an arc.  angular_z = speed / radius."""
    angular_z = speed / radius if radius != 0.0 else 0.0
    return [(_twist(linear_x=speed, angular_z=angular_z), duration)]


def turn_in_place(rate: float = 0.5, duration: float = 2.0) -> List[Tuple[Twist, float]]:
    """Rotate in place at *rate* rad/s for *duration* seconds."""
    return [(_twist(angular_z=rate), duration)]


def stop(duration: float = 1.0) -> List[Tuple[Twist, float]]:
    """Hold zero velocity for *duration* seconds (inter-maneuver pause)."""
    return [(_twist(), duration)]


# ---------------------------------------------------------------------------
# 2. Composite Motion Patterns
# ---------------------------------------------------------------------------

def row_traversal(speed: float = 0.5, length: float = 5.0) -> List[Tuple[Twist, float]]:
    """Drive a straight row at working speed for *length* seconds."""
    return straight(speed=speed, duration=length)


def u_turn(speed: float = 0.3, radius: float = 1.0,
           direction: str = 'left') -> List[Tuple[Twist, float]]:
    """180-degree turn.  direction='left' → positive angular_z."""
    # duration for 180° = π × radius / speed
    dur = math.pi * radius / speed if speed != 0.0 else 0.0
    sign = 1.0 if direction == 'left' else -1.0
    angular_z = sign * speed / radius if radius != 0.0 else 0.0
    return [(_twist(linear_x=speed, angular_z=angular_z), dur)]


def headland_uturn(speed: float = 0.3,
                   direction: str = 'left') -> List[Tuple[Twist, float]]:
    """180-degree turn in place.  direction='left' → positive angular_z."""
    # Use speed to derive turn rate (clamped to safe range)
    rate = min(abs(speed), 1.0) if speed != 0.0 else 0.5
    dur = math.pi / rate
    sign = 1.0 if direction == 'left' else -1.0
    cmds: List[Tuple[Twist, float]] = []
    cmds.extend(turn_in_place(rate=sign * rate, duration=dur))
    cmds.extend(stop(0.5))
    return cmds


def s_pattern(speed: float = 0.3, num_rows: int = 3,
              row_length: float = 4.0) -> List[Tuple[Twist, float]]:
    """Traverse *num_rows* rows connected by alternating U-turns."""
    cmds: List[Tuple[Twist, float]] = []
    for i in range(num_rows):
        cmds.extend(row_traversal(speed=speed, length=row_length))
        if i < num_rows - 1:
            direction = 'left' if i % 2 == 0 else 'right'
            cmds.extend(stop(0.5))
            cmds.extend(headland_uturn(speed=speed, direction=direction))
            cmds.extend(stop(0.5))
    return cmds


def circle(speed: float = 0.3, radius: float = 1.0,
           revolutions: int = 1) -> List[Tuple[Twist, float]]:
    """Drive *revolutions* full circles of given *radius*."""
    dur_one = 2.0 * math.pi * radius / speed if speed != 0.0 else 0.0
    angular_z = speed / radius if radius != 0.0 else 0.0
    return [(_twist(linear_x=speed, angular_z=angular_z), dur_one * revolutions)]


def figure_eight(speed: float = 0.3,
                 radius: float = 1.0) -> List[Tuple[Twist, float]]:
    """Drive a figure-eight: circle left then circle right."""
    dur = 2.0 * math.pi * radius / speed if speed != 0.0 else 0.0
    angular_z = speed / radius if radius != 0.0 else 0.0
    cmds: List[Tuple[Twist, float]] = []
    cmds.append((_twist(linear_x=speed, angular_z=angular_z), dur))
    cmds.append((_twist(linear_x=speed, angular_z=-angular_z), dur))
    return cmds


def square(speed: float = 0.3,
           side_length: float = 3.0) -> List[Tuple[Twist, float]]:
    """Drive a square: 4 straights with 90° turn-in-place between each."""
    # 90° turn: π/2 rad at 0.5 rad/s ≈ 3.14s
    turn_rate = 0.5
    turn_dur = (math.pi / 2.0) / turn_rate
    cmds: List[Tuple[Twist, float]] = []
    for i in range(4):
        cmds.extend(straight(speed=speed, duration=side_length))
        cmds.extend(stop(0.5))
        cmds.extend(turn_in_place(rate=turn_rate, duration=turn_dur))
        cmds.extend(stop(0.5))
    return cmds


def diamond(speed: float = 0.3,
            side_length: float = 3.0) -> List[Tuple[Twist, float]]:
    """Drive a diamond (square rotated 45°)."""
    turn_rate = 0.5
    # Initial 45° turn
    turn_45_dur = (math.pi / 4.0) / turn_rate
    turn_90_dur = (math.pi / 2.0) / turn_rate
    cmds: List[Tuple[Twist, float]] = []
    cmds.extend(turn_in_place(rate=turn_rate, duration=turn_45_dur))
    cmds.extend(stop(0.5))
    for i in range(4):
        cmds.extend(straight(speed=speed, duration=side_length))
        cmds.extend(stop(0.5))
        cmds.extend(turn_in_place(rate=turn_rate, duration=turn_90_dur))
        cmds.extend(stop(0.5))
    return cmds


# -- Stress test patterns --

def sharp_turn(speed: float = 0.5,
               max_angular: float = 1.0) -> List[Tuple[Twist, float]]:
    """Drive straight then command a sudden angular velocity change."""
    cmds: List[Tuple[Twist, float]] = []
    cmds.extend(straight(speed=speed, duration=2.0))
    cmds.append((_twist(linear_x=speed, angular_z=max_angular), 3.0))
    cmds.extend(stop(1.0))
    return cmds


def sudden_stop(speed: float = 0.5) -> List[Tuple[Twist, float]]:
    """Drive at speed then publish zero velocity instantly."""
    cmds: List[Tuple[Twist, float]] = []
    cmds.extend(straight(speed=speed, duration=3.0))
    cmds.extend(stop(2.0))
    return cmds


def forward_reverse(speed: float = 0.5,
                    cycles: int = 3) -> List[Tuple[Twist, float]]:
    """Alternate between forward and reverse *cycles* times."""
    cmds: List[Tuple[Twist, float]] = []
    for _ in range(cycles):
        cmds.extend(straight(speed=speed, duration=2.0))
        cmds.extend(stop(0.5))
        cmds.extend(straight(speed=-speed, duration=2.0))
        cmds.extend(stop(0.5))
    return cmds


def max_steering_hold(angular_speed: float = 1.0,
                       duration: float = 5.0) -> List[Tuple[Twist, float]]:
    """Hold maximum angular velocity for a sustained period."""
    return turn_in_place(rate=angular_speed, duration=duration)


# ---------------------------------------------------------------------------
# 2b. Letter / Glyph Patterns
#
#     Each letter is driven as a continuous path.  The robot starts at the
#     bottom-left of the letter and traces it in one pass.  Letter height
#     is configurable (default 5 m) for visibility in the Gazebo camera.
#
#     Convention:
#       - "up"   = straight(+speed)   (robot drives forward = +X in field)
#       - "down" = straight(-speed)   (reverse)
#       - turns use turn_in_place() then straight segments
#       - arcs  use arc() for curves
# ---------------------------------------------------------------------------

def letter_L(speed: float = 0.3, height: float = 5.0) -> List[Tuple[Twist, float]]:
    """Trace the letter L: vertical stroke up, then horizontal stroke right.

    Start: bottom-left.  Drive up *height*, 90° right turn, drive right *height/2*.
    """
    turn_rate = 0.5
    turn_90 = (math.pi / 2.0) / turn_rate
    cmds: List[Tuple[Twist, float]] = []
    cmds.extend(straight(speed=speed, duration=height / speed))
    cmds.extend(stop(0.3))
    # 90° clockwise turn (negative rate = turn right in ROS convention)
    cmds.extend(turn_in_place(rate=-turn_rate, duration=turn_90))
    cmds.extend(stop(0.3))
    cmds.extend(straight(speed=speed, duration=(height * 0.5) / speed))
    return cmds


def letter_U(speed: float = 0.3, height: float = 5.0) -> List[Tuple[Twist, float]]:
    """Trace the letter U: down-left stroke, semicircle at bottom, up-right stroke.

    Start: top-left.  Drive down, semicircle right, drive up.
    """
    radius = height * 0.25  # semicircle radius
    leg = height - radius   # vertical leg length
    cmds: List[Tuple[Twist, float]] = []
    # Drive forward (down the left stroke)
    cmds.extend(straight(speed=speed, duration=leg / speed))
    # Semicircle at bottom (180° arc turning right)
    arc_dur = math.pi * radius / speed
    angular_z = speed / radius
    cmds.append((_twist(linear_x=speed, angular_z=-angular_z), arc_dur))
    # Drive forward (up the right stroke)
    cmds.extend(straight(speed=speed, duration=leg / speed))
    return cmds


def letter_S(speed: float = 0.3, height: float = 5.0) -> List[Tuple[Twist, float]]:
    """Trace the letter S: two opposing semicircles stacked vertically.

    Start: bottom-right.  Upper semicircle curves left, lower curves right.
    """
    radius = height * 0.25  # each semicircle is 1/4 of total height
    arc_dur = math.pi * radius / speed
    angular_z = speed / radius
    cmds: List[Tuple[Twist, float]] = []
    # Bottom semicircle (curving left = positive angular_z)
    cmds.append((_twist(linear_x=speed, angular_z=angular_z), arc_dur))
    # Top semicircle (curving right = negative angular_z)
    cmds.append((_twist(linear_x=speed, angular_z=-angular_z), arc_dur))
    return cmds


def letter_P(speed: float = 0.3, height: float = 5.0) -> List[Tuple[Twist, float]]:
    """Trace the letter P: vertical stroke up, then semicircle back down to midpoint.

    Start: bottom.  Drive up full height, then semicircle curving right
    back down to the midpoint.
    """
    radius = height * 0.25  # semicircle radius = 1/4 height
    arc_dur = math.pi * radius / speed
    angular_z = speed / radius
    cmds: List[Tuple[Twist, float]] = []
    # Vertical stroke up
    cmds.extend(straight(speed=speed, duration=height / speed))
    cmds.extend(stop(0.3))
    # Semicircle curving right (clockwise from top, comes back to midpoint)
    cmds.append((_twist(linear_x=speed, angular_z=-angular_z), arc_dur))
    return cmds


def letter_D(speed: float = 0.3, height: float = 5.0) -> List[Tuple[Twist, float]]:
    """Trace the letter D: vertical stroke up, then large arc back to start.

    Start: bottom.  Drive up full height, then a large semicircular arc
    curving right back down to the starting point.
    """
    radius = height * 0.5  # semicircle spans full height
    arc_dur = math.pi * radius / speed
    angular_z = speed / radius
    cmds: List[Tuple[Twist, float]] = []
    # Vertical stroke up
    cmds.extend(straight(speed=speed, duration=height / speed))
    cmds.extend(stop(0.3))
    # Large semicircle arc back to bottom (curving right)
    cmds.append((_twist(linear_x=speed, angular_z=-angular_z), arc_dur))
    return cmds


def letter_Z(speed: float = 0.3, height: float = 5.0) -> List[Tuple[Twist, float]]:
    """Trace the letter Z: top horizontal, diagonal down-left, bottom horizontal.

    Start: top-left.  Drive right, then diagonal down-left, then right again.
    """
    width = height * 0.6
    turn_rate = 0.5
    # Angles: first turn ~135° right (from +X heading to diagonal down-left)
    # diagonal length = sqrt(height^2 + width^2)
    diag = math.sqrt(height ** 2 + width ** 2)
    diag_angle = math.atan2(height, width)  # angle of diagonal from horizontal
    # Turn from facing right (+X) to facing diagonal down-left
    # That's a turn of (pi - diag_angle) to the right... but we need to think
    # in terms of robot heading.
    # After top stroke: facing +X. Need to face roughly (-width, -height) direction.
    # Angle change = pi + diag_angle (about 180° + ~59°... no)
    # Actually: heading +X = 0. Target heading = atan2(-height, -width) = -(pi - diag_angle)
    # Turn amount = target - current = -(pi - diag_angle)
    turn_to_diag = math.pi - diag_angle  # ~2.11 rad, turn right
    turn_to_diag_dur = turn_to_diag / turn_rate
    # After diagonal: facing down-left. Need to face +X again.
    turn_to_right = turn_to_diag  # same angle back
    turn_to_right_dur = turn_to_diag_dur

    cmds: List[Tuple[Twist, float]] = []
    # Top horizontal stroke (right)
    cmds.extend(straight(speed=speed, duration=width / speed))
    cmds.extend(stop(0.3))
    # Turn to diagonal direction (turn right = negative rate)
    cmds.extend(turn_in_place(rate=-turn_rate, duration=turn_to_diag_dur))
    cmds.extend(stop(0.3))
    # Diagonal stroke
    cmds.extend(straight(speed=speed, duration=diag / speed))
    cmds.extend(stop(0.3))
    # Turn back to face right (turn left = positive rate)
    cmds.extend(turn_in_place(rate=turn_rate, duration=turn_to_right_dur))
    cmds.extend(stop(0.3))
    # Bottom horizontal stroke (right)
    cmds.extend(straight(speed=speed, duration=width / speed))
    return cmds


# ---------------------------------------------------------------------------
# 3. Teleport / Reset
# ---------------------------------------------------------------------------

def teleport_robot(x: float = -10.0, y: float = 0.9, z: float = 1.0,
                   model_name: str = 'vehicle_control',
                   world_name: str = 'cotton_field',
                   facing_x_positive: bool = True) -> bool:
    """Teleport the robot to a given world position via ``gz service``.

    The URDF requires a 90° roll to stand upright.  *facing_x_positive*
    controls the yaw: True → heading into the field (+X), False → default
    spawn heading (-X).

    Returns True on success.
    """
    # Quaternion for roll=90° only (facing +X)
    # quat = (w=0.7071, x=0.7071, y=0, z=0)
    if facing_x_positive:
        qw, qx, qy, qz = 0.707107, 0.707107, 0.0, 0.0
    else:
        # roll=90° + yaw=180°  → (w≈0, x≈0, y=0.7071, z=0.7071)
        qw, qx, qy, qz = 0.0, 0.0, 0.707107, 0.707107

    req = (
        f'name: "{model_name}", '
        f'position: {{x: {x}, y: {y}, z: {z}}}, '
        f'orientation: {{x: {qx}, y: {qy}, z: {qz}, w: {qw}}}'
    )
    try:
        result = subprocess.run(
            [
                'gz', 'service',
                '-s', f'/world/{world_name}/set_pose',
                '--reqtype', 'gz.msgs.Pose',
                '--reptype', 'gz.msgs.Boolean',
                '--timeout', '5000',
                '--req', req,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f'[teleport] WARNING: set_pose failed '
                  f'(exit {result.returncode}): {result.stderr.strip()}')
            return False
        print(f'[teleport] Robot moved to ({x:.1f}, {y:.1f}, {z:.1f})')
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f'[teleport] WARNING: {exc}')
        return False


def teleport_to_field_start() -> bool:
    """Teleport robot to the field_marker_start position, facing +X."""
    return teleport_robot(x=-10.0, y=0.9, z=1.0, facing_x_positive=True)


# ---------------------------------------------------------------------------
# 3b. Ground Path Visualization
#
#     Compute ideal waypoints for a pattern by numerically integrating
#     the (Twist, duration) commands, then spawn small flat markers on the
#     Gazebo ground plane so the intended path is visible.
# ---------------------------------------------------------------------------

def compute_path_waypoints(
    commands: List[Tuple[Twist, float]],
    start_x: float = -10.0,
    start_y: float = 0.9,
    start_heading: float = 0.0,
    dt: float = 0.1,
    spacing: float = 0.5,
) -> List[Tuple[float, float]]:
    """Numerically integrate Twist commands to compute (x, y) waypoints.

    Parameters
    ----------
    commands : list of (Twist, duration)
        The motion pattern commands.
    start_x, start_y : float
        Starting world position (matches teleport_to_field_start).
    start_heading : float
        Initial heading in radians (0 = facing +X).
    dt : float
        Integration time step in seconds.
    spacing : float
        Minimum distance between emitted waypoints (metres).

    Returns
    -------
    list of (x, y)
        Waypoints along the ideal path.
    """
    x, y, theta = start_x, start_y, start_heading
    waypoints: List[Tuple[float, float]] = [(x, y)]
    accum = 0.0  # accumulated distance since last waypoint

    for twist, duration in commands:
        v = twist.linear.x
        w = twist.angular.z
        steps = int(duration / dt)
        for _ in range(steps):
            x += v * math.cos(theta) * dt
            y += v * math.sin(theta) * dt
            theta += w * dt
            accum += abs(v) * dt
            if accum >= spacing:
                waypoints.append((x, y))
                accum = 0.0

    # Always include the final point
    if len(waypoints) < 2 or (
        math.hypot(waypoints[-1][0] - x, waypoints[-1][1] - y) > 0.1
    ):
        waypoints.append((x, y))

    return waypoints


def _marker_sdf(name: str, x: float, y: float,
                r: float = 1.0, g: float = 0.9, b: float = 0.0) -> str:
    """Return an SDF string for a small flat ground marker at (x, y)."""
    return (
        f'<?xml version="1.0" ?>'
        f'<sdf version="1.9">'
        f'<model name="{name}">'
        f'  <static>true</static>'
        f'  <pose>{x} {y} 0.005 0 0 0</pose>'
        f'  <link name="marker">'
        f'    <visual name="v">'
        f'      <geometry>'
        f'        <cylinder>'
        f'          <radius>0.15</radius>'
        f'          <length>0.01</length>'
        f'        </cylinder>'
        f'      </geometry>'
        f'      <material>'
        f'        <ambient>{r} {g} {b} 1</ambient>'
        f'        <diffuse>{r} {g} {b} 1</diffuse>'
        f'      </material>'
        f'    </visual>'
        f'  </link>'
        f'</model>'
        f'</sdf>'
    )


# Track spawned marker names for cleanup
_spawned_markers: List[str] = []


def spawn_ground_path(
    commands: List[Tuple[Twist, float]],
    pattern_name: str = 'path',
    start_x: float = -10.0,
    start_y: float = 0.9,
    start_heading: float = 0.0,
    spacing: float = 0.5,
    world_name: str = 'cotton_field',
    color: Tuple[float, float, float] = (1.0, 0.9, 0.0),
) -> int:
    """Spawn ground markers along the ideal path for a pattern.

    Parameters
    ----------
    commands : list of (Twist, duration)
        The motion pattern commands.
    pattern_name : str
        Prefix for marker model names.
    start_x, start_y, start_heading : float
        Robot starting position and heading.
    spacing : float
        Distance between markers in metres.
    world_name : str
        Gazebo world name.
    color : tuple of (r, g, b)
        Marker colour (0-1 range).

    Returns
    -------
    int
        Number of markers spawned.
    """
    global _spawned_markers

    waypoints = compute_path_waypoints(
        commands,
        start_x=start_x,
        start_y=start_y,
        start_heading=start_heading,
        spacing=spacing,
    )

    count = 0
    r, g, b = color
    # Write SDF to a temp file to avoid protobuf string escaping issues
    for i, (wx, wy) in enumerate(waypoints):
        name = f'_path_{pattern_name}_{i}'
        sdf = _marker_sdf(name, wx, wy, r=r, g=g, b=b)
        try:
            # Write SDF to temp file, use sdf_filename field
            sdf_file = os.path.join(tempfile.gettempdir(), f'{name}.sdf')
            with open(sdf_file, 'w') as f:
                f.write(sdf)
            result = subprocess.run(
                [
                    'gz', 'service',
                    '-s', f'/world/{world_name}/create',
                    '--reqtype', 'gz.msgs.EntityFactory',
                    '--reptype', 'gz.msgs.Boolean',
                    '--timeout', '2000',
                    '--req', f'sdf_filename: "{sdf_file}"',
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                _spawned_markers.append(name)
                count += 1
            # Clean up temp file
            try:
                os.remove(sdf_file)
            except OSError:
                pass
        except (FileNotFoundError, subprocess.TimeoutExpired):
            break  # gz not available, stop trying

    print(f'[ground_path] Spawned {count} markers for "{pattern_name}" '
          f'({len(waypoints)} waypoints)')
    return count


def clear_ground_path(world_name: str = 'cotton_field') -> int:
    """Remove all previously spawned ground path markers.

    Returns the number of markers removed.
    """
    global _spawned_markers
    removed = 0
    for name in _spawned_markers:
        try:
            result = subprocess.run(
                [
                    'gz', 'service',
                    '-s', f'/world/{world_name}/remove',
                    '--reqtype', 'gz.msgs.Entity',
                    '--reptype', 'gz.msgs.Boolean',
                    '--timeout', '2000',
                    '--req', f'name: "{name}", type: 2',
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                removed += 1
        except (FileNotFoundError, subprocess.TimeoutExpired):
            break
    print(f'[ground_path] Removed {removed}/{len(_spawned_markers)} markers')
    _spawned_markers.clear()
    return removed


# ---------------------------------------------------------------------------
# 4. Video Capture Functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 3d. Video Recording
#
#     Uses the CameraVideoRecorder server-side plugin attached to the
#     overhead camera in cotton_field.sdf.  Recording is controlled via
#     the ``/overhead/record_video`` gz service endpoint.  OGV (Theora)
#     format is used because Gazebo's video encoder produces black frames
#     with MP4 on WSLg + ogre2 platforms.
# ---------------------------------------------------------------------------

# gz service endpoint for the CameraVideoRecorder plugin
_RECORD_SERVICE = '/overhead/record_video'


def verify_recording(filepath: str) -> bool:
    """Verify that a recorded video file exists and is non-empty."""
    if os.path.isfile(filepath):
        size = os.path.getsize(filepath)
        if size > 0:
            print(f'[video] Verified: {filepath} ({size} bytes)')
            return True
        else:
            print(f'[video] WARNING: {filepath} exists but is 0 bytes')
            return False
    else:
        print(f'[video] WARNING: {filepath} not found')
        return False


class VideoRecorder:
    """Records video from the overhead camera sensor in Gazebo.

    Uses the CameraVideoRecorder server-side plugin which is attached to
    the overhead camera model in ``cotton_field.sdf``.  Recording is
    controlled via ``gz service`` calls to start/stop the plugin.

    OGV (Theora) format is used because Gazebo's built-in video encoder
    produces black frames with MP4 on WSLg + ogre2.
    """

    def __init__(self, video_dir: str | None = None, enabled: bool = True):
        if video_dir is None:
            video_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'videos',
            )
        os.makedirs(video_dir, exist_ok=True)
        self.video_dir = video_dir
        self.enabled = enabled
        self._current_file: str | None = None
        self._recorded_files: List[str] = []
        self._recording: bool = False

    def _make_filepath(self, name: str) -> str:
        """Generate a video filepath for a pattern name."""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        return os.path.join(self.video_dir, f'{safe_name}_{ts}.ogv')

    def _gz_record_service(self, start: bool = False,
                           stop: bool = False,
                           filepath: str = '') -> bool:
        """Call the gz service to start or stop recording.

        Returns True if the service responded successfully.
        """
        req_parts = []
        if start:
            req_parts.append('start: true')
            req_parts.append('format: "ogv"')
            if filepath:
                req_parts.append(f'save_filename: "{filepath}"')
        if stop:
            req_parts.append('stop: true')
        req = ', '.join(req_parts)

        try:
            result = subprocess.run(
                [
                    'gz', 'service',
                    '-s', _RECORD_SERVICE,
                    '--reqtype', 'gz.msgs.VideoRecord',
                    '--reptype', 'gz.msgs.Boolean',
                    '--timeout', '5000',
                    '--req', req,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and 'data: true' in result.stdout:
                return True
            if 'timed out' in result.stdout.lower():
                print(f'[video] WARNING: gz service timed out')
                return False
            print(f'[video] WARNING: gz service returned: '
                  f'{result.stdout.strip()}')
            return False
        except FileNotFoundError:
            print('[video] WARNING: gz CLI not found')
            return False
        except subprocess.TimeoutExpired:
            print('[video] WARNING: gz service call timed out')
            return False

    def start(self, pattern_name: str = 'demo') -> bool:
        """Start recording video for the given pattern.

        Returns True if recording started successfully.
        """
        if not self.enabled:
            return False
        if self._recording:
            self.stop()

        filepath = self._make_filepath(pattern_name)
        self._current_file = filepath

        if self._gz_record_service(start=True, filepath=filepath):
            self._recording = True
            print(f'[video] Recording started -> {filepath}')
            return True
        else:
            print(f'[video] WARNING: failed to start recording')
            self._current_file = None
            return False

    def stop(self) -> str | None:
        """Stop the current recording.

        Returns the filepath of the recorded video, or None if not recording.
        """
        filepath = self._current_file
        if not self._recording:
            return None

        self._gz_record_service(stop=True)
        self._recording = False
        self._current_file = None

        # Give Gazebo a moment to finalize the file
        time.sleep(1.0)

        if filepath:
            print(f'[video] Recording stopped')
            if verify_recording(filepath):
                self._recorded_files.append(filepath)
                return filepath
        return None

    @property
    def recorded_files(self) -> List[str]:
        """List of successfully recorded video file paths."""
        return list(self._recorded_files)

    def set_label(self, text: str) -> None:
        """No-op for API compatibility."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


# ---------------------------------------------------------------------------
# 4. Orchestrator Core
# ---------------------------------------------------------------------------

# Flag set by signal handler to request graceful shutdown.
_interrupted = False


def _handle_signal(signum, frame):
    global _interrupted
    _interrupted = True


def execute_pattern(node, publisher, commands: List[Tuple[Twist, float]],
                    speed_scale: float = 1.0) -> bool:
    """Publish a sequence of (Twist, duration) tuples at 10 Hz.

    Returns True if completed, False if interrupted.
    """
    global _interrupted
    for msg, duration in commands:
        if _interrupted:
            return False
        # Apply speed scaling
        scaled = _twist(
            linear_x=msg.linear.x * speed_scale,
            angular_z=msg.angular.z * speed_scale,
        )
        elapsed = 0.0
        interval = 0.1  # 10 Hz
        while elapsed < duration:
            if _interrupted:
                return False
            try:
                publisher.publish(scaled)
                rclpy.spin_once(node, timeout_sec=0.01)
            except Exception:
                return False
            time.sleep(interval)
            elapsed += interval
    # Clean stop after pattern
    try:
        publisher.publish(_twist())
    except Exception:
        pass
    return True


# -- Demo sequence definitions --

def _field_patterns() -> List[Tuple[str, List[Tuple[Twist, float]]]]:
    """Field operation patterns with descriptive names."""
    return [
        ('row_traversal', row_traversal(speed=0.5, length=5.0)),
        ('headland_uturn_left', headland_uturn(speed=0.3, direction='left')),
        ('headland_uturn_right', headland_uturn(speed=0.3, direction='right')),
        ('s_pattern_3rows', s_pattern(speed=0.3, num_rows=3, row_length=4.0)),
    ]


def _geometric_patterns() -> List[Tuple[str, List[Tuple[Twist, float]]]]:
    """Geometric validation patterns."""
    return [
        ('circle', circle(speed=0.3, radius=1.0, revolutions=1)),
        ('figure_eight', figure_eight(speed=0.3, radius=1.0)),
        ('square', square(speed=0.3, side_length=3.0)),
        ('diamond', diamond(speed=0.3, side_length=3.0)),
    ]


def _stress_patterns() -> List[Tuple[str, List[Tuple[Twist, float]]]]:
    """Stress test patterns."""
    return [
        ('sharp_turn', sharp_turn(speed=0.5, max_angular=1.0)),
        ('sudden_stop', sudden_stop(speed=0.5)),
        ('forward_reverse', forward_reverse(speed=0.5, cycles=3)),
        ('max_steering_hold', max_steering_hold(angular_speed=1.0, duration=5.0)),
    ]


def _letter_patterns() -> List[Tuple[str, List[Tuple[Twist, float]]]]:
    """Letter / glyph tracing patterns.

    Letters are 10m tall — fits comfortably within the 20m field (x=-10 to
    x=+10) while being ~5x the robot's 2m width for clear readability.
    """
    h = 10.0   # letter height in metres
    spd = 1.5  # fast enough for dynamic video while staying controllable
    r = h * 0.25  # radius for circle/figure-8, proportional to letter size
    return [
        ('letter_P', letter_P(speed=spd, height=h)),
        ('letter_D', letter_D(speed=spd, height=h)),
        ('letter_8', figure_eight(speed=spd, radius=r)),
        ('letter_O', circle(speed=spd, radius=r, revolutions=1)),
        ('letter_S', letter_S(speed=spd, height=h)),
        ('letter_L', letter_L(speed=spd, height=h)),
        ('letter_U', letter_U(speed=spd, height=h)),
        ('letter_Z', letter_Z(speed=spd, height=h)),
    ]


CATEGORY_MAP = {
    'field': ('Field Operations', _field_patterns),
    'geometric': ('Geometric Validation', _geometric_patterns),
    'stress': ('Stress Tests', _stress_patterns),
    'letters': ('Letter Patterns', _letter_patterns),
}


def run_demo(categories: List[str], record_video: bool = False,
             video_dir: str | None = None, pause: float = 2.0,
             speed_scale: float = 1.0,
             only: List[str] | None = None) -> None:
    """Run the demo sequence.

    Parameters
    ----------
    categories : list of str
        Which pattern categories to run ('field', 'geometric', 'stress',
        'letters').
    record_video : bool
        Whether to record video (per-pattern OGV files via CameraVideoRecorder).
    video_dir : str or None
        Custom video output directory (None → auto 'videos/' in project root).
    pause : float
        Inter-pattern pause in seconds.
    speed_scale : float
        Scale factor for all velocities (1.0 = normal).
    only : list of str or None
        If set, only run patterns whose names are in this list.
    """
    global _interrupted
    _interrupted = False

    # Install signal handlers
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ROS2 init
    rclpy.init()
    node = rclpy.create_node(
        'demo_patterns',
        parameter_overrides=[
            Parameter('use_sim_time', Parameter.Type.BOOL, True),
        ],
    )
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)

    # Wait for publisher discovery
    print('[demo] Waiting for publisher setup...')
    time.sleep(1.0)

    # Build pattern list from selected categories
    # Each entry: (cat_key, cat_label, name, commands)
    all_patterns: List[Tuple[str, str, str, List[Tuple[Twist, float]]]] = []
    for cat_key in categories:
        if cat_key not in CATEGORY_MAP:
            print(f'[demo] WARNING: unknown category "{cat_key}", skipping')
            continue
        cat_label, factory = CATEGORY_MAP[cat_key]
        for name, cmds in factory():
            all_patterns.append((cat_key, cat_label, name, cmds))

    # Filter to specific patterns if --only was used
    if only:
        only_set = set(only)
        all_patterns = [p for p in all_patterns if p[2] in only_set]
        if not all_patterns:
            print(f'[demo] ERROR: no patterns matched --only {only}')
            print(f'       Available: {[n for _, _, n, _ in all_patterns]}')
            return

    total = len(all_patterns)
    completed = 0
    failed: List[str] = []
    skipped: List[str] = []
    start_time = time.time()

    print(f'[demo] Starting demo: {total} patterns, '
          f'categories={categories}, speed_scale={speed_scale}')
    print('=' * 60)

    with VideoRecorder(video_dir=video_dir, enabled=record_video) as recorder:
        for idx, (cat_key, cat_label, name, cmds) in enumerate(all_patterns):
            if _interrupted:
                skipped.extend(n for _, _, n, _ in all_patterns[idx:])
                break

            # Teleport to field start before each pattern
            teleport_to_field_start()
            time.sleep(2.0)  # let physics settle after teleport

            print(f'\n[{cat_label.lower()}] Starting: {name}  '
                  f'({idx + 1}/{total})')

            # Start per-pattern video recording
            recorder.start(pattern_name=name)

            try:
                ok = execute_pattern(node, publisher, cmds,
                                     speed_scale=speed_scale)
                if ok:
                    completed += 1
                    print(f'[{cat_label.lower()}] Completed: {name}')
                else:
                    # Interrupted mid-pattern
                    skipped.append(name)
                    skipped.extend(n for _, _, n, _ in all_patterns[idx + 1:])
                    recorder.stop()
                    break
            except Exception as exc:
                failed.append(f'{name}: {exc}')
                print(f'[{cat_label.lower()}] FAILED: {name} — {exc}')
                completed += 1  # count as attempted

            # Stop per-pattern video recording
            recorder.stop()

            # Return to start position after each pattern
            teleport_to_field_start()

            # Inter-pattern pause (publish zero velocity)
            if not _interrupted and idx < total - 1:
                publisher.publish(_twist())
                # Sleep in small increments so SIGTERM can cancel the pause
                pause_remaining = pause
                while pause_remaining > 0 and not _interrupted:
                    step = min(0.1, pause_remaining)
                    time.sleep(step)
                    pause_remaining -= step

    # Ensure robot is stopped
    try:
        publisher.publish(_twist())
        for _ in range(10):
            publisher.publish(_twist())
            time.sleep(0.05)
    except Exception:
        pass  # ROS2 may already be shutting down

    elapsed = time.time() - start_time

    # Summary
    print('\n' + '=' * 60)
    print('[demo] SUMMARY')
    print(f'  Patterns executed : {completed}/{total}')
    print(f'  Elapsed time      : {elapsed:.1f}s')
    if failed:
        print(f'  Failed            : {len(failed)}')
        for f in failed:
            print(f'    - {f}')
    if skipped:
        print(f'  Skipped           : {len(skipped)}')
        for s in skipped:
            print(f'    - {s}')
    if not failed and not skipped:
        print('  All patterns completed successfully.')
    if record_video and recorder.recorded_files:
        print(f'  Videos recorded   : {len(recorder.recorded_files)}')
        for vf in recorder.recorded_files:
            print(f'    - {vf}')
    print('=' * 60)

    # Cleanup ROS2
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:
        pass  # may already be shut down


# ---------------------------------------------------------------------------
# 5. CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Gazebo demo pattern orchestrator for Pragati robot')
    parser.add_argument('--field', action='store_true',
                        help='Run field operation patterns')
    parser.add_argument('--geometric', action='store_true',
                        help='Run geometric validation patterns')
    parser.add_argument('--stress', action='store_true',
                        help='Run stress test patterns')
    parser.add_argument('--letters', action='store_true',
                        help='Run letter tracing patterns (P, D, 8, O, S, L, U, Z)')
    parser.add_argument('--all', action='store_true',
                        help='Run all pattern categories (default)')
    parser.add_argument('--record', action='store_true', default=False,
                         help='Enable per-pattern video recording '
                              '(overhead camera via CameraVideoRecorder plugin)')
    parser.add_argument('--no-record', action='store_true',
                        help='Disable video recording (default)')
    parser.add_argument('--video-dir', type=str, default=None,
                        help='Custom video output directory '
                             '(default: videos/ in project root)')
    parser.add_argument('--pause', type=float, default=2.0,
                        help='Inter-pattern pause in seconds (default: 2.0)')
    parser.add_argument('--speed-scale', type=float, default=1.0,
                        help='Speed scaling factor (default: 1.0)')
    parser.add_argument('--only', type=str, nargs='+', default=None,
                        metavar='NAME',
                        help='Run only specific patterns by name '
                             '(e.g. --only letter_P letter_D circle)')
    args = parser.parse_args()

    # Determine categories
    if args.field or args.geometric or args.stress or args.letters:
        categories = []
        if args.field:
            categories.append('field')
        if args.geometric:
            categories.append('geometric')
        if args.stress:
            categories.append('stress')
        if args.letters:
            categories.append('letters')
    else:
        # Default to all (including letters)
        categories = ['field', 'geometric', 'stress', 'letters']

    record = args.record and not args.no_record

    run_demo(
        categories=categories,
        record_video=record,
        video_dir=args.video_dir,
        pause=args.pause,
        speed_scale=args.speed_scale,
        only=args.only,
    )

    # Avoid WSL ROS2 shutdown hang
    os._exit(0)


if __name__ == '__main__':
    main()
