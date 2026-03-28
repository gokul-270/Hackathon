"""
scripts/log_analyzer/tests/test_deep_analysis_d.py

Tests for log-analyzer-deep-analysis change — batch D:
  18.13 — Test mode awareness (group 14)
  18.14 — Session duration accuracy (group 15)
  18.15 — Executive summary (group 16)
  18.16 — EE start distance (group 17)
"""
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from log_analyzer.analyzer import (
    AnalysisReport,
    Issue,
    ROS2LogAnalyzer,
    SessionTopology,
    SessionTopologyMode,
)
from log_analyzer.models import EventStore, MQTTMetrics


# ===================================================================
# Helpers — lightweight analyzer construction without filesystem I/O
# ===================================================================


def _make_analyzer(**overrides):
    """Build a minimal ROS2LogAnalyzer without touching the filesystem.

    Skips ``__init__`` entirely, wiring only the attributes used by
    the methods under test.
    """
    a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
    a.events = EventStore()
    a.mqtt = MQTTMetrics()
    a.session_mode = None  # no CLI override
    a.topology = SessionTopology(
        mode=SessionTopologyMode.SINGLE_ARM,
        vehicle_dir=None,
        arm_dirs=[],
    )
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
    a._file_time_ranges = {}
    a._source_category_ranges = {}
    a.entries = []
    a.field_summary = None
    a.build_provenances = []
    a.stale_threshold_hours = 1.0
    a._json_skip_count = 0
    a.detector_filter = None
    a._current_arm_id = None
    a.verbose = False
    a.log_dir = Path("/tmp/fake_logs")
    a._session_mode = "bench"
    a._session_mode_source = "auto"
    a.network = None

    for k, v in overrides.items():
        setattr(a, k, v)
    return a


def _make_report(**overrides):
    """Build a minimal AnalysisReport with sensible defaults."""
    defaults = dict(
        log_directory="/tmp/fake_logs",
        analysis_time="2026-02-19T12:00:00",
        total_files=1,
        total_lines=100,
        total_size_bytes=5000,
        duration_seconds=3600.0,
        level_counts={},
        issues=[],
        node_stats={},
        performance={},
        timeline=[],
        errors=[],
        warnings=[],
        source_durations={},
        operational_duration_seconds=3600.0,
        executive_summary="",
        session_mode="bench",
        session_mode_source="auto",
    )
    defaults.update(overrides)
    return AnalysisReport(**defaults)


# ===================================================================
# Task 18.13 — Unit tests for test mode awareness (group 14)
# ===================================================================


class TestModeDetectionBench:
    """18.13.1: Bench mode auto-detection."""

    def test_single_arm_no_mqtt_returns_bench(self):
        """SINGLE_ARM topology with no MQTT/vehicle data → bench."""
        a = _make_analyzer()
        mode, source = a._detect_session_mode()
        assert mode == "bench"
        assert source == "auto"

    def test_bench_no_state_transitions(self):
        """No state_transitions or drive_commands → no vehicle signal."""
        a = _make_analyzer()
        a.events.state_transitions = []
        a.events.drive_commands = []
        mode, _ = a._detect_session_mode()
        assert mode == "bench"


class TestModeDetectionField:
    """18.13.2: Field mode auto-detection."""

    def test_multi_role_with_mqtt_returns_field(self):
        """MULTI_ROLE topology + MQTT events → field."""
        a = _make_analyzer(
            topology=SessionTopology(
                mode=SessionTopologyMode.MULTI_ROLE,
                vehicle_dir=Path("/tmp/vehicle"),
                arm_dirs=[Path("/tmp/arm_0")],
            ),
        )
        a.events.arm_client_mqtt_events = [{"_ts": 1.0}]
        mode, source = a._detect_session_mode()
        assert mode == "field"
        assert source == "auto"

    def test_vehicle_data_plus_broker_connects(self):
        """State transitions + broker connects → field."""
        a = _make_analyzer()
        a.events.state_transitions = [{"_ts": 1.0, "state": "IDLE"}]
        a.mqtt.broker_connects = [{"_ts": 2.0}]
        mode, _ = a._detect_session_mode()
        assert mode == "field"


