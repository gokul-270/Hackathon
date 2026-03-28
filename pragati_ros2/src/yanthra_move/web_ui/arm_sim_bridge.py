#!/usr/bin/env python3
"""
Arm Simulation Bridge Node
===========================
Bridges the web UI to Gazebo simulation for the arm.
Handles: TF transforms, cotton spawning, centroid.txt writing, reachability computation.

Communication:
  Subscribe: /arm_sim/command  (std_msgs/String, JSON)
  Publish:   /arm_sim/response (std_msgs/String, JSON)

Supported actions (via JSON on /arm_sim/command):
  {"action": "spawn_cotton", "cam_x": 0.328, "cam_y": -0.011, "cam_z": -0.003, "l4_pos": -0.100}
  {"action": "remove_cotton"}
  {"action": "write_centroid", "cam_x": 0.328, "cam_y": -0.011, "cam_z": -0.003}
  {"action": "compute_approach", "cam_x": 0.328, "cam_y": -0.011, "cam_z": -0.003}
"""

import json
import math
import os
import subprocess
import time

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.time import Time
from std_msgs.msg import String, Float64
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformListener
from geometry_msgs.msg import PointStamped
import tf2_geometry_msgs  # noqa: F401


class ArmSimBridge(Node):
    def __init__(self):
        super().__init__('arm_sim_bridge')

        # TF
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # Joint state tracking — subscribe to Gazebo's published states
        # instead of publishing our own (which would conflict with ros_gz_bridge).
        self.joint_names = ['joint2', 'joint3', 'joint4', 'joint5']
        self.joint_positions = {name: 0.0 for name in self.joint_names}
        self.create_subscription(
            JointState, '/joint_states', self._joint_state_cb, 10)

        # Joint limits (from URDF and config)
        self.joint_limits = {
            'joint3': {'min': -0.9, 'max': 0.0, 'unit': 'rad'},      # revolute
            'joint4': {'min': -0.250, 'max': 0.350, 'unit': 'm'},    # prismatic lateral
            'joint5': {'min': 0.0, 'max': 0.450, 'unit': 'm'}        # prismatic extension
        }

        # Publishers (to Gazebo bridge — use production topic names)
        self.response_pub = self.create_publisher(String, '/arm_sim/response', 10)
        self.j3_cmd_pub = self.create_publisher(Float64, '/joint3_position_controller/command', 10)
        self.j4_cmd_pub = self.create_publisher(Float64, '/joint4_position_controller/command', 10)
        self.j5_cmd_pub = self.create_publisher(Float64, '/joint5_position_controller/command', 10)

        # Subscribers
        self.create_subscription(String, '/arm_sim/command', self.command_cb, 10)
        
        # Joint command filters (UI → clamped → Gazebo)
        self.create_subscription(Float64, '/joint3_ui', self._j3_ui_cb, 10)
        self.create_subscription(Float64, '/joint4_ui', self._j4_ui_cb, 10)
        self.create_subscription(Float64, '/joint5_ui', self._j5_ui_cb, 10)

        # State
        self.cotton_spawned = False
        self.cotton_counter = 0
        self.pick_in_progress = False

        # Last cotton placement (used by pick_cotton)
        self.last_cotton_cam = None   # (cam_x, cam_y, cam_z)
        self.last_cotton_l4 = 0.0
        self.enable_j4_compensation = True   # Match physical arm default
        self.enable_phi_compensation = False  # Disabled by default
        
        # Phi compensation parameters (from production.yaml)
        self.phi_zone1_max_deg = 50.5
        self.phi_zone2_max_deg = 60.0
        self.phi_zone1_offset = 0.014   # rotations (+5°)
        self.phi_zone2_offset = 0.0
        self.phi_zone3_offset = -0.014  # rotations (-5°)
        self.phi_l5_scale = 0.5         # L5 scaling factor
        self.joint5_max = 0.6           # meters (for L5 normalization)

        # Hardware offset: distance from yanthra_link origin to joint5 origin
        # along X-axis. Using 0.320 to match C++ default (motion_controller.cpp line 2336).
        # Config files specify 0.290, but C++ default is 0.320 if config not loaded.
        # Physical arm logs show J5 values consistent with 0.320.
        self.hardware_offset = 0.320

        # Workspace root (for centroid.txt)
        self.workspace_root = self._find_workspace_root()

        self.get_logger().info('🌐 Arm Simulation Bridge started')
        self.get_logger().info(f'   Workspace: {self.workspace_root}')
        self.get_logger().info('   Listening on: /arm_sim/command')
        self.get_logger().info('   Publishing to: /arm_sim/response')

    def _find_workspace_root(self):
        """Find the pragati_ros2 workspace root."""
        # Walk up from this file's location
        path = os.path.dirname(os.path.abspath(__file__))
        for _ in range(10):
            if os.path.exists(os.path.join(path, 'centroid.txt')) or \
               os.path.exists(os.path.join(path, 'src', 'yanthra_move')):
                return path
            path = os.path.dirname(path)
        # Fallback
        return os.path.expanduser('~/pragati_ros2')

    def send_response(self, data: dict):
        """Publish JSON response."""
        msg = String()
        msg.data = json.dumps(data)
        self.response_pub.publish(msg)
        self.get_logger().info(f'📤 Response: {data.get("action", "?")} → {data.get("success", "?")}')

    def command_cb(self, msg: String):
        """Handle incoming JSON commands from web UI."""
        try:
            cmd = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.send_response({'action': 'error', 'success': False, 'message': f'Invalid JSON: {e}'})
            return

        action = cmd.get('action', '')
        self.get_logger().info(f'📥 Command: {action}')

        try:
            if action == 'spawn_cotton':
                self.handle_spawn_cotton(cmd)
            elif action == 'remove_cotton':
                self.handle_remove_cotton(cmd)
            elif action == 'write_centroid':
                self.handle_write_centroid(cmd)
            elif action == 'compute_approach':
                self.handle_compute_approach(cmd)
            elif action == 'set_camera_view':
                self.handle_set_camera_view(cmd)
            elif action == 'pick_cotton':
                self.handle_pick_cotton(cmd)
            else:
                self.send_response({'action': action, 'success': False, 'message': f'Unknown action: {action}'})
        except Exception as e:
            self.get_logger().error(f'❌ Error handling {action}: {e}')
            self.send_response({'action': action, 'success': False, 'message': str(e)})

    # ──────────────────────────────────────────────────────────────────
    # Action handlers
    # ──────────────────────────────────────────────────────────────────

    def handle_spawn_cotton(self, cmd):
        """Spawn a cotton ball in Gazebo at the given camera-frame position."""
        cam_x = float(cmd.get('cam_x', 0.328))
        cam_y = float(cmd.get('cam_y', -0.011))
        cam_z = float(cmd.get('cam_z', -0.003))
        l4_pos = float(cmd.get('l4_pos', 0.0))
        
        # Store compensation settings
        self.enable_j4_compensation = cmd.get('enable_j4_compensation', True)
        self.enable_phi_compensation = cmd.get('enable_phi_compensation', False)

        self.get_logger().info(
            f'🎯 Spawning cotton: cam({cam_x}, {cam_y}, {cam_z}), L4={l4_pos} '
            f'[J4_comp={self.enable_j4_compensation}, Phi_comp={self.enable_phi_compensation}]')
        # Remember for pick_cotton
        self.last_cotton_cam = (cam_x, cam_y, cam_z)
        self.last_cotton_l4 = l4_pos
        # Step 1: Compute world position using forward kinematics (no TF dependency!)
        joints = dict(self.joint_positions)
        joints['joint4'] = l4_pos
        wx, wy, wz = self.camera_to_world_fk(cam_x, cam_y, cam_z, joints)
        self.get_logger().info(f'   FK → world({wx:.4f}, {wy:.4f}, {wz:.4f})')

        # Step 2: Send J4 command to Gazebo and track internally
        j4_msg = Float64()
        j4_msg.data = l4_pos
        self.j4_cmd_pub.publish(j4_msg)
        self.joint_positions['joint4'] = l4_pos

        # Step 3: Remove previous cotton if any
        if self.cotton_spawned:
            self._gz_remove_model('cotton_target')

        # Step 4: Spawn cotton sphere in Gazebo
        self.cotton_counter += 1
        model_name = 'cotton_target'

        sdf = f'''<?xml version="1.0" ?>
<sdf version="1.9">
  <model name="{model_name}">
    <static>true</static>
    <link name="cotton_link">
      <visual name="cotton_visual">
        <geometry>
          <sphere><radius>0.03</radius></sphere>
        </geometry>
        <material>
          <ambient>1 1 1 1</ambient>
          <diffuse>1.0 1.0 1.0 1</diffuse>
          <specular>1.0 1.0 1.0 1</specular>
          <emissive>0.8 0.8 0.8 1</emissive>
        </material>
      </visual>
    </link>
  </model>
</sdf>'''

        success = self._gz_spawn_model(model_name, sdf, wx, wy, wz)
        self.cotton_spawned = success

        # Step 5: Reset J4 to home (send to Gazebo if running)
        if abs(l4_pos) > 0.001:
            self.get_logger().info('   Resetting J4 to home (0.0)...')
            self.joint_positions['joint4'] = 0.0
            j4_msg = Float64()
            j4_msg.data = 0.0
            self.j4_cmd_pub.publish(j4_msg)

        self.send_response({
            'action': 'spawn_cotton',
            'success': success,
            'world_x': round(wx, 4),
            'world_y': round(wy, 4),
            'world_z': round(wz, 4),
            'cam_x': cam_x, 'cam_y': cam_y, 'cam_z': cam_z,
            'l4_pos': l4_pos,
            'message': f'Cotton placed at world ({wx:.4f}, {wy:.4f}, {wz:.4f})' if success else 'Spawn failed'
        })

    def handle_remove_cotton(self, cmd):
        """Remove cotton from Gazebo."""
        success = self._gz_remove_model('cotton_target')
        self.cotton_spawned = False
        self.send_response({
            'action': 'remove_cotton',
            'success': success,
            'message': 'Cotton removed' if success else 'Remove failed (may not exist)'
        })

    def handle_write_centroid(self, cmd):
        """Write centroid.txt with the given camera coordinates."""
        cam_x = float(cmd.get('cam_x', 0.328))
        cam_y = float(cmd.get('cam_y', -0.011))
        cam_z = float(cmd.get('cam_z', -0.003))

        centroid_path = os.path.join(self.workspace_root, 'centroid.txt')
        try:
            with open(centroid_path, 'w') as f:
                f.write(f'# Written by arm_sim_bridge for web UI testing\n')
                f.write(f'# Camera frame coordinates (x y z in meters)\n')
                f.write(f'{cam_x} {cam_y} {cam_z}\n')
            self.get_logger().info(f'📝 Wrote centroid.txt: {cam_x} {cam_y} {cam_z}')
            self.send_response({
                'action': 'write_centroid',
                'success': True,
                'path': centroid_path,
                'cam_x': cam_x, 'cam_y': cam_y, 'cam_z': cam_z,
                'message': f'Written to {centroid_path}'
            })
        except Exception as e:
            self.send_response({
                'action': 'write_centroid',
                'success': False,
                'message': str(e)
            })

    def handle_compute_approach(self, cmd):
        """Compute joint values for given camera coords (without moving)."""
        cam_x = float(cmd.get('cam_x', 0.328))
        cam_y = float(cmd.get('cam_y', -0.011))
        cam_z = float(cmd.get('cam_z', -0.003))

        # Transform camera → yanthra_link (arm base frame)
        arm_pos = self.transform_camera_to_frame(cam_x, cam_y, cam_z, 'yanthra_link')
        if arm_pos is None:
            self.send_response({
                'action': 'compute_approach', 'success': False,
                'message': 'TF transform to yanthra_link failed'
            })
            return

        ax, ay, az = arm_pos

        # Polar conversion (same as motion_controller.cpp)
        r = math.sqrt(ax * ax + az * az)
        theta = ay  # J4: direct Y passthrough
        denom = math.sqrt(az * az + ax * ax)
        phi = math.asin(az / denom) if denom > 0.001 else 0.0

        RAD_TO_ROT = 1.0 / (2.0 * math.pi)
        HARDWARE_OFFSET = 0.290  # from simulation.yaml

        j3_cmd = phi * RAD_TO_ROT       # rotations
        j4_cmd = theta                    # meters
        j5_cmd = r - HARDWARE_OFFSET      # meters

        # Check limits (from simulation.yaml)
        j3_ok = -1.57 <= j3_cmd <= 1.57
        j4_ok = -0.125 <= j4_cmd <= 0.175
        j5_ok = 0.0 <= j5_cmd <= 0.6
        reachable = j3_ok and j4_ok and j5_ok and r > 0.1

        self.get_logger().info(
            f'📐 Computed: cam({cam_x},{cam_y},{cam_z}) → arm({ax:.3f},{ay:.3f},{az:.3f}) '
            f'→ J3={j3_cmd:.4f}rot J4={j4_cmd:.4f}m J5={j5_cmd:.4f}m | {"✅" if reachable else "❌"}'
        )

        self.send_response({
            'action': 'compute_approach',
            'success': True,
            'arm_x': round(ax, 4), 'arm_y': round(ay, 4), 'arm_z': round(az, 4),
            'r': round(r, 4), 'theta': round(theta, 4),
            'phi_rad': round(phi, 4), 'phi_deg': round(math.degrees(phi), 2),
            'j3_cmd': round(j3_cmd, 4), 'j4_cmd': round(j4_cmd, 4), 'j5_cmd': round(j5_cmd, 4),
            'j3_ok': j3_ok, 'j4_ok': j4_ok, 'j5_ok': j5_ok,
            'reachable': reachable,
            'message': 'Reachable ✅' if reachable else 'NOT reachable ❌'
        })

    # ──────────────────────────────────────────────────────────────────
    # Camera view presets
    # ──────────────────────────────────────────────────────────────────

    # position (x y z) and euler angles (roll pitch yaw) in radians
    # Robot is at origin (z=0.1), arm extends along +X
    CAMERA_PRESETS = {
        'front':       {'pos': (1.5, 0.0, 0.5),  'rpy': (0.0, 0.2, 3.14159),  'desc': 'Front view'},
        'front_close': {'pos': (0.8, 0.0, 0.45), 'rpy': (0.0, 0.25, 3.14159), 'desc': 'Front close-up'},
        'back':        {'pos': (-1.5, 0.0, 0.5), 'rpy': (0.0, 0.2, 0.0),      'desc': 'Back view'},
        'top':         {'pos': (0.0, 0.0, 2.5),  'rpy': (0.0, 1.5708, 0.0),   'desc': 'Top-down view'},
        'left':        {'pos': (0.0, 1.5, 0.5),  'rpy': (0.0, 0.2, -1.5708),  'desc': 'Left side view'},
        'right':       {'pos': (0.0, -1.5, 0.5), 'rpy': (0.0, 0.2, 1.5708),   'desc': 'Right side view'},
        'iso':         {'pos': (1.2, -1.0, 1.0), 'rpy': (0.0, 0.45, 2.356),   'desc': 'Isometric view'},
    }

    @staticmethod
    def _euler_to_quat(roll, pitch, yaw):
        """Convert roll/pitch/yaw (rad) to quaternion (x, y, z, w)."""
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        return (
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy,
        )

    def handle_set_camera_view(self, cmd):
        """Move the Gazebo GUI camera to a preset view."""
        view = cmd.get('view', 'front')
        preset = self.CAMERA_PRESETS.get(view)
        if not preset:
            self.send_response({
                'action': 'set_camera_view', 'success': False,
                'message': f'Unknown view: {view}. Options: {list(self.CAMERA_PRESETS.keys())}'
            })
            return

        px, py, pz = preset['pos']
        roll, pitch, yaw = preset['rpy']
        qx, qy, qz, qw = self._euler_to_quat(roll, pitch, yaw)

        self.get_logger().info(f'📷 Camera → {view} ({preset["desc"]})')

        # Build the protobuf text for gz.msgs.GUICamera
        proto_txt = (
            f'pose: {{'
            f'position: {{x: {px}, y: {py}, z: {pz}}}, '
            f'orientation: {{x: {qx:.6f}, y: {qy:.6f}, z: {qz:.6f}, w: {qw:.6f}}}'
            f'}}'
        )

        # Approach 1 (preferred): service call /gui/move_to/pose
        #   Requires CameraTracking plugin loaded in gazebo_gui.config
        cmd_service = [
            'gz', 'service', '-s', '/gui/move_to/pose',
            '--reqtype', 'gz.msgs.GUICamera',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '3000',
            '--req', proto_txt
        ]

        # Approach 2 (fallback): publish to /gui/move_to/pose topic
        cmd_topic = [
            'gz', 'topic', '-t', '/gui/move_to/pose',
            '-m', 'gz.msgs.GUICamera',
            '-p', proto_txt, '-n', '1'
        ]

        success = False
        err_msg = ''
        for attempt in [cmd_service, cmd_topic]:
            try:
                result = subprocess.run(attempt, capture_output=True, text=True, timeout=6)
                if result.returncode == 0:
                    success = True
                    break
                err_msg = result.stderr.strip()
                self.get_logger().warn(f'Camera attempt failed: {" ".join(attempt[:5])}... → {err_msg}')
            except Exception as e:
                err_msg = str(e)

        self.send_response({
            'action': 'set_camera_view',
            'success': success,
            'view': view,
            'message': f'Camera → {preset["desc"]}' if success else
                       f'Camera move may not have worked — try clicking inside Gazebo first. ({err_msg[:80]})'
        })

    # ──────────────────────────────────────────────────────────────────
    # Pick Cotton — arm moves to reach the cotton
    # ──────────────────────────────────────────────────────────────────

    def handle_pick_cotton(self, cmd):
        """Move the arm in Gazebo to pick the placed cotton.

        Replicates the real robot's approach trajectory:
          camera_link coords -> yanthra_link frame -> polar -> J4, J3, J5 commands.
        Joints move sequentially with timer delays so the user can see the animation.
        The existing Trigger Start (multi-scan) flow is NOT affected.
        """
        if self.pick_in_progress:
            self.send_response({
                'action': 'pick_cotton', 'success': False,
                'message': 'Pick already in progress — wait for it to finish'
            })
            return

        # Use explicit coords from the command, or fall back to last spawned cotton
        cam_x = cmd.get('cam_x')
        cam_y = cmd.get('cam_y')
        cam_z = cmd.get('cam_z')
        if cam_x is not None:
            cam_x, cam_y, cam_z = float(cam_x), float(cam_y), float(cam_z)
        elif self.last_cotton_cam is not None:
            cam_x, cam_y, cam_z = self.last_cotton_cam
        else:
            self.send_response({
                'action': 'pick_cotton', 'success': False,
                'message': 'No cotton placed yet — place cotton first'
            })
            return

        self.pick_in_progress = True
        # Get the L4 scan position when cotton was detected
        l4_scan = self.last_cotton_l4 if self.last_cotton_l4 is not None else 0.0
        self.get_logger().info(
            f'🤚 PICK COTTON — target cam({cam_x}, {cam_y}, {cam_z}), L4_scan={l4_scan}')

        # ── Step 1: camera_link -> yanthra_link using TF (accounts for all joint positions) ──
        arm_pos = self.transform_camera_to_frame(cam_x, cam_y, cam_z, 'yanthra_link')
        if arm_pos is None:
            self.pick_in_progress = False
            self.send_response({
                'action': 'pick_cotton', 'success': False,
                'message': 'TF transform camera_link → yanthra_link failed. Check TF tree.'
            })
            return
        
        ax, ay, az = arm_pos
        self.get_logger().info(
            f'   arm frame (via TF): ({ax:.4f}, {ay:.4f}, {az:.4f})')

        # ── Step 2: Polar conversion (same as motion_controller.cpp) ──
        r = math.sqrt(ax * ax + az * az)
        theta = ay  # J4: direct Y passthrough (meters)
        denom = math.sqrt(az * az + ax * ax)
        phi = math.asin(az / denom) if denom > 0.001 else 0.0
        
        # Apply J4 offset compensation if enabled (matches physical arm behavior)
        if self.enable_j4_compensation and l4_scan != 0.0:
            theta_compensated = theta + l4_scan
            self.get_logger().info(
                f'   J4 compensation: theta {theta:.4f} + offset {l4_scan:.4f} = {theta_compensated:.4f}')
            theta = theta_compensated

        self.get_logger().info(
            f'   polar: r={r:.4f}m, theta={theta:.4f}m, '
            f'phi={math.degrees(phi):.1f} deg')
        
        # ── Step 3: Compute J5 first (needed for phi compensation L5 scaling) ──
        j5_cmd_prelim = r - self.hardware_offset
        
        # Apply phi compensation if enabled (matches physical arm zone-based system)
        phi_compensation = 0.0
        if self.enable_phi_compensation:
            phi_deg = abs(math.degrees(phi))
            phi_normalized = phi_deg / 90.0
            
            # Determine zone and get compensation parameters
            if phi_deg <= self.phi_zone1_max_deg:
                offset = self.phi_zone1_offset
                zone_name = "Zone1"
            elif phi_deg <= self.phi_zone2_max_deg:
                offset = self.phi_zone2_offset
                zone_name = "Zone2"
            else:
                offset = self.phi_zone3_offset
                zone_name = "Zone3"
            
            # Calculate base compensation (in rotations)
            base_compensation = offset
            
            # Apply L5 extension scaling (compensation increases with extension)
            l5_scale_factor = 1.0
            if self.phi_l5_scale > 0.0 and self.joint5_max > 0.0:
                l5_normalized = max(0.0, j5_cmd_prelim) / self.joint5_max
                l5_scale_factor = 1.0 + self.phi_l5_scale * l5_normalized
            
            final_compensation_rot = base_compensation * l5_scale_factor
            phi_compensation = final_compensation_rot * 2.0 * math.pi  # Convert rotations to radians
            
            self.get_logger().info(
                f'   🔧 Phi compensation ({zone_name}, {phi_deg:.1f}°): '
                f'{final_compensation_rot*360.0:+.1f}° (base={base_compensation*360.0:.1f}°, '
                f'L5_scale={l5_scale_factor:.2f})')

        # ── Step 4: Compute Gazebo joint commands ──
        # Gazebo URDF joint3 is in radians, axis (0,-1,0).
        # Due to camera mount rotation, az ≈ -cam_y + 0.1005:
        #   cam_y < 0.10 → phi > 0 → above arm → J3 clamped to 0
        #   cam_y > 0.10 → phi < 0 → below arm → J3 tilts down ✓
        j3_cmd = phi + phi_compensation                      # radians (with compensation)
        j4_cmd = theta                       # meters (already compensated if enabled)
        j5_cmd = j5_cmd_prelim               # meters (calculated earlier for L5 scaling)

        # Clamp to URDF limits
        j3_cmd = max(-0.9, min(0.0, j3_cmd))
        j4_cmd = max(-0.250, min(0.350, j4_cmd))
        j5_cmd = max(0.0, min(0.450, j5_cmd))

        reachable = (j5_cmd > 0.001 or abs(j3_cmd) > 0.001)

        if not reachable:
            self.pick_in_progress = False
            self.get_logger().warn(
                f'   ❌ Cotton unreachable: r={r:.3f}m < offset={self.hardware_offset:.3f}m '
                f'and phi={math.degrees(phi):.1f}° > 0 (above arm). '
                f'Try larger cam_x (further) or larger cam_y (>0.10 for tilt).')
            self.send_response({
                'action': 'pick_cotton', 'success': False,
                'arm_x': round(ax, 4), 'arm_y': round(ay, 4), 'arm_z': round(az, 4),
                'r': round(r, 4), 'theta': round(theta, 4),
                'phi_deg': round(math.degrees(phi), 2),
                'j3_cmd': round(j3_cmd, 4), 'j4_cmd': round(j4_cmd, 4),
                'j5_cmd': round(j5_cmd, 4), 'reachable': False,
                'message': f'Cotton unreachable — r={r:.3f}m too close '
                           f'(need >{self.hardware_offset:.3f}m) or above arm '
                           f'(phi={math.degrees(phi):.0f}°). '
                           f'Arm frame: ({ax:.3f},{ay:.3f},{az:.3f}) → '
                           f'J3={j3_cmd:.3f}rad J4={j4_cmd:.3f}m J5={j5_cmd:.3f}m'
            })
            return

        self.get_logger().info(
            f'   joints: J3={j3_cmd:.4f}rad  J4={j4_cmd:.4f}m  '
            f'J5={j5_cmd:.4f}m {"reachable" if reachable else "NOT reachable"}')

        # ── Step 4: Animate the pick sequence via timers ──
        self._execute_pick_sequence(
            j3_cmd, j4_cmd, j5_cmd,
            cam_x, cam_y, cam_z, ax, ay, az, r, theta, phi, reachable)

    # ── Pick animation helpers ──

    def _execute_pick_sequence(self, j3, j4, j5, cam_x, cam_y, cam_z,
                               ax, ay, az, r, theta, phi, reachable):
        """Send joints one at a time with timer-based delays (non-blocking)."""
        steps = [
            (0.0,  'J4 lateral',  'joint4', j4),
            (0.8,  'J3 tilt',     'joint3', j3),
            (1.6,  'J5 extend',   'joint5', j5),
            (3.0,  'J5 retract',  'joint5', 0.0),
            (3.8,  'J3 home',     'joint3', 0.0),
            (4.6,  'J4 home',     'joint4', 0.0),
        ]

        pubs = {
            'joint3': self.j3_cmd_pub,
            'joint4': self.j4_cmd_pub,
            'joint5': self.j5_cmd_pub,
        }

        for delay, label, joint_name, value in steps:
            self.create_timer(
                delay + 0.01,
                self._make_one_shot_joint(pubs[joint_name], joint_name, value, label),
            )

        # Final callback: send response and clear pick flag
        def finish():
            self.pick_in_progress = False
            self.get_logger().info('Pick sequence complete — arm returned home')
            self.send_response({
                'action': 'pick_cotton',
                'success': True,
                'arm_x': round(ax, 4), 'arm_y': round(ay, 4), 'arm_z': round(az, 4),
                'r': round(r, 4), 'theta': round(theta, 4),
                'phi_deg': round(math.degrees(phi), 2),
                'j3_cmd': round(j3, 4), 'j4_cmd': round(j4, 4),
                'j5_cmd': round(j5, 4),
                'reachable': reachable,
                'message': 'Pick complete — arm homed' if reachable else
                           'Pick attempted (may be out of reach) — arm homed'
            })
        self.create_timer(5.5, self._make_one_shot(finish))

    def _make_one_shot_joint(self, pub, joint_name, value, label):
        """Return a callback that fires once: publish a joint command."""
        fired = [False]
        def cb():
            if fired[0]:
                return
            fired[0] = True
            msg = Float64()
            msg.data = float(value)
            pub.publish(msg)
            self.joint_positions[joint_name] = value
            self.get_logger().info(f'   {label}: {joint_name}={value:.4f}')
        return cb

    @staticmethod
    def _make_one_shot(fn):
        """Wrap fn so it only fires once from a repeating timer."""
        fired = [False]
        def cb():
            if fired[0]:
                return
            fired[0] = True
            fn()
        return cb

    def camera_to_yanthra_fk(self, cam_x, cam_y, cam_z, j4_pos=0.0):
        """Transform a point from camera_link to yanthra_link.
        
        IMPORTANT: The camera is fixed to yanthra_link, which is fixed to link3.
        Link3 is connected to link4 via joint3 (revolute), and link4 moves via joint4 (prismatic Y).
        When calculating arm frame coordinates, we need the position RELATIVE to yanthra_link,
        but when J4 is offset during scanning, the detected Y coordinate needs adjustment.
        
        The physical robot's TF automatically accounts for this, but we need to do it manually.
        
        Args:
            cam_x, cam_y, cam_z: point in camera_link frame (as seen when J4=j4_pos)
            j4_pos: joint4 position when cotton was detected (meters, Y-axis offset)
        Returns:
            (ax, ay, az): point in yanthra_link frame
        """
        # Step 1: Camera to yanthra using fixed URDF joint transform.
        # The URDF origin describes yanthra→camera; applying it directly
        # (NOT inverted) reproduces the real arm's C++ tf2 pipeline.
        T_cam_to_arm = self._tf_origin(
            (0.016845, 0.100461, -0.077129), (1.5708, 0.785398, 0))
        pt = T_cam_to_arm @ np.array([cam_x, cam_y, cam_z, 1.0])
        
        # Step 2: Adjust for J4 scan offset
        # When J4 is at position j4_pos, the detected Y coordinate in yanthra_link frame
        # needs to include this offset to get the absolute Y position
        ax, ay, az = float(pt[0]), float(pt[1]), float(pt[2])
        ay_absolute = ay + j4_pos  # Add J4 offset to get absolute Y position
        
        return (ax, ay_absolute, az)

    # ──────────────────────────────────────────────────────────────────
    # Forward kinematics (direct computation — no TF dependency)
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _tf_translation(x, y, z):
        """4x4 homogeneous translation matrix."""
        T = np.eye(4)
        T[0, 3] = x
        T[1, 3] = y
        T[2, 3] = z
        return T

    @staticmethod
    def _tf_rpy(roll, pitch, yaw):
        """4x4 homogeneous rotation from roll-pitch-yaw (URDF convention)."""
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        R = np.eye(4)
        R[0, 0] = cy * cp
        R[0, 1] = cy * sp * sr - sy * cr
        R[0, 2] = cy * sp * cr + sy * sr
        R[1, 0] = sy * cp
        R[1, 1] = sy * sp * sr + cy * cr
        R[1, 2] = sy * sp * cr - cy * sr
        R[2, 0] = -sp
        R[2, 1] = cp * sr
        R[2, 2] = cp * cr
        return R

    @staticmethod
    def _tf_origin(xyz, rpy):
        """Combined translation + rotation from URDF <origin>.
        
        URDF convention: The transform is applied as rotation first, then translation.
        So the final matrix is: T * R (translation matrix times rotation matrix).
        """
        R = ArmSimBridge._tf_rpy(*rpy)
        T = ArmSimBridge._tf_translation(*xyz)
        # Apply rotation first, then translation: result = T * R
        result = T @ R
        return result

    @staticmethod
    def _tf_prismatic(axis, value):
        """4x4 transform for prismatic joint displacement."""
        return ArmSimBridge._tf_translation(
            axis[0] * value, axis[1] * value, axis[2] * value
        )

    @staticmethod
    def _tf_revolute(axis, value):
        """4x4 transform for revolute joint (Rodrigues' rotation)."""
        ax, ay, az = axis
        c, s = math.cos(value), math.sin(value)
        t = 1 - c
        R = np.eye(4)
        R[0, 0] = t * ax * ax + c
        R[0, 1] = t * ax * ay - az * s
        R[0, 2] = t * ax * az + ay * s
        R[1, 0] = t * ax * ay + az * s
        R[1, 1] = t * ay * ay + c
        R[1, 2] = t * ay * az - ax * s
        R[2, 0] = t * ax * az - ay * s
        R[2, 1] = t * ay * az + ax * s
        R[2, 2] = t * az * az + c
        return R

    def camera_to_world_fk(self, cam_x, cam_y, cam_z, joints):
        """
        Compute world position of a point in camera_link frame
        using forward kinematics from the URDF chain.

        Chain: world → base_link → link2 → link4 → link3 → yanthra_link → camera_link

        Args:
            cam_x, cam_y, cam_z: point in camera_link frame
            joints: dict {'joint2': val, 'joint3': val, 'joint4': val}
        Returns:
            (wx, wy, wz) in world frame
        """
        j2 = joints.get('joint2', 0.0)
        j3 = joints.get('joint3', 0.0)
        j4 = joints.get('joint4', 0.0)

        # world → base_link (static: spawn at z=0.1)
        T = self._tf_translation(0, 0, 0.1)

        # base_link → link2 via joint2 (prismatic Z)
        # <origin xyz="0 0 0.45922" rpy="0 0 0" />  <axis xyz="0 0 1" />
        T = T @ self._tf_origin((0, 0, 0.45922), (0, 0, 0))
        T = T @ self._tf_prismatic((0, 0, 1), j2)

        # link2 → link4 via joint4 (prismatic Y)
        # <origin xyz="0 0.33411 0" rpy="0 0 0" />  <axis xyz="0 1 0" />
        T = T @ self._tf_origin((0, 0.33411, 0), (0, 0, 0))
        T = T @ self._tf_prismatic((0, 1, 0), j4)

        # link4 → link3 via joint3 (revolute)
        # <origin xyz="-0.0675 0.042 -0.127" rpy="0 0.0063952 0" />  <axis xyz="0 -1 0" />
        T = T @ self._tf_origin((-0.0675, 0.042, -0.127), (0, 0.0063952, 0))
        T = T @ self._tf_revolute((0, -1, 0), j3)

        # link3 → yanthra_link via yantra_joint (fixed)
        # <origin xyz="0 -0.082 0" rpy="0 0 0" />
        T = T @ self._tf_origin((0, -0.082, 0), (0, 0, 0))

        # yanthra_link → camera_link via camera_link_joint (fixed)
        # <origin xyz="0.016845 0.100461 -0.077129" rpy="1.5708 0.785398 0" />
        T = T @ self._tf_origin((0.016845, 0.100461, -0.077129), (1.5708, 0.785398, 0))

        # Transform the camera-frame point to world
        world_pt = T @ np.array([cam_x, cam_y, cam_z, 1.0])
        return (float(world_pt[0]), float(world_pt[1]), float(world_pt[2]))

    # ──────────────────────────────────────────────────────────────────
    # Joint state management
    # ──────────────────────────────────────────────────────────────────

    def _joint_state_cb(self, msg):
        """Track joint positions from Gazebo (via ros_gz_bridge → /joint_states)."""
        for i, name in enumerate(msg.name):
            if name in self.joint_positions and i < len(msg.position):
                self.joint_positions[name] = msg.position[i]

    # ──────────────────────────────────────────────────────────────────
    # Joint command filters with physical limits
    # ──────────────────────────────────────────────────────────────────

    def _clamp_and_publish(self, joint_name, value, publisher):
        """Clamp joint value to physical limits and publish."""
        limits = self.joint_limits[joint_name]
        clamped = max(limits['min'], min(limits['max'], value))
        
        if abs(clamped - value) > 0.001:
            self.get_logger().warn(
                f'⚠️  {joint_name}: {value:.4f}{limits["unit"]} exceeds limits '
                f'[{limits["min"]}, {limits["max"]}] → clamped to {clamped:.4f}{limits["unit"]}')
        
        msg = Float64()
        msg.data = clamped
        publisher.publish(msg)

    def _j3_ui_cb(self, msg):
        """Joint3 UI command → clamp → Gazebo."""
        self._clamp_and_publish('joint3', msg.data, self.j3_cmd_pub)

    def _j4_ui_cb(self, msg):
        """Joint4 UI command → clamp → Gazebo."""
        self._clamp_and_publish('joint4', msg.data, self.j4_cmd_pub)

    def _j5_ui_cb(self, msg):
        """Joint5 UI command → clamp → Gazebo."""
        self._clamp_and_publish('joint5', msg.data, self.j5_cmd_pub)

    # ──────────────────────────────────────────────────────────────────
    # TF helpers
    # ──────────────────────────────────────────────────────────────────

    def transform_camera_to_world(self, cx, cy, cz):
        """Transform camera-frame point to world frame. Returns (wx, wy, wz) or None."""
        return self.transform_camera_to_frame(cx, cy, cz, 'world')

    def transform_camera_to_frame(self, cx, cy, cz, target_frame):
        """Transform camera-frame point to target frame. Returns (x, y, z) or None."""
        pt = PointStamped()
        pt.header.frame_id = 'camera_link'
        # Use time=0 to get the LATEST available transform.
        # This avoids sim_time vs wall_time mismatch when use_sim_time
        # is not set or clock sources differ.
        pt.header.stamp = Time(seconds=0).to_msg()
        pt.point.x = cx
        pt.point.y = cy
        pt.point.z = cz

        try:
            result = self.tf_buffer.transform(pt, target_frame, Duration(seconds=5.0))
            return (result.point.x, result.point.y, result.point.z)
        except Exception as e:
            # Diagnostic: list available frames to help debug
            frames = self.tf_buffer.all_frames_as_string()
            self.get_logger().error(
                f'❌ TF camera_link→{target_frame}: {e}\n'
                f'   Available frames:\n{frames}'
            )
            return None

    # ──────────────────────────────────────────────────────────────────
    # Gazebo helpers
    # ──────────────────────────────────────────────────────────────────

    def _gz_spawn_model(self, name, sdf, x, y, z):
        """Spawn an SDF model in Gazebo via gz service."""
        sdf_escaped = sdf.replace('"', '\\"').replace('\n', ' ')
        req = (
            f'sdf: "{sdf_escaped}" '
            f'pose: {{position: {{x: {x}, y: {y}, z: {z}}}}} '
            f'name: "{name}"'
        )
        cmd = [
            'gz', 'service', '-s', '/world/empty/create',
            '--reqtype', 'gz.msgs.EntityFactory',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '5000',
            '--req', req
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.get_logger().info(f'✅ Spawned "{name}" at ({x:.3f}, {y:.3f}, {z:.3f})')
                return True
            else:
                self.get_logger().error(f'❌ gz spawn failed: {result.stderr.strip()}')
                return False
        except Exception as e:
            self.get_logger().error(f'❌ gz spawn exception: {e}')
            return False

    def _gz_remove_model(self, name):
        """Remove a model from Gazebo via gz service."""
        req = f'type: MODEL, name: "{name}"'
        cmd = [
            'gz', 'service', '-s', '/world/empty/remove',
            '--reqtype', 'gz.msgs.Entity',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '5000',
            '--req', req
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.get_logger().info(f'🗑️ Removed "{name}"')
                return True
            else:
                self.get_logger().warn(f'⚠️ gz remove: {result.stderr.strip()}')
                return False
        except Exception as e:
            self.get_logger().warn(f'⚠️ gz remove exception: {e}')
            return False


def main():
    rclpy.init()
    node = ArmSimBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
