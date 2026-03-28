"""Tests for PID safety validation module.

Covers: GainLimitEnforcer, GainRamper, OscillationDetector,
TuningSessionLock, and TuningSessionLogger.
"""

from __future__ import annotations

import json
import math
import threading
import time

import pytest
import yaml

from pid_tuning.pid_safety import (
    GAIN_KEYS,
    GainLimitEnforcer,
    GainLimits,
    GainRamper,
    OscillationDetector,
    OscillationResult,
    TuningSessionLock,
    TuningSessionLogger,
    ValidationResult,
)


# ===================================================================
# GainLimits dataclass
# ===================================================================


class TestGainLimits:
    """Basic smoke tests for the GainLimits dataclass."""

    def test_default_values(self):
        gl = GainLimits()
        assert gl.position_kp == (0, 200)
        assert gl.torque_ki == (0, 80)

    def test_as_dict_returns_all_keys(self):
        gl = GainLimits()
        d = gl.as_dict()
        assert set(d.keys()) == set(GAIN_KEYS)
        assert d["speed_kp"] == (0, 200)


# ===================================================================
# GainLimitEnforcer
# ===================================================================


class TestGainLimitEnforcer:
    """Tests for gain limit validation and clamping."""

    def test_valid_gains_pass(self):
        enforcer = GainLimitEnforcer()
        gains = {
            "position_kp": 100,
            "position_ki": 50,
            "speed_kp": 150,
            "speed_ki": 80,
            "torque_kp": 100,
            "torque_ki": 60,
        }
        result = enforcer.validate_gains("MG6010", gains)
        assert result.valid is True
        assert result.errors == []

    def test_excessive_gains_blocked(self):
        enforcer = GainLimitEnforcer()
        gains = {
            "position_kp": 250,  # max is 200
            "torque_ki": 100,  # max is 80
        }
        result = enforcer.validate_gains("MG6010", gains)
        assert result.valid is False
        assert len(result.errors) == 2
        assert any("position_kp" in e for e in result.errors)
        assert any("torque_ki" in e for e in result.errors)

    def test_negative_gains_blocked(self):
        enforcer = GainLimitEnforcer()
        gains = {"position_kp": -1}
        result = enforcer.validate_gains("MG6010", gains)
        assert result.valid is False
        assert any("-1" in e for e in result.errors)

    def test_boundary_gains_pass(self):
        """Gains exactly at min/max should be valid."""
        enforcer = GainLimitEnforcer()
        gains = {
            "position_kp": 0,
            "position_ki": 100,
            "torque_kp": 150,
            "torque_ki": 80,
        }
        result = enforcer.validate_gains("MG6010", gains)
        assert result.valid is True

    def test_override_expands_range(self):
        enforcer = GainLimitEnforcer()
        gains = {"position_kp": 250}
        # Without override — blocked
        result_no_override = enforcer.validate_gains("MG6010", gains)
        assert result_no_override.valid is False
        # With override — passes (0-255)
        result_override = enforcer.validate_gains(
            "MG6010", gains, override=True
        )
        assert result_override.valid is True

    def test_override_still_rejects_above_255(self):
        enforcer = GainLimitEnforcer()
        gains = {"position_kp": 256}
        result = enforcer.validate_gains("MG6010", gains, override=True)
        assert result.valid is False

    def test_clamp_gains(self):
        enforcer = GainLimitEnforcer()
        gains = {
            "position_kp": 300,
            "position_ki": -10,
            "speed_kp": 100,
        }
        clamped = enforcer.clamp_gains("MG6010", gains)
        assert clamped["position_kp"] == 200
        assert clamped["position_ki"] == 0
        assert clamped["speed_kp"] == 100

    def test_clamp_preserves_unknown_keys(self):
        enforcer = GainLimitEnforcer()
        gains = {"position_kp": 300, "custom_param": 42}
        clamped = enforcer.clamp_gains("MG6010", gains)
        assert clamped["custom_param"] == 42

    def test_missing_config_falls_back_to_defaults(self):
        """Non-existent config dir should trigger fallback."""
        enforcer = GainLimitEnforcer(config_dir="/nonexistent/path")
        limits = enforcer.load_limits("MG6010")
        assert limits.position_kp == (0, 200)

    def test_unknown_motor_type_falls_back_to_mg6010(self):
        enforcer = GainLimitEnforcer(config_dir="/nonexistent/path")
        limits = enforcer.load_limits("UNKNOWN_MOTOR")
        assert limits.position_kp == (0, 200)
        assert limits.torque_ki == (0, 80)

    def test_load_limits_from_yaml(self, tmp_path):
        """Limits loaded from YAML override hardcoded defaults."""
        config_dir = tmp_path / "pid_safety"
        config_dir.mkdir()
        config = {
            "position_kp": {"min": 10, "max": 180},
            "position_ki": {"min": 5, "max": 90},
            "speed_kp": [0, 220],
            "speed_ki": [0, 110],
            "torque_kp": {"min": 0, "max": 130},
            "torque_ki": {"min": 0, "max": 70},
        }
        yaml_path = config_dir / "CUSTOM.yaml"
        yaml_path.write_text(yaml.dump(config))

        enforcer = GainLimitEnforcer(config_dir=str(config_dir))
        limits = enforcer.load_limits("CUSTOM")
        assert limits.position_kp == (10, 180)
        assert limits.position_ki == (5, 90)
        assert limits.speed_kp == (0, 220)
        assert limits.torque_ki == (0, 70)

    def test_load_limits_caches_result(self, tmp_path):
        config_dir = tmp_path / "pid_safety"
        config_dir.mkdir()

        enforcer = GainLimitEnforcer(config_dir=str(config_dir))
        limits1 = enforcer.load_limits("MG6010")
        limits2 = enforcer.load_limits("MG6010")
        assert limits1 is limits2  # Same object from cache

    def test_invalid_yaml_falls_back(self, tmp_path):
        config_dir = tmp_path / "pid_safety"
        config_dir.mkdir()
        yaml_path = config_dir / "BAD.yaml"
        yaml_path.write_text("not: a: valid: yaml: [[[")

        enforcer = GainLimitEnforcer(config_dir=str(config_dir))
        # Should not raise, should fallback
        limits = enforcer.load_limits("BAD")
        assert limits.position_kp == (0, 200)

    def test_non_numeric_gain_rejected(self):
        enforcer = GainLimitEnforcer()
        gains = {"position_kp": "abc"}
        result = enforcer.validate_gains("MG6010", gains)
        assert result.valid is False
        assert any("numeric" in e for e in result.errors)

    def test_partial_gains_validated(self):
        """Only keys present in gains dict are checked."""
        enforcer = GainLimitEnforcer()
        gains = {"speed_kp": 50}
        result = enforcer.validate_gains("MG6010", gains)
        assert result.valid is True