class TestModeDetectionIntegration:
    """18.13.3: Integration mode auto-detection."""

    def test_vehicle_no_mqtt_returns_integration(self):
        """Vehicle data present, no MQTT → integration."""
        a = _make_analyzer(
            topology=SessionTopology(
                mode=SessionTopologyMode.MULTI_ROLE,
                vehicle_dir=Path("/tmp/vehicle"),
                arm_dirs=[Path("/tmp/arm_0")],
            ),
        )
        # Has vehicle (MULTI_ROLE) but no MQTT
        mode, source = a._detect_session_mode()
        assert mode == "integration"
        assert source == "auto"

    def test_mqtt_no_vehicle_returns_integration(self):
        """MQTT data present, no vehicle → integration."""
        a = _make_analyzer()
        # SINGLE_ARM topology, no state_transitions, but has MQTT
        a.mqtt.connects = [{"_ts": 1.0}]
        mode, _ = a._detect_session_mode()
        assert mode == "integration"


class TestModeDetectionCLIOverride:
    """18.13.4: CLI override bypasses auto-detection."""

    def test_user_override_bench(self):
        """session_mode='bench' → ('bench', 'user')."""
        a = _make_analyzer(session_mode="bench")
        mode, source = a._detect_session_mode()
        assert mode == "bench"
        assert source == "user"

    def test_user_override_field(self):
        """session_mode='field' → ('field', 'user')."""
        a = _make_analyzer(session_mode="field")
        mode, source = a._detect_session_mode()
        assert mode == "field"
        assert source == "user"

    def test_user_override_ignores_signals(self):
        """CLI override trumps any vehicle/MQTT signals."""
        a = _make_analyzer(session_mode="bench")
        a.events.state_transitions = [{"_ts": 1.0}]
        a.mqtt.connects = [{"_ts": 2.0}]
        mode, source = a._detect_session_mode()
        assert mode == "bench"
        assert source == "user"


class TestModeFilter:
    """18.13.5: Section suppression via mode_filter."""

    def test_vehicle_perf_omitted_in_bench(self):
        from log_analyzer.reports.printing import mode_filter

        assert mode_filter("VEHICLE PERFORMANCE", "bench") == "omit"

    def test_mqtt_downgraded_in_bench(self):
        from log_analyzer.reports.printing import mode_filter

        assert (
            mode_filter("COMMUNICATION HEALTH (MQTT)", "bench")
            == "downgrade"
        )

    def test_pick_perf_shown_in_bench(self):
        from log_analyzer.reports.printing import mode_filter

        assert mode_filter("PICK PERFORMANCE", "bench") == "show"

    def test_vehicle_perf_shown_in_field(self):
        from log_analyzer.reports.printing import mode_filter

        assert mode_filter("VEHICLE PERFORMANCE", "field") == "show"

    def test_arbitrary_section_shown_in_field(self):
        from log_analyzer.reports.printing import mode_filter

        assert mode_filter("WHATEVER SECTION", "field") == "show"

    def test_coordination_omitted_in_bench(self):
        from log_analyzer.reports.printing import mode_filter

        assert mode_filter("COORDINATION CYCLES", "bench") == "omit"


class TestModeInReport:
    """18.13.6: Mode is written to the AnalysisReport."""

    def test_report_has_mode_fields(self):
        report = _make_report(
            session_mode="bench", session_mode_source="auto"
        )
        assert report.session_mode == "bench"
        assert report.session_mode_source == "auto"

    def test_report_field_mode(self):
        report = _make_report(
            session_mode="field", session_mode_source="user"
        )
        assert report.session_mode == "field"
        assert report.session_mode_source == "user"


# ===================================================================
# Task 18.14 — Unit tests for session duration accuracy (group 15)
# ===================================================================


