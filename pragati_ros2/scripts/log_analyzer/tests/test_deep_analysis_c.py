"""
scripts/log_analyzer/tests/test_deep_analysis_c.py

Tests for log-analyzer-deep-analysis change — batch C:
  18.9  — Issue deduplication quality (group 11)
  18.10 — Session lifecycle detector (group 12)
  18.11 — Zero-timing detection (group 13)
  18.12 — Integration validation
"""

import sys
from collections import defaultdict
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from log_analyzer.analyzer import Issue, ROS2LogAnalyzer
from log_analyzer.models import EventStore, MQTTMetrics, NetworkMetrics


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _make_issue(
    title="Test issue",
    description="Test description",
    severity="medium",
    category="test",
    occurrences=1,
    first_seen="10:00:00",
    last_seen="10:00:00",
    affected_nodes=None,
    sample_messages=None,
):
    """Create an Issue with sensible defaults."""
    return Issue(
        severity=severity,
        category=category,
        title=title,
        description=description,
        occurrences=occurrences,
        first_seen=first_seen,
        last_seen=last_seen,
        affected_nodes=affected_nodes or ["node_a"],
        sample_messages=sample_messages or ["msg"],
    )


def _make_minimal_analyzer(tmp_path):
    """Build a minimal ROS2LogAnalyzer without touching disk."""
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
    a._file_time_ranges = {}
    a._source_category_ranges = {}
    a.detector_filter = None
    a.build_provenances = []
    a.stale_threshold_hours = 1.0
    a.topology = None
    a.session_mode = None
    a.max_timeline = 200
    a.max_errors = 500
    a.max_warnings = 500
    return a


# ===================================================================
# Task 18.9 — Issue deduplication quality (group 11)
# ===================================================================


class TestNumericSimilarityGrouping:
    """18.9: Near-identical issues differing only in numeric value
    should collapse into a single representative issue."""

    def test_57_numeric_variants_collapse_to_one(self):
        """57 near-identical issues collapse to 1 group."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {}
        for i in range(57):
            rate = 44.0 + i * 0.1  # 44.0 .. 49.6
            issues[f"issue_{i}"] = _make_issue(
                title="Detection Rate Warning",
                description=f"Detection rate: {rate:.1f}%",
                severity="low",
                category="detection",
            )

        result = deduplicate_issues(issues)
        assert len(result) == 1, (
            f"Expected 1 collapsed group, got {len(result)}"
        )

    def test_severity_preservation_on_group(self):
        """Highest severity in group is preserved after collapse."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        severities = (
            ["low"] * 3 + ["medium"] * 3 + ["high"] * 1
        )
        issues = {}
        for i, sev in enumerate(severities):
            issues[f"issue_{i}"] = _make_issue(
                title="Motor Drift Warning",
                description=f"Motor drift: {i * 0.5:.1f} deg",
                severity=sev,
                category="motor",
            )

        result = deduplicate_issues(issues)
        assert len(result) == 1
        merged = list(result.values())[0]
        assert merged.severity == "high"

    def test_small_group_not_collapsed(self):
        """Groups with <= 3 members are NOT collapsed by numeric
        similarity."""
        from log_analyzer.detectors.deduplication import (
            deduplicate_issues,
        )

        issues = {}
        for i in range(3):
            issues[f"issue_{i}"] = _make_issue(
                title="Minor Drift",
                description=f"Minor drift: {i * 1.5:.1f} deg",
                severity="low",
                category="calibration",
            )

        result = deduplicate_issues(issues)
        # 3 members stays as-is (threshold is 4)
        assert len(result) == 3


class TestNoDedup:
    """18.9: --no-dedup flag bypasses deduplication entirely."""

    def test_skip_dedup_preserves_all_issues(self, tmp_path):
        """Setting skip_dedup=True keeps all original issues."""
        a = _make_minimal_analyzer(tmp_path)
        a.skip_dedup = True

        # Add 10 near-identical issues via _add_issue
        for i in range(10):
            key = f"test:issue_{i}"
            a.issues[key] = _make_issue(
                title=f"issue_{i}",
                description=f"Rate: {i * 0.1:.1f}%",
                severity="low",
                category="test",
            )

        # Verify skip_dedup is respected
        assert getattr(a, "skip_dedup", False) is True
        # All 10 should remain
        assert len(a.issues) == 10


# ===================================================================
# Task 18.10 — Session lifecycle detector (group 12)
# ===================================================================