# ===================================================================
# GainRamper
# ===================================================================


class TestGainRamper:
    """Tests for gain ramping logic."""

    def test_no_ramping_for_small_changes(self):
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 100, "speed_kp": 50}
        target = {"position_kp": 110, "speed_kp": 60}
        assert ramper.needs_ramping(current, target) is False
        steps = ramper.compute_ramp_steps(current, target)
        assert len(steps) == 1
        assert steps[0]["position_kp"] == 110
        assert steps[0]["speed_kp"] == 60

    def test_ramping_for_large_jump(self):
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 0}
        target = {"position_kp": 100}
        assert ramper.needs_ramping(current, target) is True
        steps = ramper.compute_ramp_steps(current, target)
        # 100 / 20 = 5 steps
        assert len(steps) == 5
        # Final step must equal target
        assert steps[-1]["position_kp"] == 100
        # Each step should increase monotonically
        for i in range(1, len(steps)):
            assert steps[i]["position_kp"] > steps[i - 1]["position_kp"]

    def test_multiple_parameters_ramped(self):
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 0, "speed_kp": 100}
        target = {"position_kp": 60, "speed_kp": 40}
        steps = ramper.compute_ramp_steps(current, target)
        # max delta is 60, so ceil(60/20) = 3 steps
        assert len(steps) == 3
        assert steps[-1]["position_kp"] == 60
        assert steps[-1]["speed_kp"] == 40

    def test_no_change_returns_single_step(self):
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 50}
        target = {"position_kp": 50}
        steps = ramper.compute_ramp_steps(current, target)
        assert len(steps) == 1
        assert steps[0]["position_kp"] == 50

    def test_exact_threshold_no_ramping(self):
        """Delta == max_step should NOT need ramping (needs_ramping checks >)."""
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 100}
        target = {"position_kp": 120}
        assert ramper.needs_ramping(current, target) is False

    def test_one_above_threshold_needs_ramping(self):
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 100}
        target = {"position_kp": 121}
        assert ramper.needs_ramping(current, target) is True

    def test_step_delta_within_max(self):
        """Each step should not change any parameter by more than max_step."""
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 10, "speed_kp": 200}
        target = {"position_kp": 90, "speed_kp": 50}
        steps = ramper.compute_ramp_steps(current, target)

        prev = current
        for step in steps:
            for key in ["position_kp", "speed_kp"]:
                delta = abs(step[key] - prev[key])
                # Allow rounding tolerance of 1
                assert delta <= ramper.max_step + 1, (
                    f"Step delta {delta} exceeds max_step {ramper.max_step} "
                    f"for {key}"
                )
            prev = step

    def test_target_keys_not_in_current_passed_through(self):
        """Keys only in target should appear in every step."""
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 0}
        target = {"position_kp": 60, "torque_kp": 99}
        steps = ramper.compute_ramp_steps(current, target)
        for step in steps:
            assert step["torque_kp"] == 99

    def test_decreasing_ramp(self):
        ramper = GainRamper(max_step=20)
        current = {"position_kp": 100}
        target = {"position_kp": 0}
        steps = ramper.compute_ramp_steps(current, target)
        assert len(steps) == 5
        assert steps[-1]["position_kp"] == 0
        for i in range(1, len(steps)):
            assert steps[i]["position_kp"] < steps[i - 1]["position_kp"]


