"""
tests/test_detectors.py

Tests for issue detectors: vehicle issues, arm issues, cross-correlation,
MQTT issues, motor command correlation, EE position monitoring,
stale detection rate, joint limit analysis, and compressor dominance.

Tasks: 21.8–21.10, 21.19, 11.5, 22.2–22.4, 22.9 (detect_border_skip_rate)
"""

import json
from unittest.mock import patch

import pytest

from log_analyzer import arm_patterns as _arm
from log_analyzer import detectors as _det
from log_analyzer import mqtt as _mqtt
from log_analyzer import parser as _parser
from log_analyzer.analyzer import ROS2LogAnalyzer
from log_analyzer.models import EventStore, NetworkMetrics

from conftest import make_minimal_analyzer


# ---------------------------------------------------------------------------
# task 21.8 — vehicle issue detection
# ---------------------------------------------------------------------------


class TestVehicleIssueDetection:
    def _make_analyzer_with_log(self, tmp_path, lines):
        """Build an analyzer with the given lines in a .log file and run analyze()."""
        log_file = tmp_path / "vehicle.log"
        log_file.write_text("\n".join(lines) + "\n")
        a = ROS2LogAnalyzer(str(tmp_path))
        # Run analyze but swallow stdout
        with patch("builtins.print"):
            try:
                report = a.analyze()
            except SystemExit:
                pass  # log might produce no-file-found warnings
        return a

    def test_state_error_detected(self, tmp_path):
        """A state_transition to ERROR state generates an issue."""
        lines = [
            "[ERROR] [1700000001.000] [vehicle_control_node]: [TIMING] "
            + json.dumps(
                {
                    "event": "state_transition",
                    "from_state": "AUTO",
                    "to_state": "ERROR",
                    "error_cause": "motor_fault",
                }
            )
        ]
        a = self._make_analyzer_with_log(tmp_path, lines)
        titles = [i.title for i in a.issues.values()]
        assert any("error" in t.lower() or "state" in t.lower() for t in titles)

    def test_estop_high_latency(self, tmp_path):
        """A state_transition with estop_latency_ms > 500ms triggers a high-severity issue."""
        lines = [
            "[INFO] [1700000001.000] [vehicle_control_node]: [TIMING] "
            + json.dumps(
                {
                    "event": "state_transition",
                    "from_state": "AUTO",
                    "to_state": "ESTOP",
                    "estop_latency_ms": 800,
                }
            )
        ]
        a = self._make_analyzer_with_log(tmp_path, lines)
        severities = [i.severity for i in a.issues.values()]
        assert any(s in ("high", "critical") for s in severities)


# ---------------------------------------------------------------------------
# task 21.9 — arm issue detection
# ---------------------------------------------------------------------------


class TestArmIssueDetection:
    def _make_analyzer_with_log(self, tmp_path, lines):
        log_file = tmp_path / "arm.log"
        log_file.write_text("\n".join(lines) + "\n")
        a = ROS2LogAnalyzer(str(tmp_path))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        return a

    def test_motor_thermal_issue(self, tmp_path):
        """Arm motor temperature >75°C triggers a thermal issue."""
        motor_list = [
            {
                "joint": "J1",
                "temp_c": 80.0,
                "ok": True,
                "voltage_v": 24.0,
                "current_a": 5.0,
                "health": 0.9,
                "err_flags": 0,
                "cmds": 10,
                "warnings": 0,
            }
        ]
        lines = [
            "[INFO] [1700000001.000] [arm_node]: "
            + json.dumps(
                {
                    "event": "motor_health",
                    "vbus_v": 24.0,
                    "uptime_s": 60.0,
                    "degraded": False,
                    "motors": motor_list,
                }
            )
        ]
        a = self._make_analyzer_with_log(tmp_path, lines)
        titles = " ".join(i.title.lower() for i in a.issues.values())
        assert "thermal" in titles or "temperature" in titles or "motor" in titles

    def test_critical_motor_alert(self, tmp_path):
        """A critical motor_alert event generates a critical issue."""
        lines = [
            "[ERROR] [1700000001.000] [arm_node]: "
            + json.dumps(
                {
                    "event": "motor_alert",
                    "joint": "J1",
                    "level": "critical",
                    "message": "Overcurrent",
                }
            )
        ]
        a = self._make_analyzer_with_log(tmp_path, lines)
        issues = list(a.issues.values())
        assert any(i.severity == "critical" for i in issues)


