#!/usr/bin/env python3
"""
AST-based tests for vehicle-exception-cleanup change.

Verifies that vehicle_control_node.py has no silent exception swallowing:
- No bare `except:` blocks (catch SystemExit/KeyboardInterrupt)
- No `except Exception: pass` blocks (silent swallowing)
- No `except Exception:` without name binding (no error detail)
- MQTT paths use `except Exception as e:` with name binding
- GPIO paths use typed exception tuples (not bare except, not broad Exception)

These tests parse the source with ast.parse() and require no ROS2 runtime.
"""

import ast
import os
import sys

import pytest

# Path to the source file under test
_SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "integration",
    "vehicle_control_node.py",
)


def _parse_source():
    """Parse vehicle_control_node.py and return the AST."""
    with open(_SOURCE_PATH, "r") as f:
        return ast.parse(f.read(), filename=_SOURCE_PATH)


def _get_all_except_handlers(tree):
    """Return all ExceptHandler nodes from the AST."""
    handlers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            handlers.append(node)
    return handlers


# =============================================================================
# Task 1.1: No bare except, no silent except-pass, no unbound except-Exception
# =============================================================================


class TestNoBareExcept:
    """Task 1.1(a): No bare `except:` blocks remain."""

    def test_no_bare_except_blocks(self):
        """Every ExceptHandler must have a type (handler.type is not None)."""
        tree = _parse_source()
        handlers = _get_all_except_handlers(tree)

        bare = [h for h in handlers if h.type is None]
        assert len(bare) == 0, (
            f"Found {len(bare)} bare `except:` block(s) at line(s): "
            f"{[h.lineno for h in bare]}. "
            f"Replace with typed exceptions to let SystemExit/KeyboardInterrupt propagate."
        )


class TestNoSilentExceptPass:
    """Task 1.1(b): No `except Exception: pass` blocks remain."""

    def test_no_silent_except_exception_pass(self):
        """No handler catches Exception without name binding with body of single Pass."""
        tree = _parse_source()
        handlers = _get_all_except_handlers(tree)

        silent = []
        for h in handlers:
            # Must catch Exception (not a tuple, not bare)
            if not isinstance(h.type, ast.Name):
                continue
            if h.type.id != "Exception":
                continue
            # Must have no name binding
            if h.name is not None:
                continue
            # Must have body that is a single Pass
            if len(h.body) == 1 and isinstance(h.body[0], ast.Pass):
                silent.append(h)

        assert len(silent) == 0, (
            f"Found {len(silent)} `except Exception: pass` block(s) at line(s): "
            f"{[h.lineno for h in silent]}. "
            f"Add `as e` and logging to make failures visible."
        )


class TestNoUnboundExceptException:
    """Task 1.1(c): No `except Exception:` blocks without name binding."""

    def test_no_except_exception_without_name(self):
        """Every handler catching Exception must bind with `as e`."""
        tree = _parse_source()
        handlers = _get_all_except_handlers(tree)

        unbound = []
        for h in handlers:
            if not isinstance(h.type, ast.Name):
                continue
            if h.type.id != "Exception":
                continue
            if h.name is None:
                unbound.append(h)

        assert len(unbound) == 0, (
            f"Found {len(unbound)} `except Exception:` block(s) without name binding "
            f"at line(s): {[h.lineno for h in unbound]}. "
            f"Add `as e` to capture error details."
        )


# =============================================================================
# Task 1.2: MQTT-path handlers have `except Exception as e:`
# =============================================================================


def _find_handlers_in_function(tree, func_name):
    """Return all ExceptHandler nodes inside the named function/method."""
    handlers = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                for child in ast.walk(node):
                    if isinstance(child, ast.ExceptHandler):
                        handlers.append(child)
    return handlers


def _read_source_lines():
    """Read source file lines (1-indexed via list offset)."""
    with open(_SOURCE_PATH, "r") as f:
        return [""] + f.readlines()  # 1-indexed: lines[1] is first line


