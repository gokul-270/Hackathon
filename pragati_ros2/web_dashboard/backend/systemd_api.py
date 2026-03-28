"""Systemd Service Management API (Tasks 5.1-5.2).

Provides endpoints to manage systemd services from the dashboard:
- GET /api/systemd/services — list status of allowed services
- POST /api/systemd/services/{name}/start|stop|restart|enable|disable
- GET /api/systemd/services/{name}/logs — fetch journal log lines

Only services in the allowlist can be managed. All operations are
executed via ``asyncio.create_subprocess_exec`` calling ``systemctl``
or ``journalctl``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

systemd_router = APIRouter(tags=["Systemd Services"])

# -----------------------------------------------------------------
# Allowlist — only these services can be managed
# -----------------------------------------------------------------

ALLOWED_SERVICES = [
    "pragati-dashboard",
    "pragati-agent",
    "arm_launch",
    "vehicle_launch",
    "pigpiod",
    "can-watchdog@can0",
    "field-monitor",
    "boot_timing.timer",
]

# -----------------------------------------------------------------
# Audit logger (module-level, injectable via setter)
# -----------------------------------------------------------------

_audit_logger: Optional[Any] = None


def set_audit_logger(al: Optional[Any]) -> None:
    """Set the module-level audit logger instance."""
    global _audit_logger  # noqa: PLW0603
    _audit_logger = al


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _validate_service_name(name: str) -> None:
    """Raise 403 if service name is not in the allowlist."""
    if name not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Service '{name}' is not in the allowed list. " f"Allowed: {ALLOWED_SERVICES}"
            ),
        )


def _unit_name(name: str) -> str:
    """Return the full systemd unit name.

    If *name* already contains a dot-suffix (e.g. ``boot_timing.timer``),
    return it unchanged.  Otherwise append ``.service``.
    """
    if "." in name:
        return name
    return f"{name}.service"


async def _run_systemctl(
    *args: str,
) -> tuple[str, str, int]:
    """Run a systemctl command and return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "sudo",
        "systemctl",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        proc.returncode,
    )


async def _get_service_status(name: str) -> Dict[str, Any]:
    """Query systemctl show for a single service's status."""
    stdout, _stderr, _rc = await _run_systemctl(
        "show",
        _unit_name(name),
        "--property=ActiveState,SubState,UnitFileState",
        "--no-pager",
    )

    # Parse key=value output
    props: Dict[str, str] = {}
    for line in stdout.strip().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            props[key.strip()] = value.strip()

    active_state = props.get("ActiveState", "unknown")
    sub_state = props.get("SubState", "unknown")
    unit_file_state = props.get("UnitFileState", "unknown")

    return {
        "name": name,
        "active_state": active_state,
        "sub_state": sub_state,
        "enabled": unit_file_state == "enabled",
    }


# Regex patterns for validating time parameters passed to journalctl
# ISO 8601 date/datetime: 2024-01-15 or 2024-01-15T10:30:00 (with optional tz)
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
# Relative time: "10 minutes ago", "1 hour ago", "2 days ago"
_RELATIVE_TIME_RE = re.compile(r"^\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago$")
# Named shortcuts accepted by journalctl
_NAMED_TIMES = {"yesterday", "today", "now", "tomorrow"}
# Shell metacharacters that must never appear in time params
_DANGEROUS_CHARS_RE = re.compile(r"[;|&`$\\\"'<>(){}!\n\r]")


def _validate_time_param(value: Optional[str]) -> Optional[str]:
    """Validate and return a time parameter for journalctl --since/--until.

    Accepts:
    - None (returns None)
    - ISO 8601 date or datetime strings
    - Relative strings like "10 minutes ago"
    - Named shortcuts: "yesterday", "today", "now", "tomorrow"

    Raises ValueError for invalid or dangerous input.
    """
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    # Reject shell metacharacters first
    if _DANGEROUS_CHARS_RE.search(stripped):
        raise ValueError(f"Invalid time parameter: {stripped!r}")

    # Check against known-good patterns
    if _ISO_DATETIME_RE.match(stripped):
        return stripped
    if _RELATIVE_TIME_RE.match(stripped):
        return stripped
    if stripped.lower() in _NAMED_TIMES:
        return stripped

    raise ValueError(
        f"Invalid time parameter: {stripped!r}. "
        "Use ISO format (2024-01-15T10:30:00), "
        "relative ('10 minutes ago'), or named ('yesterday')."
    )


def _log_action(action: str, params: Dict[str, Any], result: str) -> None:
    """Log an action via audit logger if available."""
    if _audit_logger is not None:
        try:
            _audit_logger.log(action, params, result)
        except Exception:
            logger.exception("Failed to write audit log")


