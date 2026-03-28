"""Process manager and launch API for subprocess lifecycle management.

Provides ProcessManager class for spawning, tracking, and stopping
async subprocesses with output buffering and graceful shutdown
escalation (SIGINT → SIGTERM → SIGKILL).

Also provides a FastAPI router (launch_router) with endpoints for
launching/stopping arm and vehicle ROS2 launch files.
"""

import asyncio
import datetime
import signal
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


# -----------------------------------------------------------------
# Phase sequence and marker definitions
# -----------------------------------------------------------------

_PHASE_ORDER = [
    "cleanup",
    "daemon_restart",
    "node_startup",
    "motor_homing",
    "system_ready",
]

_PHASE_DURATIONS: Dict[str, float] = {
    "cleanup": 5.0,
    "daemon_restart": 2.0,
    "node_startup": 1.0,
    "motor_homing": 7.0,
    "system_ready": 0.0,
}

_PHASE_MARKERS: Dict[str, List[str]] = {
    "cleanup": ["AUTO-CLEANUP:", "Ensuring clean launch"],
    "daemon_restart": ["daemon start", "Starting fresh daemon"],
    "node_startup": [
        "robot_state_publisher",
        "joint_state_publisher",
        "mg6010_controller",
    ],
    "motor_homing": ["yanthra_move"],
}

# Node names that trigger node_startup phase
_NODE_NAMES = [
    "robot_state_publisher",
    "joint_state_publisher",
    "mg6010_controller",
]


class LaunchPhaseTracker:
    """Track launch progress through sequential phases.

    Phases advance in order: cleanup -> daemon_restart -> node_startup
    -> motor_homing -> system_ready.

    Each output line is checked against phase markers.  When a marker
    for a *later* phase is detected, the current phase is completed
    and the new phase becomes active.
    """

    def __init__(
        self,
        on_phase_change: Optional[Callable[..., Any]] = None,
    ):
        self._on_phase_change = on_phase_change
        self._phase_index = 0  # index into _PHASE_ORDER
        self._completed: List[str] = []
        self._start_time = time.monotonic()
        self._activated = False  # True once first marker seen
        self.phase_durations = dict(_PHASE_DURATIONS)

    # -- public API --------------------------------------------------

    def process_line(self, line: str) -> None:
        """Feed an output line to the tracker for phase detection."""
        target_idx = self._match_phase(line)
        if target_idx is None:
            return

        # Ignore markers for phases we've already passed
        if target_idx < self._phase_index:
            return

        if target_idx == self._phase_index:
            # Marker matches current phase — activate if not yet
            if not self._activated:
                self._activated = True
                self._emit(
                    _PHASE_ORDER[self._phase_index], "active"
                )
        else:
            # Marker for a later phase — complete current, advance
            self._advance_to(target_idx)

    def mark_ready(self) -> None:
        """Externally mark the system as ready (final phase)."""
        ready_idx = _PHASE_ORDER.index("system_ready")
        if self._phase_index < ready_idx:
            self._advance_to(ready_idx)

    def get_progress(self) -> Dict[str, Any]:
        """Return progress dict with phase info and timing."""
        elapsed = time.monotonic() - self._start_time
        remaining = sum(
            self.phase_durations[p]
            for p in _PHASE_ORDER[self._phase_index :]
        )
        return {
            "current_phase": _PHASE_ORDER[self._phase_index],
            "completed_phases": list(self._completed),
            "elapsed_time": round(elapsed, 2),
            "estimated_remaining": round(remaining, 2),
        }

    # -- internal helpers --------------------------------------------

    def _match_phase(self, line: str) -> Optional[int]:
        """Return index of the phase matched by *line*, or None."""
        for idx, phase in enumerate(_PHASE_ORDER):
            markers = _PHASE_MARKERS.get(phase, [])
            for marker in markers:
                if marker in line:
                    return idx
        return None

    def _advance_to(self, target_idx: int) -> None:
        """Complete current phase and activate target phase."""
        # Complete current
        current = _PHASE_ORDER[self._phase_index]
        if current not in self._completed:
            if self._activated:
                self._emit(current, "complete")
            self._completed.append(current)

        # Complete any intermediate skipped phases
        for i in range(self._phase_index + 1, target_idx):
            skipped = _PHASE_ORDER[i]
            if skipped not in self._completed:
                self._completed.append(skipped)

        self._phase_index = target_idx
        self._activated = True
        self._emit(_PHASE_ORDER[target_idx], "active")

    def _emit(self, phase: str, status: str) -> None:
        """Call the on_phase_change callback if set."""
        if self._on_phase_change is not None:
            ts = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            self._on_phase_change(phase, status, ts)


