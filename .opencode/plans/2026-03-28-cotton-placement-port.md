# Cotton Placement Port: yanthra_move to vehicle_arm_sim

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the camera-to-arm cotton placement system (spawn cotton, animated pick sequence, compute approach preview, phi compensation) from `yanthra_move/web_ui/arm_sim_bridge.py` into `vehicle_arm_sim/web_ui/testing_backend.py` and `testing_ui.js`, using FastAPI endpoints and per-arm support for 3 arms.

**Architecture:** New FastAPI endpoints in `testing_backend.py` handle cotton spawn (via FK chain), pick animation (via ROS2 joint publishers + timer thread), and compute approach (polar decomposition). The frontend `testing_ui.js` gets new UI panels and calls these endpoints via `fetch()`. The URDF is modified to move `camera_link` onto `arm_yanthra_link` (Arm 1 only). A new Python module `fk_chain.py` encapsulates all FK math for testability.

**Tech Stack:** Python 3 (FastAPI, numpy, rclpy), JavaScript (vanilla, ROSLIB), Node.js test runner, pytest, Playwright, Gazebo `gz` CLI.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `web_ui/fk_chain.py` | **CREATE** | FK math: transform helpers, camera-to-world FK, camera-to-arm inverse, polar decomposition, phi compensation. Pure functions, no ROS2 dependency. |
| `web_ui/test_fk_chain.py` | **CREATE** | pytest unit tests for all FK math. |
| `web_ui/testing_backend.py` | **MODIFY** | Add cotton endpoints: `/api/cotton/spawn`, `/api/cotton/remove`, `/api/cotton/compute`, `/api/cotton/pick`. Add arm FK config, pick animation thread. |
| `web_ui/test_cam_markers_backend.py` | **MODIFY** | Add tests for new cotton endpoints. |
| `web_ui/tests/cam_to_joint_shim.js` | **MODIFY** | Add phi compensation function export. |
| `web_ui/tests/test_cam_to_joint.js` | **MODIFY** | Add phi compensation unit tests. |
| `web_ui/testing_ui.js` | **MODIFY** | Add cotton spawn/pick/compute UI calls, animated pick button, compute approach panel, compensation toggles. |
| `web_ui/testing_ui.html` | **MODIFY** | Add cotton placement UI sections (spawn form, compute panel, pick button, compensation toggles). |
| `web_ui/testing_ui.css` | **MODIFY** | Add styles for new cotton placement sections. |
| `web_ui/tests/e2e/cotton_placement.spec.js` | **CREATE** | Playwright E2E tests for the new cotton placement UI. |
| `urdf/saved/vehicle_arm_merged.urdf` | **MODIFY** | Move `camera_link` from `base-v1` to `arm_yanthra_link`. |
| `urdf/vehicle_arm_merged.urdf` | **MODIFY** | Same URDF change (keep both copies in sync). |

**Base path for all relative paths:** `/home/sriswetha/collision_avoidance/pragati_ros2/src/vehicle_arm_sim/`

---

## Arm Configuration Reference

All 3 arms have identical internal joint chains. They differ only in base mount pose and topic names.

| Arm | Suffix | J3 Topic | J4 Topic | J5 Topic | Base Mount Joint | yanthra_link |
|-----|--------|----------|----------|----------|-----------------|--------------|
| arm1 | (none) | `/joint3_cmd` | `/joint4_cmd` | `/joint5_cmd` | `base-v1_to_arm_link2_joint` | `arm_yanthra_link` |
| arm2 | `_copy` | `/joint3_copy_cmd` | `/joint4_copy_cmd` | `/joint5_copy_cmd` | `base-v1_to_arm_link2_joint_copy` | `arm_yanthra_link_copy` |
| arm3 | `_copy1` | `/arm_joint3_copy1_cmd` | `/arm_joint4_copy1_cmd` | `/arm_joint5_copy1_cmd` | `base-v1_to_arm_link2_joint_copy1` | `arm_yanthra_link_copy1` |

### Internal FK Chain (same for all arms, substitute suffix):

```
base-v1
  -> [base-v1_to_arm_link2_joint{sfx}] FIXED  xyz=<per-arm>  rpy=<per-arm>
    -> arm_link2{sfx}
      -> [arm_joint4{sfx}] PRISMATIC(Y)  xyz=(0, 0.33411, 0)  rpy=(0,0,0)  limits=[-0.250, 0.350]
        -> arm_link4{sfx}
          -> [arm_joint3{sfx}] REVOLUTE(-Y)  xyz=(-0.069574, 0.009556, -0.12761)  rpy=(0, 0.006395, 0)  limits=[-0.9, 0.0]
            -> arm_link3{sfx}
              -> [arm_yantra_joint{sfx}] FIXED  xyz=(0, -0.082, 0)  rpy=(0,0,0)
                -> arm_yanthra_link{sfx}
```

### Base Mount Poses (per arm):

| Arm | xyz | rpy |
|-----|-----|-----|
| arm1 | `(0.338848, 0.394908, 0)` | `(-1.521774, -1.550976, -0.049013)` |
| arm2 | `(0.964599, 0.394908, 1.807259)` | `(-1.675779, 1.561533, -0.087054)` |
| arm3 | `(0.355298, 0.394908, 0.913409)` | `(-1.521774, -1.550976, -0.049013)` |

### Vehicle Spawn Pose:

`x=0, y=0, z=1.0, Roll=1.5708 (pi/2), Pitch=0, Yaw=0`

### Camera-to-Yanthra Transform (from yanthra_move URDF, to be added to vehicle_arm_sim):

`xyz=(0.016845, 0.100461, -0.077129)  rpy=(1.5708, 0.785398, 0)`

### Joint Limits (all arms):

| Joint | Min | Max | Unit |
|-------|-----|-----|------|
| J3 | -0.9 | 0.0 | rad |
| J4 | -0.250 | 0.350 | m |
| J5 | 0.0 | 0.450 | m |

### Constants:

| Name | Value | Purpose |
|------|-------|---------|
| `HARDWARE_OFFSET` | `0.320` | J5 offset for polar decomposition (m) |
| `PHI_ZONE1_MAX_DEG` | `50.5` | Zone 1 upper bound (degrees) |
| `PHI_ZONE2_MAX_DEG` | `60.0` | Zone 2 upper bound (degrees) |
| `PHI_ZONE1_OFFSET` | `0.014` | Zone 1 offset (rotations, ~+5 deg) |
| `PHI_ZONE2_OFFSET` | `0.0` | Zone 2 offset (no compensation) |
| `PHI_ZONE3_OFFSET` | `-0.014` | Zone 3 offset (rotations, ~-5 deg) |
| `PHI_L5_SCALE` | `0.5` | L5 scaling factor for phi compensation |
| `JOINT5_MAX` | `0.450` | L5 normalization max (m) |

---

## Task 1: Create FK Math Module (`fk_chain.py`)

