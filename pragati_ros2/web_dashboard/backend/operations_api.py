"""Operations API — unified sync.sh operation runner with multi-target support.

Provides OperationsManager for running sync.sh operations against fleet
entities with operation ID tracking, per-target subprocess state, sequential
multi-target execution, SSE streaming, cancellation, and timeout support.

Replaces the limited /api/sync/ endpoints with a richer operations model
that supports all 12 sync.sh operations with entity-aware targeting.
"""

import asyncio
import datetime
import logging
import os
import re
import signal
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_OUTPUT_LINES = 5000
DEFAULT_TIMEOUT_S = 600  # 10 minutes
CANCEL_GRACE_S = 5  # SIGTERM grace before SIGKILL
STREAM_DRAIN_TIMEOUT_S = 5  # max wait for stream readers after process death
OPERATIONS_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "operations_logs"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operation definitions — maps operation name to sync.sh flags
# ---------------------------------------------------------------------------

OPERATION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "deploy-cross": {
        "flags": ["--deploy-cross", "--ip", "{ip}"],
        "label": "Deploy (cross-compiled)",
        "description": "Deploy cross-compiled ARM binaries from install_rpi/",
        "params": [],
    },
    "deploy-cross-restart": {
        "flags": ["--deploy-cross", "--restart", "--ip", "{ip}"],
        "label": "Deploy Cross + Restart",
        "description": "Deploy cross-compiled ARM binaries and restart all services",
        "params": [],
    },
    "deploy-local": {
        "flags": ["--deploy-local", "--ip", "{ip}"],
        "label": "Deploy (local)",
        "description": "Deploy locally-built x86 binaries from install/",
        "params": [],
    },
    "build": {
        "flags": ["--build", "--ip", "{ip}"],
        "label": "Build on RPi",
        "description": "Sync source and trigger native build on RPi",
        "params": [],
    },
    "quick-sync": {
        "flags": ["--quick", "--ip", "{ip}"],
        "label": "Quick sync",
        "description": "Quick source sync without full build",
        "params": [],
    },
    "provision": {
        "flags": ["--provision", "--ip", "{ip}"],
        "label": "Provision",
        "description": "Apply OS fixes and install systemd services",
        "params": [],
    },
    "set-role": {
        "flags": ["--provision", "--role", "{role}", "--ip", "{ip}"],
        "label": "Set role",
        "description": "Set entity role (arm or vehicle)",
        "params": ["role"],
    },
    "set-arm-identity": {
        "flags": ["--provision", "--arm-id", "{arm_id}", "--ip", "{ip}"],
        "label": "Set arm identity",
        "description": "Set arm ID (1-6)",
        "params": ["arm_id"],
    },
    "set-mqtt-address": {
        "flags": ["--mqtt-address", "{mqtt_address}", "--ip", "{ip}"],
        "label": "Set MQTT address",
        "description": "Configure MQTT broker address",
        "params": ["mqtt_address"],
    },
    "collect-logs": {
        "flags": ["--collect-logs", "--ip", "{ip}"],
        "label": "Collect logs",
        "description": "Pull field trial logs from RPi",
        "params": [],
    },
    "verify": {
        "flags": ["--verify", "--ip", "{ip}"],
        "label": "Verify",
        "description": "Verify deployment on RPi",
        "params": [],
    },
    "restart": {
        "flags": ["--restart", "--ip", "{ip}"],
        "label": "Restart services",
        "description": "Restart systemd services on RPi",
        "params": [],
    },
    "test-mqtt": {
        "flags": ["--test-mqtt", "--ip", "{ip}"],
        "label": "Test MQTT",
        "description": "Test MQTT connectivity",
        "params": [],
    },
    "time-sync": {
        "flags": ["--time-sync", "--ip", "{ip}"],
        "label": "Time sync",
        "description": "Sync RPi clock from dev machine",
        "params": [],
    },
}

ALLOWED_OPERATIONS = frozenset(OPERATION_DEFINITIONS.keys())

_IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}" r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)

# ---------------------------------------------------------------------------
# Target status constants
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_TIMEOUT = "timeout"

# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class OperationRunRequest(BaseModel):
    """Request body for POST /api/operations/run."""

    operation: str
    target_ids: List[str]
    params: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Per-target state
