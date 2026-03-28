#!/usr/bin/env python3
"""
EKF Sensor Fusion Engine — Odom + IMU + RTK GPS

Implements a 6-state Extended Kalman Filter that fuses:
  • Wheel odometry  (50 Hz predict + update)
  • IMU gyroscope   (blended into predict as yaw-rate reference)
  • RTK GPS         (10 Hz position update, only when fix ≥ FLOAT)

State vector:  x = [x, y, θ, vx, vy, ω]ᵀ

Also includes a GPS↔local coordinate converter using a known reference
point (RTK base station at surveyed geodetic + Gazebo world coordinates).
"""

from __future__ import annotations

import math
import time
from typing import Optional

import numpy as np

# ─── WGS-84 constants (copied from rtk_gps_simulator.py) ──────────
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_E2 = 1.0 - (WGS84_B ** 2) / (WGS84_A ** 2)


# ─── Coordinate conversion helpers ─────────────────────────────────

def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt: float) -> tuple[float, float, float]:
    """WGS-84 (lat°, lon°, alt_m) → ECEF (x, y, z) metres."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    N = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat ** 2)
    x = (N + alt) * cos_lat * cos_lon
    y = (N + alt) * cos_lat * sin_lon
    z = (N * (1.0 - WGS84_E2) + alt) * sin_lat
    return x, y, z


def ecef_to_enu(dx: float, dy: float, dz: float,
                ref_lat_deg: float, ref_lon_deg: float) -> tuple[float, float, float]:
    """ECEF delta → ENU (East, North, Up) relative to a reference point."""
    lat = math.radians(ref_lat_deg)
    lon = math.radians(ref_lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    e = -sin_lon * dx + cos_lon * dy
    n = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    u = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    return e, n, u


# ─── GPS ↔ Local Coordinate Converter ──────────────────────────────

class GPSLocalConverter:
    """Convert between WGS-84 GPS coordinates and Gazebo local frame.

    Uses a known reference point (the RTK base station) whose geodetic
    AND Gazebo-world coordinates are both known, establishing the mapping.
    """

    def __init__(self,
                 base_lat: float = 23.0225,
                 base_lon: float = 72.5714,
                 base_alt: float = 53.0,
                 base_world_x: float = 0.0,
                 base_world_y: float = 0.0):
        self.base_lat = base_lat
        self.base_lon = base_lon
        self.base_alt = base_alt
        self.base_world_x = base_world_x
        self.base_world_y = base_world_y
        self._base_ecef = geodetic_to_ecef(base_lat, base_lon, base_alt)

    def gps_to_local(self, lat: float, lon: float, alt: float = 53.0) -> tuple[float, float]:
        """Convert (lat°, lon°, alt) → (gazebo_x, gazebo_y).

        Steps:
          1. Convert rover GPS to ECEF
          2. Compute ECEF delta from base station
          3. Convert delta to ENU
          4. Map ENU (East→X, North→Y) + base world offset
        """
        rover_ecef = geodetic_to_ecef(lat, lon, alt)
        dx = rover_ecef[0] - self._base_ecef[0]
        dy = rover_ecef[1] - self._base_ecef[1]
        dz = rover_ecef[2] - self._base_ecef[2]
        e, n, _u = ecef_to_enu(dx, dy, dz, self.base_lat, self.base_lon)
        # ENU East → Gazebo X, ENU North → Gazebo Y
        return self.base_world_x + e, self.base_world_y + n

    def local_to_gps(self, x: float, y: float) -> tuple[float, float]:
        """Convert (gazebo_x, gazebo_y) → (lat°, lon°). Approximate inverse."""
        # Offset from base in ENU
        e = x - self.base_world_x
        n = y - self.base_world_y
        lat_rad = math.radians(self.base_lat)
        N = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(lat_rad) ** 2)
        M = WGS84_A * (1.0 - WGS84_E2) / (1.0 - WGS84_E2 * math.sin(lat_rad) ** 2) ** 1.5
        d_lat = n / M
        d_lon = e / (N * math.cos(lat_rad))
        return self.base_lat + math.degrees(d_lat), self.base_lon + math.degrees(d_lon)


# ─── Default EKF Configuration ─────────────────────────────────────

DEFAULT_EKF_CONFIG = {
    # IMU gyro weight in predict (0=odom-only, 1=IMU-only)
    'alpha_imu': 0.7,

    # Process noise (per second)
    'q_pos': 0.01,       # m²/s  — position
    'q_theta': 0.005,    # rad²/s — heading
    'q_vel': 0.1,        # (m/s)²/s — velocity
    'q_omega': 0.05,     # (rad/s)²/s — yaw rate

    # Odom measurement noise
    'r_odom_pos': 0.05,    # m²
    'r_odom_theta': 0.02,  # rad²

    # GPS measurement noise floor
    'r_gps_floor': 0.01,   # m² minimum

    # Heading divergence alert
    'heading_div_thresh': 0.35,   # rad
    'heading_div_timeout': 2.0,   # seconds
}


def _wrap_angle(a: float) -> float:
    """Normalise angle to [-π, π]."""
    return math.atan2(math.sin(a), math.cos(a))


# ─── Extended Kalman Filter ────────────────────────────────────────

class EKFEngine:
    """6-state Extended Kalman Filter for Odom + IMU + GPS fusion.

    State: [x, y, θ, vx, vy, ω]
    """

    N_STATES = 6

    # Observation matrices (constant)
    _H_ODOM = np.zeros((3, 6))
    _H_ODOM[0, 0] = 1.0  # x
    _H_ODOM[1, 1] = 1.0  # y
    _H_ODOM[2, 2] = 1.0  # θ

    _H_GPS = np.zeros((2, 6))
    _H_GPS[0, 0] = 1.0  # x
    _H_GPS[1, 1] = 1.0  # y

    # Velocity threshold below which we consider the robot stationary
    _STATIC_V_THRESH = 0.02    # m/s
    _STATIC_W_THRESH = 0.01    # rad/s

    def __init__(self, config: dict | None = None):
        self._cfg = dict(DEFAULT_EKF_CONFIG)
        if config:
            self._cfg.update(config)

        # State vector
        self._x = np.zeros(self.N_STATES)

        # Covariance matrix — start with moderate uncertainty
        self._P = np.diag([1.0, 1.0, 0.1, 0.5, 0.5, 0.1])

        # Identity matrix (cached)
        self._I = np.eye(self.N_STATES)

        # Whether we have received the first odom to seed state
        self._initialized = False

        # Diagnostics
        self._last_predict_time = 0.0
        self._predict_count = 0
        self._odom_update_count = 0
        self._gps_update_count = 0
        self._last_innovation_odom = np.zeros(3)
        self._last_innovation_gps = np.zeros(2)
        self._heading_div_start: Optional[float] = None
        self._heading_diverged = False
        self._imu_heading_ref: Optional[float] = None

    # ── Predict ─────────────────────────────────────────────────────

    def initialize_from_odom(self, x: float, y: float, theta: float) -> None:
        """Seed the EKF state from the first odometry reading.

        Must be called once before predict/update to avoid a large
        initial innovation from state [0,0,0].
        """
        if not self._initialized:
            self._x = np.array([x, y, theta, 0.0, 0.0, 0.0])
            self._P = np.diag([0.01, 0.01, 0.005, 0.1, 0.1, 0.05])
            self._initialized = True

    def predict(self, v_odom: float, omega_odom: float,
                omega_imu: float, dt: float) -> None:
        """Predict step using kinematic-center velocity + IMU gyro.

        Called at odom rate (~50 Hz).
        *v_odom* must be the KINEMATIC-CENTER forward velocity
        (caller subtracts KC_LAT * omega from raw odom linear.x before
        passing here — see odom_callback in backend.py).

        Ackermann assumption: KC lateral velocity = 0 (no sideways slip).
        Skips position update when nearly stationary to prevent
        process-noise drift.
        """
        if dt <= 0 or dt > 1.0:
            return  # Skip invalid dt
        if not self._initialized:
            return  # Wait for initialization from first odom

        alpha = self._cfg['alpha_imu']
        # Fuse odom and IMU yaw rates
        omega_fused = alpha * omega_imu + (1.0 - alpha) * omega_odom

        x, y, theta, vx, vy, omega = self._x

        # New velocity estimates
        vx_new = v_odom        # KC forward velocity (KC_LAT correction applied by caller)
        vy_new = 0.0           # Ackermann: KC has no lateral velocity
        omega_new = omega_fused

        # Skip position prediction when the KC is stationary.
        # With correct v_kc_x ≈ 0 during in-place turns,
        # this only fires when truly stopped (v AND omega both near zero).
        truly_static = (
            abs(vx_new) < self._STATIC_V_THRESH and
            abs(omega_odom) < self._STATIC_W_THRESH and
            abs(omega_imu) < self._STATIC_W_THRESH
        )

        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        if truly_static:
            # Still update velocity state — heading is unchanged
            self._x = np.array([x, y, theta, vx_new, vy_new, omega_new])
            self._predict_count += 1
            return

        # ── Kinematic prediction (use NEW measured velocity, not stale state) ──
        x_new = x + (vx_new * cos_t - vy_new * sin_t) * dt
        y_new = y + (vx_new * sin_t + vy_new * cos_t) * dt
        theta_new = _wrap_angle(theta + omega_fused * dt)

        # Update state
        self._x = np.array([x_new, y_new, theta_new, vx_new, vy_new, omega_new])

        # ── Jacobian F (linearised at new velocity measurement) ─────
        F = np.eye(self.N_STATES)
        F[0, 2] = (-vx_new * sin_t - vy_new * cos_t) * dt
        F[0, 3] = cos_t * dt
        F[0, 4] = -sin_t * dt
        F[1, 2] = (vx_new * cos_t - vy_new * sin_t) * dt
        F[1, 3] = sin_t * dt
        F[1, 4] = cos_t * dt
        F[2, 5] = dt

        # ── Process noise Q ────────────────────────────────────────
        cfg = self._cfg
        Q = np.diag([
            cfg['q_pos'] * dt,
            cfg['q_pos'] * dt,
            cfg['q_theta'] * dt,
            cfg['q_vel'] * dt,
            cfg['q_vel'] * dt,
            cfg['q_omega'] * dt,
        ])

        # Covariance prediction
        self._P = F @ self._P @ F.T + Q

        self._predict_count += 1

    # ── Update: Odometry ────────────────────────────────────────────

    def update_odom(self, x: float, y: float, theta: float) -> None:
        """Update with odometry position measurement (kinematic center)."""
        if not self._initialized:
            return
        z = np.array([x, y, theta])
        H = self._H_ODOM

        cfg = self._cfg
        R = np.diag([cfg['r_odom_pos'], cfg['r_odom_pos'], cfg['r_odom_theta']])

        # Innovation
        y_innov = z - H @ self._x
        y_innov[2] = _wrap_angle(y_innov[2])  # Wrap heading innovation

        # Innovation covariance
        S = H @ self._P @ H.T + R

        # Kalman gain
        try:
            K = self._P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return  # Singular matrix — skip this update

        # State update
        self._x = self._x + K @ y_innov
        self._x[2] = _wrap_angle(self._x[2])

        # Covariance update (Joseph form for numerical stability)
        IKH = self._I - K @ H
        self._P = IKH @ self._P @ IKH.T + K @ R @ K.T

        self._last_innovation_odom = y_innov
        self._odom_update_count += 1

    # ── Update: GPS ─────────────────────────────────────────────────

    def update_gps(self, gps_x: float, gps_y: float,
                   cov_x: float, cov_y: float) -> None:
        """Update with GPS position in local frame.

        Only call when RTK status ≥ FLOAT.
        """
        if not self._initialized:
            return
        z = np.array([gps_x, gps_y])
        H = self._H_GPS

        floor = self._cfg['r_gps_floor']
        R = np.diag([max(cov_x, floor), max(cov_y, floor)])

        # Innovation
        y_innov = z - H @ self._x

        # Innovation covariance
        S = H @ self._P @ H.T + R

        # Kalman gain
        try:
            K = self._P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return

        # State update
        self._x = self._x + K @ y_innov
        self._x[2] = _wrap_angle(self._x[2])

        # Covariance update (Joseph form)
        IKH = self._I - K @ H
        self._P = IKH @ self._P @ IKH.T + K @ R @ K.T

        self._last_innovation_gps = y_innov
        self._gps_update_count += 1

    # ── Heading Reference Check ─────────────────────────────────────

    def check_heading_divergence(self, imu_yaw: float) -> bool:
        """Check if EKF heading diverges from IMU heading reference.

        Returns True if diverged for longer than the timeout.
        """
        self._imu_heading_ref = imu_yaw
        heading_diff = abs(_wrap_angle(self._x[2] - imu_yaw))

        if heading_diff > self._cfg['heading_div_thresh']:
            if self._heading_div_start is None:
                self._heading_div_start = time.monotonic()
            elif time.monotonic() - self._heading_div_start > self._cfg['heading_div_timeout']:
                self._heading_diverged = True
                return True
        else:
            self._heading_div_start = None
            self._heading_diverged = False

        return False

    # ── Properties ──────────────────────────────────────────────────

    @property
    def state(self) -> tuple[float, float, float]:
        """Return (x, y, theta) — the fused pose estimate."""
        return float(self._x[0]), float(self._x[1]), float(self._x[2])

    @property
    def velocity(self) -> tuple[float, float, float]:
        """Return (vx, vy, omega) — the fused velocity estimate."""
        return float(self._x[3]), float(self._x[4]), float(self._x[5])

    @property
    def covariance(self) -> np.ndarray:
        """Return the 6×6 state covariance matrix."""
        return self._P.copy()

    @property
    def covariance_diagonal(self) -> list[float]:
        """Return the diagonal of the covariance as a list (for JSON)."""
        return [float(v) for v in np.diag(self._P)]

    # ── Diagnostics ─────────────────────────────────────────────────

    def get_diagnostics(self) -> dict:
        """Return diagnostic dict for WS broadcast."""
        cov_diag = self.covariance_diagonal
        return {
            'predict_count': self._predict_count,
            'odom_update_count': self._odom_update_count,
            'gps_update_count': self._gps_update_count,
            'covariance_diag': cov_diag,
            'sigma_x': math.sqrt(max(cov_diag[0], 0)),
            'sigma_y': math.sqrt(max(cov_diag[1], 0)),
            'sigma_theta': math.sqrt(max(cov_diag[2], 0)),
            'innovation_odom': [float(v) for v in self._last_innovation_odom],
            'innovation_gps': [float(v) for v in self._last_innovation_gps],
            'heading_diverged': self._heading_diverged,
            'imu_heading_ref': self._imu_heading_ref,
            'alpha_imu': self._cfg['alpha_imu'],
        }

    # ── Configuration ───────────────────────────────────────────────

    def update_config(self, config: dict) -> None:
        """Live-update noise parameters from dashboard tuning sliders."""
        for key in config:
            if key in self._cfg:
                self._cfg[key] = float(config[key])

    def get_config(self) -> dict:
        """Return current configuration."""
        return dict(self._cfg)

    # ── Reset ───────────────────────────────────────────────────────

    def reset(self, x: float = 0.0, y: float = 0.0, theta: float = 0.0) -> None:
        """Reset state and covariance (e.g. after teleport)."""
        self._x = np.array([x, y, theta, 0.0, 0.0, 0.0])
        self._P = np.diag([0.01, 0.01, 0.005, 0.1, 0.1, 0.05])
        self._initialized = True  # Keep initialized after reset
        self._last_innovation_odom = np.zeros(3)
        self._last_innovation_gps = np.zeros(2)
        self._heading_div_start = None
        self._heading_diverged = False
        self._predict_count = 0
        self._odom_update_count = 0
        self._gps_update_count = 0