**Files:**
- Create: `web_ui/fk_chain.py`
- Create: `web_ui/test_fk_chain.py`

This module contains all FK math as pure functions with no ROS2 dependencies. It is the core of the cotton placement system.

- [ ] **Step 1.1: Write failing test for `tf_origin` helper**

File: `web_ui/test_fk_chain.py`

```python
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
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_tf_origin_identity web_ui/test_fk_chain.py::test_tf_origin_translation_only -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fk_chain'`

- [ ] **Step 1.3: Implement transform helpers**

File: `web_ui/fk_chain.py`

```python
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
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_tf_origin_identity web_ui/test_fk_chain.py::test_tf_origin_translation_only -v`
Expected: PASS

- [ ] **Step 1.5: Write failing test for `camera_to_world_fk`**

Append to `web_ui/test_fk_chain.py`:

```python
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
```

- [ ] **Step 1.6: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_camera_to_world_fk_origin_with_zero_joints web_ui/test_fk_chain.py::test_camera_to_world_fk_deterministic -v`
Expected: FAIL with `ImportError: cannot import name 'camera_to_world_fk'`

- [ ] **Step 1.7: Implement `camera_to_world_fk` and `ARM_CONFIGS`**

Append to `web_ui/fk_chain.py`:

```python
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
```

- [ ] **Step 1.8: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_fk_chain.py -v`
Expected: All 4 tests PASS

- [ ] **Step 1.9: Write failing test for `camera_to_arm`**

Append to `web_ui/test_fk_chain.py`:

```python
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
```

- [ ] **Step 1.10: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_camera_to_arm_roundtrip web_ui/test_fk_chain.py::test_camera_to_arm_j4_offset -v`
Expected: FAIL with `ImportError: cannot import name 'camera_to_arm'`

- [ ] **Step 1.11: Implement `camera_to_arm`**

Append to `web_ui/fk_chain.py`:

```python
# Pre-compute the inverse of the camera-to-yanthra fixed transform
_T_YANTHRA_TO_CAM = tf_origin(CAMERA_LINK_XYZ, CAMERA_LINK_RPY)
_T_CAM_TO_YANTHRA = np.linalg.inv(_T_YANTHRA_TO_CAM)


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
    pt = _T_CAM_TO_YANTHRA @ np.array([cam_x, cam_y, cam_z, 1.0])
    ax, ay, az = float(pt[0]), float(pt[1]), float(pt[2])
    ay_absolute = ay + j4_pos
    return (ax, ay_absolute, az)
```

- [ ] **Step 1.12: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_fk_chain.py -v`
Expected: All 6 tests PASS

- [ ] **Step 1.13: Write failing test for `polar_decompose`**

Append to `web_ui/test_fk_chain.py`:

```python
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
```

- [ ] **Step 1.14: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_polar_decompose_known_values web_ui/test_fk_chain.py::test_polar_decompose_near_zero_r -v`
Expected: FAIL with `ImportError: cannot import name 'polar_decompose'`

- [ ] **Step 1.15: Implement `polar_decompose`**

Append to `web_ui/fk_chain.py`:

```python
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
```

- [ ] **Step 1.16: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_fk_chain.py -v`
Expected: All 8 tests PASS

- [ ] **Step 1.17: Write failing test for `phi_compensation`**

Append to `web_ui/test_fk_chain.py`:

```python
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
```

- [ ] **Step 1.18: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_phi_compensation_zone1 -v`
Expected: FAIL with `ImportError: cannot import name 'phi_compensation'`

- [ ] **Step 1.19: Implement `phi_compensation`**

Append to `web_ui/fk_chain.py`:

```python
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
```

- [ ] **Step 1.20: Run all tests to verify they pass**

Run: `python3 -m pytest web_ui/test_fk_chain.py -v`
Expected: All 11 tests PASS

- [ ] **Step 1.21: Commit**

```bash
git add web_ui/fk_chain.py web_ui/test_fk_chain.py
git commit -m "feat: add FK math module for cotton placement (fk_chain.py)"
```

---

## Task 2: Move Camera Link in URDF

**Files:**
- Modify: `urdf/saved/vehicle_arm_merged.urdf`
- Modify: `urdf/vehicle_arm_merged.urdf`

Move `camera_link` from being a child of `base-v1` to being a child of `arm_yanthra_link` (Arm 1 only), matching the yanthra_move URDF where the camera is mounted on the arm.

- [ ] **Step 2.1: Write failing test for URDF camera parent**

Append to `web_ui/test_fk_chain.py`:

```python
import xml.etree.ElementTree as ET
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent
_URDF_PATH = _PKG_DIR / "urdf" / "vehicle_arm_merged.urdf"


def test_urdf_camera_joint_parent_is_arm_yanthra_link():
    """camera_joint parent link must be arm_yanthra_link (not base-v1)."""
    tree = ET.parse(_URDF_PATH)
    root = tree.getroot()
    camera_joint = root.find(".//joint[@name='camera_joint']")
    assert camera_joint is not None, "camera_joint not found in URDF"
    parent = camera_joint.find("parent")
    assert parent is not None, "camera_joint has no <parent> element"
    assert parent.get("link") == "arm_yanthra_link", (
        f"camera_joint parent is '{parent.get('link')}', expected 'arm_yanthra_link'"
    )


def test_urdf_camera_joint_origin_matches_yanthra_move():
    """camera_joint origin must match yanthra_move values."""
    tree = ET.parse(_URDF_PATH)
    root = tree.getroot()
    camera_joint = root.find(".//joint[@name='camera_joint']")
    origin = camera_joint.find("origin")
    xyz = origin.get("xyz").split()
    rpy = origin.get("rpy").split()
    # Expected: xyz="0.016845 0.100461 -0.077129" rpy="1.5708 0.785398 0"
    assert abs(float(xyz[0]) - 0.016845) < 1e-4
    assert abs(float(xyz[1]) - 0.100461) < 1e-4
    assert abs(float(xyz[2]) - (-0.077129)) < 1e-4
    assert abs(float(rpy[0]) - 1.5708) < 1e-3
    assert abs(float(rpy[1]) - 0.785398) < 1e-3
    assert abs(float(rpy[2]) - 0.0) < 1e-3
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_urdf_camera_joint_parent_is_arm_yanthra_link -v`
Expected: FAIL with `AssertionError: camera_joint parent is 'base-v1', expected 'arm_yanthra_link'`

- [ ] **Step 2.3: Modify both URDF files**

In both `urdf/vehicle_arm_merged.urdf` and `urdf/saved/vehicle_arm_merged.urdf`, find the `camera_joint` definition and change:

**Old:**
```xml
<joint name="camera_joint" type="fixed">
    <parent link="base-v1"/>
    <child link="camera_link"/>
    <origin xyz="1.55 -0.25 0.9" rpy="-1.5707963267948966 0.0 -0.2618"/>