# ---------------------------------------------------------------------------


class TargetState:
    """Tracks the state of a sync.sh subprocess for one target."""

    __slots__ = (
        "target_id",
        "ip",
        "status",
        "exit_code",
        "process",
        "started_at",
        "finished_at",
    )

    def __init__(self, target_id: str, ip: str):
        self.target_id = target_id
        self.ip = ip
        self.status: str = STATUS_PENDING
        self.exit_code: Optional[int] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "ip": self.ip,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


# ---------------------------------------------------------------------------
# Operation state
# ---------------------------------------------------------------------------


class Operation:
    """Tracks the full state of a multi-target operation."""

    def __init__(
        self,
        operation_id: str,
        operation_name: str,
        targets: List[TargetState],
        timeout_seconds: float,
    ):
        self.operation_id = operation_id
        self.operation_name = operation_name
        self.targets = targets
        self.timeout_seconds = timeout_seconds
        self.output_buffer: deque = deque(maxlen=MAX_OUTPUT_LINES)
        self.sse_subscribers: Set[asyncio.Queue] = set()
        self.started_at = _now_iso()
        self.finished_at: Optional[str] = None
        self._cancelled = False
        self._run_task: Optional[asyncio.Task] = None

    @property
    def is_active(self) -> bool:
        """True if any target is still pending or running."""
        return any(t.status in (STATUS_PENDING, STATUS_RUNNING) for t in self.targets)

    @property
    def current_target(self) -> Optional[TargetState]:
        """Return the currently running target, if any."""
        for t in self.targets:
            if t.status == STATUS_RUNNING:
                return t
        return None

    def summary(self) -> Dict[str, int]:
        """Return summary counts."""
        total = len(self.targets)
        succeeded = sum(1 for t in self.targets if t.status == STATUS_SUCCESS)
        failed = sum(1 for t in self.targets if t.status in (STATUS_FAILED, STATUS_TIMEOUT))
        cancelled = sum(1 for t in self.targets if t.status == STATUS_CANCELLED)
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "cancelled": cancelled,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation": self.operation_name,
            "targets": [t.to_dict() for t in self.targets],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "is_active": self.is_active,
            "summary": self.summary(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _build_sync_args(operation_name: str, ip: str, params: Dict[str, Any]) -> List[str]:
    """Build sync.sh argument list from operation definition and params.

    Raises ValueError if required params are missing or invalid.
    """
    defn = OPERATION_DEFINITIONS[operation_name]
    args = []
    for flag in defn["flags"]:
        if flag == "{ip}":
            args.append(ip)
        elif flag.startswith("{") and flag.endswith("}"):
            param_name = flag[1:-1]
            if param_name not in params:
                raise ValueError(f"Missing required parameter: {param_name}")
            args.append(str(params[param_name]))
        else:
            args.append(flag)
    return args


def validate_params(operation_name: str, params: Dict[str, Any]) -> None:
    """Validate operation-specific parameters.

    Raises ValueError on invalid parameters.
    """
    if operation_name == "set-role":
        role = params.get("role")
        if role not in ("arm", "vehicle"):
            raise ValueError(f"Invalid role: {role}. Must be 'arm' or 'vehicle'.")
    elif operation_name == "set-arm-identity":
        arm_id = params.get("arm_id")
        try:
            arm_id_int = int(arm_id)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid arm_id: {arm_id}. Must be 1-6.")
        if arm_id_int < 1 or arm_id_int > 6:
            raise ValueError(f"Invalid arm_id: {arm_id_int}. Must be 1-6.")
    elif operation_name == "set-mqtt-address":
        addr = params.get("mqtt_address")
        if not addr or not _IPV4_PATTERN.match(str(addr)):
            raise ValueError(f"Invalid mqtt_address: {addr}. Must be a valid IPv4.")


# ---------------------------------------------------------------------------
# OperationsManager
# ---------------------------------------------------------------------------


class OperationsManager:
    """Manages sync.sh operations with multi-target support.

    Supports operation ID tracking, per-target subprocess state,
    sequential multi-target execution, SSE streaming, cancellation,
    timeout, and conflict detection.
    """

    def __init__(self, sync_sh_path: str = ""):
        self._sync_sh_path = sync_sh_path
        self._operations: Dict[str, Operation] = {}
        # Track active target IPs to prevent conflicts
        self._active_targets: Dict[str, str] = {}  # ip -> operation_id
        self._entity_manager: Any = None
        self._audit_logger: Any = None

    # -- Properties ----------------------------------------------------

    @property
    def available(self) -> bool:
        """Check if sync.sh exists and is a file."""
        p = Path(self._sync_sh_path)
        return p.is_file()

    # -- Dependency setters --------------------------------------------

    def set_entity_manager(self, em: Any) -> None:
        """Inject the entity manager for target resolution."""
        self._entity_manager = em

    def set_audit_logger(self, logger: Any) -> None:
        """Inject the audit logger."""
        self._audit_logger = logger

    # -- Target resolution ---------------------------------------------

    def resolve_targets(self, target_ids: List[str]) -> List[TargetState]:
        """Resolve target IDs to TargetState objects with IPs.

        Supports:
        - Entity IDs resolved via entity manager
        - ["all"] to target all known entities that are online and configured
        - Raw IPv4 addresses as fallback

        Raises ValueError if a target cannot be resolved.
        """
        if target_ids == ["all"]:
            if self._entity_manager is None:
                raise ValueError("Entity manager unavailable; cannot resolve 'all'")
            entities = self._entity_manager.get_all_entities()
            if not entities:
                raise ValueError("No entities found")
            # Filter to online, remote, configured entities only
            targets = [
                TargetState(target_id=e.id, ip=e.ip)
                for e in entities
                if e.ip is not None
                and e.source != "local"  # Don't deploy to dev machine
                and e.status not in ("offline", "unknown")
                and e.group_id  # Must be assigned to a group
            ]
            if not targets:
                raise ValueError(
                    "No online, configured entities found. "
                    "Check that entities are online and assigned to a group."
                )
            return targets

        results = []
        for tid in target_ids:
            # Try entity manager first
            if self._entity_manager is not None:
                entity = self._entity_manager.get_entity(tid)
                if entity is not None:
                    if entity.ip is None:
                        raise ValueError(f"Entity '{tid}' has no IP address")
                    results.append(TargetState(target_id=entity.id, ip=entity.ip))
                    continue

            # Fallback: treat as raw IP
            if _IPV4_PATTERN.match(tid):
                results.append(TargetState(target_id=tid, ip=tid))
                continue

            raise ValueError(f"Cannot resolve target: {tid}")

        return results

    # -- Conflict detection --------------------------------------------

    def _check_conflicts(self, targets: List[TargetState]) -> Optional[str]:
        """Check if any target IP already has an active operation.

        Returns the conflicting target ID or None.
        Automatically clears stale locks for operations that are no longer active.
        """
        for t in targets:
            if t.ip in self._active_targets:
                # Safety net: verify the referenced operation is truly active
                ref_op_id = self._active_targets[t.ip]
                ref_op = self._operations.get(ref_op_id)
                if ref_op is None or not ref_op.is_active:
                    # Stale lock — clean it up
                    logger.warning(
                        "Clearing stale lock for ip=%s (op=%s)",
                        t.ip,
                        ref_op_id,
                    )
                    self._active_targets.pop(t.ip, None)
                    continue
                return t.target_id
        return None

    # -- Run operation -------------------------------------------------

    async def run_operation(
        self,
        operation_name: str,
        target_ids: List[str],
        params: Dict[str, Any],
    ) -> Operation:
        """Start a new operation.

        Returns the Operation object with an assigned ID.

        Raises:
            FileNotFoundError: sync.sh not available
            ValueError: Invalid operation, params, or targets
            RuntimeError: Conflict with active operation
        """
        if not self.available:
            raise FileNotFoundError("sync.sh not found")

        if operation_name not in ALLOWED_OPERATIONS:
            raise ValueError(f"Unknown operation: {operation_name}")

        # Validate params
        validate_params(operation_name, params)

        # Resolve targets
        targets = self.resolve_targets(target_ids)
        if not targets:
            raise ValueError("No valid targets resolved")

        # Check conflicts
        conflict = self._check_conflicts(targets)
        if conflict is not None:
            raise RuntimeError(f"Operation already active for target: {conflict}")

        # Create operation
        timeout_s = float(params.get("timeout_seconds", DEFAULT_TIMEOUT_S))
        operation_id = f"op-{uuid.uuid4().hex[:12]}"
        op = Operation(
            operation_id=operation_id,
            operation_name=operation_name,
            targets=targets,
            timeout_seconds=timeout_s,
        )
        self._operations[operation_id] = op

        # Mark targets as active
        for t in targets:
            self._active_targets[t.ip] = operation_id

        # Start execution in background
        op._run_task = asyncio.create_task(self._execute_operation(op, operation_name, params))

        if self._audit_logger:
            self._audit_logger.log(
                "operations.run",
                {
                    "operation": operation_name,
                    "targets": [t.target_id for t in targets],
                },
                "started",
            )

        return op

    # -- Sequential execution ------------------------------------------

    async def _execute_operation(
        self,
        op: Operation,
        operation_name: str,
        params: Dict[str, Any],
    ) -> None:
        """Execute sync.sh sequentially for each target."""
        try:
            for target in op.targets:
                if op._cancelled:
                    target.status = STATUS_CANCELLED
                    continue

                await self._run_target(op, target, operation_name, params)
        finally:
            op.finished_at = _now_iso()
            # Release active target locks
            for t in op.targets:
                self._active_targets.pop(t.ip, None)
            # Persist output to log file
            self._persist_operation_log(op)
            # Send operation_complete event
            await self._broadcast_event(
                op,
                {
                    "event": "operation_complete",
                    "summary": op.summary(),
                },
            )

    def _persist_operation_log(self, op: Operation) -> None:
        """Write operation output to a persistent log file.

        Logs are saved to ``data/operations_logs/<date>/<op_name>_<op_id>.log``
        so they survive server restarts.
        """
        try:
            date_str = datetime.date.today().isoformat()
            log_dir = OPERATIONS_LOG_DIR / date_str
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{op.operation_name}_{op.operation_id}.log"

            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"Operation: {op.operation_name}\n")
                f.write(f"ID:        {op.operation_id}\n")
                f.write(f"Started:   {op.started_at}\n")
                f.write(f"Finished:  {op.finished_at}\n")
                f.write(f"Targets:   {', '.join(t.target_id for t in op.targets)}\n")
                f.write(f"Summary:   {op.summary()}\n")
                f.write("=" * 72 + "\n\n")

                for event in op.output_buffer:
                    if event.get("event") == "output":
                        f.write(event.get("line", "") + "\n")
                    elif event.get("event") in ("start", "complete", "timeout", "error"):
                        target_id = event.get("target", "?")
                        evt = event.get("event")
                        detail = ""
                        if evt == "complete":
                            detail = f" (exit code: {event.get('exit_code', '?')})"
                        elif evt == "error":
                            detail = f": {event.get('detail', '')}"
                        f.write(f"--- {evt}: {target_id}{detail} ---\n")

            logger.info("Operation log saved to %s", log_file)
        except Exception:
            logger.exception("Failed to persist operation log for %s", op.operation_id)

    async def _run_target(
        self,
        op: Operation,
        target: TargetState,
        operation_name: str,
        params: Dict[str, Any],
    ) -> None:
        """Run sync.sh for a single target with timeout."""
        target.status = STATUS_RUNNING
        target.started_at = _now_iso()

        # Broadcast target start event
        await self._broadcast_event(
            op,
            {
                "target": target.target_id,
                "event": "start",
            },
        )

        try:
            args = _build_sync_args(operation_name, target.ip, params)
            proc = await asyncio.create_subprocess_exec(
                self._sync_sh_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # own process group for clean kill
            )
            target.process = proc

            # Start stream readers
            stdout_task = asyncio.create_task(self._read_stream(op, target, proc.stdout, "stdout"))
            stderr_task = asyncio.create_task(self._read_stream(op, target, proc.stderr, "stderr"))

            # Wait with timeout
            try:
                await asyncio.wait_for(proc.wait(), timeout=op.timeout_seconds)
            except asyncio.TimeoutError:
                # Timeout — kill the process group
                await self._terminate_process(proc)
                target.status = STATUS_TIMEOUT
                target.finished_at = _now_iso()
                await self._broadcast_event(
                    op,
                    {
                        "target": target.target_id,
                        "event": "timeout",
                    },
                )
                # Wait for stream readers with a bounded timeout
                await self._drain_streams(stdout_task, stderr_task)
                return

            # Wait for stream readers with a bounded timeout
            await self._drain_streams(stdout_task, stderr_task)

            target.exit_code = proc.returncode
            target.status = STATUS_SUCCESS if proc.returncode == 0 else STATUS_FAILED
            target.finished_at = _now_iso()

            # Broadcast completion
            await self._broadcast_event(
                op,
                {
                    "target": target.target_id,
                    "event": "complete",
                    "exit_code": proc.returncode,
                },
            )

        except asyncio.CancelledError:
            target.status = STATUS_CANCELLED
            target.finished_at = _now_iso()
        except Exception as exc:
            target.status = STATUS_FAILED
            target.finished_at = _now_iso()
            await self._broadcast_event(
                op,
                {
                    "target": target.target_id,
                    "event": "error",
                    "detail": str(exc),
                },
            )

    # -- Process termination -------------------------------------------

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        """SIGTERM with grace period, then SIGKILL.

        Kills the entire process group (sync.sh + child rsync/ssh) so
        orphaned children don't hold pipes open and stall stream readers.
        """
        pid = proc.pid
        try:
            # Kill entire process group so children (rsync, ssh) also die
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            # Fallback to single-process signal
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                return

        try:
            await asyncio.wait_for(proc.wait(), timeout=CANCEL_GRACE_S)
            return
        except asyncio.TimeoutError:
            pass

        # Escalate to SIGKILL on the process group
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                return

        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

    # -- Stream helpers ------------------------------------------------

    async def _drain_streams(self, *tasks: asyncio.Task) -> None:
        """Wait for stream reader tasks with a bounded timeout.

        If child processes (rsync, ssh) survive the parent kill and keep
        pipes open, the readers would hang forever. This prevents that.
        """
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=STREAM_DRAIN_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("Stream readers timed out — cancelling")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # -- Stream reading ------------------------------------------------

    async def _read_stream(
        self,
        op: Operation,
        target: TargetState,
        stream: asyncio.StreamReader,
        stream_name: str,
    ) -> None:
        """Read lines from subprocess stream, buffer and broadcast."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                timestamp = _now_iso()
                event = {
                    "event": "output",
                    "target": target.target_id,
                    "stream": stream_name,
                    "line": decoded,
                    "timestamp": timestamp,
                }
                op.output_buffer.append(event)
                await self._broadcast_event(op, event)
        except (asyncio.CancelledError, Exception):
            pass

    # -- SSE broadcasting ----------------------------------------------

    async def _broadcast_event(self, op: Operation, event: Dict[str, Any]) -> None:
        """Send an event to all SSE subscribers for this operation."""
        dead: List[asyncio.Queue] = []
        for queue in list(op.sse_subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        for q in dead:
            op.sse_subscribers.discard(q)

    def subscribe(self, operation_id: str) -> Optional[asyncio.Queue]:
        """Subscribe to SSE events for an operation.

        Returns a Queue to read events from, or None if operation
        not found.
        """
        op = self._operations.get(operation_id)
        if op is None:
            return None
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        op.sse_subscribers.add(queue)
        return queue

    def unsubscribe(self, operation_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from SSE events."""
        op = self._operations.get(operation_id)
        if op is not None:
            op.sse_subscribers.discard(queue)

    def get_buffered_output(self, operation_id: str) -> List[Dict[str, Any]]:
        """Return buffered output for replay-on-reconnect."""
        op = self._operations.get(operation_id)
        if op is None:
            return []
        return list(op.output_buffer)

    # -- Cancel --------------------------------------------------------

    async def cancel_operation(self, operation_id: str) -> Dict[str, Any]:
        """Cancel an operation.

        Raises:
            KeyError: Unknown operation ID
            RuntimeError: Operation already completed
        """
        op = self._operations.get(operation_id)
        if op is None:
            raise KeyError(f"Unknown operation: {operation_id}")

        if not op.is_active:
            raise RuntimeError("Operation already completed")

        op._cancelled = True

        # Terminate currently running process
        current = op.current_target
        if current is not None and current.process is not None:
            await self._terminate_process(current.process)
            current.status = STATUS_CANCELLED
            current.finished_at = _now_iso()

        # Mark pending targets as cancelled
        for t in op.targets:
            if t.status == STATUS_PENDING:
                t.status = STATUS_CANCELLED
                t.finished_at = _now_iso()

        # Eagerly release active-target locks so new operations can start
        # immediately. The _execute_operation finally block may also pop
        # these, but it can be stuck waiting on stream readers.
        for t in op.targets:
            self._active_targets.pop(t.ip, None)

        targets_cancelled = [t.target_id for t in op.targets if t.status == STATUS_CANCELLED]

        if self._audit_logger:
            self._audit_logger.log(
                "operations.cancel",
                {"operation_id": operation_id},
                "cancelled",
            )

        return {
            "status": "cancelled",
            "targets_cancelled": targets_cancelled,
        }

    # -- Active operations query ---------------------------------------

    def get_active_operations(self) -> List[Dict[str, Any]]:
        """Return all currently active operations."""
        return [op.to_dict() for op in self._operations.values() if op.is_active]

    # -- Get operation -------------------------------------------------

    def get_operation(self, operation_id: str) -> Optional[Operation]:
        """Get operation by ID."""
        return self._operations.get(operation_id)


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_operations_manager: Optional[OperationsManager] = None
_audit_logger: Any = None


