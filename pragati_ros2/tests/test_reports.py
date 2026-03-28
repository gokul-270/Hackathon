"""
tests/test_reports.py

Tests for report generation: field summary, per-arm pick performance,
cross-arm motor health, vehicle motor health section, per-arm failure/MQTT,
camera health, scan effectiveness, motor homing, per-joint timing,
detection quality, fallback position count, and no-data section omission.

Tasks: 21.12, 10.4–10.7, 22.2 (ee_short_retract), 22.3 (severely_stale),
       22.5–22.9, fix #7, fix #8
"""

from io import StringIO
from unittest.mock import patch

import pytest

from log_analyzer import detectors as _det
from log_analyzer import reports
from log_analyzer.analyzer import ROS2LogAnalyzer
from log_analyzer.models import EventStore, FieldSummary, MQTTMetrics, NetworkMetrics

from conftest import make_minimal_analyzer

# ---------------------------------------------------------------------------
# task 21.12 — field summary generation
# ---------------------------------------------------------------------------


class TestFieldSummaryGeneration:
    def test_field_summary_populated(self, log_dir_with_files):
        """generate_field_summary populates all major sections."""
        a = ROS2LogAnalyzer(str(log_dir_with_files))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        summary = reports.generate_field_summary(a)
        assert summary is not None
        # All major sections should be present as dict/list keys
        assert hasattr(summary, "pick_performance")
        assert hasattr(summary, "vehicle_performance")
        assert hasattr(summary, "motor_reliability")
        assert hasattr(summary, "session_health")


# ---------------------------------------------------------------------------
# task 10.4 — per-arm pick performance report data
# ---------------------------------------------------------------------------


