#!/usr/bin/env python3
"""
Verify no spin_until_future_complete calls exist in vehicle_control_node.py
and that all future.done() polling loops have explicit timeouts.

Task 4.28: Source verification for future polling patterns.
"""

import os
import re

import pytest

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_FILE = os.path.join(PACKAGE_ROOT, "integration", "vehicle_control_node.py")


class TestNoSpinUntilFutureComplete:
    """Verify spin_until_future_complete is not used in active code."""

    def test_node_file_exists(self):
        """Verify vehicle_control_node.py exists."""
        assert os.path.exists(NODE_FILE), f"vehicle_control_node.py not found at {NODE_FILE}"

    def test_no_spin_until_future_complete_in_active_code(self):
        """No spin_until_future_complete() calls in active (non-comment) code."""
        with open(NODE_FILE) as f:
            in_docstring = False
            triple_char = None
            for i, line in enumerate(f, 1):
                stripped = line.strip()

                # Track docstring state (triple-quoted strings)
                for tq in ('"""', "'''"):
                    count = stripped.count(tq)
                    if count >= 2:
                        # Opens and closes on same line — no state change
                        pass
                    elif count == 1:
                        if in_docstring and tq == triple_char:
                            in_docstring = False
                            triple_char = None
                        elif not in_docstring:
                            in_docstring = True
                            triple_char = tq

                if in_docstring:
                    continue

                # Skip comment lines
                if stripped.startswith("#"):
                    continue

                # Check for spin_until_future_complete in active code
                # Remove inline comments before checking
                code_part = line.split("#")[0]
                assert "spin_until_future_complete" not in code_part, (
                    f"Line {i}: spin_until_future_complete found in active code: " f"{stripped}"
                )


class TestFuturePollingHasTimeout:
    """Verify all future.done() polling loops have explicit timeout."""

    def test_future_polling_has_timeout(self):
        """All future.done() polling loops must have explicit timeout."""
        with open(NODE_FILE) as f:
            content = f.read()

        # Find while-not-future.done loops (various patterns)
        loop_pattern = re.compile(r"while\s+not\s+\w+\.done\(\)")
        matches = list(loop_pattern.finditer(content))

        if not matches:
            pytest.skip("No future.done() polling loops found")

        for match in matches:
            # Check surrounding context (200 chars before and after) for timeout
            start = max(0, match.start() - 200)
            end = min(len(content), match.end() + 200)
            context = content[start:end]
            assert (
                "timeout" in context.lower()
            ), f"Future polling loop without timeout near: {match.group()}"

    def test_future_polling_has_sleep(self):
        """All future.done() polling loops must have a sleep to avoid busy-waiting."""
        with open(NODE_FILE) as f:
            content = f.read()

        loop_pattern = re.compile(r"while\s+not\s+\w+\.done\(\)")
        matches = list(loop_pattern.finditer(content))

        if not matches:
            pytest.skip("No future.done() polling loops found")

        for match in matches:
            # Check the loop body (500 chars after) for time.sleep
            end = min(len(content), match.end() + 500)
            body = content[match.end() : end]
            assert (
                "time.sleep" in body or "sleep" in body
            ), f"Future polling loop without sleep near: {match.group()}"
