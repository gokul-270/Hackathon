"""
scripts/log_analyzer/tests/test_deep_analysis_b.py

Tests for log-analyzer-deep-analysis change — batch B:
  18.5 — New report sections (groups 6-7)
  18.6 — Structural improvements / registry (group 8)
  18.7 — Motor telemetry detector (group 9)
  18.8 — Camera health detector (group 10)
"""

import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from log_analyzer.analyzer import ROS2LogAnalyzer
from log_analyzer.models import EventStore, FieldSummary, MQTTMetrics


# ---------------------------------------------------------------------------
# Helpers — build minimal analyzer / summary objects
# ---------------------------------------------------------------------------


def _make_analyzer(events=None, **overrides):
    """Create a minimal ROS2LogAnalyzer without __init__."""
    a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
    a.events = events or EventStore()
    a.issues = {}
    a.start_time = overrides.get("start_time", 0.0)
    a.end_time = overrides.get("end_time", 0.0)
    a.verbose = False
    a.entries = []
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
    a.mqtt = MQTTMetrics()
    a.field_summary = None
    a._json_skip_count = 0
    a._current_arm_id = None
    a._source_category_ranges = {}
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


# ===================================================================
# Task 18.5 — New report sections (groups 6-7)
# ===================================================================


class TestDmesgSummarySection:
    """task 6.1 — _section_dmesg_summary with/without dmesg events."""

    def test_empty_dmesg_no_section(self):
        """No dmesg events → dmesg_summary stays empty."""
        from log_analyzer.reports.sections import (
            _section_dmesg_summary,
        )

        summary = FieldSummary()
        analyzer = _make_analyzer()
        _section_dmesg_summary(summary, analyzer)
        assert summary.dmesg_summary == {}

    def test_usb_disconnect_counted(self):
        """USB disconnect events are counted correctly."""
        from log_analyzer.reports.sections import (
            _section_dmesg_summary,
        )

        es = EventStore()
        es.dmesg_usb_disconnects = [
            {"_ts": 100.0, "message": "USB disconnect"},
            {"_ts": 200.0, "message": "USB disconnect 2"},
        ]
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_dmesg_summary(summary, analyzer)

        assert summary.dmesg_summary["has_data"] is True
        assert summary.dmesg_summary["total_events"] == 2
        usb = summary.dmesg_summary["by_category"]["usb_disconnect"]
        assert usb["count"] == 2
        assert usb["first_ts"] == 100.0
        assert usb["last_ts"] == 200.0

    def test_multiple_categories(self):
        """Multiple dmesg categories aggregated independently."""
        from log_analyzer.reports.sections import (
            _section_dmesg_summary,
        )

        es = EventStore()
        es.dmesg_usb_disconnects = [
            {"_ts": 10.0, "message": "usb"},
        ]
        es.dmesg_thermal = [
            {"_ts": 20.0, "message": "thermal"},
            {"_ts": 30.0, "message": "thermal 2"},
        ]
        es.dmesg_oom = [
            {"_ts": 50.0, "message": "oom"},
        ]
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_dmesg_summary(summary, analyzer)

        assert summary.dmesg_summary["total_events"] == 4
        assert len(summary.dmesg_summary["by_category"]) == 3
        assert (
            summary.dmesg_summary["by_category"]["thermal"]["count"]
            == 2
        )

    def test_can_and_spi_categories(self):
        """CAN and SPI dmesg categories are tracked."""
        from log_analyzer.reports.sections import (
            _section_dmesg_summary,
        )

        es = EventStore()
        es.dmesg_can_errors = [
            {"_ts": 5.0, "message": "can err"},
        ]
        es.dmesg_spi_errors = [
            {"_ts": 6.0, "message": "spi err"},
        ]
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_dmesg_summary(summary, analyzer)

        assert summary.dmesg_summary["total_events"] == 2
        assert "can_error" in summary.dmesg_summary["by_category"]
        assert "spi_error" in summary.dmesg_summary["by_category"]