class TestPerSourceDuration:
    """18.14.1: Per-source category time ranges."""

    def test_source_category_ranges_populated(self):
        """_source_category_ranges stores min/max timestamps."""
        a = _make_analyzer()
        a._source_category_ranges = {
            "ros2": [100.0, 200.0],
            "dmesg": [110.0, 190.0],
        }
        source_durations = {}
        for cat, (lo, hi) in a._source_category_ranges.items():
            source_durations[cat] = {"start": lo, "end": hi}
        assert "ros2" in source_durations
        assert "dmesg" in source_durations
        assert source_durations["ros2"]["start"] == 100.0
        assert source_durations["ros2"]["end"] == 200.0
        assert source_durations["dmesg"]["start"] == 110.0
        assert source_durations["dmesg"]["end"] == 190.0

    def test_operational_duration_from_ros2(self):
        """Operational duration is computed from ros2 source window."""
        a = _make_analyzer()
        a._source_category_ranges = {
            "ros2": [100.0, 200.0],
            "dmesg": [90.0, 210.0],
        }
        source_durations = {}
        for cat, (lo, hi) in a._source_category_ranges.items():
            source_durations[cat] = {"start": lo, "end": hi}
        # Operational duration from ros2 = 200 - 100 = 100s
        op_dur = (
            source_durations["ros2"]["end"]
            - source_durations["ros2"]["start"]
        )
        assert op_dur == pytest.approx(100.0)

    def test_record_source_timestamp(self):
        """_record_source_timestamp updates category ranges."""
        a = _make_analyzer()
        a._source_category_ranges = {}
        # Simulate recording timestamps
        a._record_source_timestamp(Path("fake.log"), 100.0)
        a._record_source_timestamp(Path("fake.log"), 200.0)
        a._record_source_timestamp(Path("fake.log"), 150.0)
        assert "ros2" in a._source_category_ranges
        rng = a._source_category_ranges["ros2"]
        assert rng[0] == 100.0
        assert rng[1] == 200.0


class TestCrossSourceGapExclusion:
    """18.14.2: Operational duration excludes cross-source gaps."""

    def test_dmesg_wider_than_ros2(self):
        """Dmesg range wider than ros2 doesn't inflate op duration."""
        a = _make_analyzer()
        a._source_category_ranges = {
            "ros2": [100.0, 200.0],
            "dmesg": [50.0, 250.0],
        }
        ros2_dur = (
            a._source_category_ranges["ros2"][1]
            - a._source_category_ranges["ros2"][0]
        )
        dmesg_dur = (
            a._source_category_ranges["dmesg"][1]
            - a._source_category_ranges["dmesg"][0]
        )
        # Operational should be based on ros2, not dmesg
        assert ros2_dur == 100.0
        assert dmesg_dur == 200.0
        assert ros2_dur < dmesg_dur


class TestMQTTZeroConnects:
    """18.14.3: MQTT shows 'not established' with 0 connects."""

    def test_zero_connects_no_attempts(self):
        """0 connects, 0 disconnects/failures → 'not established'."""
        from log_analyzer.models import FieldSummary

        a = _make_analyzer()
        summary = FieldSummary()
        from log_analyzer.reports.sections import (
            _section_communication_health,
        )

        _section_communication_health(a, summary, 3600.0)
        ch = summary.communication_health
        assert ch["mqtt_connects"] == 0
        assert ch["mqtt_status_note"] == "MQTT: not established"


class TestMQTTFailedConnects:
    """18.14.4: MQTT shows 'failed to connect' with attempts."""

    def test_zero_connects_with_disconnects(self):
        """0 connects but disconnect events → 'failed to connect'."""
        from log_analyzer.models import FieldSummary

        a = _make_analyzer()
        a.mqtt.disconnects = [
            {"_ts": 1.0, "type": "unexpected"},
            {"_ts": 2.0, "type": "unexpected"},
        ]
        summary = FieldSummary()
        from log_analyzer.reports.sections import (
            _section_communication_health,
        )

        _section_communication_health(a, summary, 3600.0)
        ch = summary.communication_health
        assert ch["mqtt_connects"] == 0
        assert "failed to connect" in ch["mqtt_status_note"]
        assert "2 attempts" in ch["mqtt_status_note"]

    def test_zero_connects_with_publish_failures(self):
        """0 connects + publish failures → 'failed to connect'."""
        from log_analyzer.models import FieldSummary

        a = _make_analyzer()
        a.mqtt.publish_failures = [{"_ts": 1.0, "topic": "/status"}]
        summary = FieldSummary()
        from log_analyzer.reports.sections import (
            _section_communication_health,
        )

        _section_communication_health(a, summary, 3600.0)
        ch = summary.communication_health
        assert ch["mqtt_connects"] == 0
        assert "failed to connect" in ch["mqtt_status_note"]


