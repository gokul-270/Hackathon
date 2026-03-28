#!/usr/bin/env python3
"""
Pragati Robot Web UI — FastAPI Backend

Provides WebSocket-based pattern execution, freehand drawing path control,
and video recording for the Gazebo simulation.  Publishes cmd_vel via rclpy
with velocity ramping for smooth motion.

Usage:
    python3 backend.py
    # or
    uvicorn backend:app --host 0.0.0.0 --port 8888
"""

import asyncio
import logging
import math
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Path setup — import pattern library from scripts/demo_patterns.py
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[4]  # web_ui -> gazebo -> simulation -> vehicle_control -> src -> root
sys.path.insert(0, str(_PROJECT_ROOT / 'scripts'))

from demo_patterns import (  # noqa: E402
    VideoRecorder,
    _twist,
    circle,
    diamond,
    figure_eight,
    letter_D,
    letter_L,
    letter_P,
    letter_S,
    letter_U,
    letter_Z,
    row_traversal,
    s_pattern,
    square,
    teleport_robot,
    teleport_to_field_start,
    verify_recording,
)

# ROS2 imports (deferred to avoid issues when rclpy is not available)
try:
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Imu, NavSatFix, Image as RosImage, CompressedImage
    from std_msgs.msg import String as StringMsg
    from rclpy.qos import QoSProfile
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False

import numpy as np  # noqa: E402  — required by EKF engine

# Sensor fusion engine
from ekf_engine import EKFEngine, GPSLocalConverter  # noqa: E402
from path_corrector import PathCorrector  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger('backend')

# ---------------------------------------------------------------------------
# Pattern Registry
# ---------------------------------------------------------------------------

def _estimate_duration(commands) -> float:
    """Sum durations from a (Twist, float) command list."""
    return sum(dur for _, dur in commands)


def _compensate_kinematics_caps(commands):
    """Stretch segment durations to account for kinematics-node speed limits.

    The kinematics node applies TWO sequential speed reductions:

      1. **Effective-steering-angle check** — computes the max effective
         steering angle across all wheels (with backward-flip, so pure
         reverse is NOT penalised).  If it exceeds 0.4 rad, both vx and
         omega are scaled by ``max(0.4, 1 - (angle-0.4)*0.6)``.

      2. **Hard turn-rate cap** — after (1), it enforces
         ``|vx| <= 1 / (1 + 2·|omega|)``.

    Since pattern segments are time-based (fixed duration), we must
    stretch the duration by the inverse of each reduction so the vehicle
    actually travels the intended distance.

    An extra 20 % buffer covers the steering low-pass filter convergence
    delay (alpha=0.3) and the velocity-ramping engine's ramp phases.
    """
    # Wheel positions relative to kinematic center (from kinematics_node)
    _WHEELS = [(0.75, 0.0), (-0.75, 0.90), (-0.75, -0.90)]
    _STEER_THR = 0.4   # rad — threshold in kinematics node
    _K_TURN = 2.0       # proportionality constant for turn-rate cap
    _BUFFER = 1.20       # 20 % margin for filter lag / ramp

    result = []
    for twist, duration in commands:
        vx_raw = twist.linear.x
        omega_raw = twist.angular.z

        if abs(vx_raw) < 0.01:
            # Pure rotation or stop — speed reductions don't apply
            result.append((twist, duration))
            continue

        # --- Mechanism 1: effective-steering-angle reduction ---
        # Replicate _effective_steering_angle() with backward-flip
        max_eff = 0.0
        for wx, wy in _WHEELS:
            vix = vx_raw - omega_raw * wy
            viy = omega_raw * wx
            if abs(vix) < 1e-6 and abs(viy) < 1e-6:
                continue
            raw = math.atan2(viy, vix)
            # Backward-flip: angles > 90° are flipped to < 90°
            if abs(raw) > math.pi / 2:
                raw = raw - math.pi if raw > 0 else raw + math.pi
            max_eff = max(max_eff, abs(raw))

        if max_eff > _STEER_THR:
            sf1 = max(0.4, 1.0 - (max_eff - _STEER_THR) * 0.6)
        else:
            sf1 = 1.0

        vx = vx_raw * sf1
        omega = omega_raw * sf1

        # --- Mechanism 2: hard turn-rate speed cap ---
        max_speed = 1.0 / (1.0 + _K_TURN * abs(omega))
        if abs(vx) > max_speed:
            sf2 = max_speed / abs(vx)
        else:
            sf2 = 1.0

        # Combined actual-speed fraction
        total_fraction = sf1 * sf2
        if total_fraction < 0.999:
            scale = _BUFFER / total_fraction
        else:
            scale = 1.0

        result.append((twist, duration * scale))

    return result


def _build_registry() -> Dict[str, dict]:
    """Build the pattern registry with metadata.

    Letter pattern speed must stay below the kinematics node speed cap:
        max_speed = 1 / (1 + 2 * |omega|)
    With height=5, arc radius=1.25, omega=speed/radius=0.4,
    max_speed = 1/(1+0.8) ≈ 0.556.  speed=0.5 < 0.556 ✓
    """
    h = 5.0
    spd = 0.5
    r = h * 0.25

    entries = {
        # Letter patterns (available from demo_patterns.py)
        'letter_P': {'func': letter_P, 'category': 'letter', 'args': {'speed': spd, 'height': h}},
        'letter_D': {'func': letter_D, 'category': 'letter', 'args': {'speed': spd, 'height': h}},
        'letter_L': {'func': letter_L, 'category': 'letter', 'args': {'speed': spd, 'height': h}},
        'letter_U': {'func': letter_U, 'category': 'letter', 'args': {'speed': spd, 'height': h}},
        'letter_S': {'func': letter_S, 'category': 'letter', 'args': {'speed': spd, 'height': h}},
        'letter_Z': {'func': letter_Z, 'category': 'letter', 'args': {'speed': spd, 'height': h}},
        'letter_8': {'func': figure_eight, 'category': 'letter', 'args': {'speed': spd, 'radius': r}},
        'letter_O': {'func': circle, 'category': 'letter', 'args': {'speed': spd, 'radius': r, 'revolutions': 1}},
        # Geometric
        'circle':       {'func': circle, 'category': 'geometric', 'args': {'speed': 0.3, 'radius': 1.0}},
        'figure_eight': {'func': figure_eight, 'category': 'geometric', 'args': {'speed': 0.3, 'radius': 1.0}},
        'square':       {'func': square, 'category': 'geometric', 'args': {'speed': 0.3, 'side_length': 3.0}},
        'diamond':      {'func': diamond, 'category': 'geometric', 'args': {'speed': 0.3, 'side_length': 3.0}},
        # Field
        'row_traversal': {'func': row_traversal, 'category': 'field', 'args': {'speed': 0.5, 'length': 5.0}},
        's_pattern':     {'func': s_pattern, 'category': 'field', 'args': {'speed': 0.3, 'num_rows': 3, 'row_length': 4.0}},
    }

    # Pre-compute estimated durations (with kinematics compensation)
    for name, entry in entries.items():
        cmds = _compensate_kinematics_caps(entry['func'](**entry['args']))
        entry['estimated_duration'] = round(_estimate_duration(cmds), 1)

    return entries


PATTERN_REGISTRY = _build_registry()


# ---------------------------------------------------------------------------
# Ramer-Douglas-Peucker path simplification
# ---------------------------------------------------------------------------

