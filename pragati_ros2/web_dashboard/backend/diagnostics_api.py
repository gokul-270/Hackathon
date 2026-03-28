"""Active fleet diagnostics router.

Provides GET /api/diagnostics/run — probes each configured entity's
connectivity and subsystem health on demand, returning structured results.

Capability: active-fleet-diagnostics (dashboard-reliability-hardening)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter

from .entity_manager import AGENT_PORT, get_entity_manager
from .entity_model import Entity

logger = logging.getLogger(__name__)

diagnostics_router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

# Timeout for agent HTTP probes (seconds)
_DIAG_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------
# Internal probe helpers
# ---------------------------------------------------------------------------


async def _probe_agent_http(entity: Entity) -> dict[str, Any]:
    """Probe the agent's /health endpoint. Returns a check result dict."""
    url = f"{entity.agent_base_url(AGENT_PORT)}/health"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_DIAG_TIMEOUT_S) as client:
            resp = await client.get(url)
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            return {
                "status": "pass",
                "latency_ms": latency_ms,
                "message": f"Agent responded in {latency_ms}ms",
                "fix_hint": None,
                "_agent_data": resp.json(),
            }
        else:
            return {
                "status": "fail",
                "latency_ms": latency_ms,
                "message": f"Agent returned HTTP {resp.status_code}",
                "fix_hint": "Check agent logs: journalctl -u pragati-agent --since '5 min ago'",
                "_agent_data": None,
            }
    except (httpx.ConnectTimeout, httpx.ReadTimeout):
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "fail",
            "latency_ms": latency_ms,
            "message": f"Connection timed out after {int(_DIAG_TIMEOUT_S)}s",
            "fix_hint": "Ensure the RPi is reachable and the agent is running: systemctl status pragati-agent",
            "_agent_data": None,
        }
    except (httpx.ConnectError, OSError) as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "fail",
            "latency_ms": latency_ms,
            "message": f"Connection refused: {exc}",
            "fix_hint": "Start the agent: systemctl start pragati-agent",
            "_agent_data": None,
        }


async def _probe_agent_diagnostics(entity: Entity) -> dict[str, Any]:
    """Probe the agent's /diagnostics/check endpoint for systemd_sudo."""
    url = f"{entity.agent_base_url(AGENT_PORT)}/diagnostics/check"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_DIAG_TIMEOUT_S) as client:
            resp = await client.get(url)
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "latency_ms": latency_ms, "data": resp.json()}
        return {"ok": False, "latency_ms": latency_ms, "data": None}
    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, OSError):
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "data": None}


def _skip_result(reason: str) -> dict[str, Any]:
    return {
        "status": "skip",
        "latency_ms": None,
        "message": reason,
        "fix_hint": None,
    }


def _build_ros2_result(agent_data: dict | None) -> dict[str, Any]:
    """Build ROS2 check result from cached agent health response."""
    if agent_data is None:
        return _skip_result("Skipped — agent unreachable")
    # The /health endpoint on the agent doesn't directly expose rclpy_available,
    # but /diagnostics/check does. If we have agent_data from /diagnostics/check,
    # use it; otherwise fall back to checking ros2_available from entity state.
    return _skip_result("ROS2 status not in health response")


def _build_systemd_result(diag_data: dict | None, diag_latency: int | None) -> dict[str, Any]:
    """Build Systemd check result from /diagnostics/check response."""
    if diag_data is None:
        return _skip_result("Skipped — agent unreachable")
    sudo_ok = diag_data.get("systemd_sudo", False)
    if sudo_ok:
        return {
            "status": "pass",
            "latency_ms": diag_latency,
            "message": "sudoers configured correctly",
            "fix_hint": None,
        }
    else:
        return {
            "status": "fail",
            "latency_ms": diag_latency,
            "message": "sudo systemctl requires password or is unavailable",
            "fix_hint": "Run ./sync.sh --provision --ip <IP> to fix sudoers",
        }