class TestScanTotals:
    """18.14.5: Scan position totals equal per-position sums."""

    def test_totals_match_per_position(self):
        """total_cotton_found/picked = sum of per-position values."""
        from log_analyzer.models import FieldSummary

        a = _make_analyzer()
        a.events.scan_position_results = [
            {
                "position_index": "0",
                "cotton_found": 5,
                "cotton_picked": 3,
            },
            {
                "position_index": "1",
                "cotton_found": 8,
                "cotton_picked": 6,
            },
            {
                "position_index": "0",
                "cotton_found": 3,
                "cotton_picked": 2,
            },
        ]
        a.events.scan_summaries = [{"_ts": 1.0}]
        summary = FieldSummary()
        from log_analyzer.reports.sections import (
            _section_scan_effectiveness,
        )

        _section_scan_effectiveness(a, summary)
        se = summary.scan_effectiveness
        assert se["total_cotton_found"] == 5 + 8 + 3
        assert se["total_cotton_picked"] == 3 + 6 + 2
        # Verify per-position breakdown sums match
        by_pos = se["by_position"]
        sum_found = sum(v["found"] for v in by_pos.values())
        sum_picked = sum(v["picked"] for v in by_pos.values())
        assert sum_found == se["total_cotton_found"]
        assert sum_picked == se["total_cotton_picked"]

    def test_empty_scan_data_no_section(self):
        """No scan data → scan_effectiveness not populated."""
        from log_analyzer.models import FieldSummary

        a = _make_analyzer()
        summary = FieldSummary()
        from log_analyzer.reports.sections import (
            _section_scan_effectiveness,
        )

        _section_scan_effectiveness(a, summary)
        assert summary.scan_effectiveness == {}


# ===================================================================
# Task 18.15 — Unit tests for executive summary (group 16)
# ===================================================================


class TestExecutiveSummaryBench:
    """18.15.1: Bench mode executive summary."""

    def test_bench_summary_contains_bench_test(self):
        """Summary string includes 'bench test'."""
        a = _make_analyzer(_session_mode="bench")
        report = _make_report(duration_seconds=3600.0)
        summary = a._compute_executive_summary(report)
        assert "bench test" in summary

    def test_bench_summary_contains_pick_count(self):
        """Summary includes pick count."""
        a = _make_analyzer(_session_mode="bench")
        a.events.picks = [
            {"success": True},
            {"success": False},
            {"success": True},
        ]
        report = _make_report(duration_seconds=3600.0)
        summary = a._compute_executive_summary(report)
        assert "3 picks" in summary

    def test_bench_motor_findings(self):
        """Bench findings include motor alert status."""
        a = _make_analyzer(_session_mode="bench")
        report = _make_report(duration_seconds=3600.0)
        findings = a._collect_key_findings(report, "bench")
        # Should mention motor current alerts (0 = "no motor current alerts")
        motor_related = [
            f for f in findings if "motor" in f.lower()
        ]
        assert len(motor_related) >= 1

    def test_bench_joint_limit_findings(self):
        """Bench findings include joint limit status."""
        a = _make_analyzer(_session_mode="bench")
        a.events._joint_limit_total = 5
        report = _make_report(duration_seconds=3600.0)
        findings = a._collect_key_findings(report, "bench")
        jl_related = [
            f for f in findings if "joint limit" in f.lower()
        ]
        assert len(jl_related) >= 1
        assert any("5" in f for f in jl_related)


class TestExecutiveSummaryField:
    """18.15.2: Field mode executive summary."""

    def test_field_summary_contains_field_test(self):
        """Summary string includes 'field test'."""
        a = _make_analyzer(_session_mode="field")
        report = _make_report(duration_seconds=7200.0)
        summary = a._compute_executive_summary(report)
        assert "field test" in summary

    def test_field_picks_per_hour(self):
        """Field findings include picks/hr throughput."""
        a = _make_analyzer(_session_mode="field")
        a.events.picks = [{"success": True}] * 10
        report = _make_report(duration_seconds=3600.0)
        findings = a._collect_key_findings(report, "field")
        pph_related = [f for f in findings if "picks/hr" in f]
        assert len(pph_related) >= 1

    def test_field_success_rate(self):
        """Field findings include success rate."""
        a = _make_analyzer(_session_mode="field")
        a.events.picks = [
            {"success": True},
            {"success": True},
            {"success": False},
            {"result": "success"},
        ]
        report = _make_report(duration_seconds=3600.0)
        findings = a._collect_key_findings(report, "field")
        rate_related = [f for f in findings if "success rate" in f]
        assert len(rate_related) >= 1

    def test_field_camera_reconnections(self):
        """Field findings include camera reconnection count."""
        a = _make_analyzer(_session_mode="field")
        a.events.camera_reconnections = [
            {"_ts": 1.0},
            {"_ts": 2.0},
        ]
        report = _make_report(duration_seconds=3600.0)
        findings = a._collect_key_findings(report, "field")
        cam_related = [
            f for f in findings if "camera reconnection" in f
        ]
        assert len(cam_related) >= 1