def _perpendicular_distance(px, py, ax, ay, bx, by) -> float:
    """Perpendicular distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def rdp_simplify(points: List[dict], epsilon: float = 0.1) -> List[dict]:
    """Ramer-Douglas-Peucker path simplification."""
    if len(points) <= 2:
        return points

    # Find the point with the maximum distance
    max_dist = 0.0
    max_idx = 0
    ax, ay = points[0]['x'], points[0]['y']
    bx, by = points[-1]['x'], points[-1]['y']

    for i in range(1, len(points) - 1):
        d = _perpendicular_distance(points[i]['x'], points[i]['y'], ax, ay, bx, by)
        if d > max_dist:
            max_dist = d
            max_idx = i

    if max_dist > epsilon:
        left = rdp_simplify(points[:max_idx + 1], epsilon)
        right = rdp_simplify(points[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]


def points_to_commands(points: List[dict], drive_speed: float = 0.3,
                       turn_rate: float = 0.5) -> List[Tuple]:
    """Convert world-coordinate points to (Twist, duration) commands.

    Uses turn-then-drive approach: for each segment, rotate to face the
    next point, then drive straight to it.
    """
    if len(points) < 2:
        return []

    commands = []
    current_heading = 0.0  # assume starting facing +X

    for i in range(len(points) - 1):
        dx = points[i + 1]['x'] - points[i]['x']
        dy = points[i + 1]['y'] - points[i]['y']
        distance = math.hypot(dx, dy)
        if distance < 0.01:
            continue

        target_heading = math.atan2(dy, dx)
        heading_change = target_heading - current_heading

        # Normalize to [-pi, pi]
        while heading_change > math.pi:
            heading_change -= 2 * math.pi
        while heading_change < -math.pi:
            heading_change += 2 * math.pi

        # Turn in place if heading change is significant
        if abs(heading_change) > 0.05:
            turn_duration = abs(heading_change) / turn_rate
            turn_dir = math.copysign(turn_rate, heading_change)
            commands.append((_twist(angular_z=turn_dir), turn_duration))

        # Drive straight
        drive_duration = distance / drive_speed
        commands.append((_twist(linear_x=drive_speed), drive_duration))
        current_heading = target_heading

    return commands


# ---------------------------------------------------------------------------
# Velocity Ramping Engine
# ---------------------------------------------------------------------------

class VelocityRampingEngine:
    """Executes (Twist, duration) command sequences with velocity ramping.

    Publishes cmd_vel at 20 Hz with linear interpolation during transitions.
    """

    PUBLISH_HZ = 20
    PUBLISH_INTERVAL = 1.0 / PUBLISH_HZ

    def __init__(self, publisher, ramp_duration: float = 0.3):
        self._publisher = publisher
        self._ramp_duration = ramp_duration
        self._speed_scale = 1.0
        self._task: Optional[asyncio.Task] = None
        self._paused = asyncio.Event()
        self._paused.set()  # not paused initially
        self._stop_requested = False
        self._state = 'idle'  # idle, executing, paused, completed, stopped
        self._pattern_name = ''
        self._current_segment = 0
        self._total_segments = 0
        self._elapsed_time = 0.0
        self._start_time = 0.0

    @property
    def speed_scale(self) -> float:
        return self._speed_scale

    @speed_scale.setter
    def speed_scale(self, value: float):
        self._speed_scale = max(0.25, min(2.0, value))

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state in ('executing', 'paused')

    def get_status(self) -> dict:
        progress = 0.0
        if self._total_segments > 0:
            progress = (self._current_segment / self._total_segments) * 100
        return {
            'type': 'pattern_status',
            'pattern_name': self._pattern_name,
            'progress_percent': round(progress, 1),
            'current_segment': self._current_segment,
            'total_segments': self._total_segments,
            'elapsed_time': round(self._elapsed_time, 1),
            'state': self._state,
        }

    def _publish(self, linear_x: float, angular_z: float):
        """Publish a scaled Twist message."""
        if not HAS_RCLPY or self._publisher is None:
            return
        msg = Twist()
        msg.linear.x = linear_x * self._speed_scale
        msg.angular.z = angular_z * self._speed_scale
        try:
            self._publisher.publish(msg)
        except Exception as e:
            logger.warning(f'Failed to publish cmd_vel: {e}')

    def _publish_zero(self):
        """Publish zero velocity."""
        self._publish(0.0, 0.0)

    def _interpolate(self, v0: float, v1: float, t: float, ramp: float) -> float:
        """Linear interpolation between v0 and v1 over ramp duration."""
        if ramp <= 0:
            return v1
        ratio = min(t / ramp, 1.0)
        return v0 + (v1 - v0) * ratio

    async def execute(self, commands: List[Tuple], name: str = '',
                      broadcast_fn=None, odom_getter=None,
                      fused_odom_getter=None,
                      path_corrector=None) -> str:
        """Execute a command sequence with velocity ramping.

        If *odom_getter* is provided (a callable returning (x, y, theta)),
        each segment uses **closed-loop odometry feedback**: the segment
        runs until the robot has actually traveled the intended distance /
        angle, with a generous safety timeout.  Otherwise falls back to the
        legacy open-loop timer.

        *fused_odom_getter* (optional): returns the EKF-fused position for
        CTE path correction.  If not provided, falls back to odom_getter.

        Returns final state: 'completed' or 'stopped'.
        """
        self._stop_requested = False
        self._paused.set()
        self._pattern_name = name
        self._total_segments = len(commands)
        self._current_segment = 0
        self._elapsed_time = 0.0
        self._start_time = time.monotonic()
        self._state = 'executing'

        prev_lx, prev_az = 0.0, 0.0
        last_status_time = 0.0
        last_trail_time = 0.0

        # ── Build planned (intended) path from commands ──
        planned_path = []
        actual_trail = []
        if odom_getter:
            px, py, ptheta = odom_getter()
            planned_path.append({'x': round(px, 4), 'y': round(py, 4)})
            for _twist, _dur in commands:
                _lx = _twist.linear.x
                _az = _twist.angular.z
                if abs(_lx) < 0.01 and abs(_az) > 0.01:
                    # Pure rotation — same position, new heading
                    ptheta += _az * _dur
                else:
                    # Straight or arc — step forward
                    steps = max(int(_dur / 0.1), 1)
                    sdt = _dur / steps
                    for _ in range(steps):
                        ptheta += _az * sdt
                        px += _lx * math.cos(ptheta) * sdt
                        py += _lx * math.sin(ptheta) * sdt
                    planned_path.append({'x': round(px, 4), 'y': round(py, 4)})

        # Tolerances for closed-loop completion
        DIST_TOL = 0.08        # metres
        ANGLE_TOL = 0.05       # radians  (~3°)
        TIMEOUT_FACTOR = 4.0   # safety: max 4× nominal duration

        try:
            for seg_idx, (twist, duration) in enumerate(commands):
                if self._stop_requested:
                    break

                self._current_segment = seg_idx
                target_lx = twist.linear.x
                target_az = twist.angular.z

                # ---- Determine expected travel for this segment ----
                use_odom = odom_getter is not None
                if use_odom:
                    ox, oy, otheta = odom_getter()
                    start_x, start_y, start_theta = ox, oy, otheta

                    if abs(target_lx) < 0.01 and abs(target_az) < 0.01:
                        seg_mode = 'stop'
                    elif abs(target_lx) < 0.01:
                        seg_mode = 'rotate'
                        seg_target_angle = abs(target_az * duration)
                    elif abs(target_az) < 0.01:
                        seg_mode = 'straight'
                        seg_target_dist = abs(target_lx * duration)
                    else:
                        seg_mode = 'arc'
                        seg_target_dist = abs(target_lx * duration)
                        seg_target_angle = abs(target_az * duration)

                    # Set up path corrector for straight segments.
                    # Use raw odom position for segment reference — must be in
                    # the same coordinate frame as the completion check which
                    # also uses raw odom.  Heading from fused (if available)
                    # provides a cleaner reference than raw odom heading.
                    if path_corrector and seg_mode == 'straight':
                        sx, sy, _ = odom_getter()
                        # Use fused heading if available (better IMU-aided estimate)
                        if fused_odom_getter:
                            _, _, stheta = fused_odom_getter()
                        else:
                            _, _, stheta = odom_getter()
                        end_x = sx + math.cos(stheta) * seg_target_dist
                        end_y = sy + math.sin(stheta) * seg_target_dist
                        path_corrector.set_segment(sx, sy, end_x, end_y)

                    # Stop segments use nominal duration; motion uses 4x safety
                    timeout = duration if seg_mode == 'stop' else max(duration * TIMEOUT_FACTOR, 2.0)
                else:
                    timeout = duration

                seg_elapsed = 0.0
                ramp = min(self._ramp_duration, duration / 2)

                while seg_elapsed < timeout:
                    if self._stop_requested:
                        break

                    # Handle pause
                    if not self._paused.is_set():
                        self._publish_zero()
                        self._state = 'paused'
                        if broadcast_fn:
                            await broadcast_fn(self.get_status())
                        await self._paused.wait()
                        if self._stop_requested:
                            break
                        self._state = 'executing'
                        prev_lx, prev_az = 0.0, 0.0
                        # Re-read odom after resume so deltas restart
                        if use_odom:
                            ox, oy, otheta = odom_getter()
                            start_x, start_y, start_theta = ox, oy, otheta

                    # Velocity ramping (only in the first `duration` seconds)
                    if seg_elapsed < ramp:
                        lx = self._interpolate(prev_lx, target_lx, seg_elapsed, ramp)
                        az = self._interpolate(prev_az, target_az, seg_elapsed, ramp)
                    elif not use_odom and seg_elapsed > duration - ramp and seg_idx == len(commands) - 1:
                        remaining = duration - seg_elapsed
                        lx = self._interpolate(target_lx, 0.0, ramp - remaining, ramp)
                        az = self._interpolate(target_az, 0.0, ramp - remaining, ramp)
                    else:
                        lx, az = target_lx, target_az

                    # Apply path corrector CTE correction on straight segments
                    # Use raw odom position (consistent with segment reference)
                    # but fused heading (better IMU-aided estimate).
                    if path_corrector and use_odom and seg_mode == 'straight':
                        fx, fy, _ = odom_getter()
                        if fused_odom_getter:
                            _, _, ftheta = fused_odom_getter()
                        else:
                            _, _, ftheta = odom_getter()
                        cte_correction = path_corrector.compute_correction(fx, fy, ftheta)
                        az = az + cte_correction

                    self._publish(lx, az)

                    await asyncio.sleep(self.PUBLISH_INTERVAL)
                    seg_elapsed += self.PUBLISH_INTERVAL
                    self._elapsed_time = time.monotonic() - self._start_time

                    # Status broadcast at 1 Hz
                    if broadcast_fn and self._elapsed_time - last_status_time >= 1.0:
                        last_status_time = self._elapsed_time
                        await broadcast_fn(self.get_status())

                    # Sample actual trail at ~5 Hz
                    if use_odom and self._elapsed_time - last_trail_time >= 0.2:
                        last_trail_time = self._elapsed_time
                        _tx, _ty, _ = odom_getter()
                        actual_trail.append({'x': round(_tx, 4), 'y': round(_ty, 4)})

                    # ---- Closed-loop completion check ----
                    if use_odom and seg_mode != 'stop':
                        ox, oy, otheta = odom_getter()
                        dx = ox - start_x
                        dy = oy - start_y
                        dist = math.hypot(dx, dy)
                        dtheta = otheta - start_theta
                        # Normalise to [-π, π]
                        dtheta = math.atan2(math.sin(dtheta), math.cos(dtheta))
                        angle = abs(dtheta)

                        if seg_mode == 'straight' and dist >= seg_target_dist - DIST_TOL:
                            break
                        elif seg_mode == 'rotate' and angle >= seg_target_angle - ANGLE_TOL:
                            break
                        elif seg_mode == 'arc':
                            dp = dist / max(seg_target_dist, 0.01)
                            ap = angle / max(seg_target_angle, 0.01)
                            if max(dp, ap) >= 0.95:
                                break

                    # Legacy open-loop: stop at nominal duration
                    if not use_odom and seg_elapsed >= duration:
                        break
                    # Stop-segments (zero vel pause) also use nominal duration
                    if use_odom and seg_mode == 'stop' and seg_elapsed >= duration:
                        break

                prev_lx, prev_az = target_lx, target_az

            # Final zero velocity
            self._publish_zero()

            if self._stop_requested:
                self._state = 'stopped'
            else:
                self._current_segment = self._total_segments
                self._elapsed_time = time.monotonic() - self._start_time
                self._state = 'completed'

            if broadcast_fn:
                await broadcast_fn(self.get_status())
                # Broadcast planned vs actual trail for visualization
                if planned_path or actual_trail:
                    # Add final position to actual trail
                    if odom_getter:
                        _fx, _fy, _ = odom_getter()
                        actual_trail.append({'x': round(_fx, 4), 'y': round(_fy, 4)})
                    await broadcast_fn({
                        'type': 'pattern_trail',
                        'planned': planned_path,
                        'actual': actual_trail,
                        'name': name,
                        'state': self._state,
                    })

        except asyncio.CancelledError:
            self._publish_zero()
            self._state = 'stopped'
            if broadcast_fn:
                await broadcast_fn(self.get_status())

        return self._state

    def stop(self):
        """Request stop of current execution."""
        self._stop_requested = True
        self._paused.set()  # unblock if paused
        if self._task and not self._task.done():
            self._task.cancel()
        self._publish_zero()
        self._state = 'stopped'

    def pause(self):
        """Pause execution."""
        if self._state == 'executing':
            self._paused.clear()

    def resume(self):
        """Resume from pause."""
        if self._state == 'paused' or not self._paused.is_set():
            self._paused.set()


# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------

class AppState:
    """Global application state shared between WebSocket handlers."""

    def __init__(self):
        self.node = None
        self.publisher = None
        self.engine: Optional[VelocityRampingEngine] = None
        self.recorder: Optional[VideoRecorder] = None
        self.clients: Set[WebSocket] = set()
        self.execution_task: Optional[asyncio.Task] = None
        self.spin_task: Optional[asyncio.Task] = None
        self.recording_timer_task: Optional[asyncio.Task] = None
        self.auto_record = False
        self.recording_start_time: Optional[float] = None
        self.recording_filename: Optional[str] = None
        # Fused pose (primary — used by odom_getter, patterns, precision moves)
        self.odom_x = 0.0
        self.odom_y = 0.0
        self.odom_theta = 0.0
        self.odom_subscription = None
        self.precision_move_task: Optional[asyncio.Task] = None
        self.precision_move_cancel = False

        # ── Sensor Fusion ───────────────────────────────────────────
        self.ekf = EKFEngine()
        self.gps_converter = GPSLocalConverter()
        self.path_corrector = PathCorrector()

        # Raw sensor caches (for diagnostics / drift comparison)
        self.raw_odom_x: float = 0.0
        self.raw_odom_y: float = 0.0
        self.raw_odom_theta: float = 0.0

        self.imu_yaw: float = 0.0
        self.imu_gyro_z: float = 0.0

        self.gps_local_x: float = 0.0
        self.gps_local_y: float = 0.0
        self.rtk_fix_state: str = 'SEARCHING'

        # Subscriptions for IMU / GPS / RTK status
        self.imu_subscription = None
        self.gps_subscription = None
        self.rtk_status_subscription = None

        # EKF timing
        self.last_predict_time: float = 0.0

        # Sensor fusion enable flag (dashboard toggle)
        self.fusion_enabled: bool = True

        # EKF broadcast timing
        self._last_ekf_broadcast: float = 0.0

        # ── Camera ──────────────────────────────────────────────────
        self.camera_subscription = None
        self._camera_jpeg: bytes = b''           # latest JPEG frame
        self._camera_event = asyncio.Event()      # notify new frame
        self._camera_stamp: float = 0.0

        # ── Cotton Detection ────────────────────────────────────────
        self.detection_subscription = None
        self.detection_result_subscription = None
        self._detection_jpeg: bytes = b''         # latest detection debug JPEG
        self._detection_event = asyncio.Event()    # notify new detection frame
        self._detection_stamp: float = 0.0
        self._detection_data: dict = {}            # latest detection stats
        self._last_detection_broadcast: float = 0.0

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected WebSocket clients."""
        dead = set()
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.clients -= dead


