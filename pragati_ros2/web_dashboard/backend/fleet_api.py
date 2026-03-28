"""
Fleet API Router — Role config endpoint and fleet management endpoints.

Provides:
- /api/config/role — returns current dashboard role
- /api/config/publishable-topics — returns the curated topic publish allowlist
- /api/fleet/status — returns fleet member health array
- /api/fleet/sync — triggers sync.sh per RPi (returns job ID)
- /api/fleet/logs — triggers log collection per RPi (returns job ID)
- /api/fleet/jobs/<job_id> — returns per-RPi progress/status

Role parsing validates against dev|vehicle|arm, defaulting to dev if absent.
"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

VALID_ROLES = {"dev", "vehicle", "arm"}

fleet_router = APIRouter(tags=["Fleet"])
role_config_router = APIRouter(tags=["Config"])

# Module-level state — set during app startup
_dashboard_role: Optional[str] = None

# Fleet job store: job_id -> {type, status, members: [{name, ip, status, error?}]}
_fleet_jobs: Dict[str, Dict[str, Any]] = {}

# Timeout per RPi subprocess (seconds)
_SUBPROCESS_TIMEOUT_S = 120

# Locate sync.sh relative to repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SYNC_SH = _REPO_ROOT / "sync.sh"


def parse_role_config(config: dict) -> str:
    """Parse and validate the role from dashboard config.

    Args:
        config: Full dashboard.yaml config dict.

    Returns:
        Validated role string (dev, vehicle, or arm).

    Raises:
        ValueError: If role is present but invalid.
    """
    role = config.get("role", None)

    if not role:
        logger.warning("No role configured, defaulting to dev")
        return "dev"

    role = str(role).strip().lower()

    if role not in VALID_ROLES:
        raise ValueError(
            f"Invalid role '{role}' in dashboard.yaml. " f"Valid roles: dev, vehicle, arm"
        )

    return role


def set_dashboard_role(role: str) -> None:
    """Set the module-level dashboard role (called during app startup)."""
    global _dashboard_role
    _dashboard_role = role


def get_dashboard_role() -> str:
    """Get the current dashboard role."""
    return _dashboard_role or "dev"


def _get_fleet_svc():
    """Get FleetHealthService instance from service registry.

    Separated into its own function so tests can patch it easily.
    """
    try:
        from .service_registry import get_fleet_health_service

        return get_fleet_health_service()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@role_config_router.get("/api/config/role")
async def get_role():
    """Return the current dashboard role configuration."""
    return {"role": get_dashboard_role()}


@role_config_router.get("/api/config/publishable-topics")
async def get_publishable_topics():
    """Return the curated topic publish allowlist from dashboard.yaml.

    Reads ``pragati.publishable_topics`` from config/dashboard.yaml and returns
    the list. Returns an empty array when the config is absent or the key is
    not set, so the frontend can render a "no topics configured" message.
    """
    try:
        config_path = Path(__file__).resolve().parent.parent / "config" / "dashboard.yaml"
        if not config_path.exists():
            return []
        with open(config_path) as fh:
            config = yaml.safe_load(fh) or {}
        pragati = config.get("pragati") or {}
        return pragati.get("publishable_topics") or []
    except Exception:
        logger.exception("Failed to load publishable_topics from dashboard.yaml")
        return []


@fleet_router.get("/api/fleet/status")
async def get_fleet_status():
    """Return fleet member health array.

    Returns a JSON object with a ``members`` key containing the array
    of fleet member dicts from FleetHealthService.
    """
    svc = _get_fleet_svc()
    if svc is None:
        return {"members": []}
    return {"members": svc.get_fleet_status()}


@fleet_router.post("/api/fleet/sync")
async def start_fleet_sync():
    """Trigger sync.sh --deploy-cross for each fleet member.

    Returns a job_id immediately. Poll GET /api/fleet/jobs/<job_id>
    for per-RPi progress.
    """
    svc = _get_fleet_svc()
    members = svc.get_fleet_status() if svc else []

    if not members:
        raise HTTPException(status_code=400, detail="No fleet members configured")

    job_id = str(uuid.uuid4())
    _fleet_jobs[job_id] = {
        "type": "sync",
        "status": "running",
        "members": [{"name": m["name"], "ip": m["ip"], "status": "pending"} for m in members],
    }

    asyncio.create_task(_run_fleet_job(job_id))
    return {"job_id": job_id}


@fleet_router.post("/api/fleet/logs")
async def start_fleet_logs():
    """Trigger sync.sh --collect-logs for each fleet member.

    Returns a job_id immediately. Poll GET /api/fleet/jobs/<job_id>
    for per-RPi progress.
    """
    svc = _get_fleet_svc()
    members = svc.get_fleet_status() if svc else []

    if not members:
        raise HTTPException(status_code=400, detail="No fleet members configured")

    job_id = str(uuid.uuid4())
    _fleet_jobs[job_id] = {
        "type": "logs",
        "status": "running",
        "members": [{"name": m["name"], "ip": m["ip"], "status": "pending"} for m in members],
    }

    asyncio.create_task(_run_fleet_job(job_id))
    return {"job_id": job_id}


@fleet_router.get("/api/fleet/jobs/{job_id}")
async def get_fleet_job(job_id: str):
    """Return per-RPi progress for a fleet job."""
    job = _fleet_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Subprocess execution (runs in background)
# ---------------------------------------------------------------------------


async def _run_fleet_job(job_id: str) -> None:
    """Execute sync.sh or log collection for each member in a fleet job.

    Each RPi is processed in parallel via asyncio.gather.
    The job dict is updated in-place as each member completes.
    """
    job = _fleet_jobs.get(job_id)
    if job is None:
        return

    job_type = job["type"]

    async def _run_for_member(member_entry: Dict[str, Any]) -> None:
        ip = member_entry["ip"]
        member_entry["status"] = "running"

        if job_type == "sync":
            cmd_args = [str(_SYNC_SH), "--deploy-cross", "--ip", ip]
        else:
            cmd_args = [str(_SYNC_SH), "--collect-logs", "--ip", ip]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_SUBPROCESS_TIMEOUT_S
            )

            if proc.returncode == 0:
                member_entry["status"] = "success"
            else:
                member_entry["status"] = "failed"
                member_entry["error"] = (
                    stderr.decode("utf-8", errors="replace").strip()
                    or f"Exit code {proc.returncode}"
                )

        except asyncio.TimeoutError:
            member_entry["status"] = "failed"
            member_entry["error"] = f"Timeout after {_SUBPROCESS_TIMEOUT_S}s"
            try:
                proc.kill()  # type: ignore[possibly-undefined]
            except Exception:
                pass

        except Exception as exc:
            member_entry["status"] = "failed"
            member_entry["error"] = str(exc)

    tasks = [_run_for_member(m) for m in job["members"]]
    await asyncio.gather(*tasks, return_exceptions=True)

    job["status"] = "completed"