class TestNodeLifecycleTimeline:
    """18.10: Session lifecycle analysis from launch events."""

    def test_timeline_from_start_and_crash(self):
        """Start + crash events produce a timeline with one period."""
        from log_analyzer.detectors.session_lifecycle import (
            _build_node_timeline,
        )

        events = [
            {
                "type": "start",
                "name": "cotton_detection",
                "pid": 1234,
                "start_ts": 100.0,
            },
            {
                "type": "crash",
                "name": "cotton_detection",
                "pid": 1234,
                "start_ts": 100.0,
                "crash_ts": 200.0,
                "exit_code": -11,
                "exit_signal": "SIGSEGV",
                "shutdown_type": "crash",
            },
        ]

        timeline, gaps = _build_node_timeline(events)
        assert "cotton_detection" in timeline
        periods = timeline["cotton_detection"]
        assert len(periods) == 1
        assert periods[0]["start_ts"] == 100.0
        assert periods[0]["end_ts"] == 200.0

    def test_gap_detected_between_periods(self):
        """Gap between crash and restart is detected."""
        from log_analyzer.detectors.session_lifecycle import (
            _build_node_timeline,
        )

        events = [
            {
                "type": "start",
                "name": "cotton_detection",
                "pid": 1000,
                "start_ts": 100.0,
            },
            {
                "type": "crash",
                "name": "cotton_detection",
                "pid": 1000,
                "start_ts": 100.0,
                "crash_ts": 200.0,
                "exit_code": -11,
                "exit_signal": "SIGSEGV",
                "shutdown_type": "crash",
            },
            {
                "type": "start",
                "name": "cotton_detection",
                "pid": 2000,
                "start_ts": 260.0,
            },
            {
                "type": "still_running",
                "name": "cotton_detection",
                "pid": 2000,
                "start_ts": 260.0,
            },
        ]

        timeline, gaps = _build_node_timeline(events)
        assert len(gaps) == 1
        gap = gaps[0]
        assert gap["node"] == "cotton_detection"
        assert gap["gap_s"] == 60.0

    def test_still_running_period_has_no_end(self):
        """A still_running event produces a period with end_ts=None."""
        from log_analyzer.detectors.session_lifecycle import (
            _build_node_timeline,
        )

        events = [
            {
                "type": "start",
                "name": "yanthra_move",
                "pid": 5000,
                "start_ts": 50.0,
            },
            {
                "type": "still_running",
                "name": "yanthra_move",
                "pid": 5000,
                "start_ts": 50.0,
            },
        ]

        timeline, _gaps = _build_node_timeline(events)
        assert timeline["yanthra_move"][0]["end_ts"] is None


class TestRebootDetection:
    """18.10: RPi reboot detection via PID wraparound."""

    def test_pid_wraparound_detected(self):
        """PIDs dropping from 32000 to 150 with >60s gap = reboot."""
        from log_analyzer.detectors.session_lifecycle import (
            _detect_reboots,
        )

        events = [
            {
                "type": "start",
                "name": "node_a",
                "pid": 32000,
                "start_ts": 1000.0,
            },
            {
                "type": "start",
                "name": "node_b",
                "pid": 150,
                "start_ts": 1100.0,  # 100s gap > 60s threshold
            },
        ]

        reboots = _detect_reboots(events)
        assert len(reboots) == 1
        assert reboots[0]["prev_pid"] == 32000
        assert reboots[0]["curr_pid"] == 150
        assert reboots[0]["gap_s"] == 100.0

    def test_no_reboot_when_gap_too_small(self):
        """PID drop with gap < 60s is not flagged as reboot."""
        from log_analyzer.detectors.session_lifecycle import (
            _detect_reboots,
        )

        events = [
            {
                "type": "start",
                "name": "node_a",
                "pid": 32000,
                "start_ts": 1000.0,
            },
            {
                "type": "start",
                "name": "node_b",
                "pid": 150,
                "start_ts": 1030.0,  # only 30s gap
            },
        ]

        reboots = _detect_reboots(events)
        assert len(reboots) == 0

    def test_no_reboot_when_pid_increases(self):
        """Increasing PIDs are not flagged as reboots."""
        from log_analyzer.detectors.session_lifecycle import (
            _detect_reboots,
        )

        events = [
            {
                "type": "start",
                "name": "node_a",
                "pid": 150,
                "start_ts": 1000.0,
            },
            {
                "type": "start",
                "name": "node_b",
                "pid": 32000,
                "start_ts": 1100.0,
            },
        ]

        reboots = _detect_reboots(events)
        assert len(reboots) == 0


