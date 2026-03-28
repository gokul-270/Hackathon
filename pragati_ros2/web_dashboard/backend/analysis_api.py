#!/usr/bin/env python3

"""Field Analysis REST API and WebSocket endpoints for Pragati dashboard.

Provides FastAPI router with endpoints for:
- Listing field log directories
- Running log analysis jobs (via subprocess to scripts/log_analyzer.py)
- Retrieving analysis results (summary, motors, detection, failures, timeline)
- Browsing analysis history
- Comparing two analysis runs
- Real-time job progress via WebSocket

The analyzer script is always invoked as a subprocess — never imported
as a Python library.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)

logger = logging.getLogger(__name__)

# ===================================================================
# Module-level state
# ===================================================================

_jobs: dict[str, dict] = {}
_job_semaphore = asyncio.Semaphore(2)
_results_dir = Path("data/analysis_results")
FIELD_LOGS_DIR = Path(os.environ.get("FIELD_LOGS_DIR", str(Path.home() / "field_logs")))
ANALYZER_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "log_analyzer.py"
_ws_connections: dict[str, list[WebSocket]] = {}

# ===================================================================
# WebSocket helpers
# ===================================================================


async def _notify_ws(job_id: str, payload: dict) -> None:
    """Send a JSON payload to all WebSocket subscribers for a job."""
    connections = _ws_connections.get(job_id, [])
    dead: list[WebSocket] = []
    for ws in connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)


# ===================================================================
# Result-file helpers
# ===================================================================


def _job_result_dir(job_id: str) -> Path:
    """Return the result directory for a given job_id."""
    return _results_dir / job_id


def _load_result_file(job_id: str, filename: str) -> Optional[dict]:
    """Load a JSON result file for a completed job."""
    path = _job_result_dir(job_id) / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception(
            "Failed to load result file %s for job %s",
            filename,
            job_id,
        )
        return None


def _resolve_job_status(job_id: str) -> Optional[dict]:
    """Return job dict from memory or from cached results on disk."""
    if job_id in _jobs:
        return _jobs[job_id]
    metadata_path = _job_result_dir(job_id) / "metadata.json"
    if metadata_path.exists():
        try:
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            return {
                "job_id": job_id,
                "status": meta.get("status", "completed"),
                "log_directory": meta.get("log_directory", ""),
            }
        except Exception:
            return None
    return None


def _cached_result_for_directory(
    log_directory: str,
) -> Optional[str]:
    """Find a completed job_id whose results match log_directory."""
    if not _results_dir.exists():
        return None
    for entry in _results_dir.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("log_directory") == log_directory and meta.get("status") == "completed":
                return entry.name
        except Exception:
            continue
    return None


def _safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dict keys."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


# ===================================================================
# Result splitting logic
# ===================================================================


def _compute_overall_health(
    sess_health: dict,
    pick_perf: dict,
    critical_issues: list,
) -> float:
    """Compute a 0-1 overall health score from analyzer outputs.

    Heuristic:
    - Start at 1.0
    - Deduct 0.15 per critical/high issue (capped)
    - Deduct based on error ratio if level_counts available
    - Deduct for log gaps / restarts
    - Boost for successful picks
    """
    score = 1.0

    # Penalty for critical/high issues
    n_issues = len(critical_issues) if critical_issues else 0
    score -= min(n_issues * 0.15, 0.6)

    # Penalty for restarts
    restarts = sess_health.get("restarts", 0) or 0
    score -= min(restarts * 0.1, 0.3)

    # Penalty for log gaps (>10 is noisy)
    gaps = sess_health.get("log_gaps", 0) or 0
    if gaps > 10:
        score -= 0.1

    # Boost for picks (if any succeeded)
    succeeded = pick_perf.get("succeeded", 0) or 0
    if succeeded > 0:
        score += 0.05

    return max(0.0, min(1.0, round(score, 2)))


def _split_results(
    job_id: str,
    analyzer_output: dict,
    log_directory: str,
) -> None:
    """Split analyzer JSON output into separate result files.

    Creates _results_dir / job_id / with:
      summary.json, motors.json, detection.json,
      failures.json, timeline.json, metadata.json
    """
    out_dir = _job_result_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    field_summary = analyzer_output.get("field_summary", {})

    # --- summary.json ---
    issues = analyzer_output.get("issues", [])
    critical_high = [i for i in issues if i.get("severity") in ("critical", "high")]
    pick_perf = field_summary.get("pick_performance") or {}
    sess_health = field_summary.get("session_health") or {}
    summary = {
        "executive_summary": analyzer_output.get("executive_summary"),
        "summary": analyzer_output.get("summary", {}),
        "issues": critical_high,
        "level_counts": analyzer_output.get("level_counts", {}),
        "session_mode": analyzer_output.get("session_mode"),
        "analysis_time": analyzer_output.get("analysis_time"),
        "log_directory": analyzer_output.get("log_directory"),
        "pick_performance": pick_perf,
        "session_health": sess_health,
        # Flat aliases for frontend compatibility
        "status": "completed",
        "overall_health": _compute_overall_health(sess_health, pick_perf, critical_high),
        "duration": (
            sess_health.get("operational_duration_s") or sess_health.get("session_duration_s")
        ),
        "total_picks": pick_perf.get("total", 0),
        "success_rate": (pick_perf.get("success_rate_pct", 0) or 0) / 100.0,
        "error_count": len(critical_high),
        "key_findings": [
            i.get("title") or i.get("message") or i.get("description") or "Unknown issue"
            for i in critical_high[:5]
        ],
        "critical_issues": [i for i in critical_high if i.get("severity") == "critical"],
    }
    _write_json(out_dir / "summary.json", summary)

    # --- motors.json ---
    motor_health = field_summary.get("motor_health_trends", {})
    joints: list[dict] = []
    if isinstance(motor_health, dict):
        for joint_name, data in motor_health.items():
            if not isinstance(data, dict):
                continue
            joints.append(
                {
                    "joint_name": joint_name,
                    "temperature": data.get("temperature"),
                    "current": data.get("current"),
                    "position_error": data.get("position_error"),
                    "health_score": data.get("health_score"),
                    "error_flags": data.get("error_flags", []),
                }
            )
    motors = {
        "joints": joints,
        "motor_trending": field_summary.get("motor_trending"),
    }
    _write_json(out_dir / "motors.json", motors)

    # --- detection.json ---
    det_quality = field_summary.get("detection_quality", {})
    performance = analyzer_output.get("performance", {})
    detection = {
        "total_raw_detections": det_quality.get("total_raw_detections"),
        "total_accepted": det_quality.get("total_accepted"),
        "acceptance_rate_pct": det_quality.get("acceptance_rate_pct"),
        "acceptance_rate": (det_quality.get("acceptance_rate_pct", 0) or 0) / 100.0,
        "border_skip_rate_pct": det_quality.get("border_skip_rate_pct"),
        "border_skip_rate": (det_quality.get("border_skip_rate_pct", 0) or 0) / 100.0,
        "detection_timing_ms": performance.get("detection_timing_ms"),
        "timing": performance.get("detection_timing_ms"),
        "scan_effectiveness": field_summary.get("scan_effectiveness"),
        "confidence_distribution": det_quality.get("confidence_distribution", {}),
    }
    _write_json(out_dir / "detection.json", detection)

    # --- failures.json ---
    pick_failure = field_summary.get("pick_failure_analysis", {})
    correlation_issues = [i for i in issues if i.get("category") == "correlation"]
    failures = {
        "failure_by_phase": pick_failure.get("failure_by_phase"),
        "top_failure_reasons": pick_failure.get("top_failure_reasons"),
        "emergency_shutdowns": pick_failure.get("emergency_shutdowns"),
        "recovery_overhead_pct": pick_failure.get("recovery_overhead_pct"),
        "recovery_overhead": (pick_failure.get("recovery_overhead_pct", 0) or 0) / 100.0,
        "correlated_events": correlation_issues,
        "shutdown_details": pick_failure.get("shutdown_details", {}),
    }
    _write_json(out_dir / "failures.json", failures)

    # --- timeline.json ---
    all_events = analyzer_output.get("timeline", [])
    max_events = 500
    timeline = {
        "events": all_events[:max_events],
        "total_events": len(all_events),
        "total": len(all_events),
        "truncated": len(all_events) > max_events,
    }
    _write_json(out_dir / "timeline.json", timeline)

    # --- metadata.json ---
    pick_perf = field_summary.get("pick_performance", {})
    summary_data = analyzer_output.get("summary", {})
    metadata = {
        "job_id": job_id,
        "log_directory": log_directory,
        "date_run": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "key_findings_summary": [i.get("message", str(i)) for i in critical_high[:3]],
        "success_rate_pct": pick_perf.get("success_rate_pct"),
        "total_picks": pick_perf.get("total_picks"),
        "session_duration_s": summary_data.get("duration_seconds"),
    }
    _write_json(out_dir / "metadata.json", metadata)


def _write_json(path: Path, data: Any) -> None:
    """Write JSON data to a file."""
    try:
        path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("Failed to write %s", path)


# ===================================================================
# Analysis job runner
# ===================================================================


async def _run_analysis_job(job_id: str, log_directory: str) -> None:
    """Run the log analyzer subprocess and store results.

    Acquires _job_semaphore (max 2 concurrent), updates _jobs dict,
    and notifies WebSocket subscribers at each state change.
    """
    try:
        async with _job_semaphore:
            _jobs[job_id]["status"] = "running"
            await _notify_ws(
                job_id,
                {
                    "job_id": job_id,
                    "status": "running",
                    "progress": 0,
                    "message": "Starting analysis...",
                },
            )

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(ANALYZER_SCRIPT),
                    log_directory,
                    "--json",
                    "--field-summary",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.TimeoutError:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = "Analysis timed out after 120 seconds"
                await _notify_ws(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "error": _jobs[job_id]["error"],
                    },
                )
                try:
                    proc.kill()  # type: ignore[possibly-undefined]
                except Exception:
                    pass
                return
            except Exception as exc:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(exc)
                await _notify_ws(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "error": str(exc),
                    },
                )
                return

            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = stderr_text or f"Exit code {proc.returncode}"
                await _notify_ws(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "error": _jobs[job_id]["error"],
                    },
                )
                return

            # Parse output
            try:
                output = json.loads(stdout.decode("utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = f"Invalid JSON from analyzer: {exc}"
                await _notify_ws(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "error": _jobs[job_id]["error"],
                    },
                )
                return

            _split_results(job_id, output, log_directory)
            _jobs[job_id]["status"] = "completed"
            await _notify_ws(
                job_id,
                {
                    "job_id": job_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Analysis complete",
                },
            )

    except Exception as exc:
        logger.exception("Unexpected error in analysis job %s", job_id)
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)
        await _notify_ws(
            job_id,
            {
                "job_id": job_id,
                "status": "failed",
                "error": str(exc),
            },
        )


# ===================================================================
# Endpoint helpers
# ===================================================================


def _result_endpoint_response(job_id: str, filename: str) -> dict:
    """Common logic for GET /api/analysis/{job_id}/<section>.

    Returns the loaded JSON dict or raises the appropriate HTTP error.
    """
    job = _resolve_job_status(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found",
        )

    status = job.get("status", "unknown")
    if status in ("queued", "running"):
        raise HTTPException(
            status_code=202,
            detail={
                "job_id": job_id,
                "status": status,
                "message": f"Analysis is {status}",
            },
        )

    if status == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": job.get("error", "Unknown error"),
        }

    data = _load_result_file(job_id, filename)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=(f"Result file {filename} not found " f"for job {job_id}"),
        )
    return data


# ===================================================================
# FastAPI Router
# ===================================================================

analysis_router = APIRouter(prefix="/api/analysis", tags=["Field Analysis"])


# -------------------------------------------------------------------
# 1. GET /api/analysis/log-dirs
# -------------------------------------------------------------------


@analysis_router.get("/log-dirs")
async def list_log_dirs() -> dict:
    """List available field log directories."""
    if not FIELD_LOGS_DIR.exists():
        return {
            "directories": [],
            "warning": "Log directory does not exist",
        }

    dirs: list[dict] = []
    try:
        for entry in FIELD_LOGS_DIR.iterdir():
            if not entry.is_dir():
                continue
            try:
                stat = entry.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                size_bytes = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                arm_match = re.search(r"arm_(\d+)", entry.name)
                arm_id = int(arm_match.group(1)) if arm_match else None
                dirs.append(
                    {
                        "name": entry.name,
                        "path": str(entry.resolve()),
                        "date": mtime.isoformat(),
                        "size_bytes": size_bytes,
                        "arm_id": arm_id,
                    }
                )
            except PermissionError:
                logger.warning("Permission denied reading %s", entry)
                continue
            except Exception:
                logger.exception("Error reading directory %s", entry)
                continue
    except PermissionError:
        return {
            "directories": [],
            "warning": "Permission denied reading log directory",
        }

    dirs.sort(key=lambda d: d["date"], reverse=True)
    return {"directories": dirs}


# -------------------------------------------------------------------
# 2. POST /api/analysis/run
# -------------------------------------------------------------------


@analysis_router.post("/run", status_code=202)
async def run_analysis(body: dict) -> dict:
    """Launch a log analysis job."""
    log_directory = body.get("log_directory")
    force = body.get("force", False)

    if not log_directory:
        raise HTTPException(
            status_code=400,
            detail="log_directory is required",
        )

    # Path resolution: absolute paths used as-is, relative under FIELD_LOGS_DIR
    if Path(log_directory).is_absolute():
        resolved = Path(log_directory).resolve()
    else:
        resolved = Path(FIELD_LOGS_DIR, log_directory).resolve()

    # Security: path must be under FIELD_LOGS_DIR or collected_logs
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _allowed = [
        Path(FIELD_LOGS_DIR).resolve(),
        (_repo_root / "collected_logs").resolve(),
    ]
    _cl_env = os.environ.get("COLLECTED_LOGS_DIR")
    if _cl_env:
        _allowed.append(Path(_cl_env).resolve())
    if not any(str(resolved).startswith(str(r)) for r in _allowed):
        raise HTTPException(
            status_code=403,
            detail="Path outside allowed directories",
        )

    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=(f"log_directory does not exist or is not a " f"directory: {resolved}"),
        )

    # Check for already-running job on same directory
    resolved_str = str(resolved)
    for jid, jdata in _jobs.items():
        if jdata.get("log_directory") == resolved_str and jdata.get("status") in (
            "queued",
            "running",
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "job_id": jid,
                    "status": "already_running",
                },
            )

    # Check for cached results
    if not force:
        cached_id = _cached_result_for_directory(resolved_str)
        if cached_id is not None:
            return {
                "job_id": cached_id,
                "status": "completed",
            }

    job_id = str(uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "log_directory": str(resolved),
    }

    asyncio.ensure_future(_run_analysis_job(job_id, str(resolved)))

    return {"job_id": job_id, "status": "queued"}


# -------------------------------------------------------------------
# 4. GET /api/analysis/{job_id}/summary
# -------------------------------------------------------------------


@analysis_router.get("/{job_id}/summary")
async def get_summary(job_id: str) -> dict:
    """Return analysis summary for a completed job."""
    return _result_endpoint_response(job_id, "summary.json")


# -------------------------------------------------------------------
# 5. GET /api/analysis/{job_id}/motors
# -------------------------------------------------------------------


@analysis_router.get("/{job_id}/motors")
async def get_motors(job_id: str) -> dict:
    """Return motor health data for a completed job."""
    return _result_endpoint_response(job_id, "motors.json")


# -------------------------------------------------------------------
# 6. GET /api/analysis/{job_id}/detection
# -------------------------------------------------------------------


@analysis_router.get("/{job_id}/detection")
async def get_detection(job_id: str) -> dict:
    """Return detection quality data for a completed job."""
    return _result_endpoint_response(job_id, "detection.json")


# -------------------------------------------------------------------
# 7. GET /api/analysis/{job_id}/failures
# -------------------------------------------------------------------


@analysis_router.get("/{job_id}/failures")
async def get_failures(job_id: str) -> dict:
    """Return failure analysis data for a completed job."""
    return _result_endpoint_response(job_id, "failures.json")


# -------------------------------------------------------------------
# 8. GET /api/analysis/{job_id}/timeline
# -------------------------------------------------------------------


@analysis_router.get("/{job_id}/timeline")
async def get_timeline(job_id: str) -> dict:
    """Return timeline events for a completed job."""
    return _result_endpoint_response(job_id, "timeline.json")


# -------------------------------------------------------------------
# 9. GET /api/analysis/history
# -------------------------------------------------------------------


@analysis_router.get("/history")
async def get_history() -> dict:
    """Return analysis history from cached results."""
    entries: list[dict] = []
    if not _results_dir.exists():
        return {"history": []}

    for entry in _results_dir.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            entries.append(
                {
                    "job_id": meta.get("job_id", entry.name),
                    "log_directory": meta.get("log_directory"),
                    "date_run": meta.get("date_run"),
                    "created": meta.get("date_run"),
                    "status": meta.get("status"),
                    "key_findings_summary": meta.get("key_findings_summary", []),
                    "success_rate_pct": meta.get("success_rate_pct"),
                    "success_rate": (meta.get("success_rate_pct", 0) or 0) / 100.0,
                    "total_picks": meta.get("total_picks"),
                    "session_duration_s": meta.get("session_duration_s"),
                }
            )
        except Exception:
            logger.exception(
                "Failed to read metadata from %s",
                meta_path,
            )
            continue

    entries.sort(
        key=lambda e: e.get("date_run") or "",
        reverse=True,
    )
    return {"history": entries}


# -------------------------------------------------------------------
# 10. GET /api/analysis/compare?a={job_id_a}&b={job_id_b}
# -------------------------------------------------------------------


def _numeric_delta(val_a: Any, val_b: Any) -> Optional[float]:
    """Compute b - a for numeric values, or None."""
    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
        return round(val_b - val_a, 4)
    return None


@analysis_router.get("/compare")
async def compare_analyses(
    a: str = Query(..., description="Job ID A"),
    b: str = Query(..., description="Job ID B"),
) -> dict:
    """Compare two completed analysis runs."""
    # Validate both exist and are completed
    for label, jid in [("a", a), ("b", b)]:
        job = _resolve_job_status(jid)
        if job is None:
            raise HTTPException(
                status_code=400,
                detail=f"Job {label}={jid} not found",
            )
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=400,
                detail=(f"Job {label}={jid} is not completed " f"(status={job.get('status')})"),
            )

    summary_a = _load_result_file(a, "summary.json")
    summary_b = _load_result_file(b, "summary.json")
    if summary_a is None or summary_b is None:
        raise HTTPException(
            status_code=400,
            detail="Could not load summary for one or both jobs",
        )

    motors_a = _load_result_file(a, "motors.json") or {}
    motors_b = _load_result_file(b, "motors.json") or {}

    detection_a = _load_result_file(a, "detection.json") or {}
    detection_b = _load_result_file(b, "detection.json") or {}

    # --- pick_performance ---
    pp_a = summary_a.get("pick_performance", {}) or {}
    pp_b = summary_b.get("pick_performance", {}) or {}
    pick_fields = [
        "total_picks",
        "success_rate_pct",
        "picks_per_hour",
        "cycle_time_ms",
    ]
    pick_performance = {}
    for field in pick_fields:
        pick_performance[field] = {
            "a": pp_a.get(field),
            "b": pp_b.get(field),
        }

    # --- motor_health ---
    joints_a = {j["joint_name"]: j for j in (motors_a.get("joints") or [])}
    joints_b = {j["joint_name"]: j for j in (motors_b.get("joints") or [])}
    all_joints = sorted(set(joints_a.keys()) | set(joints_b.keys()))
    motor_health: dict[str, dict] = {}
    for jn in all_joints:
        ja = joints_a.get(jn, {})
        jb = joints_b.get(jn, {})
        motor_health[jn] = {
            "health_score": {
                "a": ja.get("health_score"),
                "b": jb.get("health_score"),
            }
        }

    # --- detection_performance ---
    det_fields = [
        "acceptance_rate_pct",
        "total_raw_detections",
        "border_skip_rate_pct",
    ]
    detection_performance: dict[str, dict] = {}
    for field in det_fields:
        detection_performance[field] = {
            "a": detection_a.get(field),
            "b": detection_b.get(field),
        }

    # --- session_health ---
    sh_a = summary_a.get("session_health", {}) or {}
    sh_b = summary_b.get("session_health", {}) or {}
    sh_fields = ["duration_s", "restarts", "log_gaps"]
    session_health: dict[str, dict] = {}
    for field in sh_fields:
        session_health[field] = {
            "a": sh_a.get(field),
            "b": sh_b.get(field),
        }

    # --- deltas ---
    deltas: dict[str, Any] = {}
    for field in pick_fields:
        deltas[field] = _numeric_delta(pp_a.get(field), pp_b.get(field))
    for field in det_fields:
        deltas[field] = _numeric_delta(
            detection_a.get(field),
            detection_b.get(field),
        )
    for field in sh_fields:
        deltas[field] = _numeric_delta(sh_a.get(field), sh_b.get(field))
    for jn in all_joints:
        ja = joints_a.get(jn, {})
        jb = joints_b.get(jn, {})
        deltas[f"motor_health_{jn}"] = _numeric_delta(
            ja.get("health_score"),
            jb.get("health_score"),
        )

    # --- flat per-job objects for frontend compatibility ---
    meta_a = _load_result_file(a, "metadata.json") or {}
    meta_b = _load_result_file(b, "metadata.json") or {}

    def _flat_job(meta: dict, pp: dict, sh: dict, det: dict) -> dict:
        return {
            "job_id": meta.get("job_id"),
            "log_directory": meta.get("log_directory"),
            "success_rate": (pp.get("success_rate_pct", 0) or 0) / 100.0,
            "success_rate_pct": pp.get("success_rate_pct"),
            "total_picks": pp.get("total_picks"),
            "picks_per_hour": pp.get("picks_per_hour"),
            "duration": sh.get("duration_s"),
            "overall_health": sh.get("overall_health"),
            "acceptance_rate_pct": det.get("acceptance_rate_pct"),
        }

    return {
        "job_a": a,
        "job_b": b,
        "a": _flat_job(meta_a, pp_a, sh_a, detection_a),
        "b": _flat_job(meta_b, pp_b, sh_b, detection_b),
        "pick_performance": pick_performance,
        "motor_health": motor_health,
        "detection_performance": detection_performance,
        "session_health": session_health,
        "deltas": deltas,
    }


# -------------------------------------------------------------------
# 11. WebSocket /api/analysis/ws/progress
# -------------------------------------------------------------------


@analysis_router.websocket("/ws/progress")
async def ws_progress(
    websocket: WebSocket,
    job_id: str = Query(...),
) -> None:
    """Stream job progress updates via WebSocket."""
    await websocket.accept()

    if job_id not in _ws_connections:
        _ws_connections[job_id] = []
    _ws_connections[job_id].append(websocket)

    # Send current status immediately
    job = _resolve_job_status(job_id)
    if job is not None:
        try:
            await websocket.send_json(
                {
                    "job_id": job_id,
                    "status": job.get("status", "unknown"),
                }
            )
        except Exception:
            pass

    try:
        while True:
            # Keep connection alive; wait for client messages
            # or disconnection
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send ping/keepalive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
            except WebSocketDisconnect:
                break

            # Check if job completed
            current = _resolve_job_status(job_id)
            if current and current.get("status") in (
                "completed",
                "failed",
            ):
                try:
                    await websocket.send_json(
                        {
                            "job_id": job_id,
                            "status": current["status"],
                        }
                    )
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug(
            "WebSocket progress disconnected for job %s",
            job_id,
        )
    finally:
        conns = _ws_connections.get(job_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            _ws_connections.pop(job_id, None)


# ===================================================================
# Initialization
# ===================================================================


def initialize_analysis_service() -> None:
    """Initialize the analysis service.

    Creates result directory and populates _jobs dict from cached
    results on disk.
    """
    try:
        _results_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception(
            "Failed to create results directory %s",
            _results_dir,
        )

    # Populate _jobs from existing cached results
    if _results_dir.exists():
        for entry in _results_dir.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                job_id = meta.get("job_id", entry.name)
                _jobs[job_id] = {
                    "job_id": job_id,
                    "status": meta.get("status", "completed"),
                    "log_directory": meta.get("log_directory", ""),
                }
            except Exception:
                logger.warning(
                    "Failed to load cached result from %s",
                    entry,
                )
                continue

    logger.info(
        "Analysis service initialized — " "%d cached results loaded from %s",
        len(_jobs),
        _results_dir,
    )
