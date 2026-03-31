"""Tests for collision_math — centralized collision distance helpers."""

import pytest
from collision_math import j4_collision_gap


def test_j4_collision_gap_same_sign_gives_large_gap():
    """Both J4 positive (arms sliding same direction) → large gap."""
    # abs(0.10 + 0.10) = 0.20
    assert j4_collision_gap(0.10, 0.10) == pytest.approx(0.20, abs=1e-9)


def test_j4_collision_gap_opposite_signs_gives_small_gap():
    """J4 values with opposite signs (arms converging) → small gap."""
    # abs(0.10 + (-0.10)) = 0.00
    assert j4_collision_gap(0.10, -0.10) == pytest.approx(0.00, abs=1e-9)


def test_j4_collision_gap_realistic_near_collision():
    """Realistic near-collision: arm1=+0.05, arm2=-0.02 → gap=0.03."""
    # abs(0.05 + (-0.02)) = 0.03
    assert j4_collision_gap(0.05, -0.02) == pytest.approx(0.03, abs=1e-9)


def test_j4_collision_gap_symmetric():
    """Gap is the same regardless of which arm is first."""
    assert j4_collision_gap(0.10, -0.05) == j4_collision_gap(-0.05, 0.10)


def test_j4_collision_gap_both_zero():
    """Both at zero → gap is zero."""
    assert j4_collision_gap(0.0, 0.0) == pytest.approx(0.0, abs=1e-9)
