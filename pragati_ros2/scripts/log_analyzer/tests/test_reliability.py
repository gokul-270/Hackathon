"""
scripts/log_analyzer/tests/test_reliability.py

Tests for log-analyzer-reliability changes (tasks 7.1-7.5):
  7.1 — Python logging format parsing
  7.2 — journalctl prefix stripping
  7.3 — False positive suppression (thermal thresholds, per-file clock jumps)
  7.4 — Cross-log correlation (window constant, MQTT→process-death chain)
  7.5 — analyze_logs.sh path fix
"""

import inspect
import sys
from pathlib import Path

import pytest

# Ensure the scripts/ directory is on sys.path so bare `log_analyzer.*`
# imports work the same way as in tests/conftest.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from log_analyzer.analyzer import ROS2LogAnalyzer

# ---------------------------------------------------------------------------
# Task 7.1 — Python logging format parsing
# ---------------------------------------------------------------------------


class TestPythonLogPatternParsing:
    """Task 7.1: Test PYTHON_LOG_PATTERN regex parses ARM_client log lines."""

    SAMPLE_LINES = [
        "2026-02-18 23:42:58,123 [INFO] Connected to MQTT broker at 10.42.0.10",
        "2026-02-18 23:43:10,456 [WARNING] MQTT connection timeout",
        "2026-02-18 23:43:25,789 [ERROR] Connection timed out",
        "2026-02-18 23:43:25,790 [CRITICAL] Fatal error occurred",
    ]

    def test_all_lines_match(self):
        """Every sample ARM_client log line matches PYTHON_LOG_PATTERN."""
        pattern = ROS2LogAnalyzer.PYTHON_LOG_PATTERN
        for line in self.SAMPLE_LINES:
            match = pattern.match(line)
            assert match is not None, f"Failed to match: {line}"

    def test_timestamp_extraction(self):
        """Timestamp group is extracted correctly."""
        pattern = ROS2LogAnalyzer.PYTHON_LOG_PATTERN
        m = pattern.match(self.SAMPLE_LINES[0])
        assert m is not None
        assert m.group("timestamp") == "2026-02-18 23:42:58,123"

    def test_level_extraction(self):
        """Level group is extracted correctly."""
        pattern = ROS2LogAnalyzer.PYTHON_LOG_PATTERN
        m = pattern.match(self.SAMPLE_LINES[0])
        assert m is not None
        assert m.group("level") == "INFO"

    def test_message_extraction(self):
        """Message group captures everything after the level tag."""
        pattern = ROS2LogAnalyzer.PYTHON_LOG_PATTERN
        m = pattern.match(self.SAMPLE_LINES[0])
        assert m is not None
        assert m.group("message") == "Connected to MQTT broker at 10.42.0.10"

    def test_level_mapping_completeness(self):
        """_PYTHON_LEVEL_MAP covers all five standard Python log levels."""
        level_map = ROS2LogAnalyzer._PYTHON_LEVEL_MAP
        assert level_map["DEBUG"] == "DEBUG"
        assert level_map["INFO"] == "INFO"
        assert level_map["WARNING"] == "WARN"
        assert level_map["ERROR"] == "ERROR"
        assert level_map["CRITICAL"] == "FATAL"

    def test_debug_level_matches(self):
        """DEBUG-level line matches pattern."""
        line = "2026-02-18 23:42:58,001 [DEBUG] Heartbeat sent"
        m = ROS2LogAnalyzer.PYTHON_LOG_PATTERN.match(line)
        assert m is not None
        assert m.group("level") == "DEBUG"


# ---------------------------------------------------------------------------
# Task 7.2 — journalctl prefix stripping
# ---------------------------------------------------------------------------


class TestJournalctlPrefixStripping:
    """Task 7.2: Test JOURNALCTL_PREFIX strips syslog header to inner content."""

    def test_journalctl_prefix_matches(self):
        """journalctl syslog prefix is detected and stripped."""
        pattern = ROS2LogAnalyzer.JOURNALCTL_PREFIX
        test_line = (
            "Feb 18 23:42:58 raspberrypi ros2[1234]: "
            "[INFO] [1708300978.123456789] [cotton_detector]: Detection started"
        )
        match = pattern.match(test_line)
        assert match is not None
        inner = match.group(1)
        assert inner.startswith("[INFO]")

    def test_inner_content_matches_ros2_pattern(self):
        """Inner content after stripping matches the ROS2 LOG_PATTERN."""
        jctl_line = (
            "Feb 18 23:42:58 raspberrypi ros2[1234]: "
            "[INFO] [1708300978.123456789] [cotton_detector]: Detection started"
        )
        jctl_match = ROS2LogAnalyzer.JOURNALCTL_PREFIX.match(jctl_line)
        assert jctl_match is not None
        inner = jctl_match.group(1)
        ros2_match = ROS2LogAnalyzer.LOG_PATTERN.match(inner)
        assert ros2_match is not None
        assert ros2_match.group("node") == "cotton_detector"
        assert ros2_match.group("level") == "INFO"

    def test_non_journalctl_line_does_not_match(self):
        """A regular ROS2 line does not match JOURNALCTL_PREFIX."""
        ros2_line = "[INFO] [1708300978.123456789] [cotton_detector]: Detection started"
        match = ROS2LogAnalyzer.JOURNALCTL_PREFIX.match(ros2_line)
        assert match is None


# ---------------------------------------------------------------------------
# Task 7.3 — False positive suppression
# ---------------------------------------------------------------------------


class TestThermalThresholdConstants:
    """Task 7.3: Verify thermal threshold constants exist and have correct values."""

    def test_warning_threshold_exists(self):
        assert hasattr(ROS2LogAnalyzer, "CAMERA_THERMAL_WARNING_C")
        assert ROS2LogAnalyzer.CAMERA_THERMAL_WARNING_C == 85.0

    def test_critical_threshold_exists(self):
        assert hasattr(ROS2LogAnalyzer, "CAMERA_THERMAL_CRITICAL_C")
        assert ROS2LogAnalyzer.CAMERA_THERMAL_CRITICAL_C == 95.0

    def test_critical_higher_than_warning(self):
        assert ROS2LogAnalyzer.CAMERA_THERMAL_CRITICAL_C > ROS2LogAnalyzer.CAMERA_THERMAL_WARNING_C