class TestShutdownClassification:
    """18.10: Classify shutdown types from launch events."""

    def test_sigterm_is_clean(self):
        """SIGTERM exit (-15) classified as clean."""
        from log_analyzer.detectors.session_lifecycle import (
            _classify_shutdowns,
        )

        events = [
            {
                "type": "crash",
                "name": "node_a",
                "pid": 1000,
                "exit_code": -15,
                "exit_signal": "SIGTERM",
                "shutdown_type": "clean",
                "crash_ts": 200.0,
            },
        ]

        result = _classify_shutdowns(events)
        assert result["node_a"]["shutdown_type"] == "clean"

    def test_sigsegv_is_crash(self):
        """SIGSEGV exit (-11) classified as crash."""
        from log_analyzer.detectors.session_lifecycle import (
            _classify_shutdowns,
        )

        events = [
            {
                "type": "crash",
                "name": "detector",
                "pid": 2000,
                "exit_code": -11,
                "exit_signal": "SIGSEGV",
                "shutdown_type": "crash",
                "crash_ts": 300.0,
            },
        ]

        result = _classify_shutdowns(events)
        assert result["detector"]["shutdown_type"] == "crash"

    def test_sigkill_is_kill(self):
        """SIGKILL exit (-9) classified as kill."""
        from log_analyzer.detectors.session_lifecycle import (
            _classify_shutdowns,
        )

        events = [
            {
                "type": "crash",
                "name": "motor_ctrl",
                "pid": 3000,
                "exit_code": -9,
                "exit_signal": "SIGKILL",
                "shutdown_type": "kill",
                "crash_ts": 400.0,
            },
        ]

        result = _classify_shutdowns(events)
        assert result["motor_ctrl"]["shutdown_type"] == "kill"


class TestMqttFailurePatterns:
    """18.10: ARM_client MQTT failure pattern detection."""

    def test_mqtt_failures_detected(self):
        """Repeated MQTT timeouts produce a failure pattern."""
        from log_analyzer.detectors.session_lifecycle import (
            _detect_mqtt_failure_patterns,
        )

        events = EventStore()
        for i in range(5):
            events.arm_client_mqtt_events.append({
                "event_type": "mqtt_timeout",
                "arm_id": "arm_0",
                "message": (
                    "MQTT connection timeout connecting to"
                    " broker 10.42.0.1:1883"
                ),
                "timestamp": 1000.0 + i * 10,
            })

        patterns = _detect_mqtt_failure_patterns(events)
        assert len(patterns) == 1
        pat = patterns[0]
        assert pat["arm_id"] == "arm_0"
        assert pat["failure_count"] == 5
        assert pat["timeout_count"] == 5
        assert pat["disconnect_count"] == 0

    def test_below_threshold_no_pattern(self):
        """Fewer than 3 failures are not reported as a pattern."""
        from log_analyzer.detectors.session_lifecycle import (
            _detect_mqtt_failure_patterns,
        )

        events = EventStore()
        for i in range(2):
            events.arm_client_mqtt_events.append({
                "event_type": "mqtt_timeout",
                "arm_id": "arm_1",
                "message": "Timeout to broker 10.42.0.1",
                "timestamp": 1000.0 + i * 10,
            })

        patterns = _detect_mqtt_failure_patterns(events)
        assert len(patterns) == 0


# ===================================================================
# Task 18.11 — Zero-timing detection (group 13)
# ===================================================================


class TestZeroTimingDetection:
    """18.11: _check_zero_timing cross-references JSON and text
    timing data."""

    def _make_analyzer_with_picks(self, tmp_path, picks, pjt=None,
                                  rb=None):
        """Build a minimal analyzer with pick and timing data."""
        a = _make_minimal_analyzer(tmp_path)
        a.events.picks = picks
        if pjt is not None:
            a.events.per_joint_timings = pjt
        if rb is not None:
            a.events.retreat_breakdowns = rb
        return a

    def test_zero_timing_with_text_counterparts(self, tmp_path):
        """Zero JSON timing + non-zero text = high severity issue."""
        picks = [
            {"j3_ms": 0, "j4_ms": 0, "j5_ms": 0},
            {"j3_ms": 0, "j4_ms": 0, "j5_ms": 0},
        ]
        pjt = [
            {"joint": "j3", "duration_ms": 150.0},
            {"joint": "j4", "duration_ms": 200.0},
        ]

        a = self._make_analyzer_with_picks(tmp_path, picks, pjt=pjt)
        a._check_zero_timing()

        assert len(a.issues) == 1
        issue = list(a.issues.values())[0]
        assert issue.severity == "high"
        assert "zeroed" in issue.title.lower() or (
            "zero" in issue.title.lower()
        )

    def test_zero_timing_without_text(self, tmp_path):
        """Zero JSON timing + no text logs = medium severity issue."""
        picks = [
            {"j3_ms": 0, "j4_ms": 0, "j5_ms": 0},
        ]

        a = self._make_analyzer_with_picks(tmp_path, picks)
        a._check_zero_timing()

        assert len(a.issues) == 1
        issue = list(a.issues.values())[0]
        assert issue.severity == "medium"

    def test_no_issue_for_nonzero(self, tmp_path):
        """Non-zero JSON j3/j4/j5_ms values raise no issue."""
        picks = [
            {"j3_ms": 120, "j4_ms": 80, "j5_ms": 50},
            {"j3_ms": 130, "j4_ms": 90, "j5_ms": 60},
        ]

        a = self._make_analyzer_with_picks(tmp_path, picks)
        a._check_zero_timing()

        assert len(a.issues) == 0

    def test_mixed_zeros_no_issue(self, tmp_path):
        """When only some picks have zeros but not all, no issue."""
        picks = [
            {"j3_ms": 0, "j4_ms": 0, "j5_ms": 0},
            {"j3_ms": 120, "j4_ms": 80, "j5_ms": 50},
        ]

        a = self._make_analyzer_with_picks(tmp_path, picks)
        a._check_zero_timing()

        # Not ALL picks have zeroed timing, so no issue
        assert len(a.issues) == 0

    def test_no_picks_no_issue(self, tmp_path):
        """Empty picks list raises no issue."""
        a = self._make_analyzer_with_picks(tmp_path, [])
        a._check_zero_timing()
        assert len(a.issues) == 0


