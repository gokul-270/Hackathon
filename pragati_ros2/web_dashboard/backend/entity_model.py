"""Entity data model — unified representation of a fleet member.

Each RPi in the Pragati fleet (arms, vehicle, local dev machine) is
represented as an Entity with system metrics, ROS2 state, and health status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def default_health_state() -> dict[str, Any]:
    """Return the default multi-layer health state for a new entity."""
    return {
        "network": "unknown",
        "network_latency_ms": None,
        "agent": "unknown",
        "agent_warnings": [],
        "mqtt": "unknown",
        "mqtt_arm_state": None,
        "mqtt_last_seen": None,
        "ros2": "unknown",
        "ros2_node_count": None,
        "composite": "unknown",
        "diagnostic": "Health check initializing",
    }


@dataclass
class Entity:
    """A single fleet member (arm RPi, vehicle RPi, or local machine).

    Attributes
    ----------
    id : str
        Unique identifier, e.g. "arm1", "vehicle", "local".
    name : str
        Human-readable name, e.g. "Arm 1 RPi".
    entity_type : str
        One of "arm" | "vehicle".
    source : str
        How the entity was discovered: "local" | "remote" | "discovered".
    ip : str | None
        IP address (None for local entity).
    poll_host : str | None
        Override host for health polling (e.g. 127.0.0.1 via portproxy).
        Falls back to ``ip`` when None.
    poll_port : int | None
        Override port for health polling. Falls back to AGENT_PORT when None.
    status : str
        Current health status: "online" | "offline" | "degraded" | "unknown".
    last_seen : datetime | None
        Last successful poll timestamp.
    system_metrics : dict
        CPU, memory, temperature, disk, uptime readings.
    ros2_available : bool
        Whether ROS2 introspection succeeded.
    ros2_state : dict | None
        ROS2 introspection data (node/topic/service counts).
    services : list[dict]
        Active services reported by the entity.
    errors : list[str]
        Recent error messages, capped at 10.
    metadata : dict
        Arbitrary metadata (SSH user, config source, etc.).
    """

    id: str
    name: str
    entity_type: str
    source: str
    ip: str | None = None
    port: int | None = None
    network_context: str | None = None
    member_id: str | None = None
    group_id: str | None = None
    slot: str | None = None
    membership_state: str = "approved"
    poll_host: str | None = None
    poll_port: int | None = None
    status: str = "unknown"
    health: dict[str, Any] = field(default_factory=default_health_state)
    last_seen: datetime | None = None
    system_metrics: dict = field(
        default_factory=lambda: {
            "cpu_percent": None,
            "memory_percent": None,
            "temperature_c": None,
            "disk_percent": None,
            "uptime_seconds": None,
            "motor_temperatures": None,
            "camera_temperature_c": None,
        }
    )
    ros2_available: bool = False
    ros2_state: dict | None = None
    services: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        had_default_health = self.health == default_health_state()
        if self.member_id is None:
            self.member_id = self.id
        if self.source in ("discovered", "mdns_discovered") and self.membership_state == "approved":
            self.membership_state = "candidate"
        self.health = self._normalized_health(self.health)
        if had_default_health and self.status != "unknown":
            self.health["composite"] = self.status
            self.health["diagnostic"] = self._diagnostic_for_composite(self.status)
        else:
            self._refresh_composite_status()
        self.status = self.health["composite"]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        health = dict(self.health)
        mqtt_last_seen = health.get("mqtt_last_seen")
        if isinstance(mqtt_last_seen, datetime):
            health["mqtt_last_seen"] = mqtt_last_seen.isoformat()
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "source": self.source,
            "ip": self.ip,
            "port": self.port,
            "network_context": self.network_context,
            "member_id": self.member_id,
            "group_id": self.group_id,
            "slot": self.slot,
            "membership_state": self.membership_state,
            "status": self.status,
            "health": health,
            "last_seen": (self.last_seen.isoformat() if self.last_seen else None),
            "system_metrics": self.system_metrics,
            "ros2_available": self.ros2_available,
            "ros2_state": self.ros2_state,
            "services": self.services,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    def add_error(self, error: str) -> None:
        """Add an error message, capping the list at 10 entries."""
        self.errors.append(error)
        if len(self.errors) > 10:
            self.errors = self.errors[-10:]

    def update_health(self, **updates: Any) -> None:
        """Update layer health fields and refresh the composite status."""
        self.health.update(updates)
        self._refresh_composite_status()
        self.status = self.health["composite"]

    def _refresh_composite_status(self) -> None:
        composite, diagnostic = self._derive_composite_status()
        self.health["composite"] = composite
        self.health["diagnostic"] = diagnostic

    def _derive_composite_status(self) -> tuple[str, str]:
        network = self.health.get("network", "unknown")
        agent = self.health.get("agent", "unknown")
        mqtt = self.health.get("mqtt", "unknown")
        ros2 = self.health.get("ros2", "unknown")

        if network == "unreachable":
            return "unreachable", "Host not reachable on network"
        if network == "degraded":
            return "degraded", "Network connectivity unstable"
        if network == "unknown":
            return "unknown", "Health check initializing"
        if agent == "down":
            if mqtt == "active":
                return "degraded", "Agent not responding but ARM application is active via MQTT"
            return "offline", "Agent not responding"
        if agent == "degraded":
            return "degraded", "Agent health degraded"
        if ros2 == "down":
            return "degraded", "ROS2 stack is down"
        if mqtt == "stale":
            if ros2 == "down":
                return "degraded", "ARM heartbeat stale, ROS2 down"
            return "degraded", "ARM heartbeat stale"
        if mqtt == "offline":
            return "degraded", "ARM application offline"
        if mqtt == "broker_down":
            if ros2 == "healthy":
                return "online", "MQTT broker unreachable (non-critical)"
            return "degraded", "MQTT broker unreachable, ROS2 stack is down"
        if mqtt == "disabled":
            if ros2 == "healthy":
                return "online", "MQTT not configured"
            return "degraded", "ROS2 stack is down"
        if network == "reachable" and agent == "alive" and mqtt == "active" and ros2 == "healthy":
            return "online", "All systems operational"
        return "unknown", "Health check initializing"

    @staticmethod
    def _diagnostic_for_composite(composite: str) -> str:
        mapping = {
            "online": "All systems operational",
            "degraded": "Entity health degraded",
            "offline": "Agent not responding",
            "unreachable": "Host not reachable on network",
            "unknown": "Health check initializing",
        }
        return mapping.get(composite, "Health check initializing")

    @staticmethod
    def _normalized_health(health: dict[str, Any] | None) -> dict[str, Any]:
        merged = default_health_state()
        if not health:
            return merged
        merged.update(health)
        merged["agent_warnings"] = list(merged.get("agent_warnings") or [])
        return merged

    def agent_base_url(self, agent_port: int) -> str:
        """Return the base URL for reaching this entity's agent.

        Uses ``poll_host``/``poll_port`` overrides when set (e.g. for
        Windows portproxy in WSL), falling back to ``ip``/``agent_port``.
        """
        host = self.poll_host or self.ip
        port = self.poll_port if self.poll_port is not None else agent_port
        return f"http://{host}:{port}"
