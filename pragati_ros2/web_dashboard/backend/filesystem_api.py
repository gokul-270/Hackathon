"""Filesystem browsing API with path traversal protection.

Provides a sandboxed directory listing endpoint that only allows
browsing within an allowlist of base directories.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

filesystem_router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])

# Allowlisted base paths for browsing
_ALLOWED_ROOTS: list[Path] = []


def _build_allowed_roots() -> list[Path]:
    """Build the allowlist of browsable root directories."""
    roots: list[Path] = [
        Path("/home"),
        Path.home(),
        Path("/tmp"),
    ]
    for env_var in (
        "FIELD_LOGS_DIR",
        "PRAGATI_BAG_DIR",
        "ROS_LOG_DIR",
        "COLLECTED_LOGS_DIR",
    ):
        val = os.environ.get(env_var)
        if val:
            roots.append(Path(val))
    # Add collected_logs directory (repo-relative)
    repo_root = Path(__file__).resolve().parent.parent.parent
    collected_logs = repo_root / "collected_logs"
    if collected_logs.exists():
        roots.append(collected_logs)
    # Deduplicate and resolve
    seen: set[str] = set()
    result: list[Path] = []
    for r in roots:
        resolved = str(r.resolve())
        if resolved not in seen:
            seen.add(resolved)
            result.append(r.resolve())
    return result


def initialize_filesystem_api() -> None:
    """Initialize the filesystem API (call at startup)."""
    global _ALLOWED_ROOTS  # noqa: PLW0603
    _ALLOWED_ROOTS = _build_allowed_roots()


def _is_path_allowed(target: Path) -> bool:
    """Check if resolved target is under any allowed root."""
    resolved = target.resolve()
    return any(resolved == root or root in resolved.parents for root in _ALLOWED_ROOTS)


@filesystem_router.get("/browse")
async def browse_directory(
    path: str = Query(..., description="Directory path to browse"),
    dirs_only: bool = Query(
        False,
        description="Only return directories",
    ),
) -> dict:
    """List contents of a directory with path traversal protection."""
    target = Path(path).resolve()

    # Security: check allowlist
    if not _is_path_allowed(target):
        raise HTTPException(
            status_code=403,
            detail=(f"Access denied: path '{path}' is outside " "allowed directories"),
        )

    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Path does not exist: {path}",
        )

    if not target.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {path}",
        )

    entries: list[dict] = []
    try:
        for item in target.iterdir():
            if dirs_only and not item.is_dir():
                continue
            try:
                stat = item.stat()
                entries.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "type": ("directory" if item.is_dir() else "file"),
                        "size": (stat.st_size if not item.is_dir() else None),
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
            except (PermissionError, OSError):
                continue  # Skip inaccessible entries
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied reading: {path}",
        )

    # Sort: directories first, then alphabetical
    entries.sort(
        key=lambda e: (
            0 if e["type"] == "directory" else 1,
            e["name"].lower(),
        )
    )

    return {
        "path": str(target),
        "entries": entries,
        "parent": (str(target.parent) if _is_path_allowed(target.parent) else None),
    }