# ---------------------------------------------------------------------------
# task 21.10 — cross-correlation
# ---------------------------------------------------------------------------


class TestCrossCorrelation:
    def test_pick_during_motion_detected(self, tmp_path):
        """A pick event during an active drive_command triggers an issue."""
        a = make_minimal_analyzer(tmp_path)

        # Add a drive_command that spans the pick timestamp
        a.events.drive_commands.append(
            {
                "_ts": 100.0,
                "total_ms": 5000,  # 5 seconds → ends at 105.0
            }
        )
        # Add a pick during the drive window
        a.events.picks.append(
            {
                "_ts": 102.0,
                "success": True,
            }
        )

        _det.correlate_picks_with_vehicle_state(a)
        # A picks_during_motion count should be computed
        picks_during = getattr(a.events, "_picks_during_motion", 0)
        assert picks_during >= 1

    def test_failure_chain_detection(self, tmp_path):
        """Consecutive pick failures within a window are flagged as a chain."""
        a = make_minimal_analyzer(tmp_path)
        base_ts = 1700000000.0
        for i in range(4):
            a.events.picks.append({"_ts": base_ts + i * 10.0, "success": False})

        _det.detect_failure_chains(a)
        chains = getattr(a.events, "_failure_chains", [])
        assert len(chains) >= 1
        assert chains[0]["length"] >= 4


# ---------------------------------------------------------------------------
# task 21.19 — MQTT issue detection
# ---------------------------------------------------------------------------


class TestMQTTIssueDetection:
    def test_frequent_disconnects_flagged(self, tmp_path):
        """More than 5 disconnects in a session triggers a frequent-disconnect issue."""
        a = make_minimal_analyzer(tmp_path)
        base = 1700000000.0
        for i in range(7):
            a.mqtt.disconnects.append(
                {
                    "_ts": base + i * 30.0,
                    "type": "unexpected",
                    "rc": 1,
                }
            )
        _mqtt.detect_mqtt_issues(a)
        issues = list(a.issues.values())
        titles = " ".join(i.title.lower() for i in issues)
        assert "disconnect" in titles or "mqtt" in titles

    def test_extended_disconnect_flagged(self, tmp_path):
        """A single MQTT disconnect lasting >5 minutes triggers an issue."""
        a = make_minimal_analyzer(tmp_path)
        a.mqtt.health_checks.append(
            {
                "_ts": 1700000000.0,
                "connected": False,
                "failures": 3,
                "disconnect_duration_s": 400.0,  # > 5 min
            }
        )
        _mqtt.detect_mqtt_issues(a)
        issues = list(a.issues.values())
        assert len(issues) >= 1


# ---------------------------------------------------------------------------
# task 11.5 — Motor-command cross-correlation detector tests
# ---------------------------------------------------------------------------


def _make_motor_health(arm_id, joints_rx: dict, ts: float = 1700000000.0) -> dict:
    """Build a motor_health_arm record with cmds.rx per joint."""
    motors = [
        {"joint": j, "temp_c": 30.0, "cmds": {"rx": rx}, "err_flags": 0}
        for j, rx in joints_rx.items()
    ]
    return {
        "event": "motor_health",
        "_ts": ts,
        "_node": "arm_control",
        "motors": motors,
        "arm_id": arm_id,
    }