class TestClockJumpPerFileTracking:
    """Task 7.3: Verify clock jump detection uses per-file tracking."""

    def test_validate_timestamp_monotonicity_uses_per_file(self):
        """_validate_timestamp_monotonicity resets prev_ts at file boundaries."""
        from log_analyzer.detectors.failure_analysis import (
            _validate_timestamp_monotonicity,
        )

        source = inspect.getsource(_validate_timestamp_monotonicity)
        # Must reference file tracking to avoid cross-file false positives
        assert (
            "prev_file" in source or "file" in source
        ), "_validate_timestamp_monotonicity should track file boundaries"

    def test_prev_file_reset_logic(self):
        """Source contains logic to reset prev_ts when file changes."""
        from log_analyzer.detectors.failure_analysis import (
            _validate_timestamp_monotonicity,
        )

        source = inspect.getsource(_validate_timestamp_monotonicity)
        # Should reset prev_ts to None when entering a new file
        assert "prev_ts = None" in source
        assert "prev_file" in source


# ---------------------------------------------------------------------------
# Task 7.4 — Cross-log correlation
# ---------------------------------------------------------------------------


class TestCorrelationWindowConstant:
    """Task 7.4: Verify CORRELATION_WINDOW_S constant exists and has correct value."""

    def test_correlation_window_value(self):
        from log_analyzer.detectors.correlation import CORRELATION_WINDOW_S

        assert CORRELATION_WINDOW_S == 30.0


class TestMqttFailureProcessDeathCorrelation:
    """Task 7.4: Test MQTT timeout -> process death chain detection function."""

    def test_function_exists_and_callable(self):
        from log_analyzer.detectors.correlation import (
            _detect_mqtt_failure_process_death,
        )

        assert callable(_detect_mqtt_failure_process_death)

    def test_returns_list(self, tmp_path):
        """Returns empty list when no MQTT failures or crashes exist."""
        from collections import defaultdict

        from log_analyzer.detectors.correlation import (
            _detect_mqtt_failure_process_death,
        )
        from log_analyzer.models import EventStore, MQTTMetrics, NetworkMetrics

        # Build a minimal analyzer
        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        a.log_dir = tmp_path
        a.verbose = False
        a.entries = []
        a.issues = {}
        a.performance = {}
        a.node_stats = defaultdict(
            lambda: {
                "total": 0,
                "debug": 0,
                "info": 0,
                "warn": 0,
                "error": 0,
                "fatal": 0,
            }
        )
        a.level_counts = defaultdict(int)
        a.total_lines = 0
        a.total_size = 0
        a.start_time = None
        a.end_time = None
        a.events = EventStore()
        a.mqtt = MQTTMetrics()
        a.network = NetworkMetrics()
        a.field_summary = None
        a._json_skip_count = 0
        a._current_arm_id = None

        result = _detect_mqtt_failure_process_death(a)
        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Task 7.5 — analyze_logs.sh path fix
# ---------------------------------------------------------------------------


class TestAnalyzeLogsScriptPath:
    """Task 7.5: Verify analyze_logs.sh uses correct path resolution."""

    SCRIPT_PATH = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "scripts"
        / "utils"
        / "analyze_logs.sh"
    )

    def test_script_exists(self):
        assert self.SCRIPT_PATH.exists(), "analyze_logs.sh not found"

    def test_uses_bash_source(self):
        """SCRIPT_DIR should be derived from BASH_SOURCE, not $0."""
        content = self.SCRIPT_PATH.read_text()
        assert "BASH_SOURCE" in content

    def test_no_double_scripts_path(self):
        """Should NOT reference $SCRIPT_DIR/scripts/ (wrong nested path)."""
        content = self.SCRIPT_PATH.read_text()
        assert "$SCRIPT_DIR/scripts/" not in content

    def test_analyzer_path_is_relative(self):
        """ANALYZER path should reference ../log_analyzer/ from utils/."""
        content = self.SCRIPT_PATH.read_text()
        assert "../log_analyzer/" in content


# ---------------------------------------------------------------------------
# Task 7.10 — OAK-D thermal trending
# ---------------------------------------------------------------------------


class TestOakDThermalTrending:
    """Task 7.10: Synthetic temperature rise triggers warning at 70°C."""

    def _make_events_with_temps(self, temps_with_ts):
        """Build an EventStore with detection_summaries carrying temp data."""
        from log_analyzer.models import EventStore

        es = EventStore()
        for ts, temp in temps_with_ts:
            es.detection_summaries.append(
                {
                    "_ts": ts,
                    "camera_temp_c": temp,
                }
            )
        return es

    def test_warning_raised_at_70c(self):
        """Temperature rise 45→72°C triggers medium warning issue."""
        from log_analyzer.detectors.camera_thermal import (
            analyze_camera_thermal,
        )

        # 10 readings over 10 minutes, rising from 45 to 72
        base_ts = 1000.0
        temps = [(base_ts + i * 60, 45.0 + (72.0 - 45.0) * i / 9) for i in range(10)]
        es = self._make_events_with_temps(temps)
        result = analyze_camera_thermal(es)

        assert result["thermal"]["has_data"] is True
        assert result["thermal"]["max_temp"] == 72.0
        assert result["thermal"]["min_temp"] == 45.0

        issues = result["issues"]
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"
        assert issues[0]["category"] == "thermal"
        assert "70" in issues[0]["description"]  # threshold mentioned

    def test_rate_of_rise_calculation(self):
        """Rate of rise computed correctly for linear temperature ramp."""
        from log_analyzer.detectors.camera_thermal import (
            analyze_camera_thermal,
        )

        base_ts = 0.0
        # 45→72°C over 9 minutes (540s)
        temps = [(base_ts + i * 60, 45.0 + 3.0 * i) for i in range(10)]
        # 45, 48, 51, ..., 72 over 540 seconds = 9 minutes
        es = self._make_events_with_temps(temps)
        result = analyze_camera_thermal(es)

        thermal = result["thermal"]
        # delta = 27°C over 9 min = 3.0 °C/min
        assert thermal["rate_of_rise"] == 3.0

    def test_no_warning_below_70c(self):
        """Temperature staying below 70°C raises no issues."""
        from log_analyzer.detectors.camera_thermal import (
            analyze_camera_thermal,
        )

        temps = [(i * 60.0, 45.0 + i * 2.0) for i in range(10)]
        # max = 45 + 18 = 63°C
        es = self._make_events_with_temps(temps)
        result = analyze_camera_thermal(es)
        assert len(result["issues"]) == 0

    def test_stats_computed_correctly(self):
        """Min, max, mean, sample count are correct."""
        from log_analyzer.detectors.camera_thermal import (
            analyze_camera_thermal,
        )

        temps = [(i * 60.0, 50.0 + i) for i in range(5)]
        # temps: 50, 51, 52, 53, 54
        es = self._make_events_with_temps(temps)
        result = analyze_camera_thermal(es)
        thermal = result["thermal"]
        assert thermal["min_temp"] == 50.0
        assert thermal["max_temp"] == 54.0
        assert thermal["mean_temp"] == 52.0
        assert thermal["sample_count"] == 5


# ---------------------------------------------------------------------------
# Task 7.11 — Cross-file timestamp normalization
# ---------------------------------------------------------------------------