</joint>
```

**New:**
```xml
<joint name="camera_joint" type="fixed">
    <parent link="arm_yanthra_link"/>
    <child link="camera_link"/>
    <origin xyz="0.016845 0.100461 -0.077129" rpy="1.5708 0.785398 0"/>
</joint>
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_fk_chain.py::test_urdf_camera_joint_parent_is_arm_yanthra_link web_ui/test_fk_chain.py::test_urdf_camera_joint_origin_matches_yanthra_move -v`
Expected: PASS

- [ ] **Step 2.5: Commit**

```bash
git add urdf/vehicle_arm_merged.urdf urdf/saved/vehicle_arm_merged.urdf web_ui/test_fk_chain.py
git commit -m "fix: move camera_link from chassis to arm_yanthra_link"
```

---

## Task 3: Add Cotton Spawn Endpoint

**Files:**
- Modify: `web_ui/testing_backend.py`
- Modify: `web_ui/test_cam_markers_backend.py`

Add `POST /api/cotton/spawn` that converts camera coords to world frame via FK and spawns a cotton sphere in Gazebo.

- [ ] **Step 3.1: Write failing test for cotton spawn endpoint**

Append to `web_ui/test_cam_markers_backend.py`:

```python
# ---------------------------------------------------------------------------
# Cotton spawn endpoint tests
# ---------------------------------------------------------------------------
class TestCottonSpawn:
    def test_spawn_returns_200_with_world_coords(self, client):
        """POST /api/cotton/spawn with valid cam coords returns 200 + world position."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.1, "cam_y": -0.02, "cam_z": 0.05, "arm": "arm1", "j4_pos": 0.0},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "world_x" in body
        assert "world_y" in body
        assert "world_z" in body

    def test_spawn_calls_gz_create(self, client):
        """POST /api/cotton/spawn calls gz service create."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.1, "cam_y": -0.02, "cam_z": 0.05, "arm": "arm1", "j4_pos": 0.0},
            )
        assert mock_run.called
        call_args = " ".join(mock_run.call_args_list[-1][0][0])
        assert "create" in call_args
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonSpawn -v`
Expected: FAIL with 404 (endpoint doesn't exist)

- [ ] **Step 3.3: Implement cotton spawn endpoint**

Add to `web_ui/testing_backend.py`:

1. Import `fk_chain` at the top:
```python
from fk_chain import camera_to_world_fk, camera_to_arm, polar_decompose, phi_compensation, ARM_CONFIGS, J3_MIN, J3_MAX, J4_MIN, J4_MAX, J5_MIN, J5_MAX
```

2. Add Pydantic model:
```python
class CottonSpawnRequest(BaseModel):
    cam_x: float
    cam_y: float
    cam_z: float
    arm: str = "arm1"
    j4_pos: float = 0.0
```

3. Add state variables after `_spawned_marker_names`:
```python
_cotton_spawned: bool = False
_cotton_name: str = "cotton_target"
_last_cotton_cam: tuple[float, float, float] | None = None
_last_cotton_arm: str = "arm1"
_last_cotton_j4: float = 0.0
```

4. Add cotton SDF template:
```python
_COTTON_SDF_TEMPLATE = (
    "<sdf version='1.7'>"
    "<model name='{name}'>"
    "<static>true</static>"
    "<link name='link'>"
    "<visual name='visual'>"
    "<geometry><sphere><radius>0.03</radius></sphere></geometry>"
    "<material>"
    "<ambient>1 1 1 1</ambient>"
    "<diffuse>1 1 1 1</diffuse>"
    "<emissive>0.8 0.8 0.8 1</emissive>"
    "</material>"
    "</visual>"
    "</link>"
    "</model>"
    "</sdf>"
)
```

5. Add helper functions (extract from existing marker code):
```python
def _gz_spawn_model(name: str, sdf: str, x: float, y: float, z: float, world_name: str):
    """Spawn an SDF model in Gazebo at the given world position."""
    sdf_escaped = sdf.replace('"', '\\"')
    cmd = [
        "gz", "service", "-s", f"/world/{world_name}/create",
        "--reqtype", "gz.msgs.EntityFactory",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "3000",
        "-r",
        f'sdf: "{sdf_escaped}" pose: {{position: {{x: {x}, y: {y}, z: {z}}}}}'
    ]
    subprocess.run(cmd, capture_output=True, timeout=10)


def _gz_remove_model(name: str, world_name: str):
    """Remove a model from Gazebo by name."""
    cmd = [
        "gz", "service", "-s", f"/world/{world_name}/remove",
        "--reqtype", "gz.msgs.Entity",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "3000",
        "-r",
        f'name: "{name}" type: MODEL'
    ]
    subprocess.run(cmd, capture_output=True, timeout=10)
```

6. Add endpoint:
```python
@app.post("/api/cotton/spawn")
def cotton_spawn(req: CottonSpawnRequest):
    global _cotton_spawned, _last_cotton_cam, _last_cotton_arm, _last_cotton_j4

    arm_config = ARM_CONFIGS.get(req.arm)
    if arm_config is None:
        raise HTTPException(status_code=400, detail=f"Unknown arm: {req.arm}")

    wx, wy, wz = camera_to_world_fk(
        req.cam_x, req.cam_y, req.cam_z,
        j3=0.0, j4=req.j4_pos,
        arm_config=arm_config,
    )

    # Remove previous cotton if spawned
    if _cotton_spawned:
        world_name = _detect_gz_world_name()
        _gz_remove_model(_cotton_name, world_name)

    # Spawn cotton sphere
    world_name = _detect_gz_world_name()
    sdf = _COTTON_SDF_TEMPLATE.format(name=_cotton_name)
    _gz_spawn_model(_cotton_name, sdf, wx, wy, wz, world_name)

    _cotton_spawned = True
    _last_cotton_cam = (req.cam_x, req.cam_y, req.cam_z)
    _last_cotton_arm = req.arm
    _last_cotton_j4 = req.j4_pos

    return {
        "status": "ok",
        "world_x": wx, "world_y": wy, "world_z": wz,
        "arm": req.arm,
    }
```

Note: Refactor existing marker place/clear code to also use `_gz_spawn_model` / `_gz_remove_model` helpers for DRY.

- [ ] **Step 3.4: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonSpawn -v`
Expected: PASS

- [ ] **Step 3.5: Commit**

```bash
git add web_ui/testing_backend.py web_ui/test_cam_markers_backend.py
git commit -m "feat: add /api/cotton/spawn endpoint with FK-based world placement"
```

---

## Task 4: Add Cotton Remove Endpoint

**Files:**
- Modify: `web_ui/testing_backend.py`
- Modify: `web_ui/test_cam_markers_backend.py`

- [ ] **Step 4.1: Write failing test for cotton remove endpoint**

Append to `web_ui/test_cam_markers_backend.py`:

```python
class TestCottonRemove:
    def test_remove_returns_200(self, client):
        """POST /api/cotton/remove returns 200."""
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post("/api/cotton/remove")
        assert resp.status_code == 200

    def test_remove_clears_cotton_state(self, client):
        """After remove, _cotton_spawned is False."""
        import testing_backend
        testing_backend._cotton_spawned = True
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            client.post("/api/cotton/remove")
        assert testing_backend._cotton_spawned is False
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonRemove -v`
Expected: FAIL with 404

- [ ] **Step 4.3: Implement cotton remove endpoint**

Add to `web_ui/testing_backend.py`:

```python
@app.post("/api/cotton/remove")
def cotton_remove():
    global _cotton_spawned
    if _cotton_spawned:
        world_name = _detect_gz_world_name()
        _gz_remove_model(_cotton_name, world_name)
    _cotton_spawned = False
    return {"status": "ok"}
```

- [ ] **Step 4.4: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonRemove -v`
Expected: PASS

- [ ] **Step 4.5: Commit**

```bash
git add web_ui/testing_backend.py web_ui/test_cam_markers_backend.py
git commit -m "feat: add /api/cotton/remove endpoint"
```

---

## Task 5: Add Compute Approach Endpoint

**Files:**
- Modify: `web_ui/testing_backend.py`
- Modify: `web_ui/test_cam_markers_backend.py`

Add `POST /api/cotton/compute` -- transforms camera coords to arm frame, performs polar decomposition, and returns preview data without moving any joints.

- [ ] **Step 5.1: Write failing test for compute approach**

Append to `web_ui/test_cam_markers_backend.py`:

```python
class TestCottonCompute:
    def test_compute_returns_polar_values(self, client):
        """POST /api/cotton/compute returns r, theta, phi, j3, j4, j5, reachable."""
        resp = client.post(
            "/api/cotton/compute",
            json={"cam_x": 0.328, "cam_y": -0.011, "cam_z": -0.003, "arm": "arm1", "j4_pos": 0.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("r", "theta", "phi", "j3", "j4", "j5", "reachable"):
            assert key in body, f"Missing key: {key}"

    def test_compute_unreachable_returns_reachable_false(self, client):
        """Extreme camera coords produce reachable=false."""
        resp = client.post(
            "/api/cotton/compute",
            json={"cam_x": 10.0, "cam_y": 10.0, "cam_z": 10.0, "arm": "arm1", "j4_pos": 0.0},
        )
        assert resp.status_code == 200
        assert resp.json()["reachable"] is False
```

- [ ] **Step 5.2: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonCompute -v`
Expected: FAIL with 404

- [ ] **Step 5.3: Implement compute approach endpoint**

Add to `web_ui/testing_backend.py`:

```python
class CottonComputeRequest(BaseModel):
    cam_x: float = 0.328
    cam_y: float = -0.011
    cam_z: float = -0.003
    arm: str = "arm1"
    j4_pos: float = 0.0
    enable_phi_compensation: bool = False


@app.post("/api/cotton/compute")
def cotton_compute(req: CottonComputeRequest):
    arm_config = ARM_CONFIGS.get(req.arm)
    if arm_config is None:
        raise HTTPException(status_code=400, detail=f"Unknown arm: {req.arm}")

    ax, ay, az = camera_to_arm(req.cam_x, req.cam_y, req.cam_z, j4_pos=req.j4_pos)
    result = polar_decompose(ax, ay, az)

    j3 = result['j3']
    j5 = result['j5']

    if req.enable_phi_compensation:
        j3 = phi_compensation(j3, j5)
        result['reachable'] = (
            J3_MIN <= j3 <= J3_MAX
            and J4_MIN <= result['j4'] <= J4_MAX
            and J5_MIN <= j5 <= J5_MAX
            and result['r'] > 0.1
        )

    j3_clamped = max(J3_MIN, min(J3_MAX, j3))
    j4_clamped = max(J4_MIN, min(J4_MAX, result['j4']))
    j5_clamped = max(J5_MIN, min(J5_MAX, j5))

    return {
        "arm_x": ax, "arm_y": ay, "arm_z": az,
        "r": result['r'], "theta": result['theta'], "phi": result['phi'],
        "j3": j3_clamped, "j4": j4_clamped, "j5": j5_clamped,
        "j3_raw": j3, "j4_raw": result['j4'], "j5_raw": j5,
        "reachable": result['reachable'],
        "phi_compensated": req.enable_phi_compensation,
    }
```

- [ ] **Step 5.4: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonCompute -v`
Expected: PASS

- [ ] **Step 5.5: Commit**

```bash
git add web_ui/testing_backend.py web_ui/test_cam_markers_backend.py
git commit -m "feat: add /api/cotton/compute endpoint with polar decomposition"
```

---

## Task 6: Add Pick Animation Endpoint

**Files:**
- Modify: `web_ui/testing_backend.py`
- Modify: `web_ui/test_cam_markers_backend.py`

Add `POST /api/cotton/pick` -- computes joint targets from camera coords, then executes the animated pick sequence (J4 -> J3 -> J5 extend -> J5 retract -> J3 home -> J4 home) by publishing to Gazebo topics via `gz` CLI.

- [ ] **Step 6.1: Write failing test for pick endpoint**

Append to `web_ui/test_cam_markers_backend.py`:

```python
class TestCottonPick:
    def test_pick_returns_200_with_sequence_info(self, client):
        """POST /api/cotton/pick returns 200 with computed joint values and status."""
        import testing_backend
        testing_backend._last_cotton_cam = (0.328, -0.011, -0.003)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0
        with mock.patch("testing_backend._execute_pick_sequence"):
            resp = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1", "enable_phi_compensation": False},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "j3" in body
        assert "j4" in body
        assert "j5" in body
        assert body["status"] == "picking"

    def test_pick_rejects_when_no_cotton_spawned(self, client):
        """POST /api/cotton/pick returns 400 when no cotton has been spawned."""
        import testing_backend
        testing_backend._last_cotton_cam = None
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 400

    def test_pick_rejects_concurrent_pick(self, client):
        """POST /api/cotton/pick returns 409 when pick is already in progress."""
        import testing_backend
        testing_backend._last_cotton_cam = (0.1, 0.0, 0.0)
        testing_backend._pick_in_progress = True
        with mock.patch("testing_backend._execute_pick_sequence"):
            resp = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1"},
            )
        assert resp.status_code == 409
        testing_backend._pick_in_progress = False
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonPick -v`
Expected: FAIL with 404

- [ ] **Step 6.3: Implement pick endpoint and animation**

Add to `web_ui/testing_backend.py`:

1. State variables:
```python
_pick_in_progress: bool = False
_pick_status: str = "idle"  # idle, picking, done, error
```

2. Request model:
```python
class CottonPickRequest(BaseModel):
    arm: str = "arm1"
    enable_j4_compensation: bool = True
    enable_phi_compensation: bool = False
    cam_x: float | None = None
    cam_y: float | None = None
    cam_z: float | None = None
```

3. Pick endpoint:
```python
@app.post("/api/cotton/pick")
def cotton_pick(req: CottonPickRequest):
    global _pick_in_progress

    if _pick_in_progress:
        raise HTTPException(status_code=409, detail="Pick already in progress")

    if req.cam_x is not None and req.cam_y is not None and req.cam_z is not None:
        cam_x, cam_y, cam_z = req.cam_x, req.cam_y, req.cam_z
    elif _last_cotton_cam is not None:
        cam_x, cam_y, cam_z = _last_cotton_cam
    else:
        raise HTTPException(status_code=400, detail="No cotton position available")

    arm_config = ARM_CONFIGS.get(req.arm)
    if arm_config is None:
        raise HTTPException(status_code=400, detail=f"Unknown arm: {req.arm}")

    j4_pos = _last_cotton_j4 if req.enable_j4_compensation else 0.0
    ax, ay, az = camera_to_arm(cam_x, cam_y, cam_z, j4_pos=j4_pos)
    result = polar_decompose(ax, ay, az)

    j3 = result['j3']
    j4 = result['j4']
    j5 = result['j5']

    if req.enable_phi_compensation:
        j3 = phi_compensation(j3, j5)

    j3 = max(J3_MIN, min(J3_MAX, j3))
    j4 = max(J4_MIN, min(J4_MAX, j4))
    j5 = max(J5_MIN, min(J5_MAX, j5))

    _pick_in_progress = True

    import threading
    threading.Thread(
        target=_execute_pick_sequence,
        args=(j3, j4, j5, req.arm),
        daemon=True,
    ).start()

    return {
        "status": "picking",
        "j3": j3, "j4": j4, "j5": j5,
        "arm": req.arm,
        "reachable": result['reachable'],
    }
```

4. Animation function:
```python
def _execute_pick_sequence(j3: float, j4: float, j5: float, arm: str):
    """Execute the 6-step pick animation sequence.

    Timing matches yanthra_move/arm_sim_bridge.py:
      0.0s: J4 lateral
      0.8s: J3 tilt
      1.6s: J5 extend
      3.0s: J5 retract to 0
      3.8s: J3 home to 0
      4.6s: J4 home to 0
      5.5s: done
    """
    global _pick_in_progress, _pick_status
    import time

    arm_config = ARM_CONFIGS[arm]
    _pick_status = "picking"

    steps = [
        (0.0, arm_config['j4_topic'], j4, "J4 lateral"),
        (0.8, arm_config['j3_topic'], j3, "J3 tilt"),
        (1.6, arm_config['j5_topic'], j5, "J5 extend"),
        (3.0, arm_config['j5_topic'], 0.0, "J5 retract"),
        (3.8, arm_config['j3_topic'], 0.0, "J3 home"),
        (4.6, arm_config['j4_topic'], 0.0, "J4 home"),
    ]

    start_time = time.monotonic()
    for delay, topic, value, label in steps:
        elapsed = time.monotonic() - start_time
        wait = delay - elapsed
        if wait > 0:
            time.sleep(wait)
        _publish_joint_gz(topic, value)

    remaining = 5.5 - (time.monotonic() - start_time)
    if remaining > 0:
        time.sleep(remaining)

    _pick_in_progress = False
    _pick_status = "done"


def _publish_joint_gz(topic: str, value: float):
    """Publish a Float64 value to a Gazebo topic via gz CLI."""
    subprocess.Popen(
        ["gz", "topic", "-t", topic, "-m", "gz.msgs.Double", "-p", f"data: {value}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
```

5. Status endpoint:
```python
@app.get("/api/cotton/pick/status")
def cotton_pick_status():
    return {"status": _pick_status, "in_progress": _pick_in_progress}
```

- [ ] **Step 6.4: Run test to verify it passes**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py::TestCottonPick -v`
Expected: PASS

- [ ] **Step 6.5: Commit**

```bash
git add web_ui/testing_backend.py web_ui/test_cam_markers_backend.py
git commit -m "feat: add /api/cotton/pick endpoint with animated pick sequence"
```

---

## Task 7: Add Phi Compensation to Frontend `camToJoint`

**Files:**
- Modify: `web_ui/tests/cam_to_joint_shim.js`
- Modify: `web_ui/tests/test_cam_to_joint.js`
- Modify: `web_ui/testing_ui.js`

Add a `phiCompensation(j3, j5)` function to the frontend that mirrors the Python implementation.

- [ ] **Step 7.1: Write failing test for JS phi compensation**

Append to `web_ui/tests/test_cam_to_joint.js`:

```javascript
const { phiCompensation } = require('./cam_to_joint_shim.js');

// Phi Compensation Tests

test('phiCompensation zone1 applies positive offset for phi_deg <= 50.5', () => {
  assert.equal(typeof phiCompensation, 'function', 'phiCompensation must be exported');
  // j3 = -0.5 rad => phi_deg = 28.6 => Zone1
  var result = phiCompensation(-0.5, 0.1);
  var expected = -0.5 + 0.014 * (1.0 + 0.5 * (0.1 / 0.450)) * 2 * Math.PI;
  assert.ok(Math.abs(result - expected) < 1e-9, `result ${result} should be near ${expected}`);
});

test('phiCompensation zone2 applies zero offset for 50.5 < phi_deg <= 60', () => {
  var result = phiCompensation(-0.93, 0.2);
  assert.ok(Math.abs(result - (-0.93)) < 1e-9, `result ${result} should be -0.93`);
});

test('phiCompensation zone3 applies negative offset for phi_deg > 60', () => {
  var result = phiCompensation(-1.06, 0.3);
  var expected = -1.06 + (-0.014) * (1.0 + 0.5 * (0.3 / 0.450)) * 2 * Math.PI;
  assert.ok(Math.abs(result - expected) < 1e-9, `result ${result} should be near ${expected}`);
});
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `node --test web_ui/tests/test_cam_to_joint.js`
Expected: FAIL -- `phiCompensation` is not exported from the shim

- [ ] **Step 7.3: Implement `phiCompensation` in shim and in testing_ui.js**

Append to `web_ui/tests/cam_to_joint_shim.js` (before `module.exports`):

```javascript
var PHI_ZONE1_MAX_DEG = 50.5;
var PHI_ZONE2_MAX_DEG = 60.0;
var PHI_ZONE1_OFFSET  = 0.014;
var PHI_ZONE2_OFFSET  = 0.0;
var PHI_ZONE3_OFFSET  = -0.014;
var PHI_L5_SCALE      = 0.5;
var PHI_JOINT5_MAX    = 0.450;

function phiCompensation(j3, j5) {
    var phiDeg = Math.abs(j3 * 180.0 / Math.PI);
    var baseOffset;
    if (phiDeg <= PHI_ZONE1_MAX_DEG) {
        baseOffset = PHI_ZONE1_OFFSET;
    } else if (phiDeg <= PHI_ZONE2_MAX_DEG) {
        baseOffset = PHI_ZONE2_OFFSET;
    } else {
        baseOffset = PHI_ZONE3_OFFSET;
    }
    var l5Norm = Math.max(0.0, j5) / PHI_JOINT5_MAX;
    var l5Scale = 1.0 + PHI_L5_SCALE * l5Norm;
    var compRot = baseOffset * l5Scale;
    var compRad = compRot * 2.0 * Math.PI;
    return j3 + compRad;
}
```

Update `module.exports` line:
```javascript
module.exports = { camToJoint: camToJoint, phiCompensation: phiCompensation };
```

Also add the same `phiCompensation` function to `web_ui/testing_ui.js` right after the `camToJoint` function (~line 1105).

- [ ] **Step 7.4: Run test to verify it passes**

Run: `node --test web_ui/tests/test_cam_to_joint.js`
Expected: All 7 tests PASS (4 existing + 3 new)

- [ ] **Step 7.5: Commit**

```bash
git add web_ui/tests/cam_to_joint_shim.js web_ui/tests/test_cam_to_joint.js web_ui/testing_ui.js
git commit -m "feat: add phiCompensation function to frontend and tests"
```

---

## Task 8: Add Cotton Placement UI to HTML

**Files:**
- Modify: `web_ui/testing_ui.html`
- Modify: `web_ui/testing_ui.css`

Add a "Cotton Placement" panel to the Testing UI with camera coordinate inputs, arm selector, spawn/remove/compute/pick buttons, compensation toggles, and results display.

- [ ] **Step 8.1: Add the Cotton Placement HTML section**

In `web_ui/testing_ui.html`, find the cotton sequence section (`id="cam-seq-section"`) and add a new section **before** it:

```html
<!-- Cotton Placement (ported from yanthra_move) -->
<section id="cotton-placement-section" class="panel">
  <h2>Cotton Placement</h2>

  <div class="cotton-controls">
    <div class="cotton-inputs">
      <label>Arm:
        <select id="cotton-arm-select">
          <option value="arm1">Arm 1</option>
          <option value="arm2">Arm 2</option>
          <option value="arm3">Arm 3</option>
        </select>
      </label>
      <label>cam_x: <input type="number" id="cotton-cam-x" value="0.328" step="0.001"></label>
      <label>cam_y: <input type="number" id="cotton-cam-y" value="-0.011" step="0.001"></label>
      <label>cam_z: <input type="number" id="cotton-cam-z" value="-0.003" step="0.001"></label>
      <label>J4 pos: <input type="number" id="cotton-j4-pos" value="0.0" step="0.01"></label>
    </div>

    <div class="cotton-actions">
      <button id="cotton-spawn-btn" class="btn btn-primary">Spawn Cotton</button>
      <button id="cotton-remove-btn" class="btn btn-danger">Remove Cotton</button>
      <button id="cotton-compute-btn" class="btn btn-secondary">Compute Approach</button>
      <button id="cotton-pick-btn" class="btn btn-success">Pick Cotton</button>
    </div>

    <div class="cotton-toggles">
      <label><input type="checkbox" id="cotton-j4-comp" checked> J4 Compensation</label>
      <label><input type="checkbox" id="cotton-phi-comp"> Phi Compensation</label>
    </div>
  </div>

  <div id="cotton-compute-results" class="cotton-results" style="display:none;">
    <h3>Compute Approach Results</h3>
    <table class="compact-table">
      <tr><td>Arm Frame</td><td id="cotton-arm-xyz">--</td></tr>
      <tr><td>r</td><td id="cotton-r">--</td></tr>
      <tr><td>theta (J4)</td><td id="cotton-theta">--</td></tr>
      <tr><td>phi (J3)</td><td id="cotton-phi">--</td></tr>
      <tr><td>J3</td><td id="cotton-j3">--</td></tr>
      <tr><td>J4</td><td id="cotton-j4">--</td></tr>
      <tr><td>J5</td><td id="cotton-j5">--</td></tr>
      <tr><td>Reachable</td><td id="cotton-reachable">--</td></tr>
    </table>
  </div>

  <div id="cotton-pick-status" class="pick-status" style="display:none;">
    <span id="cotton-pick-status-text">Idle</span>
  </div>
</section>
```

- [ ] **Step 8.2: Add CSS styles for the cotton placement panel**

Append to `web_ui/testing_ui.css`:

```css
/* Cotton Placement Panel */
#cotton-placement-section .cotton-controls {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

#cotton-placement-section .cotton-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

#cotton-placement-section .cotton-inputs label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.85rem;
}

#cotton-placement-section .cotton-inputs input[type="number"] {
  width: 5.5rem;
}

#cotton-placement-section .cotton-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

#cotton-placement-section .cotton-toggles {
  display: flex;
  gap: 1rem;
  font-size: 0.85rem;
}