class TestPickSuccessTrendSection:
    """task 6.2 — pick success rate trend."""

    def test_insufficient_picks_no_section(self):
        """Fewer than 10 picks → no trend section."""
        from log_analyzer.reports.sections import (
            _section_pick_success_trend,
        )

        es = EventStore()
        es.picks = [{"success": True}] * 5
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_pick_success_trend(summary, analyzer)
        assert summary.pick_success_trend == {}

    def test_sufficient_picks_trend_computed(self):
        """10+ picks → trend section populated."""
        from log_analyzer.reports.sections import (
            _section_pick_success_trend,
        )

        es = EventStore()
        es.picks = [{"success": True}] * 12
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_pick_success_trend(summary, analyzer)

        assert summary.pick_success_trend["has_data"] is True
        assert summary.pick_success_trend["total_picks"] == 12
        assert len(summary.pick_success_trend["windows"]) > 0

    def test_degradation_detected(self):
        """Declining success rate triggers 'degrading' trend."""
        from log_analyzer.reports.sections import (
            _section_pick_success_trend,
        )

        es = EventStore()
        # First half: all success. Last half: all fail.
        es.picks = (
            [{"success": True}] * 10
            + [{"success": False}] * 10
        )
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_pick_success_trend(summary, analyzer)

        trend = summary.pick_success_trend
        assert trend["trend_direction"] == "degrading"
        assert trend["issue"] is not None
        assert trend["delta_pp"] > 20

    def test_stable_trend(self):
        """Constant success rate → stable trend, no issue."""
        from log_analyzer.reports.sections import (
            _section_pick_success_trend,
        )

        es = EventStore()
        es.picks = [{"success": True}] * 20
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_pick_success_trend(summary, analyzer)

        trend = summary.pick_success_trend
        assert trend["trend_direction"] == "stable"
        assert trend["issue"] is None


class TestThroughputTrendSection:
    """task 6.3 — throughput trend."""

    def test_short_session_no_section(self):
        """Session <10 minutes → no throughput section."""
        from log_analyzer.reports.sections import (
            _section_throughput_trend,
        )

        es = EventStore()
        es.picks = [{"_ts": 100.0, "success": True}] * 5
        summary = FieldSummary()
        analyzer = _make_analyzer(
            events=es, start_time=0.0, end_time=300.0
        )
        _section_throughput_trend(summary, analyzer, 300.0)
        assert summary.throughput_trend == {}

    def test_sufficient_duration_computed(self):
        """Session 30+ min → throughput section populated."""
        from log_analyzer.reports.sections import (
            _section_throughput_trend,
        )

        es = EventStore()
        # Spread picks over 30 minutes
        for i in range(20):
            es.picks.append({"_ts": 100.0 + i * 100, "success": True})
        summary = FieldSummary()
        analyzer = _make_analyzer(
            events=es, start_time=100.0, end_time=2100.0
        )
        _section_throughput_trend(summary, analyzer, 2000.0)

        tp = summary.throughput_trend
        assert tp["has_data"] is True
        assert tp["overall_picks_per_hour"] > 0
        assert len(tp["windows"]) > 0

    def test_decline_detected(self):
        """Declining throughput detected when last window < 50% peak."""
        from log_analyzer.reports.sections import (
            _section_throughput_trend,
        )

        es = EventStore()
        start = 0.0
        # First 5 min: 20 picks; last 5 min: 1 pick
        for i in range(20):
            es.picks.append({"_ts": start + i * 10, "success": True})
        es.picks.append({"_ts": start + 800, "success": True})
        summary = FieldSummary()
        analyzer = _make_analyzer(
            events=es, start_time=start, end_time=start + 900
        )
        _section_throughput_trend(summary, analyzer, 900.0)

        tp = summary.throughput_trend
        assert tp["has_data"] is True
        # Peak window should be higher than last window
        assert tp["peak_picks_per_hour"] > tp["last_window_picks_per_hour"]


class TestStaleDetectionWarningsSection:
    """task 6.4 — stale detection warnings."""

    def test_no_warnings_no_section(self):
        """No stale warnings → section not populated."""
        from log_analyzer.reports.sections import (
            _section_stale_detection_warnings,
        )

        summary = FieldSummary()
        analyzer = _make_analyzer()
        _section_stale_detection_warnings(summary, analyzer)
        assert summary.stale_detection_section == {}

    def test_warnings_captured(self):
        """Stale detection warnings are captured."""
        from log_analyzer.reports.sections import (
            _section_stale_detection_warnings,
        )

        es = EventStore()
        es.stale_detection_warnings = [
            {
                "_ts": 100.0,
                "reported_age_ms": 2500,
                "source_node": "detector",
            },
            {
                "_ts": 200.0,
                "reported_age_ms": 150,
                "source_node": "detector",
            },
        ]
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_stale_detection_warnings(summary, analyzer)

        sec = summary.stale_detection_section
        assert sec["has_data"] is True
        assert sec["count"] == 2
        assert sec["first_ts"] == 100.0
        assert sec["last_ts"] == 200.0
        assert sec["age_distribution"][">2000ms"] == 1
        assert sec["age_distribution"]["100-500ms"] == 1

    def test_source_nodes_collected(self):
        """Source nodes are collected and deduped."""
        from log_analyzer.reports.sections import (
            _section_stale_detection_warnings,
        )

        es = EventStore()
        es.stale_detection_warnings = [
            {
                "_ts": 1.0,
                "reported_age_ms": 50,
                "source_node": "node_a",
            },
            {
                "_ts": 2.0,
                "reported_age_ms": 60,
                "source_node": "node_b",
            },
            {
                "_ts": 3.0,
                "reported_age_ms": 70,
                "source_node": "node_a",
            },
        ]
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_stale_detection_warnings(summary, analyzer)

        sec = summary.stale_detection_section
        assert sorted(sec["source_nodes"]) == ["node_a", "node_b"]