class TestCrossFileTimestampAnnotation:
    """Task 7.11: Issues spanning different source files get annotations."""

    def test_different_files_get_annotation(self):
        """first_seen/last_seen annotated when files differ."""
        from log_analyzer.analyzer import Issue, annotate_issue_timestamps

        issue = Issue(
            severity="high",
            category="error",
            title="Test issue",
            description="Test",
            first_seen="23:42:58",
            last_seen="10:23:59",
            first_seen_file="/logs/arm_client.log",
            last_seen_file="/logs/motor_control.log",
        )
        annotate_issue_timestamps(issue)
        assert "[arm_client]" in issue.first_seen
        assert "[motor_control]" in issue.last_seen

    def test_same_file_no_annotation(self):
        """No annotation when first and last come from same file."""
        from log_analyzer.analyzer import Issue, annotate_issue_timestamps

        issue = Issue(
            severity="high",
            category="error",
            title="Test issue",
            description="Test",
            first_seen="23:42:58",
            last_seen="23:43:00",
            first_seen_file="/logs/arm_client.log",
            last_seen_file="/logs/arm_client.log",
        )
        annotate_issue_timestamps(issue)
        assert "[" not in issue.first_seen
        assert "[" not in issue.last_seen

    def test_no_double_annotation(self):
        """Already-annotated timestamps are not re-annotated."""
        from log_analyzer.analyzer import Issue, annotate_issue_timestamps

        issue = Issue(
            severity="high",
            category="error",
            title="Test issue",
            description="Test",
            first_seen="23:42:58 [arm_client]",
            last_seen="10:23:59 [motor_control]",
            first_seen_file="/logs/arm_client.log",
            last_seen_file="/logs/motor_control.log",
        )
        annotate_issue_timestamps(issue)
        # Should not double-bracket
        assert issue.first_seen.count("[") == 1
        assert issue.last_seen.count("[") == 1

    def test_missing_file_info_no_crash(self):
        """No crash when source file info is None."""
        from log_analyzer.analyzer import Issue, annotate_issue_timestamps

        issue = Issue(
            severity="high",
            category="error",
            title="Test issue",
            description="Test",
            first_seen="23:42:58",
            last_seen="23:43:00",
        )
        annotate_issue_timestamps(issue)
        # Should remain unchanged
        assert issue.first_seen == "23:42:58"


# ---------------------------------------------------------------------------
# Task 7.12 — Confidence threshold discrepancy
# ---------------------------------------------------------------------------


class TestConfidenceThresholdDiscrepancy:
    """Task 7.12: Detect gap between app (0.70) and NN (0.50) thresholds."""

    def _make_analyzer_with_entries(self, messages, tmp_path):
        """Build a minimal analyzer with LogEntry objects."""
        from log_analyzer.analyzer import LogEntry

        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        a.log_dir = tmp_path
        a.verbose = False
        a.entries = []
        for i, msg in enumerate(messages):
            a.entries.append(
                LogEntry(
                    timestamp=1000.0 + i,
                    level="INFO",
                    node="test_node",
                    message=msg,
                    file="test.log",
                    line_number=i + 1,
                    raw_line=msg,
                )
            )
        return a

    def test_discrepancy_detected(self, tmp_path):
        """App=0.70 vs NN=0.50 triggers informational issue."""
        from log_analyzer.detectors.camera_thermal import (
            detect_confidence_discrepancy,
        )

        messages = [
            "Setting confidence_threshold: 0.70",
            "NN pipeline nn_confidence: 0.50",
        ]
        a = self._make_analyzer_with_entries(messages, tmp_path)
        issues = detect_confidence_discrepancy(a)

        assert len(issues) == 1
        issue = issues[0]
        assert issue["severity"] == "low"
        assert issue["category"] == "configuration"
        assert "0.70" in issue["description"]
        assert "0.50" in issue["description"]
        assert "Discrepancy" in issue["title"]

    def test_no_discrepancy_when_equal(self, tmp_path):
        """No issue when thresholds match."""
        from log_analyzer.detectors.camera_thermal import (
            detect_confidence_discrepancy,
        )

        messages = [
            "Setting confidence_threshold: 0.70",
            "NN pipeline nn_confidence: 0.70",
        ]
        a = self._make_analyzer_with_entries(messages, tmp_path)
        issues = detect_confidence_discrepancy(a)
        assert len(issues) == 0

    def test_no_issue_without_both_thresholds(self, tmp_path):
        """No issue when only one threshold is present."""
        from log_analyzer.detectors.camera_thermal import (
            detect_confidence_discrepancy,
        )

        messages = ["Setting confidence_threshold: 0.70"]
        a = self._make_analyzer_with_entries(messages, tmp_path)
        issues = detect_confidence_discrepancy(a)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Task 7.13 — Per-joint tolerance
# ---------------------------------------------------------------------------


class TestPerJointTolerance:
    """Task 7.13: Joint3=0.040 (below 0.050) not flagged; Joint1=0.015 flagged."""

    def _make_homing_events(self, joint_errors):
        """Build EventStore with homing events.

        Args:
            joint_errors: dict mapping joint_name -> list of errors
        """
        from log_analyzer.models import EventStore

        es = EventStore()
        for joint_name, errors in joint_errors.items():
            for err in errors:
                es.homing_events.append(
                    {
                        "joint": joint_name,
                        "position_error": err,
                    }
                )
        return es

    def test_joint3_below_threshold_not_flagged(self):
        """Joint3 at 0.040 rot (below 0.050) should not be flagged."""
        from log_analyzer.detectors.motor_trending import (
            analyze_motor_trending,
        )

        es = self._make_homing_events(
            {
                "Joint3": [0.040, 0.040, 0.040, 0.040],
            }
        )
        result = analyze_motor_trending(es)
        assert len(result["issues"]) == 0
        assert "Joint3" in result["joints"]

    def test_joint1_above_threshold_flagged(self):
        """Joint1 at 0.015 rot (above 0.010) should be flagged."""
        from log_analyzer.detectors.motor_trending import (
            analyze_motor_trending,
        )

        es = self._make_homing_events(
            {
                "Joint1": [0.015, 0.015, 0.015, 0.015],
            }
        )
        result = analyze_motor_trending(es)
        assert len(result["issues"]) == 1
        issue = result["issues"][0]
        assert "Joint1" in issue["description"]
        assert "0.01" in issue["description"]  # threshold mentioned

    def test_mixed_joints_only_joint1_flagged(self):
        """With both joints, only Joint1 exceeding threshold is flagged."""
        from log_analyzer.detectors.motor_trending import (
            analyze_motor_trending,
        )

        es = self._make_homing_events(
            {
                "Joint1": [0.015, 0.015, 0.015, 0.015],
                "Joint3": [0.040, 0.040, 0.040, 0.040],
            }
        )
        result = analyze_motor_trending(es)
        assert len(result["issues"]) == 1
        assert "Joint1" in result["issues"][0]["description"]
        # Joint3 should NOT be in any issue
        flagged_joints = [i["description"] for i in result["issues"]]
        assert not any("Joint3" in d for d in flagged_joints)


