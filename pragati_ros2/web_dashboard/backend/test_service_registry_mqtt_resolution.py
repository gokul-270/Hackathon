"""Tests for MQTT broker host resolution helpers in service_registry."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.service_registry import _resolve_mqtt_broker_host


def test_explicit_mqtt_broker_host_takes_priority(tmp_path: Path):
    dashboard = tmp_path / "dashboard.yaml"
    entities = tmp_path / "entities.yaml"
    dashboard.write_text(yaml.dump({"mqtt": {"broker_host": "10.0.0.50", "broker_port": 1883}}))
    entities.write_text(
        yaml.dump(
            {
                "entities": [
                    {
                        "id": "vehicle",
                        "entity_type": "vehicle",
                        "ip": "10.0.0.99",
                        "group_id": "group-a",
                        "slot": "vehicle",
                        "membership_state": "approved",
                    }
                ]
            }
        )
    )

    assert _resolve_mqtt_broker_host(dashboard, entities) == "10.0.0.50"


def test_approved_vehicle_slot_is_used_when_broker_host_empty(tmp_path: Path):
    dashboard = tmp_path / "dashboard.yaml"
    entities = tmp_path / "entities.yaml"
    dashboard.write_text(yaml.dump({"mqtt": {"broker_host": "", "broker_port": 1883}}))
    entities.write_text(
        yaml.dump(
            {
                "entities": [
                    {
                        "id": "vehicle",
                        "entity_type": "vehicle",
                        "ip": "10.42.0.10",
                        "group_id": "machine-1",
                        "slot": "vehicle",
                        "membership_state": "approved",
                    },
                    {
                        "id": "vehicle_candidate",
                        "entity_type": "vehicle",
                        "ip": "10.42.0.11",
                        "group_id": "machine-2",
                        "slot": "vehicle",
                        "membership_state": "candidate",
                    },
                ]
            }
        )
    )

    assert _resolve_mqtt_broker_host(dashboard, entities) == "10.42.0.10"


def test_no_explicit_or_approved_vehicle_returns_empty(tmp_path: Path):
    dashboard = tmp_path / "dashboard.yaml"
    entities = tmp_path / "entities.yaml"
    dashboard.write_text(yaml.dump({"mqtt": {"broker_host": "", "broker_port": 1883}}))
    entities.write_text(yaml.dump({"entities": []}))

    assert _resolve_mqtt_broker_host(dashboard, entities) == ""
