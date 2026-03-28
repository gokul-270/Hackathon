"""Sync.sh integration API for remote deployment operations.

Provides endpoints for running sync.sh operations (deploy, build,
provision, collect-logs) against target Raspberry Pi devices.
Operations are serialized — only one can run at a time.
"""

import asyncio
import json
import re
import signal
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


# -----------------------------------------------------------------
# Constants
# -----------------------------------------------------------------

ALLOWED_OPERATIONS = frozenset(
    {
        "deploy-cross",
        "deploy-local",
        "build",
        "provision",
        "collect-logs",
    }
)

_IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)

MAX_OUTPUT_LINES = 1000
MAX_RECENT_IPS = 5


# -----------------------------------------------------------------
# Request/response models
# -----------------------------------------------------------------


class RunRequest(BaseModel):
    operation: str
    target_ip: str


class ConfigRequest(BaseModel):
    target_ips: List[str]


# -----------------------------------------------------------------
# SyncManager
# -----------------------------------------------------------------


class SyncManager:
    """Manages sync.sh subprocess lifecycle.

    Serializes operations (one at a time), captures output into a
    ring buffer, and supports subscriber callbacks for live output
    streaming.
    """

    def __init__(
        self,
        sync_sh_path: str = "",
        data_dir: str = "",
    ):
        self._sync_sh_path = sync_sh_path
        self._data_dir = Path(data_dir) if data_dir else None

        # Operation state
        self._running: bool = False
        self._operation: Optional[str] = None
        self._target_ip: Optional[str] = None
        self._exit_code: Optional[int] = None
        self._process: Optional[asyncio.subprocess.Process] = None
        self._output_buffer: deque = deque(maxlen=MAX_OUTPUT_LINES)

        # Output subscribers (Task 6.3)
        self._output_subscribers: Set[Callable] = set()

        # Audit logger
        self._audit_logger: Optional[Any] = None

    # -- Properties ------------------------------------------------

    @property
    def available(self) -> bool:
        """Check if sync.sh exists and is a file."""
        p = Path(self._sync_sh_path)
        return p.is_file()

    @property
    def sync_sh_path(self) -> Optional[str]:
        """Return sync.sh path if available, else None."""
        return self._sync_sh_path if self.available else None

    # -- Audit logger setter ---------------------------------------

    def set_audit_logger(self, logger: Any) -> None:
        """Set the audit logger instance."""
        self._audit_logger = logger

    # -- Core operations -------------------------------------------

    async def run_operation(
        self, operation: str, target_ip: str
    ) -> Dict[str, str]:
        """Start a sync.sh operation.

        Raises:
            RuntimeError: If an operation is already running.
            FileNotFoundError: If sync.sh is not available.
            ValueError: If operation or IP is invalid.
        """
        if not self.available:
            raise FileNotFoundError("sync.sh not found")

        if operation not in ALLOWED_OPERATIONS:
            raise ValueError(f"Invalid operation: {operation}")

        if not _IPV4_PATTERN.match(target_ip):
            raise ValueError(f"Invalid IP address: {target_ip}")

        if self._running:
            raise RuntimeError("Operation already in progress")

        # Reset state
        self._running = True
        self._operation = operation
        self._target_ip = target_ip
        self._exit_code = None
        self._output_buffer.clear()

        # Track recent IP
        self._track_recent_ip(target_ip)

        # Spawn subprocess
        cmd = self._sync_sh_path
        args = [f"--{operation}", "--ip", target_ip]

        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = proc

        # Start background readers
        asyncio.ensure_future(self._read_stream(proc.stdout))
        asyncio.ensure_future(self._read_stream(proc.stderr))
        asyncio.ensure_future(self._wait_process(proc))

        if self._audit_logger:
            self._audit_logger.log(
                "sync.run",
                {"operation": operation, "target_ip": target_ip},
                "started",
            )

        return {
            "status": "started",
            "operation": operation,
            "target_ip": target_ip,
        }

    async def cancel_operation(self) -> Dict[str, str]:
        """Cancel the running operation by sending SIGINT.

        Raises:
            RuntimeError: If no operation is running.
        """
        if not self._running or self._process is None:
            raise RuntimeError("No operation running")

        self._process.send_signal(signal.SIGINT)

        if self._audit_logger:
            self._audit_logger.log(
                "sync.cancel",
                {"operation": self._operation},
                "sigint_sent",
            )

        return {"status": "cancelled", "operation": self._operation}

    def get_status(self) -> Dict[str, Any]:
        """Return current operation status."""
        return {
            "running": self._running,
            "operation": self._operation if self._running else None,
            "target_ip": self._target_ip if self._running else None,
            "exit_code": self._exit_code,
            "output_lines": len(self._output_buffer),
        }

    # -- Config persistence (Task 6.2) ----------------------------

    def _config_path(self) -> Path:
        """Return path to sync_config.json."""
        if self._data_dir is None:
            return Path("sync_config.json")
        return self._data_dir / "sync_config.json"

    def _load_config(self) -> Dict[str, Any]:
        """Load config from disk or return defaults."""
        path = self._config_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"target_ips": [], "recent_ips": []}

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save config to disk."""
        path = self._config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def get_config(self) -> Dict[str, Any]:
        """Return current config (target_ips + recent_ips)."""
        config = self._load_config()
        return {
            "target_ips": config.get("target_ips", []),
            "recent_ips": config.get("recent_ips", []),
        }

    def put_config(self, target_ips: List[str]) -> None:
        """Update target IPs in config.

        Raises:
            ValueError: If any IP is invalid.
        """
        for ip in target_ips:
            if not _IPV4_PATTERN.match(ip):
                raise ValueError(f"Invalid IP address: {ip}")

        config = self._load_config()
        config["target_ips"] = target_ips
        self._save_config(config)

    def _track_recent_ip(self, ip: str) -> None:
        """Add IP to recent_ips list (last N unique)."""
        config = self._load_config()
        recent = config.get("recent_ips", [])

        # Remove if already present, then prepend
        if ip in recent:
            recent.remove(ip)
        recent.insert(0, ip)

        # Trim to max
        config["recent_ips"] = recent[:MAX_RECENT_IPS]
        self._save_config(config)

    # -- Output subscription (Task 6.3) ---------------------------

    def subscribe_output(self, callback: Callable) -> None:
        """Register an async callback for live output lines."""
        self._output_subscribers.add(callback)

    def unsubscribe_output(self, callback: Callable) -> None:
        """Remove a subscriber callback."""
        self._output_subscribers.discard(callback)

    async def _broadcast_output(self, line: str) -> None:
        """Send a line to all output subscribers."""
        dead: List[Callable] = []
        for cb in list(self._output_subscribers):
            try:
                await cb(line)
            except Exception:
                dead.append(cb)
        for cb in dead:
            self._output_subscribers.discard(cb)

    # -- Internal stream readers -----------------------------------

    async def _read_stream(
        self, stream: asyncio.StreamReader
    ) -> None:
        """Read lines from stream into output buffer and broadcast."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode(
                    "utf-8", errors="replace"
                ).rstrip("\n")
                self._output_buffer.append(decoded)
                await self._broadcast_output(decoded)
        except (asyncio.CancelledError, Exception):
            pass

    async def _wait_process(
        self, proc: asyncio.subprocess.Process
    ) -> None:
        """Wait for process exit and update state."""
        try:
            return_code = await proc.wait()
            self._exit_code = return_code
            self._running = False
        except (asyncio.CancelledError, Exception):
            self._running = False


