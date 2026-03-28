#!/usr/bin/env python3
"""
FK chain math for camera-to-world and camera-to-arm transforms.

Pure functions -- no ROS2 dependency. Used by testing_backend.py for
cotton placement, pick animation, and compute approach.
"""

import math
import numpy as np


def tf_translation(x: float, y: float, z: float) -> np.ndarray:
    """Pure translation 4x4 matrix."""
    T = np.eye(4)
    T[0, 3] = x
    T[1, 3] = y
    T[2, 3] = z
    return T


def tf_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Rotation matrix from URDF RPY (roll-pitch-yaw, extrinsic XYZ)."""
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


def tf_origin(xyz: tuple, rpy: tuple) -> np.ndarray:
    """Combined translation + rotation (URDF <origin> element)."""
    return tf_translation(*xyz) @ tf_rpy(*rpy)


def tf_prismatic(axis: tuple, value: float) -> np.ndarray:
    """Prismatic joint displacement along axis * value."""
    T = np.eye(4)
    T[0, 3] = axis[0] * value
    T[1, 3] = axis[1] * value
    T[2, 3] = axis[2] * value
    return T


def tf_revolute(axis: tuple, angle: float) -> np.ndarray:
    """Revolute joint rotation via Rodrigues' formula."""
    ax = np.array(axis[:3], dtype=float)
    ax = ax / np.linalg.norm(ax)
    c, s = math.cos(angle), math.sin(angle)
    K = np.array([
        [0, -ax[2], ax[1]],
        [ax[2], 0, -ax[0]],
        [-ax[1], ax[0], 0],
    ])
    R3 = np.eye(3) + s * K + (1 - c) * (K @ K)
    T = np.eye(4)
    T[:3, :3] = R3
    return T


# ---------------------------------------------------------------------------
# Per-arm FK configuration
# ---------------------------------------------------------------------------

# Vehicle spawn pose: x=0, y=0, z=1.0, Roll=pi/2, Pitch=0, Yaw=0
VEHICLE_SPAWN_Z = 1.0
VEHICLE_SPAWN_ROLL = math.pi / 2

# Camera link transform (fixed, from yanthra_move URDF)
CAMERA_LINK_XYZ = (0.016845, 0.100461, -0.077129)
CAMERA_LINK_RPY = (1.5708, 0.785398, 0.0)

# Internal arm chain origins (identical for all arms)
_ARM_J4_ORIGIN_XYZ = (0.0, 0.33411, 0.0)
_ARM_J4_ORIGIN_RPY = (0.0, 0.0, 0.0)
_ARM_J4_AXIS = (0, 1, 0)

_ARM_J3_ORIGIN_XYZ = (-0.069574, 0.009556, -0.12761)
_ARM_J3_ORIGIN_RPY = (0.0, 0.006395, 0.0)
_ARM_J3_AXIS = (0, -1, 0)

_ARM_YANTHRA_ORIGIN_XYZ = (0.0, -0.082, 0.0)
_ARM_YANTHRA_ORIGIN_RPY = (0.0, 0.0, 0.0)

ARM_CONFIGS = {
    'arm1': {
        'base_xyz': (0.338848, 0.394908, 0.0),
        'base_rpy': (-1.521774, -1.550976, -0.049013),
        'j3_topic': '/joint3_cmd',
        'j4_topic': '/joint4_cmd',
        'j5_topic': '/joint5_cmd',
        'yanthra_link': 'arm_yanthra_link',
    },
    'arm2': {
        'base_xyz': (0.964599, 0.394908, 1.807259),
        'base_rpy': (-1.675779, 1.561533, -0.087054),
        'j3_topic': '/joint3_copy_cmd',
        'j4_topic': '/joint4_copy_cmd',
        'j5_topic': '/joint5_copy_cmd',
        'yanthra_link': 'arm_yanthra_link_copy',
    },
    'arm3': {
        'base_xyz': (0.355298, 0.394908, 0.913409),
        'base_rpy': (-1.521774, -1.550976, -0.049013),
        'j3_topic': '/arm_joint3_copy1_cmd',
        'j4_topic': '/arm_joint4_copy1_cmd',
        'j5_topic': '/arm_joint5_copy1_cmd',
        'yanthra_link': 'arm_yanthra_link_copy1',
    },
}

# Joint limits (identical for all arms)
J3_MIN, J3_MAX = -0.9, 0.0       # rad
J4_MIN, J4_MAX = -0.250, 0.350   # m
J5_MIN, J5_MAX = 0.0, 0.450      # m

HARDWARE_OFFSET = 0.320  # m, distance from yanthra_link to J5 origin