class TestScanEffectivenessSection:
    """task 7.1-7.2 — scan effectiveness, dead zones, yield ranking."""

    def test_dead_zone_identified(self):
        """Position with 0 picks over 3+ scans flagged as dead zone."""
        from log_analyzer.reports.sections import (
            _section_scan_effectiveness,
        )

        es = EventStore()
        # Position "0" has picks; position "1" has 0 picks over 3
        for _ in range(3):
            es.scan_position_results.append({
                "position_index": "0",
                "cotton_found": 5,
                "cotton_picked": 3,
            })
        for _ in range(3):
            es.scan_position_results.append({
                "position_index": "1",
                "cotton_found": 4,
                "cotton_picked": 0,
            })
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_scan_effectiveness(analyzer, summary)

        scan = summary.scan_effectiveness
        assert "1" in scan["dead_zones"]
        assert "0" not in scan["dead_zones"]

    def test_no_dead_zone_when_all_productive(self):
        """No dead zones when all positions have picks."""
        from log_analyzer.reports.sections import (
            _section_scan_effectiveness,
        )

        es = EventStore()
        for _ in range(4):
            es.scan_position_results.append({
                "position_index": "0",
                "cotton_found": 5,
                "cotton_picked": 2,
            })
        for _ in range(4):
            es.scan_position_results.append({
                "position_index": "1",
                "cotton_found": 3,
                "cotton_picked": 1,
            })
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_scan_effectiveness(analyzer, summary)

        scan = summary.scan_effectiveness
        assert scan["dead_zones"] == []

    def test_yield_ranking_computed(self):
        """With 5+ scan events, yield ranking is computed."""
        from log_analyzer.reports.sections import (
            _section_scan_effectiveness,
        )

        es = EventStore()
        # 5 events across 2 positions
        for _ in range(3):
            es.scan_position_results.append({
                "position_index": "A",
                "cotton_found": 10,
                "cotton_picked": 8,
            })
        for _ in range(2):
            es.scan_position_results.append({
                "position_index": "B",
                "cotton_found": 10,
                "cotton_picked": 2,
            })
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_scan_effectiveness(analyzer, summary)

        scan = summary.scan_effectiveness
        assert len(scan["yield_ranking"]) == 2
        # A should be ranked higher (80% vs 20%)
        assert scan["yield_ranking"][0]["position"] == "A"
        assert scan["yield_ranking"][0]["pick_yield_pct"] == 80.0
        assert scan["yield_ranking"][1]["position"] == "B"
        assert scan["yield_ranking"][1]["pick_yield_pct"] == 20.0

    def test_yield_ranking_skipped_few_events(self):
        """With <5 scan events, yield ranking is empty."""
        from log_analyzer.reports.sections import (
            _section_scan_effectiveness,
        )

        es = EventStore()
        for _ in range(3):
            es.scan_position_results.append({
                "position_index": "X",
                "cotton_found": 5,
                "cotton_picked": 3,
            })
        summary = FieldSummary()
        analyzer = _make_analyzer(events=es)
        _section_scan_effectiveness(analyzer, summary)

        scan = summary.scan_effectiveness
        assert scan["yield_ranking"] == []


# ===================================================================
# Task 18.6 — Structural improvements / registry (group 8)
# ===================================================================