.cotton-results {
  margin-top: 0.75rem;
  padding: 0.5rem;
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
}

.cotton-results .compact-table {
  width: 100%;
  font-size: 0.85rem;
}

.cotton-results .compact-table td:first-child {
  font-weight: bold;
  width: 30%;
}

.pick-status {
  margin-top: 0.5rem;
  padding: 0.4rem 0.75rem;
  border-radius: 4px;
  font-weight: bold;
}

.pick-status.picking {
  background: #f0ad4e33;
  color: #f0ad4e;
}

.pick-status.done {
  background: #5cb85c33;
  color: #5cb85c;
}
```

- [ ] **Step 8.3: Commit**

```bash
git add web_ui/testing_ui.html web_ui/testing_ui.css
git commit -m "feat: add cotton placement UI section to testing_ui"
```

---

## Task 9: Wire Up Cotton Placement JS Logic

**Files:**
- Modify: `web_ui/testing_ui.js`
- Create: `web_ui/tests/e2e/cotton_placement.spec.js`

Connect the new HTML elements to the backend endpoints.

- [ ] **Step 9.1: Write E2E test for cotton placement UI**

Create `web_ui/tests/e2e/cotton_placement.spec.js`:

```javascript
// @ts-check
const { test, expect } = require('@playwright/test');

