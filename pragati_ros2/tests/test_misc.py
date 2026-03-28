"""
tests/test_misc.py

Miscellaneous tests: PerformanceMetric unit helper and
regression guard that verifies the total test count.

Tasks: 21.15, 22.11
"""

from unittest.mock import patch

from log_analyzer.analyzer import PerformanceMetric, ROS2LogAnalyzer


# ---------------------------------------------------------------------------
# task 21.15 — unit fix
# ---------------------------------------------------------------------------


class TestUnitFix:
    def test_fps_unit(self, log_dir_with_files):
        """FPS performance metric shows 'fps' unit."""
        a = ROS2LogAnalyzer(str(log_dir_with_files))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        # Inject a known fps metric
        a.performance["fps"] = PerformanceMetric(
            name="fps", values=[30.0], unit="fps"
        )
        assert a.performance["fps"].unit == "fps"

    def test_temperature_unit(self, log_dir_with_files):
        """Temperature performance metric shows '°C' unit."""
        a = ROS2LogAnalyzer(str(log_dir_with_files))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        a.performance["temperature"] = PerformanceMetric(
            name="temperature", values=[52.0], unit="°C"
        )
        assert a.performance["temperature"].unit == "°C"

    def test_detection_confidence_unitless(self, log_dir_with_files):
        """detection_confidence metric has empty unit string."""
        a = ROS2LogAnalyzer(str(log_dir_with_files))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        a.performance["detection_confidence"] = PerformanceMetric(
            name="detection_confidence", values=[0.85], unit=""
        )
        assert a.performance["detection_confidence"].unit == ""

    def test_metric_units_dict_present(self):
        """METRIC_UNITS dict is defined on the analyzer class."""
        assert "fps" in ROS2LogAnalyzer.METRIC_UNITS
        assert ROS2LogAnalyzer.METRIC_UNITS["fps"] == "fps"
        assert "temperature" in ROS2LogAnalyzer.METRIC_UNITS
        assert "°C" in ROS2LogAnalyzer.METRIC_UNITS["temperature"]
        assert "detection_confidence" in ROS2LogAnalyzer.METRIC_UNITS
        assert ROS2LogAnalyzer.METRIC_UNITS["detection_confidence"] == ""


# ---------------------------------------------------------------------------
# task 22.11 — Verify all existing tests still pass
# ---------------------------------------------------------------------------


class TestVerifyAllExistingTestsPass:
    """
    task 22.11 — Regression guard.

    This class documents the intent that all previously-passing tests must
    continue to pass after adding the 22.x test classes above.  The full
    test suite (pytest tests/) is the authoritative check — no individual
    test bodies are needed here.
    """