class TestDetectorRegistry:
    """task 8.1-8.3 — detector registry register/get/filter."""

    def test_register_and_get_all(self):
        """register() adds a detector, get_all() returns it."""
        from log_analyzer.detectors import registry

        initial_count = len(registry.get_all())
        # Register a test detector
        registry.register(
            "_test_detector_a",
            lambda e: None,
            category="test",
            description="Test detector A",
            order=900,
        )
        try:
            all_dets = registry.get_all()
            assert len(all_dets) == initial_count + 1
            names = [d["name"] for d in all_dets]
            assert "_test_detector_a" in names
        finally:
            # Clean up
            registry._REGISTRY.pop("_test_detector_a", None)

    def test_get_by_category(self):
        """get_by_category() filters by category."""
        from log_analyzer.detectors import registry

        registry.register(
            "_test_cat_motor",
            lambda e: None,
            category="test_motor",
            description="Motor test",
        )
        registry.register(
            "_test_cat_camera",
            lambda e: None,
            category="test_camera",
            description="Camera test",
        )
        try:
            motor_dets = registry.get_by_category("test_motor")
            assert len(motor_dets) == 1
            assert motor_dets[0]["name"] == "_test_cat_motor"

            camera_dets = registry.get_by_category("test_camera")
            assert len(camera_dets) == 1
            assert camera_dets[0]["name"] == "_test_cat_camera"
        finally:
            registry._REGISTRY.pop("_test_cat_motor", None)
            registry._REGISTRY.pop("_test_cat_camera", None)

    def test_ordering_by_order_then_name(self):
        """Detectors returned sorted by order, then name."""
        from log_analyzer.detectors import registry

        registry.register(
            "_test_ord_z",
            lambda e: None,
            category="test_ord",
            description="Z",
            order=1,
        )
        registry.register(
            "_test_ord_a",
            lambda e: None,
            category="test_ord",
            description="A",
            order=1,
        )
        registry.register(
            "_test_ord_first",
            lambda e: None,
            category="test_ord",
            description="First",
            order=0,
        )
        try:
            dets = registry.get_by_category("test_ord")
            names = [d["name"] for d in dets]
            assert names == [
                "_test_ord_first",
                "_test_ord_a",
                "_test_ord_z",
            ]
        finally:
            registry._REGISTRY.pop("_test_ord_z", None)
            registry._REGISTRY.pop("_test_ord_a", None)
            registry._REGISTRY.pop("_test_ord_first", None)

    def test_get_names(self):
        """get_names() returns sorted list of detector names."""
        from log_analyzer.detectors import registry

        names = registry.get_names()
        assert isinstance(names, list)
        assert names == sorted(names)

    def test_is_registered(self):
        """is_registered() correctly checks for existence."""
        from log_analyzer.detectors import registry

        registry.register(
            "_test_exists_check",
            lambda e: None,
            category="test",
            description="Exists",
        )
        try:
            assert registry.is_registered("_test_exists_check")
            assert not registry.is_registered("_no_such_detector")
        finally:
            registry._REGISTRY.pop("_test_exists_check", None)


class TestFilterParsing:
    """task 8.5 — --filter KEY:VALUE parsing."""

    def test_valid_detector_filter(self):
        """Valid 'detector:name' parses correctly."""
        from log_analyzer.cli import _parse_filters

        result = _parse_filters(["detector:detect_vehicle_issues"])
        assert "detector" in result
        assert "detect_vehicle_issues" in result["detector"]

    def test_valid_severity_filter(self):
        """Valid 'severity:critical' parses correctly."""
        from log_analyzer.cli import _parse_filters

        result = _parse_filters(["severity:critical"])
        assert "severity" in result
        assert "critical" in result["severity"]

    def test_valid_joint_filter(self):
        """Valid 'joint:3' parses correctly."""
        from log_analyzer.cli import _parse_filters

        result = _parse_filters(["joint:3"])
        assert "joint" in result
        assert "3" in result["joint"]

    def test_multiple_filters(self):
        """Multiple filters accumulate correctly."""
        from log_analyzer.cli import _parse_filters

        result = _parse_filters([
            "detector:d1",
            "detector:d2",
            "severity:high",
        ])
        assert result["detector"] == {"d1", "d2"}
        assert result["severity"] == {"high"}

    def test_invalid_key_exits(self):
        """Invalid filter key causes sys.exit(1)."""
        from log_analyzer.cli import _parse_filters

        with pytest.raises(SystemExit) as exc_info:
            _parse_filters(["invalid_key:value"])
        assert exc_info.value.code == 1

    def test_missing_colon_exits(self):
        """Missing colon in filter causes sys.exit(1)."""
        from log_analyzer.cli import _parse_filters

        with pytest.raises(SystemExit) as exc_info:
            _parse_filters(["no_colon_here"])
        assert exc_info.value.code == 1


class TestListDetectors:
    """task 8.4 — --list-detectors flag."""

    def test_list_detectors_exits_zero(self):
        """--list-detectors causes sys.exit(0)."""
        from log_analyzer.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--list-detectors"])
        assert exc_info.value.code == 0


class TestWatchModeJsonParsing:
    """task 8.8 — Watch mode JSON parsing."""

    def test_watch_function_exists(self):
        """watch_logs function exists and is callable."""
        from log_analyzer.cli import watch_logs

        assert callable(watch_logs)