state = AppState()


def _quaternion_to_yaw(x, y, z, w):
    """Extract yaw from quaternion."""
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(title='Pragati Web UI Backend')


@app.on_event('startup')
async def startup():
    """Initialize ROS2 node and engine on server start."""
    if HAS_RCLPY:
        try:
            rclpy.init()
            state.node = rclpy.create_node('web_ui_backend')
            state.publisher = state.node.create_publisher(Twist, '/cmd_vel', 10)
            logger.info('ROS2 node initialized, /cmd_vel publisher created')

            # Kinematic-center offset from base-v1 (right rear wheel)
            # in the body frame: 0.65 m forward, 0.90 m in kinematic-Y.
            # Kinematic-Y maps to world -Y (URDF spawned with 90° roll),
            # so effective body-frame offset is (0.65, -0.90).
            _KC_FWD = 0.65   # metres forward from base-v1
            _KC_LAT = 0.90   # metres in kinematic-Y (world -Y at θ=0)
            # GPS antenna URDF Z from base-v1 (same convention as _KC_LAT)
            _GPS_LAT = 1.20  # navsat_joint xyz=(0.65, 0.0, 1.2)
            # Offset from GPS antenna to kinematic center (in code convention)
            _GPS_TO_KC_DLAT = _KC_LAT - _GPS_LAT   # −0.30

            def odom_callback(msg):
                raw_x = msg.pose.pose.position.x
                raw_y = msg.pose.pose.position.y
                q = msg.pose.pose.orientation
                theta = _quaternion_to_yaw(q.x, q.y, q.z, q.w)
                # Transform from base-v1 to kinematic center
                cos_t = math.cos(theta)
                sin_t = math.sin(theta)
                center_x = raw_x + _KC_FWD * cos_t + _KC_LAT * sin_t
                center_y = raw_y + _KC_FWD * sin_t - _KC_LAT * cos_t

                # Store raw odom (for drift comparison)
                state.raw_odom_x = center_x
                state.raw_odom_y = center_y
                state.raw_odom_theta = theta

                if state.fusion_enabled:
                    # Seed EKF from first odom reading (avoids huge innovation)
                    state.ekf.initialize_from_odom(center_x, center_y, theta)

                    # EKF predict with odom velocity + IMU gyro
                    now = time.monotonic()
                    dt = now - state.last_predict_time if state.last_predict_time > 0 else 0.02
                    state.last_predict_time = now

                    v_odom = msg.twist.twist.linear.x
                    omega_odom = msg.twist.twist.angular.z

                    # Convert base-v1 velocity → kinematic-center forward velocity.
                    #
                    # Rigid body: v_KC = v_base + ω × r_{base→KC}
                    # In 2D: v_kc_x = v_base_x - ω × KC_LAT  (SUBTRACT)
                    #         v_kc_y = 0  (Ackermann: KC moves in heading dir)
                    #
                    # Verification — in-place turn (v_KC=0, ω=0.5 rad/s):
                    #   odom linear.x = base-v1 orbiting KC ≈ ω × KC_LAT = 0.45 m/s
                    #   v_kc_x = 0.45 − 0.5×0.90 = 0  ✓
                    alpha = state.ekf._cfg['alpha_imu']
                    omega_blend = alpha * state.imu_gyro_z + (1.0 - alpha) * omega_odom
                    v_kc_x = v_odom - _KC_LAT * omega_blend   # correct sign: SUBTRACT

                    state.ekf.predict(v_kc_x, omega_odom, state.imu_gyro_z, dt)
                    state.ekf.update_odom(center_x, center_y, theta)

                    fx, fy, ftheta = state.ekf.state
                    state.odom_x = fx
                    state.odom_y = fy
                    state.odom_theta = ftheta
                else:
                    # Fusion disabled — pass through raw odom
                    state.odom_x = center_x
                    state.odom_y = center_y
                    state.odom_theta = theta

            state.odom_subscription = state.node.create_subscription(
                Odometry, '/odom', odom_callback, 10
            )
            logger.info('/odom subscription created')

            # ── IMU subscription (gyro for EKF predict) ─────────────
            GYRO_DEADZONE = 0.005  # rad/s

            def imu_callback(msg):
                gz = msg.angular_velocity.z
                state.imu_gyro_z = gz if abs(gz) > GYRO_DEADZONE else 0.0
                state.imu_yaw = _quaternion_to_yaw(
                    msg.orientation.x, msg.orientation.y,
                    msg.orientation.z, msg.orientation.w
                )
                # Heading divergence check
                if state.fusion_enabled:
                    state.ekf.check_heading_divergence(state.imu_yaw)

            state.imu_subscription = state.node.create_subscription(
                Imu, '/imu', imu_callback, 10
            )
            logger.info('/imu subscription created (EKF gyro input)')

            # ── RTK GPS subscription (position update) ──────────────
            def gps_callback(msg):
                local_x, local_y = state.gps_converter.gps_to_local(
                    msg.latitude, msg.longitude, msg.altitude
                )
                state.gps_local_x = local_x
                state.gps_local_y = local_y

                if state.fusion_enabled and state.rtk_fix_state in ('FLOAT', 'RTK_FIXED'):
                    cov_x = msg.position_covariance[0]
                    cov_y = msg.position_covariance[4]
                    # GPS antenna is offset from kinematic center.
                    # Transform antenna world pos → KC world pos using
                    # the body-frame lateral delta and current heading.
                    theta = state.raw_odom_theta
                    cos_t = math.cos(theta)
                    sin_t = math.sin(theta)
                    kc_gps_x = local_x + _GPS_TO_KC_DLAT * sin_t
                    kc_gps_y = local_y - _GPS_TO_KC_DLAT * cos_t
                    state.ekf.update_gps(kc_gps_x, kc_gps_y, cov_x, cov_y)

                    fx, fy, ftheta = state.ekf.state
                    state.odom_x = fx
                    state.odom_y = fy
                    state.odom_theta = ftheta

            state.gps_subscription = state.node.create_subscription(
                NavSatFix, '/gps/fix', gps_callback, 10
            )
            logger.info('/gps/fix subscription created (EKF GPS update)')

            # ── RTK status subscription (fix state tracking) ────────
            def rtk_status_callback(msg):
                import json as _json
                try:
                    data = _json.loads(msg.data)
                    state.rtk_fix_state = data.get('fix_state', 'SEARCHING')
                except Exception:
                    pass

            state.rtk_status_subscription = state.node.create_subscription(
                StringMsg, '/rtk/status', rtk_status_callback, 10
            )
            logger.info('/rtk/status subscription created')

            # ── Front Camera subscription (JPEG streaming) ──────────
            def camera_callback(msg):
                """Convert ROS Image (RGB8) to JPEG and store for streaming."""
                try:
                    import io
                    from PIL import Image as PILImage
                    w, h = msg.width, msg.height
                    enc = msg.encoding.lower()
                    if enc in ('rgb8', '8uc3'):
                        img = PILImage.frombytes('RGB', (w, h), bytes(msg.data))
                    elif enc in ('bgr8',):
                        img = PILImage.frombytes('RGB', (w, h), bytes(msg.data))
                        r, g, b = img.split()
                        img = PILImage.merge('RGB', (b, g, r))
                    else:
                        return
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=70)
                    state._camera_jpeg = buf.getvalue()
                    state._camera_stamp = time.monotonic()
                    state._camera_event.set()
                except Exception:
                    pass

            try:
                from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
                cam_qos = QoSProfile(
                    reliability=ReliabilityPolicy.BEST_EFFORT,
                    durability=DurabilityPolicy.VOLATILE,
                    depth=1,
                )
                state.camera_subscription = state.node.create_subscription(
                    RosImage, '/front_camera', camera_callback, cam_qos
                )
                logger.info('/front_camera subscription created (MJPEG streaming)')
            except Exception as e:
                logger.warning(f'Camera subscription failed: {e}')

            # ── Cotton Detection debug image subscription ───────────
            def detection_image_callback(msg):
                """Store CompressedImage JPEG bytes for detection stream."""
                try:
                    state._detection_jpeg = bytes(msg.data)
                    state._detection_stamp = time.monotonic()
                    state._detection_event.set()
                except Exception:
                    pass

            def detection_result_callback(msg):
                """Parse detection result string (JSON) and store stats."""
                import json as _json
                try:
                    data = _json.loads(msg.data)
                    state._detection_data = {
                        'total_count': data.get('total_count', 0),
                        'cotton_count': data.get('cotton_count', 0),
                        'not_pickable_count': data.get('not_pickable_count', 0),
                        'detection_successful': data.get('detection_successful', False),
                        'processing_time_ms': data.get('processing_time_ms', 0),
                        'positions': data.get('positions', []),
                    }
                except Exception:
                    pass

            try:
                det_qos = QoSProfile(
                    reliability=ReliabilityPolicy.BEST_EFFORT,
                    durability=DurabilityPolicy.VOLATILE,
                    depth=1,
                )
                state.detection_subscription = state.node.create_subscription(
                    CompressedImage,
                    '/front_camera/cotton_detection/debug_image',
                    detection_image_callback,
                    det_qos,
                )
                logger.info('/front_camera/cotton_detection/debug_image subscription created')

                state.detection_result_subscription = state.node.create_subscription(
                    StringMsg,
                    '/cotton_detection/result_json',
                    detection_result_callback,
                    10,
                )
                logger.info('/cotton_detection/result_json subscription created')
            except Exception as e:
                logger.warning(f'Cotton detection subscriptions failed: {e}')

            # Periodic rclpy spin + EKF status broadcast
            async def spin_loop():
                while True:
                    try:
                        rclpy.spin_once(state.node, timeout_sec=0)
                    except Exception:
                        pass

                    # Broadcast EKF status at ~2 Hz
                    now = time.monotonic()
                    if now - state._last_ekf_broadcast >= 0.5:
                        state._last_ekf_broadcast = now
                        try:
                            ekf_diag = state.ekf.get_diagnostics()
                            # Determine fusion mode string
                            if not state.fusion_enabled:
                                ekf_mode = 'DISABLED'
                            elif state.rtk_fix_state in ('RTK_FIXED', 'FLOAT'):
                                ekf_mode = 'ODOM+IMU+GPS'
                            elif state.imu_subscription is not None:
                                ekf_mode = 'ODOM+IMU'
                            else:
                                ekf_mode = 'ODOM_ONLY'
                            ekf_msg = {
                                'type': 'ekf_status',
                                'fusion_enabled': state.fusion_enabled,
                                'mode': ekf_mode,
                                'rtk_fix_state': state.rtk_fix_state,
                                'fused_x': round(state.odom_x, 4),
                                'fused_y': round(state.odom_y, 4),
                                'fused_theta': round(state.odom_theta, 4),
                                'raw_odom_x': round(state.raw_odom_x, 4),
                                'raw_odom_y': round(state.raw_odom_y, 4),
                                'raw_odom_theta': round(state.raw_odom_theta, 4),
                                'gps_local_x': round(state.gps_local_x, 4),
                                'gps_local_y': round(state.gps_local_y, 4),
                                'drift_x': round(state.odom_x - state.raw_odom_x, 4),
                                'drift_y': round(state.odom_y - state.raw_odom_y, 4),
                                'drift_theta': round(state.odom_theta - state.raw_odom_theta, 4),
                                # counters
                                'predictions': ekf_diag['predict_count'],
                                'odom_updates': ekf_diag['odom_update_count'],
                                'gps_updates': ekf_diag['gps_update_count'],
                                # uncertainty
                                'cov_diag': ekf_diag['covariance_diag'],
                                'heading_diverged': ekf_diag['heading_diverged'],
                            }
                            await state.broadcast(ekf_msg)
                        except Exception:
                            pass

                    # Broadcast cotton detection stats at ~2 Hz
                    if state._detection_data and now - state._last_detection_broadcast >= 0.5:
                        state._last_detection_broadcast = now
                        try:
                            det_msg = dict(state._detection_data)
                            det_msg['type'] = 'detection_stats'
                            det_msg['stream_active'] = bool(state._detection_jpeg)
                            await state.broadcast(det_msg)
                        except Exception:
                            pass

                    await asyncio.sleep(0.05)

            state.spin_task = asyncio.create_task(spin_loop())
        except Exception as e:
            logger.error(f'Failed to initialize ROS2: {e}')
    else:
        logger.warning('rclpy not available — running without ROS2')

    state.engine = VelocityRampingEngine(state.publisher)

    # Initialize video recorder
    video_dir = str(_PROJECT_ROOT / 'videos')
    try:
        state.recorder = VideoRecorder(video_dir=video_dir, enabled=True)
        logger.info(f'VideoRecorder initialized, output dir: {video_dir}')
    except Exception as e:
        logger.warning(f'VideoRecorder init failed: {e}')

    logger.info('Backend started on port 8888')