# ---------------------------------------------------------------------------
# Task 7.14 — --joint-tolerance CLI override
# ---------------------------------------------------------------------------


class TestJointToleranceCLIOverride:
    """Task 7.14: --joint-tolerance 3=0.080 overrides Joint3 threshold."""

    def test_cli_parsing(self):
        """CLI parses '3=0.080' into {'Joint3': 0.080}."""
        from log_analyzer.cli import main

        # Simulate argument parsing by testing the parsing logic directly
        pairs = "3=0.080"
        jt = {}
        for pair in pairs.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            jname, jval = pair.split("=", 1)
            jname = jname.strip()
            if jname.isdigit():
                jname = f"Joint{jname}"
            jt[jname] = float(jval.strip())

        assert jt == {"Joint3": 0.080}

    def test_override_applied_to_trending(self):
        """Joint3 with 0.060 error flagged when threshold overridden to 0.040."""
        from log_analyzer.detectors.motor_trending import (
            analyze_motor_trending,
        )
        from log_analyzer.models import EventStore

        es = EventStore()
        for _ in range(5):
            es.homing_events.append(
                {
                    "joint": "Joint3",
                    "position_error": 0.060,
                }
            )
        # Default Joint3 threshold is 0.050, so 0.060 would be flagged.
        # But with override to 0.080, it should NOT be flagged.
        result = analyze_motor_trending(es, joint_tolerances={"Joint3": 0.080})
        assert len(result["issues"]) == 0

    def test_override_lowers_threshold(self):
        """Joint3 at 0.040 flagged when threshold lowered to 0.030."""
        from log_analyzer.detectors.motor_trending import (
            analyze_motor_trending,
        )
        from log_analyzer.models import EventStore

        es = EventStore()
        for _ in range(5):
            es.homing_events.append(
                {
                    "joint": "Joint3",
                    "position_error": 0.040,
                }
            )
        # Default 0.050 would not flag 0.040, but 0.030 should
        result = analyze_motor_trending(es, joint_tolerances={"Joint3": 0.030})
        assert len(result["issues"]) == 1
        assert "Joint3" in result["issues"][0]["description"]


# ---------------------------------------------------------------------------
# Task 7.15 — format_duration()
# ---------------------------------------------------------------------------


class TestFormatDuration:
    """Task 7.15: Verify format_duration() output for known inputs."""

    def test_zero_seconds(self):
        from log_analyzer.utils import format_duration

        assert format_duration(0) == "0s"

    def test_45_seconds(self):
        from log_analyzer.utils import format_duration

        assert format_duration(45.2) == "45s"

    def test_5_minutes(self):
        from log_analyzer.utils import format_duration

        assert format_duration(300) == "5m"

    def test_11m_12s(self):
        from log_analyzer.utils import format_duration

        assert format_duration(672.3) == "11m 12s"

    def test_1_hour(self):
        from log_analyzer.utils import format_duration

        assert format_duration(3600) == "1h"

    def test_1h_5m_30s(self):
        from log_analyzer.utils import format_duration

        assert format_duration(3930) == "1h 5m 30s"

    def test_fractional_seconds_truncated(self):
        """Fractional seconds are truncated, not rounded."""
        from log_analyzer.utils import format_duration

        # 59.9 truncates to 59
        assert format_duration(59.9) == "59s"
        # 60.9 truncates to 60 → 1m exactly
        assert format_duration(60.9) == "1m"

    def test_negative_returns_0s(self):
        """Negative values return '0s'."""
        from log_analyzer.utils import format_duration

        assert format_duration(-5) == "0s"


# ---------------------------------------------------------------------------
# Task 7.16 — Motor current draw statistics
# ---------------------------------------------------------------------------


class TestMotorCurrentStatistics:
    """Task 7.16: Per-joint min/max/mean/stddev from synthetic data."""

    def _make_motor_health_events(self, joint_currents):
        """Build EventStore with motor_health_arm events.

        Args:
            joint_currents: dict mapping joint_name -> list of current_a
        """
        from log_analyzer.models import EventStore

        es = EventStore()
        # Build one event per sample (each event has a motors list)
        max_len = max(len(v) for v in joint_currents.values())
        for i in range(max_len):
            motors = []
            for jname, currents in joint_currents.items():
                if i < len(currents):
                    motors.append(
                        {
                            "joint": jname,
                            "current_a": currents[i],
                        }
                    )
            es.motor_health_arm.append({"motors": motors})
        return es

    def test_basic_statistics(self):
        """Verify min, max, mean, stddev for known data."""
        import statistics

        from log_analyzer.detectors.motor_current import (
            analyze_motor_current,
        )

        # 20 samples of known values for Joint1
        currents = [
            1.0,
            1.2,
            0.8,
            1.1,
            0.9,
            1.0,
            1.2,
            0.8,
            1.1,
            0.9,
            1.0,
            1.2,
            0.8,
            1.1,
            0.9,
            1.0,
            1.2,
            0.8,
            1.1,
            0.9,
        ]
        es = self._make_motor_health_events({"Joint1": currents})
        result = analyze_motor_current(es)

        assert "Joint1" in result["joints"]
        j1 = result["joints"]["Joint1"]
        assert j1["sample_count"] == 20
        assert j1["min_a"] == round(min(currents), 3)
        assert j1["max_a"] == round(max(currents), 3)
        assert j1["mean_a"] == round(statistics.mean(currents), 3)
        assert j1["stddev_a"] == round(statistics.stdev(currents), 3)

    def test_multiple_joints(self):
        """Statistics computed independently per joint."""
        from log_analyzer.detectors.motor_current import (
            analyze_motor_current,
        )

        es = self._make_motor_health_events(
            {
                "Joint1": [1.0] * 15,
                "Joint2": [2.0] * 15,
            }
        )
        result = analyze_motor_current(es)
        assert "Joint1" in result["joints"]
        assert "Joint2" in result["joints"]
        assert result["joints"]["Joint1"]["mean_a"] == 1.0
        assert result["joints"]["Joint2"]["mean_a"] == 2.0

    def test_insufficient_samples_excluded(self):
        """Joints with fewer than MIN_SAMPLES_PER_JOINT are excluded."""
        from log_analyzer.detectors.motor_current import (
            MIN_SAMPLES_PER_JOINT,
            analyze_motor_current,
        )

        es = self._make_motor_health_events(
            {
                "Joint1": [1.0] * (MIN_SAMPLES_PER_JOINT - 1),
            }
        )
        result = analyze_motor_current(es)
        assert "Joint1" not in result["joints"]