# ===================================================================
# Task 18.7 — Motor telemetry (group 9)
# ===================================================================


class TestMotorTelemetryUnified:
    """task 9.8 — analyze_motor_telemetry entry point."""

    def test_empty_events_returns_empty(self):
        """No motor_health_arm events → empty results."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        result = analyze_motor_telemetry(es)
        assert result["temperature"] == {}
        assert result["voltage"] == {}
        assert result["issues"] == []

    def test_temperature_trend_rising(self):
        """Rising temperature is detected."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        # Create 20 readings with rising temp from 40 to 70
        for i in range(20):
            temp = 40.0 + i * 1.5
            es.motor_health_arm.append({
                "_ts": 100.0 + i * 60,
                "motors": [
                    {"joint": "J1", "temp_c": temp},
                ],
            })
        result = analyze_motor_telemetry(es)

        j1 = result["temperature"]["J1"]
        assert j1["trend_direction"] == "rising"
        assert j1["start_temp_c"] == 40.0
        assert j1["peak_temp_c"] == 68.5

    def test_temperature_high_issue(self):
        """Temperature above 65C triggers high severity issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(10):
            es.motor_health_arm.append({
                "_ts": 100.0 + i * 60,
                "motors": [
                    {"joint": "J2", "temp_c": 60.0 + i * 1.5},
                ],
            })
        result = analyze_motor_telemetry(es)
        # Peak is 60 + 9*1.5 = 73.5 > 65
        issues = [
            i for i in result["issues"]
            if i["category"] == "motor" and "J2" in i["title"]
        ]
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_temperature_medium_issue(self):
        """Temperature between 55C and 65C triggers medium issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(10):
            es.motor_health_arm.append({
                "_ts": 100.0 + i * 60,
                "motors": [
                    {"joint": "J3", "temp_c": 50.0 + i * 1.0},
                ],
            })
        result = analyze_motor_telemetry(es)
        # Peak is 50 + 9 = 59, which is > 55 but < 65
        issues = [
            i for i in result["issues"]
            if i["category"] == "motor" and "J3" in i["title"]
        ]
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"


class TestMotorVoltageTracking:
    """task 9.3 — Battery voltage tracking."""

    def test_voltage_discharge_rate(self):
        """Declining voltage computes correct discharge rate."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        # 10 samples over 1 hour: 52V → 50V (2V drop)
        for i in range(10):
            es.motor_health_arm.append({
                "_ts": 1000.0 + i * 360,  # 3600s total
                "vbus_v": 52.0 - i * 0.2,
                "motors": [],
            })
        result = analyze_motor_telemetry(es)
        voltage = result["voltage"]
        assert voltage["start_v"] == 52.0
        # end_v = 52.0 - 9*0.2 = 50.2
        assert voltage["end_v"] == 50.2
        # discharge ~2V/hour
        assert voltage["discharge_rate_v_per_hour"] is not None
        assert abs(
            voltage["discharge_rate_v_per_hour"]
            - round(
                (52.0 - 50.2) / (9 * 360 / 3600.0), 3
            )
        ) < 0.01

    def test_low_voltage_high_issue(self):
        """Voltage below 45V triggers high severity issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(5):
            es.motor_health_arm.append({
                "_ts": 100.0 + i * 60,
                "vbus_v": 50.0 - i * 2.0,
                "motors": [],
            })
        # min is 50 - 4*2 = 42V < 45V
        result = analyze_motor_telemetry(es)
        voltage_issues = [
            i for i in result["issues"]
            if i["category"] == "power"
        ]
        assert len(voltage_issues) == 1
        assert voltage_issues[0]["severity"] == "high"