test('Cotton Placement section is visible on page load', async ({ page }) => {
  await page.goto('/');
  const section = page.locator('#cotton-placement-section');
  await expect(section).toBeVisible({ timeout: 3000 });
});

test('Spawn Cotton button exists and is clickable', async ({ page }) => {
  await page.goto('/');
  const btn = page.locator('#cotton-spawn-btn');
  await expect(btn).toBeVisible({ timeout: 2000 });
  await expect(btn).toBeEnabled();
});

test('Compute Approach button shows results panel', async ({ page }) => {
  await page.goto('/');
  await page.route('/api/cotton/compute', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        arm_x: -0.1, arm_y: 0.05, arm_z: -0.08,
        r: 0.128, theta: 0.05, phi: -0.675,
        j3: -0.675, j4: 0.05, j5: 0.0,
        j3_raw: -0.675, j4_raw: 0.05, j5_raw: -0.192,
        reachable: false, phi_compensated: false,
      }),
    });
  });
  await page.locator('#cotton-compute-btn').click();
  const resultsPanel = page.locator('#cotton-compute-results');
  await expect(resultsPanel).toBeVisible({ timeout: 2000 });
});

test('Pick Cotton button exists and is clickable', async ({ page }) => {
  await page.goto('/');
  const btn = page.locator('#cotton-pick-btn');
  await expect(btn).toBeVisible({ timeout: 2000 });
  await expect(btn).toBeEnabled();
});
```

- [ ] **Step 9.2: Add JS event handlers for cotton placement**

Add to `web_ui/testing_ui.js` (inside the IIFE, near `setupCottonSequence()`):

```javascript
// Cotton Placement (ported from yanthra_move)

