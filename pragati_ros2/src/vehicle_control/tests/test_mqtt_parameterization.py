#!/usr/bin/env python3
"""
Tests for MQTT broker address parameterization.

Verifies that vehicle_control_node reads mqtt_broker_host and mqtt_broker_port
from YAML config instead of hardcoding "localhost":1883.
"""

import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestMqttConfigDefaults:
    """3.1 + 3.2: Default config includes MQTT broker host and port."""

    def test_default_config_has_mqtt_broker_host(self):
        """_get_default_config SHALL include mqtt_broker_host='localhost'."""
        with patch("integration.vehicle_control_node.rclpy"):
            from integration.vehicle_control_node import ROS2VehicleControlNode

            node = MagicMock(spec=ROS2VehicleControlNode)
            config = ROS2VehicleControlNode._get_default_config(node)
            assert config["mqtt_broker_host"] == "localhost"

    def test_default_config_has_mqtt_broker_port(self):
        """_get_default_config SHALL include mqtt_broker_port=1883."""
        with patch("integration.vehicle_control_node.rclpy"):
            from integration.vehicle_control_node import ROS2VehicleControlNode

            node = MagicMock(spec=ROS2VehicleControlNode)
            config = ROS2VehicleControlNode._get_default_config(node)
            assert config["mqtt_broker_port"] == 1883


class TestMqttConnectUsesConfig:
    """3.3: MQTT connect uses config values, not hardcoded."""

    @patch("integration.vehicle_control_node.mqtt")
    @patch("integration.vehicle_control_node.rclpy")
    def test_initialize_mqtt_uses_config_host_port(self, mock_rclpy, mock_mqtt):
        """_initialize_mqtt SHALL pass config host/port to client.connect()."""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock(spec=ROS2VehicleControlNode)
        node.config = {
            "mqtt_broker_host": "192.168.1.100",
            "mqtt_broker_port": 1884,
        }
        node.logger = MagicMock()
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client

        ROS2VehicleControlNode._initialize_mqtt(node)

        mock_client.connect.assert_called_once_with("192.168.1.100", 1884, keepalive=30)

    @patch("integration.vehicle_control_node.mqtt")
    @patch("integration.vehicle_control_node.rclpy")
    def test_selftest_reconnect_uses_config_host_port(self, mock_rclpy, mock_mqtt):
        """_mqtt_selftest_check reconnect SHALL use config host/port."""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock(spec=ROS2VehicleControlNode)
        node.config = {
            "mqtt_broker_host": "10.0.0.5",
            "mqtt_broker_port": 1885,
        }
        node.logger = MagicMock()
        node._mqtt_client = MagicMock()
        node._mqtt_lock = threading.Lock()
        node._mqtt_connected = True
        node._selftest_consecutive_failures = 1
        node._selftest_last_sent = 1.0
        node._selftest_last_received = 0.0  # Not echoed -> failure

        # Patch time.monotonic to return a value > last_sent + 5s timeout
        with patch("integration.vehicle_control_node.time") as mock_time:
            mock_time.monotonic.return_value = 20.0

            ROS2VehicleControlNode._mqtt_selftest_check(node)

        node._mqtt_client.connect.assert_called_once_with(
            "10.0.0.5", 1885, keepalive=30
        )