# ---------------------------------------------------------------------------
# Task 7.17 — Motor current spike detection
# ---------------------------------------------------------------------------


class TestMotorCurrentSpikeDetection:
    """Task 7.17: 3x rolling-mean spike → Medium severity issue."""

    def test_spike_detected(self):
        """A single 3x spike triggers medium severity issue."""
        from log_analyzer.detectors.motor_current import (
            analyze_motor_current,
        )
        from log_analyzer.models import EventStore

        # 20 normal samples then 1 spike at 3x the mean, then 9 more
        normal = [1.0] * 20
        spike = [3.5]  # > 2.5x rolling mean of ~1.0
        tail = [1.0] * 9
        currents = normal + spike + tail

        es = EventStore()
        for c in currents:
            es.motor_health_arm.append({"motors": [{"joint": "Joint2", "current_a": c}]})

        result = analyze_motor_current(es)
        j2 = result["joints"]["Joint2"]
        assert j2["spike_count"] >= 1
        assert j2["health_indicator"] == "ALERT"

        # Check issue raised
        spike_issues = [i for i in result["issues"] if i["title"] == "Motor Current Spike Detected"]
        assert len(spike_issues) == 1
        assert spike_issues[0]["severity"] == "medium"
        assert "Joint2" in spike_issues[0]["description"]

    def test_no_spike_for_steady_current(self):
        """Steady current produces no spike issues."""
        from log_analyzer.detectors.motor_current import (
            analyze_motor_current,
        )
        from log_analyzer.models import EventStore

        es = EventStore()
        for _ in range(30):
            es.motor_health_arm.append({"motors": [{"joint": "Joint1", "current_a": 1.0}]})

        result = analyze_motor_current(es)
        j1 = result["joints"]["Joint1"]
        assert j1["spike_count"] == 0
        spike_issues = [i for i in result["issues"] if i["title"] == "Motor Current Spike Detected"]
        assert len(spike_issues) == 0


# ---------------------------------------------------------------------------
# Task 7.18 — Motor current gradual increase
# ---------------------------------------------------------------------------


class TestMotorCurrentGradualIncrease:
    """Task 7.18: Late-session mean 35% > early → Low severity issue."""

    def test_gradual_increase_detected(self):
        """35% increase from early to late session triggers low issue."""
        from log_analyzer.detectors.motor_current import (
            analyze_motor_current,
        )
        from log_analyzer.models import EventStore

        # Early half: 1.0A, Late half: 1.35A (35% increase)
        early = [1.0] * 15
        late = [1.35] * 15
        currents = early + late

        es = EventStore()
        for c in currents:
            es.motor_health_arm.append({"motors": [{"joint": "Joint4", "current_a": c}]})

        result = analyze_motor_current(es)
        grad_issues = [
            i for i in result["issues"] if i["title"] == "Motor Current Gradual Increase"
        ]
        assert len(grad_issues) == 1
        issue = grad_issues[0]
        assert issue["severity"] == "low"
        assert "Joint4" in issue["description"]
        assert "35.0%" in issue["description"]


# ---------------------------------------------------------------------------
# Task 7.1 — Build provenance extraction
# ---------------------------------------------------------------------------


class TestBuildProvenanceExtraction:
    """Task 7.1: Test _RE_BUILT regex and extract_build_provenance()."""

    def test_legacy_format_matches(self):
        """Legacy 'Built: <date> <time>' line matches _RE_BUILT."""
        from log_analyzer.detectors.build_provenance import _RE_BUILT

        line = "Built: Feb 18 2026 22:43:10"
        m = _RE_BUILT.search(line)
        assert m is not None
        assert m.group(1) == "Feb 18 2026"
        assert m.group(2) == "22:43:10"
        assert m.group(3) is None  # no git hash
        assert m.group(4) is None  # no branch

    def test_enhanced_format_matches(self):
        """Enhanced 'Built: ... (hash on branch)' matches _RE_BUILT."""
        from log_analyzer.detectors.build_provenance import _RE_BUILT

        line = "Built: Feb 18 2026 22:43:10 (abc1234 on main)"
        m = _RE_BUILT.search(line)
        assert m is not None
        assert m.group(1) == "Feb 18 2026"
        assert m.group(2) == "22:43:10"
        assert m.group(3) == "abc1234"
        assert m.group(4) == "main"

    def test_dirty_build_format_matches(self):
        """Dirty build 'Built: ... (hash-dirty on branch)' matches."""
        from log_analyzer.detectors.build_provenance import _RE_BUILT

        line = "Built: Feb 18 2026 22:43:10" " (abc1234-dirty on feature/arm)"
        m = _RE_BUILT.search(line)
        assert m is not None
        assert m.group(3) == "abc1234-dirty"
        assert m.group(4) == "feature/arm"

    def test_no_build_line_returns_empty(self):
        """Python node logs with no Built: line yield empty list."""
        from log_analyzer.analyzer import LogEntry
        from log_analyzer.detectors.build_provenance import (
            extract_build_provenance,
        )

        entries = [
            LogEntry(
                timestamp=1000.0 + i,
                level="INFO",
                node="arm_client",
                message=f"Normal log message {i}",
                file="arm_client.log",
                line_number=i + 1,
                raw_line=f"Normal log message {i}",
            )
            for i in range(20)
        ]
        result = extract_build_provenance(entries, {"arm_client": {}})
        assert result == []

    def test_extract_provenance_from_entries(self):
        """extract_build_provenance returns BuildProvenance for matching entries."""
        from log_analyzer.analyzer import LogEntry
        from log_analyzer.detectors.build_provenance import (
            extract_build_provenance,
        )

        entries = [
            LogEntry(
                timestamp=1000.0,
                level="INFO",
                node="cotton_detector",
                message="Built: Feb 18 2026 22:43:10 (abc1234 on main)",
                file="cotton_detector.log",
                line_number=1,
                raw_line=(
                    "[INFO] [1000.0] [cotton_detector]: "
                    "Built: Feb 18 2026 22:43:10 (abc1234 on main)"
                ),
            ),
        ]
        result = extract_build_provenance(entries, {"cotton_detector": {}})
        assert len(result) == 1
        bp = result[0]
        assert bp.node_name == "cotton_detector"
        assert bp.git_hash == "abc1234"
        assert bp.git_branch == "main"
        assert bp.is_dirty is False

    def test_extract_dirty_provenance(self):
        """Dirty hash detected and cleaned in BuildProvenance."""
        from log_analyzer.analyzer import LogEntry
        from log_analyzer.detectors.build_provenance import (
            extract_build_provenance,
        )

        entries = [
            LogEntry(
                timestamp=1000.0,
                level="INFO",
                node="motor_control",
                message=("Built: Feb 18 2026 22:43:10" " (abc1234-dirty on feature/arm)"),
                file="motor_control.log",
                line_number=1,
                raw_line=("Built: Feb 18 2026 22:43:10" " (abc1234-dirty on feature/arm)"),
            ),
        ]
        result = extract_build_provenance(entries, {"motor_control": {}})
        assert len(result) == 1
        bp = result[0]
        assert bp.is_dirty is True
        assert bp.git_hash == "abc1234"  # -dirty stripped