def _find_handler_by_try_content(tree, source_lines, keyword):
    """Find ExceptHandler whose try-block contains a line matching keyword."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                # Check lines in the try body for the keyword
                for body_node in ast.walk(node):
                    if hasattr(body_node, "lineno"):
                        line = (
                            source_lines[body_node.lineno]
                            if body_node.lineno < len(source_lines)
                            else ""
                        )
                        if keyword in line:
                            return handler
    return None


class TestMqttPathHandlers:
    """Task 1.2: MQTT loop_start and recreate handlers have name binding."""

    def test_mqtt_loop_start_handler_has_name_binding(self):
        """MQTT loop_start fallback handler must be `except Exception as e:`."""
        tree = _parse_source()
        source_lines = _read_source_lines()
        # Find the except handler for the try block containing loop_start()
        # inside _initialize_mqtt
        handlers = _find_handlers_in_function(tree, "_initialize_mqtt")
        # The loop_start fallback is the handler whose try body calls loop_start
        handler = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for body_node in ast.walk(node):
                    if (
                        isinstance(body_node, ast.Attribute)
                        and body_node.attr == "loop_start"
                        and node.handlers
                    ):
                        # Check this try is inside _initialize_mqtt
                        for h in handlers:
                            if h in node.handlers:
                                handler = h
                                break
                if handler:
                    break
        assert (
            handler is not None
        ), "No ExceptHandler found for MQTT loop_start try block"
        assert isinstance(
            handler.type, ast.Name
        ), "MQTT loop_start handler: expected typed except, got bare except"
        assert handler.type.id == "Exception", (
            f"MQTT loop_start handler: expected `except Exception`, "
            f"got `except {handler.type.id}`"
        )
        assert (
            handler.name is not None
        ), "MQTT loop_start handler must bind exception with `as e`"

    def test_mqtt_recreate_handler_has_name_binding(self):
        """MQTT client recreation cleanup handler must be `except Exception as e:`."""
        tree = _parse_source()
        handlers = _find_handlers_in_function(tree, "_recreate_mqtt_client")
        # The recreate cleanup handler is the first except in _recreate_mqtt_client
        # that wraps loop_stop()/disconnect()
        handler = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for body_node in ast.walk(node):
                    if (
                        isinstance(body_node, ast.Attribute)
                        and body_node.attr == "loop_stop"
                    ):
                        for h in handlers:
                            if h in node.handlers:
                                handler = h
                                break
                if handler:
                    break
        assert (
            handler is not None
        ), "No ExceptHandler found for MQTT recreate cleanup try block"
        assert isinstance(
            handler.type, ast.Name
        ), "MQTT recreate handler: expected typed except, got bare except"
        assert handler.type.id == "Exception", (
            f"MQTT recreate handler: expected `except Exception`, "
            f"got `except {handler.type.id}`"
        )
        assert (
            handler.name is not None
        ), "MQTT recreate handler must bind exception with `as e`"


# =============================================================================
# Task 1.3: GPIO handlers catch typed tuple (not bare, not broad Exception)
# =============================================================================


class TestGpioHandlers:
    """Task 1.3: GPIO RED LED handlers catch a tuple of types."""

    def _find_gpio_led_handler(self, tree, source_lines, led_value):
        """Find handler for the innermost try wrapping GPIO RED_LED set_output."""
        keyword = f"RED_LED, {led_value}"
        # Find all Try nodes, then pick the one where the try body directly
        # contains the keyword line (innermost try)
        candidates = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Try) and node.handlers:
                try_start = node.body[0].lineno if node.body else node.lineno
                handler_start = node.handlers[0].lineno
                for lineno in range(try_start, min(handler_start, len(source_lines))):
                    if keyword in source_lines[lineno]:
                        candidates.append((handler_start - try_start, node.handlers[0]))
                        break
        if not candidates:
            return None
        # Return the handler from the smallest try block (innermost)
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def test_gpio_red_led_on_catches_typed_tuple(self):
        """GPIO RED LED on must catch a tuple of exception types."""
        tree = _parse_source()
        source_lines = _read_source_lines()
        handler = self._find_gpio_led_handler(tree, source_lines, "True")
        assert handler is not None, "No ExceptHandler found for GPIO RED LED on"
        assert handler.type is not None, "GPIO RED LED on: bare `except:` not allowed"
        assert isinstance(handler.type, ast.Tuple), (
            f"GPIO RED LED on: expected tuple of exception types, "
            f"got {ast.dump(handler.type)}"
        )

    def test_gpio_red_led_off_catches_typed_tuple(self):
        """GPIO RED LED off must catch a tuple of exception types."""
        tree = _parse_source()
        source_lines = _read_source_lines()
        handler = self._find_gpio_led_handler(tree, source_lines, "False")
        assert handler is not None, "No ExceptHandler found for GPIO RED LED off"
        assert handler.type is not None, "GPIO RED LED off: bare `except:` not allowed"
        assert isinstance(handler.type, ast.Tuple), (
            f"GPIO RED LED off: expected tuple of exception types, "
            f"got {ast.dump(handler.type)}"
        )
