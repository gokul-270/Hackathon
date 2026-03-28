#!/usr/bin/env python3
"""
Path Corrector — Cross-Track Error PD Controller

Monitors the fused pose against the intended trajectory during pattern
and draw-path execution, applying small heading corrections to keep the
vehicle on the intended line.

Only active during *straight* segments — rotation and stop segments
are not corrected.
"""

from __future__ import annotations

import math
import time


class PathCorrector:
    """Cross-track error correction during path/pattern execution.

    Uses a PD controller that combines:
      - CTE  (perpendicular distance to the planned line)
      - Heading error (angle between robot heading and path direction)

    Both terms are corrected simultaneously for faster recovery.
    """

    def __init__(self,
                 kp: float = 0.5,
                 kd: float = 0.1,
                 kh: float = 0.4,
                 max_correction: float = 0.3):
        """
        Args:
            kp: Proportional gain for CTE — rad/s per metre
            kd: Derivative gain for CTE rate
            kh: Heading-error gain — rad/s per radian of heading error
            max_correction: Maximum angular velocity correction (rad/s)
        """
        self.kp = kp
        self.kd = kd
        self.kh = kh
        self.max_correction = max_correction

        # Current segment endpoints
        self._start_x = 0.0
        self._start_y = 0.0
        self._end_x = 0.0
        self._end_y = 0.0
        self._seg_len = 0.0
        self._seg_dx = 0.0
        self._seg_dy = 0.0
        self._path_heading = 0.0   # atan2(seg_dy, seg_dx)
        self._has_segment = False

        # CTE state for derivative
        self._prev_cte = 0.0
        self._prev_time = 0.0
        self._cte = 0.0
        self._heading_error = 0.0
        self._correction = 0.0

    def set_segment(self, start_x: float, start_y: float,
                    end_x: float, end_y: float) -> None:
        """Set the current intended path segment.

        The CTE is computed as the signed perpendicular distance from
        the vehicle position to the line from start→end.
        The heading error is computed against the segment direction.
        """
        self._start_x = start_x
        self._start_y = start_y
        self._end_x = end_x
        self._end_y = end_y
        self._seg_dx = end_x - start_x
        self._seg_dy = end_y - start_y
        self._seg_len = math.hypot(self._seg_dx, self._seg_dy)
        self._has_segment = self._seg_len > 0.01
        self._path_heading = math.atan2(self._seg_dy, self._seg_dx)
        self._prev_cte = 0.0
        self._prev_time = time.monotonic()
        self._cte = 0.0
        self._heading_error = 0.0
        self._correction = 0.0

    def compute_correction(self, fused_x: float, fused_y: float,
                           fused_theta: float) -> float:
        """Return angular velocity correction (rad/s) to reduce CTE + heading error.

        Combines:
          CTE term:     −kp × cte − kd × d(cte)/dt
          Heading term: −kh × heading_error

        Positive correction = turn left (positive angular_z in ROS).

        Args:
            fused_x, fused_y: Current fused position (EKF or raw odom)
            fused_theta:      Current heading (rad)

        Returns:
            Angular velocity correction in rad/s, clamped to ±max_correction.
        """
        if not self._has_segment:
            return 0.0

        # ── CTE via 2D cross product ──
        # CTE = ((P − A) × (B − A)) / |B − A|
        # Positive = vehicle is LEFT of A→B direction
        apx = fused_x - self._start_x
        apy = fused_y - self._start_y
        cross = apx * self._seg_dy - apy * self._seg_dx
        self._cte = cross / self._seg_len

        # CTE derivative
        now = time.monotonic()
        dt = now - self._prev_time
        if dt > 0.001:
            cte_rate = (self._cte - self._prev_cte) / dt
        else:
            cte_rate = 0.0
        self._prev_cte = self._cte
        self._prev_time = now

        # ── Heading error: difference between robot heading and segment direction ──
        # Positive heading_error = robot faces LEFT of intended path
        raw_he = fused_theta - self._path_heading
        self._heading_error = math.atan2(math.sin(raw_he), math.cos(raw_he))

        # ── Combined PD + heading correction ──
        # Negative CTE (right of path) → positive correction (turn left) → correction = -kp*cte
        # Negative heading error (facing right of path) → positive correction
        raw_correction = (-self.kp * self._cte
                         - self.kd * cte_rate
                         - self.kh * self._heading_error)

        # Clamp
        self._correction = max(-self.max_correction,
                               min(self.max_correction, raw_correction))
        return self._correction

    def get_diagnostics(self) -> dict:
        """Return CTE, correction, and segment info for dashboard."""
        return {
            'cte': round(self._cte, 4),
            'heading_error': round(math.degrees(self._heading_error), 2),
            'correction': round(self._correction, 4),
            'has_segment': self._has_segment,
            'path_heading_deg': round(math.degrees(self._path_heading), 1),
            'kp': self.kp,
            'kd': self.kd,
            'kh': self.kh,
            'max_correction': self.max_correction,
        }

    def reset(self) -> None:
        """Reset for new path/pattern."""
        self._has_segment = False
        self._cte = 0.0
        self._heading_error = 0.0
        self._correction = 0.0
        self._prev_cte = 0.0
        self._prev_time = 0.0

    @property
    def cross_track_error(self) -> float:
        """Current CTE in metres (signed). + = left of path."""
        return self._cte

    def update_gains(self, kp: float | None = None,
                     kd: float | None = None,
                     kh: float | None = None,
                     max_correction: float | None = None) -> None:
        """Live-update PD+H gains from dashboard."""
        if kp is not None:
            self.kp = float(kp)
        if kd is not None:
            self.kd = float(kd)
        if kh is not None:
            self.kh = float(kh)
        if max_correction is not None:
            self.max_correction = float(max_correction)
