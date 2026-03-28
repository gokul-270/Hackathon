#!/usr/bin/env python3
"""
Source verification tests for blocking sleep annotations in vehicle_control.

Tasks 4.27 part 1 + 4.28b + sleep audit:
- All time.sleep() calls in production code must have BLOCKING_SLEEP_OK annotation
- No bare 'except:' should remain in production code
"""

import os
import re

import pytest

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_python_files(directory):
    """Get production .py files in directory recursively.

    Excludes tests/, archive/, simulation/, __pycache__/, and non-production
    scripts (demos, launch files, test frameworks, quick_start).
    """
    # Files that are scripts/demos/launch helpers — not production node code
    _NON_PRODUCTION_FILES = {
        "quick_start.py",
        "demo_complete_functionality.py",
        "test_framework.py",
        "system_diagnostics.py",
    }
    # Directories that are not production code
    _NON_PRODUCTION_DIRS = {
        "tests",
        "archive",
        "simulation",
        "__pycache__",
        "launch",
    }
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in _NON_PRODUCTION_DIRS]
        for f in filenames:
            if f.endswith(".py") and f not in _NON_PRODUCTION_FILES:
                files.append(os.path.join(root, f))
    return files


def find_unannotated_sleeps(filepath):
    """Find time.sleep() calls without BLOCKING_SLEEP_OK annotation.

    Handles multi-line sleep calls where black reformats:
        time.sleep(
            0.5
        )  # BLOCKING_SLEEP_OK: ...
    by scanning forward up to 5 lines for the annotation.
    """
    issues = []
    with open(filepath) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip comments and import lines
        if stripped.startswith("#"):
            continue
        if "time.sleep(" in line and "import" not in line:
            # Check same line and previous line for annotation
            has_annotation = "BLOCKING_SLEEP_OK" in line
            if i > 0:
                has_annotation = has_annotation or "BLOCKING_SLEEP_OK" in lines[i - 1]
            # For multi-line sleep calls, scan forward up to 5 lines.
            # black reformats time.sleep(val)  # comment into:
            #   time.sleep(
            #       val
            #   )  # comment
            # We scan until we find the annotation or hit a blank line /
            # a line at same or lesser indentation that starts a new statement.
            if not has_annotation:
                sleep_indent = len(line) - len(line.lstrip())
                for j in range(1, 6):
                    if i + j >= len(lines):
                        break
                    fwd_line = lines[i + j]
                    if "BLOCKING_SLEEP_OK" in fwd_line:
                        has_annotation = True
                        break
                    fwd_stripped = fwd_line.strip()
                    # Stop at blank lines
                    if not fwd_stripped:
                        break
                    # Stop if we hit a new statement at same/lesser indent
                    # (but not closing parens or continuation lines)
                    fwd_indent = len(fwd_line) - len(fwd_line.lstrip())
                    if fwd_indent <= sleep_indent and not fwd_stripped.startswith(
                        (")", "]", "}", "#")
                    ):
                        break
            if not has_annotation:
                issues.append((filepath, i + 1, stripped))
    return issues


class TestBlockingSleepAnnotations:
    """Verify all time.sleep() calls are annotated with BLOCKING_SLEEP_OK."""

    def test_no_unannotated_sleeps_in_production_code(self):
        """All time.sleep() in production code must have BLOCKING_SLEEP_OK annotation."""
        all_issues = []
        for filepath in get_python_files(PACKAGE_ROOT):
            all_issues.extend(find_unannotated_sleeps(filepath))
        assert len(all_issues) == 0, "Unannotated sleeps found:\n" + "\n".join(
            f"  {f}:{l}: {c}" for f, l, c in all_issues
        )

    def test_annotation_format_is_consistent(self):
        """BLOCKING_SLEEP_OK annotations should follow the standard format."""
        # Format: # BLOCKING_SLEEP_OK: <reason> — <context> — reviewed <date>
        annotation_re = re.compile(r"BLOCKING_SLEEP_OK:\s+\S+")
        files_with_annotations = []
        bad_annotations = []

        for filepath in get_python_files(PACKAGE_ROOT):
            with open(filepath) as f:
                for i, line in enumerate(f, 1):
                    if "BLOCKING_SLEEP_OK" in line:
                        files_with_annotations.append((filepath, i))
                        if not annotation_re.search(line):
                            bad_annotations.append((filepath, i, line.strip()))

        # We expect at least some annotations exist
        assert (
            len(files_with_annotations) > 0
        ), "No BLOCKING_SLEEP_OK annotations found in production code"

        assert len(bad_annotations) == 0, "Malformed BLOCKING_SLEEP_OK annotations:\n" + "\n".join(
            f"  {f}:{l}: {c}" for f, l, c in bad_annotations
        )

    def test_annotated_files_cover_known_sleep_locations(self):
        """Verify known files with sleeps have annotations."""
        known_files_with_sleeps = [
            "motor_controller.py",
            "safety_manager.py",
            "vehicle_controller.py",
            "gpio_manager.py",
            "imu_interface.py",
            "vehicle_control_node.py",
        ]
        production_files = get_python_files(PACKAGE_ROOT)
        production_basenames = {os.path.basename(f): f for f in production_files}

        for filename in known_files_with_sleeps:
            if filename not in production_basenames:
                continue
            filepath = production_basenames[filename]
            with open(filepath) as f:
                content = f.read()
            if "time.sleep(" in content:
                assert (
                    "BLOCKING_SLEEP_OK" in content
                ), f"{filename} contains time.sleep() but no BLOCKING_SLEEP_OK annotation"


class TestNoBareExcept:
    """Verify no bare 'except:' remains in production code."""

    def test_no_bare_except_in_production_code(self):
        """No bare 'except:' should remain in production code."""
        issues = []
        bare_except_re = re.compile(r"^\s*except\s*:\s*(#.*)?$")
        for filepath in get_python_files(PACKAGE_ROOT):
            with open(filepath) as f:
                for i, line in enumerate(f, 1):
                    if bare_except_re.match(line):
                        issues.append((filepath, i, line.strip()))
        assert len(issues) == 0, "Bare excepts found:\n" + "\n".join(
            f"  {f}:{l}: {c}" for f, l, c in issues
        )

    def test_gpio_manager_uses_typed_except(self):
        """gpio_manager.py should use 'except Exception:' not bare 'except:'."""
        gpio_path = os.path.join(PACKAGE_ROOT, "hardware", "gpio_manager.py")
        if not os.path.exists(gpio_path):
            pytest.skip("gpio_manager.py not found")
        bare_except_re = re.compile(r"^\s*except\s*:\s*(#.*)?$")
        with open(gpio_path) as f:
            for i, line in enumerate(f, 1):
                assert not bare_except_re.match(
                    line
                ), f"gpio_manager.py:{i} has bare except: {line.strip()}"

    def test_imu_interface_uses_typed_except(self):
        """imu_interface.py should use 'except Exception:' not bare 'except:'."""
        imu_path = os.path.join(PACKAGE_ROOT, "integration", "imu_interface.py")
        if not os.path.exists(imu_path):
            pytest.skip("imu_interface.py not found")
        bare_except_re = re.compile(r"^\s*except\s*:\s*(#.*)?$")
        with open(imu_path) as f:
            for i, line in enumerate(f, 1):
                assert not bare_except_re.match(
                    line
                ), f"imu_interface.py:{i} has bare except: {line.strip()}"