class TestPositionPrecision:
    """task 9.4 — Position precision by transmission ratio."""

    def test_grouping_by_ratio(self):
        """Motors grouped by transmission ratio."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(10):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {
                        "joint": "J1",
                        "pos_error": 0.01 * (i + 1),
                        "transmission_ratio": 1.0,
                    },
                    {
                        "joint": "J4",
                        "pos_error": 0.001 * (i + 1),
                        "transmission_ratio": 12.7,
                    },
                ],
            })
        result = analyze_motor_telemetry(es)
        precision = result["position_precision"]
        assert "1:1" in precision
        assert "12.7:1" in precision
        assert precision["1:1"]["sample_count"] == 10
        assert precision["12.7:1"]["sample_count"] == 10


class TestReachTimeDegradation:
    """task 9.5 — Reach time degradation."""

    def test_degradation_detected(self):
        """Increasing reach times trigger degradation flag."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        # 20 samples: first half ~100ms, last half ~200ms (+100%)
        for i in range(20):
            rt = 100.0 if i < 10 else 200.0
            es.motor_health_arm.append({
                "_ts": 100.0 + i * 10,
                "motors": [
                    {"joint": "J5", "reach_time_ms": rt},
                ],
            })
        result = analyze_motor_telemetry(es)
        j5 = result["reach_time"]["J5"]
        assert j5["degraded"] is True

        # Check issue raised
        degrade_issues = [
            i for i in result["issues"]
            if "degradation" in i["title"].lower()
        ]
        assert len(degrade_issues) == 1

    def test_stable_reach_time(self):
        """Stable reach times → no degradation."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(20):
            es.motor_health_arm.append({
                "_ts": 100.0 + i * 10,
                "motors": [
                    {"joint": "J1", "reach_time_ms": 100.0},
                ],
            })
        result = analyze_motor_telemetry(es)
        j1 = result["reach_time"]["J1"]
        assert j1["degraded"] is False


class TestSupersedeRate:
    """task 9.6 — Command supersede rate."""

    def test_supersede_rate_computed(self):
        """Supersede rate computed correctly."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        # 10 commands, 3 superseded (30%)
        for i in range(10):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {
                        "joint": "J2",
                        "superseded": i < 3,
                    },
                ],
            })
        result = analyze_motor_telemetry(es)
        j2 = result["supersede_rate"]["J2"]
        assert j2["total_commands"] == 10
        assert j2["superseded_commands"] == 3
        assert j2["supersede_rate_pct"] == 30.0

        # 30% > 25% threshold → issue raised
        sup_issues = [
            i for i in result["issues"]
            if "supersede" in i["title"].lower()
        ]
        assert len(sup_issues) == 1

    def test_low_supersede_no_issue(self):
        """Supersede rate below threshold → no issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(10):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {"joint": "J3", "superseded": False},
                ],
            })
        result = analyze_motor_telemetry(es)
        j3 = result["supersede_rate"]["J3"]
        assert j3["supersede_rate_pct"] == 0.0
        sup_issues = [
            i for i in result["issues"]
            if "supersede" in i["title"].lower()
        ]
        assert len(sup_issues) == 0


class TestCANHealth:
    """task 9.7 — CAN bus health."""

    def test_zero_failures_no_issue(self):
        """Zero CAN failures → no issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(5):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {
                        "joint": "J1",
                        "can_tx_fail": 0,
                        "can_timeout": 0,
                    },
                ],
            })
        result = analyze_motor_telemetry(es)
        j1 = result["can_health"]["J1"]
        assert j1["tx_fail_count"] == 0
        assert j1["timeout_count"] == 0
        can_issues = [
            i for i in result["issues"]
            if i["category"] == "can_bus"
        ]
        assert len(can_issues) == 0

    def test_nonzero_failures_high_issue(self):
        """Non-zero CAN failures → high severity issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(5):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {
                        "joint": "J4",
                        "can_tx_fail": 1,
                        "can_timeout": 0,
                    },
                ],
            })
        result = analyze_motor_telemetry(es)
        j4 = result["can_health"]["J4"]
        assert j4["tx_fail_count"] == 5
        can_issues = [
            i for i in result["issues"]
            if i["category"] == "can_bus"
        ]
        assert len(can_issues) == 1
        assert can_issues[0]["severity"] == "high"

    def test_timeout_failures_reported(self):
        """CAN timeout failures also trigger high issue."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(5):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {
                        "joint": "J5",
                        "can_tx_fail": 0,
                        "can_timeout": 2,
                    },
                ],
            })
        result = analyze_motor_telemetry(es)
        j5 = result["can_health"]["J5"]
        assert j5["timeout_count"] == 10
        can_issues = [
            i for i in result["issues"]
            if i["category"] == "can_bus" and "J5" in i["title"]
        ]
        assert len(can_issues) == 1


class TestMotorHealthJsonParsing:
    """task 9.2 — Motor health JSON event parsing verification."""

    def test_multiple_motors_per_event(self):
        """Multiple motors in a single event are all parsed."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(5):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {"joint": "J1", "temp_c": 40.0},
                    {"joint": "J2", "temp_c": 45.0},
                    {"joint": "J3", "temp_c": 50.0},
                ],
            })
        result = analyze_motor_telemetry(es)
        assert "J1" in result["temperature"]
        assert "J2" in result["temperature"]
        assert "J3" in result["temperature"]

    def test_missing_fields_handled(self):
        """Motors with missing optional fields don't crash."""
        from log_analyzer.detectors.motor_telemetry import (
            analyze_motor_telemetry,
        )

        es = EventStore()
        for i in range(5):
            es.motor_health_arm.append({
                "_ts": 100.0 + i,
                "motors": [
                    {"joint": "J1"},  # no temp, no voltage, etc.
                ],
            })
        result = analyze_motor_telemetry(es)
        # Should not crash; J1 won't appear in temperature
        # (fewer than MIN_SAMPLES with temp data)
        assert result["issues"] == []