# -----------------------------------------------------------------
# Module-level state
# -----------------------------------------------------------------

_sync_manager: Optional[SyncManager] = None
_audit_logger: Optional[Any] = None


def set_audit_logger(logger: Any) -> None:
    """Set the module-level audit logger."""
    global _audit_logger  # noqa: PLW0603
    _audit_logger = logger
    if _sync_manager:
        _sync_manager.set_audit_logger(logger)


def get_sync_manager() -> Optional[SyncManager]:
    """Return the module-level SyncManager (None if not yet created)."""
    return _sync_manager


def _get_manager() -> SyncManager:
    """Get or create the module-level SyncManager."""
    global _sync_manager  # noqa: PLW0603
    if _sync_manager is None:
        repo_root = Path(__file__).parent.parent.parent
        sync_sh = repo_root / "sync.sh"
        data_dir = Path(__file__).parent.parent / "data"
        _sync_manager = SyncManager(
            sync_sh_path=str(sync_sh), data_dir=str(data_dir)
        )
        if _audit_logger:
            _sync_manager.set_audit_logger(_audit_logger)
    return _sync_manager


# -----------------------------------------------------------------
# Router
# -----------------------------------------------------------------

sync_router = APIRouter(prefix="/api/sync", tags=["sync"])


@sync_router.get("/available")
async def get_available():
    """Check if sync.sh is available."""
    mgr = _get_manager()
    return {
        "available": mgr.available,
        "path": mgr.sync_sh_path,
    }


@sync_router.post("/run")
async def post_run(req: RunRequest):
    """Start a sync operation."""
    mgr = _get_manager()

    try:
        result = await mgr.run_operation(req.operation, req.target_ip)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@sync_router.post("/cancel")
async def post_cancel():
    """Cancel a running sync operation."""
    mgr = _get_manager()

    try:
        result = await mgr.cancel_operation()
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sync_router.get("/status")
async def get_status():
    """Get current sync operation status."""
    mgr = _get_manager()
    return mgr.get_status()


@sync_router.get("/config")
async def get_config():
    """Get sync configuration."""
    mgr = _get_manager()
    return mgr.get_config()


@sync_router.put("/config")
async def put_config(req: ConfigRequest):
    """Update sync configuration."""
    mgr = _get_manager()

    try:
        mgr.put_config(req.target_ips)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
