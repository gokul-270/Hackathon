"""Pragati RPi Agent — lightweight FastAPI app for entity monitoring.

Runs on each Raspberry Pi to expose health, ROS2 introspection,
systemd management, and log streaming over HTTP.

Usage:
    python3 -m rpi_agent.agent --port 8091
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import re
import signal
import socket
import subprocess
import threading
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from urllib.request import urlopen
from urllib.error import URLError

import psutil
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("pragati.agent")

AGENT_VERSION = "0.1.0"
_MAX_SSE_CONNECTIONS = 10


class _Counter:
    """Thread-safe-ish integer counter for SSE tracking."""

    def __init__(self):
        self._value = 0

    def get(self) -> int:
        return self._value

    def increment(self):
        self._value += 1

    def decrement(self):
        self._value = max(0, self._value - 1)

    def reset(self, v: int):
        self._value = v


_sse_connection_count = _Counter()

# ---------------------------------------------------------------------------
# mDNS helpers (lazy-loaded zeroconf)
# ---------------------------------------------------------------------------
_zc_instance = None
_zc_info = None

try:
    from zeroconf import ServiceInfo, Zeroconf
except ImportError:  # pragma: no cover
    Zeroconf = None  # type: ignore[assignment,misc]
    ServiceInfo = None  # type: ignore[assignment,misc]


def register_mdns() -> None:
    global _zc_instance, _zc_info
    if Zeroconf is None:
        logger.warning("zeroconf not installed — mDNS disabled")
        return
    entity_id = os.environ.get("PRAGATI_ENTITY_ID", socket.gethostname())
    entity_type = os.environ.get("PRAGATI_ENTITY_TYPE", "arm")
    port = int(os.environ.get("PRAGATI_AGENT_PORT", "8091"))
    _zc_info = ServiceInfo(
        "_pragati-agent._tcp.local.",
        f"{entity_id}._pragati-agent._tcp.local.",
        addresses=[socket.inet_aton("0.0.0.0")],
        port=port,
        properties={
            "entity_id": entity_id,
            "entity_type": entity_type,
            "agent_version": AGENT_VERSION,
        },
    )
    _zc_instance = Zeroconf()
    _zc_instance.register_service(_zc_info)
    logger.info("mDNS registered: %s", entity_id)


def unregister_mdns() -> None:
    global _zc_instance, _zc_info
    if _zc_instance and _zc_info:
        _zc_instance.unregister_service(_zc_info)
        _zc_instance.close()
        _zc_instance = None
        _zc_info = None
        logger.info("mDNS unregistered")


# ---------------------------------------------------------------------------
# Health helpers
# ---------------------------------------------------------------------------


def _collect_health() -> dict:
    cpu = psutil.cpu_percent(interval=0)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    uptime = time.time() - psutil.boot_time()

    temps = psutil.sensors_temperatures()
    temp_c: Optional[float] = None
    if temps:
        first_sensor = next(iter(temps.values()))
        if first_sensor:
            temp_c = first_sensor[0].current

    warnings = []
    if temp_c is not None and temp_c > 80.0:
        warnings.append("thermal_throttling")

    return {
        "cpu_percent": cpu,
        "memory_percent": mem,
        "temperature_c": temp_c,
        "disk_percent": disk,
        "uptime_seconds": uptime,
        "warnings": warnings,
        "hostname": platform.node(),
    }


# ---------------------------------------------------------------------------
# Server-side caches (process/stats: 3s, aggregate status: 5s)
# ---------------------------------------------------------------------------

_SYSTEM_STATS_CACHE_TTL = 3.0
_STATUS_CACHE_TTL = 10.0  # Cache status for 10s to reduce subprocess overhead on RPi

_process_cache: dict = {"data": [], "timestamp": 0.0}
_stats_cache: dict = {"data": {}, "timestamp": 0.0}
_status_cache: dict = {"data": None, "timestamp": 0.0}
_status_lock: asyncio.Lock | None = None  # Initialized lazily inside event loop

# Exponential backoff for ros2 CLI failures — prevents endless CPU-burning
# subprocess calls when DDS discovery is stuck.
_ROS2_BACKOFF_MAX = 15.0  # Max seconds to wait between retries (was 120)
_ros2_backoff: dict = {
    "consecutive_failures": 0,
    "backoff_until": 0.0,  # time.time() when we can retry
}

# ---------------------------------------------------------------------------
# Local dashboard query — preferred source for ROS2 introspection
# ---------------------------------------------------------------------------
_DASHBOARD_PORT = 8090
_DASHBOARD_QUERY_TIMEOUT = 2.0  # seconds; fast fail if dashboard is down


def _parse_node_string(full_name: str) -> dict:
    """Convert a full node name like '/arm1/motion_controller' to a dict.

    Returns ``{"name": "motion_controller", "namespace": "/arm1",
    "lifecycle_state": None}``.  For root-namespace nodes like
    ``"/motion_planner"`` the namespace is ``"/"``.
    """
    full_name = full_name.strip()
    if not full_name:
        return {"name": "", "namespace": "/", "lifecycle_state": None}
    parts = full_name.rsplit("/", 1)
    if len(parts) == 2 and parts[0]:
        ns = parts[0]  # e.g. "/arm1"
        name = parts[1]
    else:
        ns = "/"
        name = parts[-1].lstrip("/")
    return {"name": name, "namespace": ns, "lifecycle_state": None}


def _query_local_dashboard(endpoint: str) -> list[dict] | None:
    """Query the co-located dashboard REST API for ROS2 data.

    The dashboard's ``entity_proxy.py`` returns responses shaped like::

        {"entity_id": "local", "source": "local",
         "data": {"nodes": ["/arm1/motor_control", ...]}}

    where ``data`` is a dict keyed by the endpoint name (``nodes``,
    ``topics``, or ``services``) containing a list of **strings** (full
    names).  This function extracts the inner list and converts strings
    to the dict format that ``_ros2_node_list`` / ``_ros2_topic_list`` /
    ``_ros2_service_list`` callers expect.

    Returns the converted list on success, or ``None`` on any failure
    (connection refused, timeout, bad JSON, missing key).
    """
    url = f"http://localhost:{_DASHBOARD_PORT}/api/entities/local/ros2/{endpoint}"
    try:
        with urlopen(url, timeout=_DASHBOARD_QUERY_TIMEOUT) as resp:
            body = json.loads(resp.read())
            data = body.get("data")
            if data is None:
                logger.debug("Dashboard response for %s missing 'data' key", endpoint)
                return None

            # data is a dict like {"nodes": [...]} — extract the inner list
            if isinstance(data, dict):
                items = data.get(endpoint)
                if items is None:
                    logger.debug("Dashboard data for %s missing '%s' key", endpoint, endpoint)
                    return None
            else:
                # Unexpected format — treat as raw list (future-proofing)
                items = data

            if not isinstance(items, list):
                logger.debug("Dashboard data[%s] is not a list: %s", endpoint, type(items))
                return None

            # Convert string arrays to the dict format callers expect.
            # Dashboard may return strings (legacy) or dicts (modern with type info).
            if endpoint == "nodes":
                return [_parse_node_string(n) if isinstance(n, str) else n for n in items]
            elif endpoint == "topics":
                return [
                    (
                        t
                        if isinstance(t, dict)
                        else {
                            "name": t,
                            "type": None,
                            "publisher_count": None,
                            "subscriber_count": None,
                        }
                    )
                    for t in items
                ]
            elif endpoint == "services":
                return [s if isinstance(s, dict) else {"name": s, "type": None} for s in items]
            else:
                logger.debug("Unknown endpoint '%s', returning raw items", endpoint)
                return items
    except Exception:
        # Any failure (connection refused, timeout, bad JSON, etc.)
        # is non-fatal — we fall back to CLI.
        logger.debug(
            "Local dashboard query for %s failed, will fall back to CLI",
            endpoint,
            exc_info=True,
        )
        return None


def _collect_processes() -> list[dict]:
    """Return top 15 processes by CPU%, with 3s cache."""
    now = time.time()
    if now - _process_cache["timestamp"] < _SYSTEM_STATS_CACHE_TTL:
        return _process_cache["data"]

    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
        try:
            info = proc.info
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "",
                    "cpu_percent": info["cpu_percent"] or 0.0,
                    "memory_mb": round(
                        ((info["memory_info"].rss / (1024 * 1024)) if info["memory_info"] else 0.0),
                        1,
                    ),
                    "status": info["status"] or "unknown",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    procs.sort(key=lambda p: p["cpu_percent"], reverse=True)
    result = procs[:15]
    _process_cache["data"] = result
    _process_cache["timestamp"] = now
    return result


def _collect_system_stats() -> dict:
    """Return aggregate system stats, with 3s cache."""
    now = time.time()
    if now - _stats_cache["timestamp"] < _SYSTEM_STATS_CACHE_TTL:
        return _stats_cache["data"]

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    temps = psutil.sensors_temperatures()
    cpu_temp: Optional[float] = None
    if temps:
        first_sensor = next(iter(temps.values()))
        if first_sensor:
            cpu_temp = first_sensor[0].current

    result = {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_used": mem.used,
        "memory_total": mem.total,
        "disk_used": disk.used,
        "disk_total": disk.total,
        "cpu_temp": cpu_temp,
    }
    _stats_cache["data"] = result
    _stats_cache["timestamp"] = now
    return result


# ---------------------------------------------------------------------------
# ROS2 helpers
# ---------------------------------------------------------------------------
_ROS2_TIMEOUT = 5  # seconds; allow headroom for DDS cold start on RPi4
_ROS2_FIRST_CALL_TIMEOUT = 10  # extra time for very first call after agent startup
_ros2_first_call_done = False  # tracks whether first successful call has completed


def _run_ros2_cmd(
    cmd: list[str],
    timeout: int | float = _ROS2_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run a ROS2 CLI command with reliable timeout and process cleanup.

    Uses Popen with a new session so the entire process group can be
    killed via SIGKILL on timeout — prevents zombie ``ros2`` processes
    that ignore SIGTERM (common with DDS daemon hangs).
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the entire process group (ros2 may spawn children)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.kill()  # belt-and-suspenders
        proc.wait()
        raise subprocess.TimeoutExpired(cmd, timeout)

    if proc.returncode != 0:
        raise RuntimeError(f"ros2 CLI failed (rc={proc.returncode}): {stderr.strip()}")
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Lazy rclpy init (for topic echo / service call)
# ---------------------------------------------------------------------------
_rclpy_node = None
_rclpy_lock = threading.Lock()
_rclpy_available = False
_rclpy_last_activity: float = 0.0
_executor = None
_spin_thread = None
_rclpy_subscription_count = 0
_rclpy_teardown_task = None
_RCLPY_TEARDOWN_SECONDS = 60
_topic_publishers: dict = {}

# ---------------------------------------------------------------------------
# Diagnostic subscription state
# ---------------------------------------------------------------------------

# Cached motor temperatures: dict keyed by joint name
_motor_temperatures: Optional[dict] = None
_camera_temperature_c: Optional[float] = None
_diagnostic_subscriptions_registered = False


def _spin_rclpy_executor(executor) -> None:
    try:
        executor.spin()
    except Exception:
        logger.exception("rclpy executor spin crashed")
        with _rclpy_lock:
            global _rclpy_available
            _rclpy_available = False


def _ensure_rclpy():
    """Lazily init rclpy and create a shared node. Returns node or None."""
    global _rclpy_node, _rclpy_available, _rclpy_last_activity, _executor, _spin_thread
    with _rclpy_lock:
        current_time = time.time()
        _rclpy_last_activity = current_time
        if _rclpy_node is not None and _rclpy_available:
            return _rclpy_node
        if _rclpy_node is not None and not _rclpy_available:
            if _executor is not None:
                _executor.shutdown()
            if _spin_thread is not None:
                _spin_thread.join(timeout=5)
            _rclpy_node.destroy_node()
            try:
                rclpy = __import__("rclpy")
                rclpy.try_shutdown()
            except Exception:
                logger.exception("rclpy shutdown failed during re-init")
            _rclpy_node = None
            _executor = None
            _spin_thread = None
        try:
            rclpy = __import__("rclpy")
            if not rclpy.ok():
                rclpy.init()
            _rclpy_node = rclpy.create_node("pragati_agent_node")
            _executor = rclpy.executors.SingleThreadedExecutor()
            _executor.add_node(_rclpy_node)
            _spin_thread = threading.Thread(
                target=lambda: _spin_rclpy_executor(_executor),
                name="pragati-agent-rclpy-spin",
                daemon=True,
            )
            _spin_thread.start()
            _rclpy_available = True
            _rclpy_last_activity = current_time
            return _rclpy_node
        except Exception:
            _rclpy_available = False
            _executor = None
            _spin_thread = None
            return None


def register_subscription(topic, msg_type, callback, qos):
    global _rclpy_subscription_count
    node = _ensure_rclpy()
    if node is None:
        return None

    with _rclpy_lock:
        subscription = node.create_subscription(msg_type, topic, callback, qos)
        _rclpy_subscription_count += 1
        return subscription


def unregister_subscription(subscription) -> None:
    global _rclpy_subscription_count
    with _rclpy_lock:
        if _rclpy_node is None or subscription is None:
            return
        _rclpy_node.destroy_subscription(subscription)
        _rclpy_subscription_count = max(0, _rclpy_subscription_count - 1)


def _on_motor_diagnostics(msg) -> None:
    """Callback for /motor_control/motor_diagnostics topic; updates _motor_temperatures."""
    global _motor_temperatures
    temps = {}
    for status in msg.status:
        # Use hardware_id (e.g. "joint5") as key — matches production.yaml joint names.
        # Falls back to status.name (e.g. "motor/joint5") if hardware_id is empty.
        key = (status.hardware_id or status.name or "").strip()
        if not key:
            continue
        for kv in status.values:
            if kv.key == "temperature_c":
                try:
                    temps[key] = float(kv.value)
                except (ValueError, TypeError):
                    pass
    if temps:
        _motor_temperatures = temps


def _on_camera_diagnostics(msg) -> None:
    """Callback for /diagnostics topic; updates _camera_temperature_c."""
    global _camera_temperature_c
    for status in msg.status:
        name_lower = (status.name or "").lower()
        if "oak-d" in name_lower or "camera" in name_lower:
            for kv in status.values:
                if kv.key == "Temperature (C)":
                    try:
                        _camera_temperature_c = float(kv.value)
                    except (ValueError, TypeError):
                        pass
            break  # Only first matching entry


def _ensure_diagnostic_subscriptions() -> None:
    """Lazily register diagnostic subscriptions once rclpy is available."""
    global _diagnostic_subscriptions_registered
    if _diagnostic_subscriptions_registered:
        return
    try:
        from diagnostic_msgs.msg import DiagnosticArray
    except ImportError:
        return
    motor_sub = register_subscription(
        "/motor_control/motor_diagnostics", DiagnosticArray, _on_motor_diagnostics, 10
    )
    camera_sub = register_subscription("/diagnostics", DiagnosticArray, _on_camera_diagnostics, 10)
    if motor_sub is not None or camera_sub is not None:
        _diagnostic_subscriptions_registered = True


def _teardown_rclpy() -> None:
    global _rclpy_node
    global _rclpy_available
    global _executor
    global _spin_thread
    global _rclpy_subscription_count

    with _rclpy_lock:
        if _rclpy_node is None and _executor is None and _spin_thread is None:
            _rclpy_available = False
            _rclpy_subscription_count = 0
            return

        executor = _executor
        spin_thread = _spin_thread
        node = _rclpy_node

        _executor = None
        _spin_thread = None
        _rclpy_node = None
        _rclpy_available = False
        _rclpy_subscription_count = 0

    if executor is not None:
        executor.shutdown()
    if spin_thread is not None:
        spin_thread.join(timeout=5)
    if node is not None:
        node.destroy_node()

    try:
        rclpy = __import__("rclpy")
    except Exception:
        return

    try:
        rclpy.try_shutdown()
    except Exception:
        logger.exception("rclpy shutdown failed")


async def _rclpy_teardown_checker() -> None:
    while True:
        now = time.time()
        should_teardown = False
        acquired = await asyncio.to_thread(_rclpy_lock.acquire)
        try:
            should_teardown = (
                _rclpy_node is not None
                and _rclpy_subscription_count == 0
                and (now - _rclpy_last_activity) > _RCLPY_TEARDOWN_SECONDS
            )
        finally:
            if acquired:
                _rclpy_lock.release()
        if should_teardown:
            _teardown_rclpy()
        await asyncio.sleep(30)


async def _cancel_rclpy_teardown_task() -> None:
    global _rclpy_teardown_task

    task = _rclpy_teardown_task
    _rclpy_teardown_task = None
    if task is None:
        return

    task.cancel()
    if hasattr(task, "__await__"):
        with suppress(asyncio.CancelledError):
            await task


async def _create_echo_generator(topic_name: str, hz: int) -> AsyncGenerator[str, None]:
    """Generate SSE events from a ROS2 topic via async subprocess.

    Uses ``asyncio.create_subprocess_exec`` so that reading stdout never
    blocks the event loop (the previous ``subprocess.Popen`` with synchronous
    ``for line in proc.stdout`` would stall *all* concurrent requests).

    The ``--once`` flag is intentionally omitted: this is a continuous SSE
    stream that should keep echoing until the client disconnects.
    """
    node = _ensure_rclpy()
    if node is None:
        return

    min_interval = 1.0 / hz if hz > 0 else 0.1
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ros2",
            "topic",
            "echo",
            topic_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        last_emit = 0.0
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break  # EOF — process exited
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if line:
                now = time.time()
                if now - last_emit < min_interval:
                    continue
                yield f"data: {json.dumps({'data': line})}\n\n"
                last_emit = now
    except (asyncio.CancelledError, GeneratorExit):
        pass
    except Exception:
        pass
    finally:
        global _rclpy_last_activity
        _rclpy_last_activity = time.time()
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass


def _ros2_node_info(node_name: str) -> dict:
    """Parse `ros2 node info` output into structured dict."""
    result = subprocess.run(
        ["ros2", "node", "info", node_name],
        capture_output=True,
        text=True,
        timeout=_ROS2_TIMEOUT,
    )
    if result.returncode != 0:
        # Distinguish not-found from general failure
        stderr = result.stderr or ""
        if "Unable to find node" in stderr or "unknown node" in stderr.lower():
            return None  # type: ignore[return-value]
        raise RuntimeError("ros2 CLI failed")

    sections: dict[str, list[dict]] = {
        "publishers": [],
        "subscribers": [],
        "service_servers": [],
        "service_clients": [],
    }
    current_section = None
    section_map = {
        "Publishers:": "publishers",
        "Subscribers:": "subscribers",
        "Service Servers:": "service_servers",
        "Service Clients:": "service_clients",
    }

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped in section_map:
            current_section = section_map[stripped]
            continue
        if current_section and ":" in stripped and stripped[0] == "/":
            parts = stripped.split(":", 1)
            topic = parts[0].strip()
            msg_type = parts[1].strip() if len(parts) > 1 else ""
            sections[current_section].append({"topic": topic, "type": msg_type})
        elif stripped and not stripped.startswith("/"):
            # Non-topic line (section header without ":") resets section
            if stripped.rstrip(":") not in (
                "Publishers",
                "Subscribers",
                "Service Servers",
                "Service Clients",
            ):
                current_section = None

    # Extract short name from node_name (last segment)
    short_name = node_name.rsplit("/", 1)[-1]
    return {
        "name": short_name,
        "publishers": sections["publishers"],
        "subscribers": sections["subscribers"],
        "service_servers": sections["service_servers"],
        "service_clients": sections["service_clients"],
    }


# Param operations need longer timeout than node/topic listing.
# ros2 param dump can take 10-20s on RPi4 with DDS cold start.
_ROS2_PARAM_TIMEOUT = max(_ROS2_TIMEOUT * 4, 20)


def _ros2_param_list(node_name: str) -> list[str]:
    """Get parameter names for a node."""
    result = subprocess.run(
        ["ros2", "param", "list", "--node", node_name, "--timeout", "10"],
        capture_output=True,
        text=True,
        timeout=_ROS2_PARAM_TIMEOUT,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]


def _ros2_param_get(node_name: str, param_name: str) -> dict:
    """Get a parameter value and infer its type."""
    result = subprocess.run(
        ["ros2", "param", "get", node_name, param_name],
        capture_output=True,
        text=True,
        timeout=_ROS2_PARAM_TIMEOUT,
    )
    if result.returncode != 0:
        return {"name": param_name, "type": "unknown", "value": None}

    output = result.stdout.strip()
    # Parse output format: "Type value is: X"
    ptype = "string"
    value: object = output
    if output.startswith("Integer value is:"):
        ptype = "integer"
        value = int(output.split(":", 1)[1].strip())
    elif output.startswith("Double value is:"):
        ptype = "double"
        value = float(output.split(":", 1)[1].strip())
    elif output.startswith("Boolean value is:"):
        ptype = "boolean"
        value = output.split(":", 1)[1].strip().lower() == "true"
    elif output.startswith("String value is:"):
        ptype = "string"
        value = output.split(":", 1)[1].strip()
    else:
        ptype = "string"
        value = output

    return {"name": param_name, "type": ptype, "value": value}


def _ros2_param_dump(node_name: str) -> list[dict]:
    """Dump all parameters for a node using `ros2 param dump`.

    Much faster than calling `ros2 param get` per parameter (1 subprocess
    vs N).  Parses the YAML output into [{name, type, value}, ...].
    Falls back to the slower param-list + param-get approach on failure.
    """
    try:
        result = subprocess.run(
            ["ros2", "param", "dump", node_name, "--timeout", "10"],
            capture_output=True,
            text=True,
            timeout=_ROS2_PARAM_TIMEOUT,
        )
        if result.returncode != 0:
            # Fallback to legacy approach
            names = _ros2_param_list(node_name)
            return [_ros2_param_get(node_name, n) for n in names]

        # Parse YAML output.  `ros2 param dump --print` produces:
        #   <node_short_name>:
        #     ros__parameters:
        #       param_name: value
        #       nested.param: value
        import yaml as _yaml

        data = _yaml.safe_load(result.stdout)
        if not isinstance(data, dict):
            return []

        # Navigate into the first key (node name) then ros__parameters
        for _node_key, node_val in data.items():
            if isinstance(node_val, dict):
                ros_params = node_val.get("ros__parameters", node_val)
                break
        else:
            return []

        params = []
        for pname, pvalue in ros_params.items():
            if isinstance(pvalue, bool):
                ptype = "boolean"
            elif isinstance(pvalue, int):
                ptype = "integer"
            elif isinstance(pvalue, float):
                ptype = "double"
            elif isinstance(pvalue, str):
                ptype = "string"
            elif isinstance(pvalue, list):
                ptype = "array"
            else:
                ptype = "unknown"
            params.append({"name": pname, "type": ptype, "value": pvalue})
        return params

    except ImportError:
        # PyYAML not available — fallback
        names = _ros2_param_list(node_name)
        return [_ros2_param_get(node_name, n) for n in names]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------


def _get_log_dirs() -> list[str]:
    """Return log directories to scan."""
    env_dirs = os.environ.get("PRAGATI_LOG_DIRS", "")
    if env_dirs:
        return [d.strip() for d in env_dirs.split(":") if d.strip()]
    return [
        os.path.expanduser("~/pragati_ros2/log/"),
        os.path.expanduser("~/.ros/log/"),
    ]


def _list_log_files() -> list[dict]:
    """Scan log directories and return file metadata."""
    files = []
    for log_dir in _get_log_dirs():
        if not os.path.isdir(log_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(log_dir):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, log_dir)
                # Prevent path traversal in output
                if ".." in rel_path:
                    continue
                try:
                    stat = os.stat(full_path)
                    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                    files.append(
                        {
                            "name": fname,
                            "path": rel_path,
                            "size_bytes": stat.st_size,
                            "modified": modified,
                        }
                    )
                except OSError:
                    continue

    # Add journald special entry
    files.append(
        {
            "name": "System Journal (pragati-*)",
            "path": "__journald__",
            "size_bytes": None,
            "modified": None,
        }
    )
    return files


def _resolve_log_path(log_name: str) -> Optional[str]:
    """Resolve a log file name to its absolute path, or None."""
    # Block path traversal
    if ".." in log_name or log_name.startswith("/"):
        return None
    for log_dir in _get_log_dirs():
        if not os.path.isdir(log_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(log_dir):
            for fname in filenames:
                rel_path = os.path.relpath(os.path.join(dirpath, fname), log_dir)
                if rel_path == log_name or fname == log_name:
                    full = os.path.join(dirpath, fname)
                    # Double-check no traversal
                    if ".." in os.path.relpath(full, log_dir):
                        return None
                    return full
    return None


# ---------------------------------------------------------------------------
# Pydantic models for request bodies
# ---------------------------------------------------------------------------


class ParamSetItem(BaseModel):
    name: str
    value: str


class ParamSetRequest(BaseModel):
    params: list[ParamSetItem]


class ServiceCallRequest(BaseModel):
    type: str
    request: dict


class SystemControlRequest(BaseModel):
    token: str


# -- Motor / Rosbag request models ----------------------------------------


class MotorCommandRequest(BaseModel):
    motor_id: int | None = None
    mode: str
    params: dict = {}


class PIDWriteRequest(BaseModel):
    motor_id: int
    angle_kp: int
    angle_ki: int
    speed_kp: int
    speed_ki: int
    current_kp: int
    current_ki: int


class CalibrateZeroRequest(BaseModel):
    motor_id: int


class MotorLimitsWriteRequest(BaseModel):
    motor_id: int
    min_angle_deg: float
    max_angle_deg: float
    max_speed_dps: float
    max_current_a: float


class StepResponseRequest(BaseModel):
    motor_id: int
    target_angle_deg: float
    duration_s: float = 5.0
    sample_rate_hz: int = 50


class RosbagRecordStartRequest(BaseModel):
    profile: str = "standard"


class RosbagPlayStartRequest(BaseModel):
    bag_name: str


# -- Motor config constants ------------------------------------------------
# Default motor IDs for a 6-DOF arm (overridable via env)
_MOTOR_IDS = list(range(1, 7))

# Default motor limits (used when no config file exists)
_DEFAULT_MOTOR_LIMITS: dict[str, float] = {
    "min_angle_deg": -180.0,
    "max_angle_deg": 180.0,
    "max_speed_dps": 360.0,
    "max_current_a": 10.0,
}

# Step response timeout (longer than normal ROS2 calls)
_STEP_RESPONSE_TIMEOUT = 30

# Recording profiles -> topic lists
_RECORDING_PROFILES: dict[str, list[str]] = {
    "minimal": ["/joint_states", "/motor_state"],
    "standard": [
        "/joint_states",
        "/motor_state",
        "/camera/color/image_raw",
        "/diagnostics",
    ],
    "debug": [],  # empty = record all topics
}

# Bag storage directory
_BAG_DIR = os.path.expanduser(os.environ.get("PRAGATI_BAG_DIR", "~/pragati_bags"))


# ---------------------------------------------------------------------------
# Motor helpers (subprocess-based, no rclpy dependency)
# ---------------------------------------------------------------------------


def _ros2_motor_status(motor_id: int | None = None) -> list[dict]:
    """Get motor state via ros2 service call to /motor_state service.

    Each motor returns: motor_id, angle_deg, speed_dps, current_a,
    temperature_c, online.
    """
    ids = [motor_id] if motor_id is not None else _MOTOR_IDS
    results = []
    for mid in ids:
        try:
            result = subprocess.run(
                [
                    "ros2",
                    "service",
                    "call",
                    f"/motor{mid}/get_state",
                    "pragati_interfaces/srv/GetMotorState",
                    json.dumps({"motor_id": mid}),
                ],
                capture_output=True,
                text=True,
                timeout=_ROS2_TIMEOUT,
            )
            if result.returncode == 0:
                # Parse the service response
                out = result.stdout.strip()
                state = _parse_motor_state_response(out, mid)
                results.append(state)
            else:
                results.append(_offline_motor(mid))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            results.append(_offline_motor(mid))
    return results


def _parse_motor_state_response(output: str, motor_id: int) -> dict:
    """Parse ros2 service call output into motor state dict."""
    state = {
        "motor_id": motor_id,
        "angle_deg": None,
        "speed_dps": None,
        "current_a": None,
        "temperature_c": None,
        "online": False,
    }
    # Parse key=value pairs from ros2 service call output
    for line in output.splitlines():
        line = line.strip()
        for field, key in [
            ("angle_deg", "angle_deg"),
            ("speed_dps", "speed_dps"),
            ("current_a", "current_a"),
            ("temperature_c", "temperature_c"),
        ]:
            match = re.search(rf"{key}[:\s=]+([+-]?\d+\.?\d*)", line)
            if match:
                state[field] = float(match.group(1))
                state["online"] = True
    return state


def _offline_motor(motor_id: int) -> dict:
    """Return an offline motor state placeholder."""
    return {
        "motor_id": motor_id,
        "angle_deg": None,
        "speed_dps": None,
        "current_a": None,
        "temperature_c": None,
        "online": False,
    }


def _ros2_motor_command(motor_id: int | None, mode: str, params: dict) -> dict:
    """Send a motor command via ros2 service call."""
    if mode == "stop" or mode == "0x81":
        # Emergency stop: send to all motors
        ids = _MOTOR_IDS if motor_id is None else [motor_id]
        results = []
        for mid in ids:
            try:
                subprocess.run(
                    [
                        "ros2",
                        "service",
                        "call",
                        f"/motor{mid}/command",
                        "pragati_interfaces/srv/MotorCommand",
                        json.dumps({"motor_id": mid, "mode": "0x81", "params": {}}),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_ROS2_TIMEOUT,
                )
                results.append({"motor_id": mid, "stopped": True})
            except (FileNotFoundError, subprocess.TimeoutExpired):
                results.append({"motor_id": mid, "stopped": False})
        return {"success": True, "stopped_motors": results}

    # Single motor command
    if motor_id is None:
        raise ValueError("motor_id required for non-stop commands")

    result = subprocess.run(
        [
            "ros2",
            "service",
            "call",
            f"/motor{motor_id}/command",
            "pragati_interfaces/srv/MotorCommand",
            json.dumps({"motor_id": motor_id, "mode": mode, "params": params}),
        ],
        capture_output=True,
        text=True,
        timeout=_ROS2_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Motor command failed: {result.stderr or result.stdout}")
    return {"success": True, "motor_id": motor_id}


def _ros2_pid_read(motor_id: int) -> dict:
    """Read PID gains for a motor via ros2 service call."""
    result = subprocess.run(
        [
            "ros2",
            "service",
            "call",
            f"/motor{motor_id}/pid/read",
            "pragati_interfaces/srv/PIDRead",
            json.dumps({"motor_id": motor_id}),
        ],
        capture_output=True,
        text=True,
        timeout=_ROS2_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PID read failed for motor {motor_id}")

    # Parse gains from output
    gains = {
        "motor_id": motor_id,
        "angle_kp": 0,
        "angle_ki": 0,
        "speed_kp": 0,
        "speed_ki": 0,
        "current_kp": 0,
        "current_ki": 0,
    }
    out = result.stdout
    for key in [
        "angle_kp",
        "angle_ki",
        "speed_kp",
        "speed_ki",
        "current_kp",
        "current_ki",
    ]:
        match = re.search(rf"{key}[:\s=]+(\d+)", out)
        if match:
            gains[key] = int(match.group(1))
    return gains


def _ros2_pid_write(motor_id: int, gains: dict) -> dict:
    """Write PID gains for a motor via ros2 service call."""
    result = subprocess.run(
        [
            "ros2",
            "service",
            "call",
            f"/motor{motor_id}/pid/write",
            "pragati_interfaces/srv/PIDWrite",
            json.dumps({"motor_id": motor_id, **gains}),
        ],
        capture_output=True,
        text=True,
        timeout=_ROS2_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PID write failed for motor {motor_id}")
    return {"success": True}


def _ros2_calibrate_read(motor_id: int) -> dict:
    """Read encoder calibration data for a motor."""
    result = subprocess.run(
        [
            "ros2",
            "service",
            "call",
            f"/motor{motor_id}/encoder/read",
            "pragati_interfaces/srv/EncoderRead",
            json.dumps({"motor_id": motor_id}),
        ],
        capture_output=True,
        text=True,
        timeout=_ROS2_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Encoder read failed for motor {motor_id}")

    data = {
        "motor_id": motor_id,
        "raw_position": 0,
        "angle_deg": 0.0,
        "offset": 0,
    }
    out = result.stdout
    for key, cast in [("raw_position", int), ("angle_deg", float), ("offset", int)]:
        match = re.search(rf"{key}[:\s=]+([+-]?\d+\.?\d*)", out)
        if match:
            data[key] = cast(match.group(1))
    return data


def _ros2_calibrate_zero(motor_id: int) -> dict:
    """Zero-set the encoder for a motor."""
    result = subprocess.run(
        [
            "ros2",
            "service",
            "call",
            f"/motor{motor_id}/encoder/zero",
            "pragati_interfaces/srv/EncoderZero",
            json.dumps({"motor_id": motor_id}),
        ],
        capture_output=True,
        text=True,
        timeout=_ROS2_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Encoder zero failed for motor {motor_id}")
    return {"success": True, "motor_id": motor_id}


def _read_motor_limits(motor_id: int) -> dict:
    """Read motor limits config (from file or defaults)."""
    limits_file = os.path.join(_BAG_DIR, "..", "motor_limits.json")
    limits = dict(_DEFAULT_MOTOR_LIMITS)
    limits["motor_id"] = motor_id
    try:
        if os.path.isfile(limits_file):
            with open(limits_file) as f:
                all_limits = json.load(f)
                if str(motor_id) in all_limits:
                    limits.update(all_limits[str(motor_id)])
    except (json.JSONDecodeError, OSError):
        pass
    return limits


def _write_motor_limits(motor_id: int, limits: dict) -> dict:
    """Write motor limits config to file."""
    limits_file = os.path.join(_BAG_DIR, "..", "motor_limits.json")
    all_limits: dict = {}
    try:
        if os.path.isfile(limits_file):
            with open(limits_file) as f:
                all_limits = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    all_limits[str(motor_id)] = {
        "min_angle_deg": limits["min_angle_deg"],
        "max_angle_deg": limits["max_angle_deg"],
        "max_speed_dps": limits["max_speed_dps"],
        "max_current_a": limits["max_current_a"],
    }
    os.makedirs(os.path.dirname(limits_file), exist_ok=True)
    with open(limits_file, "w") as f:
        json.dump(all_limits, f, indent=2)
    return {"success": True, "motor_id": motor_id}


def _ros2_step_response(
    motor_id: int,
    target_angle_deg: float,
    duration_s: float,
    sample_rate_hz: int,
) -> dict:
    """Execute step response test locally via ros2 service call.

    The agent runs the entire test loop (command + sample) and returns
    the full response data.
    """
    result = subprocess.run(
        [
            "ros2",
            "service",
            "call",
            f"/motor{motor_id}/step_test",
            "pragati_interfaces/srv/StepTest",
            json.dumps(
                {
                    "motor_id": motor_id,
                    "target_angle_deg": target_angle_deg,
                    "duration_s": duration_s,
                    "sample_rate_hz": sample_rate_hz,
                }
            ),
        ],
        capture_output=True,
        text=True,
        timeout=_STEP_RESPONSE_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Step response test failed for motor {motor_id}: " f"{result.stderr or result.stdout}"
        )

    # Parse response — expected to contain JSON-like data
    out = result.stdout.strip()
    # Try to extract JSON from the output
    try:
        # ros2 service call wraps response; try to find JSON block
        json_match = re.search(r"\{.*\}", out, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            data["motor_id"] = motor_id
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: return raw output with minimal structure
    return {
        "motor_id": motor_id,
        "samples": [],
        "rise_time_s": 0.0,
        "settling_time_s": 0.0,
        "overshoot_percent": 0.0,
        "steady_state_error_deg": 0.0,
        "raw_output": out,
    }


# ---------------------------------------------------------------------------
# Rosbag helpers
# ---------------------------------------------------------------------------

# Active recording process (module-level to persist across requests)
_recording_process: subprocess.Popen | None = None
_recording_start_time: float | None = None
_recording_profile: str | None = None

# Active playback process
_playback_process: subprocess.Popen | None = None


def _rosbag_list() -> list[dict]:
    """List bag files in the configured bag directory with metadata."""
    bags: list[dict] = []
    if not os.path.isdir(_BAG_DIR):
        return bags

    for entry in sorted(os.listdir(_BAG_DIR), reverse=True):
        bag_path = os.path.join(_BAG_DIR, entry)
        if not os.path.isdir(bag_path):
            continue
        # Check for metadata.yaml (ROS2 bag directory marker)
        metadata_file = os.path.join(bag_path, "metadata.yaml")
        if not os.path.isfile(metadata_file):
            continue

        # Get basic size info
        total_size = 0
        for dirpath, _, filenames in os.walk(bag_path):
            for fname in filenames:
                total_size += os.path.getsize(os.path.join(dirpath, fname))

        # Try to get detailed metadata from ros2 bag info
        info = _rosbag_info(entry)
        bags.append(
            {
                "name": entry,
                "size_bytes": total_size,
                "duration_s": info.get("duration_s"),
                "topic_count": info.get("topic_count"),
                "message_count": info.get("message_count"),
                "created": info.get(
                    "created",
                    datetime.fromtimestamp(
                        os.path.getctime(bag_path),
                        tz=timezone.utc,
                    ).isoformat(),
                ),
            }
        )
    return bags


def _rosbag_info(bag_name: str) -> dict:
    """Run ros2 bag info and parse output."""
    bag_path = os.path.join(_BAG_DIR, bag_name)
    try:
        result = subprocess.run(
            ["ros2", "bag", "info", bag_path],
            capture_output=True,
            text=True,
            timeout=_ROS2_TIMEOUT,
        )
        if result.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    info: dict = {}
    out = result.stdout
    # Parse duration
    dur_match = re.search(r"Duration:\s+([\d.]+)s", out)
    if dur_match:
        info["duration_s"] = float(dur_match.group(1))
    # Parse topic count
    topic_match = re.search(r"Topic count:\s+(\d+)", out)
    if topic_match:
        info["topic_count"] = int(topic_match.group(1))
    # Parse message count
    msg_match = re.search(r"Messages:\s+(\d+)", out)
    if not msg_match:
        msg_match = re.search(r"Message count:\s+(\d+)", out)
    if msg_match:
        info["message_count"] = int(msg_match.group(1))
    # Parse start time as created date
    start_match = re.search(r"Start:\s+(.+)", out)
    if start_match:
        info["created"] = start_match.group(1).strip()
    return info


def _rosbag_record_start(profile: str) -> dict:
    """Start a ros2 bag record process."""
    global _recording_process, _recording_start_time, _recording_profile

    if _recording_process is not None and _recording_process.poll() is None:
        raise ValueError("recording_active")

    os.makedirs(_BAG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bag_name = f"recording_{timestamp}"
    bag_path = os.path.join(_BAG_DIR, bag_name)

    topics = _RECORDING_PROFILES.get(profile, [])
    cmd = ["ros2", "bag", "record", "-o", bag_path, "-s", "mcap"]
    if topics:
        cmd.extend(topics)
    else:
        cmd.append("--all")

    _recording_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _recording_start_time = time.time()
    _recording_profile = profile
    return {"active": True, "profile": profile}


def _rosbag_record_stop() -> dict:
    """Stop the active recording process."""
    global _recording_process, _recording_start_time, _recording_profile

    if _recording_process is None or _recording_process.poll() is not None:
        raise ValueError("not_recording")

    _recording_process.terminate()
    try:
        _recording_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _recording_process.kill()
    _recording_process = None
    _recording_start_time = None
    _recording_profile = None
    return {"active": False}


def _rosbag_record_status() -> dict:
    """Get current recording status."""
    active = _recording_process is not None and _recording_process.poll() is None
    disk = psutil.disk_usage(_BAG_DIR if os.path.isdir(_BAG_DIR) else "/")
    return {
        "active": active,
        "profile": _recording_profile if active else None,
        "duration_s": (
            round(time.time() - _recording_start_time, 1)
            if active and _recording_start_time
            else None
        ),
        "estimated_size_bytes": None,  # Hard to estimate without monitoring
        "disk_remaining_bytes": disk.free,
    }


def _rosbag_play_start(bag_name: str) -> dict:
    """Start ros2 bag play for a bag."""
    global _playback_process

    if _recording_process is not None and _recording_process.poll() is None:
        raise ValueError("recording_active")

    if _playback_process is not None and _playback_process.poll() is None:
        raise ValueError("playback_active")

    bag_path = os.path.join(_BAG_DIR, bag_name)
    if not os.path.isdir(bag_path):
        raise FileNotFoundError(f"Bag '{bag_name}' not found")

    _playback_process = subprocess.Popen(
        ["ros2", "bag", "play", bag_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"playing": True, "bag_name": bag_name}


def _rosbag_play_stop() -> dict:
    """Stop active bag playback."""
    global _playback_process

    if _playback_process is None or _playback_process.poll() is not None:
        return {"playing": False}

    _playback_process.terminate()
    try:
        _playback_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _playback_process.kill()
    _playback_process = None
    return {"playing": False}


_VALID_LIFECYCLE_TRANSITIONS = {
    "configure",
    "activate",
    "deactivate",
    "shutdown",
    "cleanup",
}


def _ros2_effective_timeout() -> float:
    """Return a longer timeout for the first call after startup (DDS cold start)."""
    if not _ros2_first_call_done:
        return _ROS2_FIRST_CALL_TIMEOUT
    return _ROS2_TIMEOUT


def _ros2_node_list() -> list[dict]:
    # Prefer local dashboard (persistent rclpy node, reliable discovery)
    dashboard_result = _query_local_dashboard("nodes")
    if dashboard_result is not None:
        return dashboard_result

    # Fallback: ros2 CLI subprocess (unreliable on RPi4 wifi due to
    # CycloneDDS multicast discovery failure with short-lived participants)
    result = _run_ros2_cmd(
        ["ros2", "node", "list", "--no-daemon"],
        timeout=_ros2_effective_timeout(),
    )
    nodes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.rsplit("/", 1)
        if len(parts) == 2:
            ns = "/" + parts[0].lstrip("/") if parts[0] else "/"
            name = parts[1]
        else:
            ns, name = "/", parts[0].lstrip("/")
        nodes.append({"name": name, "namespace": ns, "lifecycle_state": None})
    return nodes


def _ros2_topic_list() -> list[dict]:
    # Prefer local dashboard
    dashboard_result = _query_local_dashboard("topics")
    if dashboard_result is not None:
        return dashboard_result

    # Fallback: ros2 CLI subprocess
    result = _run_ros2_cmd(
        ["ros2", "topic", "list", "-t", "--no-daemon"],
        timeout=_ros2_effective_timeout(),
    )
    topics = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\S+)\s+\[(\S+)\]$", line)
        if match:
            topics.append(
                {
                    "name": match.group(1),
                    "type": match.group(2),
                    "publisher_count": None,
                    "subscriber_count": None,
                }
            )
    return topics


def _ros2_service_list() -> list[dict]:
    # Prefer local dashboard
    dashboard_result = _query_local_dashboard("services")
    if dashboard_result is not None:
        return dashboard_result

    # Fallback: ros2 CLI subprocess
    result = _run_ros2_cmd(
        ["ros2", "service", "list", "-t", "--no-daemon"],
        timeout=_ros2_effective_timeout(),
    )
    services = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\S+)\s+\[(\S+)\]$", line)
        if match:
            services.append(
                {
                    "name": match.group(1),
                    "type": match.group(2),
                }
            )
    return services


# ---------------------------------------------------------------------------
# Systemd helpers
# ---------------------------------------------------------------------------
_SYSTEMCTL_TIMEOUT = 30  # Increased for restart operations (takes ~16s)

ALLOWED_SERVICES = {
    "pragati-dashboard",
    "pragati-agent",
    "arm_launch",
    "vehicle_launch",
    "pigpiod",
    "can-watchdog@can0",
    "field-monitor",
    "boot_timing.timer",
}

ALLOWED_ACTIONS = {"start", "stop", "restart", "enable", "disable"}


def _unit_name(name: str) -> str:
    """Return the full systemd unit name.

    If *name* already contains a dot-suffix (e.g. ``boot_timing.timer``),
    return it unchanged.  Otherwise append ``.service``.
    """
    if "." in name:
        return name
    return f"{name}.service"


def _validate_service(name: str):
    """Return JSONResponse if service is not allowed, else None."""
    if name not in ALLOWED_SERVICES:
        return JSONResponse(
            status_code=403,
            content={
                "error": "forbidden",
                "message": f"Service '{name}' not in allowed list",
            },
        )
    return None


def _systemd_list_services() -> list[dict]:
    """List all allowed services with their status."""
    services = []
    for name in sorted(ALLOWED_SERVICES):
        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "show",
                    name,
                    "--property=ActiveState,SubState,Description",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                timeout=_SYSTEMCTL_TIMEOUT,
            )
            if result.returncode == 0:
                props = {}
                for line in result.stdout.strip().split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        props[k] = v
                services.append(
                    {
                        "name": name,
                        "active_state": props.get("ActiveState", "unknown"),
                        "sub_state": props.get("SubState", "unknown"),
                        "description": props.get("Description", ""),
                    }
                )
            else:
                services.append(
                    {
                        "name": name,
                        "active_state": "unknown",
                        "sub_state": "unknown",
                        "description": "",
                    }
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            services.append(
                {
                    "name": name,
                    "active_state": "unknown",
                    "sub_state": "unknown",
                    "description": "",
                }
            )
    return services


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    api_key = os.environ.get("PRAGATI_AGENT_API_KEY", "")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        global _rclpy_teardown_task
        register_mdns()
        _rclpy_teardown_task = asyncio.create_task(_rclpy_teardown_checker())
        try:
            yield
        finally:
            await _cancel_rclpy_teardown_task()
            _teardown_rclpy()
            unregister_mdns()

    app = FastAPI(title="Pragati RPi Agent", version=AGENT_VERSION, lifespan=lifespan)

    # -- Global exception-catching middleware (outermost) -----------------
    @app.middleware("http")
    async def error_middleware(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled exception on %s", request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_error",
                    "message": str(exc),
                },
            )

    # -- Auth middleware --------------------------------------------------
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if api_key and request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if request.url.path == "/health":
                return await call_next(request)
            provided = request.headers.get("X-API-Key", "")
            if not provided or provided != api_key:
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized"},
                )
        return await call_next(request)

    # -- Endpoints -------------------------------------------------------

    @app.get("/health")
    async def health():
        return _collect_health()

    @app.get("/diagnostics/check")
    async def diagnostics_check():
        """Self-check endpoint — verifies agent subsystem health on demand.

        Returns lightweight boolean/integer indicators for:
        - rclpy_available: whether rclpy is initialized and node is active
        - systemd_sudo:    whether 'sudo systemctl list-units' succeeds without password
        - ros2_node_count: number of ROS2 nodes visible (or -1 on failure)
        - can_bus_up:      whether /sys/class/net/can0/operstate is "up" (null if no CAN)
        - uptime_seconds:  agent process uptime in seconds
        """
        # --- rclpy_available ---
        rclpy_ok: bool = bool(_rclpy_available and _rclpy_node is not None)

        # --- systemd_sudo ---
        try:
            result = subprocess.run(
                ["sudo", "-n", "systemctl", "list-units", "--no-pager", "--quiet"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            systemd_ok: bool = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            systemd_ok = False

        # --- ros2_node_count ---
        try:
            result2 = _run_ros2_cmd(["ros2", "node", "list"], timeout=3)
            lines = [ln.strip() for ln in result2.stdout.splitlines() if ln.strip()]
            ros2_count: int = len(lines)
        except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired, OSError):
            ros2_count = -1

        # --- can_bus_up ---
        can_operstate_path = "/sys/class/net/can0/operstate"
        can_up: bool | None = None
        try:
            with open(can_operstate_path) as _f:
                can_up = _f.read().strip() == "up"
        except (FileNotFoundError, OSError):
            can_up = None  # CAN interface not present on this machine

        # --- uptime_seconds ---
        uptime_s: float = time.time() - psutil.boot_time()

        return {
            "rclpy_available": rclpy_ok,
            "systemd_sudo": systemd_ok,
            "ros2_node_count": ros2_count,
            "can_bus_up": can_up,
            "uptime_seconds": uptime_s,
        }

    @app.get("/ros2/nodes")
    async def ros2_nodes():
        try:
            return _ros2_node_list()
        except (FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": ("ROS2 is not running on this entity"),
                },
            )

    @app.get("/ros2/topics")
    async def ros2_topics():
        try:
            return _ros2_topic_list()
        except (FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": ("ROS2 is not running on this entity"),
                },
            )

    @app.get("/ros2/services")
    async def ros2_services():
        try:
            return _ros2_service_list()
        except (FileNotFoundError, RuntimeError, OSError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": ("ROS2 is not running on this entity"),
                },
            )

    @app.get("/systemd/services")
    async def systemd_services():
        return _systemd_list_services()

    @app.post("/systemd/services/{name}/{action}")
    async def systemd_service_action(name: str, action: str):
        if action not in ALLOWED_ACTIONS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "bad_request",
                    "message": (
                        f"Invalid action '{action}'." f" Allowed: {sorted(ALLOWED_ACTIONS)}"
                    ),
                },
            )
        err = _validate_service(name)
        if err:
            return err
        try:
            result = subprocess.run(
                ["sudo", "systemctl", action, name],
                capture_output=True,
                text=True,
                timeout=_SYSTEMCTL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return JSONResponse(
                status_code=504,
                content={
                    "error": "timeout",
                    "message": f"systemctl {action} {name} timed out",
                },
            )
        except FileNotFoundError:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "not_found",
                    "message": "systemctl not found",
                },
            )
        if result.returncode != 0:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "systemctl_failed",
                    "message": result.stderr.strip(),
                },
            )
        past_tense = {
            "start": "started",
            "stop": "stopped",
            "restart": "restarted",
            "enable": "enabled",
            "disable": "disabled",
        }
        response = {"status": past_tense.get(action, action), "service": name}
        if name == "pragati-agent" and action in ("stop", "disable"):
            response["warning"] = (
                "Stopping or disabling pragati-agent will prevent" " remote management of this RPi"
            )
        return response

    @app.get("/systemd/services/{name}/logs")
    async def systemd_service_logs(name: str, lines: int = 100):
        err = _validate_service(name)
        if err:
            return err
        if lines < 1:
            lines = 1
        elif lines > 10000:
            lines = 10000
        try:
            result = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    _unit_name(name),
                    "-n",
                    str(lines),
                    "--no-pager",
                    "--output=short-iso",
                ],
                capture_output=True,
                text=True,
                timeout=_SYSTEMCTL_TIMEOUT * 2,
            )
        except subprocess.TimeoutExpired:
            return JSONResponse(
                status_code=504,
                content={
                    "error": "timeout",
                    "message": f"journalctl timed out for {name}",
                },
            )
        except FileNotFoundError:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "not_found",
                    "message": "journalctl not found",
                },
            )
        if result.returncode != 0:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "journalctl_failed",
                    "message": result.stderr.strip(),
                },
            )
        log_lines = [line for line in result.stdout.strip().split("\n") if line]
        return {"service": name, "lines": lines, "logs": log_lines}

    # -- System control (reboot / shutdown) ----------------------------

    @app.post("/system/reboot")
    async def system_reboot(req: SystemControlRequest):
        if req.token != "REBOOT":
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": "Invalid reboot token",
                },
            )
        # Use Popen so we respond before the OS kills us
        subprocess.Popen(
            ["sudo", "reboot"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"status": "rebooting", "message": "System is rebooting"}

    @app.post("/system/shutdown")
    async def system_shutdown(req: SystemControlRequest):
        if req.token != "SHUTDOWN":
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": "Invalid shutdown token",
                },
            )
        subprocess.Popen(
            ["sudo", "shutdown", "-h", "now"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "shutting_down",
            "message": "System is shutting down",
        }

    # -- System stats (CPU, RAM, disk, temp, processes) ----------------

    @app.get("/system/processes")
    async def system_processes():
        """Return top 15 processes by CPU usage."""
        return _collect_processes()

    @app.get("/system/stats")
    async def system_stats():
        """Return aggregate system metrics."""
        return _collect_system_stats()

    # -- Journalctl per-unit SSE stream --------------------------------

    # Allowlist for journal streaming (subset of ALLOWED_SERVICES that
    # are pragati-related systemd units operators actually tail).
    _JOURNAL_ALLOWED_UNITS = {
        "arm_launch",
        "vehicle_launch",
        "pragati-agent",
        "pragati-dashboard",
        "pigpiod",
        "can-watchdog@can0",
    }

    @app.get("/logs/journal/{unit}")
    async def logs_journal_unit(unit: str, request: Request):
        """SSE stream of journalctl output for a specific systemd unit.

        Optional query params:
        - since: ISO 8601 timestamp for --since
        - until: ISO 8601 timestamp for --until
        When either is present, runs in historical (non-follow) mode.
        """
        if unit not in _JOURNAL_ALLOWED_UNITS:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": (f"Unit '{unit}' not in allowed list"),
                },
            )

        if _sse_connection_count.get() >= _MAX_SSE_CONNECTIONS:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "too_many_streams",
                    "message": "Maximum 3 concurrent SSE connections",
                },
            )

        # Parse optional time filter query params
        since = request.query_params.get("since")
        until = request.query_params.get("until")
        # Sanitize: only allow digits, dashes, colons, T, spaces, dots, plus
        _safe_re = re.compile(r"^[\d\-T: .+]+$")
        if since and not _safe_re.match(since):
            since = None
        if until and not _safe_re.match(until):
            until = None
        has_time_filter = bool(since or until)

        def _generate():
            _sse_connection_count.increment()
            proc = None
            try:
                cmd = [
                    "journalctl",
                    "-u",
                    _unit_name(unit),
                    "--output=json",
                ]
                if since:
                    cmd += ["--since", since]
                if until:
                    cmd += ["--until", until]
                if has_time_filter:
                    cmd += ["--no-tail"]
                else:
                    cmd += ["-n", "50", "-f"]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
            except FileNotFoundError:
                yield ('data: {"error": "journalctl not found"}\n\n')
            finally:
                _sse_connection_count.decrement()
                if proc:
                    proc.kill()
                    proc.wait()

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @app.get("/logs/stream")
    async def logs_stream():
        if _sse_connection_count.get() >= _MAX_SSE_CONNECTIONS:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "too_many_streams",
                    "message": ("Maximum 3 concurrent SSE connections"),
                },
            )

        def _generate():
            _sse_connection_count.increment()
            proc = None
            try:
                proc = subprocess.Popen(
                    [
                        "journalctl",
                        "-u",
                        "pragati-*",
                        "-n",
                        "50",
                        "-f",
                        "--output=json",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
            finally:
                _sse_connection_count.decrement()
                if proc:
                    proc.kill()
                    proc.wait()

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # -- Task 1.7: Node detail ----------------------------------------

    @app.get("/ros2/nodes/{node_name}")
    async def ros2_node_detail(node_name: str):
        # Ensure node_name has leading slash for ros2 CLI
        if not node_name.startswith("/"):
            node_name = "/" + node_name
        try:
            info = _ros2_node_info(node_name)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )
        except RuntimeError:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )
        if info is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "node_not_found",
                    "message": f"Node '{node_name}' not found",
                },
            )
        return info

    # -- Task 1.8: Lifecycle transition --------------------------------

    @app.post("/ros2/nodes/{node_name}/lifecycle/{transition}")
    async def ros2_lifecycle_transition(node_name: str, transition: str):
        if transition not in _VALID_LIFECYCLE_TRANSITIONS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_transition",
                    "message": (
                        f"Invalid transition '{transition}'. "
                        f"Valid: {sorted(_VALID_LIFECYCLE_TRANSITIONS)}"
                    ),
                },
            )
        try:
            subprocess.run(
                ["ros2", "lifecycle", "set", node_name, transition],
                capture_output=True,
                text=True,
                timeout=_ROS2_TIMEOUT,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )
        return {
            "success": True,
            "node": node_name,
            "transition": transition,
        }

    # -- Task 1.3: Parameters list -------------------------------------

    @app.get("/ros2/parameters")
    async def ros2_parameters():
        """Get node list with empty parameters (lightweight).

        Returns node names only. Use GET /ros2/parameters/{node_name}
        to fetch parameters for a specific node on demand.
        This avoids running ros2 param dump for ALL nodes at once,
        which overwhelms the RPi CPU.
        """
        try:
            node_entries = _ros2_node_list()
        except (
            FileNotFoundError,
            RuntimeError,
            subprocess.TimeoutExpired,
        ):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )

        nodes = []
        for node_entry in node_entries:
            full_name = node_entry["namespace"].rstrip("/") + "/" + node_entry["name"]
            if full_name.startswith("//"):
                full_name = full_name[1:]
            nodes.append({"name": full_name, "parameters": None})  # None = not yet loaded
        return {"nodes": nodes}

    @app.get("/ros2/parameters/{node_name:path}")
    async def ros2_node_parameters(node_name: str):
        """Get parameters for a single node (on-demand).

        Runs in a thread pool to avoid blocking the event loop.
        """
        import asyncio

        def _fetch():
            return _ros2_param_dump(f"/{node_name}" if not node_name.startswith("/") else node_name)

        try:
            params = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception:
            params = []
        return {
            "name": f"/{node_name}" if not node_name.startswith("/") else node_name,
            "parameters": params,
        }

    # -- Task 1.4: Parameter set ---------------------------------------

    @app.put("/ros2/parameters/{node_name}")
    async def ros2_set_parameters(node_name: str, body: ParamSetRequest):
        results = []
        try:
            for param in body.params:
                result = subprocess.run(
                    [
                        "ros2",
                        "param",
                        "set",
                        node_name,
                        param.name,
                        param.value,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_ROS2_TIMEOUT,
                )
                results.append(
                    {
                        "name": param.name,
                        "success": result.returncode == 0,
                    }
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )
        return {"results": results}

    # -- Task 1.5: Log file listing ------------------------------------

    @app.get("/logs")
    async def log_listing():
        return {"files": _list_log_files()}

    # -- Task 1.6: Log tail SSE ----------------------------------------

    @app.get("/logs/{log_name:path}/tail")
    async def log_tail(log_name: str):
        # Path traversal check — reject early with 400
        if ".." in log_name or log_name.startswith("/"):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_path",
                    "message": "Path traversal not allowed",
                },
            )

        if _sse_connection_count.get() >= _MAX_SSE_CONNECTIONS:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "too_many_streams",
                    "message": "Maximum 3 concurrent SSE connections",
                },
            )

        is_journald = log_name == "__journald__"

        if not is_journald:
            resolved = _resolve_log_path(log_name)
            if resolved is None or not os.path.isfile(resolved):
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "log_not_found",
                        "message": f"Log file '{log_name}' not found",
                    },
                )

        def _generate():
            _sse_connection_count.increment()
            proc = None
            try:
                if is_journald:
                    proc = subprocess.Popen(
                        [
                            "journalctl",
                            "-u",
                            "pragati-*",
                            "-n",
                            "50",
                            "-f",
                            "--output=json",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                else:
                    proc = subprocess.Popen(
                        ["tail", "-n", "50", "-f", resolved],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
            finally:
                _sse_connection_count.decrement()
                if proc:
                    proc.kill()
                    proc.wait()

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # -- Task 1.1: Topic echo SSE -------------------------------------

    @app.get("/ros2/topics/{topic_name:path}/echo")
    async def ros2_topic_echo(topic_name: str, hz: int = Query(default=10, ge=1, le=100)):
        if _sse_connection_count.get() >= _MAX_SSE_CONNECTIONS:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "too_many_streams",
                    "message": "Maximum 3 concurrent SSE connections",
                },
            )

        # Clamp hz to max 30
        effective_hz = min(hz, 30)

        if not _rclpy_available:
            node = _ensure_rclpy()
            if node is None:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "ros2_unavailable",
                        "message": "ROS2 (rclpy) is not available",
                    },
                )

        # Ensure topic has leading slash for rclpy
        if not topic_name.startswith("/"):
            topic_name = "/" + topic_name
        decoded_topic = topic_name.replace("%2F", "/")

        generator = _create_echo_generator(decoded_topic, effective_hz)

        async def _sse_wrapper():
            _sse_connection_count.increment()
            try:
                async for chunk in generator:
                    yield chunk
            finally:
                _sse_connection_count.decrement()

        return StreamingResponse(
            _sse_wrapper(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # -- Task 1.2: Service call ----------------------------------------

    @app.post("/ros2/services/{service_name:path}/call")
    async def ros2_service_call(service_name: str, request: Request):
        # Ensure service has leading slash for ros2 CLI
        if not service_name.startswith("/"):
            service_name = "/" + service_name
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "bad_request",
                    "message": "Invalid JSON body",
                },
            )

        if "type" not in body:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "bad_request",
                    "message": "Missing required field 'type'",
                },
            )

        srv_type = body["type"]
        srv_request = body.get("request", {})

        # Build ros2 service call command
        request_yaml = json.dumps(srv_request)
        start_time = time.time()
        try:
            result = subprocess.run(
                [
                    "ros2",
                    "service",
                    "call",
                    service_name,
                    srv_type,
                    request_yaml,
                ],
                capture_output=True,
                text=True,
                timeout=_ROS2_TIMEOUT,
            )
            duration_ms = round((time.time() - start_time) * 1000, 1)
        except subprocess.TimeoutExpired:
            return JSONResponse(
                status_code=408,
                content={
                    "error": "service_timeout",
                    "message": (f"Service call to '{service_name}' timed out"),
                },
            )
        except FileNotFoundError:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )

        return {
            "response": result.stdout.strip(),
            "duration_ms": duration_ms,
        }

    # =================================================================
    # Motor endpoints (Tasks 1.1–1.6 of dashboard-motor-rosbag)
    # =================================================================

    @app.get("/motors/status")
    async def motors_status(motor_id: int | None = Query(default=None)):
        """Return motor state for one or all motors."""
        try:
            data = _ros2_motor_status(motor_id)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )
        if motor_id is not None:
            return data[0] if data else _offline_motor(motor_id)
        return data

    @app.post("/motors/command")
    async def motors_command(body: MotorCommandRequest):
        """Send a CAN motor command."""
        try:
            result = _ros2_motor_command(body.motor_id, body.mode, body.params)
            return result
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"error": "bad_request", "message": str(exc)},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ros2_unavailable",
                    "message": "ROS2 is not running on this entity",
                },
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=500,
                content={"error": "command_failed", "message": str(exc)},
            )

    @app.get("/motors/pid/read")
    async def motors_pid_read(motor_id: int = Query()):
        """Read PID gains for a motor."""
        try:
            return _ros2_pid_read(motor_id)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=504,
                content={
                    "error": "motor_timeout",
                    "message": (f"Motor {motor_id} not responding on CAN bus"),
                },
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=504,
                content={
                    "error": "motor_timeout",
                    "message": str(exc),
                },
            )

    @app.post("/motors/pid/write")
    async def motors_pid_write(body: PIDWriteRequest):
        """Write PID gains to a motor."""
        try:
            gains = {
                "angle_kp": body.angle_kp,
                "angle_ki": body.angle_ki,
                "speed_kp": body.speed_kp,
                "speed_ki": body.speed_ki,
                "current_kp": body.current_kp,
                "current_ki": body.current_ki,
            }
            _ros2_pid_write(body.motor_id, gains)
            return {"success": True}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=504,
                content={
                    "error": "motor_timeout",
                    "message": (f"Motor {body.motor_id} not responding on CAN bus"),
                },
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=500,
                content={"error": "pid_write_failed", "message": str(exc)},
            )

    @app.get("/motors/calibrate/read")
    async def motors_calibrate_read(motor_id: int = Query()):
        """Read encoder calibration data."""
        try:
            return _ros2_calibrate_read(motor_id)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=504,
                content={
                    "error": "motor_timeout",
                    "message": (f"Motor {motor_id} not responding on CAN bus"),
                },
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "calibrate_read_failed",
                    "message": str(exc),
                },
            )

    @app.post("/motors/calibrate/zero")
    async def motors_calibrate_zero(body: CalibrateZeroRequest):
        """Zero-set encoder for a motor."""
        try:
            return _ros2_calibrate_zero(body.motor_id)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=504,
                content={
                    "error": "motor_timeout",
                    "message": (f"Motor {body.motor_id} not responding on CAN bus"),
                },
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "calibrate_zero_failed",
                    "message": str(exc),
                },
            )

    @app.get("/motors/limits")
    async def motors_limits_read(motor_id: int = Query()):
        """Read motor limits config."""
        return _read_motor_limits(motor_id)

    @app.put("/motors/limits")
    async def motors_limits_write(body: MotorLimitsWriteRequest):
        """Write motor limits config."""
        return _write_motor_limits(body.motor_id, body.model_dump())

    @app.post("/motors/step-response")
    async def motors_step_response(body: StepResponseRequest):
        """Execute a step response test locally."""
        try:
            return _ros2_step_response(
                motor_id=body.motor_id,
                target_angle_deg=body.target_angle_deg,
                duration_s=body.duration_s,
                sample_rate_hz=body.sample_rate_hz,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return JSONResponse(
                status_code=504,
                content={
                    "error": "motor_timeout",
                    "message": (f"Motor {body.motor_id} not responding on CAN bus"),
                },
            )
        except RuntimeError as exc:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "step_response_failed",
                    "message": str(exc),
                },
            )

    # =================================================================
    # Rosbag endpoints (Tasks 2.1–2.5 of dashboard-motor-rosbag)
    # =================================================================

    @app.get("/rosbag/list")
    async def rosbag_list():
        """List bag files with metadata."""
        return _rosbag_list()

    @app.post("/rosbag/record/start")
    async def rosbag_record_start(body: RosbagRecordStartRequest):
        """Start recording with a profile."""
        try:
            return _rosbag_record_start(body.profile)
        except ValueError as exc:
            error_code = str(exc)
            return JSONResponse(
                status_code=409,
                content={
                    "error": error_code,
                    "message": "A recording is already in progress",
                },
            )

    @app.post("/rosbag/record/stop")
    async def rosbag_record_stop():
        """Stop the active recording."""
        try:
            return _rosbag_record_stop()
        except ValueError:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "not_recording",
                    "message": "No recording is in progress",
                },
            )

    @app.get("/rosbag/record/status")
    async def rosbag_record_status():
        """Get recording status."""
        return _rosbag_record_status()

    @app.get("/rosbag/download/{bag_name}")
    async def rosbag_download(bag_name: str):
        """Download a bag as tar.gz stream."""
        # Path traversal prevention
        if ".." in bag_name or "/" in bag_name or "\\" in bag_name:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_path",
                    "message": "Path traversal is not allowed",
                },
            )

        bag_path = os.path.join(_BAG_DIR, bag_name)
        if not os.path.isdir(bag_path):
            return JSONResponse(
                status_code=404,
                content={"error": "bag_not_found"},
            )

        import tarfile
        import io

        def _stream_tar():
            """Stream bag directory as tar.gz."""
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(bag_path, arcname=bag_name)
            buf.seek(0)
            while True:
                chunk = buf.read(65536)
                if not chunk:
                    break
                yield chunk

        return StreamingResponse(
            _stream_tar(),
            media_type="application/gzip",
            headers={
                "Content-Disposition": (f'attachment; filename="{bag_name}.tar.gz"'),
            },
        )

    @app.post("/rosbag/play/start")
    async def rosbag_play_start(body: RosbagPlayStartRequest):
        """Start bag playback."""
        try:
            return _rosbag_play_start(body.bag_name)
        except ValueError as exc:
            error_code = str(exc)
            msg = (
                "Cannot play while recording"
                if error_code == "recording_active"
                else "A playback is already active"
            )
            return JSONResponse(
                status_code=409,
                content={"error": error_code, "message": msg},
            )
        except FileNotFoundError:
            return JSONResponse(
                status_code=404,
                content={"error": "bag_not_found"},
            )

    @app.post("/rosbag/play/stop")
    async def rosbag_play_stop():
        """Stop bag playback."""
        return _rosbag_play_stop()

    # =================================================================
    # Detection image browser
    # =================================================================

    _IMAGE_DIRS = {
        "input": os.path.expanduser("~/pragati_ros2/data/inputs"),
        "output": os.path.expanduser("~/pragati_ros2/data/outputs"),
    }

    @app.get("/images")
    async def list_images(
        image_type: str = Query(default="all", regex="^(all|input|output)$"),
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        """List detection images from input and output directories."""
        files = []
        dirs_to_scan = (
            _IMAGE_DIRS.items() if image_type == "all" else [(image_type, _IMAGE_DIRS[image_type])]
        )
        for img_type, img_dir in dirs_to_scan:
            if not os.path.isdir(img_dir):
                continue
            for fname in os.listdir(img_dir):
                fpath = os.path.join(img_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                # Only serve image files
                lower = fname.lower()
                if not (
                    lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png")
                ):
                    continue
                try:
                    stat = os.stat(fpath)
                    files.append(
                        {
                            "name": fname,
                            "type": img_type,
                            "size_bytes": stat.st_size,
                            "modified": datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }
                    )
                except OSError:
                    continue

        # Sort by modified date, newest first
        files.sort(key=lambda f: f["modified"] or "", reverse=True)
        return {"images": files[:limit]}

    @app.get("/images/{image_type}/{filename}")
    async def get_image(image_type: str, filename: str):
        """Serve a single detection image file."""
        if image_type not in _IMAGE_DIRS:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_type", "message": "Type must be 'input' or 'output'"},
            )
        # Path traversal prevention
        if ".." in filename or "/" in filename or "\\" in filename:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_path", "message": "Path traversal not allowed"},
            )
        img_dir = _IMAGE_DIRS[image_type]
        fpath = os.path.join(img_dir, filename)
        if not os.path.isfile(fpath):
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "message": f"Image '{filename}' not found"},
            )

        lower = filename.lower()
        if lower.endswith(".png"):
            media = "image/png"
        else:
            media = "image/jpeg"

        from starlette.responses import FileResponse

        return FileResponse(
            fpath,
            media_type=media,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.delete("/images/{image_type}/{filename}")
    async def delete_image(image_type: str, filename: str):
        """Delete a single detection image."""
        if image_type not in _IMAGE_DIRS:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_type", "message": "Type must be 'input' or 'output'"},
            )
        if ".." in filename or "/" in filename or "\\" in filename:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_path", "message": "Path traversal not allowed"},
            )
        fpath = os.path.join(_IMAGE_DIRS[image_type], filename)
        if not os.path.isfile(fpath):
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "message": f"Image '{filename}' not found"},
            )
        try:
            os.remove(fpath)
            return {"deleted": 1, "files": [filename]}
        except OSError as exc:
            return JSONResponse(
                status_code=500,
                content={"error": "delete_failed", "message": str(exc)},
            )

    class BulkDeleteRequest(BaseModel):
        image_type: str = "all"  # "all", "input", or "output"
        before: str | None = None  # ISO datetime — delete images modified before this
        filenames: list[str] | None = None  # explicit list of files to delete

    @app.post("/images/delete")
    async def bulk_delete_images(body: BulkDeleteRequest):
        """Bulk-delete detection images by date or explicit list.

        Uses POST instead of DELETE to allow a JSON body.
        """
        deleted = []
        errors = []

        if body.filenames:
            # Delete explicit list
            dirs_to_check = (
                _IMAGE_DIRS.items()
                if body.image_type == "all"
                else [(body.image_type, _IMAGE_DIRS.get(body.image_type, ""))]
            )
            for fname in body.filenames:
                if ".." in fname or "/" in fname or "\\" in fname:
                    errors.append(fname)
                    continue
                found = False
                for _, img_dir in dirs_to_check:
                    fpath = os.path.join(img_dir, fname)
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                            deleted.append(fname)
                            found = True
                            break
                        except OSError:
                            errors.append(fname)
                            found = True
                            break
                if not found:
                    errors.append(fname)
        elif body.before:
            # Delete images older than the given timestamp
            try:
                cutoff = datetime.fromisoformat(body.before)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_date", "message": f"Cannot parse: {body.before}"},
                )
            dirs_to_scan = (
                _IMAGE_DIRS.items()
                if body.image_type == "all"
                else [(body.image_type, _IMAGE_DIRS.get(body.image_type, ""))]
            )
            for _, img_dir in dirs_to_scan:
                if not os.path.isdir(img_dir):
                    continue
                for fname in os.listdir(img_dir):
                    fpath = os.path.join(img_dir, fname)
                    if not os.path.isfile(fpath):
                        continue
                    lower = fname.lower()
                    if not (
                        lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png")
                    ):
                        continue
                    try:
                        mtime = datetime.fromtimestamp(os.stat(fpath).st_mtime, tz=timezone.utc)
                        if mtime < cutoff:
                            os.remove(fpath)
                            deleted.append(fname)
                    except OSError:
                        errors.append(fname)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "missing_criteria", "message": "Provide 'before' or 'filenames'"},
            )

        return {"deleted": len(deleted), "errors": len(errors), "files": deleted}

    # =================================================================
    # Aggregate status (existing)
    # =================================================================

    @app.get("/status")
    async def aggregate_status():
        global _status_lock
        if _status_lock is None:
            _status_lock = asyncio.Lock()

        now = time.time()
        if (
            _status_cache["data"] is not None
            and now - _status_cache["timestamp"] < _STATUS_CACHE_TTL
        ):
            return _status_cache["data"]

        # Concurrency guard: only one /status computation at a time.
        # Other requests that arrive while computing will wait for the
        # lock, then hit the cache (which will be fresh by then).
        async with _status_lock:
            # Re-check cache under lock — another request may have
            # already refreshed it while we waited.
            now = time.time()
            if (
                _status_cache["data"] is not None
                and now - _status_cache["timestamp"] < _STATUS_CACHE_TTL
            ):
                return _status_cache["data"]

            def _compute_status() -> dict:
                health_data = _collect_health()
                # Include diagnostic temperature data from ROS2 subscriptions
                health_data["motor_temperatures"] = _motor_temperatures
                health_data["camera_temperature_c"] = _camera_temperature_c
                # Lazily register diagnostic subscriptions on first status call
                _ensure_diagnostic_subscriptions()

                # ROS2 introspection with exponential backoff.
                # If previous calls timed out, skip the expensive subprocess
                # calls entirely until the backoff period expires.
                ros2_data: dict
                now_mono = time.time()
                if now_mono < _ros2_backoff["backoff_until"]:
                    ros2_data = {
                        "available": False,
                        "node_count": None,
                        "topic_count": None,
                        "service_count": None,
                    }
                else:
                    try:
                        nodes = _ros2_node_list()
                        topics = _ros2_topic_list()
                        services = _ros2_service_list()
                        ros2_data = {
                            "available": True,
                            "node_count": len(nodes),
                            "topic_count": len(topics),
                            "service_count": len(services),
                        }
                        # Success — reset backoff and mark cold start done
                        _ros2_backoff["consecutive_failures"] = 0
                        _ros2_backoff["backoff_until"] = 0.0
                        global _ros2_first_call_done
                        _ros2_first_call_done = True
                    except (
                        FileNotFoundError,
                        RuntimeError,
                        OSError,
                        subprocess.TimeoutExpired,
                    ):
                        ros2_data = {
                            "available": False,
                            "node_count": None,
                            "topic_count": None,
                            "service_count": None,
                        }
                        # Increment backoff: 5s, 10s, 20s, 40s, 60s max
                        _ros2_backoff["consecutive_failures"] += 1
                        delay = min(
                            5.0 * (2 ** (_ros2_backoff["consecutive_failures"] - 1)),
                            _ROS2_BACKOFF_MAX,
                        )
                        _ros2_backoff["backoff_until"] = time.time() + delay
                        logger.warning(
                            "ros2 CLI failed (%d consecutive), " "backing off %.0fs",
                            _ros2_backoff["consecutive_failures"],
                            delay,
                        )

                systemd_data = _systemd_list_services()

                return {
                    "health": health_data,
                    "ros2": ros2_data,
                    "systemd": systemd_data,
                }

            result = await asyncio.to_thread(_compute_status)
            _status_cache["data"] = result
            _status_cache["timestamp"] = time.time()
            return result

    @app.post("/ros2/topics/{topic_name:path}/publish")
    async def ros2_topic_publish(topic_name: str, request: Request):
        """Publish a message to a ROS2 topic."""
        from urllib.parse import unquote

        topic_name = unquote(topic_name)
        if not topic_name.startswith("/"):
            topic_name = "/" + topic_name

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "bad_request", "message": "Invalid JSON body"},
            )

        message_type_str = body.get("message_type")
        data = body.get("data", {})

        if not message_type_str:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "bad_request",
                    "message": "Missing required field 'message_type'",
                },
            )

        # Dynamically import message type (e.g., "std_msgs/msg/Bool" -> from std_msgs.msg import Bool)
        try:
            pkg_parts = message_type_str.split("/")  # ["std_msgs", "msg", "Bool"]
            if len(pkg_parts) != 3:
                raise ImportError(f"Invalid message type format: {message_type_str}")
            module_path = f"{pkg_parts[0]}.{pkg_parts[1]}"
            class_name = pkg_parts[2]
            import importlib

            module = importlib.import_module(module_path)
            MsgClass = getattr(module, class_name)
        except (ImportError, AttributeError, ModuleNotFoundError) as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_message_type",
                    "message": f"Could not import message type '{message_type_str}': {e}",
                },
            )

        # Create publisher on demand (cached)
        node = _ensure_rclpy()
        if node is None:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "rclpy_unavailable",
                    "message": "ROS2 is not available",
                },
            )

        if topic_name not in _topic_publishers:
            with _rclpy_lock:
                if topic_name not in _topic_publishers:
                    _topic_publishers[topic_name] = node.create_publisher(MsgClass, topic_name, 10)

        # Populate message fields from data dict
        try:
            msg = MsgClass()
            for field_name, value in data.items():
                setattr(msg, field_name, value)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "bad_data",
                    "message": f"Data does not match message schema: {e}",
                },
            )

        try:
            _topic_publishers[topic_name].publish(msg)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "publish_failed", "message": str(e)},
            )

        return {"status": "published"}

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Pragati RPi Agent")
    parser.add_argument("--port", type=int, default=8091, help="Port to listen on")
    args = parser.parse_args()
    os.environ["PRAGATI_AGENT_PORT"] = str(args.port)
    application = create_app()
    uvicorn.run(application, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
