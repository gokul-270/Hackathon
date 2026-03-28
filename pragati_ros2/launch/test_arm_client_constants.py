"""Regression tests for ARM MQTT heartbeat constants."""

from __future__ import annotations

from pathlib import Path
import re


def test_arm_client_heartbeat_publish_interval_is_five_seconds():
    arm_client = Path(__file__).resolve().parent / "ARM_client.py"
    content = arm_client.read_text()

    match = re.search(r"HEARTBEAT_PUBLISH_INTERVAL\s*=\s*([0-9.]+)", content)
    assert match is not None
    assert float(match.group(1)) == 5.0
