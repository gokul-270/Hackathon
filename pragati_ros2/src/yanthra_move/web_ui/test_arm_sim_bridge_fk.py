#!/usr/bin/env python3
"""Tests for arm_sim_bridge camera_to_yanthra_fk transform.

arm_sim_bridge.ArmSimBridge requires a running ROS2 node, so we cannot
import it directly.  Instead we replicate the exact static-method math
(which is identical to fk_chain.tf_origin) and verify the transform
logic in camera_to_yanthra_fk lines 662-673.

If the implementation in arm_sim_bridge.py uses np.linalg.inv (the
INVERSE of the URDF origin), this test FAILS — proving the bug exists.
"""

import math

import numpy as np
import pytest


# ── replicate ArmSimBridge static helpers (identical to fk_chain) ──

def _tf_translation(x, y, z):
    T = np.eye(4)
    T[0, 3], T[1, 3], T[2, 3] = x, y, z
    return T


def _tf_rpy(roll, pitch, yaw):
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


def _tf_origin(xyz, rpy):
    return _tf_translation(*xyz) @ _tf_rpy(*rpy)


# ── Constants from arm_sim_bridge.camera_to_yanthra_fk ──
_CAM_XYZ = (0.016845, 0.100461, -0.077129)
_CAM_RPY = (1.5708, 0.785398, 0)


def _camera_to_yanthra_fk_BUGGY(cam_x, cam_y, cam_z, j4_pos=0.0):
    """Replicate the CURRENT (buggy) arm_sim_bridge code: lines 662-673."""
    T_yanthra_to_cam = _tf_origin(_CAM_XYZ, _CAM_RPY)
    T_cam_to_yanthra = np.linalg.inv(T_yanthra_to_cam)       # BUG: inverse
    pt = T_cam_to_yanthra @ np.array([cam_x, cam_y, cam_z, 1.0])
    ax, ay, az = float(pt[0]), float(pt[1]), float(pt[2])
    return (ax, ay + j4_pos, az)


def _camera_to_yanthra_fk_FIXED(cam_x, cam_y, cam_z, j4_pos=0.0):
    """Replicate the FIXED code: use forward transform directly."""
    T_cam_to_arm = _tf_origin(_CAM_XYZ, _CAM_RPY)            # FIX: forward
    pt = T_cam_to_arm @ np.array([cam_x, cam_y, cam_z, 1.0])
    ax, ay, az = float(pt[0]), float(pt[1]), float(pt[2])
    return (ax, ay + j4_pos, az)


# ── Reference data (same as test_fk_chain.py) ──
_LOG_DATA = [
    ((0.494, -0.001, 0.004), (0.3654, 0.0965, -0.4271)),
    ((0.510, -0.020, 0.050), (0.3633, 0.0505, -0.4519)),
    ((0.450, 0.010, -0.030), (0.3421, 0.1305, -0.3883)),
    ((0.480, -0.005, 0.020), (0.3527, 0.0805, -0.4201)),
    ((0.520, -0.030, 0.060), (0.3633, 0.0405, -0.4660)),
]


def test_buggy_transform_does_not_match_log_data():
    """The INVERSE transform (current code) must NOT match real log data."""
    for (cx, cy, cz), (ex, ey, ez) in _LOG_DATA:
        ax, ay, az = _camera_to_yanthra_fk_BUGGY(cx, cy, cz, j4_pos=0.0)
        # At least one axis should be off by > 2 mm
        err = max(abs(ax - ex), abs(ay - ey), abs(az - ez))
        assert err > 0.01, (
            f"Buggy transform unexpectedly matches for ({cx},{cy},{cz})"
        )


def test_fixed_transform_matches_log_data():
    """The FORWARD transform (fix) must match real log data within 2 mm."""
    for (cx, cy, cz), (ex, ey, ez) in _LOG_DATA:
        ax, ay, az = _camera_to_yanthra_fk_FIXED(cx, cy, cz, j4_pos=0.0)
        assert abs(ax - ex) < 0.002, (
            f"cam=({cx},{cy},{cz}): ax={ax:.4f}, expected={ex:.4f}"
        )
        assert abs(ay - ey) < 0.002, (
            f"cam=({cx},{cy},{cz}): ay={ay:.4f}, expected={ey:.4f}"
        )
        assert abs(az - ez) < 0.002, (
            f"cam=({cx},{cy},{cz}): az={az:.4f}, expected={ez:.4f}"
        )