# -----------------------------------------------------------------
# Routes: Service listing
# -----------------------------------------------------------------


@systemd_router.get("/api/systemd/services")
async def list_services() -> Dict[str, Any]:
    """List status of all allowed systemd services."""
    services: List[Dict[str, Any]] = []
    for name in ALLOWED_SERVICES:
        try:
            status = await _get_service_status(name)
            services.append(status)
        except Exception as exc:
            services.append(
                {
                    "name": name,
                    "active_state": "unknown",
                    "sub_state": "unknown",
                    "enabled": False,
                    "error": str(exc),
                }
            )
    return {"services": services}


# -----------------------------------------------------------------
# Routes: Service actions (start/stop/restart/enable/disable)
# -----------------------------------------------------------------


@systemd_router.post("/api/systemd/services/{name}/start")
async def start_service(name: str) -> Dict[str, Any]:
    """Start a systemd service."""
    _validate_service_name(name)

    stdout, stderr, rc = await _run_systemctl("start", f"{name}.service")

    success = rc == 0
    result = "success" if success else f"failed: {stderr.strip()}"
    _log_action(
        "systemd_start",
        {"service": name},
        result,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"systemctl start failed: {stderr.strip()}",
        )

    return {"success": True, "service": name, "action": "start"}


@systemd_router.post("/api/systemd/services/{name}/stop")
async def stop_service(name: str) -> Dict[str, Any]:
    """Stop a systemd service."""
    _validate_service_name(name)

    stdout, stderr, rc = await _run_systemctl("stop", f"{name}.service")

    success = rc == 0
    result = "success" if success else f"failed: {stderr.strip()}"
    _log_action(
        "systemd_stop",
        {"service": name},
        result,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"systemctl stop failed: {stderr.strip()}",
        )

    return {"success": True, "service": name, "action": "stop"}


@systemd_router.post("/api/systemd/services/{name}/restart")
async def restart_service(name: str) -> Dict[str, Any]:
    """Restart a systemd service."""
    _validate_service_name(name)

    stdout, stderr, rc = await _run_systemctl("restart", f"{name}.service")

    success = rc == 0
    result = "success" if success else f"failed: {stderr.strip()}"
    _log_action(
        "systemd_restart",
        {"service": name},
        result,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"systemctl restart failed: {stderr.strip()}",
        )

    return {"success": True, "service": name, "action": "restart"}


@systemd_router.post("/api/systemd/services/{name}/enable")
async def enable_service(name: str) -> Dict[str, Any]:
    """Enable auto-start for a systemd service."""
    _validate_service_name(name)

    stdout, stderr, rc = await _run_systemctl("enable", f"{name}.service")

    success = rc == 0
    result = "success" if success else f"failed: {stderr.strip()}"
    _log_action(
        "systemd_enable",
        {"service": name},
        result,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"systemctl enable failed: {stderr.strip()}",
        )

    return {"success": True, "service": name, "action": "enable"}


@systemd_router.post("/api/systemd/services/{name}/disable")
async def disable_service(name: str) -> Dict[str, Any]:
    """Disable auto-start for a systemd service."""
    _validate_service_name(name)

    stdout, stderr, rc = await _run_systemctl("disable", f"{name}.service")

    success = rc == 0
    result = "success" if success else f"failed: {stderr.strip()}"
    _log_action(
        "systemd_disable",
        {"service": name},
        result,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"systemctl disable failed: {stderr.strip()}",
        )

    return {"success": True, "service": name, "action": "disable"}


# -----------------------------------------------------------------
# Routes: Journal logs (Task 5.2)
# -----------------------------------------------------------------


@systemd_router.get("/api/systemd/services/{name}/logs")
async def get_service_logs(
    name: str,
    lines: int = Query(200, ge=1, le=10000),
    since: Optional[str] = Query(
        None,
        description="Start time (ISO format or relative like '10 minutes ago')",
    ),
    until: Optional[str] = Query(
        None,
        description="End time (ISO format or relative like '1 hour ago')",
    ),
) -> Dict[str, Any]:
    """Fetch recent journal log lines for a service."""
    _validate_service_name(name)

    # Validate time parameters
    try:
        validated_since = _validate_time_param(since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        validated_until = _validate_time_param(until)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Build journalctl command
    cmd: List[str] = [
        "journalctl",
        "-u",
        _unit_name(name),
        "--no-pager",
        "-n",
        str(lines),
    ]
    if validated_since:
        cmd.extend(["--since", validated_since])
    if validated_until:
        cmd.extend(["--until", validated_until])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    output = stdout.decode("utf-8", errors="replace")
    log_lines = [line for line in output.splitlines() if line.strip()]

    return {
        "service": name,
        "lines": log_lines,
        "count": len(log_lines),
    }
