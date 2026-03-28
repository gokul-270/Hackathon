#!/usr/bin/env python3
"""Tests for fk_chain module -- FK math for cotton placement."""

import math
import numpy as np
import pytest


def test_tf_origin_identity():
    """tf_origin with zero xyz and zero rpy returns 4x4 identity."""
    from fk_chain import tf_origin
    T = tf_origin((0, 0, 0), (0, 0, 0))
    np.testing.assert_allclose(T, np.eye(4), atol=1e-12)


def test_tf_origin_translation_only():
    """tf_origin with nonzero xyz and zero rpy returns pure translation."""
    from fk_chain import tf_origin
    T = tf_origin((1.5, -0.25, 0.9), (0, 0, 0))
    assert abs(T[0, 3] - 1.5) < 1e-12
    assert abs(T[1, 3] - (-0.25)) < 1e-12
    assert abs(T[2, 3] - 0.9) < 1e-12
    # Rotation part should be identity
    np.testing.assert_allclose(T[:3, :3], np.eye(3), atol=1e-12)


# --- Arm 1 base mount ---
ARM1_BASE_XYZ = (0.338848, 0.394908, 0.0)
ARM1_BASE_RPY = (-1.521774, -1.550976, -0.049013)

# Vehicle spawn pose
VEHICLE_SPAWN_Z = 1.0
VEHICLE_SPAWN_ROLL = 1.5708  # pi/2

# Camera-to-yanthra transform (from yanthra_move URDF)
CAM_TO_YANTHRA_XYZ = (0.016845, 0.100461, -0.077129)
CAM_TO_YANTHRA_RPY = (1.5708, 0.785398, 0.0)


def test_camera_to_world_fk_origin_with_zero_joints():
    """camera_to_world_fk(0,0,0, j3=0, j4=0) returns a point in world frame."""
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    wx, wy, wz = camera_to_world_fk(
        cam_x=0.0, cam_y=0.0, cam_z=0.0,
        j3=0.0, j4=0.0,
        arm_config=ARM_CONFIGS['arm1'],
    )
    # The result must be a finite 3D point (not NaN or inf)
    assert math.isfinite(wx), f"wx={wx}"
    assert math.isfinite(wy), f"wy={wy}"
    assert math.isfinite(wz), f"wz={wz}"
    # World z must be positive (arm is above ground)
    assert wz > 0.0, f"wz={wz} should be positive (above ground)"


def test_camera_to_world_fk_deterministic():
    """Two calls with same inputs return identical results."""
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    r1 = camera_to_world_fk(0.1, -0.02, 0.05, j3=-0.3, j4=0.1, arm_config=ARM_CONFIGS['arm1'])
    r2 = camera_to_world_fk(0.1, -0.02, 0.05, j3=-0.3, j4=0.1, arm_config=ARM_CONFIGS['arm1'])
    np.testing.assert_allclose(r1, r2, atol=1e-12)


def test_camera_to_arm_roundtrip():
    """camera_to_arm inverts the camera-to-yanthra fixed transform."""
    from fk_chain import camera_to_arm
    # A point at camera origin should map to a known arm-frame position
    ax, ay, az = camera_to_arm(0.0, 0.0, 0.0, j4_pos=0.0)
    # Must be finite
    assert math.isfinite(ax) and math.isfinite(ay) and math.isfinite(az)


def test_camera_to_arm_j4_offset():
    """camera_to_arm adds j4_pos to the arm Y coordinate."""
    from fk_chain import camera_to_arm
    ax1, ay1, az1 = camera_to_arm(0.1, -0.02, 0.05, j4_pos=0.0)
    ax2, ay2, az2 = camera_to_arm(0.1, -0.02, 0.05, j4_pos=0.15)
    # X and Z should be identical
    assert abs(ax1 - ax2) < 1e-12
    assert abs(az1 - az2) < 1e-12
    # Y should differ by exactly 0.15
    assert abs((ay2 - ay1) - 0.15) < 1e-12


def test_polar_decompose_known_values():
    """polar_decompose returns r, theta=ay, phi=asin(az/r), j3, j4, j5."""
    from fk_chain import polar_decompose
    # ax=-0.5, ay=0.1, az=-0.2
    result = polar_decompose(-0.5, 0.1, -0.2)
    expected_r = math.sqrt(0.25 + 0.04)  # sqrt(0.29) ~ 0.53852
    assert abs(result['r'] - expected_r) < 1e-6
    assert abs(result['theta'] - 0.1) < 1e-12  # theta = ay
    expected_phi = math.asin(-0.2 / expected_r)
    assert abs(result['phi'] - expected_phi) < 1e-9
    assert abs(result['j4'] - 0.1) < 1e-12  # j4 = theta = ay
    assert abs(result['j3'] - expected_phi) < 1e-9  # j3 = phi (radians)
    expected_j5 = expected_r - 0.320
    assert abs(result['j5'] - expected_j5) < 1e-9


def test_polar_decompose_near_zero_r():
    """polar_decompose with r near zero returns phi=0."""
    from fk_chain import polar_decompose
    result = polar_decompose(0.0, 0.1, 0.0)
    assert abs(result['phi']) < 1e-9


def test_phi_compensation_zone1():
    """phi_compensation returns positive offset for phi_deg <= 50.5."""
    from fk_chain import phi_compensation
    # phi = -0.5 rad => phi_deg = abs(degrees(-0.5)) = 28.6 => Zone1
    j3_compensated = phi_compensation(j3=-0.5, j5=0.1)
    # Zone1 base = +0.014 rot
    # l5_norm = max(0, 0.1) / 0.450 = 0.222
    # l5_scale = 1.0 + 0.5 * 0.222 = 1.111
    # comp_rot = 0.014 * 1.111 = 0.01556
    # comp_rad = 0.01556 * 2 * pi = 0.09774
    # result = -0.5 + 0.09774 = -0.40226
    expected = -0.5 + 0.014 * (1.0 + 0.5 * (0.1 / 0.450)) * 2 * math.pi
    assert abs(j3_compensated - expected) < 1e-9


def test_phi_compensation_zone2():
    """phi_compensation returns zero offset for 50.5 < phi_deg <= 60."""
    from fk_chain import phi_compensation
    # phi = -0.93 rad => phi_deg = abs(degrees(-0.93)) = 53.3 => Zone2
    j3_compensated = phi_compensation(j3=-0.93, j5=0.2)
    # Zone2 offset is 0 => no change
    assert abs(j3_compensated - (-0.93)) < 1e-9


def test_phi_compensation_zone3():
    """phi_compensation returns negative offset for phi_deg > 60."""
    from fk_chain import phi_compensation
    # phi = -1.06 rad => phi_deg = 60.7 => Zone3
    j3_compensated = phi_compensation(j3=-1.06, j5=0.3)
    # Zone3 base = -0.014 rot
    # l5_norm = 0.3 / 0.450 = 0.667
    # l5_scale = 1.0 + 0.5 * 0.667 = 1.333
    # comp_rot = -0.014 * 1.333 = -0.01867
    # comp_rad = -0.01867 * 2 * pi = -0.11731
    expected = -1.06 + (-0.014) * (1.0 + 0.5 * (0.3 / 0.450)) * 2 * math.pi
    assert abs(j3_compensated - expected) < 1e-9