def camera_to_world_fk(
    cam_x: float, cam_y: float, cam_z: float,
    j3: float, j4: float,
    arm_config: dict,
) -> tuple[float, float, float]:
    """Transform a camera-frame point to Gazebo world frame via explicit FK.

    Used for spawning cotton markers (Gazebo hasn't moved yet, so we can't
    use live TF -- we must compute the full chain from known joint values).

    Args:
        cam_x, cam_y, cam_z: point in camera_link frame
        j3: current arm_joint3 value (rad)
        j4: current arm_joint4 value (m)
        arm_config: dict from ARM_CONFIGS with 'base_xyz' and 'base_rpy'

    Returns:
        (wx, wy, wz) in Gazebo world frame
    """
    # World -> base-v1 (vehicle spawn pose: z=1.0, Roll=pi/2)
    T = tf_origin((0, 0, VEHICLE_SPAWN_Z), (VEHICLE_SPAWN_ROLL, 0, 0))

    # base-v1 -> arm_link2 (fixed base mount, per-arm)
    T = T @ tf_origin(arm_config['base_xyz'], arm_config['base_rpy'])

    # arm_link2 -> arm_link4 via arm_joint4 (prismatic Y)
    T = T @ tf_origin(_ARM_J4_ORIGIN_XYZ, _ARM_J4_ORIGIN_RPY)
    T = T @ tf_prismatic(_ARM_J4_AXIS, j4)

    # arm_link4 -> arm_link3 via arm_joint3 (revolute -Y)
    T = T @ tf_origin(_ARM_J3_ORIGIN_XYZ, _ARM_J3_ORIGIN_RPY)
    T = T @ tf_revolute(_ARM_J3_AXIS, j3)

    # arm_link3 -> arm_yanthra_link (fixed)
    T = T @ tf_origin(_ARM_YANTHRA_ORIGIN_XYZ, _ARM_YANTHRA_ORIGIN_RPY)

    # arm_yanthra_link -> camera_link (fixed)
    T = T @ tf_origin(CAMERA_LINK_XYZ, CAMERA_LINK_RPY)

    # Transform camera-frame point to world
    world_pt = T @ np.array([cam_x, cam_y, cam_z, 1.0])
    return (float(world_pt[0]), float(world_pt[1]), float(world_pt[2]))


# Camera-link joint transform from the URDF.
# The URDF origin describes the yanthra→camera transform, and applying it
# directly (NOT inverted) reproduces the real arm's C++ tf2 pipeline output.
# See test_camera_to_arm_matches_real_arm_log_data for numerical proof.
_T_CAM_TO_ARM = tf_origin(CAMERA_LINK_XYZ, CAMERA_LINK_RPY)


def camera_to_arm(
    cam_x: float, cam_y: float, cam_z: float,
    j4_pos: float,
) -> tuple[float, float, float]:
    """Transform camera-frame point to arm (yanthra_link) frame.

    Used for polar decomposition during pick/compute. Adds j4_pos to
    the Y coordinate to get absolute lateral position.

    Args:
        cam_x, cam_y, cam_z: point in camera_link frame
        j4_pos: current arm_joint4 value (m) -- added to arm Y

    Returns:
        (ax, ay_absolute, az) in yanthra_link frame
    """
    pt = _T_CAM_TO_ARM @ np.array([cam_x, cam_y, cam_z, 1.0])
    ax, ay, az = float(pt[0]), float(pt[1]), float(pt[2])
    ay_absolute = ay + j4_pos
    return (ax, ay_absolute, az)


def polar_decompose(
    ax: float, ay: float, az: float,
) -> dict:
    """Convert arm-frame coordinates to polar form and joint commands.

    Matches the decomposition in yanthra_move/arm_sim_bridge.py and
    motion_controller.cpp.

    Args:
        ax, ay, az: point in yanthra_link (arm) frame

    Returns:
        dict with keys: r, theta, phi, j3, j4, j5, reachable
    """
    r = math.sqrt(ax * ax + az * az)
    theta = ay  # direct passthrough to J4
    denom = math.sqrt(az * az + ax * ax)  # same as r
    phi = math.asin(az / denom) if denom > 1e-6 else 0.0

    j3 = phi          # radians
    j4 = theta         # meters
    j5 = r - HARDWARE_OFFSET  # meters

    reachable = (
        J3_MIN <= j3 <= J3_MAX
        and J4_MIN <= j4 <= J4_MAX
        and J5_MIN <= j5 <= J5_MAX
        and r > 0.1
    )

    return {
        'r': r, 'theta': theta, 'phi': phi,
        'j3': j3, 'j4': j4, 'j5': j5,
        'reachable': reachable,
    }


# Phi compensation constants
PHI_ZONE1_MAX_DEG = 50.5
PHI_ZONE2_MAX_DEG = 60.0
PHI_ZONE1_OFFSET = 0.014    # rotations (+5 deg)
PHI_ZONE2_OFFSET = 0.0      # rotations (no change)
PHI_ZONE3_OFFSET = -0.014   # rotations (-5 deg)
PHI_L5_SCALE = 0.5
JOINT5_MAX = 0.450           # m, for L5 normalization


def phi_compensation(j3: float, j5: float) -> float:
    """Apply phi zone-based compensation to J3.

    Three zones based on abs(degrees(j3)):
      Zone1 (<=50.5 deg): +0.014 rotations
      Zone2 (<=60.0 deg): 0.0 rotations
      Zone3 (>60.0 deg):  -0.014 rotations

    The base offset is scaled by L5 extension:
      l5_scale = 1.0 + PHI_L5_SCALE * (j5 / JOINT5_MAX)

    Args:
        j3: current J3 value in radians (= phi from polar decomposition)
        j5: current J5 value in meters

    Returns:
        compensated J3 value in radians
    """
    phi_deg = abs(math.degrees(j3))

    if phi_deg <= PHI_ZONE1_MAX_DEG:
        base_offset = PHI_ZONE1_OFFSET
    elif phi_deg <= PHI_ZONE2_MAX_DEG:
        base_offset = PHI_ZONE2_OFFSET
    else:
        base_offset = PHI_ZONE3_OFFSET

    l5_normalized = max(0.0, j5) / JOINT5_MAX
    l5_scale_factor = 1.0 + PHI_L5_SCALE * l5_normalized
    compensation_rot = base_offset * l5_scale_factor
    compensation_rad = compensation_rot * 2.0 * math.pi

    return j3 + compensation_rad