@app.on_event('shutdown')
async def shutdown():
    """Clean up ROS2 resources."""
    if state.spin_task:
        state.spin_task.cancel()
        try:
            await state.spin_task
        except asyncio.CancelledError:
            pass

    if state.execution_task and not state.execution_task.done():
        state.execution_task.cancel()

    if state.engine:
        state.engine.stop()

    if HAS_RCLPY and state.node:
        try:
            state.node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass
    logger.info('Backend shut down')


@app.get('/health')
async def health():
    return JSONResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# MJPEG Camera Stream Endpoint
# ---------------------------------------------------------------------------

@app.get('/camera/stream')
async def camera_stream():
    """MJPEG stream of the front camera.

    Browsers render this natively inside an <img src="/camera/stream"> tag.
    """
    async def generate():
        BOUNDARY = b'--frame\r\n'
        prev_stamp = 0.0
        while True:
            # Wait for a new frame (with timeout so connection stays alive)
            state._camera_event.clear()
            try:
                await asyncio.wait_for(state._camera_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            frame = state._camera_jpeg
            stamp = state._camera_stamp
            if not frame or stamp == prev_stamp:
                continue
            prev_stamp = stamp

            yield (
                BOUNDARY
                + b'Content-Type: image/jpeg\r\n'
                + b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                + frame
                + b'\r\n'
            )

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/camera/snapshot')
async def camera_snapshot():
    """Single JPEG snapshot from the front camera."""
    if not state._camera_jpeg:
        return JSONResponse({'error': 'No camera frame available'}, status_code=503)
    return StreamingResponse(
        iter([state._camera_jpeg]),
        media_type='image/jpeg',
    )


# ---------------------------------------------------------------------------
# MJPEG Cotton Detection Stream Endpoint
# ---------------------------------------------------------------------------

@app.get('/camera/detection_stream')
async def detection_stream():
    """MJPEG stream of the cotton detection debug image (with bounding boxes).

    Browsers render this natively inside an <img src="/camera/detection_stream"> tag.
    """
    async def generate():
        BOUNDARY = b'--frame\r\n'
        prev_stamp = 0.0
        while True:
            state._detection_event.clear()
            try:
                await asyncio.wait_for(state._detection_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            frame = state._detection_jpeg
            stamp = state._detection_stamp
            if not frame or stamp == prev_stamp:
                continue
            prev_stamp = stamp

            yield (
                BOUNDARY
                + b'Content-Type: image/jpeg\r\n'
                + b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                + frame
                + b'\r\n'
            )

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/camera/detection_snapshot')
async def detection_snapshot():
    """Single JPEG snapshot from the cotton detection debug image."""
    if not state._detection_jpeg:
        return JSONResponse({'error': 'No detection frame available'}, status_code=503)
    return StreamingResponse(
        iter([state._detection_jpeg]),
        media_type='image/jpeg',
    )


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------

@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.clients.add(websocket)
    logger.info(f'WebSocket client connected ({len(state.clients)} total)')

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get('type', '')

            if msg_type == 'ping':
                await websocket.send_json({'type': 'pong'})

            elif msg_type == 'get_patterns':
                await _handle_get_patterns(websocket)

            elif msg_type == 'start_pattern':
                await _handle_start_pattern(data, websocket)

            elif msg_type == 'stop_pattern':
                await _handle_stop(websocket)

            elif msg_type == 'pause_pattern':
                await _handle_pause(websocket)

            elif msg_type == 'resume_pattern':
                await _handle_resume(websocket)

            elif msg_type == 'set_speed_scale':
                await _handle_set_speed_scale(data, websocket)

            elif msg_type == 'draw_path':
                await _handle_draw_path(data, websocket)

            elif msg_type == 'start_recording':
                await _handle_start_recording(data, websocket)

            elif msg_type == 'stop_recording':
                await _handle_stop_recording(websocket)

            elif msg_type == 'set_auto_record':
                state.auto_record = bool(data.get('enabled', False))
                await websocket.send_json({
                    'type': 'auto_record_status',
                    'enabled': state.auto_record,
                })

            elif msg_type == 'teleport':
                await _handle_teleport(data, websocket)

            elif msg_type == 'precision_move':
                await _handle_precision_move(data, websocket)

            elif msg_type == 'cancel_move':
                await _handle_cancel_move(websocket)

            elif msg_type == 'get_sim_config':
                await _handle_get_sim_config(websocket)

            elif msg_type == 'update_sim_config':
                await _handle_update_sim_config(data, websocket)

            # ── Sensor Fusion commands ──────────────────────────────
            elif msg_type == 'toggle_fusion':
                state.fusion_enabled = bool(data.get('enabled', True))
                if not state.fusion_enabled:
                    # When disabling, snap to raw odom
                    state.odom_x = state.raw_odom_x
                    state.odom_y = state.raw_odom_y
                    state.odom_theta = state.raw_odom_theta
                await websocket.send_json({'type': 'fusion_toggled', 'enabled': state.fusion_enabled})
                logger.info(f'Sensor fusion {"enabled" if state.fusion_enabled else "disabled"}')

            elif msg_type == 'update_ekf_config':
                config = data.get('config', {})
                state.ekf.update_config(config)
                # Also update path corrector gains if present
                if 'cte_kp' in config or 'cte_kd' in config or 'cte_kh' in config or 'cte_max' in config:
                    state.path_corrector.update_gains(
                        kp=config.get('cte_kp'),
                        kd=config.get('cte_kd'),
                        kh=config.get('cte_kh'),
                        max_correction=config.get('cte_max'),
                    )
                await websocket.send_json({'type': 'ekf_config_updated', 'config': state.ekf.get_config()})
                logger.info(f'EKF config updated: {config}')

            elif msg_type == 'reset_ekf':
                state.ekf.reset(state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)
                state.odom_x = state.raw_odom_x
                state.odom_y = state.raw_odom_y
                state.odom_theta = state.raw_odom_theta
                await websocket.send_json({'type': 'ekf_reset'})
                logger.info('EKF manually reset')

            else:
                await websocket.send_json({
                    'type': 'error',
                    'message': f'Unknown message type: {msg_type}',
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f'WebSocket error: {e}')
    finally:
        state.clients.discard(websocket)
        logger.info(f'WebSocket client disconnected ({len(state.clients)} total)')


# ---------------------------------------------------------------------------
# Message Handlers
# ---------------------------------------------------------------------------

async def _handle_get_patterns(ws: WebSocket):
    """Send the pattern list to the client."""
    patterns = []
    for name, entry in PATTERN_REGISTRY.items():
        patterns.append({
            'name': name,
            'category': entry['category'],
            'estimated_duration': entry['estimated_duration'],
        })
    await ws.send_json({'type': 'pattern_list', 'patterns': patterns})


async def _handle_start_pattern(data: dict, ws: WebSocket):
    """Start executing a pattern."""
    name = data.get('name', '')
    if name not in PATTERN_REGISTRY:
        await ws.send_json({'type': 'error', 'message': f'Unknown pattern: {name}'})
        return

    # Stop any current execution first (exclusive execution)
    if state.engine and state.engine.is_running:
        await _stop_execution()

    # Notify browser: backend owns cmd_vel
    await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'backend'})

    # Teleport to field start (run in thread to avoid blocking)
    try:
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, teleport_to_field_start)
        if not ok:
            await ws.send_json({'type': 'error', 'message': 'Teleport failed'})
            await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})
            return
        # Brief settle time after teleport
        await asyncio.sleep(1.0)
        # Reset EKF after teleport to avoid huge innovation spike
        if state.fusion_enabled:
            state.ekf.reset(state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)
            state.odom_x = state.raw_odom_x
            state.odom_y = state.raw_odom_y
            state.odom_theta = state.raw_odom_theta
            logger.info('EKF reset after teleport')
    except Exception as e:
        await ws.send_json({'type': 'error', 'message': f'Teleport error: {e}'})
        await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})
        return

    # Auto-record
    if state.auto_record and state.recorder:
        await _do_start_recording(name)

    # Get commands and execute with closed-loop odom feedback.
    # No duration compensation needed — odom feedback handles speed caps.
    entry = PATTERN_REGISTRY[name]
    commands = entry['func'](**entry['args'])

    # Use RAW odom for distance/angle checking (ground truth of wheel movement).
    # Use FUSED odom only for CTE correction (smoother path tracking).
    def _odom_getter():
        return (state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)

    def _fused_odom_getter():
        return (state.odom_x, state.odom_y, state.odom_theta)

    async def run():
        try:
            # Reset path corrector for fresh pattern
            state.path_corrector.reset()
            final_state = await state.engine.execute(
                commands, name=name, broadcast_fn=state.broadcast,
                odom_getter=_odom_getter,
                fused_odom_getter=_fused_odom_getter if state.fusion_enabled else None,
                path_corrector=state.path_corrector if state.fusion_enabled else None,
            )
        except Exception as e:
            logger.error(f'Pattern execution error: {e}')
        finally:
            # Auto-record stop
            if state.auto_record and state.recorder and state.recorder._recording:
                await _do_stop_recording()
            # Release cmd_vel ownership
            await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})

    state.execution_task = asyncio.create_task(run())