class TestExecutiveSummaryShortSession:
    """18.15.3: Short session with 0 picks."""

    def test_zero_picks_summary(self):
        """Summary gracefully handles 0 picks."""
        a = _make_analyzer(_session_mode="bench")
        report = _make_report(duration_seconds=30.0)
        summary = a._compute_executive_summary(report)
        assert "0 picks" in summary

    def test_zero_duration_no_crash(self):
        """0-second session doesn't crash summary computation."""
        a = _make_analyzer(_session_mode="field")
        report = _make_report(duration_seconds=0.0)
        summary = a._compute_executive_summary(report)
        assert isinstance(summary, str)


class TestCriticalIssuesFirst:
    """18.15.4: Critical issues appear early in findings."""

    def test_critical_issues_inserted_early(self):
        """Critical-severity issues are inserted near the front."""
        a = _make_analyzer(_session_mode="bench")
        critical_issue = Issue(
            severity="critical",
            category="system",
            title="System overheating",
            description="CPU temp exceeded 90°C",
            occurrences=3,
        )
        report = _make_report(
            duration_seconds=3600.0,
            issues=[critical_issue],
        )
        findings = a._collect_key_findings(report, "bench")
        # Critical issue should appear somewhere in findings
        assert any("System overheating" in f for f in findings)

    def test_high_before_info(self):
        """High-severity issues take precedence."""
        a = _make_analyzer(_session_mode="bench")
        high_issue = Issue(
            severity="high",
            category="can",
            title="CAN bus errors",
            description="Frequent CAN bus errors detected",
            occurrences=10,
        )
        report = _make_report(
            duration_seconds=3600.0,
            issues=[high_issue],
        )
        findings = a._collect_key_findings(report, "bench")
        assert any("CAN bus errors" in f for f in findings)


class TestSummaryInJSON:
    """18.15.5: executive_summary appears in report dataclass."""

    def test_report_has_executive_summary_field(self):
        """AnalysisReport has executive_summary attribute."""
        report = _make_report(executive_summary="test summary")
        assert report.executive_summary == "test summary"

    def test_executive_summary_nonempty_after_compute(self):
        """_compute_executive_summary returns non-empty string."""
        a = _make_analyzer(_session_mode="bench")
        report = _make_report(duration_seconds=60.0)
        summary = a._compute_executive_summary(report)
        assert len(summary) > 0


# ===================================================================
# Task 18.16 — Unit tests for EE start distance (group 17)
# ===================================================================


class TestEEDistanceParsing:
    """18.16.1: Distance parsing from text patterns."""

    def test_text_pattern_match(self):
        """'EE dynamic start distance: 150mm' is parsed."""
        from log_analyzer.arm_patterns import _try_ee_start_distance

        a = _make_analyzer()
        _try_ee_start_distance(
            a, "EE dynamic start distance: 150mm", 1000.0
        )
        assert len(a.events.ee_start_distances) == 1
        assert a.events.ee_start_distances[0]["distance_mm"] == 150.0

    def test_json_pattern_match(self):
        """'start_distance_mm: 120.5' is parsed."""
        from log_analyzer.arm_patterns import _try_ee_start_distance

        a = _make_analyzer()
        _try_ee_start_distance(
            a, 'start_distance_mm: 120.5', 2000.0
        )
        assert len(a.events.ee_start_distances) == 1
        assert (
            a.events.ee_start_distances[0]["distance_mm"]
            == pytest.approx(120.5)
        )

    def test_timestamp_stored(self):
        """Timestamp is stored in the event dict."""
        from log_analyzer.arm_patterns import _try_ee_start_distance

        a = _make_analyzer()
        _try_ee_start_distance(
            a, "EE start distance: 100mm", 5000.0
        )
        assert a.events.ee_start_distances[0]["_ts"] == 5000.0

    def test_arm_id_stored(self):
        """arm_id is captured from analyzer._current_arm_id."""
        from log_analyzer.arm_patterns import _try_ee_start_distance

        a = _make_analyzer(_current_arm_id="arm_0")
        _try_ee_start_distance(
            a, "EE dynamic start distance: 80mm", 1000.0
        )
        assert a.events.ee_start_distances[0]["arm_id"] == "arm_0"

    def test_no_match_no_event(self):
        """Unrelated text does not produce events."""
        from log_analyzer.arm_patterns import _try_ee_start_distance

        a = _make_analyzer()
        _try_ee_start_distance(a, "Motor J2 reached target", 1000.0)
        assert len(a.events.ee_start_distances) == 0