def set_audit_logger(logger: Any) -> None:
    """Set the module-level audit logger."""
    global _audit_logger
    _audit_logger = logger
    if _operations_manager is not None:
        _operations_manager.set_audit_logger(logger)


def get_operations_manager() -> Optional[OperationsManager]:
    """Return the module-level OperationsManager (None if not created)."""
    return _operations_manager


def _get_manager() -> OperationsManager:
    """Get or create the module-level OperationsManager."""
    global _operations_manager
    if _operations_manager is None:
        repo_root = Path(__file__).parent.parent.parent
        sync_sh = repo_root / "sync.sh"
        _operations_manager = OperationsManager(
            sync_sh_path=str(sync_sh),
        )
        if _audit_logger:
            _operations_manager.set_audit_logger(_audit_logger)
    return _operations_manager


def set_entity_manager(em: Any) -> None:
    """Inject entity manager into the operations manager."""
    mgr = _get_manager()
    mgr.set_entity_manager(em)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

operations_router = APIRouter(prefix="/api/operations", tags=["operations"])


@operations_router.get("/definitions")
async def get_definitions():
    """Return all operation definitions for the frontend."""
    return {
        name: {
            "label": defn["label"],
            "description": defn["description"],
            "params": defn["params"],
        }
        for name, defn in OPERATION_DEFINITIONS.items()
    }


