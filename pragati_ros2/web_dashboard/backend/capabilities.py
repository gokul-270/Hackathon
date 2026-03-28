#!/usr/bin/env python3

"""
Enhanced Dashboard Capabilities Manager
======================================

Handles feature flags, configuration loading, and message envelope system
for LazyROS-style enhancements while maintaining backward compatibility.
"""

import os
import yaml
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from backend.version import get_version

logger = logging.getLogger(__name__)


class CapabilitiesManager:
    """Manages dashboard capabilities and configuration"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = (
            config_path or Path(__file__).parent.parent / "config" / "dashboard.yaml"
        )
        self.capabilities = {}
        self.server_config = {}
        self.last_loaded = 0
        self.load_config()

    def load_config(self):
        """Load configuration from YAML file with environment overrides"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f)

                self.capabilities = config.get("capabilities", {})
                self.server_config = config.get("server", {})

                # Apply environment overrides
                env_prefix = config.get(
                    "environment_override_prefix", "DASHBOARD_CAPABILITY_"
                )
                for key, default_value in self.capabilities.items():
                    env_key = f"{env_prefix}{key.upper()}"
                    if env_key in os.environ:
                        # Convert string to boolean
                        env_value = os.environ[env_key].lower() in (
                            "true",
                            "1",
                            "yes",
                            "on",
                        )
                        self.capabilities[key] = env_value
                        logger.info(f"Environment override: {key} = {env_value}")

                # Development overrides
                dev_config = config.get("development", {})
                if dev_config.get("enable_all_capabilities", False):
                    for key in self.capabilities:
                        self.capabilities[key] = True
                    logger.warning("Development mode: All capabilities enabled!")

                self.last_loaded = time.time()
                logger.info(
                    f"Loaded {len(self.capabilities)} capabilities from {self.config_path}"
                )

            else:
                logger.warning(
                    f"Config file not found at {self.config_path}, using defaults"
                )
                self._load_defaults()

        except Exception as e:
            logger.error(f"Error loading capabilities config: {e}")
            self._load_defaults()

    def _load_defaults(self):
        """Load default configuration if file is unavailable"""
        self.capabilities = {
            "topic_stats": False,
            "topic_echo": False,
            "logs_history": False,
            "logs_export": False,
            "message_envelope": False,
        }
        self.server_config = {
            "websocket_rate_hz": 1.0,
            "max_topic_echo_rate_hz": 100.0,
            "max_log_entries": 50000,
            "ros_command_timeout": 10.0,
            "ros_info_timeout": 2.0,
            "max_message_size_bytes": 1048576,
            "truncate_large_messages": True,
        }

    def is_enabled(self, capability: str) -> bool:
        """Check if a capability is enabled"""
        return self.capabilities.get(capability, False)

    def get_enabled_capabilities(self) -> List[str]:
        """Get list of enabled capabilities"""
        return [k for k, v in self.capabilities.items() if v]

    def get_server_config(self, key: str, default=None):
        """Get server configuration value"""
        return self.server_config.get(key, default)

    def reload_if_changed(self):
        """Reload configuration if file has changed"""
        try:
            if Path(self.config_path).exists():
                mtime = Path(self.config_path).stat().st_mtime
                if mtime > self.last_loaded:
                    logger.info("Configuration file changed, reloading...")
                    self.load_config()
        except Exception as e:
            logger.error(f"Error checking config file: {e}")


class MessageEnvelope:
    """Enhanced message envelope for WebSocket communications"""

    def __init__(self, capabilities_manager: CapabilitiesManager):
        self.capabilities_manager = capabilities_manager
        self.server_version = get_version()

    def create_envelope(self, msg_type: str, data: Any, **kwargs) -> Dict[str, Any]:
        """Create message envelope based on capabilities"""

        # Always include basic data for backward compatibility
        if not self.capabilities_manager.is_enabled("message_envelope"):
            # Legacy format - return data directly
            return data

        # Enhanced envelope format
        envelope = {
            "meta": {
                "timestamp_ns": int(time.time_ns()),
                "timestamp": datetime.now().isoformat(),
                "msg_type": msg_type,
                "server_version": self.server_version,
            },
            "data": data,
        }

        # Add optional metadata based on enabled capabilities
        if (
            self.capabilities_manager.is_enabled("topic_stats")
            and "topic_stats" in kwargs
        ):
            envelope["meta"]["topic_stats"] = kwargs["topic_stats"]

        if (
            self.capabilities_manager.is_enabled("perf_metrics")
            and "performance" in kwargs
        ):
            envelope["meta"]["performance"] = kwargs["performance"]

        # Add capability announcement for handshake messages
        if msg_type == "handshake":
            envelope["meta"][
                "capabilities"
            ] = self.capabilities_manager.get_enabled_capabilities()

        # Add size information for large messages
        data_size = len(str(data))
        if data_size > 1024:  # > 1KB
            envelope["meta"]["size_bytes"] = data_size

        return envelope

    def create_handshake(self) -> Dict[str, Any]:
        """Create handshake message with capability announcement"""
        return self.create_envelope(
            "handshake",
            {
                "status": "connected",
                "message": "Pragati ROS2 Dashboard ready",
                "features": {
                    "enhanced_echo": self.capabilities_manager.is_enabled("topic_echo"),
                    "advanced_logs": self.capabilities_manager.is_enabled(
                        "logs_history"
                    ),
                    "performance_metrics": self.capabilities_manager.is_enabled(
                        "perf_metrics"
                    ),
                },
            },
        )

    def create_error(
        self, error_msg: str, error_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create error message envelope"""
        error_data = {"error": error_msg, "timestamp": datetime.now().isoformat()}
        if error_code:
            error_data["error_code"] = error_code

        return self.create_envelope("error", error_data)


# Global capabilities manager instance
capabilities_manager = CapabilitiesManager()
message_envelope = MessageEnvelope(capabilities_manager)


def get_capabilities_manager() -> CapabilitiesManager:
    """Get global capabilities manager instance"""
    return capabilities_manager


def get_message_envelope() -> MessageEnvelope:
    """Get global message envelope instance"""
    return message_envelope


def reload_capabilities():
    """Reload capabilities configuration"""
    capabilities_manager.reload_if_changed()