class ProcessManager:
    """Manage async subprocesses with PID tracking and output buffering.

    Each process is tracked by name in an internal registry with:
    - pid: process ID
    - status: launching / running / stopped / error / stopping
    - return_code: exit code or None
    - output_buffer: deque ring buffer (max 1000 lines)
    - phase_tracker: LaunchPhaseTracker instance
    """

    def __init__(
        self,
        max_buffer_lines: int = 1000,
        stability_seconds: float = 2.0,
    ):
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._max_buffer = max_buffer_lines
        self._stability_seconds = stability_seconds
        # WebSocket subscribers: name -> set of async callback(line: str)
        self._subscribers: Dict[str, Set[Callable]] = {}

    async def start_process(
        self, name: str, cmd: str, args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Spawn a subprocess and register it.

        Raises RuntimeError if a process with *name* is already
        running or launching.
        """
        if name in self._registry and self._registry[name][
            "status"
        ] in ("running", "launching"):
            raise RuntimeError(f"Process '{name}' is already running")

        args = args or []
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        tracker = LaunchPhaseTracker(
            on_phase_change=lambda phase, status, ts: (
                asyncio.ensure_future(
                    self._broadcast(
                        name,
                        "",
                        msg_type="phase",
                        phase=phase,
                        status=status,
                        timestamp=ts,
                    )
                )
            ),
        )

        entry: Dict[str, Any] = {
            "pid": proc.pid,
            "status": "launching",
            "return_code": None,
            "output_buffer": deque(maxlen=self._max_buffer),
            "process": proc,
            "phase_tracker": tracker,
        }
        self._registry[name] = entry

        # Start background reader tasks
        asyncio.ensure_future(
            self._read_stream(name, proc.stdout, "stdout")
        )
        asyncio.ensure_future(
            self._read_stream(name, proc.stderr, "stderr")
        )
        asyncio.ensure_future(self._wait_process(name, proc))
        asyncio.ensure_future(self._stability_check(name, proc))

        return entry

    async def _stability_check(
        self, name: str, proc: asyncio.subprocess.Process
    ) -> None:
        """Check process health every 0.5s; after stable for
        stability_seconds, transition launching -> running."""
        check_interval = 0.5
        elapsed_stable = 0.0

        while elapsed_stable < self._stability_seconds:
            await asyncio.sleep(check_interval)
            if name not in self._registry:
                return
            entry = self._registry[name]
            if entry["status"] != "launching":
                return  # already transitioned (error/stopped/etc.)
            if proc.returncode is not None:
                # Process died during launch
                entry["status"] = "error"
                entry["return_code"] = proc.returncode
                return
            elapsed_stable += check_interval

        # Process survived the stability window
        if name in self._registry:
            entry = self._registry[name]
            if entry["status"] == "launching":
                entry["status"] = "running"
                entry["phase_tracker"].mark_ready()

    def subscribe(self, name: str, callback: Callable) -> None:
        """Register an async callback to receive output lines for *name*.

        On subscribe, the callback receives the current buffer contents
        (reconnection support — last 1000 lines).
        """
        if name not in self._subscribers:
            self._subscribers[name] = set()
        self._subscribers[name].add(callback)

    def unsubscribe(self, name: str, callback: Callable) -> None:
        """Remove a subscriber callback."""
        if name in self._subscribers:
            self._subscribers[name].discard(callback)
            if not self._subscribers[name]:
                del self._subscribers[name]

    async def _broadcast(
        self,
        name: str,
        line: str,
        *,
        msg_type: str = "output",
        phase: Optional[str] = None,
        status: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """Send a structured message to all subscribers for *name*.

        For output lines: ``{"type": "output", "data": "<line>"}``
        For phase events: ``{"type": "phase", "phase": "...",
        "status": "active"|"complete", "timestamp": "..."}``
        """
        if name not in self._subscribers:
            return

        if msg_type == "phase":
            message: Dict[str, Any] = {
                "type": "phase",
                "phase": phase,
                "status": status,
                "timestamp": timestamp,
            }
        else:
            message = {"type": "output", "data": line}

        dead: List[Callable] = []
        for cb in list(self._subscribers.get(name, set())):
            try:
                await cb(message)
            except Exception:
                dead.append(cb)
        for cb in dead:
            self._subscribers.get(name, set()).discard(cb)

    async def get_buffered_output(self, name: str) -> List[str]:
        """Return all buffered output for reconnection support."""
        if name not in self._registry:
            return []
        return list(self._registry[name]["output_buffer"])

    async def _read_stream(
        self, name: str, stream: asyncio.StreamReader, label: str
    ) -> None:
        """Read lines from *stream* into output buffer, broadcast, and feed tracker."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                if name in self._registry:
                    decoded = line.decode(
                        "utf-8", errors="replace"
                    ).rstrip("\n")
                    tagged = f"[{label}] {decoded}"
                    entry = self._registry[name]
                    entry["output_buffer"].append(tagged)
                    await self._broadcast(name, tagged)
                    # Feed to phase tracker
                    tracker = entry.get("phase_tracker")
                    if tracker is not None:
                        tracker.process_line(decoded)
        except Exception:
            pass

    async def _wait_process(
        self, name: str, proc: asyncio.subprocess.Process
    ) -> None:
        """Wait for the process to exit and update status."""
        try:
            return_code = await proc.wait()
            if name in self._registry:
                entry = self._registry[name]
                entry["return_code"] = return_code
                if entry["status"] in ("running", "launching"):
                    entry["status"] = (
                        "stopped" if return_code == 0 else "error"
                    )
        except Exception:
            pass

    async def stop_process(self, name: str) -> None:
        """Stop a process with graceful escalation.

        Sequence: SIGINT → wait 10s → SIGTERM → wait 5s → SIGKILL.
        """
        if name not in self._registry:
            return

        entry = self._registry[name]
        if entry["status"] not in ("running", "launching"):
            return

        proc = entry["process"]
        entry["status"] = "stopping"

        # Step 1: SIGINT
        try:
            proc.send_signal(signal.SIGINT)
            await asyncio.wait_for(proc.wait(), timeout=10.0)
            entry["return_code"] = proc.returncode
            entry["status"] = "stopped"
            return
        except asyncio.TimeoutError:
            pass

        # Step 2: SIGTERM
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            entry["return_code"] = proc.returncode
            entry["status"] = "stopped"
            return
        except asyncio.TimeoutError:
            pass

        # Step 3: SIGKILL
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        entry["return_code"] = proc.returncode
        entry["status"] = "stopped"

    def get_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Return status dict for *name*, or None if unknown."""
        if name not in self._registry:
            return None

        entry = self._registry[name]
        return {
            "pid": entry["pid"],
            "status": entry["status"],
            "return_code": entry["return_code"],
            "output_buffer": list(entry["output_buffer"]),
        }

    def get_output(self, name: str, last_n: int = 100) -> List[str]:
        """Return last *last_n* lines of captured output."""
        if name not in self._registry:
            return []

        buf = self._registry[name]["output_buffer"]
        items = list(buf)
        return items[-last_n:]

    async def stop_all(self) -> None:
        """Stop all running or launching processes."""
        running = [
            name
            for name, entry in self._registry.items()
            if entry["status"] in ("running", "launching")
        ]
        for name in running:
            await self.stop_process(name)


# -----------------------------------------------------------------
# Module-level dependencies (injected at startup)
# -----------------------------------------------------------------

_process_manager: Optional[ProcessManager] = None
_audit_logger: Optional[Any] = None  # AuditLogger, kept as Any to avoid circular


def set_process_manager(pm: Optional[ProcessManager]) -> None:
    """Set the module-level ProcessManager for router endpoints."""
    global _process_manager
    _process_manager = pm


def set_audit_logger(al: Optional[Any]) -> None:
    """Set the module-level AuditLogger for router endpoints."""
    global _audit_logger
    _audit_logger = al


def _get_pm() -> ProcessManager:
    """Return the module-level ProcessManager or raise."""
    if _process_manager is None:
        raise HTTPException(
            status_code=503, detail="ProcessManager not initialized"
        )
    return _process_manager


def _log_audit(action: str, params: Dict[str, Any], result: str) -> None:
    """Log via AuditLogger if available."""
    if _audit_logger is not None:
        _audit_logger.log(action, params, result)


# -----------------------------------------------------------------
# Allowlist: only known launch files are permitted
# -----------------------------------------------------------------

_ALLOWED_LAUNCHES: Dict[str, Dict[str, str]] = {
    "arm": {
        "package": "yanthra_move",
        "launch_file": "pragati_complete.launch.py",
    },
    "vehicle": {
        "package": "yanthra_move",
        "launch_file": "pragati_complete.launch.py",
    },
}

# -----------------------------------------------------------------
# Expected vehicle subsystems for detection
# -----------------------------------------------------------------

_VEHICLE_SUBSYSTEMS: List[str] = [
    "steering_controller",
    "drive_controller",
    "vehicle_state_machine",
    "sensor_fusion",
    "mqtt_bridge",
]


# -----------------------------------------------------------------
# Request / Response models
# -----------------------------------------------------------------


class ArmLaunchRequest(BaseModel):
    """Body for POST /api/launch/arm."""

    use_simulation: bool = True
    enable_arm_client: bool = True
    enable_cotton_detection: bool = True


class VehicleLaunchRequest(BaseModel):
    """Body for POST /api/launch/vehicle."""

    params: Dict[str, Any] = {}


# -----------------------------------------------------------------
# Router
# -----------------------------------------------------------------

launch_router = APIRouter()


# ---- Arm endpoints ----


@launch_router.post("/api/launch/arm")
async def launch_arm(body: ArmLaunchRequest) -> Dict[str, Any]:
    """Launch the arm bringup ROS2 launch file."""
    pm = _get_pm()
    launch_info = _ALLOWED_LAUNCHES["arm"]
    params = body.model_dump()

    args = [
        "launch",
        launch_info["package"],
        launch_info["launch_file"],
        f"use_simulation:={str(params['use_simulation']).lower()}",
        f"enable_arm_client:={str(params['enable_arm_client']).lower()}",
        f"enable_cotton_detection:={str(params['enable_cotton_detection']).lower()}",
    ]

    try:
        await pm.start_process("arm", "ros2", args)
    except RuntimeError:
        raise HTTPException(
            status_code=409, detail="Arm process is already running"
        )

    _log_audit("arm_launch", params, "launched")
    return {"status": "launched", "params": params}


@launch_router.post("/api/launch/arm/stop")
async def stop_arm() -> Dict[str, Any]:
    """Stop the arm process."""
    pm = _get_pm()
    status = pm.get_status("arm")
    if status is None or status["status"] not in (
        "running",
        "launching",
        "stopping",
    ):
        raise HTTPException(status_code=404, detail="Arm process not running")

    await pm.stop_process("arm")
    _log_audit("arm_stop", {}, "stopped")
    return {"status": "stopped"}


@launch_router.get("/api/launch/arm/status")
async def arm_status() -> Dict[str, Any]:
    """Return arm process status."""
    pm = _get_pm()
    status = pm.get_status("arm")
    if status is None:
        return {"status": "not_running", "pid": None, "return_code": None}
    return {
        "status": status["status"],
        "pid": status["pid"],
        "return_code": status["return_code"],
    }


# ---- Vehicle endpoints ----


@launch_router.post("/api/launch/vehicle")
async def launch_vehicle(body: VehicleLaunchRequest) -> Dict[str, Any]:
    """Launch the vehicle bringup ROS2 launch file."""
    pm = _get_pm()
    launch_info = _ALLOWED_LAUNCHES["vehicle"]
    params = body.model_dump()

    args = [
        "launch",
        launch_info["package"],
        launch_info["launch_file"],
    ]

    try:
        await pm.start_process("vehicle", "ros2", args)
    except RuntimeError:
        raise HTTPException(
            status_code=409, detail="Vehicle process is already running"
        )

    _log_audit("vehicle_launch", params, "launched")
    return {"status": "launched", "params": params}


@launch_router.post("/api/launch/vehicle/stop")
async def stop_vehicle() -> Dict[str, Any]:
    """Stop the vehicle process."""
    pm = _get_pm()
    status = pm.get_status("vehicle")
    if status is None or status["status"] not in (
        "running",
        "launching",
        "stopping",
    ):
        raise HTTPException(
            status_code=404, detail="Vehicle process not running"
        )

    await pm.stop_process("vehicle")
    _log_audit("vehicle_stop", {}, "stopped")
    return {"status": "stopped"}


@launch_router.get("/api/launch/vehicle/status")
async def vehicle_status() -> Dict[str, Any]:
    """Return vehicle process status."""
    pm = _get_pm()
    status = pm.get_status("vehicle")
    if status is None:
        return {"status": "not_running", "pid": None, "return_code": None}
    return {
        "status": status["status"],
        "pid": status["pid"],
        "return_code": status["return_code"],
    }


@launch_router.get("/api/launch/vehicle/subsystems")
async def vehicle_subsystems() -> Dict[str, Any]:
    """Return expected vehicle subsystems and their detected state.

    Detection: grep the vehicle process output buffer for node name
    patterns like ``[node_name]``.
    """
    pm = _get_pm()
    status = pm.get_status("vehicle")

    if status is None or status["status"] not in (
        "running",
        "launching",
        "stopping",
    ):
        # Vehicle not running — all inactive
        return {
            "subsystems": [
                {"name": name, "status": "inactive"}
                for name in _VEHICLE_SUBSYSTEMS
            ]
        }

    # Grep output buffer for subsystem node name patterns
    output_lines = pm.get_output("vehicle", last_n=1000)
    detected: Dict[str, str] = {}
    for name in _VEHICLE_SUBSYSTEMS:
        pattern = f"[{name}]"
        if any(pattern in line for line in output_lines):
            detected[name] = "active"
        else:
            detected[name] = "unknown"

    return {
        "subsystems": [
            {"name": name, "status": detected.get(name, "unknown")}
            for name in _VEHICLE_SUBSYSTEMS
        ]
    }