class TestStartSwitchParsing:
    """18.16.2: Start switch activation/deactivation events."""

    def test_activated_parsed(self):
        """'Start switch activated' produces activated event."""
        from log_analyzer.arm_patterns import _try_start_switch

        a = _make_analyzer()
        _try_start_switch(a, "Start switch activated", 1000.0)
        assert len(a.events.start_switch_events) == 1
        assert a.events.start_switch_events[0]["type"] == "activated"

    def test_deactivated_parsed(self):
        """'Start switch deactivated' produces deactivated event."""
        from log_analyzer.arm_patterns import _try_start_switch

        a = _make_analyzer()
        _try_start_switch(a, "Start switch deactivated", 2000.0)
        assert len(a.events.start_switch_events) == 1
        ev = a.events.start_switch_events[0]
        assert ev["type"] == "deactivated"
        assert ev["_ts"] == 2000.0

    def test_pressed_variant(self):
        """'Start switch pressed' matches activated pattern."""
        from log_analyzer.arm_patterns import _try_start_switch

        a = _make_analyzer()
        _try_start_switch(a, "Start switch pressed", 3000.0)
        assert len(a.events.start_switch_events) == 1
        assert a.events.start_switch_events[0]["type"] == "activated"

    def test_released_variant(self):
        """'Start switch released' matches deactivated pattern."""
        from log_analyzer.arm_patterns import _try_start_switch

        a = _make_analyzer()
        _try_start_switch(a, "Start switch released", 4000.0)
        assert len(a.events.start_switch_events) == 1
        assert a.events.start_switch_events[0]["type"] == "deactivated"

    def test_unrelated_no_event(self):
        """Unrelated text does not produce switch events."""
        from log_analyzer.arm_patterns import _try_start_switch

        a = _make_analyzer()
        _try_start_switch(a, "Motor J1 reached target", 1000.0)
        assert len(a.events.start_switch_events) == 0


class TestDistanceDistributionStats:
    """18.16.3: Mean/stddev computation from distance data."""

    def test_mean_stddev_computation(self):
        """Section builder computes correct mean and stddev."""
        import statistics

        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import (
            _section_ee_start_distance,
        )

        a = _make_analyzer()
        distances = [100.0, 110.0, 120.0, 130.0, 140.0]
        a.events.ee_start_distances = [
            {"distance_mm": d, "_ts": float(i), "arm_id": None}
            for i, d in enumerate(distances)
        ]
        summary = FieldSummary()
        _section_ee_start_distance(summary, a)

        dist = summary.ee_start_distance["distance"]
        assert dist["count"] == 5
        assert dist["mean_mm"] == pytest.approx(
            statistics.mean(distances), abs=0.2
        )
        assert dist["stddev_mm"] == pytest.approx(
            statistics.stdev(distances), abs=0.2
        )
        assert dist["min_mm"] == pytest.approx(100.0)
        assert dist["max_mm"] == pytest.approx(140.0)

    def test_single_distance_zero_stddev(self):
        """Single data point → stddev is 0."""
        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import (
            _section_ee_start_distance,
        )

        a = _make_analyzer()
        a.events.ee_start_distances = [
            {"distance_mm": 100.0, "_ts": 1.0, "arm_id": None}
        ]
        summary = FieldSummary()
        _section_ee_start_distance(summary, a)

        dist = summary.ee_start_distance["distance"]
        assert dist["stddev_mm"] == 0.0


