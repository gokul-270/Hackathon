"""
tests/conftest.py

Shared fixtures and helpers for log_analyzer test suite.
Auto-discovered by pytest — no explicit imports needed in test files.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import pytest

# Ensure the scripts/ directory is on sys.path so we can import the package.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from log_analyzer.models import EventStore, FieldSummary, MQTTMetrics, NetworkMetrics


# ---------------------------------------------------------------------------
# Shared fixtures for synthetic log lines (task 21.1)
# ---------------------------------------------------------------------------


@pytest.fixture
def ros2_json_line():
    """A well-formed ROS2 log line containing a JSON event (vehicle [TIMING] path)."""
    event = {"event": "startup_timing", "total_ms": 1234, "hardware_init_ms": 200}
    msg = f"[TIMING] {json.dumps(event)}"
    return f"[INFO] [1700000000.000] [vehicle_control_node]: {msg}"


@pytest.fixture
def arm_bare_json_line():
    """An arm-side ROS2 log line with bare JSON (no [TIMING] prefix)."""
    event = {"event": "pick_complete", "success": True, "ts": 1700000001000, "cotton_id": "c1"}
    msg = json.dumps(event)
    return f"[INFO] [1700000001.100] [motion_controller_node]: {msg}"


@pytest.fixture
def shutdown_timing_print_line():
    """A bare [TIMING] line emitted via print() from shutdown_timing."""
    event = {"event": "shutdown_timing", "total_ms": 500}
    return f"[TIMING] {json.dumps(event)}"


@pytest.fixture
def non_json_timing_line():
    """A [TIMING] line that is plain text from C++ (not JSON)."""
    return "[TIMING] Phase durations: approach=50ms capture=30ms retreat=25ms"


@pytest.fixture
def plain_log_line():
    """A standard ROS2 log line with no JSON payload."""
    return "[INFO] [1700000002.000] [some_node]: Camera initialised successfully"


@pytest.fixture
def log_dir_with_files(tmp_path):
    """A temporary directory with a minimal .log file for analyzer tests."""
    log_file = tmp_path / "test_session.log"
    lines = [
        "[INFO] [1700000000.000] [vehicle_control_node]: [TIMING] "
        + json.dumps({"event": "startup_timing", "total_ms": 1000})
        + "\n",
        "[INFO] [1700000001.000] [vehicle_control_node]: [TIMING] "
        + json.dumps(
            {
                "event": "state_transition",
                "from_state": "IDLE",
                "to_state": "AUTO",
                "trigger": "auto_start",
            }
        )
        + "\n",
        "[INFO] [1700000002.000] [motion_controller_node]: "
        + json.dumps({"event": "pick_complete", "success": True, "ts": 1700000002000})
        + "\n",
        "[WARN] [1700000003.000] [camera_node]: USB 2.0 device connected\n",
    ]
    log_file.write_text("".join(lines))
    return tmp_path


# ---------------------------------------------------------------------------
# Shared helper: build a minimal ROS2LogAnalyzer without disk I/O
# ---------------------------------------------------------------------------


def make_minimal_analyzer(tmp_path):
    """Build a minimal ROS2LogAnalyzer instance for unit tests (no disk I/O)."""
    from log_analyzer.analyzer import ROS2LogAnalyzer

    a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
    a.log_dir = tmp_path
    a.verbose = False
    a.entries = []
    a.issues = {}
    a.performance = {}
    a.node_stats = defaultdict(
        lambda: {
            "total": 0,
            "debug": 0,
            "info": 0,
            "warn": 0,
            "error": 0,
            "fatal": 0,
        }
    )
    a.level_counts = defaultdict(int)
    a.total_lines = 0
    a.total_size = 0
    a.start_time = None
    a.end_time = None
    a.events = EventStore()
    a.mqtt = MQTTMetrics()
    a.network = NetworkMetrics()
    a.field_summary = None
    a._json_skip_count = 0
    a._current_arm_id = None  # task 2.1 — arm_id context for parser
    return a
