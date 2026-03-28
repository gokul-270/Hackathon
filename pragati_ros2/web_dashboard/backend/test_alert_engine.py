#!/usr/bin/env python3
"""
Tests for the Alert Engine
==========================

Covers: config loading, threshold evaluation, duration requirements,
cooldown behavior, rule management, and alert acknowledgement.
"""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.alert_engine import AlertEngine, AlertRule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ALERTS_YAML = Path(__file__).parent.parent / "config" / "alerts.yaml"


@pytest.fixture
def engine():
    """Bare AlertEngine with no config (for unit tests)."""
    eng = AlertEngine()
    # Disable cooldown and grouping so tests fire freely.
    eng.cooldown_sec = 0
    eng.group_window_sec = 0
    return eng


@pytest.fixture
def config_engine():
    """AlertEngine loaded from the real alerts.yaml."""
    eng = AlertEngine(config_path=str(ALERTS_YAML))
    eng.cooldown_sec = 0
    eng.group_window_sec = 0
    return eng


@pytest.fixture
def cpu_rule():
    """Simple cpu_percent > 80 rule with no duration."""
    return AlertRule(
        name="test_cpu_high",
        metric="cpu_percent",
        threshold=80,
        comparison="greater_than",
        severity="warning",
    )


@pytest.fixture
def memory_rule():
    """memory_percent > 85 rule with no duration."""
    return AlertRule(
        name="test_memory_high",
        metric="memory_percent",
        threshold=85,
        comparison="greater_than",
        severity="warning",
    )


# ---------------------------------------------------------------------------
# 1. Config loading
# ---------------------------------------------------------------------------


def test_load_config(config_engine):
    """Load alerts.yaml and verify expected rules exist."""
    rule_names = list(config_engine.rules.keys())

    # Must contain at least these three families of rules.
    cpu_rules = [n for n in rule_names if "cpu" in n.lower()]
    mem_rules = [n for n in rule_names if "memory" in n.lower()]
    motor_temp = [
        n for n in rule_names if "motor" in n.lower() and "temp" in n.lower()
    ]

    assert len(cpu_rules) >= 1, "No cpu_percent rules loaded"
    assert len(mem_rules) >= 1, "No memory_percent rules loaded"
    assert len(motor_temp) >= 1, "No motor_temperature rules loaded"


# ---------------------------------------------------------------------------
# 2. Greater-than threshold triggers alert
# ---------------------------------------------------------------------------


def test_check_metric_greater_than_triggers(engine, cpu_rule):
    """Value above threshold must produce an active alert."""
    engine.add_rule(cpu_rule)
    engine.check_metric("cpu_percent", 90)

    alerts = engine.get_active_alerts()
    assert len(alerts) == 1
    assert alerts[0]["rule_name"] == "test_cpu_high"
    assert alerts[0]["metric_value"] == 90


# ---------------------------------------------------------------------------
# 3. Below threshold — no alert
# ---------------------------------------------------------------------------


def test_check_metric_below_threshold_no_alert(engine, cpu_rule):
    """Value below threshold must NOT produce an alert."""
    engine.add_rule(cpu_rule)
    engine.check_metric("cpu_percent", 70)

    assert engine.get_active_alerts() == []


# ---------------------------------------------------------------------------
# 4. High memory triggers alert
# ---------------------------------------------------------------------------


def test_high_memory_triggers_alert(engine, memory_rule):
    """memory_percent > 85 with value 90 should fire."""
    engine.add_rule(memory_rule)
    engine.check_metric("memory_percent", 90)

    alerts = engine.get_active_alerts()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "warning"
    assert alerts[0]["metric_value"] == 90


# ---------------------------------------------------------------------------
# 5. Metric returns to normal — rule state resets
# ---------------------------------------------------------------------------


def test_metric_returns_to_normal_clears(engine, cpu_rule):
    """After alert fires, a sub-threshold value must reset triggered_since."""
    engine.add_rule(cpu_rule)

    # Trigger
    engine.check_metric("cpu_percent", 90)
    assert len(engine.get_active_alerts()) == 1

    # Return to normal
    engine.check_metric("cpu_percent", 70)

    rule = engine.rules["test_cpu_high"]
    assert rule.triggered_since is None


# ---------------------------------------------------------------------------
# 6. Cooldown prevents repeated alerts
# ---------------------------------------------------------------------------


def test_cooldown_prevents_repeated_alerts(engine, cpu_rule):
    """With cooldown active, a second breach should NOT create a new alert."""
    engine.cooldown_sec = 300  # large cooldown
    engine.group_window_sec = 300
    engine.add_rule(cpu_rule)

    engine.check_metric("cpu_percent", 90)
    engine.check_metric("cpu_percent", 95)

    # Only 1 active alert despite two breaches.
    assert len(engine.get_active_alerts()) == 1


# ---------------------------------------------------------------------------
# 7. Duration requirement delays alert
# ---------------------------------------------------------------------------


def test_duration_requirement(engine):
    """Rule with duration_sec > 0: first check starts timer, no alert yet."""
    rule = AlertRule(
        name="test_duration",
        metric="cpu_percent",
        threshold=80,
        comparison="greater_than",
        duration_sec=5,
        severity="warning",
    )
    engine.add_rule(rule)

    # First check — starts the timer but must NOT fire.
    engine.check_metric("cpu_percent", 90)
    assert engine.get_active_alerts() == []
    assert rule.triggered_since is not None

    # Simulate time passage beyond the duration requirement.
    rule.triggered_since = time.time() - 6

    engine.check_metric("cpu_percent", 90)
    assert len(engine.get_active_alerts()) == 1


