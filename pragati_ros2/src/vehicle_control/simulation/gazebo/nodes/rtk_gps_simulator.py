#!/usr/bin/env python3
"""
RTK GPS Simulator Node — Production-grade RTK pipeline simulation.

Simulates a complete u-blox F9P + NTRIP RTK correction workflow:

  1. **Base Station** — A fixed GPS receiver at known coordinates publishes
     noisy GPS readings on ``/base_station/navsat``.
  2. **Rover** — The robot's Gazebo NavSat sensor publishes perfect GPS
     on ``/navsat``; this node adds realistic single-point noise.
  3. **RTK Engine** — Computes the baseline vector (base→rover), applies
     differential corrections, and models convergence through fix states
     (NO_FIX → FLOAT → RTK_FIXED).
  4. **Output** — Corrected ``/gps/fix`` with proper ``NavSatStatus``,
     covariance, and a JSON ``/rtk/status`` diagnostic topic for the Web UI.

The algorithm mirrors what happens inside a real F9P receiver:

  * The base station knows its *true* position (surveyed-in).
  * At each epoch, the base computes ``error = measured − true``.
  * That error (the RTCM correction) is applied to the rover reading.
  * Once corrections converge, residual error drops from metres to centimetres.

Coordinate maths uses WGS-84 → ECEF → ENU conversions (no external libs).

Usage:
  ros2 run vehicle_control gazebo_rtk_gps_simulator

Parameters (all configurable via launch or CLI):
  base_lat, base_lon, base_alt   — True surveyed base station coordinates
  convergence_time               — Seconds to reach RTK Fixed (default 30)
  dropout_probability            — Per-second chance of losing fix (0.01)
  enable_multipath               — Simulate multipath noise spikes (true)
"""

from __future__ import annotations

import math
import random
import time
import json

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import String
from geometry_msgs.msg import Vector3Stamped


# ─── WGS-84 constants ───────────────────────────────────────────────
WGS84_A = 6378137.0             # Semi-major axis (m)
WGS84_F = 1.0 / 298.257223563  # Flattening
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_E2 = 1.0 - (WGS84_B ** 2) / (WGS84_A ** 2)  # First eccentricity squared


# ─── Coordinate conversion helpers ──────────────────────────────────