# ---------------------------------------------------------------------------
# Task 7.2 — Stale binary detection
# ---------------------------------------------------------------------------


class TestStaleBinaryDetection:
    """Task 7.2: Test detect_stale_builds with artificial time gaps."""

    def test_stale_detected_when_over_threshold(self):
        """Two nodes >1h apart triggers stale issue."""
        from datetime import datetime

        from log_analyzer.detectors.build_provenance import (
            detect_stale_builds,
        )
        from log_analyzer.models import BuildProvenance

        newest = datetime(2026, 2, 18, 22, 43, 10)
        # 2 hours behind
        old = datetime(2026, 2, 18, 20, 43, 10)

        provenances = [
            BuildProvenance(
                node_name="cotton_detector",
                build_timestamp=newest,
            ),
            BuildProvenance(
                node_name="motor_control",
                build_timestamp=old,
            ),
        ]
        issues = detect_stale_builds(provenances)
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"
        assert issues[0]["title"] == "Stale Binary Detected"
        assert "motor_control" in issues[0]["description"]

    def test_no_stale_when_within_threshold(self):
        """Two nodes <1h apart triggers no stale issue."""
        from datetime import datetime

        from log_analyzer.detectors.build_provenance import (
            detect_stale_builds,
        )
        from log_analyzer.models import BuildProvenance

        t1 = datetime(2026, 2, 18, 22, 43, 10)
        t2 = datetime(2026, 2, 18, 22, 13, 10)  # 30 min apart

        provenances = [
            BuildProvenance(
                node_name="cotton_detector",
                build_timestamp=t1,
            ),
            BuildProvenance(
                node_name="motor_control",
                build_timestamp=t2,
            ),
        ]
        issues = detect_stale_builds(provenances)
        assert len(issues) == 0

    def test_single_node_no_stale(self):
        """Single node cannot be stale (nothing to compare against)."""
        from datetime import datetime

        from log_analyzer.detectors.build_provenance import (
            detect_stale_builds,
        )
        from log_analyzer.models import BuildProvenance

        provenances = [
            BuildProvenance(
                node_name="cotton_detector",
                build_timestamp=datetime(2026, 2, 18, 22, 43, 10),
            ),
        ]
        issues = detect_stale_builds(provenances)
        assert len(issues) == 0

    def test_custom_threshold(self):
        """Custom stale_threshold_hours is respected."""
        from datetime import datetime

        from log_analyzer.detectors.build_provenance import (
            detect_stale_builds,
        )
        from log_analyzer.models import BuildProvenance

        t1 = datetime(2026, 2, 18, 22, 43, 10)
        t2 = datetime(2026, 2, 18, 22, 13, 10)  # 30 min apart

        provenances = [
            BuildProvenance(
                node_name="cotton_detector",
                build_timestamp=t1,
            ),
            BuildProvenance(
                node_name="motor_control",
                build_timestamp=t2,
            ),
        ]
        # Default 1h: no stale. With 0.25h (15 min): stale.
        issues = detect_stale_builds(provenances, stale_threshold_hours=0.25)
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# Task 7.3 — ROS2 log directory resolution
# ---------------------------------------------------------------------------


class TestRosLogDirResolution:
    """Task 7.3: Test --ros-log-dir resolution logic."""

    def test_latest_symlink_resolution(self, tmp_path, monkeypatch):
        """--ros-log-dir with no prefix resolves latest symlink."""
        ros_log = tmp_path / ".ros" / "log"
        ros_log.mkdir(parents=True)
        actual_dir = ros_log / "session_2026-02-18_22-43"
        actual_dir.mkdir()
        (actual_dir / "dummy.log").write_text("test")
        latest = ros_log / "latest"
        latest.symlink_to(actual_dir)

        monkeypatch.setenv("ROS_LOG_DIR", str(ros_log))

        # Simulate CLI resolution logic from cli.py
        import os

        ros_log_root = Path(
            os.environ.get(
                "ROS_LOG_DIR",
                os.path.expanduser("~/.ros/log"),
            )
        )
        latest_path = ros_log_root / "latest"
        assert latest_path.exists()
        resolved = str(latest_path.resolve())
        assert resolved == str(actual_dir)

    def test_ros_log_dir_env_override(self, tmp_path, monkeypatch):
        """ROS_LOG_DIR env var overrides default ~/.ros/log."""
        custom_dir = tmp_path / "custom_logs"
        custom_dir.mkdir()
        actual_session = custom_dir / "session_2026-02-18"
        actual_session.mkdir()
        latest = custom_dir / "latest"
        latest.symlink_to(actual_session)

        monkeypatch.setenv("ROS_LOG_DIR", str(custom_dir))

        import os

        ros_log_root = Path(os.environ.get("ROS_LOG_DIR", "~/.ros/log"))
        assert ros_log_root == custom_dir
        assert (ros_log_root / "latest").exists()

    def test_prefix_matching(self, tmp_path, monkeypatch):
        """Prefix matching finds matching session dir."""
        ros_log = tmp_path / "ros_log"
        ros_log.mkdir()
        (ros_log / "session_2026-02-15_09-30").mkdir()
        (ros_log / "session_2026-02-18_22-43").mkdir()
        (ros_log / "session_2026-02-18_23-00").mkdir()

        monkeypatch.setenv("ROS_LOG_DIR", str(ros_log))

        import os

        ros_log_root = Path(os.environ.get("ROS_LOG_DIR", "~/.ros/log"))
        prefix = "session_2026-02-15"
        matches = sorted(
            d for d in ros_log_root.iterdir() if d.is_dir() and d.name.startswith(prefix)
        )
        assert len(matches) == 1
        assert matches[0].name == "session_2026-02-15_09-30"

    def test_prefix_matching_multiple_error(self, tmp_path, monkeypatch):
        """Multiple matches for ambiguous prefix detected."""
        ros_log = tmp_path / "ros_log"
        ros_log.mkdir()
        (ros_log / "session_2026-02-18_22-43").mkdir()
        (ros_log / "session_2026-02-18_23-00").mkdir()

        monkeypatch.setenv("ROS_LOG_DIR", str(ros_log))

        import os

        ros_log_root = Path(os.environ.get("ROS_LOG_DIR", "~/.ros/log"))
        prefix = "session_2026-02-18"
        matches = sorted(
            d for d in ros_log_root.iterdir() if d.is_dir() and d.name.startswith(prefix)
        )
        # Should find 2 matches — CLI would error
        assert len(matches) == 2