function setupCottonPlacement() {
    var spawnBtn   = document.getElementById('cotton-spawn-btn');
    var removeBtn  = document.getElementById('cotton-remove-btn');
    var computeBtn = document.getElementById('cotton-compute-btn');
    var pickBtn    = document.getElementById('cotton-pick-btn');

    if (spawnBtn)   spawnBtn.addEventListener('click', cottonSpawn);
    if (removeBtn)  removeBtn.addEventListener('click', cottonRemove);
    if (computeBtn) computeBtn.addEventListener('click', cottonCompute);
    if (pickBtn)    pickBtn.addEventListener('click', cottonPick);
}

function getCottonParams() {
    return {
        cam_x: parseFloat(document.getElementById('cotton-cam-x').value) || 0,
        cam_y: parseFloat(document.getElementById('cotton-cam-y').value) || 0,
        cam_z: parseFloat(document.getElementById('cotton-cam-z').value) || 0,
        arm:   document.getElementById('cotton-arm-select').value || 'arm1',
        j4_pos: parseFloat(document.getElementById('cotton-j4-pos').value) || 0,
        enable_j4_compensation: document.getElementById('cotton-j4-comp').checked,
        enable_phi_compensation: document.getElementById('cotton-phi-comp').checked,
    };
}

function cottonSpawn() {
    var params = getCottonParams();
    log('Spawning cotton at cam(' + params.cam_x + ', ' + params.cam_y + ', ' + params.cam_z + ')...');
    fetch('/api/cotton/spawn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            cam_x: params.cam_x, cam_y: params.cam_y, cam_z: params.cam_z,
            arm: params.arm, j4_pos: params.j4_pos,
        }),
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        log('Cotton spawned at world(' + d.world_x.toFixed(3) + ', ' +
            d.world_y.toFixed(3) + ', ' + d.world_z.toFixed(3) + ')', 'success');
    })
    .catch(function (e) { log('Cotton spawn error: ' + e, 'error'); });
}

function cottonRemove() {
    fetch('/api/cotton/remove', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function () { log('Cotton removed', 'success'); })
    .catch(function (e) { log('Cotton remove error: ' + e, 'error'); });
}

function cottonCompute() {
    var params = getCottonParams();
    fetch('/api/cotton/compute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            cam_x: params.cam_x, cam_y: params.cam_y, cam_z: params.cam_z,
            arm: params.arm, j4_pos: params.j4_pos,
            enable_phi_compensation: params.enable_phi_compensation,
        }),
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        var panel = document.getElementById('cotton-compute-results');
        panel.style.display = 'block';
        document.getElementById('cotton-arm-xyz').textContent =
            '(' + d.arm_x.toFixed(4) + ', ' + d.arm_y.toFixed(4) + ', ' + d.arm_z.toFixed(4) + ')';
        document.getElementById('cotton-r').textContent = d.r.toFixed(4) + ' m';
        document.getElementById('cotton-theta').textContent = d.theta.toFixed(4) + ' m';
        document.getElementById('cotton-phi').textContent =
            d.phi.toFixed(4) + ' rad (' + (d.phi * 180 / Math.PI).toFixed(1) + ' deg)';
        document.getElementById('cotton-j3').textContent = d.j3.toFixed(4) + ' rad';
        document.getElementById('cotton-j4').textContent = d.j4.toFixed(4) + ' m';
        document.getElementById('cotton-j5').textContent = d.j5.toFixed(4) + ' m';
        document.getElementById('cotton-reachable').textContent = d.reachable ? 'YES' : 'NO';
        document.getElementById('cotton-reachable').style.color = d.reachable ? '#5cb85c' : '#d9534f';
        log('Compute approach: r=' + d.r.toFixed(3) + ' reachable=' + d.reachable,
            d.reachable ? 'success' : 'warn');
    })
    .catch(function (e) { log('Compute error: ' + e, 'error'); });
}

function cottonPick() {
    var params = getCottonParams();
    var pickBtn = document.getElementById('cotton-pick-btn');
    var statusDiv = document.getElementById('cotton-pick-status');
    var statusText = document.getElementById('cotton-pick-status-text');

    pickBtn.disabled = true;
    statusDiv.style.display = 'block';
    statusDiv.className = 'pick-status picking';
    statusText.textContent = 'Picking...';

    log('Starting pick sequence on ' + params.arm + '...');
    fetch('/api/cotton/pick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            arm: params.arm,
            enable_j4_compensation: params.enable_j4_compensation,
            enable_phi_compensation: params.enable_phi_compensation,
        }),
    })
    .then(function (r) {
        if (!r.ok) { throw new Error('HTTP ' + r.status); }
        return r.json();
    })
    .then(function (d) {
        log('Pick started: J3=' + d.j3.toFixed(3) + ' J4=' + d.j4.toFixed(3) +
            ' J5=' + d.j5.toFixed(3), 'success');
        pollPickStatus(pickBtn, statusDiv, statusText);
    })
    .catch(function (e) {
        log('Pick error: ' + e, 'error');
        pickBtn.disabled = false;
        statusDiv.className = 'pick-status';
        statusText.textContent = 'Error';
    });
}

