"""Tests for MQTT config defaults used by dashboard startup."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_dashboard_mqtt_timeout_default_is_seven_point_five_seconds():
    config_path = Path(__file__).resolve().parent.parent / "config" / "dashboard.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert config["mqtt"]["heartbeat_timeout_s"] == 7.5