# ===================================================================
# Task 18.8 — Camera health (group 10)
# ===================================================================


class TestCameraTemperatureTrend:
    """task 10.1 — OAK-D temperature trend extraction."""

    def test_temperature_trend_extracted(self):
        """Camera temperature trend is extracted from summaries."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "camera_temp_c": 50.0 + i * 3.0,
            })
        result = analyze_camera_health(es)
        temp = result["temperature"]
        assert temp["has_data"] is True
        assert temp["start_temp_c"] == 50.0
        # peak = 50 + 9*3 = 77
        assert temp["peak_temp_c"] == 77.0
        assert temp["end_temp_c"] == 77.0

    def test_high_temp_issue(self):
        """Temperature >80C triggers high severity issue."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "camera_temp_c": 70.0 + i * 2.0,
            })
        # peak = 70 + 9*2 = 88 > 80
        result = analyze_camera_health(es)
        issues = [
            i for i in result["issues"]
            if i["category"] == "thermal"
        ]
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_medium_temp_issue(self):
        """Temperature between 70C and 80C triggers medium issue."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "camera_temp_c": 60.0 + i * 1.5,
            })
        # peak = 60 + 9*1.5 = 73.5, > 70 but < 80
        result = analyze_camera_health(es)
        issues = [
            i for i in result["issues"]
            if i["category"] == "thermal"
        ]
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"

    def test_normal_temp_no_issue(self):
        """Temperature below 70C triggers no issue."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "camera_temp_c": 40.0 + i * 2.0,
            })
        # peak = 40 + 18 = 58 < 70
        result = analyze_camera_health(es)
        temp_issues = [
            i for i in result["issues"]
            if i["category"] == "thermal"
        ]
        assert len(temp_issues) == 0

    def test_stabilization_time(self):
        """Stabilization time computed when temps stabilize."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        # 5 rising, then 10 stable at ~65
        for i in range(5):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "camera_temp_c": 50.0 + i * 3.0,
            })
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1300.0 + i * 60,
                "camera_temp_c": 65.0 + 0.1 * (i % 2),
            })
        result = analyze_camera_health(es)
        temp = result["temperature"]
        assert temp["stabilize_time_s"] is not None


class TestCameraMemoryLeak:
    """task 10.2 — Camera memory leak detection."""

    def test_no_leak_stable_memory(self):
        """Stable memory readings → no leak detected."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "host_memory_mb": 500.0,
            })
        result = analyze_camera_health(es)
        memory = result["memory"]
        assert memory["leak_detected"] is False

    def test_gradual_growth_detected(self):
        """Memory growing >50% triggers gradual leak detection."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "host_memory_mb": 400.0 + i * 30.0,
            })
        # peak = 400 + 270 = 670, growth = 67.5% > 50%
        result = analyze_camera_health(es)
        memory = result["memory"]
        assert memory["leak_detected"] is True
        assert memory["gradual_increase_pct"] > 50.0

    def test_post_reconnect_increase(self):
        """Memory increase after reconnection detected."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        # Pre-reconnection memory: ~400MB
        for i in range(5):
            es.detection_summaries.append({
                "_ts": 1000.0 + i * 60,
                "host_memory_mb": 400.0,
            })
        # Reconnection event
        es.camera_reconnections.append({
            "_ts": 1350.0,
            "type": "reconnected",
            "success": True,
        })
        # Post-reconnection memory: ~550MB (+37.5% > 20%)
        for i in range(10):
            es.detection_summaries.append({
                "_ts": 1400.0 + i * 60,
                "host_memory_mb": 550.0,
            })
        result = analyze_camera_health(es)
        memory = result["memory"]
        assert memory["leak_detected"] is True
        assert memory["post_reconnect_increase_pct"] is not None