def _build_mqtt_result(entity: Entity) -> dict[str, Any]:
    """Build MQTT check result from cached entity health state."""
    mqtt_status = entity.health.get("mqtt", "unknown")
    if mqtt_status == "active":
        return {
            "status": "pass",
            "latency_ms": None,
            "message": "MQTT connection active",
            "fix_hint": None,
        }
    elif mqtt_status in ("disabled", "unknown"):
        return {
            "status": "skip",
            "latency_ms": None,
            "message": f"MQTT status: {mqtt_status}",
            "fix_hint": None,
        }
    else:
        return {
            "status": "fail",
            "latency_ms": None,
            "message": f"MQTT status: {mqtt_status}",
            "fix_hint": "Check MQTT broker: systemctl status mosquitto",
        }


def _strip_internal(check: dict[str, Any]) -> dict[str, Any]:
    """Remove internal keys (prefixed with _) from check result."""
    return {k: v for k, v in check.items() if not k.startswith("_")}


async def _run_entity_diagnostics(entity: Entity) -> dict[str, Any]:
    """Run all diagnostic checks for a single entity."""
    is_local = entity.source == "local"

    if is_local:
        # Local entity: skip agent HTTP and systemd, check MQTT from cache
        agent_http = _skip_result("Local entity")
        ros2_check = _skip_result("Local entity")
        systemd_check = _skip_result("Local entity")
        mqtt_check = _build_mqtt_result(entity)
        overall = _overall_status([agent_http, ros2_check, systemd_check, mqtt_check])
        return {
            "entity_id": entity.id,
            "entity_name": entity.name,
            "overall": overall,
            "checks": {
                "agent_http": _strip_internal(agent_http),
                "ros2": _strip_internal(ros2_check),
                "systemd": _strip_internal(systemd_check),
                "mqtt": _strip_internal(mqtt_check),
            },
        }

    # Remote entity: probe agent HTTP first
    agent_http = await _probe_agent_http(entity)
    agent_reachable = agent_http["status"] == "pass"

    if agent_reachable:
        # Get /diagnostics/check for systemd_sudo check
        diag_probe = await _probe_agent_diagnostics(entity)
        diag_data = diag_probe["data"] if diag_probe["ok"] else None
        diag_latency = diag_probe["latency_ms"]

        # ROS2: use ros2_available from entity manager cached state
        ros2_available = entity.ros2_available
        if ros2_available:
            ros2_check: dict[str, Any] = {
                "status": "pass",
                "latency_ms": None,
                "message": "ROS2 nodes visible",
                "fix_hint": None,
            }
        else:
            ros2_check = {
                "status": "fail",
                "latency_ms": None,
                "message": "ROS2 introspection unavailable",
                "fix_hint": "Check ROS2 is running: ros2 node list",
            }

        systemd_check = _build_systemd_result(diag_data, diag_latency)
    else:
        ros2_check = _skip_result("Skipped — agent unreachable")
        systemd_check = _skip_result("Skipped — agent unreachable")

    mqtt_check = _build_mqtt_result(entity)
    overall = _overall_status([agent_http, ros2_check, systemd_check, mqtt_check])

    return {
        "entity_id": entity.id,
        "entity_name": entity.name,
        "overall": overall,
        "checks": {
            "agent_http": _strip_internal(agent_http),
            "ros2": _strip_internal(ros2_check),
            "systemd": _strip_internal(systemd_check),
            "mqtt": _strip_internal(mqtt_check),
        },
    }


def _overall_status(checks: list[dict[str, Any]]) -> str:
    """Compute overall entity status: fail > pass > skip."""
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "fail"
    if "pass" in statuses:
        return "pass"
    return "skip"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@diagnostics_router.get("/run")
async def run_diagnostics() -> dict[str, Any]:
    """Run active diagnostics for all configured entities.

    Probes each entity sequentially (to avoid overwhelming the network).
    Returns per-entity, per-check results.
    """
    mgr = get_entity_manager()
    if mgr is None:
        return {"entities": [], "error": "EntityManager not initialized"}

    entities = mgr.get_all_entities()
    results = []
    for entity in entities:
        result = await _run_entity_diagnostics(entity)
        results.append(result)

    return {"entities": results}
