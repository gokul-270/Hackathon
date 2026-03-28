#!/usr/bin/env python3

"""Bag Manager REST API for Pragati dashboard (rosbag2 integration).

Provides FastAPI router with endpoints for:
- Starting/stopping rosbag2 recordings with named profiles
- Listing recorded bags with metadata
- Detailed bag info (topics, durations, message counts)
- Downloading bags as .mcap or .tar.gz
- Deleting bags with safety checks
- Background disk monitoring and automatic retention cleanup
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shutil
import signal
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Router
# -------------------------------------------------------------------
bag_router = APIRouter(prefix="/api/bags", tags=["Bag Manager"])

# -------------------------------------------------------------------
# Module-level state
# -------------------------------------------------------------------
_recording_state: dict | None = None

BAGS_DIR = Path(
    os.environ.get("PRAGATI_BAG_DIR", str(Path.home() / "bags"))
)
PROFILES_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "bag_profiles.yaml"
)

_profiles: dict = {}

BAG_RETENTION_DAYS = 7
DISK_STOP_THRESHOLD_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB
_disk_monitor_task: asyncio.Task | None = None

# Metadata cache: path_str -> (timestamp, metadata_dict)
_metadata_cache: dict[str, tuple[float, dict]] = {}
_METADATA_CACHE_TTL = 30.0  # seconds


# -------------------------------------------------------------------
# Pydantic models
# -------------------------------------------------------------------
class RecordStartRequest(BaseModel):
    profile: str


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------


@bag_router.post("/record/start")
async def record_start(body: RecordStartRequest) -> dict[str, Any]:
    """Start a rosbag2 recording with the given profile."""
    global _recording_state, _disk_monitor_task

    # Check for already-active recording
    if _recording_state is not None:
        proc = _recording_state["process"]
        if proc.returncode is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Recording already active",
                    "profile": _recording_state["profile"],
                },
            )
        # Process exited unexpectedly — clean up stale state
        logger.warning(
            "Stale recording state found (pid=%d exited), cleaning up",
            _recording_state["pid"],
        )
        _recording_state = None

    profile = body.profile
    if profile not in _profiles:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Unknown profile '{profile}'",
                "available": list(_profiles.keys()),
            },
        )

    # Rotate old bags before starting a new recording
    try:
        _rotate_old_bags()
    except Exception:
        logger.exception("Failed to rotate old bags")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = BAGS_DIR / f"trial_{timestamp}_{profile}"

    cmd = [
        "ros2",
        "bag",
        "record",
        "--storage",
        "mcap",
        "--max-cache-size",
        "100000000",
        "--output",
        str(output_dir),
    ] + _profiles[profile]["topics"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:
        logger.exception("Failed to start ros2 bag record")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to start recording: {exc}"},
        ) from exc

    _recording_state = {
        "pid": proc.pid,
        "process": proc,
        "profile": profile,
        "start_time": time.time(),
        "output_dir": output_dir,
    }
    logger.info(
        "Started recording: profile=%s pid=%d dir=%s",
        profile,
        proc.pid,
        output_dir,
    )

    # Start disk monitor if not already running
    if _disk_monitor_task is None or _disk_monitor_task.done():
        _disk_monitor_task = asyncio.create_task(_disk_monitor_loop())

    return {
        "status": "recording",
        "profile": profile,
        "output_dir": str(output_dir),
    }


@bag_router.post("/record/stop")
async def record_stop() -> dict[str, Any]:
    """Stop the active rosbag2 recording."""
    global _recording_state, _disk_monitor_task

    if _recording_state is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "No active recording"},
        )

    proc = _recording_state["process"]
    output_dir = _recording_state["output_dir"]

    # Graceful stop via SIGINT
    try:
        proc.send_signal(signal.SIGINT)
    except ProcessLookupError:
        logger.warning("Recording process already exited (pid=%d)", proc.pid)

    # Wait up to 10 seconds, then SIGKILL
    try:
        await asyncio.wait_for(proc.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning(
            "Recording did not stop within 10s, sending SIGKILL (pid=%d)",
            proc.pid,
        )
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()

    logger.info("Stopped recording: dir=%s", output_dir)
    _recording_state = None

    # Cancel disk monitor
    if _disk_monitor_task is not None and not _disk_monitor_task.done():
        _disk_monitor_task.cancel()
        _disk_monitor_task = None

    return {"status": "stopped", "output_dir": str(output_dir)}


@bag_router.get("/record/status")
async def record_status() -> dict[str, Any]:
    """Return current recording state and disk info."""
    try:
        disk_free = shutil.disk_usage(str(BAGS_DIR)).free
    except OSError:
        disk_free = 0

    if _recording_state is None or _recording_state["process"].returncode is not None:
        return {
            "active": False,
            "profile": None,
            "duration_seconds": None,
            "estimated_size_bytes": None,
            "disk_space_remaining_bytes": disk_free,
        }

    duration = time.time() - _recording_state["start_time"]
    estimated_size = _dir_size(_recording_state["output_dir"])

    return {
        "active": True,
        "profile": _recording_state["profile"],
        "duration_seconds": round(duration, 2),
        "estimated_size_bytes": estimated_size,
        "disk_space_remaining_bytes": disk_free,
    }


@bag_router.get("/list")
async def list_bags(
    path: str | None = Query(
        None,
        description="Optional custom directory to list bags from",
    ),
) -> list[dict[str, Any]]:
    """List all recorded bags with metadata."""
    if path:
        target = Path(path).resolve()
        # Path traversal protection: must be under BAGS_DIR
        if not str(target).startswith(str(BAGS_DIR.resolve())):
            raise HTTPException(
                status_code=403,
                detail="Path outside allowed directory",
            )
        if not target.exists() or not target.is_dir():
            return []
        bag_dir = target
    else:
        bag_dir = BAGS_DIR

    if not bag_dir.exists():
        return []

    bags: list[dict[str, Any]] = []
    entries = sorted(bag_dir.iterdir(), key=_safe_mtime, reverse=True)

    for entry in entries:
        if entry.is_dir() or (entry.is_file() and entry.suffix == ".mcap"):
            try:
                meta = await _get_bag_metadata(entry)
                bags.append(meta)
            except Exception:
                logger.exception("Failed to get metadata for %s", entry)

    return bags


@bag_router.get("/{bag_name}/info")
async def bag_info(bag_name: str) -> dict[str, Any]:
    """Return detailed info for a specific bag."""
    bag_path = _resolve_bag_path(bag_name)
    if bag_path is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Bag '{bag_name}' not found"},
        )

    cmd = ["ros2", "bag", "info", str(bag_path), "--verbose"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=10.0
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": "ros2 bag info timed out"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to run ros2 bag info: {exc}"},
        ) from exc

    if proc.returncode != 0:
        error_msg = stderr.decode(errors="replace").strip()
        raise HTTPException(
            status_code=500,
            detail={"error": f"ros2 bag info failed: {error_msg}"},
        )

    parsed = _parse_bag_info_output(stdout.decode(errors="replace"))
    parsed["name"] = bag_name
    parsed["total_size_bytes"] = _dir_size(bag_path)
    return parsed


@bag_router.get("/{bag_name}/download")
async def download_bag(bag_name: str) -> StreamingResponse:
    """Download a bag as .mcap (single file) or .tar.gz (directory)."""
    bag_path = _resolve_bag_path(bag_name)
    if bag_path is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Bag '{bag_name}' not found"},
        )

    if bag_path.is_file():
        return StreamingResponse(
            _stream_file(bag_path),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{bag_name}.mcap"'
                ),
            },
        )

    # Directory — stream as tar.gz
    return StreamingResponse(
        _stream_tar_gz(bag_path),
        media_type="application/gzip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{bag_name}.tar.gz"'
            ),
        },
    )


@bag_router.delete("/{bag_name}")
async def delete_bag(bag_name: str) -> dict[str, Any]:
    """Delete a recorded bag."""
    bag_path = _resolve_bag_path(bag_name)
    if bag_path is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Bag '{bag_name}' not found"},
        )

    # Prevent deleting the active recording
    if _recording_state is not None:
        active_dir = _recording_state["output_dir"]
        try:
            if bag_path.resolve() == Path(active_dir).resolve():
                raise HTTPException(
                    status_code=409,
                    detail={"error": "Cannot delete active recording"},
                )
        except OSError:
            pass

    try:
        if bag_path.is_dir():
            shutil.rmtree(bag_path)
        else:
            bag_path.unlink()
    except Exception as exc:
        logger.exception("Failed to delete bag %s", bag_name)
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to delete: {exc}"},
        ) from exc

    # Evict from cache
    _metadata_cache.pop(str(bag_path), None)

    logger.info("Deleted bag: %s", bag_name)
    return {"status": "deleted", "name": bag_name}


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------


def _resolve_bag_path(bag_name: str) -> Path | None:
    """Resolve a bag name to a path under BAGS_DIR, or None."""
    if not BAGS_DIR.exists():
        return None
    candidate = BAGS_DIR / bag_name
    # Prevent path traversal
    try:
        candidate.resolve().relative_to(BAGS_DIR.resolve())
    except ValueError:
        return None
    if candidate.exists():
        return candidate
    return None


def _safe_mtime(path: Path) -> float:
    """Return mtime or 0.0 on error."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _dir_size(path: Path) -> int:
    """Sum file sizes recursively. Works for files and directories."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


async def _get_bag_metadata(path: Path) -> dict[str, Any]:
    """Get bag metadata, using cache if fresh enough."""
    cache_key = str(path)
    now = time.time()

    if cache_key in _metadata_cache:
        cached_time, cached_data = _metadata_cache[cache_key]
        if now - cached_time < _METADATA_CACHE_TTL:
            return cached_data

    meta: dict[str, Any] = {
        "name": path.name,
        "date": datetime.fromtimestamp(
            _safe_mtime(path), tz=timezone.utc
        ).isoformat(),
        "total_size_bytes": _dir_size(path),
        "duration_seconds": None,
        "message_count": None,
        "topic_count": None,
        "storage_format": _detect_storage_format(path),
    }

    # Try ros2 bag info for richer metadata
    try:
        cmd = ["ros2", "bag", "info", str(path)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(), timeout=10.0
        )
        if proc.returncode == 0:
            parsed = _parse_bag_info_output(stdout.decode(errors="replace"))
            meta["duration_seconds"] = parsed.get("total_duration_seconds")
            meta["message_count"] = parsed.get("message_count")
            meta["topic_count"] = parsed.get("topic_count")
            if parsed.get("storage_format"):
                meta["storage_format"] = parsed["storage_format"]
    except asyncio.TimeoutError:
        logger.warning("ros2 bag info timed out for %s", path)
    except Exception:
        logger.debug(
            "ros2 bag info unavailable for %s, using filesystem metadata",
            path,
        )

    _metadata_cache[cache_key] = (now, meta)
    return meta


def _detect_storage_format(path: Path) -> str:
    """Detect whether a bag uses mcap or sqlite3 storage."""
    if path.is_file() and path.suffix == ".mcap":
        return "mcap"
    if path.is_dir():
        mcap_files = list(path.glob("*.mcap"))
        if mcap_files:
            return "mcap"
        db3_files = list(path.glob("*.db3"))
        if db3_files:
            return "sqlite3"
    return "unknown"


def _parse_bag_info_output(output: str) -> dict[str, Any]:
    """Parse text output of ``ros2 bag info [--verbose]``.

    Handles both MCAP and sqlite3 format differences.
    """
    result: dict[str, Any] = {
        "total_duration_seconds": None,
        "time_range": {"start": None, "end": None},
        "compression_type": None,
        "message_count": None,
        "topic_count": None,
        "storage_format": None,
        "topics": [],
    }

    # Duration — e.g. "Duration: 12.345s" or "Duration: 1:23.456s"
    dur_match = re.search(
        r"Duration:\s+([\d:.]+)s", output
    )
    if dur_match:
        raw = dur_match.group(1)
        try:
            if ":" in raw:
                parts = raw.split(":")
                result["total_duration_seconds"] = (
                    float(parts[0]) * 60 + float(parts[1])
                )
            else:
                result["total_duration_seconds"] = float(raw)
        except ValueError:
            pass

    # Start / End times
    start_match = re.search(r"Start:\s+(.+)", output)
    if start_match:
        result["time_range"]["start"] = start_match.group(1).strip()
    end_match = re.search(r"End:\s+(.+)", output)
    if end_match:
        result["time_range"]["end"] = end_match.group(1).strip()

    # Message count
    msg_match = re.search(r"Messages:\s+(\d+)", output)
    if msg_match:
        result["message_count"] = int(msg_match.group(1))

    # Topic count
    topic_count_match = re.search(r"Topic count:\s+(\d+)", output)
    if topic_count_match:
        result["topic_count"] = int(topic_count_match.group(1))

    # Storage format — "Storage id: mcap" or "Storage id: sqlite3"
    storage_match = re.search(r"Storage id:\s+(\S+)", output)
    if storage_match:
        result["storage_format"] = storage_match.group(1)

    # Compression
    comp_match = re.search(r"Compression mode:\s+(\S+)", output)
    if comp_match:
        result["compression_type"] = comp_match.group(1)
    else:
        comp_match2 = re.search(r"Compression:\s+(\S+)", output)
        if comp_match2:
            result["compression_type"] = comp_match2.group(1)

    # Topic information lines —
    # e.g. "Topic: /camera/image | Type: sensor_msgs/msg/Image | Count: 500"
    # or from --verbose:
    # " /camera/image  | sensor_msgs/msg/Image  | 500 | ..."
    topic_pattern = re.compile(
        r"(?:Topic:\s+)?(\S+)\s+\|\s+"
        r"(?:Type:\s+)?(\S+)\s+\|\s+"
        r"(?:Count:\s+)?(\d+)"
    )
    duration = result["total_duration_seconds"]
    for m in topic_pattern.finditer(output):
        count = int(m.group(3))
        avg_rate = None
        if duration and duration > 0:
            avg_rate = round(count / duration, 2)
        result["topics"].append(
            {
                "name": m.group(1),
                "type": m.group(2),
                "message_count": count,
                "average_rate_hz": avg_rate,
            }
        )

    # Derive topic_count from parsed topics if not already set
    if result["topic_count"] is None and result["topics"]:
        result["topic_count"] = len(result["topics"])

    return result


async def _stream_file(path: Path):
    """Yield file content in chunks for streaming."""
    chunk_size = 64 * 1024  # 64 KB
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    except OSError as exc:
        logger.exception("Error streaming file %s", path)
        raise exc


async def _stream_tar_gz(directory: Path):
    """Create a tar.gz archive on the fly and yield chunks."""
    buf = io.BytesIO()
    try:
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(str(directory), arcname=directory.name)
    except OSError as exc:
        logger.exception("Error creating tar.gz for %s", directory)
        raise exc

    buf.seek(0)
    chunk_size = 64 * 1024
    while True:
        chunk = buf.read(chunk_size)
        if not chunk:
            break
        yield chunk


# -------------------------------------------------------------------
# Background tasks
# -------------------------------------------------------------------


async def _disk_monitor_loop() -> None:
    """Periodically check disk space and auto-stop if low."""
    global _recording_state, _disk_monitor_task
    logger.info("Disk monitor started")
    try:
        while _recording_state is not None:
            try:
                free = shutil.disk_usage(str(BAGS_DIR)).free
                if free < DISK_STOP_THRESHOLD_BYTES:
                    logger.warning(
                        "Disk space low (%d bytes free), auto-stopping "
                        "recording",
                        free,
                    )
                    await record_stop()
                    return
            except OSError:
                logger.exception("Disk usage check failed")
            await asyncio.sleep(300)  # 5 minutes
    except asyncio.CancelledError:
        logger.info("Disk monitor cancelled")
    finally:
        logger.info("Disk monitor stopped")


def _rotate_old_bags() -> None:
    """Delete bags older than BAG_RETENTION_DAYS."""
    if not BAGS_DIR.exists():
        return

    cutoff = time.time() - (BAG_RETENTION_DAYS * 86400)
    deleted = 0

    for entry in BAGS_DIR.iterdir():
        try:
            if _safe_mtime(entry) < cutoff:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                _metadata_cache.pop(str(entry), None)
                deleted += 1
                logger.info("Rotated old bag: %s", entry.name)
        except Exception:
            logger.exception("Failed to rotate bag %s", entry.name)

    if deleted:
        logger.info("Rotated %d old bag(s)", deleted)


# -------------------------------------------------------------------
# Initialization
# -------------------------------------------------------------------


def initialize_bag_service() -> None:
    """Initialize the bag manager service.

    - Creates the bags directory
    - Loads recording profiles from YAML
    - Cleans up any stale recording state
    """
    global _profiles, _recording_state

    # Create bags directory
    try:
        BAGS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Bag storage directory: %s", BAGS_DIR)
    except OSError:
        logger.exception("Failed to create bags directory %s", BAGS_DIR)

    # Load profiles
    if PROFILES_PATH.exists():
        try:
            with open(PROFILES_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
            _profiles = data.get("profiles", data)
            logger.info(
                "Loaded %d bag profile(s) from %s",
                len(_profiles),
                PROFILES_PATH,
            )
        except Exception:
            logger.exception(
                "Failed to load bag profiles from %s", PROFILES_PATH
            )
            _profiles = {}
    else:
        logger.warning(
            "Bag profiles file not found: %s — no profiles available",
            PROFILES_PATH,
        )
        _profiles = {}

    # Clean up stale recording state (should be None at startup, but
    # guard against module reload)
    if _recording_state is not None:
        proc = _recording_state["process"]
        if proc.returncode is None:
            logger.warning(
                "Orphan recording process found (pid=%d), terminating",
                proc.pid,
            )
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        _recording_state = None

    logger.info("Bag manager service initialized")