# ---------------------------------------------------------------------------
# 8. Add and remove rule
# ---------------------------------------------------------------------------


def test_add_and_remove_rule(engine):
    """Adding a rule makes it evaluate; removing it stops evaluation."""
    rule = AlertRule(
        name="custom_rule",
        metric="disk_percent",
        threshold=90,
        comparison="greater_than",
        severity="error",
    )
    engine.add_rule(rule)
    assert "custom_rule" in engine.rules

    engine.check_metric("disk_percent", 95)
    assert len(engine.get_active_alerts()) == 1

    # Remove and send another breach — no new alert for this metric.
    engine.remove_rule("custom_rule")
    assert "custom_rule" not in engine.rules

    # Clear the old alert so we can verify no new one appears.
    for aid in list(engine.active_alerts):
        engine.clear_alert(aid)
    assert engine.get_active_alerts() == []

    engine.check_metric("disk_percent", 99)
    assert engine.get_active_alerts() == []


# ---------------------------------------------------------------------------
# 9. Acknowledge alert
# ---------------------------------------------------------------------------


def test_acknowledge_alert(engine, cpu_rule):
    """Acknowledging an alert sets acknowledged=True."""
    engine.add_rule(cpu_rule)
    engine.check_metric("cpu_percent", 90)

    alerts = engine.get_active_alerts()
    assert len(alerts) == 1
    alert_id = alerts[0]["alert_id"]

    engine.acknowledge_alert(alert_id)

    updated = engine.get_active_alerts()
    assert updated[0]["acknowledged"] is True


# ---------------------------------------------------------------------------
# 10. Battery level rule (future / config check)
# ---------------------------------------------------------------------------


def test_battery_level_rule(config_engine):
    """Verify whether a battery_level rule exists in alerts.yaml.

    The current config does not include a battery_level rule (W2 gap).
    This test documents that gap — when the rule is added it will pass
    the positive assertion instead.
    """
    battery_rules = [
        name
        for name in config_engine.rules
        if "battery" in name.lower()
    ]
    # Flip this assertion once the battery_level rule is added.
    if battery_rules:
        # Rule exists — validate it targets the right metric.
        rule = config_engine.rules[battery_rules[0]]
        assert rule.metric == "battery_level"
    else:
        pytest.skip(
            "battery_level rule not yet in alerts.yaml (W2 gap)"
        )


# ---------------------------------------------------------------------------
# Alert Engine Integration with Performance Endpoints
# ---------------------------------------------------------------------------


class TestAlertEngineEndpointIntegration:
    """Verify alert engine is fed from the enhanced performance summary endpoint.

    Bug: check_metric was only called from /api/performance (basic endpoint)
    but the frontend polls /api/performance/summary (enhanced endpoint),
    so alerts never fire during normal operation.
    """

    def test_enhanced_summary_endpoint_feeds_alert_engine(self):
        """GET /api/performance/summary must call check_metric for cpu and memory."""
        from unittest.mock import MagicMock, patch

        from fastapi.testclient import TestClient

        from backend.dashboard_server import app

        # Create a mock alert engine to track check_metric calls
        mock_alert_engine = MagicMock()

        # Create a mock performance monitor that returns realistic data
        mock_monitor = MagicMock()
        mock_monitor.get_summary.return_value = {
            "timestamp": 1709784000.0,
            "system": {
                "cpu_percent": 85.0,
                "memory_percent": 97.3,
                "memory_used_mb": 3800.0,
                "memory_available_mb": 100.0,
            },
            "nodes": {"total": 0, "top_cpu": [], "top_memory": []},
            "topics": {"total": 0, "active": 0},
        }

        with (
            patch(
                "backend.api_routes_performance.ENHANCED_SERVICES_AVAILABLE",
                True,
            ),
            patch(
                "backend.api_routes_performance.get_performance_monitor",
                return_value=mock_monitor,
            ),
            patch(
                "backend.api_routes_performance.get_alert_engine",
                return_value=mock_alert_engine,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/performance/summary")
            assert resp.status_code == 200

        # Alert engine must have been fed cpu and memory metrics
        metric_names = [
            call.args[0] for call in mock_alert_engine.check_metric.call_args_list
        ]
        assert "cpu_percent" in metric_names, (
            f"check_metric not called with cpu_percent, calls: {metric_names}"
        )
        assert "memory_percent" in metric_names, (
            f"check_metric not called with memory_percent, calls: {metric_names}"
        )

    def test_enhanced_summary_alert_failure_does_not_break_response(self):
        """Alert engine failure must not break the performance summary response."""
        from unittest.mock import MagicMock, patch

        from fastapi.testclient import TestClient

        from backend.dashboard_server import app

        mock_alert_engine = MagicMock()
        mock_alert_engine.check_metric.side_effect = RuntimeError("alert boom")

        mock_monitor = MagicMock()
        mock_monitor.get_summary.return_value = {
            "timestamp": 1709784000.0,
            "system": {
                "cpu_percent": 50.0,
                "memory_percent": 60.0,
            },
            "nodes": {"total": 0, "top_cpu": [], "top_memory": []},
            "topics": {"total": 0, "active": 0},
        }

        with (
            patch(
                "backend.api_routes_performance.ENHANCED_SERVICES_AVAILABLE",
                True,
            ),
            patch(
                "backend.api_routes_performance.get_performance_monitor",
                return_value=mock_monitor,
            ),
            patch(
                "backend.api_routes_performance.get_alert_engine",
                return_value=mock_alert_engine,
            ),
        ):
            client = TestClient(app)
            resp = client.get("/api/performance/summary")

        # Response must still succeed even if alert engine throws
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data