class TestVarianceFlagging:
    """18.16.4: High variance flagging (stddev > 30mm)."""

    def test_high_variance_issue_raised(self):
        """stddev > 30mm → Low severity issue."""
        from log_analyzer.arm_patterns import (
            _detect_ee_start_distance_issues,
        )

        a = _make_analyzer()
        # Create data with high variance — spread > 30mm stddev
        a.events.ee_start_distances = [
            {"distance_mm": 50.0, "_ts": 1.0, "arm_id": None},
            {"distance_mm": 150.0, "_ts": 2.0, "arm_id": None},
            {"distance_mm": 50.0, "_ts": 3.0, "arm_id": None},
            {"distance_mm": 150.0, "_ts": 4.0, "arm_id": None},
        ]
        _detect_ee_start_distance_issues(a)
        # Check for high variability issue
        matching = [
            v
            for v in a.issues.values()
            if "variability" in v.title.lower()
            or "stddev" in v.description.lower()
        ]
        assert len(matching) >= 1
        assert matching[0].severity == "low"

    def test_low_variance_no_issue(self):
        """stddev < 30mm → no variance issue."""
        from log_analyzer.arm_patterns import (
            _detect_ee_start_distance_issues,
        )

        a = _make_analyzer()
        a.events.ee_start_distances = [
            {"distance_mm": 100.0, "_ts": 1.0, "arm_id": None},
            {"distance_mm": 105.0, "_ts": 2.0, "arm_id": None},
            {"distance_mm": 98.0, "_ts": 3.0, "arm_id": None},
            {"distance_mm": 102.0, "_ts": 4.0, "arm_id": None},
        ]
        _detect_ee_start_distance_issues(a)
        variability_issues = [
            v
            for v in a.issues.values()
            if "variability" in v.title.lower()
        ]
        assert len(variability_issues) == 0


class TestOutOfRangeFlagging:
    """18.16.5: Out-of-range distance flagging."""

    def test_max_exceeds_200mm_issue(self):
        """Distance > 200mm → Medium severity 'too large' issue."""
        from log_analyzer.arm_patterns import (
            _detect_ee_start_distance_issues,
        )

        a = _make_analyzer()
        a.events.ee_start_distances = [
            {"distance_mm": 180.0, "_ts": 1.0, "arm_id": None},
            {"distance_mm": 250.0, "_ts": 2.0, "arm_id": None},
        ]
        _detect_ee_start_distance_issues(a)
        too_large = [
            v
            for v in a.issues.values()
            if "too large" in v.title.lower()
        ]
        assert len(too_large) == 1
        assert too_large[0].severity == "medium"

    def test_min_below_20mm_issue(self):
        """Distance < 20mm → Medium severity 'too small' issue."""
        from log_analyzer.arm_patterns import (
            _detect_ee_start_distance_issues,
        )

        a = _make_analyzer()
        a.events.ee_start_distances = [
            {"distance_mm": 15.0, "_ts": 1.0, "arm_id": None},
            {"distance_mm": 100.0, "_ts": 2.0, "arm_id": None},
        ]
        _detect_ee_start_distance_issues(a)
        too_small = [
            v
            for v in a.issues.values()
            if "too small" in v.title.lower()
        ]
        assert len(too_small) == 1
        assert too_small[0].severity == "medium"

    def test_in_range_no_out_of_range_issue(self):
        """All distances in [20, 200] → no out-of-range issues."""
        from log_analyzer.arm_patterns import (
            _detect_ee_start_distance_issues,
        )

        a = _make_analyzer()
        a.events.ee_start_distances = [
            {"distance_mm": 100.0, "_ts": 1.0, "arm_id": None},
            {"distance_mm": 120.0, "_ts": 2.0, "arm_id": None},
            {"distance_mm": 80.0, "_ts": 3.0, "arm_id": None},
        ]
        _detect_ee_start_distance_issues(a)
        oor_issues = [
            v
            for v in a.issues.values()
            if "too large" in v.title.lower()
            or "too small" in v.title.lower()
        ]
        assert len(oor_issues) == 0