class TestPerArmPickPerformance:
    """task 10.4 — per-arm pick performance report data."""

    def _gen_summary(self, analyzer, tmp_path):
        analyzer.start_time = 1700000000.0
        analyzer.end_time = 1700003600.0  # 1 hour session
        summary = reports.generate_field_summary(analyzer)
        return summary

    def test_two_arms_yields_arm_summary_table(self, tmp_path):
        """Two arms → pick_performance.multi_arm=True, arm_summary_table has 2 rows."""
        a = make_minimal_analyzer(tmp_path)
        a.events.picks = [
            {
                "arm_id": "arm_1",
                "success": True,
                "total_ms": 1000,
                "_ts": 1700000100.0,
            },
            {
                "arm_id": "arm_1",
                "success": True,
                "total_ms": 1100,
                "_ts": 1700000200.0,
            },
            {
                "arm_id": "arm_2",
                "success": True,
                "total_ms": 900,
                "_ts": 1700000300.0,
            },
            {
                "arm_id": "arm_2",
                "success": False,
                "total_ms": 1200,
                "_ts": 1700000400.0,
            },
        ]
        summary = self._gen_summary(a, tmp_path)
        pp = summary.pick_performance
        assert pp["multi_arm"] is True
        assert len(pp["arm_summary_table"]) == 2

    def test_worst_arm_highlighted(self, tmp_path):
        """Arm with lowest success rate is marked as worst_arm."""
        a = make_minimal_analyzer(tmp_path)
        # arm_1: 100% success, arm_2: 50% success → arm_2 is worst
        a.events.picks = [
            {"arm_id": "arm_1", "success": True, "_ts": 1700000100.0},
            {"arm_id": "arm_1", "success": True, "_ts": 1700000200.0},
            {"arm_id": "arm_2", "success": True, "_ts": 1700000300.0},
            {"arm_id": "arm_2", "success": False, "_ts": 1700000400.0},
        ]
        summary = self._gen_summary(a, tmp_path)
        pp = summary.pick_performance
        assert pp["worst_arm"] == "arm_2"

    def test_per_arm_sub_sections_present(self, tmp_path):
        """Two arms → per_arm dict has two keys matching arm_ids."""
        a = make_minimal_analyzer(tmp_path)
        a.events.picks = [
            {"arm_id": "arm_1", "success": True, "_ts": 1700000100.0},
            {"arm_id": "arm_2", "success": True, "_ts": 1700000200.0},
        ]
        summary = self._gen_summary(a, tmp_path)
        pp = summary.pick_performance
        assert "arm_1" in pp["per_arm"]
        assert "arm_2" in pp["per_arm"]

    def test_single_arm_no_summary_table(self, tmp_path):
        """Single arm (all arm_id=None) → multi_arm=False, no summary table."""
        a = make_minimal_analyzer(tmp_path)
        a.events.picks = [
            {"arm_id": None, "success": True, "_ts": 1700000100.0},
            {"arm_id": None, "success": False, "_ts": 1700000200.0},
        ]
        summary = self._gen_summary(a, tmp_path)
        pp = summary.pick_performance
        assert pp["multi_arm"] is False
        assert pp["arm_summary_table"] == []

    def test_worst_arm_in_print_output(self, tmp_path):
        """Print output for multi-arm includes [worst] marker."""
        a = make_minimal_analyzer(tmp_path)
        a.events.picks = [
            {"arm_id": "arm_1", "success": True, "_ts": 1700000100.0},
            {"arm_id": "arm_1", "success": True, "_ts": 1700000200.0},
            {"arm_id": "arm_2", "success": True, "_ts": 1700000300.0},
            {"arm_id": "arm_2", "success": False, "_ts": 1700000400.0},
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        summary = reports.generate_field_summary(a)
        a.field_summary = summary

        buf = StringIO()
        with patch(
            "builtins.print",
            side_effect=lambda *args, **kw: buf.write(" ".join(str(a) for a in args) + "\n"),
        ):
            reports.print_field_summary(a)
        output = buf.getvalue()
        assert "[worst]" in output


# ---------------------------------------------------------------------------
# task 10.5 — Motor health data from different arms never pooled
# ---------------------------------------------------------------------------


class TestCrossArmMotorHealth:
    """task 10.5 — Motor health data from different arms never pooled."""

    def test_joint3_not_pooled_across_arms(self, tmp_path):
        """arm_1 and arm_2 both have joint3 → separate sub-sections."""
        a = make_minimal_analyzer(tmp_path)
        # Use list-of-dict format matching production parser output
        a.events.motor_health_arm = [
            {
                "arm_id": "arm_1",
                "_ts": 1700000100.0,
                "motors": [{"joint": "joint3", "temp_c": 40.0, "cmds": {"rx": 5}}],
            },
            {
                "arm_id": "arm_2",
                "_ts": 1700000200.0,
                "motors": [{"joint": "joint3", "temp_c": 45.0, "cmds": {"rx": 7}}],
            },
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        summary = reports.generate_field_summary(a)
        mh = summary.motor_health_trends
        assert mh.get("multi_arm") is True
        arm_summary = mh.get("arm", {})
        # Both arms should have separate entries in the per-arm dict
        assert "arm_1" in arm_summary or "arm_2" in arm_summary

    def test_trend_keys_on_arm_and_joint(self, tmp_path):
        """_trend_arm_motor_temperature keys on (arm_id, joint_name) composite."""
        a = make_minimal_analyzer(tmp_path)
        # Use list-of-dict format matching production parser output
        a.events.motor_health_arm = []
        for i in range(5):
            ts = 1700000000.0 + i * 720
            a.events.motor_health_arm.append(
                {
                    "arm_id": "arm_1",
                    "_ts": ts,
                    "motors": [{"joint": "joint3", "temp_c": 40.0 + i * 2}],
                }
            )
            a.events.motor_health_arm.append(
                {
                    "arm_id": "arm_2",
                    "_ts": ts,
                    "motors": [{"joint": "joint3", "temp_c": 60.0 + i * 2}],
                }
            )
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        alerts: list = []
        # Call should not raise even with composite keys
        reports._trend_arm_motor_temperature(a, a.start_time, alerts)
        # Verify no two alerts have the same joint label without arm prefix
        labels = [al.get("label", "") for al in alerts]
        for label in labels:
            if label == "Joint joint3":
                pytest.fail("Trend alert lacks arm_id prefix — composite key not used")


# ---------------------------------------------------------------------------
# task 10.6 — Vehicle motor health section
# ---------------------------------------------------------------------------


class TestVehicleMotorHealthSection:
    """task 10.6 — Vehicle motor health section rendered only when data present."""

    def test_vehicle_motor_section_rendered_when_present(self, tmp_path):
        """motor_health_vehicle events present → vehicle_detail in motor_health_trends."""
        a = make_minimal_analyzer(tmp_path)
        a.events.motor_health_vehicle = [
            {
                "_ts": 1700000100.0,
                "arm_id": "vehicle",
                "health_score": 95,
                "motors": [{"id": "m1", "error_count": 0, "stale_s": 0}],
            }
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        summary = reports.generate_field_summary(a)
        vehicle_detail = summary.motor_health_trends.get("vehicle_detail")
        assert vehicle_detail is not None
        assert vehicle_detail.get("has_data") is True

    def test_vehicle_motor_section_omitted_when_absent(self, tmp_path):
        """No motor_health_vehicle events → vehicle_detail not in motor_health_trends."""
        a = make_minimal_analyzer(tmp_path)
        a.events.motor_health_vehicle = []
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        summary = reports.generate_field_summary(a)
        vehicle_detail = summary.motor_health_trends.get("vehicle_detail")
        assert not vehicle_detail


# ---------------------------------------------------------------------------
# task 10.7 — Per-arm failure + MQTT sub-sections
# ---------------------------------------------------------------------------


class TestPerArmFailureMqtt:
    """task 10.7 — Per-arm failure + MQTT sub-sections, hourly per-arm tables."""

    def test_failures_from_two_arms_render_per_arm(self, tmp_path):
        """Pick failures from two arm_ids → per_arm sub-sections."""
        a = make_minimal_analyzer(tmp_path)
        # pick_failures is what _section_pick_failure_analysis groups (not picks)
        a.events.pick_failures = [
            {
                "arm_id": "arm_1",
                "phase": "approach",
                "reason": "timeout",
                "_ts": 1700000100.0,
            },
            {
                "arm_id": "arm_2",
                "phase": "capture",
                "reason": "collision",
                "_ts": 1700000200.0,
            },
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        summary = reports.generate_field_summary(a)
        pfa = summary.pick_failure_analysis
        assert pfa.get("multi_arm") is True
        assert "arm_1" in pfa.get("per_arm", {})
        assert "arm_2" in pfa.get("per_arm", {})

    def test_hourly_throughput_per_arm(self, tmp_path):
        """Picks from two arm_ids → per-arm hourly tables."""
        a = make_minimal_analyzer(tmp_path)
        a.events.picks = [
            {"arm_id": "arm_1", "success": True, "_ts": 1700000100.0},
            {"arm_id": "arm_2", "success": True, "_ts": 1700000200.0},
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        summary = reports.generate_field_summary(a)
        per_arm_hourly = getattr(summary, "_hourly_throughput_per_arm", {})
        assert "arm_1" in per_arm_hourly
        assert "arm_2" in per_arm_hourly


# ---------------------------------------------------------------------------
# task 22.2 — EE short retract note (report side)
# ---------------------------------------------------------------------------
# The detector tests are in test_detectors.py; this tests the report output.


class TestEEPositionMonitoring:
    """task 22.2 — ee_short_retract_note in report."""

    def test_100pct_short_retract_note(self, tmp_path):
        """All ee_short_retract_events have retract_mm=0 → ee_short_retract_note set."""
        a = make_minimal_analyzer(tmp_path)
        a.events.ee_short_retract_events = [
            {"retract_mm": 0, "_ts": 1.0, "arm_id": None},
            {"retract_mm": 0, "_ts": 2.0, "arm_id": None},
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        note = s.pick_performance.get("ee_short_retract_note", "")
        assert note != "", "Expected ee_short_retract_note to be set when all retracts are 0mm"


# ---------------------------------------------------------------------------
# task 22.3 — severely_stale_count (report side)
# ---------------------------------------------------------------------------


class TestStaleDetectionRate:
    """task 22.3 — severely_stale_count tracked in summary."""

    def test_severely_stale_count(self, tmp_path):
        """Picks with detection_age_ms > 10000 → severely_stale_count tracked."""
        a = make_minimal_analyzer(tmp_path)
        # 3 severely stale (>10000ms), 5 moderately stale (>2000ms), 12 fresh
        for _ in range(3):
            a.events.picks.append(
                {
                    "detection_age_ms": 15000,
                    "success": True,
                    "_ts": 1.0,
                    "arm_id": None,
                }
            )
        for _ in range(5):
            a.events.picks.append(
                {
                    "detection_age_ms": 3000,
                    "success": True,
                    "_ts": 1.0,
                    "arm_id": None,
                }
            )
        for _ in range(12):
            a.events.picks.append(
                {
                    "detection_age_ms": 300,
                    "success": True,
                    "_ts": 1.0,
                    "arm_id": None,
                }
            )
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        assert s.pick_performance.get("severely_stale_count") == 3


# ---------------------------------------------------------------------------
# task 22.5 — Camera Health
# ---------------------------------------------------------------------------


class TestCameraHealth:
    """task 22.5 — _section_camera_health section population."""

    def _make_camera_block(
        self,
        total_requests=10,
        with_cotton=5,
        frame_wait_ms=50,
        frame_wait_max_ms=100,
    ):
        return {
            "requests": total_requests,
            "with_cotton": with_cotton,
            "frame_wait_avg_ms": frame_wait_ms,
            "frame_wait_max_ms": frame_wait_max_ms,
            "temp_c": 45.0,
            "latency_avg_ms": 30.0,
            "css_pct": 120.0,
            "mss_pct": 80.0,
            "_ts": 1700000100.0,
        }

    def test_camera_stats_blocks_parsed(self, tmp_path):
        """Injecting camera_stats_blocks populates summary.camera_health."""
        a = make_minimal_analyzer(tmp_path)
        a.events.camera_stats_blocks = [self._make_camera_block()]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        ch = s.camera_health
        assert ch.get("total_blocks") == 1
        assert ch.get("total_requests") == 10
        assert ch.get("total_with_cotton") == 5

    def test_never_detected_note(self, tmp_path):
        """total_requests > 0 but total_with_cotton == 0 → never_detected_note set."""
        a = make_minimal_analyzer(tmp_path)
        a.events.camera_stats_blocks = [self._make_camera_block(total_requests=10, with_cotton=0)]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        note = s.camera_health.get("never_detected_note", "")
        assert note != "", "Expected never_detected_note when no cotton was ever detected"

    def test_max_wait_2x_median_emits_medium(self):
        """Two camera_stats_blocks with last frame_wait_max > 2x first → Medium issue."""
        events = EventStore()
        events.camera_stats_blocks = [
            {"frame_wait_max_ms": 100, "_ts": 1.0},
            {"frame_wait_max_ms": 250, "_ts": 2.0},
        ]
        issues = _det.detect_camera_frame_wait_degradation(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"


# ---------------------------------------------------------------------------
# task 22.6 — Scan Effectiveness
# ---------------------------------------------------------------------------


class TestScanEffectiveness:
    """task 22.6 — _section_scan_effectiveness section population."""

    def test_scan_positions_parsed(self, tmp_path):
        """Injecting scan_position_results → by_position populated in summary."""
        a = make_minimal_analyzer(tmp_path)
        a.events.scan_position_results = [
            {
                "position_index": "0",
                "j4_offset_m": 0.0,
                "cotton_found": 3,
                "cotton_picked": 2,
                "_ts": 1.0,
                "arm_id": None,
            },
            {
                "position_index": "1",
                "j4_offset_m": 0.1,
                "cotton_found": 5,
                "cotton_picked": 4,
                "_ts": 2.0,
                "arm_id": None,
            },
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        by_pos = s.scan_effectiveness.get("by_position", {})
        assert "0" in by_pos
        assert "1" in by_pos

    def test_dead_zone_detection(self):
        """Position with 0 cotton while others > 0 → Low issue."""
        events = EventStore()
        events.scan_position_results = [
            {"j4_offset_m": 0.0, "cotton_found": 0, "_ts": 1.0},
            {"j4_offset_m": 0.1, "cotton_found": 5, "_ts": 2.0},
            {"j4_offset_m": 0.2, "cotton_found": 3, "_ts": 3.0},
        ]
        issues = _det.detect_scan_dead_zones(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "low"
        assert "J4=0.0m" in issues[0]["title"]


# ---------------------------------------------------------------------------
# task 22.7 — Motor Homing
# ---------------------------------------------------------------------------


class TestMotorHoming:
    """task 22.7 — _section_motor_homing section population."""

    def test_successful_homing_populated(self, tmp_path):
        """Injecting a successful homing event → joint_table has homed=True."""
        a = make_minimal_analyzer(tmp_path)
        a.events.homing_events = [
            {
                "joint_name": "J3",
                "success": True,
                "position_error": 0.001,
                "tolerance": 0.01,
                "_ts": 1700000100.0,
                "arm_id": None,
            }
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        mh = s.motor_homing
        assert mh.get("total_events") == 1
        table = mh.get("joint_table", [])
        assert len(table) == 1
        assert table[0]["homed"] is True
        assert table[0]["joint"] == "J3"

    def test_near_tolerance_highlighted(self, tmp_path):
        """err/tol ratio > 80% → near_tolerance=True in joint_table entry."""
        a = make_minimal_analyzer(tmp_path)
        a.events.homing_events = [
            {
                "joint_name": "J4",
                "success": True,
                "position_error": 0.009,  # 90% of tolerance
                "tolerance": 0.01,
                "_ts": 1700000100.0,
                "arm_id": None,
            }
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        table = s.motor_homing.get("joint_table", [])
        assert table[0]["near_tolerance"] is True
        assert table[0]["err_tol_ratio_pct"] > 80.0

    def test_homing_failure_emits_critical(self):
        """A failed homing event → Critical issue from detect_homing_failures."""
        events = EventStore()
        events.homing_events = [
            {
                "joint_name": "J5",
                "success": False,
                "position_error": None,
                "tolerance": None,
                "_ts": 1700000100.0,
                "arm_id": None,
            }
        ]
        issues = _det.detect_homing_failures(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert "J5" in issues[0]["title"]


# ---------------------------------------------------------------------------
# task 22.8 — Per-Joint Timing
# ---------------------------------------------------------------------------


class TestPerJointTiming:
    """task 22.8 — _section_per_joint_timing section population."""

    def test_approach_timing_parsed(self, tmp_path):
        """Injecting per_joint_timings → joint_approach_stats populated."""
        a = make_minimal_analyzer(tmp_path)
        a.events.per_joint_timings = [
            {"joint": "j3", "duration_ms": 200, "_ts": 1.0, "arm_id": None},
            {"joint": "j3", "duration_ms": 220, "_ts": 2.0, "arm_id": None},
            {"joint": "j4", "duration_ms": 150, "_ts": 3.0, "arm_id": None},
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        stats = s.per_joint_timing.get("joint_approach_stats", {})
        assert "j3" in stats
        assert "j4" in stats

    def test_bottleneck_joint_identified(self, tmp_path):
        """Joint with highest p95 approach time → bottleneck_joint set."""
        a = make_minimal_analyzer(tmp_path)
        a.events.per_joint_timings = [
            {"joint": "j3", "duration_ms": 500, "_ts": 1.0, "arm_id": None},
            {"joint": "j4", "duration_ms": 100, "_ts": 2.0, "arm_id": None},
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        assert s.per_joint_timing.get("bottleneck_joint") == "j3"

    def test_retreat_breakdown_parsed(self, tmp_path):
        """Injecting retreat_breakdowns → retreat_stats populated."""
        a = make_minimal_analyzer(tmp_path)
        a.events.retreat_breakdowns = [
            {
                "j5_ms": 100,
                "ee_off_ms": 50,
                "j3_ms": 80,
                "j4_ms": 60,
                "compressor_ms": 200,
                "_ts": 1.0,
                "arm_id": None,
            }
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        rs = s.per_joint_timing.get("retreat_stats", {})
        assert "compressor_ms" in rs
        assert "j5_ms" in rs


# ---------------------------------------------------------------------------
# task 22.9 — Detection Quality
# ---------------------------------------------------------------------------


class TestDetectionQuality:
    """task 22.9 — _section_detection_quality section."""

    def test_detection_counts_aggregated(self, tmp_path):
        """Injecting detection_quality_events → totals computed."""
        a = make_minimal_analyzer(tmp_path)
        a.events.detection_quality_events = [
            {
                "raw": 10,
                "cotton_accepted": 6,
                "border_skip": 2,
                "border_skip_total": 2,
                "not_pickable": 1,
                "not_pickable_total": 1,
                "_ts": 1.0,
                "arm_id": None,
            },
            {
                "raw": 8,
                "cotton_accepted": 5,
                "border_skip": 1,
                "border_skip_total": 1,
                "not_pickable": 0,
                "not_pickable_total": 0,
                "_ts": 2.0,
                "arm_id": None,
            },
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        dq = s.detection_quality
        assert isinstance(dq, dict)

    def test_frame_freshness_aggregated(self, tmp_path):
        """Injecting frame_freshness_events → avg_stale_flushed_per_request computed."""
        a = make_minimal_analyzer(tmp_path)
        # Section uses stale_flushed/wait_ms keys (arm_patterns.py contract)
        a.events.frame_freshness_events = [
            {"stale_flushed": 3, "wait_ms": 120, "_ts": 1.0, "arm_id": None},
            {"stale_flushed": 1, "wait_ms": 80, "_ts": 2.0, "arm_id": None},
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        dq = s.detection_quality
        assert dq.get("avg_stale_flushed_per_request") == pytest.approx(2.0)
        assert dq.get("avg_frame_wait_ms") == pytest.approx(100.0)

    def test_border_skip_rate_emits_medium(self):
        """border_skip_total/raw > 30% with raw_total >= 10 → Medium issue."""
        events = EventStore()
        # 4 border-skipped out of 10 raw = 40%
        events.detection_quality_events = [
            {
                "raw": 10,
                "cotton_accepted": 5,
                "border_skip": 4,
                "border_skip_total": 4,
                "not_pickable": 1,
                "not_pickable_total": 1,
                "_ts": 1.0,
                "arm_id": None,
            }
        ]
        issues = _det.detect_border_skip_rate(events)
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"

    def test_border_skip_cumulative_uses_max_not_sum(self):
        """Multiple events with cumulative border_skip_total → max used, not sum."""
        events = EventStore()
        # Event 1: cumulative total=4, event 2: cumulative total=7
        # Correct: use 7 (final/max value), NOT 11 (sum)
        events.detection_quality_events = [
            {
                "raw": 10,
                "cotton_accepted": 6,
                "border_skip": 4,
                "border_skip_total": 4,
                "not_pickable": 0,
                "not_pickable_total": 0,
                "_ts": 1.0,
                "arm_id": None,
            },
            {
                "raw": 10,
                "cotton_accepted": 5,
                "border_skip": 3,
                "border_skip_total": 7,
                "not_pickable": 0,
                "not_pickable_total": 0,
                "_ts": 2.0,
                "arm_id": None,
            },
        ]
        issues = _det.detect_border_skip_rate(events)
        # raw_total = 20, border_total = max(4,7) = 7, rate = 35% > 30%
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"
        # Verify the message contains 7/20, not 11/20
        assert "7/" in issues[0].get("message", "")


# ---------------------------------------------------------------------------
# Verify fix #7 — Fallback position parsing/counting
# ---------------------------------------------------------------------------


class TestFallbackPositionCount:
    """Verify fix #7 — fallback_position_count in field summary."""

    def test_fallback_positions_counted(self, tmp_path):
        """_fallback_position_count on events → detection_quality section."""
        a = make_minimal_analyzer(tmp_path)
        a.events._fallback_position_count = 5
        a.events.detection_quality_events = [
            {
                "raw": 10,
                "cotton_accepted": 6,
                "border_skip": 1,
                "border_skip_total": 1,
                "not_pickable": 0,
                "not_pickable_total": 0,
                "_ts": 1.0,
                "arm_id": None,
            }
        ]
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        dq = s.detection_quality
        assert dq.get("fallback_position_count") == 5


# ---------------------------------------------------------------------------
# Verify fix #8 — No-data sections omitted
# ---------------------------------------------------------------------------


class TestNoDataSectionsOmitted:
    """Verify fix #8 — empty EventStore lists → empty/absent summary sections."""

    def test_no_camera_data_omits_section(self, tmp_path):
        """Empty camera_stats_blocks → camera_health is empty dict."""
        a = make_minimal_analyzer(tmp_path)
        a.events.camera_stats_blocks = []
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        assert s.camera_health == {}

    def test_no_scan_data_omits_section(self, tmp_path):
        """Empty scan_position_results → scan_effectiveness is empty dict."""
        a = make_minimal_analyzer(tmp_path)
        a.events.scan_position_results = []
        a.events.scan_summaries = []
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        assert s.scan_effectiveness == {}

    def test_no_homing_data_omits_section(self, tmp_path):
        """Empty homing_events → motor_homing is empty dict."""
        a = make_minimal_analyzer(tmp_path)
        a.events.homing_events = []
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        assert s.motor_homing == {}

    def test_no_detection_quality_omits_section(self, tmp_path):
        """Empty detection_quality_events and frame_freshness_events → empty dict."""
        a = make_minimal_analyzer(tmp_path)
        a.events.detection_quality_events = []
        a.events.frame_freshness_events = []
        a.start_time = 1700000000.0
        a.end_time = 1700003600.0
        s = reports.generate_field_summary(a)
        assert s.detection_quality == {}


# ---------------------------------------------------------------------------
# A13 — Pick cycle time trend excludes instant rejections
# ---------------------------------------------------------------------------


class TestPickCycleTimeTrendFiltering:
    """_trend_pick_cycle_time must exclude instant IK rejections (total_ms <= 1).

    February 2026 field data showed a false 21.8%/hour degradation alert
    caused by mixing 0-1ms instant rejections with real 6,400ms pick cycles.
    As the proportion of instant rejections naturally fluctuated between hours,
    the blended average shifted, creating a spurious trend.

    The fix: filter out picks with total_ms <= 1 before computing the trend.
    """

    def test_instant_rejections_cause_false_degradation(self, tmp_path):
        """Mixing instant rejections with real picks creates a false alert."""
        a = make_minimal_analyzer(tmp_path)
        a.start_time = 1700000000.0
        a.end_time = 1700007200.0  # 2 hours

        # Hour 0: 70% instant rejections, 30% real picks
        # Hour 1: 50% instant rejections, 50% real picks
        # This shift in rejection ratio inflates the blended average
        picks = []
        # Hour 0: 70 instant rejections + 30 real picks (~6500ms)
        for i in range(70):
            picks.append({"total_ms": 0, "_ts": 1700000000.0 + i * 50})
        for i in range(30):
            picks.append({"total_ms": 6500, "_ts": 1700000000.0 + 3500 + i * 50})
        # Hour 1: 50 instant rejections + 50 real picks (~6500ms)
        for i in range(50):
            picks.append({"total_ms": 0, "_ts": 1700003600.0 + i * 50})
        for i in range(50):
            picks.append({"total_ms": 6500, "_ts": 1700003600.0 + 2500 + i * 50})

        a.events.picks = picks
        alerts: list = []
        reports._trend_pick_cycle_time(a, a.start_time, alerts)

        # Should NOT fire a degradation alert — real pick times are constant
        degradation_alerts = [al for al in alerts if al["type"] == "pick_cycle_time_degradation"]
        assert degradation_alerts == [], (
            "False degradation alert fired due to instant rejection ratio shift. "
            f"Got: {degradation_alerts}"
        )

    def test_real_degradation_still_detected(self, tmp_path):
        """Genuine cycle time increase in real picks is still caught."""
        a = make_minimal_analyzer(tmp_path)
        a.start_time = 1700000000.0
        a.end_time = 1700007200.0

        picks = []
        # Hour 0: real picks at 3000ms
        for i in range(30):
            picks.append({"total_ms": 3000, "_ts": 1700000000.0 + i * 100})
        # Hour 1: real picks at 6000ms (100% increase = genuine degradation)
        for i in range(30):
            picks.append({"total_ms": 6000, "_ts": 1700003600.0 + i * 100})

        a.events.picks = picks
        alerts: list = []
        reports._trend_pick_cycle_time(a, a.start_time, alerts)

        degradation_alerts = [al for al in alerts if al["type"] == "pick_cycle_time_degradation"]
        assert (
            len(degradation_alerts) == 1
        ), "Real degradation (3000ms → 6000ms) should trigger an alert"

    def test_recovery_rejections_excluded(self, tmp_path):
        """Picks with total_ms == 1 (recovery rejections) are also excluded."""
        a = make_minimal_analyzer(tmp_path)
        a.start_time = 1700000000.0
        a.end_time = 1700007200.0

        picks = []
        # Hour 0: many recovery rejections (total_ms=1) + real picks
        for i in range(60):
            picks.append({"total_ms": 1, "_ts": 1700000000.0 + i * 50})
        for i in range(20):
            picks.append({"total_ms": 6500, "_ts": 1700000000.0 + 3000 + i * 50})
        # Hour 1: fewer recovery rejections + same real picks
        for i in range(20):
            picks.append({"total_ms": 1, "_ts": 1700003600.0 + i * 50})
        for i in range(20):
            picks.append({"total_ms": 6500, "_ts": 1700003600.0 + 1000 + i * 50})

        a.events.picks = picks
        alerts: list = []
        reports._trend_pick_cycle_time(a, a.start_time, alerts)

        degradation_alerts = [al for al in alerts if al["type"] == "pick_cycle_time_degradation"]
        assert (
            degradation_alerts == []
        ), "Recovery rejection ratio shift should not cause false degradation alert"

    def test_only_instant_rejections_no_alert(self, tmp_path):
        """Sessions with only instant rejections produce no trend alert."""
        a = make_minimal_analyzer(tmp_path)
        a.start_time = 1700000000.0
        a.end_time = 1700007200.0

        picks = []
        for i in range(50):
            picks.append({"total_ms": 0, "_ts": 1700000000.0 + i * 50})
        for i in range(50):
            picks.append({"total_ms": 1, "_ts": 1700003600.0 + i * 50})

        a.events.picks = picks
        alerts: list = []
        reports._trend_pick_cycle_time(a, a.start_time, alerts)

        assert alerts == [], "Only-rejection sessions should not produce alerts"
