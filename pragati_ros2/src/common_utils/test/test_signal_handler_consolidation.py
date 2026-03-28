"""Test that signal handler code is consolidated into common_utils.

After migration, only common_utils/src/signal_handler.cpp should contain
signal handler registration (sigaction/signal calls for SIGINT/SIGTERM).

Exceptions (documented and justified):
- yanthra_move_system_core.cpp: SAFETY-CRITICAL crash handler (GPIO cleanup
  via fork+exec pigs on SIGSEGV/SIGABRT) + second-signal forced exit.
  Cannot use shared handler because these behaviors are not supported by
  the shared API.
- mg6010_controller_node.cpp: SIGHUP handler for SSH disconnect on RPi.
  The shared handler only covers SIGINT/SIGTERM; SIGHUP is node-specific.
- vehicle_control_node.py: Python node — C++ shared handler does not apply.
"""

import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SRC_DIR = os.path.join(REPO_ROOT, "src")

# Files allowed to have signal handler registrations, with justification
ALLOWED_FILES = {
    "common_utils/src/signal_handler.cpp": "shared handler implementation",
    "yanthra_move/src/yanthra_move_system_core.cpp": (
        "safety-critical GPIO crash handler + second-signal exit"
    ),
    "motor_control_ros2/src/mg6010_controller_node.cpp": "SIGHUP handler for SSH disconnect",
    "vehicle_control/integration/vehicle_control_node.py": "Python node — C++ shared handler N/A",
    "vehicle_control/demo_complete_functionality.py": "Demo script — not production code",
}


def _is_allowed(grep_line):
    """Check if a grep output line refers to an allowed file."""
    # grep_line is "path:lineno:code" — extract path portion
    path_part = grep_line.split(":")[0]
    for allowed in ALLOWED_FILES:
        if path_part.endswith(allowed):
            return True
    return False


def _grep_signal_registrations():
    """Find all signal handler registrations in source files."""
    patterns = [
        r"std::signal\s*\(",
        r"signal\s*\(\s*SIG",
        r"sigaction\s*\(",
        r"signal\.signal\s*\(",  # Python
    ]
    combined = "|".join(patterns)

    result = subprocess.run(
        ["grep", "-rn", "-E", combined, SRC_DIR],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def test_no_duplicate_signal_handlers():
    """Verify no signal handler registrations exist outside allowed files."""
    matches = _grep_signal_registrations()

    # Filter out test files, comments, and string literals
    violations = []
    for line in matches:
        # Skip test files
        if "/test/" in line or "/test_" in line or "test.cpp" in line:
            continue
        # Skip archive directories
        if "/archive/" in line:
            continue
        # Skip comments (lines starting with // or # after the line number)
        parts = line.split(":", 2)
        if len(parts) >= 3:
            code = parts[2].strip()
            if code.startswith("//") or code.startswith("#") or code.startswith("*"):
                continue
            # Skip string literals (signal handler in quoted strings)
            if re.match(r'^".*"', code) or re.match(r"^'.*'", code):
                continue

        # Check if this is an allowed file
        if _is_allowed(line):
            continue

        violations.append(line)

    assert not violations, (
        f"Found signal handler registrations outside allowed files:\n"
        + "\n".join(violations)
        + "\n\nAllowed files: "
        + ", ".join(ALLOWED_FILES.keys())
    )


def test_common_utils_signal_handler_exists():
    """Verify the shared signal handler implementation exists."""
    hpp = os.path.join(
        SRC_DIR, "common_utils", "include", "common_utils", "signal_handler.hpp"
    )
    cpp = os.path.join(SRC_DIR, "common_utils", "src", "signal_handler.cpp")
    assert os.path.isfile(hpp), f"Missing: {hpp}"
    assert os.path.isfile(cpp), f"Missing: {cpp}"


def test_shared_handler_has_required_api():
    """Verify signal_handler.hpp declares the required API."""
    hpp = os.path.join(
        SRC_DIR, "common_utils", "include", "common_utils", "signal_handler.hpp"
    )
    with open(hpp) as f:
        content = f.read()

    assert "namespace pragati" in content, "Missing pragati namespace"
    assert (
        "install_signal_handlers" in content
    ), "Missing install_signal_handlers declaration"
    assert "shutdown_requested" in content, "Missing shutdown_requested declaration"