async def _handle_stop(ws: WebSocket):
    """Stop current execution."""
    await _stop_execution()
    await ws.send_json({'type': 'ack', 'action': 'stop_pattern'})


async def _stop_execution():
    """Internal: stop any running execution."""
    if state.engine:
        state.engine.stop()
    if state.execution_task and not state.execution_task.done():
        state.execution_task.cancel()
        try:
            await state.execution_task
        except asyncio.CancelledError:
            pass
    # Auto-record stop
    if state.auto_record and state.recorder and state.recorder._recording:
        await _do_stop_recording()
    await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})


async def _handle_pause(ws: WebSocket):
    """Pause current execution."""
    if state.engine and state.engine.is_running:
        state.engine.pause()
        await ws.send_json({'type': 'ack', 'action': 'pause_pattern'})
    else:
        await ws.send_json({'type': 'ack', 'action': 'pause_pattern', 'note': 'nothing running'})


async def _handle_resume(ws: WebSocket):
    """Resume paused execution."""
    if state.engine:
        state.engine.resume()
        await ws.send_json({'type': 'ack', 'action': 'resume_pattern'})


async def _handle_set_speed_scale(data: dict, ws: WebSocket):
    """Set the speed scale factor."""
    value = float(data.get('value', 1.0))
    if state.engine:
        state.engine.speed_scale = value
        clamped = state.engine.speed_scale
    else:
        clamped = max(0.25, min(2.0, value))
    await ws.send_json({
        'type': 'speed_scale_set',
        'value': clamped,
    })


