"""Shared JSON structured logging helpers for Pragati ROS2 nodes.

See docs/JSON_LOG_CONVENTIONS.md for field naming conventions.

Python mirror of common_utils/json_logging.hpp — same envelope schema,
same field names, same ARM_ID env-var lookup.
"""

import json
import os
import time
from typing import Optional

__all__ = [
    "epoch_ms_now",
    "json_envelope",
    "format_json_log",
    "emit_motor_alert",
    "emit_timing_event",
    "emit_health_summary",
]


def epoch_ms_now() -> int:
    """Return current UTC epoch time in milliseconds."""
    return time.time_ns() // 1_000_000


def json_envelope(
    event: str,
    node_name: str,
    arm_id: str = "",
) -> dict:
    """Build a dict with the standard Pragati log envelope fields.

    Parameters
    ----------
    event:
        Event name (e.g. ``"motor_alert"``, ``"detection_summary"``).
    node_name:
        ROS2 node name.
    arm_id:
        Arm identifier.  When empty, falls back to the ``ARM_ID``
        environment variable (default ``"arm_unknown"``).
    """
    return {
        "event": event,
        "ts": epoch_ms_now(),
        "node": node_name,
        "arm_id": arm_id if arm_id else os.environ.get("ARM_ID", "arm_unknown"),
    }


def format_json_log(
    event: str,
    node_name: str,
    arm_id: str = "",
    **kwargs: object,
) -> str:
    """Return a compact JSON string with envelope + arbitrary fields.

    Extra keyword arguments are merged into the envelope dict before
    serialisation, making this the easiest one-liner for ad-hoc structured
    logs::

        msg = format_json_log("pick_cycle", self.get_name(), bolls=3)
    """
    envelope = json_envelope(event, node_name, arm_id)
    envelope.update(kwargs)
    return json.dumps(envelope, separators=(",", ":"))


def emit_motor_alert(
    node_name: str,
    motor_id: int,
    joint_id: int,
    alert: str,
    details: Optional[dict] = None,
    arm_id: str = "",
) -> str:
    """Build and return a compact JSON ``motor_alert`` log line.

    Parameters
    ----------
    node_name:
        ROS2 node name.
    motor_id:
        CAN motor identifier.
    joint_id:
        Logical joint number.
    alert:
        Short alert description (e.g. ``"over_temp"``).
    details:
        Optional dict of extra fields merged into the log line.
    arm_id:
        Arm identifier (env-var fallback when empty).
    """
    envelope = json_envelope("motor_alert", node_name, arm_id)
    envelope["motor_id"] = motor_id
    envelope["joint_id"] = joint_id
    envelope["alert"] = alert
    if details:
        envelope.update(details)
    return json.dumps(envelope, separators=(",", ":"))


def emit_timing_event(
    node_name: str,
    operation: str,
    duration_ms: float,
    arm_id: str = "",
) -> str:
    """Build and return a compact JSON ``timing`` log line.

    Parameters
    ----------
    node_name:
        ROS2 node name.
    operation:
        Name of the timed operation (e.g. ``"inference"``, ``"ik_solve"``).
    duration_ms:
        Elapsed wall-clock time in milliseconds.
    arm_id:
        Arm identifier (env-var fallback when empty).
    """
    envelope = json_envelope("timing", node_name, arm_id)
    envelope["operation"] = operation
    envelope["duration_ms"] = duration_ms
    return json.dumps(envelope, separators=(",", ":"))


def emit_health_summary(
    node_name: str,
    component: str,
    status: str,
    details: Optional[dict] = None,
    arm_id: str = "",
) -> str:
    """Build and return a compact JSON ``health_summary`` log line.

    Parameters
    ----------
    node_name:
        ROS2 node name.
    component:
        Subsystem being reported (e.g. ``"can_bus"``, ``"camera"``).
    status:
        Health status string (e.g. ``"ok"``, ``"degraded"``, ``"error"``).
    details:
        Optional dict of extra fields merged into the log line.
    arm_id:
        Arm identifier (env-var fallback when empty).
    """
    envelope = json_envelope("health_summary", node_name, arm_id)
    envelope["component"] = component
    envelope["status"] = status
    if details:
        envelope.update(details)
    return json.dumps(envelope, separators=(",", ":"))