class TestCameraReconnectionTimeline:
    """task 10.3 — Camera reconnection timeline."""

    def test_empty_reconnections(self):
        """No reconnections → count 0, empty timeline."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        result = analyze_camera_health(es)
        recon = result["reconnections"]
        assert recon["count"] == 0
        assert recon["timeline"] == []

    def test_reconnection_timeline_built(self):
        """Trigger + reconnected events build timeline entry."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        es.camera_reconnections = [
            {"_ts": 100.0, "type": "xlink"},
            {"_ts": 105.0, "type": "reconnected"},
        ]
        result = analyze_camera_health(es)
        recon = result["reconnections"]
        assert recon["count"] == 2
        assert recon["successful_count"] == 1
        assert len(recon["timeline"]) == 1
        entry = recon["timeline"][0]
        assert entry["trigger"] == "xlink"
        assert entry["outage_duration_s"] == 5.0

    def test_excessive_reconnections_issue(self):
        """More than 2 reconnections triggers high issue."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        for i in range(3):
            es.camera_reconnections.append({
                "_ts": 100.0 + i * 100,
                "type": "xlink",
            })
            es.camera_reconnections.append({
                "_ts": 110.0 + i * 100,
                "type": "reconnected",
            })
        result = analyze_camera_health(es)
        recon_issues = [
            i for i in result["issues"]
            if i["category"] == "camera"
            and "Reconnection" in i["title"]
        ]
        assert len(recon_issues) == 1
        assert recon_issues[0]["severity"] == "high"


class TestStereoDepthFailure:
    """task 10.4 — Stereo depth failure detection."""

    def test_no_quality_events(self):
        """No detection quality events → has_data False."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        result = analyze_camera_health(es)
        depth = result["depth_failures"]
        assert depth["has_data"] is False

    def test_depth_failure_rate_computed(self):
        """Depth failures inferred from raw - accepted - border - not_pickable."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        # 100 raw, 70 accepted, 10 border, 10 not_pickable → 10 depth
        es.detection_quality_events = [
            {
                "raw": 100,
                "cotton_accepted": 70,
                "border_skip": 10,
                "not_pickable": 10,
                "_ts": 100.0,
            },
        ]
        result = analyze_camera_health(es)
        depth = result["depth_failures"]
        assert depth["has_data"] is True
        assert depth["total_raw"] == 100
        assert depth["total_depth_failures"] == 10
        assert depth["depth_failure_rate"] == 0.1

    def test_high_depth_failure_issue(self):
        """Depth failure rate >5% triggers medium issue."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        es.detection_quality_events = [
            {
                "raw": 100,
                "cotton_accepted": 50,
                "border_skip": 10,
                "not_pickable": 10,
                "_ts": 100.0,
            },
        ]
        # depth failures = 100 - 50 - 10 - 10 = 30, rate = 30%
        result = analyze_camera_health(es)
        depth_issues = [
            i for i in result["issues"]
            if "Depth" in i["title"]
        ]
        assert len(depth_issues) == 1
        assert depth_issues[0]["severity"] == "medium"

    def test_zero_depth_failures(self):
        """Zero depth failures → no issue."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        es.detection_quality_events = [
            {
                "raw": 100,
                "cotton_accepted": 80,
                "border_skip": 10,
                "not_pickable": 10,
                "_ts": 100.0,
            },
        ]
        result = analyze_camera_health(es)
        depth = result["depth_failures"]
        assert depth["total_depth_failures"] == 0


class TestDetectionFilteringStats:
    """task 10.5 — Detection filtering statistics."""

    def test_filtering_from_quality_events(self):
        """Filtering stats aggregated from quality events."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        es.detection_quality_events = [
            {
                "raw": 50,
                "cotton_accepted": 30,
                "border_skip_total": 10,
                "not_pickable_total": 5,
                "_ts": 100.0,
            },
            {
                "raw": 50,
                "cotton_accepted": 25,
                "border_skip_total": 15,
                "not_pickable_total": 8,
                "_ts": 200.0,
            },
        ]
        result = analyze_camera_health(es)
        filtering = result["filtering"]
        assert filtering["total_raw"] == 100
        assert filtering["total_accepted"] == 55
        # border = max(10, 15) = 15; not_pickable = max(5, 8) = 8
        assert filtering["total_border_filtered"] == 15
        assert filtering["total_not_pickable"] == 8
        assert filtering["acceptance_rate_pct"] == 55.0

    def test_empty_no_filtering_data(self):
        """No events → empty filtering dict."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        result = analyze_camera_health(es)
        assert result["filtering"] == {}

    def test_fallback_to_frames_summary(self):
        """When no quality_events, falls back to frames_summary."""
        from log_analyzer.detectors.camera_health import (
            analyze_camera_health,
        )

        es = EventStore()
        es.detection_frames_summary = {
            "count": 10,
            "raw_count": 80,
            "accepted_count": 60,
            "border_filtered": 10,
            "not_pickable": 5,
        }
        result = analyze_camera_health(es)
        filtering = result["filtering"]
        assert filtering["total_raw"] == 80
        assert filtering["total_accepted"] == 60