async def _handle_draw_path(data: dict, ws: WebSocket):
    """Handle drawing path execution."""
    points = data.get('points', [])
    if len(points) < 2:
        await ws.send_json({'type': 'error', 'message': 'Need at least 2 points'})
        return

    # Stop any current execution
    if state.engine and state.engine.is_running:
        await _stop_execution()

    # Notify browser: backend owns cmd_vel
    await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'backend'})

    # Simplify path
    simplified = rdp_simplify(points, epsilon=0.1)
    logger.info(f'Drawing path: {len(points)} points -> {len(simplified)} simplified')

    # Convert to commands
    commands = points_to_commands(simplified)
    if not commands:
        await ws.send_json({'type': 'error', 'message': 'Path too short'})
        await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})
        return

    total_segments = len(commands)

    # Custom broadcast that also sends draw progress
    original_segment = [0]

    async def draw_broadcast(status: dict):
        await state.broadcast(status)
        # Calculate segment from progress
        seg = int((status.get('progress_percent', 0) / 100) * total_segments)
        if seg != original_segment[0]:
            original_segment[0] = seg
            await state.broadcast({
                'type': 'draw_progress',
                'completed_segments': seg,
                'total_segments': total_segments,
            })

    async def run():
        try:
            # Raw odom for distance checking, fused for CTE correction
            def _odom_getter():
                return (state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)

            def _fused_odom_getter():
                return (state.odom_x, state.odom_y, state.odom_theta)

            # Reset path corrector for fresh draw path
            state.path_corrector.reset()
            await state.engine.execute(
                commands, name='drawing', broadcast_fn=draw_broadcast,
                odom_getter=_odom_getter,
                fused_odom_getter=_fused_odom_getter if state.fusion_enabled else None,
                path_corrector=state.path_corrector if state.fusion_enabled else None,
            )
        except Exception as e:
            logger.error(f'Drawing execution error: {e}')
        finally:
            await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})
            await state.broadcast({
                'type': 'draw_progress',
                'completed_segments': total_segments,
                'total_segments': total_segments,
            })

    state.execution_task = asyncio.create_task(run())


# ---------------------------------------------------------------------------
# Video Recording Handlers
# ---------------------------------------------------------------------------

async def _do_start_recording(name: str = 'recording'):
    """Internal: start video recording."""
    if not state.recorder:
        return False
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, state.recorder.start, name)
    if ok:
        state.recording_start_time = time.monotonic()
        state.recording_filename = state.recorder._current_file
        await state.broadcast({
            'type': 'recording_status',
            'state': 'recording',
            'filename': os.path.basename(state.recording_filename or ''),
            'duration': 0,
        })
        # Start periodic duration updates
        async def update_duration():
            while state.recorder and state.recorder._recording:
                elapsed = time.monotonic() - (state.recording_start_time or 0)
                await state.broadcast({
                    'type': 'recording_status',
                    'state': 'recording',
                    'filename': os.path.basename(state.recording_filename or ''),
                    'duration': round(elapsed, 1),
                })
                await asyncio.sleep(1.0)

        state.recording_timer_task = asyncio.create_task(update_duration())
        return True
    return False


async def _do_stop_recording():
    """Internal: stop video recording and verify."""
    if not state.recorder:
        return
    if state.recording_timer_task:
        state.recording_timer_task.cancel()
        try:
            await state.recording_timer_task
        except asyncio.CancelledError:
            pass

    elapsed = 0.0
    if state.recording_start_time:
        elapsed = time.monotonic() - state.recording_start_time

    loop = asyncio.get_event_loop()
    filepath = await loop.run_in_executor(None, state.recorder.stop)
    filename = os.path.basename(state.recording_filename or '')

    await state.broadcast({
        'type': 'recording_status',
        'state': 'stopped',
        'filename': filename,
        'duration': round(elapsed, 1),
    })

    # Verify recording
    if filepath and os.path.isfile(filepath):
        size = os.path.getsize(filepath)
        await state.broadcast({
            'type': 'recording_verified',
            'success': size > 0,
            'filename': filename,
            'size_bytes': size,
        })
    else:
        await state.broadcast({
            'type': 'recording_verified',
            'success': False,
            'filename': filename,
            'error': 'file not found',
        })

    state.recording_start_time = None
    state.recording_filename = None


async def _handle_start_recording(data: dict, ws: WebSocket):
    """Handle manual start recording request."""
    name = data.get('name', 'recording')
    ok = await _do_start_recording(name)
    if not ok:
        await ws.send_json({
            'type': 'error',
            'message': 'Failed to start recording',
        })


async def _handle_stop_recording(ws: WebSocket):
    """Handle manual stop recording request."""
    if state.recorder and state.recorder._recording:
        await _do_stop_recording()
    else:
        await ws.send_json({
            'type': 'recording_status',
            'state': 'stopped',
            'filename': '',
            'duration': 0,
        })


# ---------------------------------------------------------------------------
# Teleport & Precision Move Handlers
# ---------------------------------------------------------------------------

async def _handle_teleport(data: dict, ws: WebSocket):
    """Handle teleport command."""
    target = data.get('target', '')

    # Stop any running pattern or precision move first
    if state.engine and state.engine.is_running:
        await _stop_execution()
    if state.precision_move_task and not state.precision_move_task.done():
        state.precision_move_cancel = True
        try:
            await state.precision_move_task
        except asyncio.CancelledError:
            pass

    # Resolve coordinates
    presets = {
        'start': {'x': -10.0, 'y': 0.9, 'z': 1.0, 'facing_x_positive': True},
        'end':   {'x':  10.0, 'y': 0.9, 'z': 1.0, 'facing_x_positive': True},
        'spawn': {'x': -10.0, 'y': 0.9, 'z': 1.0, 'facing_x_positive': True},
    }

    if target in presets:
        coords = presets[target]
    elif target == 'custom':
        x = float(data.get('x', 0.0))
        y = float(data.get('y', 0.0))
        yaw = float(data.get('yaw', 0.0))
        facing = yaw >= -math.pi / 2 and yaw <= math.pi / 2
        coords = {'x': x, 'y': y, 'z': 1.0, 'facing_x_positive': facing}
    else:
        await ws.send_json({'type': 'teleport_result', 'success': False, 'message': f'Unknown target: {target}'})
        return

    try:
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(
            None, lambda: teleport_robot(
                x=coords['x'], y=coords['y'], z=coords['z'],
                facing_x_positive=coords['facing_x_positive']
            )
        )
        if ok:
            # Reset EKF after teleport to avoid innovation spike
            await asyncio.sleep(0.5)
            if state.fusion_enabled:
                state.ekf.reset(state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)
                state.odom_x = state.raw_odom_x
                state.odom_y = state.raw_odom_y
                state.odom_theta = state.raw_odom_theta
        await ws.send_json({'type': 'teleport_result', 'success': ok, 'message': 'Teleport complete' if ok else 'Teleport failed'})
    except Exception as e:
        logger.error(f'Teleport error: {e}')
        await ws.send_json({'type': 'teleport_result', 'success': False, 'message': str(e)})


