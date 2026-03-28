"""Tests for step response metrics module.

All tests generate synthetic data — no external fixtures required.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pid_tuning.step_metrics import (
    StepMetrics,
    assess_confidence,
    check_targets,
    compute_step_metrics,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic response generators
# ---------------------------------------------------------------------------

def _ideal_step_response(
    setpoint: float = 100.0,
    initial: float = 0.0,
    rise_tau: float = 0.05,
    delay: float = 0.01,
    duration: float = 2.0,
    dt: float = 0.001,
) -> tuple[np.ndarray, np.ndarray]:
    """First-order step with no overshoot.

    Returns (timestamps, positions).
    """
    ts = np.arange(0, duration, dt)
    step_size = setpoint - initial
    pos = np.where(
        ts < delay,
        initial,
        initial + step_size * (1.0 - np.exp(-(ts - delay) / rise_tau)),
    )
    return ts, pos


def _oscillatory_response(
    setpoint: float = 100.0,
    initial: float = 0.0,
    overshoot_frac: float = 0.25,
    freq: float = 5.0,
    damping: float = 3.0,
    duration: float = 3.0,
    dt: float = 0.001,
) -> tuple[np.ndarray, np.ndarray]:
    """Underdamped second-order-like response with overshoot.

    Returns (timestamps, positions).
    """
    ts = np.arange(0, duration, dt)
    step_size = setpoint - initial
    # Damped sinusoidal around the setpoint.
    envelope = np.exp(-damping * ts)
    oscillation = overshoot_frac * envelope * np.sin(2 * np.pi * freq * ts)
    pos = initial + step_size * (1.0 - np.exp(-8.0 * ts)) + step_size * oscillation
    return ts, pos


# ---------------------------------------------------------------------------
# Tests — compute_step_metrics
# ---------------------------------------------------------------------------

class TestComputeStepMetrics:
    """Tests for the main metrics computation."""

    def test_ideal_step_metrics(self):
        """Ideal first-order step: fast rise, no overshoot, small error."""
        ts, pos = _ideal_step_response(setpoint=100.0, initial=0.0)
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)

        assert not math.isnan(m.rise_time)
        assert m.rise_time > 0
        assert m.rise_time < 0.5  # fast first-order
        assert m.overshoot_percent == pytest.approx(0.0, abs=1.0)
        assert m.steady_state_error < 1.0  # degrees
        assert not math.isnan(m.settling_time)
        assert m.settling_time < 1.0

    def test_oscillatory_response(self):
        """Underdamped response should show overshoot and longer settling."""
        ts, pos = _oscillatory_response(
            setpoint=100.0, initial=0.0, overshoot_frac=0.5, damping=2.0
        )
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)

        assert m.overshoot_percent > 5.0  # noticeable overshoot
        assert not math.isnan(m.rise_time)
        assert not math.isnan(m.settling_time)
        # Oscillatory should settle slower than ideal.
        assert m.settling_time > 0

    def test_integral_errors_non_negative(self):
        """IAE, ISE, ITSE should all be >= 0."""
        ts, pos = _ideal_step_response()
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)

        assert m.iae >= 0
        assert m.ise >= 0
        assert m.itse >= 0

    def test_iae_decreases_with_faster_response(self):
        """Faster rise time → lower IAE."""
        ts_fast, pos_fast = _ideal_step_response(rise_tau=0.02)
        ts_slow, pos_slow = _ideal_step_response(rise_tau=0.2)
        m_fast = compute_step_metrics(
            ts_fast, pos_fast, setpoint=100.0, step_size=100.0
        )
        m_slow = compute_step_metrics(
            ts_slow, pos_slow, setpoint=100.0, step_size=100.0
        )

        assert m_fast.iae < m_slow.iae

    def test_incomplete_data_few_points(self):
        """Very few data points should still return a result."""
        ts = np.array([0.0, 0.5])
        pos = np.array([0.0, 50.0])
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)

        # Should not crash; some metrics may be NaN.
        assert m.data_points == 2
        assert m.confidence == "low"

    def test_single_point_returns_default(self):
        """A single data point should return defaults without crash."""
        ts = np.array([0.0])
        pos = np.array([0.0])
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)
        assert m.data_points == 1
        assert m.confidence == "low"

    def test_zero_step_size(self):
        """step_size=0 should return without crash."""
        ts = np.arange(0, 1, 0.01)
        pos = np.full_like(ts, 50.0)
        m = compute_step_metrics(ts, pos, setpoint=50.0, step_size=0.0)
        assert m.confidence == "low"

    def test_negative_step(self):
        """Negative step (moving from high to low) should work."""
        ts = np.arange(0, 2, 0.001)
        # Start at 100, settle toward 0.
        pos = 100.0 * np.exp(-5.0 * ts)
        m = compute_step_metrics(ts, pos, setpoint=0.0, step_size=-100.0)

        assert not math.isnan(m.rise_time)
        assert m.rise_time > 0
        assert m.overshoot_percent >= 0

    def test_steady_state_error_perfect_response(self):
        """If the response settles exactly at setpoint, SS error ≈ 0."""
        ts = np.arange(0, 2, 0.001)
        pos = 100.0 * (1.0 - np.exp(-20.0 * ts))  # very fast convergence
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)

        assert m.steady_state_error < 0.1


# ---------------------------------------------------------------------------
# Tests — assess_confidence
# ---------------------------------------------------------------------------

class TestAssessConfidence:
    """Tests for data quality assessment."""

    def test_high_confidence_clean_data(self):
        """Lots of clean data → 'high'."""
        ts = np.arange(0, 2, 0.001)  # 2000 points
        pos = 100.0 * (1.0 - np.exp(-5.0 * ts))
        assert assess_confidence(ts, pos) == "high"

    def test_low_confidence_few_points(self):
        """Fewer than 10 points → 'low'."""
        ts = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        pos = np.array([0.0, 20.0, 50.0, 80.0, 95.0])
        assert assess_confidence(ts, pos) == "low"

    def test_medium_confidence_moderate_data(self):
        """10-20 points with reasonable signal → 'medium' or higher."""
        ts = np.linspace(0, 1, 15)
        pos = 50.0 * (1.0 - np.exp(-5.0 * ts))
        conf = assess_confidence(ts, pos)
        assert conf in ("medium", "high")

    def test_noisy_data_lower_confidence(self):
        """Heavy noise degrades confidence."""
        rng = np.random.default_rng(123)
        ts = np.arange(0, 2, 0.001)
        pos = 100.0 * (1.0 - np.exp(-5.0 * ts)) + rng.normal(0, 50, ts.size)
        conf = assess_confidence(ts, pos)
        # Heavy noise should prevent "high".
        assert conf in ("low", "medium")


# ---------------------------------------------------------------------------
# Tests — check_targets
# ---------------------------------------------------------------------------

class TestCheckTargets:
    """Tests for target pass/fail assessment."""

    def test_all_pass_ideal(self):
        """Ideal fast step should pass all default targets."""
        ts, pos = _ideal_step_response(
            setpoint=100.0, initial=0.0, rise_tau=0.02
        )
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)
        results = check_targets(m)

        assert results["rise_time"] is True
        assert results["settling_time"] is True
        assert results["overshoot_percent"] is True
        assert results["steady_state_error"] is True

    def test_overshoot_fails(self):
        """High overshoot should fail the overshoot target."""
        ts, pos = _oscillatory_response(
            setpoint=100.0, initial=0.0, overshoot_frac=0.5, damping=2.0
        )
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)
        results = check_targets(m)

        assert results["overshoot_percent"] is False

    def test_custom_targets(self):
        """Custom (very strict) targets should cause failures."""
        ts, pos = _ideal_step_response(rise_tau=0.1)
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)

        strict = {"rise_time": 0.01, "settling_time": 0.01}
        results = check_targets(m, targets=strict)
        # Even the ideal response can't hit 10 ms rise time with tau=0.1.
        assert results["rise_time"] is False

    def test_nan_metrics_fail_targets(self):
        """NaN metrics should always fail their targets."""
        m = StepMetrics()  # all NaN defaults
        results = check_targets(m)

        for key, passed in results.items():
            assert passed is False, f"{key} should fail when NaN"

    def test_empty_targets_dict(self):
        """Empty custom targets → empty results."""
        ts, pos = _ideal_step_response()
        m = compute_step_metrics(ts, pos, setpoint=100.0, step_size=100.0)
        results = check_targets(m, targets={})
        assert results == {}