@operations_router.get("/available")
async def get_available():
    """Check if sync.sh is available."""
    mgr = _get_manager()
    return {"available": mgr.available}


@operations_router.post("/run")
async def post_run(req: OperationRunRequest):
    """Start an operation."""
    mgr = _get_manager()

    try:
        op = await mgr.run_operation(req.operation, req.target_ids, req.params)
        return {
            "operation_id": op.operation_id,
            "targets": [
                {"target_id": t.target_id, "ip": t.ip, "status": t.status} for t in op.targets
            ],
            "status": "started",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@operations_router.get("/{operation_id}/stream")
async def get_stream(operation_id: str, request: Request):
    """SSE streaming endpoint for operation output."""
    mgr = _get_manager()
    op = mgr.get_operation(operation_id)
    if op is None:
        raise HTTPException(status_code=404, detail=f"Operation not found: {operation_id}")

    queue = mgr.subscribe(operation_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Operation not found")

    async def event_generator():
        import json

        try:
            # Replay buffered output
            buffered = mgr.get_buffered_output(operation_id)
            for event in buffered:
                yield f"data: {json.dumps(event)}\n\n"

            # Stream live events
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"

                    # If operation complete, close stream
                    if event.get("event") == "operation_complete":
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        finally:
            mgr.unsubscribe(operation_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@operations_router.post("/{operation_id}/cancel")
async def post_cancel(operation_id: str):
    """Cancel an operation."""
    mgr = _get_manager()

    try:
        result = await mgr.cancel_operation(operation_id)
        return result
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@operations_router.get("/active")
async def get_active():
    """List active operations."""
    mgr = _get_manager()
    return {"operations": mgr.get_active_operations()}