async def _handle_precision_move(data: dict, ws: WebSocket):
    """Handle precision movement command."""
    action = data.get('action', '')

    # Parse action
    move_params = {
        'forward_1m':     {'type': 'linear', 'distance': 1.0,  'speed': 0.5},
        'forward_5m':     {'type': 'linear', 'distance': 5.0,  'speed': 0.5},
        'forward_10m':    {'type': 'linear', 'distance': 10.0, 'speed': 0.5},
        'turn_left_90':   {'type': 'angular', 'angle': math.pi / 2,  'speed': 0.5},
        'turn_right_90':  {'type': 'angular', 'angle': -math.pi / 2, 'speed': 0.5},
    }

    if action not in move_params:
        await ws.send_json({'type': 'precision_move_status', 'state': 'failed', 'progress_percent': 0, 'message': f'Unknown action: {action}'})
        return

    params = move_params[action]

    # Stop any running pattern first
    if state.engine and state.engine.is_running:
        await _stop_execution()

    # Cancel any existing precision move
    if state.precision_move_task and not state.precision_move_task.done():
        state.precision_move_cancel = True
        try:
            await state.precision_move_task
        except asyncio.CancelledError:
            pass

    state.precision_move_cancel = False

    async def run_move():
        try:
            # Claim cmd_vel ownership
            await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'backend'})
            await ws.send_json({'type': 'precision_move_status', 'state': 'executing', 'progress_percent': 0})

            progress = 0.0

            # --- Heading correction phase for linear moves ---
            # For forward moves, first correct heading to 0 degrees (+X axis)
            if params['type'] == 'linear':
                HEADING_TOLERANCE = 0.035  # ~2 degrees
                HEADING_SPEED = 0.4
                heading_timeout = 10.0  # seconds max for heading correction
                heading_start = time.monotonic()

                while not state.precision_move_cancel:
                    heading_elapsed = time.monotonic() - heading_start
                    if heading_elapsed > heading_timeout:
                        logger.warning('Heading correction timed out')
                        break

                    # Target heading is 0 (face +X world axis)
                    heading_error = state.odom_theta
                    # Normalize to [-pi, pi]
                    while heading_error > math.pi:
                        heading_error -= 2 * math.pi
                    while heading_error < -math.pi:
                        heading_error += 2 * math.pi

                    if abs(heading_error) < HEADING_TOLERANCE:
                        break

                    # Proportional control with minimum speed
                    turn_speed = max(0.15, min(HEADING_SPEED, abs(heading_error) * 0.8))
                    sign = -1.0 if heading_error > 0 else 1.0

                    if HAS_RCLPY and state.publisher:
                        msg = Twist()
                        msg.angular.z = sign * turn_speed
                        state.publisher.publish(msg)

                    # Heading phase is 0-10% of total progress
                    heading_progress = min(1.0 - abs(heading_error) / math.pi, 1.0) * 10.0
                    await ws.send_json({'type': 'precision_move_status', 'state': 'executing', 'progress_percent': round(heading_progress, 1)})

                    await asyncio.sleep(1.0 / VelocityRampingEngine.PUBLISH_HZ)

                # Stop rotation before starting linear move
                if HAS_RCLPY and state.publisher:
                    msg = Twist()
                    state.publisher.publish(msg)

                if state.precision_move_cancel:
                    await ws.send_json({'type': 'precision_move_status', 'state': 'cancelled', 'progress_percent': 0})
                    return

                # Brief pause to stabilize after heading correction
                await asyncio.sleep(0.1)

            # --- Main movement phase ---
            # Record start pose (after heading correction, if any)
            start_x = state.odom_x
            start_y = state.odom_y
            start_theta = state.odom_theta

            target_value = abs(params['distance']) if params['type'] == 'linear' else abs(params['angle'])
            timeout = target_value / abs(params['speed']) * 2.0 + 2.0  # 2x expected + buffer
            start_time = time.monotonic()

            # For linear moves, progress goes from 10% to 100% (heading was 0-10%)
            # For angular moves, progress goes from 0% to 100%
            progress_offset = 10.0 if params['type'] == 'linear' else 0.0
            progress_range = 100.0 - progress_offset

            while not state.precision_move_cancel:
                elapsed = time.monotonic() - start_time
                if elapsed > timeout:
                    logger.warning(f'Precision move timed out after {elapsed:.1f}s')
                    break

                # Compute progress
                if params['type'] == 'linear':
                    dx = state.odom_x - start_x
                    dy = state.odom_y - start_y
                    current = math.hypot(dx, dy)
                    target = params['distance']
                else:
                    dtheta = state.odom_theta - start_theta
                    # Normalize to [-pi, pi]
                    while dtheta > math.pi:
                        dtheta -= 2 * math.pi
                    while dtheta < -math.pi:
                        dtheta += 2 * math.pi
                    current = abs(dtheta)
                    target = abs(params['angle'])

                raw_progress = min(current / target, 1.0) if target > 0 else 1.0
                progress = progress_offset + raw_progress * progress_range

                # Check completion
                if current >= target * 0.98:
                    break

                # Deceleration within 20% of target
                remaining_frac = 1.0 - (current / target) if target > 0 else 0
                if remaining_frac < 0.2:
                    speed_factor = max(0.3, remaining_frac / 0.2)
                else:
                    speed_factor = 1.0

                # Publish velocity
                if HAS_RCLPY and state.publisher:
                    msg = Twist()
                    if params['type'] == 'linear':
                        msg.linear.x = params['speed'] * speed_factor
                    else:
                        sign = 1.0 if params['angle'] > 0 else -1.0
                        msg.angular.z = sign * abs(params['speed']) * speed_factor
                    state.publisher.publish(msg)

                # Send progress
                await ws.send_json({'type': 'precision_move_status', 'state': 'executing', 'progress_percent': round(progress, 1)})

                await asyncio.sleep(1.0 / VelocityRampingEngine.PUBLISH_HZ)

            # Stop
            if HAS_RCLPY and state.publisher:
                msg = Twist()
                state.publisher.publish(msg)

            if state.precision_move_cancel:
                await ws.send_json({'type': 'precision_move_status', 'state': 'cancelled', 'progress_percent': round(progress, 1)})
            else:
                await ws.send_json({'type': 'precision_move_status', 'state': 'completed', 'progress_percent': 100})

        except Exception as e:
            logger.error(f'Precision move error: {e}')
            # Stop velocity
            if HAS_RCLPY and state.publisher:
                msg = Twist()
                state.publisher.publish(msg)
            await ws.send_json({'type': 'precision_move_status', 'state': 'failed', 'progress_percent': 0, 'message': str(e)})
        finally:
            await state.broadcast({'type': 'cmd_vel_owner', 'owner': 'browser'})

    state.precision_move_task = asyncio.create_task(run_move())


async def _handle_cancel_move(ws: WebSocket):
    """Cancel any running precision move."""
    if state.precision_move_task and not state.precision_move_task.done():
        state.precision_move_cancel = True
        # Immediately publish zero velocity
        if HAS_RCLPY and state.publisher:
            msg = Twist()
            state.publisher.publish(msg)
        await ws.send_json({'type': 'ack', 'action': 'cancel_move'})
    else:
        await ws.send_json({'type': 'ack', 'action': 'cancel_move', 'note': 'no move running'})


# ---------------------------------------------------------------------------
# Simulation Editor — SDF read / write
# ---------------------------------------------------------------------------

# Locate the world SDF file
_GAZEBO_DIR = _SCRIPT_DIR.parent          # simulation/gazebo
_WORLDS_DIR = _GAZEBO_DIR / 'worlds'
_MODELS_DIR = _GAZEBO_DIR / 'models'
_WORLD_FILE = _WORLDS_DIR / 'cotton_field_with_plants.sdf'
_TERRAIN_SDF = _MODELS_DIR / 'soil_terrain' / 'model.sdf'


def _parse_sim_config() -> dict:
    """Parse the current SDF world file and extract grid/terrain config."""
    config = {
        'rows': 0, 'cols': 0,
        'row_spacing': 0.9, 'col_spacing': 0.7,
        'terrain_scale': 5, 'terrain_z': 0.1,
        'plants': [],
    }

    if not _WORLD_FILE.exists():
        logger.warning(f'World file not found: {_WORLD_FILE}')
        return config

    content = _WORLD_FILE.read_text()

    # Parse plants:  <name>cotton_plant_rN_pM</name> ... <uri>model://cotton_plant_TYPE</uri> ... <pose>X Y ...yaw</pose>
    plant_re = re.compile(
        r'<include>\s*'
        r'<name>(cotton_plant_r(\d+)_p(\d+))</name>\s*'
        r'<uri>model://cotton_plant_(small|medium|tall)</uri>\s*'
        r'<pose>([\-\d.]+)\s+([\-\d.]+)\s+[\-\d.]+\s+[\-\d.]+\s+[\-\d.]+\s+([\-\d.]+)</pose>\s*'
        r'</include>',
        re.DOTALL
    )

    max_r = -1
    max_c = -1
    plants = []
    xs = set()
    ys = set()

    for m in plant_re.finditer(content):
        name = m.group(1)
        r_idx = int(m.group(2))
        c_idx = int(m.group(3))
        ptype = m.group(4)
        x = float(m.group(5))
        y = float(m.group(6))
        yaw = float(m.group(7))

        plants.append({'name': name, 'type': ptype, 'x': x, 'y': y, 'yaw': yaw})
        max_r = max(max_r, r_idx)
        max_c = max(max_c, c_idx)
        xs.add(round(x, 4))
        ys.add(round(y, 4))

    config['plants'] = plants
    config['rows'] = max_r + 1 if max_r >= 0 else 0
    config['cols'] = max_c + 1 if max_c >= 0 else 0

    # Infer spacing from sorted unique positions
    if len(xs) > 1:
        sx = sorted(xs)
        diffs = [sx[i + 1] - sx[i] for i in range(len(sx) - 1)]
        config['col_spacing'] = round(sum(diffs) / len(diffs), 4)
    if len(ys) > 1:
        sy = sorted(ys)
        diffs = [sy[i + 1] - sy[i] for i in range(len(sy) - 1)]
        config['row_spacing'] = round(sum(diffs) / len(diffs), 4)

    config['field_width'] = round((config['cols'] - 1) * config['col_spacing'], 2) if config['cols'] > 1 else 0
    config['field_height'] = round((config['rows'] - 1) * config['row_spacing'], 2) if config['rows'] > 1 else 0

    # Parse terrain z from world file
    tz_match = re.search(r'<name>soil_terrain</name>\s*<uri>[^<]+</uri>\s*<pose>[\-\d.]+\s+[\-\d.]+\s+([\-\d.]+)', content)
    if tz_match:
        config['terrain_z'] = float(tz_match.group(1))

    # Parse terrain scale from model SDF
    if _TERRAIN_SDF.exists():
        tsdf = _TERRAIN_SDF.read_text()
        scale_m = re.search(r'<scale>([\d.]+)\s+[\d.]+\s+([\d.]+)</scale>', tsdf)
        if scale_m:
            config['terrain_scale'] = int(float(scale_m.group(1)))

    return config