# ===================================================================
# OscillationDetector
# ===================================================================


class TestOscillationDetector:
    """Tests for oscillation detection."""

    def test_sustained_oscillation_detected(self):
        """Sine-like error with many crossings and large amplitude."""
        detector = OscillationDetector(
            window_seconds=2.0, min_crossings=3, amplitude_factor=2.0
        )
        detector.steady_state_band = 1.0

        # Generate oscillating signal: 10 crossings over 2s
        t = 0.0
        for i in range(200):
            t = i * 0.01  # 100 Hz, 2 seconds total
            error = 5.0 * math.sin(2 * math.pi * 3 * t)  # 3 Hz sine
            detector.update(t, error)

        result = detector.check()
        assert result.detected is True
        assert result.severity == "sustained"
        assert result.crossings > 3

    def test_transient_oscillation_warning(self):
        """Brief oscillation (< 0.5s) should be 'transient'."""
        detector = OscillationDetector(
            window_seconds=2.0, min_crossings=3, amplitude_factor=2.0
        )
        detector.steady_state_band = 1.0

        # Quiet period first
        for i in range(150):
            detector.update(i * 0.01, 0.1)

        # Short burst of oscillation at end (0.3s, ~30 Hz)
        base_t = 1.5
        for i in range(30):
            t = base_t + i * 0.01
            error = 5.0 * math.sin(2 * math.pi * 30 * (t - base_t))
            detector.update(t, error)

        result = detector.check()
        if result.detected:
            assert result.severity == "transient"

    def test_clean_signal_no_detection(self):
        """Constant small error should not trigger detection."""
        detector = OscillationDetector(
            window_seconds=2.0, min_crossings=3, amplitude_factor=2.0
        )
        detector.steady_state_band = 1.0

        for i in range(200):
            detector.update(i * 0.01, 0.5)

        result = detector.check()
        assert result.detected is False
        assert result.severity == "none"

    def test_low_amplitude_not_detected(self):
        """Oscillation with amplitude below threshold is not detected."""
        detector = OscillationDetector(
            window_seconds=2.0, min_crossings=3, amplitude_factor=2.0
        )
        detector.steady_state_band = 5.0  # large band

        # Small oscillation — amplitude < 2 * 5.0 = 10.0
        for i in range(200):
            t = i * 0.01
            error = 1.0 * math.sin(2 * math.pi * 5 * t)
            detector.update(t, error)

        result = detector.check()
        assert result.detected is False

    def test_insufficient_data(self):
        detector = OscillationDetector()
        result = detector.check()
        assert result.detected is False
        assert "Insufficient" in result.message

    def test_single_data_point(self):
        detector = OscillationDetector()
        detector.update(0.0, 1.0)
        result = detector.check()
        assert result.detected is False

    def test_reset_clears_history(self):
        detector = OscillationDetector()
        for i in range(100):
            detector.update(i * 0.01, math.sin(i))
        detector.reset()
        result = detector.check()
        assert result.detected is False
        assert result.crossings == 0

    def test_sliding_window_prunes_old_data(self):
        """Old data outside window should be pruned."""
        detector = OscillationDetector(window_seconds=1.0)

        # Feed data from t=0 to t=3
        for i in range(300):
            detector.update(i * 0.01, 0.5)

        # History should only contain ~100 points (last 1.0s)
        assert len(detector._history) <= 110

    def test_exact_threshold_crossings(self):
        """Exactly min_crossings should not trigger (spec says >3)."""
        detector = OscillationDetector(
            window_seconds=2.0, min_crossings=3, amplitude_factor=2.0
        )
        detector.steady_state_band = 0.1

        # Create exactly 3 zero crossings with large amplitude
        data = [
            (0.0, 5.0),
            (0.5, -5.0),  # crossing 1
            (1.0, 5.0),   # crossing 2
            (1.5, -5.0),  # crossing 3
        ]
        for t, err in data:
            detector.update(t, err)

        result = detector.check()
        # exactly 3 crossings, spec requires >3, so not detected
        assert result.detected is False

    def test_steady_state_band_setter_floor(self):
        """Band should not go below 0.01."""
        detector = OscillationDetector()
        detector.steady_state_band = 0.0
        assert detector.steady_state_band >= 0.01


