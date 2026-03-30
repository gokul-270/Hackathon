"""Shared pytest configuration for all web_ui tests.

Adds the web_ui source directory to sys.path so that test files in
tests/unit/ and tests/e2e/ can import production modules by name
(e.g. `from run_controller import RunController`) without needing
relative imports or per-file sys.path hacks.
"""
import sys
from pathlib import Path

# web_ui/ is two levels up from this conftest (tests/conftest.py)
_WEB_UI_DIR = Path(__file__).resolve().parent.parent
if str(_WEB_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_WEB_UI_DIR))