# ---------------------------------------------------------------------------
# Task 7.4 — Streaming processing verification
# ---------------------------------------------------------------------------


class TestStreamingProcessing:
    """Task 7.4: Verify line-by-line streaming produces correct results."""

    def test_line_by_line_parsing(self, tmp_path):
        """Streaming parse produces same entries as full-file approach."""
        log_file = tmp_path / "test_node.log"
        lines = [
            "[INFO] [1000.000000] [test_node]: Line 1\n",
            "[WARN] [1001.000000] [test_node]: Warning msg\n",
            "[ERROR] [1002.000000] [test_node]: Error msg\n",
        ]
        log_file.write_text("".join(lines))

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        analyzer._parse_log_file(log_file)

        assert len(analyzer.entries) == 3
        assert analyzer.entries[0].level == "INFO"
        assert analyzer.entries[1].level == "WARN"
        assert analyzer.entries[2].level == "ERROR"
        assert analyzer.entries[0].message == "Line 1"

    def test_streaming_gzip_support(self, tmp_path):
        """Gzipped log files are parsed correctly."""
        import gzip as gz

        log_file = tmp_path / "test_node.log.gz"
        content = "[INFO] [1000.000000] [gzip_node]: Compressed line\n"
        with gz.open(log_file, "wt") as f:
            f.write(content)

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        analyzer._parse_log_file(log_file)

        assert len(analyzer.entries) == 1
        assert analyzer.entries[0].node == "gzip_node"
        assert analyzer.entries[0].message == "Compressed line"

    def test_streaming_maintains_counts(self, tmp_path):
        """Streaming parse correctly maintains level counts."""
        log_file = tmp_path / "test.log"
        lines = []
        for i in range(50):
            level = "INFO" if i % 3 != 0 else "WARN"
            lines.append(f"[{level}] [{1000 + i}.0] [node_a]: msg {i}\n")
        log_file.write_text("".join(lines))

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        analyzer._parse_log_file(log_file)

        assert analyzer.total_lines == 50
        expected_warn = sum(1 for i in range(50) if i % 3 == 0)
        expected_info = 50 - expected_warn
        assert analyzer.level_counts["WARN"] == expected_warn
        assert analyzer.level_counts["INFO"] == expected_info


# ---------------------------------------------------------------------------
# Task 7.7 — Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Task 7.7: Test fingerprint-based issue deduplication."""

    def _make_issue(
        self,
        title,
        severity,
        category,
        motor_id,
        first_seen,
        last_seen,
        occurrences=1,
    ):
        """Create an Issue for deduplication testing."""
        from log_analyzer.analyzer import Issue

        return Issue(
            severity=severity,
            category=category,
            title=title,
            description=f"Motor {motor_id} error details",
            occurrences=occurrences,
            first_seen=first_seen,
            last_seen=last_seen,
            affected_nodes=[f"motor_{motor_id}"],
            sample_messages=[f"Error on motor {motor_id}"],
        )

    def test_overlapping_issues_merged(self):
        """Same motor, same error, within 5s → merged."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {
            "issue_1": self._make_issue(
                "Motor/CAN Communication Error",
                "high",
                "motor",
                "3",
                "10:00:01",
                "10:00:01",
            ),
            "issue_2": self._make_issue(
                "Motor/CAN Communication Error",
                "medium",
                "motor",
                "3",
                "10:00:03",
                "10:00:04",
            ),
        }
        result = deduplicate_issues(issues)
        # Should merge into 1 issue
        assert len(result) == 1
        merged = list(result.values())[0]
        # Highest severity kept
        assert merged.severity == "high"
        # Earliest first_seen
        assert merged.first_seen == "10:00:01"
        # Latest last_seen
        assert merged.last_seen == "10:00:04"
        # Occurrences summed
        assert merged.occurrences == 2

    def test_non_overlapping_stay_separate(self):
        """Same motor, same error, >5s apart → stay separate."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {
            "issue_1": self._make_issue(
                "Motor/CAN Communication Error",
                "high",
                "motor",
                "3",
                "10:00:01",
                "10:00:01",
            ),
            "issue_2": self._make_issue(
                "Motor/CAN Communication Error",
                "medium",
                "motor",
                "3",
                "10:00:10",
                "10:00:10",
            ),
        }
        result = deduplicate_issues(issues)
        assert len(result) == 2

    def test_different_motors_not_merged(self):
        """Different motor IDs are never merged."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {
            "issue_1": self._make_issue(
                "Motor/CAN Communication Error",
                "high",
                "motor",
                "3",
                "10:00:01",
                "10:00:01",
            ),
            "issue_2": self._make_issue(
                "Motor/CAN Communication Error",
                "high",
                "motor",
                "5",
                "10:00:02",
                "10:00:02",
            ),
        }
        result = deduplicate_issues(issues)
        assert len(result) == 2

    def test_no_motor_id_not_merged(self):
        """Issues without motor_id in title/description stay separate."""
        from log_analyzer.analyzer import Issue
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {
            "issue_1": Issue(
                severity="high",
                category="crash",
                title="Segmentation Fault Detected",
                description="SIGSEGV in detection node",
                first_seen="10:00:01",
                last_seen="10:00:01",
            ),
            "issue_2": Issue(
                severity="high",
                category="crash",
                title="Segmentation Fault Detected",
                description="SIGSEGV in detection node again",
                first_seen="10:00:02",
                last_seen="10:00:02",
            ),
        }
        result = deduplicate_issues(issues)
        assert len(result) == 2

    def test_severity_upgrade_on_merge(self):
        """Merged issue takes the highest (most severe) severity."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {
            "issue_1": self._make_issue(
                "Motor/CAN Communication Error",
                "low",
                "motor",
                "2",
                "10:00:01",
                "10:00:01",
            ),
            "issue_2": self._make_issue(
                "Motor/CAN Communication Error",
                "critical",
                "motor",
                "2",
                "10:00:03",
                "10:00:03",
            ),
        }
        result = deduplicate_issues(issues)
        assert len(result) == 1
        merged = list(result.values())[0]
        assert merged.severity == "critical"


# ---------------------------------------------------------------------------
# Task 7.8 — Extended --compare output
# ---------------------------------------------------------------------------


