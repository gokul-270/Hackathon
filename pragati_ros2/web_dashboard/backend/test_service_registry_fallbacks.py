"""Tests for service_registry fallback values when enhanced services unavailable.

When the enhanced_services import fails, all service getters that are checked
via truthiness (``if get_X_service:``) MUST be falsy (``None``), NOT
``lambda: None`` which is truthy and causes silent call-through bugs.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest

# The fallback names that must be falsy when enhanced_services import fails.
FALSY_FALLBACKS = [
    "get_topic_echo_service",
    "get_log_aggregation_service",
    "get_node_lifecycle_service",
    "get_performance_service",
]


def _reimport_with_broken_enhanced_services():
    """Re-import service_registry with enhanced_services forced to fail."""
    # Remove cached module so it re-executes top-level code
    mod_name = "backend.service_registry"
    if mod_name in sys.modules:
        saved = sys.modules.pop(mod_name)
    else:
        saved = None

    # Also remove sub-modules that service_registry imports at top level
    to_remove = [
        k
        for k in sys.modules
        if k.startswith("backend.log_aggregator")
        or k.startswith("backend.topic_echo")
        or k.startswith("backend.node_lifecycle")
        or k.startswith("backend.performance")
    ]

    saved_subs = {}
    for k in to_remove:
        saved_subs[k] = sys.modules.pop(k)

    # Patch the import of the enhanced_services block to raise ImportError
    original_import = (
        __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
    )

    def _broken_import(name, *args, **kwargs):
        # Block imports that would come from the enhanced_services try block
        if name in (
            "backend.log_aggregator",
            "backend.topic_echo_service",
            "backend.node_lifecycle_service",
            "backend.performance_service",
        ):
            raise ImportError(f"Simulated: {name} unavailable")
        return original_import(name, *args, **kwargs)

    try:
        with patch("builtins.__import__", side_effect=_broken_import):
            mod = importlib.import_module(mod_name)
        return mod
    finally:
        # Restore original modules to avoid polluting other tests
        if saved is not None:
            sys.modules[mod_name] = saved
        for k, v in saved_subs.items():
            sys.modules[k] = v


class TestEnhancedServicesFallbacks:
    """When enhanced_services import fails, fallback getters must be falsy."""

    @pytest.mark.parametrize("attr_name", FALSY_FALLBACKS)
    def test_fallback_is_falsy(self, attr_name):
        """Fallback for {attr_name} must be None (falsy), not lambda: None."""
        mod = _reimport_with_broken_enhanced_services()
        val = getattr(mod, attr_name, "MISSING")
        assert val is not "MISSING", f"{attr_name} not found on module"
        assert not val, (
            f"{attr_name} fallback is truthy ({val!r}). "
            f"Must be None so `if not {attr_name}:` works correctly."
        )

    @pytest.mark.parametrize("attr_name", FALSY_FALLBACKS)
    def test_fallback_is_none(self, attr_name):
        """Fallback for {attr_name} must be exactly None."""
        mod = _reimport_with_broken_enhanced_services()
        val = getattr(mod, attr_name)
        assert val is None, f"{attr_name} fallback is {val!r}, expected None."
