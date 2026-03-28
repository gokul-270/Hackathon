"""
Detector registry for the log_analyzer.

Provides a central registry of all detector functions, enabling:
  - ``--list-detectors`` CLI flag
  - ``--filter detector:<name>`` to selectively enable/disable detectors
  - Sorted execution order (deduplication last at order=999)

Each registry entry is a dict:
  {"name": str, "fn": callable, "category": str, "description": str, "order": int}
"""

from typing import Callable, Dict, List, Optional

_REGISTRY: Dict[str, dict] = {}


def register(
    name: str,
    fn: Callable,
    category: str,
    description: str = "",
    order: int = 0,
) -> None:
    """Register a detector function.

    Args:
        name: Unique detector name (e.g. ``detect_vehicle_issues``).
        fn: The callable detector function.
        category: Grouping category (e.g. ``motor``, ``camera``, ``arm``).
        description: One-sentence description of what the detector does.
        order: Execution order (lower runs first; dedup should be 999).
    """
    _REGISTRY[name] = {
        "name": name,
        "fn": fn,
        "category": category,
        "description": description,
        "order": order,
    }


def get_all() -> List[dict]:
    """Return all registered detectors sorted by order, then name."""
    return sorted(
        _REGISTRY.values(),
        key=lambda d: (d["order"], d["name"]),
    )


def get_by_category(category: str) -> List[dict]:
    """Return detectors filtered by category, sorted by order then name."""
    return sorted(
        (d for d in _REGISTRY.values() if d["category"] == category),
        key=lambda d: (d["order"], d["name"]),
    )


def get_names() -> List[str]:
    """Return sorted list of all registered detector names."""
    return sorted(_REGISTRY.keys())


def is_registered(name: str) -> bool:
    """Check whether a detector name is in the registry."""
    return name in _REGISTRY