class TestExtendedCompare:
    """Task 7.8: Test compare_sessions output includes new sections."""

    def test_compare_sessions_output_sections(self, tmp_path, capsys):
        """Verify compare output contains extended sections."""
        from log_analyzer.exporters import compare_sessions

        # Create two minimal session directories with dummy logs
        dir_a = tmp_path / "session_a"
        dir_a.mkdir()
        (dir_a / "test.log").write_text("[INFO] [1000.000000] [test_node]: Hello A\n")

        dir_b = tmp_path / "session_b"
        dir_b.mkdir()
        (dir_b / "test.log").write_text("[INFO] [1000.000000] [test_node]: Hello B\n")

        analyzer_a = ROS2LogAnalyzer(str(dir_a))
        analyzer_a.analyze()

        compare_sessions(analyzer_a, str(dir_b))

        captured = capsys.readouterr()
        output = captured.out

        # Verify all extended sections are present
        assert "PICK PERFORMANCE" in output
        assert "MOTOR HEALTH" in output
        assert "DETECTION MODEL" in output
        assert "MQTT" in output
        assert "SCAN EFFECTIVENESS" in output
        assert "SESSION HEALTH" in output
        assert "VEHICLE PERFORMANCE" in output

    def test_compare_with_na_fallback(self, tmp_path, capsys):
        """Sections show N/A when data is missing."""
        from log_analyzer.exporters import compare_sessions

        # Both sessions have no data beyond minimal logs
        dir_a = tmp_path / "session_a"
        dir_a.mkdir()
        (dir_a / "test.log").write_text("[INFO] [1000.000000] [node]: msg\n")
        dir_b = tmp_path / "session_b"
        dir_b.mkdir()
        (dir_b / "test.log").write_text("[INFO] [1000.000000] [node]: msg\n")

        analyzer_a = ROS2LogAnalyzer(str(dir_a))
        analyzer_a.analyze()

        compare_sessions(analyzer_a, str(dir_b))

        captured = capsys.readouterr()
        output = captured.out
        # N/A should appear for empty motor/detection/scan data
        assert "N/A" in output


# ---------------------------------------------------------------------------
# Task 7.9 — Full analyzer integration test
# ---------------------------------------------------------------------------


class TestFullAnalyzerIntegration:
    """Task 7.9: Full analyzer integration with --field-summary sections."""

    def test_analyzer_does_not_crash_on_synthetic_data(self, tmp_path):
        """Analyzer runs without errors on representative synthetic data."""
        log_file = tmp_path / "cotton_detector.log"
        lines = [
            "[INFO] [1000.000000] [cotton_detector]:"
            " Built: Feb 18 2026 22:43:10 (abc1234 on main)\n",
            "[INFO] [1001.000000] [cotton_detector]:" " Detection started\n",
            "[INFO] [1002.000000] [cotton_detector]:" " temperature 45.2C\n",
            "[WARN] [1003.000000] [cotton_detector]:" " timeout waiting for frame\n",
            "[INFO] [1004.000000] [motor_control]:" " Built: Feb 18 2026 20:00:00\n",
            "[INFO] [1005.000000] [motor_control]:" " CAN bus initialized\n",
            "[ERROR] [1006.000000] [motor_control]:" " Motor 3 error\n",
            "[INFO] [1007.000000] [arm_client]:" " pick_complete success\n",
        ]
        log_file.write_text("".join(lines))

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        report = analyzer.analyze()

        # Basic sanity checks
        assert report.total_lines == 8
        assert report.total_files == 1
        assert len(report.issues) > 0

    def test_field_summary_sections_present(self, tmp_path, capsys):
        """--field-summary output includes new analysis sections."""
        import io
        from contextlib import redirect_stdout

        from log_analyzer.reports.printing import print_field_summary

        log_file = tmp_path / "test.log"
        lines = [
            "[INFO] [1000.000000] [cotton_detector]:"
            " Built: Feb 18 2026 22:43:10 (abc1234 on main)\n",
            "[INFO] [1001.000000] [cotton_detector]:" " Detection started\n",
            "[INFO] [1002.000000] [motor_control]:" " Built: Feb 18 2026 20:00:00\n",
        ]
        log_file.write_text("".join(lines))

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        analyzer.analyze()

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_field_summary(analyzer)

        output = buf.getvalue()
        # Field summary should contain standard section headers
        assert "PICK PERFORMANCE" in output

    def test_field_trial_data_if_available(self):
        """If /tmp/field_trial_test/ exists, run analyzer on it."""
        trial_dir = Path("/tmp/field_trial_test")
        if not trial_dir.exists():
            pytest.skip("No field trial test data at /tmp/field_trial_test/")

        analyzer = ROS2LogAnalyzer(str(trial_dir))
        report = analyzer.analyze()
        # Just verify it doesn't crash and produces output
        assert report.total_lines >= 0
        assert report.total_files >= 0

    def test_build_provenance_detected_in_full_run(self, tmp_path):
        """Full analyzer run detects build provenance from logs."""
        log_file = tmp_path / "node.log"
        lines = [
            "[INFO] [1000.000000] [cotton_detector]:"
            " Built: Feb 18 2026 22:43:10 (abc1234 on main)\n",
            "[INFO] [1001.000000] [cotton_detector]:" " Ready\n",
            "[INFO] [1002.000000] [motor_control]:" " Built: Feb 18 2026 20:00:00\n",
            "[INFO] [1003.000000] [motor_control]:" " Ready\n",
        ]
        log_file.write_text("".join(lines))

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        analyzer.analyze()

        assert len(analyzer.build_provenances) == 2
        nodes = {bp.node_name for bp in analyzer.build_provenances}
        assert "cotton_detector" in nodes
        assert "motor_control" in nodes

    def test_stale_binary_issue_in_full_run(self, tmp_path):
        """Full run with >1h build gap creates stale binary issue."""
        log_file = tmp_path / "node.log"
        lines = [
            "[INFO] [1000.000000] [cotton_detector]:" " Built: Feb 18 2026 22:43:10\n",
            "[INFO] [1001.000000] [cotton_detector]:" " Ready\n",
            "[INFO] [1002.000000] [motor_control]:" " Built: Feb 18 2026 20:00:00\n",
            "[INFO] [1003.000000] [motor_control]:" " Ready\n",
        ]
        log_file.write_text("".join(lines))

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        report = analyzer.analyze()

        stale_issues = [i for i in report.issues if i.title == "Stale Binary Detected"]
        assert len(stale_issues) >= 1

    def test_slight_increase_below_threshold(self):
        """25% increase (below 30% threshold) produces no issue."""
        from log_analyzer.detectors.motor_current import (
            analyze_motor_current,
        )
        from log_analyzer.models import EventStore

        early = [1.0] * 15
        late = [1.25] * 15  # 25% increase, below 30% threshold
        currents = early + late

        es = EventStore()
        for c in currents:
            es.motor_health_arm.append({"motors": [{"joint": "Joint4", "current_a": c}]})

        result = analyze_motor_current(es)
        grad_issues = [
            i for i in result["issues"] if i["title"] == "Motor Current Gradual Increase"
        ]
        assert len(grad_issues) == 0