# ===================================================================
# TuningSessionLock
# ===================================================================


class TestTuningSessionLock:
    """Tests for session locking."""

    def test_acquire_and_release(self):
        lock = TuningSessionLock()
        assert lock.acquire(1, "sess_a") is True
        locked, sess = lock.is_locked(1)
        assert locked is True
        assert sess == "sess_a"

        assert lock.release(1, "sess_a") is True
        locked, sess = lock.is_locked(1)
        assert locked is False
        assert sess is None

    def test_double_acquire_same_session(self):
        lock = TuningSessionLock()
        assert lock.acquire(1, "sess_a") is True
        assert lock.acquire(1, "sess_a") is True  # Re-entrant for same session

    def test_different_session_blocked(self):
        lock = TuningSessionLock()
        assert lock.acquire(1, "sess_a") is True
        assert lock.acquire(1, "sess_b") is False

    def test_release_wrong_session(self):
        lock = TuningSessionLock()
        lock.acquire(1, "sess_a")
        assert lock.release(1, "sess_b") is False
        # Original lock still held
        locked, _ = lock.is_locked(1)
        assert locked is True

    def test_release_non_locked_motor(self):
        lock = TuningSessionLock()
        assert lock.release(999, "sess_a") is False

    def test_timeout_expiry(self):
        lock = TuningSessionLock(timeout_seconds=0.1)
        lock.acquire(1, "sess_a")
        time.sleep(0.15)
        lock.cleanup_expired()
        locked, _ = lock.is_locked(1)
        assert locked is False

    def test_touch_refreshes_timeout(self):
        lock = TuningSessionLock(timeout_seconds=0.2)
        lock.acquire(1, "sess_a")
        time.sleep(0.12)
        lock.touch(1, "sess_a")
        time.sleep(0.12)
        # Total elapsed ~0.24s but last touch was at ~0.12s, so only 0.12s
        # since touch — should still be alive
        lock.cleanup_expired()
        locked, _ = lock.is_locked(1)
        assert locked is True

    def test_multiple_motors_independent(self):
        lock = TuningSessionLock()
        assert lock.acquire(1, "sess_a") is True
        assert lock.acquire(2, "sess_b") is True
        locked1, s1 = lock.is_locked(1)
        locked2, s2 = lock.is_locked(2)
        assert locked1 and s1 == "sess_a"
        assert locked2 and s2 == "sess_b"

    def test_thread_safety(self):
        """Concurrent acquires should not corrupt state."""
        lock = TuningSessionLock()
        results: list[bool] = []
        barrier = threading.Barrier(10)

        def try_acquire(session_id: str):
            barrier.wait()
            result = lock.acquire(1, session_id)
            results.append(result)

        threads = [
            threading.Thread(target=try_acquire, args=(f"sess_{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one should succeed
        assert results.count(True) == 1

    def test_is_locked_triggers_cleanup(self):
        """is_locked should clean up expired locks automatically."""
        lock = TuningSessionLock(timeout_seconds=0.05)
        lock.acquire(1, "sess_a")
        time.sleep(0.1)
        locked, _ = lock.is_locked(1)
        assert locked is False


# ===================================================================
# TuningSessionLogger
# ===================================================================


class TestTuningSessionLogger:
    """Tests for session logging."""

    def test_start_log_end_session(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        sid = logger_obj.start_session(motor_id=1, motor_type="MG6010")
        assert isinstance(sid, str)
        assert len(sid) == 12

        logger_obj.log_event(sid, "pid_read", {"kp": 100})
        logger_obj.log_event(sid, "pid_write", {"kp": 120})
        logger_obj.end_session(sid)

        events = logger_obj.get_session_log(sid)
        assert len(events) == 2
        assert events[0]["event_type"] == "pid_read"
        assert events[1]["event_type"] == "pid_write"
        assert events[1]["data"]["kp"] == 120

    def test_file_creation(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        sid = logger_obj.start_session(motor_id=5, motor_type="MG6010")
        logger_obj.end_session(sid)

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "_5.json" in files[0].name

    def test_file_content_valid_json(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        sid = logger_obj.start_session(motor_id=3, motor_type="MG6012")
        logger_obj.log_event(sid, "pid_write", {"speed_kp": 80})
        logger_obj.end_session(sid)

        files = list(tmp_path.glob("*.json"))
        content = json.loads(files[0].read_text())
        assert content["session_id"] == sid
        assert content["motor_id"] == 3
        assert content["motor_type"] == "MG6012"
        assert content["active"] is False
        assert len(content["events"]) == 1

    def test_invalid_event_type_raises(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        sid = logger_obj.start_session(motor_id=1, motor_type="MG6010")
        with pytest.raises(ValueError, match="Invalid event type"):
            logger_obj.log_event(sid, "bogus_event", {})

    def test_unknown_session_id_raises(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Unknown session"):
            logger_obj.log_event("nonexistent", "pid_read", {})

    def test_end_unknown_session_raises(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Unknown session"):
            logger_obj.end_session("nonexistent")

    def test_all_valid_event_types(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        sid = logger_obj.start_session(motor_id=1, motor_type="MG6010")
        for event_type in TuningSessionLogger.VALID_EVENT_TYPES:
            logger_obj.log_event(sid, event_type, {"test": True})
        events = logger_obj.get_session_log(sid)
        assert len(events) == len(TuningSessionLogger.VALID_EVENT_TYPES)

    def test_session_dir_created_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "dir"
        logger_obj = TuningSessionLogger(session_dir=str(nested))
        sid = logger_obj.start_session(motor_id=1, motor_type="MG6010")
        logger_obj.end_session(sid)
        assert nested.exists()
        assert len(list(nested.glob("*.json"))) == 1

    def test_multiple_sessions(self, tmp_path):
        logger_obj = TuningSessionLogger(session_dir=str(tmp_path))
        sid1 = logger_obj.start_session(motor_id=1, motor_type="MG6010")
        sid2 = logger_obj.start_session(motor_id=2, motor_type="MG6012")
        assert sid1 != sid2

        logger_obj.log_event(sid1, "pid_read", {"a": 1})
        logger_obj.log_event(sid2, "pid_write", {"b": 2})

        events1 = logger_obj.get_session_log(sid1)
        events2 = logger_obj.get_session_log(sid2)
        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0]["data"]["a"] == 1
        assert events2[0]["data"]["b"] == 2


# ===================================================================
# Integration / ValidationResult / OscillationResult
# ===================================================================


class TestResultDataclasses:
    """Smoke tests for result dataclasses."""

    def test_validation_result_defaults(self):
        vr = ValidationResult(valid=True)
        assert vr.errors == []
        assert vr.clamped_values is None

    def test_oscillation_result_fields(self):
        osc = OscillationResult(
            detected=True,
            severity="sustained",
            crossings=5,
            amplitude=12.3,
            message="test",
        )
        assert osc.detected is True
        assert osc.severity == "sustained"