def _make_real_pick(arm_id=None, ts: float = 1700000001.0) -> dict:
    """Build a pick_complete record with real joint motion (approach_ms > 10)."""
    return {
        "event": "pick_complete",
        "success": True,
        "approach_ms": 500,
        "total_ms": 1200,
        "_ts": ts,
        "_node": "motion_controller",
        "arm_id": arm_id,
    }


class TestMotorCommandCorrelation:
    """task 11.5 — correlate_motor_commands_with_picking detector."""

    def test_all_motors_have_commands_no_issue(self):
        """(a) all motors have cmds.rx > 0 with picks → no issue."""
        events = EventStore()
        events.picks.append(_make_real_pick())
        events.motor_health_arm.append(
            _make_motor_health(None, {"joint3": 10, "joint4": 5})
        )

        issues = _det.correlate_motor_commands_with_picking(events)
        assert issues == []

    def test_all_motors_zero_commands_critical(self):
        """(b) all motors have cmds.rx == 0 with picks → Critical issue."""
        events = EventStore()
        events.picks.append(_make_real_pick())
        events.motor_health_arm.append(
            _make_motor_health(None, {"joint3": 0, "joint4": 0})
        )

        issues = _det.correlate_motor_commands_with_picking(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["category"] == "coordination"
        assert "0 commands" in issues[0]["message"]
        assert "9b35007" in issues[0]["message"]

    def test_mixed_commands_high_severity(self):
        """(c) some motors have cmds.rx == 0, others > 0 → High issue."""
        events = EventStore()
        events.picks.append(_make_real_pick())
        events.motor_health_arm.append(
            _make_motor_health(
                None, {"joint3": 0, "joint4": 10, "joint5": 7}
            )
        )

        issues = _det.correlate_motor_commands_with_picking(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "Partial" in issues[0]["title"]
        assert "1 of 3" in issues[0]["message"]

    def test_no_picks_no_issue(self):
        """(d) no picks at all → no issue regardless of cmds.rx."""
        events = EventStore()
        # No picks added — motor_health_arm has data but nothing to correlate against
        events.motor_health_arm.append(
            _make_motor_health(None, {"joint3": 0})
        )

        issues = _det.correlate_motor_commands_with_picking(events)
        assert issues == []

    def test_no_real_picks_no_issue(self):
        """Picks with approach_ms <= 10 are not 'real' picks — no issue."""
        events = EventStore()
        # approach_ms=5 — not a real pick
        events.picks.append(
            {
                "event": "pick_complete",
                "success": True,
                "approach_ms": 5,
                "_ts": 1700000001.0,
                "arm_id": None,
            }
        )
        events.motor_health_arm.append(
            _make_motor_health(None, {"joint3": 0})
        )

        issues = _det.correlate_motor_commands_with_picking(events)
        assert issues == []

    def test_multi_arm_only_bad_arm_flagged(self):
        """(e) multi-arm: arm_1 healthy, arm_2 zero commands → issue only for arm_2."""
        events = EventStore()
        events.picks.append(_make_real_pick(arm_id="arm_1"))
        events.picks.append(_make_real_pick(arm_id="arm_2"))
        events.motor_health_arm.append(
            _make_motor_health("arm_1", {"joint3": 10, "joint4": 8})
        )
        events.motor_health_arm.append(
            _make_motor_health("arm_2", {"joint3": 0, "joint4": 0})
        )

        issues = _det.correlate_motor_commands_with_picking(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["arm_id"] == "arm_2"
        assert "arm_id=arm_2" in issues[0]["title"]

    def test_wired_into_analyzer(self, tmp_path):
        """task 11.4 — analyzer issues list includes motor command correlation results."""
        # Build minimal logs that parse a real pick + motor health with zero cmds.rx.
        # motor_health events need "vbus_v" to be recognised as arm-side by the parser.
        pick_ev = {
            "event": "pick_complete",
            "success": True,
            "approach_ms": 500,
            "total_ms": 1200,
            "ts": 1700000001000,
        }
        mh_ev = {
            "event": "motor_health",
            "vbus_v": 24.0,
            "motors": [
                {
                    "joint": "joint3",
                    "temp_c": 30.0,
                    "cmds": {"rx": 0},
                    "err_flags": 0,
                }
            ],
            "ts": 1700000000000,
        }
        log = tmp_path / "arm_client.log"
        log.write_text(
            f"[INFO] [1700000000.000] [arm_control_node]: {json.dumps(mh_ev)}\n"
            f"[INFO] [1700000001.000] [motion_controller_node]:"
            f" {json.dumps(pick_ev)}\n"
        )

        a = ROS2LogAnalyzer(str(tmp_path))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass

        titles = [i.title for i in a.issues.values()]
        assert any(
            "0 commands" in t or "Motor controller" in t for t in titles
        ), f"Expected motor command correlation issue, got: {titles}"


# ---------------------------------------------------------------------------
# task 22.2 — EE Position Monitoring
# ---------------------------------------------------------------------------


class TestEEPositionMonitoring:
    """task 22.2 — detect_ee_timeout_rate detector behaviour."""

    def test_timeout_majority_emits_high_issue(self, tmp_path):
        """6 of 7 ee events are timeouts (85.7%) → High issue emitted."""
        events = EventStore()
        for _ in range(6):
            events.ee_monitoring_events.append(
                {"type": "timeout", "_ts": 1.0, "arm_id": None}
            )
        events.ee_monitoring_events.append(
            {"type": "success", "_ts": 2.0, "arm_id": None}
        )

        issues = _det.detect_ee_timeout_rate(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_below_threshold_no_issue(self, tmp_path):
        """2 timeouts out of 7 total (28.5%) → no issue (rate ≤ 50%)."""
        events = EventStore()
        for _ in range(2):
            events.ee_monitoring_events.append(
                {"type": "timeout", "_ts": 1.0, "arm_id": None}
            )
        for _ in range(5):
            events.ee_monitoring_events.append(
                {"type": "success", "_ts": 1.0, "arm_id": None}
            )

        issues = _det.detect_ee_timeout_rate(events)
        assert issues == []

    def test_fewer_than_5_events_no_issue(self, tmp_path):
        """3 timeouts, 0 successes = 100% but only 3 events → no issue (min sample)."""
        events = EventStore()
        for _ in range(3):
            events.ee_monitoring_events.append(
                {"type": "timeout", "_ts": 1.0, "arm_id": None}
            )

        issues = _det.detect_ee_timeout_rate(events)
        assert issues == []

    def test_no_ee_events_no_issue(self, tmp_path):
        """Empty ee_monitoring_events → no issue."""
        events = EventStore()
        issues = _det.detect_ee_timeout_rate(events)
        assert issues == []


# ---------------------------------------------------------------------------
# task 22.3 — Stale Detection Rate
# ---------------------------------------------------------------------------


class TestStaleDetectionRate:
    """task 22.3 — detect_stale_detection_rate detector behaviour."""

    def test_75pct_stale_emits_high(self):
        """15 of 20 picks with detection_age_ms > 2000 → High issue."""
        events = EventStore()
        for _ in range(15):
            events.picks.append(
                {"detection_age_ms": 3000, "_ts": 1.0, "arm_id": None}
            )
        for _ in range(5):
            events.picks.append(
                {"detection_age_ms": 500, "_ts": 1.0, "arm_id": None}
            )

        issues = _det.detect_stale_detection_rate(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_85pct_stale_emits_critical(self):
        """17 of 20 picks with detection_age_ms > 2000 → Critical issue."""
        events = EventStore()
        for _ in range(17):
            events.picks.append(
                {"detection_age_ms": 5000, "_ts": 1.0, "arm_id": None}
            )
        for _ in range(3):
            events.picks.append(
                {"detection_age_ms": 100, "_ts": 1.0, "arm_id": None}
            )

        issues = _det.detect_stale_detection_rate(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"

    def test_below_50pct_no_issue(self):
        """8 of 20 picks stale (40%) → no issue (rate ≤ 50%)."""
        events = EventStore()
        for _ in range(8):
            events.picks.append(
                {"detection_age_ms": 3000, "_ts": 1.0, "arm_id": None}
            )
        for _ in range(12):
            events.picks.append(
                {"detection_age_ms": 200, "_ts": 1.0, "arm_id": None}
            )

        issues = _det.detect_stale_detection_rate(events)
        assert issues == []


# ---------------------------------------------------------------------------
# task 22.4 — Joint Limit Analysis
# ---------------------------------------------------------------------------


class TestJointLimitAnalysis:
    """task 22.4 — detect_joint_limit_pattern detector behaviour."""

    def test_concentrated_violations_emits_medium(self):
        """3 of 4 violations at same J4 offset (75%) → Medium issue."""
        events = EventStore()
        for _ in range(3):
            events.joint_limit_events.append(
                {
                    "joint_name": "Joint4",
                    "direction": "right",
                    "calculated_m": 0.15,
                    "_ts": 1.0,
                    "arm_id": None,
                }
            )
        events.joint_limit_events.append(
            {
                "joint_name": "Joint4",
                "direction": "left",
                "calculated_m": -0.10,
                "_ts": 1.0,
                "arm_id": None,
            }
        )

        issues = _det.detect_joint_limit_pattern(events)
        severities = [i["severity"] for i in issues]
        assert "medium" in severities
        # Verify the message references the J4 offset, not the joint name
        medium_issues = [i for i in issues if i["severity"] == "medium"]
        assert any("0.15" in i.get("title", "") for i in medium_issues)

    def test_high_violation_rate_vs_picks(self):
        """5 violations with 20 total picks (25%) → High issue."""
        events = EventStore()
        for i in range(5):
            events.joint_limit_events.append(
                {
                    "joint_name": f"Joint{i % 3}",
                    "direction": "right",
                    "_ts": 1.0,
                    "arm_id": None,
                }
            )
        for _ in range(20):
            events.picks.append(
                {"success": True, "_ts": 1.0, "arm_id": None}
            )

        issues = _det.detect_joint_limit_pattern(events)
        severities = [i["severity"] for i in issues]
        assert "high" in severities

    def test_no_violations_no_issue(self):
        """No joint_limit_events → empty issues list."""
        events = EventStore()
        issues = _det.detect_joint_limit_pattern(events)
        assert issues == []


# ---------------------------------------------------------------------------
# Verify fix #6 — Compressor dominance + bottleneck joint detectors
# ---------------------------------------------------------------------------


class TestCompressorDominance:
    """Verify fix #6 — detect_compressor_dominance detector behaviour."""

    def test_compressor_dominance_emits_low(self):
        """Retreat breakdowns where compressor > 80% of total → Low issue."""
        events = EventStore()
        # compressor_ms = 900 out of total 1000 = 90%
        for _ in range(5):
            events.retreat_breakdowns.append(
                {
                    "j5_ms": 20,
                    "ee_off_ms": 10,
                    "j3_ms": 30,
                    "j4_ms": 40,
                    "compressor_ms": 900,
                    "_ts": 1.0,
                    "arm_id": None,
                }
            )
        issues = _det.detect_compressor_dominance(events)
        low_issues = [i for i in issues if i["severity"] == "low"]
        assert any("Compressor" in i["title"] for i in low_issues)

    def test_bottleneck_joint_emits_low(self):
        """One joint p95 > 2x the other → Low issue with joint name in title."""
        events = EventStore()
        # j3: 10 timings at 500ms, j4: 10 timings at 100ms → p95 ratio = 5x
        for _ in range(10):
            events.per_joint_timings.append(
                {"joint": "j3", "duration_ms": 500, "_ts": 1.0, "arm_id": None}
            )
        for _ in range(10):
            events.per_joint_timings.append(
                {"joint": "j4", "duration_ms": 100, "_ts": 1.0, "arm_id": None}
            )
        issues = _det.detect_compressor_dominance(events)
        low_issues = [i for i in issues if i["severity"] == "low"]
        assert any("j3" in i["title"] for i in low_issues)

    def test_no_dominance_no_issue(self):
        """Even split → no compressor dominance issue emitted."""
        events = EventStore()
        # compressor_ms = 100 out of total 500 = 20%
        events.retreat_breakdowns.append(
            {
                "j5_ms": 100,
                "ee_off_ms": 100,
                "j3_ms": 100,
                "j4_ms": 100,
                "compressor_ms": 100,
                "_ts": 1.0,
                "arm_id": None,
            }
        )
        issues = _det.detect_compressor_dominance(events)
        compressor_issues = [
            i for i in issues if "Compressor" in i.get("title", "")
        ]
        assert compressor_issues == []


# ---------------------------------------------------------------------------
# task 6.5 — Zero joint movement detector
# ---------------------------------------------------------------------------


class TestZeroJointMovementDetector:
    """task 6.5 — detect_zero_joint_movement detector behaviour."""

    @staticmethod
    def _make_pick(
        approach_ms=500, j3_ms=100, j4_ms=100, j5_ms=100
    ):
        """Build a pick dict with joint timing fields."""
        return {
            "event": "pick_complete",
            "success": True,
            "approach_ms": approach_ms,
            "j3_ms": j3_ms,
            "j4_ms": j4_ms,
            "j5_ms": j5_ms,
            "_ts": 1700000000.0,
            "arm_id": None,
        }

    def test_all_zero_joints_high_severity(self):
        """10/10 picks with zero joints (100%) → high + instrumentation gap."""
        events = EventStore()
        for _ in range(10):
            events.picks.append(
                self._make_pick(
                    approach_ms=5000, j3_ms=0, j4_ms=0, j5_ms=0
                )
            )
        issues = _det.detect_zero_joint_movement(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "instrumentation gap" in issues[0]["message"]

    def test_some_zero_joints_medium_severity(self):
        """3/10 picks with zero joints (30%) → medium + stuck joint."""
        events = EventStore()
        for _ in range(3):
            events.picks.append(
                self._make_pick(
                    approach_ms=5000, j3_ms=0, j4_ms=0, j5_ms=0
                )
            )
        for _ in range(7):
            events.picks.append(
                self._make_pick(
                    approach_ms=5000, j3_ms=200, j4_ms=150, j5_ms=100
                )
            )
        issues = _det.detect_zero_joint_movement(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"
        assert "stuck joint" in issues[0]["message"]

    def test_few_zero_joints_low_severity(self):
        """1/20 picks with zero joints (5%) → low severity."""
        events = EventStore()
        events.picks.append(
            self._make_pick(
                approach_ms=5000, j3_ms=0, j4_ms=0, j5_ms=0
            )
        )
        for _ in range(19):
            events.picks.append(
                self._make_pick(
                    approach_ms=5000, j3_ms=200, j4_ms=150, j5_ms=100
                )
            )
        issues = _det.detect_zero_joint_movement(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "low"

    def test_no_zero_joints_no_issue(self):
        """All picks have non-zero joint times → no issue."""
        events = EventStore()
        for _ in range(10):
            events.picks.append(
                self._make_pick(
                    approach_ms=5000, j3_ms=200, j4_ms=150, j5_ms=100
                )
            )
        issues = _det.detect_zero_joint_movement(events)
        assert issues == []

    def test_zero_approach_excluded(self):
        """Picks with approach_ms=0 are skipped entirely → no issue."""
        events = EventStore()
        for _ in range(10):
            events.picks.append(
                self._make_pick(
                    approach_ms=0, j3_ms=0, j4_ms=0, j5_ms=0
                )
            )
        issues = _det.detect_zero_joint_movement(events)
        assert issues == []

    def test_empty_picks_no_issue(self):
        """Empty picks list → no issue."""
        events = EventStore()
        issues = _det.detect_zero_joint_movement(events)
        assert issues == []
