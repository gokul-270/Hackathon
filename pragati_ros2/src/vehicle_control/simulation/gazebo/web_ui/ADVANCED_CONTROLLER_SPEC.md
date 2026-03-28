# Advanced Controller — Sensor Fusion Specification

> **Version:** 1.0  
> **Date:** 2025-01-18  
> **Scope:** EKF-based sensor fusion (Odom + IMU + RTK GPS) for the Pragati vehicle  
> **Status:** DRAFT — awaiting review before implementation

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)  
2. [Architecture Overview](#2-architecture-overview)  
3. [EKF Engine (`ekf_engine.py`)](#3-ekf-engine)  
4. [GPS–Local Coordinate Converter](#4-gpslocal-coordinate-converter)  
5. [Path Corrector (`path_corrector.py`)](#5-path-corrector)  
6. [Backend Integration (`backend.py` changes)](#6-backend-integration)  
7. [Dashboard UI Changes](#7-dashboard-ui-changes)  
8. [WebSocket Protocol](#8-websocket-protocol)  
9. [Behavior Matrix (All Modes)](#9-behavior-matrix)  
10. [Constants & Tuning Parameters](#10-constants--tuning-parameters)  
11. [Files Created / Modified](#11-files-created--modified)  
12. [Do-Not-Touch List](#12-do-not-touch-list)  
13. [Testing Plan](#13-testing-plan)  
14. [Rollback Strategy](#14-rollback-strategy)  

---

## 1. Problem Statement

Today the vehicle relies **solely on wheel odometry** for position tracking. Odometry
drifts over time due to wheel slip, terrain irregularities, and kinematics
approximation errors. We already have two additional sensors streaming data via
rosbridge that are **displayed but not used for control**:

| Sensor | Topic | Rate | Frame | Current Use |
|--------|-------|------|-------|-------------|
| Wheel Odometry | `/odom` | 50 Hz | `base-v1` → kinematic center transform | Pattern execution, precision moves, draw path |
| IMU | `/imu` | 100 Hz | `imu_link` (at kinematic center) | Dashboard display only |
| RTK GPS | `/gps/fix` | 10 Hz | `gps` (at kinematic center + 0.3 m up) | Dashboard display only |
| RTK Status | `/rtk/status` | 10 Hz | — | Dashboard display only |

**Goal:** Fuse all three sensors with an Extended Kalman Filter (EKF) running in the
backend to produce a **corrected pose estimate** that:

- Eliminates odometry drift over long runs  
- Provides heading stabilisation from the IMU gyroscope  
- Provides absolute position anchoring from RTK GPS (once converged)  
- Works transparently in **all operating modes** (manual, pattern, precision, draw path)  
- Exposes fusion state, corrections, and drift metrics to the dashboard  

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                    Backend  (backend.py)                │
│                                                        │
│  /odom ──────┐                                         │
│  /imu ───────┤──▶  EKF Engine  ──▶  fused_x/y/θ       │
│  /gps/fix ───┘     (ekf_engine)     (replaces raw odom)│
│  /rtk/status ──▶   GPS Converter                       │
│                                                        │
│  fused_x/y/θ ──▶  odom_getter (pattern/draw/precision) │
│                ──▶  WS broadcast → Dashboard            │
│                                                        │
│              PathCorrector (optional, for patterns)     │
│              ── monitors cross-track error during       │
│                 pattern/draw execution                  │
└────────────────────────────────────────────────────────┘
```

**Data flow:**

1. Backend subscribes to `/imu` and `/gps/fix` (in addition to existing `/odom`).  
2. Every odom callback (50 Hz) → EKF **predict** step using odom delta + IMU angular rate.  
3. Every GPS callback (10 Hz) → EKF **update** step using GPS local position.  
4. `state.fused_x`, `state.fused_y`, `state.fused_theta` replace `state.odom_x/y/theta` as the pose source for all control loops.  
5. `odom_getter` lambda returns fused pose instead of raw odom.  
6. A new WS message `ekf_status` is broadcast at 2 Hz with fusion diagnostics.  
7. Dashboard shows fused vs raw odom positions, correction magnitudes, and EKF health.

---

## 3. EKF Engine

### 3.1 New file: `ekf_engine.py`

Location: `simulation/gazebo/web_ui/ekf_engine.py`

### 3.2 State Vector

```
x = [ x, y, θ, vx, vy, ω ]ᵀ   (6 × 1)
```

| Index | Symbol | Description | Unit |
|-------|--------|-------------|------|
| 0 | x | Position East (Gazebo X) | m |
| 1 | y | Position North (Gazebo Y) | m |
| 2 | θ | Heading (yaw) | rad |
| 3 | vx | Forward velocity (body frame) | m/s |
| 4 | vy | Lateral velocity (body frame) | m/s |
| 5 | ω | Yaw rate | rad/s |

### 3.3 Predict Step (called at 50 Hz, on each odom callback)

**Input:** Odom twist (`v_odom`, `ω_odom`) + IMU gyro-z (`ω_imu`)

The predict step uses a **differential-drive kinematic model** with IMU-fused yaw rate:

```python
# Fuse odom and IMU yaw rates (weighted average)
ω_fused = α_imu * ω_imu + (1 - α_imu) * ω_odom    # α_imu = 0.7 default

dt = time_since_last_predict

# State prediction (constant-velocity model in body frame)
θ_new = θ + ω_fused * dt
x_new = x + (vx * cos(θ) - vy * sin(θ)) * dt
y_new = y + (vx * sin(θ) + vy * cos(θ)) * dt
vx_new = v_odom  # from odom twist.linear.x
vy_new = 0.0     # Ackermann — no lateral velocity
ω_new = ω_fused
```

**Jacobian F** (6×6): Partial derivatives of the prediction model w.r.t. state.

```
F = ∂f/∂x = 
┌ 1  0  (-vx·sin(θ)-vy·cos(θ))·dt   cos(θ)·dt  -sin(θ)·dt   0   ┐
│ 0  1  ( vx·cos(θ)-vy·sin(θ))·dt   sin(θ)·dt   cos(θ)·dt   0   │
│ 0  0   1                           0            0            dt  │
│ 0  0   0                           1            0            0   │
│ 0  0   0                           0            1            0   │
└ 0  0   0                           0            0            1   ┘
```

**Process noise Q** (6×6 diagonal):

```python
Q = diag([
    q_pos,      # x position process noise
    q_pos,      # y position process noise
    q_theta,    # heading process noise
    q_vel,      # forward velocity process noise
    q_vel,      # lateral velocity process noise
    q_omega,    # yaw rate process noise
]) * dt
```

Default values (tunable from dashboard):

| Parameter | Symbol | Default | Description |
|-----------|--------|---------|-------------|
| `q_pos` | σ²_pos | 0.01 | Position prediction uncertainty (m²/s) |
| `q_theta` | σ²_θ | 0.005 | Heading prediction uncertainty (rad²/s) |
| `q_vel` | σ²_v | 0.1 | Velocity prediction uncertainty ((m/s)²/s) |
| `q_omega` | σ²_ω | 0.05 | Yaw rate prediction uncertainty ((rad/s)²/s) |

**Covariance prediction:**

```
P_predicted = F @ P @ Fᵀ + Q
```

### 3.4 Update Step — Odometry (50 Hz)

**Measurement:** Odom position (after kinematic center transform) → `[z_x, z_y, z_θ]`

```
H_odom = 
┌ 1  0  0  0  0  0 ┐
│ 0  1  0  0  0  0 │
└ 0  0  1  0  0  0 ┘
```

**Measurement noise R_odom** (3×3 diagonal):

```python
R_odom = diag([r_odom_pos, r_odom_pos, r_odom_theta])
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `r_odom_pos` | 0.05 | Odom position measurement noise (m²) |
| `r_odom_theta` | 0.02 | Odom heading measurement noise (rad²) |

### 3.5 Update Step — IMU (100 Hz, fused into predict step)

The IMU gyro-z is **not** handled as a separate EKF update; instead it's **blended
into the predict step** via the `α_imu` weight on yaw rate. This avoids running
the update equations at 100 Hz while still benefiting from IMU heading.

The IMU orientation (quaternion → yaw) is used as a **heading reference check**:
if `|θ_ekf − θ_imu| > heading_divergence_threshold` for more than 2 seconds,
a diagnostic warning is raised.

### 3.6 Update Step — GPS (10 Hz, when RTK status ≥ FLOAT)

**Pre-condition:** Only run GPS update when RTK status is `FLOAT` or `RTK_FIXED`.
During `SEARCHING`, `NO_FIX`, or `DGPS`, the GPS is too noisy to be useful — the
EKF runs on odom+IMU only (dead-reckoning mode).

**Measurement:** GPS position converted to local coordinates → `[z_gps_x, z_gps_y]`

```
H_gps = 
┌ 1  0  0  0  0  0 ┐
└ 0  1  0  0  0  0 ┘
```

**Measurement noise R_gps** (2×2 diagonal): Derived from the RTK covariance reported
in the NavSatFix message.

```python
# Extract from NavSatFix.position_covariance (diagonal: [H², _, _, _, H², _, _, _, V²])
r_gps_x = msg.position_covariance[0]  # Horizontal variance
r_gps_y = msg.position_covariance[4]  # Horizontal variance

# Apply a minimum floor to prevent overconfident GPS
R_gps = diag([max(r_gps_x, r_gps_floor), max(r_gps_y, r_gps_floor)])
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `r_gps_floor` | 0.01 | Minimum GPS noise floor (m²) — prevents EKF divergence on perfect sim data |

### 3.7 Standard Kalman Update Equations

For any measurement `z` with observation matrix `H` and noise `R`:

```
y = z − H @ x̂           # Innovation (residual)
S = H @ P @ Hᵀ + R       # Innovation covariance
K = P @ Hᵀ @ S⁻¹         # Kalman gain
x̂ = x̂ + K @ y           # Updated state
P = (I − K @ H) @ P      # Updated covariance (Joseph form for stability)
```

**Angle wrapping:** The heading component of the innovation (`y[θ]`) must be
wrapped to `[-π, π]` before applying the update.

### 3.8 Class API

```python
class EKFEngine:
    """Extended Kalman Filter for Odom + IMU + GPS sensor fusion."""

    def __init__(self, config: dict | None = None):
        """Initialize with default or custom noise parameters."""

    def predict(self, v_odom: float, omega_odom: float,
                omega_imu: float, dt: float) -> None:
        """Predict step using odom velocity + IMU gyro."""

    def update_odom(self, x: float, y: float, theta: float) -> None:
        """Update with odometry position measurement."""

    def update_gps(self, gps_x: float, gps_y: float,
                   cov_x: float, cov_y: float) -> None:
        """Update with GPS position in local frame.
        Only call when RTK status >= FLOAT."""

    @property
    def state(self) -> tuple[float, float, float]:
        """Return (x, y, theta) — the fused pose estimate."""

    @property
    def velocity(self) -> tuple[float, float, float]:
        """Return (vx, vy, omega) — the fused velocity estimate."""

    @property
    def covariance(self) -> np.ndarray:
        """Return the 6×6 state covariance matrix."""

    def get_diagnostics(self) -> dict:
        """Return diagnostic dict for WS broadcast."""

    def update_config(self, config: dict) -> None:
        """Live-update noise parameters from dashboard tuning sliders."""

    def reset(self, x: float = 0, y: float = 0, theta: float = 0) -> None:
        """Reset state and covariance (e.g. after teleport)."""
```

### 3.9 NumPy Dependency

The EKF uses 6×6 matrix math. We'll use **numpy** for matrix operations.
numpy is already available in the ROS2 environment (dependency of many ROS
packages). If not present, we add it to `requirements.txt`.

---

## 4. GPS–Local Coordinate Converter

### 4.1 Purpose

Convert RTK GPS geodetic coordinates (lat/lon) to the Gazebo world frame (x/y
metres) so the EKF can fuse them with odometry.

### 4.2 Approach — Known Reference Point

The RTK GPS simulator already has known parameters that establish the mapping:

```
Base station geodetic:  lat=23.0225°, lon=72.5714°, alt=53.0 m
Base station world:     x=-12.0 m, y=5.0 m
```

This gives us a fixed reference point. For any GPS reading:

```python
# Step 1: Convert GPS reading and reference to ECEF
rover_ecef = geodetic_to_ecef(gps_lat, gps_lon, gps_alt)
base_ecef  = geodetic_to_ecef(BASE_LAT, BASE_LON, BASE_ALT)

# Step 2: Compute ENU offset from base to rover
delta_ecef = (rover_ecef[i] - base_ecef[i])  for i in 0,1,2
e, n, u = ecef_to_enu(delta_ecef, BASE_LAT, BASE_LON)

# Step 3: Convert ENU to Gazebo world frame
#   Gazebo X = East  → ENU East   + base_world_x offset
#   Gazebo Y = North → ENU North  + base_world_y offset
# BUT: We need to determine the ENU↔Gazebo axis mapping.
# In our world: Gazebo +X roughly aligns with ENU East,
#               Gazebo +Y roughly aligns with ENU North.
# The base station at known world coords establishes the offset.

gps_world_x = BASE_WORLD_X + e
gps_world_y = BASE_WORLD_Y + n
```

### 4.3 Implementation

The converter will be a simple class embedded in `ekf_engine.py`:

```python
class GPSLocalConverter:
    """Convert WGS-84 GPS coordinates to local Gazebo frame."""

    BASE_LAT = 23.0225
    BASE_LON = 72.5714
    BASE_ALT = 53.0
    BASE_WORLD_X = -12.0
    BASE_WORLD_Y = 5.0

    def __init__(self):
        self._base_ecef = geodetic_to_ecef(self.BASE_LAT, self.BASE_LON, self.BASE_ALT)

    def gps_to_local(self, lat: float, lon: float, alt: float) -> tuple[float, float]:
        """Convert (lat°, lon°, alt) → (gazebo_x, gazebo_y)."""

    def local_to_gps(self, x: float, y: float) -> tuple[float, float]:
        """Convert (gazebo_x, gazebo_y) → (lat°, lon°). Inverse for display."""
```

The WGS-84 math functions (`geodetic_to_ecef`, `ecef_to_enu`) will be copied from
`rtk_gps_simulator.py` (they're pure functions, ~30 lines) to avoid import
dependency on the ROS node.

### 4.4 Axis Mapping Validation

Before implementation, we must verify the ENU↔Gazebo axis alignment by:
1. Reading the vehicle's known spawn position in Gazebo world: `(-10, 0.9)`
2. Reading the GPS coordinates from `/gps/fix` when the vehicle is at spawn
3. Converting those GPS coords using the converter
4. Checking that the result matches `(-10, 0.9)` (within RTK noise)

If there's a rotation between ENU and Gazebo frames, we'll add a rotation
parameter. This will be validated during implementation testing.

---

## 5. Path Corrector

### 5.1 New file: `path_corrector.py`

Location: `simulation/gazebo/web_ui/path_corrector.py`

### 5.2 Purpose

During pattern and draw-path execution, the existing closed-loop odometry
feedback ensures each **segment** reaches its target distance/angle. But it
doesn't correct for **accumulated cross-track error** — the vehicle may drift
laterally from the intended path over multiple segments.

The PathCorrector monitors the fused pose against the intended trajectory and
applies small heading corrections to steer the vehicle back on track.

### 5.3 Algorithm

```
Cross-track error (CTE):
  Given current segment from point A to point B, and fused position P:
  CTE = signed perpendicular distance from P to line AB
  CTE > 0 means vehicle is to the left of the intended path

Heading correction:
  δθ = -Kp * CTE - Kd * d(CTE)/dt
  Applied as an additive angular velocity correction to cmd_vel
```

### 5.4 Class API

```python
class PathCorrector:
    """Cross-track error correction during path/pattern execution."""

    def __init__(self, kp: float = 0.5, kd: float = 0.1, max_correction: float = 0.3):
        """
        kp: Proportional gain for CTE correction (rad/s per metre)
        kd: Derivative gain for CTE rate damping
        max_correction: Maximum angular velocity correction (rad/s)
        """

    def set_segment(self, start_x: float, start_y: float,
                    end_x: float, end_y: float) -> None:
        """Set the current intended path segment."""

    def compute_correction(self, fused_x: float, fused_y: float,
                           fused_theta: float) -> float:
        """Return angular velocity correction (rad/s) to reduce CTE."""

    def get_diagnostics(self) -> dict:
        """Return CTE, correction magnitude, etc. for dashboard."""

    def reset(self) -> None:
        """Reset for new path/pattern."""

    @property
    def cross_track_error(self) -> float:
        """Current CTE in metres (signed)."""
```

### 5.5 Integration with VelocityRampingEngine

The PathCorrector is **optional** — it enhances accuracy but isn't required for
basic operation. It's applied as an additive angular velocity correction inside
the execute loop:

```python
# Inside VelocityRampingEngine.execute(), in the publish loop:
if path_corrector and seg_mode == 'straight':
    fx, fy, ftheta = odom_getter()
    correction_omega = path_corrector.compute_correction(fx, fy, ftheta)
    az = target_az + correction_omega  # Add correction to commanded angular vel
```

Only active during `straight` segments (no correction during `rotate` or `stop`).

---

## 6. Backend Integration

### 6.1 New Imports

```python
from sensor_msgs.msg import Imu, NavSatFix
from std_msgs.msg import String
import numpy as np

from ekf_engine import EKFEngine, GPSLocalConverter
from path_corrector import PathCorrector
```

### 6.2 New AppState Attributes

```python
class AppState:
    def __init__(self):
        # ... existing attributes ...

        # ── Sensor Fusion ──
        self.ekf = EKFEngine()
        self.gps_converter = GPSLocalConverter()
        self.path_corrector = PathCorrector()

        # Fused pose (replaces odom_x/y/theta for control)
        self.fused_x: float = 0.0
        self.fused_y: float = 0.0
        self.fused_theta: float = 0.0

        # Raw sensor caches (for diagnostics)
        self.raw_odom_x: float = 0.0
        self.raw_odom_y: float = 0.0
        self.raw_odom_theta: float = 0.0

        self.imu_yaw: float = 0.0
        self.imu_gyro_z: float = 0.0

        self.gps_local_x: float = 0.0
        self.gps_local_y: float = 0.0
        self.rtk_fix_state: str = 'SEARCHING'

        # IMU / GPS subscriptions
        self.imu_subscription = None
        self.gps_subscription = None
        self.rtk_status_subscription = None

        # EKF timing
        self.last_predict_time: float = 0.0

        # Sensor fusion enable flag (dashboard toggle)
        self.fusion_enabled: bool = True
```

### 6.3 Subscription Setup (in `startup()`)

```python
# IMU subscription (100 Hz from Gazebo, we process every message)
state.imu_subscription = state.node.create_subscription(
    Imu, '/imu', imu_callback, 10
)

# RTK GPS subscription (10 Hz corrected position)
state.gps_subscription = state.node.create_subscription(
    NavSatFix, '/gps/fix', gps_callback, 10
)

# RTK status (JSON diagnostics — for fix state tracking)
state.rtk_status_subscription = state.node.create_subscription(
    String, '/rtk/status', rtk_status_callback, 10
)
```

### 6.4 Callback Implementations

**Modified `odom_callback`:**

```python
def odom_callback(msg):
    # Existing kinematic center transform...
    # Store as raw odom
    state.raw_odom_x = center_x
    state.raw_odom_y = center_y
    state.raw_odom_theta = yaw

    if state.fusion_enabled:
        # EKF predict with odom velocity
        now = time.monotonic()
        dt = now - state.last_predict_time if state.last_predict_time > 0 else 0.02
        state.last_predict_time = now

        v_odom = msg.twist.twist.linear.x
        omega_odom = msg.twist.twist.angular.z

        state.ekf.predict(v_odom, omega_odom, state.imu_gyro_z, dt)
        state.ekf.update_odom(center_x, center_y, yaw)

        fx, fy, ftheta = state.ekf.state
        state.fused_x = fx
        state.fused_y = fy
        state.fused_theta = ftheta
    else:
        # Fusion disabled — pass through raw odom
        state.fused_x = center_x
        state.fused_y = center_y
        state.fused_theta = yaw

    # Keep backward compatibility: odom_x/y/theta now point to fused
    state.odom_x = state.fused_x
    state.odom_y = state.fused_y
    state.odom_theta = state.fused_theta
```

**New `imu_callback`:**

```python
def imu_callback(msg):
    # Extract gyro z (with dead-zone)
    gz = msg.angular_velocity.z
    GYRO_DEADZONE = 0.005
    state.imu_gyro_z = gz if abs(gz) > GYRO_DEADZONE else 0.0

    # Extract yaw from quaternion (for heading reference check)
    state.imu_yaw = _quaternion_to_yaw(
        msg.orientation.x, msg.orientation.y,
        msg.orientation.z, msg.orientation.w
    )
```

**New `gps_callback`:**

```python
def gps_callback(msg):
    # Convert GPS to local frame
    local_x, local_y = state.gps_converter.gps_to_local(
        msg.latitude, msg.longitude, msg.altitude
    )
    state.gps_local_x = local_x
    state.gps_local_y = local_y

    # Only update EKF if RTK status is good enough
    if state.fusion_enabled and state.rtk_fix_state in ('FLOAT', 'RTK_FIXED'):
        cov_x = msg.position_covariance[0]
        cov_y = msg.position_covariance[4]
        state.ekf.update_gps(local_x, local_y, cov_x, cov_y)

        # Re-read fused state after GPS update
        fx, fy, ftheta = state.ekf.state
        state.fused_x = fx
        state.fused_y = fy
        state.fused_theta = ftheta
        state.odom_x = fx
        state.odom_y = fy
        state.odom_theta = ftheta
```

**New `rtk_status_callback`:**

```python
def rtk_status_callback(msg):
    import json
    try:
        data = json.loads(msg.data)
        state.rtk_fix_state = data.get('fix_state', 'SEARCHING')
    except Exception:
        pass
```

### 6.5 EKF Status Broadcast

A periodic broadcast (2 Hz) sends fusion diagnostics to the dashboard:

```python
# In spin_loop, every 500ms:
ekf_diag = state.ekf.get_diagnostics()
ekf_diag.update({
    'type': 'ekf_status',
    'fusion_enabled': state.fusion_enabled,
    'rtk_fix_state': state.rtk_fix_state,
    'fused_x': round(state.fused_x, 4),
    'fused_y': round(state.fused_y, 4),
    'fused_theta': round(state.fused_theta, 4),
    'raw_odom_x': round(state.raw_odom_x, 4),
    'raw_odom_y': round(state.raw_odom_y, 4),
    'raw_odom_theta': round(state.raw_odom_theta, 4),
    'gps_local_x': round(state.gps_local_x, 4),
    'gps_local_y': round(state.gps_local_y, 4),
    'drift_x': round(state.fused_x - state.raw_odom_x, 4),
    'drift_y': round(state.fused_y - state.raw_odom_y, 4),
    'drift_theta': round(state.fused_theta - state.raw_odom_theta, 4),
})
await broadcast(ekf_diag)
```

### 6.6 odom_getter Update

No change needed — since `state.odom_x/y/theta` now points to the fused pose,
the existing `odom_getter` lambda in `_handle_start_pattern` and `_handle_draw_path`
automatically uses the fused position:

```python
odom_getter=lambda: (state.odom_x, state.odom_y, state.odom_theta)
```

### 6.7 New WebSocket Message Handlers

| Message Type (from client) | Action |
|---------------------------|--------|
| `toggle_fusion` | Toggle `state.fusion_enabled` on/off |
| `update_ekf_config` | Live-update EKF noise parameters |
| `reset_ekf` | Reset EKF state to current odom position |

```python
elif msg_type == 'toggle_fusion':
    state.fusion_enabled = data.get('enabled', True)
    await ws.send_json({'type': 'fusion_toggled', 'enabled': state.fusion_enabled})

elif msg_type == 'update_ekf_config':
    config = data.get('config', {})
    state.ekf.update_config(config)
    await ws.send_json({'type': 'ekf_config_updated', 'config': config})

elif msg_type == 'reset_ekf':
    state.ekf.reset(state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)
    state.fused_x = state.raw_odom_x
    state.fused_y = state.raw_odom_y
    state.fused_theta = state.raw_odom_theta
    await ws.send_json({'type': 'ekf_reset'})
```

### 6.8 Teleport Handling

When the robot is teleported (via `_handle_start_pattern` which calls
`teleport_robot()`), the EKF must be reset to avoid a huge innovation spike:

```python
# After teleport, wait briefly for odom to settle, then:
await asyncio.sleep(0.5)
state.ekf.reset(state.raw_odom_x, state.raw_odom_y, state.raw_odom_theta)
```

### 6.9 Removal of Dead Code

The function `_compensate_kinematics_caps()` (line ~80 in backend.py) is no
longer used since closed-loop odom feedback replaced it. It will be removed
during implementation to reduce confusion.

---

## 7. Dashboard UI Changes

### 7.1 New HTML Section (in `index.html`)

Add a new sensor group inside `#sensor-panel`, after the RTK panel and before
the Odometry panel:

```html
<!-- Sensor Fusion / EKF Sub-panel -->
<div class="sensor-group" id="ekf-panel">
    <h4>Sensor Fusion (EKF)
        <label class="sensor-toggle">
            <input type="checkbox" id="ekf-toggle" checked>
            <span class="toggle-slider"></span>
        </label>
    </h4>

    <!-- Status Badge -->
    <div class="ekf-status-bar">
        <span class="ekf-mode-badge" id="ekf-mode-badge">INITIALIZING</span>
        <span class="ekf-sources" id="ekf-sources">Odom+IMU</span>
    </div>

    <!-- Fused Position -->
    <div class="ekf-section">
        <span class="ekf-section-title">Fused Position</span>
        <div class="sensor-row">
            <span class="sensor-label">X:</span>
            <span id="ekf-fused-x" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">Y:</span>
            <span id="ekf-fused-y" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">Heading:</span>
            <span id="ekf-fused-heading" class="sensor-value">--</span>
            <span class="sensor-unit">deg</span>
        </div>
    </div>

    <!-- Drift (fused - raw odom) -->
    <div class="ekf-section">
        <span class="ekf-section-title">Odom Drift Correction</span>
        <div class="sensor-row">
            <span class="sensor-label">ΔX:</span>
            <span id="ekf-drift-x" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">ΔY:</span>
            <span id="ekf-drift-y" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">Δθ:</span>
            <span id="ekf-drift-theta" class="sensor-value">--</span>
            <span class="sensor-unit">deg</span>
        </div>
    </div>

    <!-- GPS in Local Frame -->
    <div class="ekf-section">
        <span class="ekf-section-title">GPS → Local</span>
        <div class="sensor-row">
            <span class="sensor-label">X:</span>
            <span id="ekf-gps-x" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">Y:</span>
            <span id="ekf-gps-y" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
    </div>

    <!-- Covariance / Confidence -->
    <div class="ekf-section">
        <span class="ekf-section-title">Uncertainty (1σ)</span>
        <div class="sensor-row">
            <span class="sensor-label">σ_x:</span>
            <span id="ekf-sigma-x" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">σ_y:</span>
            <span id="ekf-sigma-y" class="sensor-value">--</span>
            <span class="sensor-unit">m</span>
        </div>
        <div class="sensor-row">
            <span class="sensor-label">σ_θ:</span>
            <span id="ekf-sigma-theta" class="sensor-value">--</span>
            <span class="sensor-unit">deg</span>
        </div>
    </div>

    <!-- Tuning Sliders (collapsible) -->
    <details class="ekf-tuning">
        <summary>Tuning Parameters</summary>
        <div class="ekf-tuning-content">
            <div class="slider-row">
                <label>IMU Weight (α):</label>
                <input type="range" id="ekf-alpha-imu" min="0" max="1" step="0.05" value="0.7">
                <span id="ekf-alpha-imu-val">0.70</span>
            </div>
            <div class="slider-row">
                <label>Q Position:</label>
                <input type="range" id="ekf-q-pos" min="0.001" max="0.1" step="0.001" value="0.01">
                <span id="ekf-q-pos-val">0.010</span>
            </div>
            <div class="slider-row">
                <label>Q Heading:</label>
                <input type="range" id="ekf-q-theta" min="0.001" max="0.05" step="0.001" value="0.005">
                <span id="ekf-q-theta-val">0.005</span>
            </div>
            <div class="slider-row">
                <label>R Odom Pos:</label>
                <input type="range" id="ekf-r-odom" min="0.01" max="0.5" step="0.01" value="0.05">
                <span id="ekf-r-odom-val">0.050</span>
            </div>
            <div class="slider-row">
                <label>GPS Floor:</label>
                <input type="range" id="ekf-gps-floor" min="0.001" max="0.1" step="0.001" value="0.01">
                <span id="ekf-gps-floor-val">0.010</span>
            </div>
            <button id="ekf-apply-tuning" class="btn btn-small">Apply</button>
            <button id="ekf-reset-btn" class="btn btn-small btn-danger">Reset EKF</button>
        </div>
    </details>
</div>
```

### 7.2 New CSS (in `style.css`)

```css
/* ── EKF / Sensor Fusion Panel ── */
.ekf-status-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.ekf-mode-badge {
    padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;
    background: #444; color: #aaa;
}
.ekf-mode-badge.odom-only { background: #664400; color: #ffcc00; }
.ekf-mode-badge.odom-imu  { background: #004466; color: #66ccff; }
.ekf-mode-badge.full-fusion { background: #006633; color: #66ff99; }
.ekf-sources { font-size: 0.75rem; color: #888; }
.ekf-section { margin-top: 4px; }
.ekf-section-title { font-size: 0.7rem; color: #888; text-transform: uppercase; }

.ekf-tuning { margin-top: 8px; }
.ekf-tuning summary { cursor: pointer; font-size: 0.8rem; color: #aaa; }
.ekf-tuning-content { padding: 8px 0; }
.slider-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 0.75rem; }
.slider-row label { min-width: 100px; }
.slider-row input[type="range"] { flex: 1; }
.slider-row span { min-width: 40px; text-align: right; }
```

### 7.3 New JavaScript (in `app.js`)

```javascript
// ── EKF Status Handler ──
// Listen for ekf_status messages from WebSocket (backend → client)

function handleEkfStatus(data) {
    if (!data) return;

    // Mode badge
    var badge = document.getElementById('ekf-mode-badge');
    var sources = document.getElementById('ekf-sources');
    if (data.rtk_fix_state === 'RTK_FIXED' || data.rtk_fix_state === 'FLOAT') {
        badge.textContent = 'FULL FUSION';
        badge.className = 'ekf-mode-badge full-fusion';
        sources.textContent = 'Odom + IMU + GPS';
    } else if (data.fusion_enabled) {
        badge.textContent = 'ODOM + IMU';
        badge.className = 'ekf-mode-badge odom-imu';
        sources.textContent = 'Odom + IMU (no GPS)';
    } else {
        badge.textContent = 'ODOM ONLY';
        badge.className = 'ekf-mode-badge odom-only';
        sources.textContent = 'Raw odometry';
    }

    // Fused position
    setText('ekf-fused-x', data.fused_x, 3);
    setText('ekf-fused-y', data.fused_y, 3);
    setText('ekf-fused-heading', (data.fused_theta * 180 / Math.PI).toFixed(1));

    // Drift correction
    setText('ekf-drift-x', data.drift_x, 4);
    setText('ekf-drift-y', data.drift_y, 4);
    setText('ekf-drift-theta', (data.drift_theta * 180 / Math.PI).toFixed(2));

    // GPS local
    setText('ekf-gps-x', data.gps_local_x, 3);
    setText('ekf-gps-y', data.gps_local_y, 3);

    // Uncertainty (square root of covariance diagonal)
    if (data.covariance_diag) {
        setText('ekf-sigma-x', Math.sqrt(data.covariance_diag[0]).toFixed(4));
        setText('ekf-sigma-y', Math.sqrt(data.covariance_diag[1]).toFixed(4));
        setText('ekf-sigma-theta', (Math.sqrt(data.covariance_diag[2]) * 180 / Math.PI).toFixed(2));
    }
}

function setText(id, val, decimals) {
    var el = document.getElementById(id);
    if (el) el.textContent = (typeof val === 'number') ? val.toFixed(decimals || 3) : val;
}
```

**EKF toggle handler:**

```javascript
document.getElementById('ekf-toggle').addEventListener('change', function() {
    ws.send(JSON.stringify({ type: 'toggle_fusion', enabled: this.checked }));
});
```

**Tuning sliders:**

```javascript
document.getElementById('ekf-apply-tuning').addEventListener('click', function() {
    ws.send(JSON.stringify({
        type: 'update_ekf_config',
        config: {
            alpha_imu: parseFloat(document.getElementById('ekf-alpha-imu').value),
            q_pos: parseFloat(document.getElementById('ekf-q-pos').value),
            q_theta: parseFloat(document.getElementById('ekf-q-theta').value),
            r_odom_pos: parseFloat(document.getElementById('ekf-r-odom').value),
            r_gps_floor: parseFloat(document.getElementById('ekf-gps-floor').value),
        }
    }));
});
```

### 7.4 Odometry Trail Enhancement

The existing odom trail mini-map will be enhanced to show **two trails**:
- **Blue trail:** Fused position (primary)
- **Gray trail:** Raw odometry (for drift comparison)

The GPS position will be shown as a **green dot** on the trail map.

---

## 8. WebSocket Protocol

### 8.1 Server → Client Messages

| Type | Fields | Rate | Description |
|------|--------|------|-------------|
| `ekf_status` | `fusion_enabled`, `rtk_fix_state`, `fused_x/y/theta`, `raw_odom_x/y/theta`, `gps_local_x/y`, `drift_x/y/theta`, `covariance_diag[6]`, `alpha_imu`, `sensors_active` | 2 Hz | Fusion diagnostics |
| `fusion_toggled` | `enabled` | On toggle | Confirm fusion toggle |
| `ekf_config_updated` | `config` | On change | Confirm config update |
| `ekf_reset` | — | On reset | Confirm EKF reset |

### 8.2 Client → Server Messages

| Type | Fields | Description |
|------|--------|-------------|
| `toggle_fusion` | `enabled: bool` | Enable/disable sensor fusion |
| `update_ekf_config` | `config: {alpha_imu, q_pos, q_theta, r_odom_pos, r_gps_floor}` | Update EKF tuning |
| `reset_ekf` | — | Reset EKF to current odom pose |

---

## 9. Behavior Matrix

| Mode | Fusion Active? | GPS Used? | Path Corrector? | Notes |
|------|---------------|-----------|-----------------|-------|
| **Manual** | Yes | When available | No | Fused heading stabilises manual driving; dashboard shows drift |
| **Pattern** | Yes | When available | Yes (straight segments) | Closed-loop uses fused pose; CTE correction on straights |
| **Precision Move** | Yes | When available | No | Single-segment; fused pose for distance/angle tracking |
| **Draw Path** | Yes | When available | Yes (straight segments) | Same as pattern |
| **Idle** | Yes | When available | No | EKF runs continuously; baseline drift tracking |
| **Fusion Disabled** | No | No | No | Falls back to raw odom (existing behavior) |

**Degradation modes:**

| Condition | Behavior |
|-----------|----------|
| RTK SEARCHING / NO_FIX | Odom + IMU only (no GPS update) |
| RTK FLOAT | GPS update with higher noise (0.16 m² covariance) |
| RTK FIXED | Full GPS update (0.000225 m² covariance) |
| RTK Dropout (DGPS) | GPS update suspended; Odom + IMU dead-reckoning |
| IMU lost | Odom-only predict (ω_imu defaults to 0, α_imu ignored) |
| Odom lost | EKF stops predicting; last fused pose held |

---

## 10. Constants & Tuning Parameters

All tuneable from dashboard sliders and persisted in the EKF config dict:

| Parameter | Key | Default | Range | Description |
|-----------|-----|---------|-------|-------------|
| IMU yaw weight | `alpha_imu` | 0.7 | 0.0–1.0 | Weight of IMU gyro vs odom angular vel in predict |
| Process noise: position | `q_pos` | 0.01 | 0.001–0.1 | m²/s |
| Process noise: heading | `q_theta` | 0.005 | 0.001–0.05 | rad²/s |
| Process noise: velocity | `q_vel` | 0.1 | 0.01–0.5 | (m/s)²/s |
| Process noise: yaw rate | `q_omega` | 0.05 | 0.01–0.2 | (rad/s)²/s |
| Odom measurement noise: pos | `r_odom_pos` | 0.05 | 0.01–0.5 | m² |
| Odom measurement noise: heading | `r_odom_theta` | 0.02 | 0.005–0.1 | rad² |
| GPS noise floor | `r_gps_floor` | 0.01 | 0.001–0.1 | m² (minimum) |
| Path corrector Kp | `cte_kp` | 0.5 | 0.0–2.0 | rad/s per m |
| Path corrector Kd | `cte_kd` | 0.1 | 0.0–1.0 | rad/s per m/s |
| Path corrector max | `cte_max` | 0.3 | 0.1–1.0 | rad/s |
| Heading divergence threshold | `heading_div_thresh` | 0.35 | 0.1–1.0 | rad |
| Heading divergence timeout | `heading_div_timeout` | 2.0 | 0.5–5.0 | s |

---

## 11. Files Created / Modified

### New Files

| File | Location | Purpose | LOC (est.) |
|------|----------|---------|------------|
| `ekf_engine.py` | `web_ui/ekf_engine.py` | EKF state estimation + GPS converter + WGS-84 math | ~250 |
| `path_corrector.py` | `web_ui/path_corrector.py` | Cross-track error PD controller | ~80 |
| `ADVANCED_CONTROLLER_SPEC.md` | `web_ui/` | This document | — |

### Modified Files

| File | Changes |
|------|---------|
| `web_ui/backend.py` | New imports; new callbacks (IMU, GPS, RTK status); modified odom_callback; new AppState attrs; EKF status broadcast in spin_loop; new WS message handlers; teleport reset; remove `_compensate_kinematics_caps()` |
| `web_ui/index.html` | New `#ekf-panel` HTML section (sensor fusion card with status, values, tuning sliders) |
| `web_ui/style.css` | EKF panel styles (badge, sections, sliders) |
| `web_ui/app.js` | EKF status handler; toggle/tuning WS senders; dual-trail odom map; `handleEkfStatus()` in WS message dispatch |

### Files NOT Modified

See Section 12.

---

## 12. Do-Not-Touch List

These files will **not** be modified:

- `vehicle.urdf` — Sensor configuration is already correct  
- `kinematics_node.py` — Speed caps and steering filters stay as-is  
- `rtk_gps_simulator.py` — RTK simulation pipeline is complete  
- `gazebo_sensors.launch.py` — All needed bridges already configured  
- `sim_editor.html` / `sim_editor.css` / `sim_editor.js` — Field editor is independent  
- `demo_patterns.py` — Pattern library unchanged  
- Any file under `core/`, `hardware/`, `integration/`, `config/`  

---

## 13. Testing Plan

### 13.1 Unit Tests

| Test | Method |
|------|--------|
| EKF predict produces correct state | Feed known v, ω, dt; check x/y/θ |
| EKF odom update converges | Feed noisy odom; check covariance shrinks |
| EKF GPS update pulls position toward GPS | Feed offset GPS; check state moves |
| GPS converter round-trip | Convert known coords both directions |
| Path corrector CTE calculation | Feed known geometry; verify CTE sign and magnitude |
| Angle wrapping in innovation | Test θ near ±π boundaries |

### 13.2 Integration Tests (Manual, in Gazebo)

| Test | Procedure | Pass Criteria |
|------|-----------|---------------|
| Fusion starts up | Launch system; check EKF panel shows "ODOM + IMU" | Badge shows blue, values updating |
| GPS convergence | Wait 30s for RTK Fixed; check panel switches to "FULL FUSION" | Badge turns green |
| Drift tracking | Drive manually for 2 min; check drift values | ΔX, ΔY non-zero and reasonable |
| Pattern accuracy | Run S-pattern; compare fused vs raw end position | Fused closer to expected than raw |
| Fusion toggle | Disable EKF via toggle; verify odom trail matches raw | Trail matches raw odom exactly |
| Teleport reset | Start pattern (which teleports); check EKF resets | No position jump in trail |
| GPS dropout | Wait for simulated dropout; check degrades to ODOM+IMU | Badge changes; resumes after |
| Tuning sliders | Adjust α_imu; check immediate effect | Heading becomes more/less IMU-influenced |

---

## 14. Rollback Strategy

If sensor fusion causes issues:

1. **Dashboard toggle:** User can instantly disable fusion via the EKF toggle checkbox.  
   When disabled, `state.odom_x/y/theta` reverts to raw odometry — identical to
   pre-implementation behavior.

2. **Code rollback:** All new code is in `ekf_engine.py` and `path_corrector.py`.
   Removing the EKF callbacks and reverting the odom_callback to its original form
   restores the previous system entirely.

3. **No sensor changes:** We don't modify URDF, launch files, or the kinematics
   node. The sensor pipeline is unchanged.

---

## Appendix A: Mathematical Reference

### A.1 Kinematic Center Transform (existing, unchanged)

```
center_x = odom_x + 0.65·cos(θ) + 0.90·sin(θ)
center_y = odom_y + 0.65·sin(θ) − 0.90·cos(θ)
```

Where `(odom_x, odom_y, θ)` is the raw base-v1 odometry pose.

### A.2 WGS-84 → ECEF

```
N = a / √(1 − e²·sin²(φ))
X = (N + h)·cos(φ)·cos(λ)
Y = (N + h)·cos(φ)·sin(λ)
Z = (N·(1−e²) + h)·sin(φ)
```

### A.3 ECEF → ENU

```
Δ = [ΔX, ΔY, ΔZ]  (ECEF delta from reference)
E = −sin(λ)·ΔX + cos(λ)·ΔY
N = −sin(φ)·cos(λ)·ΔX − sin(φ)·sin(λ)·ΔY + cos(φ)·ΔZ
U =  cos(φ)·cos(λ)·ΔX + cos(φ)·sin(λ)·ΔY + sin(φ)·ΔZ
```

### A.4 Cross-Track Error

For segment from A to B, vehicle at P:

```
AB = B − A
AP = P − A
CTE = (AP × AB) / |AB|    (2D cross product gives signed distance)
```

Positive CTE = vehicle is to the left of A→B direction.

---

*End of specification. Awaiting review and approval before implementation.*
