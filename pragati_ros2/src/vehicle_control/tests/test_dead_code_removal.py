#!/usr/bin/env python3
"""
Tests for dead code removal: broken RobustMotorController and
EnhancedMockMotorInterface imports removed from 3 utility files.
"""

import importlib
import sys
import os

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestBrokenImportRemoval:
    """Verify that cleaned-up files import without ImportError."""

    def test_system_diagnostics_imports_without_error(self):
        """system_diagnostics.py SHALL import without ImportError."""
        # Force reimport to catch any stale cached version
        mod_name = "integration.system_diagnostics"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        from integration import system_diagnostics  # noqa: F401

    def test_validate_system_imports_without_error(self):
        """validate_system.py SHALL import without ImportError."""
        mod_name = "validate_system"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        import validate_system  # noqa: F401

    def test_debug_diagnostics_imports_without_error(self):
        """debug_diagnostics.py SHALL import without ImportError."""
        mod_name = "debug_diagnostics"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        import debug_diagnostics  # noqa: F401