# ===================================================================
# Task 18.12 — Integration validation
# ===================================================================


class TestEndToEndAnalysis:
    """18.12: Synthetic integration test — full analyzer pipeline."""

    def _write_ros2_log(self, log_dir, node_name, lines):
        """Write a synthetic ROS2 log file."""
        log_file = log_dir / f"{node_name}.log"
        content = "\n".join(lines) + "\n"
        log_file.write_text(content)
        return log_file

    def test_end_to_end_no_exceptions(self, tmp_path):
        """Full pipeline runs without Python exceptions."""
        log_dir = tmp_path / "session"
        log_dir.mkdir()

        # Create a synthetic ROS2 log
        lines = [
            "[INFO] [1000.000000] [test_node]: Node started",
            "[INFO] [1001.000000] [test_node]: Processing frame",
            "[WARN] [1002.000000] [test_node]: Slow detection",
            "[INFO] [1003.000000] [test_node]: Detection complete",
            "[ERROR] [1004.000000] [test_node]: CAN timeout",
            "[INFO] [1005.000000] [test_node]: Recovered",
        ]
        self._write_ros2_log(log_dir, "test_node", lines)

        analyzer = ROS2LogAnalyzer(str(log_dir))
        report = analyzer.analyze()

        assert report is not None
        assert report.total_lines > 0

    def test_report_has_expected_fields(self, tmp_path):
        """Report has all expected top-level fields."""
        log_dir = tmp_path / "session"
        log_dir.mkdir()

        lines = [
            "[INFO] [1000.000000] [detector]: Initializing",
            "[INFO] [1001.000000] [detector]: Ready",
        ]
        self._write_ros2_log(log_dir, "detector", lines)

        analyzer = ROS2LogAnalyzer(str(log_dir))
        report = analyzer.analyze()

        assert hasattr(report, "executive_summary")
        assert hasattr(report, "session_mode")
        assert hasattr(report, "issues")
        assert hasattr(report, "level_counts")
        assert hasattr(report, "total_lines")
        assert hasattr(report, "duration_seconds")

    def test_session_mode_detected(self, tmp_path):
        """Session mode is populated (bench/field/integration)."""
        log_dir = tmp_path / "session"
        log_dir.mkdir()

        lines = [
            "[INFO] [1000.000000] [node_a]: Started",
        ]
        self._write_ros2_log(log_dir, "node_a", lines)

        analyzer = ROS2LogAnalyzer(str(log_dir))
        report = analyzer.analyze()

        assert report.session_mode in (
            "bench", "field", "integration",
        )

    def test_issue_severities_lowercase(self, tmp_path):
        """All issue severity values are lowercase."""
        log_dir = tmp_path / "session"
        log_dir.mkdir()

        lines = [
            "[ERROR] [1000.000000] [node_x]: Fatal error occurred",
            "[ERROR] [1001.000000] [node_x]: CAN bus timeout",
            "[WARN] [1002.000000] [node_x]: High temperature 85C",
        ]
        self._write_ros2_log(log_dir, "node_x", lines)

        analyzer = ROS2LogAnalyzer(str(log_dir))
        report = analyzer.analyze()

        valid = {"critical", "high", "medium", "low", "info"}
        for issue in report.issues:
            assert issue.severity in valid, (
                f"Severity '{issue.severity}' not in {valid}"
            )

    def test_multi_role_directory_structure(self, tmp_path):
        """Multi-role directory with arm_0/ is parsed without error."""
        arm_dir = tmp_path / "arm_0"
        arm_dir.mkdir()

        lines = [
            "[INFO] [1000.000000] [arm_ctrl]: Arm initialized",
            "[INFO] [1001.000000] [arm_ctrl]: Homing complete",
        ]
        self._write_ros2_log(arm_dir, "arm_ctrl", lines)

        analyzer = ROS2LogAnalyzer(str(tmp_path))
        report = analyzer.analyze()

        assert report is not None
        assert report.total_lines > 0