def _generate_plants_sdf(config: dict) -> str:
    """Generate SDF include blocks for cotton plants from config."""
    plants = config.get('plants', [])
    lines = []
    for p in plants:
        ptype = p.get('type', 'small')
        lines.append(
            f'    <include>\n'
            f'      <name>{p["name"]}</name>\n'
            f'      <uri>model://cotton_plant_{ptype}</uri>\n'
            f'      <pose>{p["x"]:.4f} {p["y"]:.4f} 0 0 0 {p["yaw"]:.4f}</pose>\n'
            f'    </include>'
        )
    return '\n\n'.join(lines)


def _update_world_sdf(config: dict) -> None:
    """Rewrite the world SDF with new plant grid and terrain settings."""
    if not _WORLD_FILE.exists():
        raise FileNotFoundError(f'World file not found: {_WORLD_FILE}')

    content = _WORLD_FILE.read_text()

    # 1. Replace terrain pose Z
    tz = config.get('terrain_z', 0.1)
    content = re.sub(
        r'(<name>soil_terrain</name>\s*<uri>[^<]+</uri>\s*<pose>[\-\d.]+\s+[\-\d.]+\s+)[\-\d.]+',
        lambda m: m.group(1) + f'{tz}',
        content
    )

    # 2. Replace all cotton plant includes
    # Find the region between the "Cotton Plants" comment and the next model/section
    plant_region_re = re.compile(
        r'(<!-- =+ -->\s*<!-- Cotton Plants\s*-->\s*<!-- =+ -->\s*\n)'
        r'(.*?)'
        r'(\n\s*<!-- RTK Base Station|\n\s*<model name="rtk)',
        re.DOTALL
    )
    plants_sdf = _generate_plants_sdf(config)
    content = plant_region_re.sub(
        lambda m: m.group(1) + '\n' + plants_sdf + '\n' + m.group(3),
        content
    )

    _WORLD_FILE.write_text(content)
    logger.info(f'Updated world SDF: {len(config.get("plants", []))} plants')

    # 3. Update terrain model SDF (scale and collision box)
    ts = config.get('terrain_scale', 5)
    if _TERRAIN_SDF.exists():
        tsdf = _TERRAIN_SDF.read_text()
        # Update scale
        tsdf = re.sub(
            r'<scale>[\d.]+\s+[\d.]+\s+[\d.]+</scale>',
            f'<scale>{ts} 0.5 {ts}</scale>',
            tsdf
        )
        # Update collision box
        box_size = ts * 2
        tsdf = re.sub(
            r'<size>[\d.]+\s+[\d.]+\s+[\d.]+</size>',
            f'<size>{box_size} {box_size} 0.09</size>',
            tsdf
        )
        _TERRAIN_SDF.write_text(tsdf)
        logger.info(f'Updated terrain SDF: scale={ts}, box={box_size}m')


def _rebuild_package() -> bool:
    """Rebuild the vehicle_control package so installed files are updated."""
    ws_dir = _SCRIPT_DIR.parents[4]  # workspace root (pragati_ros2)
    try:
        result = subprocess.run(
            ['colcon', 'build', '--packages-select', 'vehicle_control', '--symlink-install'],
            cwd=str(ws_dir),
            capture_output=True, text=True, timeout=60,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        if result.returncode == 0:
            logger.info('Package rebuild succeeded')
            return True
        else:
            logger.error(f'Package rebuild failed: {result.stderr}')
            return False
    except Exception as e:
        logger.error(f'Rebuild error: {e}')
        return False


def _gz_remove_model(name: str) -> bool:
    """Remove a model from the running Gazebo simulation by name."""
    try:
        result = subprocess.run(
            ['gz', 'service', '-s', '/world/cotton_field/remove',
             '--reqtype', 'gz.msgs.Entity',
             '--reptype', 'gz.msgs.Boolean',
             '--timeout', '2000',
             '--req', f'name: "{name}" type: MODEL'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True
        else:
            logger.warning(f'gz remove {name}: {result.stderr.strip()}')
            return False
    except Exception as e:
        logger.warning(f'gz remove {name} error: {e}')
        return False


def _gz_spawn_plant(name: str, ptype: str, x: float, y: float, yaw: float) -> bool:
    """Spawn a cotton plant model in the running Gazebo simulation."""
    sdf_xml = (
        f'<sdf version="1.9"><include>'
        f'<name>{name}</name>'
        f'<uri>model://cotton_plant_{ptype}</uri>'
        f'<pose>{x:.4f} {y:.4f} 0 0 0 {yaw:.4f}</pose>'
        f'</include></sdf>'
    )
    sdf_escaped = sdf_xml.replace('"', '\\"')
    req_str = f'sdf: "{sdf_escaped}"'
    try:
        result = subprocess.run(
            ['gz', 'service', '-s', '/world/cotton_field/create',
             '--reqtype', 'gz.msgs.EntityFactory',
             '--reptype', 'gz.msgs.Boolean',
             '--timeout', '3000',
             '--req', req_str],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True
        else:
            logger.warning(f'gz spawn {name}: {result.stderr.strip()}')
            return False
    except Exception as e:
        logger.warning(f'gz spawn {name} error: {e}')
        return False


def _apply_to_running_gazebo(old_config: dict, new_config: dict) -> dict:
    """Apply plant changes to the running Gazebo simulation via gz service.
    
    Returns a summary dict with counts of removed/spawned/failed.
    """
    summary = {'removed': 0, 'spawned': 0, 'remove_failed': 0, 'spawn_failed': 0}

    # 1. Remove old plants
    old_plants = old_config.get('plants', [])
    for p in old_plants:
        if _gz_remove_model(p['name']):
            summary['removed'] += 1
        else:
            summary['remove_failed'] += 1

    # 2. Spawn new plants
    new_plants = new_config.get('plants', [])
    for p in new_plants:
        if _gz_spawn_plant(p['name'], p.get('type', 'small'), p['x'], p['y'], p.get('yaw', 0)):
            summary['spawned'] += 1
        else:
            summary['spawn_failed'] += 1

    logger.info(f'Gazebo live update: removed={summary["removed"]}, spawned={summary["spawned"]}, '
                f'remove_failed={summary["remove_failed"]}, spawn_failed={summary["spawn_failed"]}')
    return summary


async def _handle_get_sim_config(ws: WebSocket):
    """Send current simulation configuration parsed from SDF."""
    try:
        config = _parse_sim_config()
        await ws.send_json({'type': 'sim_config', 'config': config})
    except Exception as e:
        logger.error(f'get_sim_config error: {e}')
        await ws.send_json({'type': 'sim_config_error', 'message': str(e)})


async def _handle_update_sim_config(data: dict, ws: WebSocket):
    """Apply new simulation configuration: update running Gazebo + rewrite SDF."""
    try:
        config = data.get('config', {})
        if not config.get('plants'):
            await ws.send_json({'type': 'sim_config_error', 'message': 'No plant data provided'})
            return

        # 1. Read old config for removal list
        loop = asyncio.get_event_loop()
        old_config = await loop.run_in_executor(None, _parse_sim_config)

        # 2. Apply live changes to running Gazebo (remove old, spawn new)
        summary = await loop.run_in_executor(None, _apply_to_running_gazebo, old_config, config)

        # 3. Update SDF files for persistence (next launch will use new config)
        await loop.run_in_executor(None, _update_world_sdf, config)
        await loop.run_in_executor(None, _rebuild_package)

        # 4. Re-read the config to confirm
        new_config = await loop.run_in_executor(None, _parse_sim_config)

        msg = {
            'type': 'sim_config_applied',
            'config': new_config,
            'plants_updated': summary['spawned'],
            'removed': summary['removed'],
            'spawn_failed': summary['spawn_failed'],
        }
        if summary['spawn_failed'] > 0 or summary['remove_failed'] > 0:
            msg['warning'] = f'{summary["spawn_failed"]} spawn and {summary["remove_failed"]} remove failures'

        await ws.send_json(msg)
        logger.info(f'Simulation config applied: {summary["spawned"]} plants live in Gazebo')

    except Exception as e:
        logger.error(f'update_sim_config error: {e}')
        await ws.send_json({'type': 'sim_config_error', 'message': str(e)})


# ---------------------------------------------------------------------------
# No-cache middleware for development — ensures browser always loads latest JS/CSS
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == '/' or path.endswith(('.js', '.css', '.html')):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

app.add_middleware(NoCacheStaticMiddleware)

# ---------------------------------------------------------------------------
# Static Files (mounted last so API routes take priority)
# ---------------------------------------------------------------------------

app.mount('/', StaticFiles(directory=str(_SCRIPT_DIR), html=True), name='static')


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend:app', host='0.0.0.0', port=8888, log_level='info')