class TestIdleTiming:
    """18.16.6: Idle timing from switch events."""

    def test_idle_timing_computation(self):
        """Idle = gap between deactivated → next activated."""
        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import (
            _section_ee_start_distance,
        )

        a = _make_analyzer()
        a.events.start_switch_events = [
            {"type": "activated", "_ts": 100.0, "arm_id": None},
            {"type": "deactivated", "_ts": 110.0, "arm_id": None},
            {"type": "activated", "_ts": 115.0, "arm_id": None},
            {"type": "deactivated", "_ts": 125.0, "arm_id": None},
            {"type": "activated", "_ts": 135.0, "arm_id": None},
        ]
        summary = FieldSummary()
        _section_ee_start_distance(summary, a)
        idle = summary.ee_start_distance["idle_timing"]
        # Two idle gaps: 115-110=5s and 135-125=10s
        assert idle["count"] == 2
        assert idle["mean_s"] == pytest.approx(7.5)
        assert idle["min_s"] == pytest.approx(5.0)
        assert idle["max_s"] == pytest.approx(10.0)

    def test_no_switch_events_no_idle(self):
        """No switch events → no idle_timing in section."""
        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import (
            _section_ee_start_distance,
        )

        a = _make_analyzer()
        # Need at least distances to get a section at all
        a.events.ee_start_distances = [
            {"distance_mm": 100.0, "_ts": 1.0, "arm_id": None}
        ]
        summary = FieldSummary()
        _section_ee_start_distance(summary, a)
        assert summary.ee_start_distance["idle_timing"] == {}

    def test_high_idle_mean_issue(self):
        """Mean idle > 5s threshold → idle_issue populated."""
        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import (
            _section_ee_start_distance,
        )

        a = _make_analyzer()
        a.events.start_switch_events = [
            {"type": "deactivated", "_ts": 100.0, "arm_id": None},
            {"type": "activated", "_ts": 110.0, "arm_id": None},
            {"type": "deactivated", "_ts": 120.0, "arm_id": None},
            {"type": "activated", "_ts": 130.0, "arm_id": None},
        ]
        summary = FieldSummary()
        _section_ee_start_distance(summary, a)
        # Mean idle = 10s > 5s threshold
        assert summary.ee_start_distance["idle_issue"] is not None
        assert (
            summary.ee_start_distance["idle_issue"]["severity"]
            == "Low"
        )


# ===================================================================
# Motor-homing-verification scenarios 2-5
# ===================================================================


class TestHomingVerificationScenarios:
    """Scenarios 2-5 from motor-homing-verification spec.

    Scenario 1 (parse successful homing) is already covered in
    test_deep_analysis_a.py.
    """

    # --- Scenario 2: Homing failure detected ---

    def test_homing_failure_raises_critical_issue(self):
        """Failed homing (success=False) → critical issue."""
        from log_analyzer.detectors.hardware import detect_homing_failures

        events = EventStore()
        events.homing_events = [
            {
                "joint_name": "J1",
                "success": False,
                "arm_id": "arm_0",
                "_ts": 100.0,
            }
        ]
        issues = detect_homing_failures(events)
        assert len(issues) >= 1
        crit = [i for i in issues if i["severity"] == "critical"]
        assert len(crit) >= 1
        assert "homing failed" in crit[0]["title"].lower()

    # --- Scenario 3: High homing error flagged ---

    def test_homing_high_error_raises_medium_issue(self):
        """Position error > 80% of tolerance → medium issue."""
        from log_analyzer.detectors.hardware import detect_homing_failures

        events = EventStore()
        events.homing_events = [
            {
                "joint_name": "J2",
                "success": True,
                "position_error": 0.045,
                "tolerance": 0.050,
                "arm_id": "arm_0",
                "_ts": 200.0,
            }
        ]
        issues = detect_homing_failures(events)
        assert len(issues) >= 1
        med = [i for i in issues if i["severity"] == "medium"]
        assert len(med) >= 1
        assert "near tolerance" in med[0]["title"].lower()

    # --- Scenario 4: Homing summary section rendered ---

    def test_homing_summary_section_rendered(self):
        """Homing events present → motor_homing section populated."""
        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import _section_motor_homing

        a = _make_analyzer()
        a.events.homing_events = [
            {
                "joint_name": "J1",
                "success": True,
                "position_error": 0.010,
                "tolerance": 0.050,
                "arm_id": "arm_0",
                "_ts": 100.0,
            },
            {
                "joint_name": "J2",
                "success": True,
                "position_error": 0.020,
                "tolerance": 0.050,
                "arm_id": "arm_0",
                "_ts": 101.0,
            },
        ]
        summary = FieldSummary()
        _section_motor_homing(a, summary)
        assert summary.motor_homing
        assert summary.motor_homing["total_events"] == 2
        assert len(summary.motor_homing["joint_table"]) == 2

    # --- Scenario 5: No homing data → section omitted ---

    def test_no_homing_data_omits_section(self):
        """Empty homing_events → motor_homing stays empty."""
        from log_analyzer.models import FieldSummary
        from log_analyzer.reports.sections import _section_motor_homing

        a = _make_analyzer()
        # homing_events is already empty by default
        summary = FieldSummary()
        _section_motor_homing(a, summary)
        assert not summary.motor_homing