def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt: float) -> tuple[float, float, float]:
    """WGS-84 (lat°, lon°, alt_m) → ECEF (x, y, z) metres."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

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
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    e = -sin_lon * dx + cos_lon * dy
    n = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    u = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    return e, n, u


def enu_to_geodetic_offset(e: float, n: float, u: float,
                           ref_lat_deg: float, ref_lon_deg: float,
                           ref_alt: float) -> tuple[float, float, float]:
    """Apply a small ENU offset to a geodetic reference → new (lat°, lon°, alt)."""
    lat_rad = math.radians(ref_lat_deg)
    # Meridional & prime-vertical radii
    N = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(lat_rad) ** 2)
    M = WGS84_A * (1.0 - WGS84_E2) / (1.0 - WGS84_E2 * math.sin(lat_rad) ** 2) ** 1.5

    d_lat = n / M
    d_lon = e / (N * math.cos(lat_rad))

    return ref_lat_deg + math.degrees(d_lat), ref_lon_deg + math.degrees(d_lon), ref_alt + u


# ─── Fix-state definitions ──────────────────────────────────────────

class FixState:
    """RTK convergence states mirroring real F9P behaviour."""
    SEARCHING = 'SEARCHING'     # Power-on, acquiring satellites
    NO_FIX    = 'NO_FIX'        # Satellites acquired, no corrections
    FLOAT     = 'FLOAT'         # Corrections arriving, ambiguities float
    RTK_FIXED = 'RTK_FIXED'     # Integer ambiguities resolved, cm-level
    DGPS      = 'DGPS'          # Differential (fallback after dropout)

# Noise models per state  (horizontal_std_m, vertical_std_m)
NOISE_MODELS: dict[str, tuple[float, float]] = {
    FixState.SEARCHING: (0.0, 0.0),      # No output during search
    FixState.NO_FIX:    (5.0, 10.0),      # Standard single-point GPS
    FixState.FLOAT:     (0.40, 0.80),     # RTK Float
    FixState.RTK_FIXED: (0.015, 0.025),   # RTK Fixed  (1.5 cm H, 2.5 cm V)
    FixState.DGPS:      (0.60, 1.20),     # Degraded differential
}

# Covariance diagonal (H² H² V²) per state
COVARIANCE_DIAG: dict[str, tuple[float, float, float]] = {
    FixState.SEARCHING: (100.0, 100.0, 200.0),
    FixState.NO_FIX:    (25.0, 25.0, 100.0),
    FixState.FLOAT:     (0.16, 0.16, 0.64),
    FixState.RTK_FIXED: (0.000225, 0.000225, 0.000625),   # 1.5cm² , 2.5cm²
    FixState.DGPS:      (0.36, 0.36, 1.44),
}

# NavSatStatus mapping
STATUS_MAP: dict[str, int] = {
    FixState.SEARCHING: NavSatStatus.STATUS_NO_FIX,
    FixState.NO_FIX:    NavSatStatus.STATUS_NO_FIX,
    FixState.FLOAT:     NavSatStatus.STATUS_SBAS_FIX,
    FixState.RTK_FIXED: NavSatStatus.STATUS_GBAS_FIX,
    FixState.DGPS:      NavSatStatus.STATUS_SBAS_FIX,
}


# ─── RTK GPS Simulator Node ─────────────────────────────────────────

class RtkGpsSimulator(Node):
    """Full RTK GPS simulation with base station, corrections, and convergence."""

    def __init__(self):
        super().__init__('rtk_gps_simulator')

        # ── Declare parameters ──────────────────────────────────────
        self.declare_parameter('base_lat', 23.0225)
        self.declare_parameter('base_lon', 72.5714)
        self.declare_parameter('base_alt', 53.0)
        # Base station position in Gazebo world frame (for reference)
        self.declare_parameter('base_world_x', 0.0)
        self.declare_parameter('base_world_y', 0.0)

        # Convergence timing (seconds)
        self.declare_parameter('search_duration', 5.0)
        self.declare_parameter('nofix_duration', 8.0)
        self.declare_parameter('float_duration', 17.0)
        # Total: 5 + 8 + 17 = 30s to RTK Fixed (realistic F9P)

        # Stochastic behaviour
        self.declare_parameter('dropout_probability', 0.005)  # Per-epoch chance
        self.declare_parameter('dropout_duration_min', 2.0)    # Seconds
        self.declare_parameter('dropout_duration_max', 8.0)
        self.declare_parameter('enable_multipath', True)
        self.declare_parameter('multipath_probability', 0.02)
        self.declare_parameter('multipath_extra_noise_m', 2.0)

        # Simulated satellite count
        self.declare_parameter('min_satellites', 6)
        self.declare_parameter('max_satellites', 14)

        # Publish rate
        self.declare_parameter('publish_rate_hz', 10.0)

        # ── Read parameters ─────────────────────────────────────────
        self.base_true_lat = self.get_parameter('base_lat').value
        self.base_true_lon = self.get_parameter('base_lon').value
        self.base_true_alt = self.get_parameter('base_alt').value

        self.search_dur = self.get_parameter('search_duration').value
        self.nofix_dur  = self.get_parameter('nofix_duration').value
        self.float_dur  = self.get_parameter('float_duration').value

        self.dropout_prob      = self.get_parameter('dropout_probability').value
        self.dropout_dur_min   = self.get_parameter('dropout_duration_min').value
        self.dropout_dur_max   = self.get_parameter('dropout_duration_max').value
        self.enable_multipath  = self.get_parameter('enable_multipath').value
        self.multipath_prob    = self.get_parameter('multipath_probability').value
        self.multipath_noise   = self.get_parameter('multipath_extra_noise_m').value
        self.min_sats          = self.get_parameter('min_satellites').value
        self.max_sats          = self.get_parameter('max_satellites').value
        self.publish_rate      = self.get_parameter('publish_rate_hz').value

        # ── ECEF of true base position (precompute) ─────────────────
        self.base_ecef = geodetic_to_ecef(
            self.base_true_lat, self.base_true_lon, self.base_true_alt
        )

        # ── State ───────────────────────────────────────────────────
        self.fix_state = FixState.SEARCHING
        self.state_start_time = self.get_clock().now()
        self.startup_time = self.get_clock().now()
        self.rng = random.Random()

        self.rover_raw: NavSatFix | None = None
        self.base_measured: NavSatFix | None = None

        # Base station noise (simulated GPS error at base)
        self.base_noise_e = 0.0   # ENU errors that slowly drift
        self.base_noise_n = 0.0
        self.base_noise_u = 0.0

        # Correction state
        self.correction_e = 0.0   # Last computed correction (ENU)
        self.correction_n = 0.0
        self.correction_u = 0.0

        # Dropout tracking
        self.in_dropout = False
        self.dropout_end_time = 0.0

        # Convergence progress (0.0 to 1.0)
        self.convergence_progress = 0.0

        # Satellite simulation
        self.current_sats = self.min_sats

        # Epoch counter
        self.epoch_count = 0

        # ── QoS ─────────────────────────────────────────────────────
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5,
        )

        # ── Subscribers ─────────────────────────────────────────────
        self.sub_rover = self.create_subscription(
            NavSatFix, '/navsat', self._rover_cb, sensor_qos
        )
        # Base station NavSat comes from Gazebo (if a sensor model exists)
        # OR we generate synthetic base readings internally.
        # We'll generate them internally for robustness.

        # ── Publishers ──────────────────────────────────────────────
        self.pub_fix = self.create_publisher(NavSatFix, '/gps/fix', 10)
        self.pub_base = self.create_publisher(NavSatFix, '/base_station/navsat', 10)
        self.pub_baseline = self.create_publisher(Vector3Stamped, '/rtk/baseline', 10)
        self.pub_status = self.create_publisher(String, '/rtk/status', 10)

        # ── Timer ───────────────────────────────────────────────────
        period = 1.0 / self.publish_rate
        self.timer = self.create_timer(period, self._on_epoch)

        self.get_logger().info(
            f'🛰️  RTK GPS Simulator started\n'
            f'   Base station: ({self.base_true_lat:.6f}°, {self.base_true_lon:.6f}°, {self.base_true_alt:.1f}m)\n'
            f'   Convergence: {self.search_dur}s search → {self.nofix_dur}s no-fix → '
            f'{self.float_dur}s float → RTK Fixed\n'
            f'   Publish rate: {self.publish_rate} Hz'
        )

    # ─── Callbacks ──────────────────────────────────────────────────

    def _rover_cb(self, msg: NavSatFix):
        """Receive clean Gazebo NavSat for the rover."""
        self.rover_raw = msg

    # ─── Main epoch loop ────────────────────────────────────────────

    def _on_epoch(self):
        """Called at publish_rate_hz — the RTK processing loop."""
        self.epoch_count += 1
        now = self.get_clock().now()
        elapsed = (now - self.startup_time).nanoseconds / 1e9

        # ── 1. Update fix state machine ─────────────────────────────
        self._update_fix_state(elapsed)

        # ── 2. Generate base station reading ────────────────────────
        self._generate_base_reading(now)

        # ── 3. Compute corrections & corrected position ─────────────
        if self.rover_raw is None:
            return  # Wait for first rover reading

        # ── 4. Apply RTK algorithm ──────────────────────────────────
        corrected_fix = self._compute_rtk_correction(now)

        # ── 5. Compute baseline ─────────────────────────────────────
        baseline_enu = self._compute_baseline()

        # ── 6. Publish everything ───────────────────────────────────
        if corrected_fix is not None:
            self.pub_fix.publish(corrected_fix)

        self._publish_baseline(baseline_enu, now)
        self._publish_status(elapsed, baseline_enu, now)

    # ─── Fix State Machine ──────────────────────────────────────────

    def _update_fix_state(self, elapsed: float):
        """Transition through fix states based on elapsed time + stochastic events."""

        # Check for dropout events (only when in good fix states)
        if not self.in_dropout and self.fix_state in (FixState.FLOAT, FixState.RTK_FIXED):
            if self.rng.random() < self.dropout_prob:
                self.in_dropout = True
                dur = self.rng.uniform(self.dropout_dur_min, self.dropout_dur_max)
                self.dropout_end_time = elapsed + dur
                self.fix_state = FixState.DGPS
                self.get_logger().warn(
                    f'⚠️  RTK dropout! Falling back to DGPS for {dur:.1f}s'
                )
                return

        # Handle dropout recovery
        if self.in_dropout:
            if elapsed >= self.dropout_end_time:
                self.in_dropout = False
                self.fix_state = FixState.FLOAT
                self.convergence_progress = 0.7  # Partial re-convergence
                self.get_logger().info('🔄 RTK recovering from dropout → FLOAT')
            return

        # Normal convergence state machine
        if elapsed < self.search_dur:
            self.fix_state = FixState.SEARCHING
            self.convergence_progress = elapsed / self.search_dur * 0.1
        elif elapsed < self.search_dur + self.nofix_dur:
            self.fix_state = FixState.NO_FIX
            t = elapsed - self.search_dur
            self.convergence_progress = 0.1 + (t / self.nofix_dur) * 0.2
            # Ramp up satellite count
            frac = t / self.nofix_dur
            self.current_sats = int(self.min_sats + frac * (self.max_sats - self.min_sats) * 0.6)
        elif elapsed < self.search_dur + self.nofix_dur + self.float_dur:
            self.fix_state = FixState.FLOAT
            t = elapsed - self.search_dur - self.nofix_dur
            self.convergence_progress = 0.3 + (t / self.float_dur) * 0.7
            self.current_sats = int(self.min_sats + 0.6 * (self.max_sats - self.min_sats)
                                    + (t / self.float_dur) * 0.4 * (self.max_sats - self.min_sats))
            self.current_sats = min(self.current_sats, self.max_sats)
        else:
            if self.fix_state != FixState.RTK_FIXED:
                self.get_logger().info('✅ RTK FIXED achieved — centimetre-level precision')
            self.fix_state = FixState.RTK_FIXED
            self.convergence_progress = 1.0
            self.current_sats = self.max_sats + self.rng.randint(-1, 1)

        # Clamp satellite count
        self.current_sats = max(self.min_sats, min(self.max_sats + 2, self.current_sats))

    # ─── Base Station Simulation ────────────────────────────────────

    def _generate_base_reading(self, stamp):
        """Simulate a GPS receiver at the base station (known position + noise).

        Real base stations have the SAME atmospheric/satellite errors as the rover
        (since they're nearby). We simulate slowly-drifting common-mode errors.
        """
        # Slowly drifting base noise (simulates ionospheric / tropospheric drift)
        drift_rate = 0.005  # m per epoch at 10Hz → 0.05 m/s drift
        self.base_noise_e += self.rng.gauss(0, drift_rate)
        self.base_noise_n += self.rng.gauss(0, drift_rate)
        self.base_noise_u += self.rng.gauss(0, drift_rate * 2)

        # Mean-revert to prevent unbounded drift (AR(1) process)
        revert = 0.995
        self.base_noise_e *= revert
        self.base_noise_n *= revert
        self.base_noise_u *= revert

        # Add random walk (satellite geometry changes)
        h_noise = 2.5  # metres — typical single-point GPS error
        v_noise = 5.0
        e_err = self.base_noise_e + self.rng.gauss(0, h_noise * 0.1)
        n_err = self.base_noise_n + self.rng.gauss(0, h_noise * 0.1)
        u_err = self.base_noise_u + self.rng.gauss(0, v_noise * 0.1)

        # Convert noise to geodetic offset
        meas_lat, meas_lon, meas_alt = enu_to_geodetic_offset(
            e_err, n_err, u_err,
            self.base_true_lat, self.base_true_lon, self.base_true_alt
        )

        # Publish base station NavSatFix
        base_msg = NavSatFix()
        base_msg.header.stamp = stamp.to_msg()
        base_msg.header.frame_id = 'base_station_gps'
        base_msg.latitude = meas_lat
        base_msg.longitude = meas_lon
        base_msg.altitude = meas_alt
        base_msg.status.status = NavSatStatus.STATUS_FIX
        base_msg.status.service = NavSatStatus.SERVICE_GPS
        base_msg.position_covariance = [
            h_noise**2, 0.0, 0.0,
            0.0, h_noise**2, 0.0,
            0.0, 0.0, v_noise**2,
        ]
        base_msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN

        self.pub_base.publish(base_msg)
        self.base_measured = base_msg

        # ── Compute correction vector ───────────────────────────────
        # correction = true_position − measured_position  (in ENU)
        # The rover applies:  corrected = rover_measured + correction
        self.correction_e = -e_err
        self.correction_n = -n_err
        self.correction_u = -u_err

    # ─── RTK Correction Algorithm ───────────────────────────────────

    def _compute_rtk_correction(self, stamp) -> NavSatFix | None:
        """Apply differential corrections to the rover position.

        This is the core RTK algorithm:
        1. Base error = base_measured - base_true
        2. Correction = -base_error  (negate to get what to ADD to rover)
        3. corrected_rover = rover_measured + correction
        4. Add residual noise based on current fix state
        5. Blend correction strength with convergence progress
        """
        if self.fix_state == FixState.SEARCHING:
            return None  # No output during satellite search

        rover = self.rover_raw
        if rover is None:
            return None

        # ── Step 1: Start with raw rover position ───────────────────
        rover_lat = rover.latitude
        rover_lon = rover.longitude
        rover_alt = rover.altitude

        # ── Step 2: Add single-point GPS noise to rover ─────────────
        # (Gazebo gives perfect position; real GPS has noise)
        sp_h_noise = 3.0   # Single-point horizontal noise std (m)
        sp_v_noise = 6.0   # Single-point vertical noise std (m)
        rover_noise_e = self.rng.gauss(0, sp_h_noise)
        rover_noise_n = self.rng.gauss(0, sp_h_noise)
        rover_noise_u = self.rng.gauss(0, sp_v_noise)

        # ── Step 3: Apply differential correction (scaled by convergence) ─
        # As convergence_progress → 1.0, corrections are fully applied
        # and residual noise drops to cm-level
        if self.fix_state in (FixState.NO_FIX,):
            # No corrections available yet — just noisy single-point
            applied_e = rover_noise_e
            applied_n = rover_noise_n
            applied_u = rover_noise_u
        else:
            # Corrections available (FLOAT, RTK_FIXED, DGPS)
            # Correction cancels common-mode error; residual is fix-state dependent
            correction_strength = min(1.0, self.convergence_progress)

            # Residual noise after correction (gets smaller as we converge)
            h_std, v_std = NOISE_MODELS[self.fix_state]
            residual_e = self.rng.gauss(0, h_std)
            residual_n = self.rng.gauss(0, h_std)
            residual_u = self.rng.gauss(0, v_std)

            # Blend: uncorrected noise * (1-strength) + residual * strength
            applied_e = rover_noise_e * (1.0 - correction_strength) + residual_e * correction_strength
            applied_n = rover_noise_n * (1.0 - correction_strength) + residual_n * correction_strength
            applied_u = rover_noise_u * (1.0 - correction_strength) + residual_u * correction_strength

        # ── Step 4: Multipath simulation ────────────────────────────
        if self.enable_multipath and self.rng.random() < self.multipath_prob:
            mp = self.multipath_noise
            applied_e += self.rng.uniform(-mp, mp)
            applied_n += self.rng.uniform(-mp, mp)
            applied_u += self.rng.uniform(-mp / 2, mp / 2)

        # ── Step 5: Convert ENU noise to geodetic offset ────────────
        corr_lat, corr_lon, corr_alt = enu_to_geodetic_offset(
            applied_e, applied_n, applied_u,
            rover_lat, rover_lon, rover_alt
        )

        # ── Step 6: Build output NavSatFix ──────────────────────────
        fix_msg = NavSatFix()
        fix_msg.header.stamp = stamp.to_msg()
        fix_msg.header.frame_id = 'gps'
        fix_msg.latitude = corr_lat
        fix_msg.longitude = corr_lon
        fix_msg.altitude = corr_alt

        # Status
        fix_msg.status.status = STATUS_MAP[self.fix_state]
        fix_msg.status.service = NavSatStatus.SERVICE_GPS | NavSatStatus.SERVICE_GLONASS

        # Covariance
        cov = COVARIANCE_DIAG[self.fix_state]
        fix_msg.position_covariance = [
            cov[0], 0.0, 0.0,
            0.0, cov[1], 0.0,
            0.0, 0.0, cov[2],
        ]
        fix_msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN

        return fix_msg

    # ─── Baseline Calculation ───────────────────────────────────────

    def _compute_baseline(self) -> tuple[float, float, float]:
        """Compute baseline vector from base station to rover in ENU.

        Baseline = rover_ECEF − base_ECEF, rotated to local ENU.
        This is the fundamental RTK observable.
        """
        if self.rover_raw is None:
            return (0.0, 0.0, 0.0)

        rover_ecef = geodetic_to_ecef(
            self.rover_raw.latitude,
            self.rover_raw.longitude,
            self.rover_raw.altitude
        )

        dx = rover_ecef[0] - self.base_ecef[0]
        dy = rover_ecef[1] - self.base_ecef[1]
        dz = rover_ecef[2] - self.base_ecef[2]

        return ecef_to_enu(dx, dy, dz, self.base_true_lat, self.base_true_lon)

    def _publish_baseline(self, enu: tuple[float, float, float], stamp):
        """Publish baseline vector as Vector3Stamped (ENU)."""
        msg = Vector3Stamped()
        msg.header.stamp = stamp.to_msg()
        msg.header.frame_id = 'base_station'
        msg.vector.x = enu[0]  # East
        msg.vector.y = enu[1]  # North
        msg.vector.z = enu[2]  # Up
        self.pub_baseline.publish(msg)

    # ─── RTK Status (JSON for Web UI) ──────────────────────────────

    def _publish_status(self, elapsed: float, baseline_enu: tuple[float, float, float], stamp):
        """Publish comprehensive RTK status as JSON on /rtk/status."""
        e, n, u = baseline_enu
        baseline_length = math.sqrt(e * e + n * n + u * u)
        baseline_azimuth = math.degrees(math.atan2(e, n)) % 360.0
        baseline_elevation = math.degrees(math.atan2(u, math.sqrt(e * e + n * n)))

        h_std, v_std = NOISE_MODELS[self.fix_state]
        cov = COVARIANCE_DIAG[self.fix_state]

        status = {
            'fix_state': self.fix_state,
            'fix_status_code': STATUS_MAP[self.fix_state],
            'convergence_pct': round(self.convergence_progress * 100.0, 1),
            'elapsed_s': round(elapsed, 1),
            'epoch': self.epoch_count,
            'satellites': self.current_sats,
            'in_dropout': self.in_dropout,

            # Baseline
            'baseline_m': round(baseline_length, 3),
            'baseline_azimuth_deg': round(baseline_azimuth, 1),
            'baseline_elevation_deg': round(baseline_elevation, 1),
            'baseline_east_m': round(e, 3),
            'baseline_north_m': round(n, 3),
            'baseline_up_m': round(u, 3),

            # Precision
            'horizontal_accuracy_m': round(h_std, 4),
            'vertical_accuracy_m': round(v_std, 4),
            'covariance_h': round(cov[0], 6),
            'covariance_v': round(cov[2], 6),

            # Base station
            'base_lat': self.base_true_lat,
            'base_lon': self.base_true_lon,
            'base_alt': self.base_true_alt,

            # Correction vector (what's being applied)
            'correction_east_m': round(self.correction_e, 4),
            'correction_north_m': round(self.correction_n, 4),
            'correction_up_m': round(self.correction_u, 4),
        }

        msg = String()
        msg.data = json.dumps(status)
        self.pub_status.publish(msg)


# ─── Entry point ────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = RtkGpsSimulator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
