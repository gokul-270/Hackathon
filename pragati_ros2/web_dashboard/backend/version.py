"""
Version — Single source of truth for the dashboard version string.

Reads from web_dashboard/VERSION so that all backend modules, the FastAPI
app metadata, and API endpoints report a consistent version without
hardcoded strings scattered across the codebase.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION_FILE_PATH: Path = Path(__file__).resolve().parent.parent / "VERSION"

_cached_version: str | None = None


def get_version(path: Path | None = None) -> str:
    """Read the version string from the VERSION file.

    Args:
        path: Override path for testing. Defaults to VERSION_FILE_PATH.

    Returns:
        Stripped version string, or ``"0.0.0-unknown"`` if the file is
        missing or unreadable.
    """
    global _cached_version

    target = path or VERSION_FILE_PATH

    # Use cache only for the default (real) path
    if path is None and _cached_version is not None:
        return _cached_version

    try:
        version = target.read_text().strip()
    except (OSError, FileNotFoundError):
        logger.warning("VERSION file not found at %s, using fallback", target)
        version = "0.0.0-unknown"

    if path is None:
        _cached_version = version

    return version