function pollPickStatus(pickBtn, statusDiv, statusText) {
    var interval = setInterval(function () {
        fetch('/api/cotton/pick/status')
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (!d.in_progress) {
                clearInterval(interval);
                pickBtn.disabled = false;
                statusDiv.className = 'pick-status done';
                statusText.textContent = 'Done';
                log('Pick sequence complete', 'success');
                setTimeout(function () { statusDiv.style.display = 'none'; }, 3000);
            }
        })
        .catch(function () { /* ignore poll errors */ });
    }, 500);
}
```

Also call `setupCottonPlacement()` in the initialization section (where `setupCottonSequence()` is called).

- [ ] **Step 9.3: Run unit tests to verify no regressions**

Run: `node --test web_ui/tests/test_cam_to_joint.js`
Expected: All 7 tests PASS

- [ ] **Step 9.4: Commit**

```bash
git add web_ui/testing_ui.js web_ui/tests/e2e/cotton_placement.spec.js
git commit -m "feat: wire up cotton placement UI to backend endpoints"
```

---

## Task 10: Update `cam_to_world` for Dynamic FK

**Files:**
- Modify: `web_ui/testing_backend.py`
- Modify: `web_ui/test_cam_markers_backend.py`

The existing `cam_to_world()` uses a static pre-computed matrix (camera on chassis). Since the camera is now on the arm, update it to use the FK chain.

- [ ] **Step 10.1: Update tests for cam_to_world**

Replace the existing `TestCamToWorld` tests in `web_ui/test_cam_markers_backend.py`:

```python
class TestCamToWorld:
    def test_cam_to_world_returns_finite_values(self):
        """cam_to_world(0, 0, 0) must return finite world coordinates."""
        wx, wy, wz = cam_to_world(0.0, 0.0, 0.0)
        import math
        assert math.isfinite(wx), f"wx={wx}"
        assert math.isfinite(wy), f"wy={wy}"
        assert math.isfinite(wz), f"wz={wz}"

    def test_cam_to_world_deterministic(self):
        """Two calls with same inputs return identical results."""
        r1 = cam_to_world(0.1, -0.02, 0.05)
        r2 = cam_to_world(0.1, -0.02, 0.05)
        assert r1 == r2
```

- [ ] **Step 10.2: Update `cam_to_world` to use FK**

In `web_ui/testing_backend.py`, replace the static `cam_to_world` function and remove the old `_T_WC_*` constants:

```python
def cam_to_world(cam_x: float, cam_y: float, cam_z: float) -> tuple[float, float, float]:
    """Convert camera-frame point to Gazebo world frame via FK.

    Uses Arm 1 with J3=0, J4=0 as default (camera is on Arm 1).
    """
    return camera_to_world_fk(
        cam_x, cam_y, cam_z,
        j3=0.0, j4=0.0,
        arm_config=ARM_CONFIGS['arm1'],
    )
```

- [ ] **Step 10.3: Run all backend tests**

Run: `python3 -m pytest web_ui/test_cam_markers_backend.py -v`
Expected: All tests PASS

- [ ] **Step 10.4: Commit**

```bash
git add web_ui/testing_backend.py web_ui/test_cam_markers_backend.py
git commit -m "refactor: update cam_to_world to use FK chain (camera now on arm)"
```

---

## Task 11: Update TF Subscriber in Frontend

**Files:**
- Modify: `web_ui/testing_ui.js`

Replace the `/tf_static` subscriber with a pre-computed camera-to-arm inverse transform based on known URDF values.

- [ ] **Step 11.1: Implement pre-computed transform**

Add to `web_ui/testing_ui.js` (replace or supplement `setupTfSubscriber`):

```javascript
// Pre-computed camera_link -> arm_yanthra_link transform.
// Based on URDF: camera_joint parent=arm_yanthra_link, child=camera_link
// origin xyz=(0.016845, 0.100461, -0.077129) rpy=(1.5708, 0.785398, 0)
// We compute the INVERSE of this transform for camToJoint.
function initCameraToArmTransform() {
    var tx = 0.016845, ty = 0.100461, tz = -0.077129;
    var roll = 1.5708, pitch = 0.785398, yaw = 0.0;

    var cr = Math.cos(roll), sr = Math.sin(roll);
    var cp = Math.cos(pitch), sp = Math.sin(pitch);
    var cy = Math.cos(yaw), sy = Math.sin(yaw);

    // Forward rotation (yanthra -> camera)
    var r00 = cy*cp, r01 = cy*sp*sr - sy*cr, r02 = cy*sp*cr + sy*sr;
    var r10 = sy*cp, r11 = sy*sp*sr + cy*cr, r12 = sy*sp*cr - cy*sr;
    var r20 = -sp,   r21 = cp*sr,             r22 = cp*cr;

    // Inverse: R^T and -R^T * t
    var inv_tx = -(r00*tx + r10*ty + r20*tz);
    var inv_ty = -(r01*tx + r11*ty + r21*tz);
    var inv_tz = -(r02*tx + r12*ty + r22*tz);

    tfMatrix = {
        apply: function(x, y, z) {
            return {
                x: r00*x + r10*y + r20*z + inv_tx,
                y: r01*x + r11*y + r21*z + inv_ty,
                z: r02*x + r12*y + r22*z + inv_tz,
            };
        }
    };
    tfReady = true;
}
```

Call `initCameraToArmTransform()` during initialization. Keep `setupTfSubscriber()` as a backup override.

- [ ] **Step 11.2: Run unit tests to verify no regressions**

Run: `node --test web_ui/tests/test_cam_to_joint.js`
Expected: All 7 tests PASS

- [ ] **Step 11.3: Commit**

```bash
git add web_ui/testing_ui.js
git commit -m "refactor: use pre-computed camera-to-arm transform instead of TF subscriber"
```

---

## Task 12: Integration Testing and Polish

**Files:**
- All modified files

Final verification that all tests pass and the system is coherent.

- [ ] **Step 12.1: Run all Python tests**

Run: `python3 -m pytest web_ui/test_fk_chain.py web_ui/test_cam_markers_backend.py -v`
Expected: All tests PASS

- [ ] **Step 12.2: Run all JS unit tests**

Run: `node --test web_ui/tests/test_cam_to_joint.js`
Expected: All tests PASS

- [ ] **Step 12.3: Verify no import errors in testing_backend.py**

Run: `python3 -c "import sys; sys.path.insert(0, 'web_ui'); from testing_backend import app; print('OK')"`
Expected: `OK`

- [ ] **Step 12.4: Final commit if any cleanup needed**

```bash
git add -A
git status
# Only commit if there are changes
git commit -m "chore: integration test verification and cleanup"
```

---

## Summary

| Task | Description | New Tests | Commit |
|------|-------------|-----------|--------|
| 1 | FK math module (`fk_chain.py`) | 11 pytest | `feat: add FK math module` |
| 2 | Move camera in URDF | 2 pytest | `fix: move camera_link to arm` |
| 3 | Cotton spawn endpoint | 2 pytest | `feat: /api/cotton/spawn` |
| 4 | Cotton remove endpoint | 2 pytest | `feat: /api/cotton/remove` |
| 5 | Compute approach endpoint | 2 pytest | `feat: /api/cotton/compute` |
| 6 | Pick animation endpoint | 3 pytest | `feat: /api/cotton/pick` |
| 7 | Frontend phi compensation | 3 node:test | `feat: phiCompensation JS` |
| 8 | Cotton placement HTML/CSS | -- | `feat: cotton placement UI` |
| 9 | Cotton placement JS wiring | 4 playwright | `feat: wire up cotton UI` |
| 10 | Update cam_to_world to FK | 2 pytest (updated) | `refactor: cam_to_world FK` |
| 11 | Pre-computed TF transform | -- | `refactor: pre-computed TF` |
| 12 | Integration verification | -- | `chore: integration verify` |

**Total: 12 tasks, ~31 new tests, ~12 commits**
