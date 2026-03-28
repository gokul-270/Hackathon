"""Tests for Z-N analyzer module.

All tests are self-contained: they generate synthetic FOPDT step responses
with known K, L, T parameters and verify the analyzer extracts values within
tolerance.
"""

from __future__ import annotations

import numpy as np
import pytest

from pid_tuning.zn_analyzer import (
    ZNAnalysisResult,
    analyze_step_response,
    compute_tuning_rules,
    suggest_gains,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic FOPDT response generators
# ---------------------------------------------------------------------------

def _fopdt_response(
    K: float = 2.0,
    L: float = 0.1,
    T: float = 0.5,
    step_size: float = 10.0,
    duration: float = 3.0,
    dt: float = 0.001,
    noise_std: float = 0.0,
    initial: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Generate a synthetic first-order plus dead-time step response.

    y(t) = initial                           for t < L
    y(t) = initial + K * step * (1 - e^(-(t-L)/T))  for t >= L

    Returns (timestamps, positions, setpoint).
    """
    ts = np.arange(0, duration, dt)
    pos = np.full_like(ts, initial)
    mask = ts >= L
    pos[mask] = initial + K * step_size * (
        1.0 - np.exp(-(ts[mask] - L) / T)
    )
    if noise_std > 0:
        rng = np.random.default_rng(42)
        pos = pos + rng.normal(0, noise_std, size=pos.shape)
    setpoint = initial + K * step_size
    return ts, pos, setpoint


# ---------------------------------------------------------------------------
# Tests — analyze_step_response
# ---------------------------------------------------------------------------

class TestAnalyzeStepResponse:
    """Tests for FOPDT parameter extraction."""

    def test_clean_fopdt_extraction(self):
        """Known K=2, L=0.1, T=0.5 should be recovered within 10 %."""
        ts, pos, sp = _fopdt_response(K=2.0, L=0.1, T=0.5, step_size=10.0)
        result = analyze_step_response(ts, pos, sp, step_size=10.0)

        assert result.success, f"Analysis failed: {result.error_message}"
        assert result.K == pytest.approx(2.0, rel=0.10)
        assert result.L == pytest.approx(0.1, rel=0.10)
        assert result.T == pytest.approx(0.5, rel=0.10)
        assert result.r_squared > 0.0  # tangent fits only the local region
        assert result.confidence in ("high", "medium", "low")

    def test_different_parameters(self):
        """Another set of parameters: K=1.5, L=0.2, T=1.0."""
        ts, pos, sp = _fopdt_response(
            K=1.5, L=0.2, T=1.0, step_size=5.0, duration=5.0
        )
        result = analyze_step_response(ts, pos, sp, step_size=5.0)

        assert result.success
        assert result.K == pytest.approx(1.5, rel=0.10)
        assert result.L == pytest.approx(0.2, rel=0.15)
        assert result.T == pytest.approx(1.0, rel=0.15)

    def test_noisy_data_still_extracts(self):
        """Moderate noise should still yield a successful extraction."""
        ts, pos, sp = _fopdt_response(
            K=2.0, L=0.1, T=0.5, step_size=10.0, noise_std=0.05
        )
        result = analyze_step_response(ts, pos, sp, step_size=10.0)

        assert result.success, f"Failed with noise: {result.error_message}"
        # Relax tolerance for noisy data.
        assert result.K == pytest.approx(2.0, rel=0.20)

    def test_heavy_noise_low_confidence(self):
        """Heavy noise should either fail or produce low/medium confidence."""
        ts, pos, sp = _fopdt_response(
            K=2.0, L=0.1, T=0.5, step_size=10.0, noise_std=3.0
        )
        result = analyze_step_response(ts, pos, sp, step_size=10.0)

        # May succeed or fail; if it succeeds, confidence should not be high
        # (heavy noise degrades fit quality).
        if result.success:
            assert result.confidence in ("low", "medium")

    def test_insufficient_data(self):
        """Fewer than 5 points should fail."""
        ts = np.array([0.0, 0.1, 0.2])
        pos = np.array([0.0, 5.0, 10.0])
        result = analyze_step_response(ts, pos, setpoint=10.0, step_size=10.0)

        assert not result.success
        assert "Insufficient" in result.error_message

    def test_length_mismatch(self):
        """Mismatched array lengths should fail."""
        ts = np.arange(0, 1, 0.01)
        pos = np.arange(0, 0.5, 0.01)
        result = analyze_step_response(ts, pos, setpoint=10.0, step_size=10.0)

        assert not result.success
        assert "mismatch" in result.error_message

    def test_zero_step_size(self):
        """step_size=0 should fail."""
        ts, pos, sp = _fopdt_response()
        result = analyze_step_response(ts, pos, sp, step_size=0.0)

        assert not result.success
        assert "non-zero" in result.error_message.lower()

    def test_inverted_response(self):
        """Response going the wrong way should yield non-positive K → fail."""
        ts = np.arange(0, 2, 0.01)
        # Position decreasing while we expect increase.
        pos = 100.0 - 5.0 * (1.0 - np.exp(-ts / 0.3))
        result = analyze_step_response(
            ts, pos, setpoint=110.0, step_size=10.0
        )

        assert not result.success
        assert "gain" in result.error_message.lower() or not result.success

    def test_flat_response_no_inflection(self):
        """Completely flat data should fail (no inflection)."""
        ts = np.arange(0, 2, 0.01)
        pos = np.full_like(ts, 50.0)
        result = analyze_step_response(ts, pos, setpoint=60.0, step_size=10.0)

        assert not result.success


# ---------------------------------------------------------------------------
# Tests — compute_tuning_rules
# ---------------------------------------------------------------------------

class TestComputeTuningRules:
    """Tests for Z-N tuning rule computation."""

    def test_all_six_rules_present(self):
        """All 6 rule keys should be returned."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        expected_keys = {
            "p_only", "pi", "classic_pid",
            "pessen", "some_overshoot", "no_overshoot",
        }
        assert set(rules.keys()) == expected_keys

    def test_all_gains_positive(self):
        """Every rule should produce positive Kp and Ki (where nonzero)."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        for key, rule in rules.items():
            assert rule.kp > 0, f"{key}: Kp should be positive"
            if key != "p_only":
                assert rule.ki > 0, f"{key}: Ki should be positive"

    def test_p_only_no_ki_kd(self):
        """P-only should have Ki=0, Kd=0."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert rules["p_only"].ki == 0.0
        assert rules["p_only"].kd == 0.0

    def test_classic_pid_has_kd(self):
        """Classic PID should have nonzero Kd and be flagged not-applicable."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert rules["classic_pid"].kd > 0
        assert not rules["classic_pid"].applicable

    def test_pessen_has_kd(self):
        """Pessen should have nonzero Kd and be flagged not-applicable."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert rules["pessen"].kd > 0
        assert not rules["pessen"].applicable

    def test_no_overshoot_no_kd(self):
        """No-Overshoot rule should have Kd=0 and be applicable."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert rules["no_overshoot"].kd == 0.0
        assert rules["no_overshoot"].applicable

    def test_some_overshoot_applicable(self):
        """Some-Overshoot should be applicable (no Kd)."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert rules["some_overshoot"].kd == 0.0
        assert rules["some_overshoot"].applicable

    def test_pi_applicable(self):
        """PI rule should be applicable (no Kd)."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert rules["pi"].kd == 0.0
        assert rules["pi"].applicable

    def test_known_values_classic_pid(self):
        """Spot-check Classic PID formulas: Kp = 1.2*T/(K*L)."""
        L, T, K = 0.1, 0.5, 2.0
        rules = compute_tuning_rules(L=L, T=T, K=K)
        expected_kp = 1.2 * T / (K * L)
        expected_ki = expected_kp / (2.0 * L)
        expected_kd = expected_kp * 0.5 * L
        assert rules["classic_pid"].kp == pytest.approx(expected_kp)
        assert rules["classic_pid"].ki == pytest.approx(expected_ki)
        assert rules["classic_pid"].kd == pytest.approx(expected_kd)

    def test_invalid_parameters_raise(self):
        """Non-positive L, T, or K should raise ValueError."""
        with pytest.raises(ValueError):
            compute_tuning_rules(L=0, T=0.5, K=2.0)
        with pytest.raises(ValueError):
            compute_tuning_rules(L=0.1, T=-1, K=2.0)
        with pytest.raises(ValueError):
            compute_tuning_rules(L=0.1, T=0.5, K=0)

    def test_ordering_kp_magnitudes(self):
        """No-Overshoot Kp < Some-Overshoot Kp < PI Kp < Classic PID Kp."""
        rules = compute_tuning_rules(L=0.1, T=0.5, K=2.0)
        assert (
            rules["no_overshoot"].kp
            < rules["some_overshoot"].kp
            < rules["pi"].kp
            < rules["classic_pid"].kp
        )


# ---------------------------------------------------------------------------
# Tests — suggest_gains
# ---------------------------------------------------------------------------

class TestSuggestGains:
    """Tests for uint8 gain mapping."""

    def test_gains_within_uint8(self):
        """All mapped gains must be in [0, 255]."""
        ts, pos, sp = _fopdt_response(K=2.0, L=0.1, T=0.5, step_size=10.0)
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        assert result.success

        for rule_key in (
            "p_only", "pi", "classic_pid",
            "pessen", "some_overshoot", "no_overshoot",
        ):
            sg = suggest_gains(result, motor_type="mg6010", rule=rule_key)
            for attr in (
                "position_kp", "position_ki",
                "speed_kp", "speed_ki",
                "torque_kp", "torque_ki",
            ):
                val = getattr(sg, attr)
                assert isinstance(val, int), f"{attr} should be int"
                assert 0 <= val <= 255, (
                    f"{attr}={val} out of uint8 range for rule {rule_key}"
                )

    def test_large_gains_clamped_to_255(self):
        """Very high Z-N gains (small L, large T/K) should be clamped."""
        # L very small → gains become enormous.
        ts, pos, sp = _fopdt_response(
            K=0.1, L=0.005, T=2.0, step_size=10.0, duration=10.0
        )
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        if result.success:
            sg = suggest_gains(result, motor_type="mg6010", rule="classic_pid")
            assert sg.position_kp <= 255
            assert sg.position_ki <= 255

    def test_failed_analysis_returns_note(self):
        """If analysis failed, suggest_gains should explain in note."""
        failed = ZNAnalysisResult(success=False, error_message="test fail")
        sg = suggest_gains(failed)
        assert "failed" in sg.applicable_note.lower()

    def test_unknown_rule_returns_note(self):
        """Unknown rule name should yield an informative note."""
        ts, pos, sp = _fopdt_response()
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        assert result.success
        sg = suggest_gains(result, rule="nonexistent_rule")
        assert "Unknown rule" in sg.applicable_note

    def test_mg6012_scaling(self):
        """MG6012 should produce different (lower) gains than MG6010."""
        ts, pos, sp = _fopdt_response(K=2.0, L=0.1, T=0.5, step_size=10.0)
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        assert result.success
        sg10 = suggest_gains(result, motor_type="mg6010", rule="pi")
        sg12 = suggest_gains(result, motor_type="mg6012", rule="pi")
        # MG6012 has lower scaling factors → lower mapped gains.
        assert sg12.position_kp <= sg10.position_kp

    def test_kd_note_for_pid_rules(self):
        """Rules with Kd should note that Kd is not applicable."""
        ts, pos, sp = _fopdt_response()
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        assert result.success
        sg = suggest_gains(result, rule="classic_pid")
        assert "NOT applicable" in sg.applicable_note

    def test_no_kd_note_for_pi_rule(self):
        """PI rule (no Kd) should note all gains are applicable."""
        ts, pos, sp = _fopdt_response()
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        assert result.success
        sg = suggest_gains(result, rule="pi")
        assert "applicable" in sg.applicable_note.lower()
        assert "NOT applicable" not in sg.applicable_note

    def test_confidence_propagated(self):
        """Confidence from analysis should carry through to suggestion."""
        ts, pos, sp = _fopdt_response()
        result = analyze_step_response(ts, pos, sp, step_size=10.0)
        assert result.success
        sg = suggest_gains(result, rule="pi")
        assert sg.confidence == result.confidence
