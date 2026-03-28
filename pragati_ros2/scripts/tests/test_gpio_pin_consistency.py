"""GPIO pin consistency checks across the Pragati codebase.

Verifies that:
  (a) yanthra_move_system.hpp has no stale GPIO pin member variables
      (pins should live in constants.py / production.yaml, not in C++ headers).
  (b) production.yaml GPIO pin names follow the consolidated naming convention
      and all pin values are valid BCM numbers (0-27).
  (c) BCM-mode test scripts do not accidentally use BOARD-mode pin numbers (>27).

These tests are pure source-file checks -- no hardware required.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root discovery
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up from this file until we find the directory containing build.sh."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "build.sh").exists():
            return current
        current = current.parent
    raise RuntimeError(
        "Could not find repo root (directory containing build.sh) "
        f"starting from {Path(__file__).resolve().parent}"
    )


REPO_ROOT = _find_repo_root()


# ---------------------------------------------------------------------------
# (a) No stale GPIO pin constants in yanthra_move_system.hpp
# ---------------------------------------------------------------------------


def test_no_stale_gpio_pins_in_yanthra_move():
    """Ensure yanthra_move_system.hpp declares no GPIO pin member variables.

    After the gpio-pin-consolidation change, all GPIO pin constants live in
    constants.py (Python) and production.yaml (ROS2 params).  The C++ header
    should not contain any of the old ``int <pin_name>{...}`` members.
    """
    header = (
        REPO_ROOT
        / "src"
        / "yanthra_move"
        / "include"
        / "yanthra_move"
        / "yanthra_move_system.hpp"
    )
    assert header.exists(), f"Header not found: {header}"
    content = header.read_text()

    # Names that must NOT appear as ``int <name>{`` member declarations.
    # We use word-boundary anchors to avoid matching longer names like
    # ``system_ready_for_start_switch_`` or ``shutdown_switch_in_``.
    stale_pin_names = [
        "vacuum_motor_on_pin_",
        "end_effector_on_pin_",
        "green_led_pin_",
        "red_led_pin_",
        "camera_led_pin_",
        "start_switch_",
        "shutdown_switch_",
        "cotton_drop_servo_pin_",
        "end_effector_direction_pin_",
        "end_effector_drop_on_",
        "end_effector_drop_direction_",
    ]

    violations = []
    for name in stale_pin_names:
        # Match  ``int  <name>{``  with optional whitespace.
        # The negative look-behind prevents matching longer identifiers that
        # happen to end with the target name (e.g. ``start_switch_in_``).
        pattern = rf"int\s+{re.escape(name)}\{{"
        if re.search(pattern, content):
            violations.append(name)

    assert (
        not violations
    ), "yanthra_move_system.hpp still contains stale GPIO pin members:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ---------------------------------------------------------------------------
# (b) production.yaml pin names follow consolidated naming convention
# ---------------------------------------------------------------------------


def test_production_yaml_pin_names():
    """Verify production.yaml uses the correct, consolidated GPIO pin names.

    After consolidation:
      - ``stop_button_pin`` was renamed to ``system_reset_pin``
      - ``direction_switch_pin`` was renamed to ``direction_right_pin``

    Also checks that all pin values are valid BCM numbers (0-27).
    """
    yaml_path = REPO_ROOT / "src" / "vehicle_control" / "config" / "production.yaml"
    assert yaml_path.exists(), f"production.yaml not found: {yaml_path}"
    content = yaml_path.read_text()

    # --- Correct names must be present ---
    assert re.search(
        r"system_reset_pin\s*:", content
    ), "production.yaml is missing 'system_reset_pin' (was it renamed back to stop_button_pin?)"

    assert re.search(
        r"direction_right_pin\s*:", content
    ), "production.yaml is missing 'direction_right_pin' (was it renamed back to direction_switch_pin?)"

    # --- Stale names must NOT be present ---
    assert not re.search(r"stop_button_pin\s*:", content), (
        "production.yaml still uses stale name 'stop_button_pin' "
        "(should be 'system_reset_pin')"
    )
    assert not re.search(r"direction_switch_pin\s*:", content), (
        "production.yaml still uses stale name 'direction_switch_pin' "
        "(should be 'direction_right_pin')"
    )

    # --- All pin values must be valid BCM numbers (0-27) ---
    # Match lines like ``some_pin: 21`` inside the gpio_pins block.
    pin_value_pattern = re.compile(r"(\w+_pin)\s*:\s*(\d+)")
    invalid_pins = []
    for match in pin_value_pattern.finditer(content):
        pin_name = match.group(1)
        pin_value = int(match.group(2))
        if pin_value > 27:
            invalid_pins.append((pin_name, pin_value))

    assert (
        not invalid_pins
    ), "production.yaml contains pin values outside BCM range (0-27):\n" + "\n".join(
        f"  - {name}: {val}" for name, val in invalid_pins
    )


# ---------------------------------------------------------------------------
# (c) No BOARD-mode pin numbers in BCM-mode scripts
# ---------------------------------------------------------------------------


def test_no_board_mode_pins_in_bcm_scripts():
    """Verify BCM-mode motor test scripts only use BCM pin numbers (0-27).

    Scripts that call ``GPIO.setmode(GPIO.BCM)`` must not use pin numbers > 27,
    which would indicate accidental BOARD-mode numbering.
    """
    bcm_scripts = [
        REPO_ROOT / "scripts" / "testing" / "motor" / "endeffector_control.py",
        REPO_ROOT / "scripts" / "testing" / "motor" / "ee_test_bcm.py",
    ]

    pin_assignment_pattern = re.compile(r"(\w*_PIN)\s*=\s*(\d+)")
    violations = []

    for script_path in bcm_scripts:
        assert script_path.exists(), f"Script not found: {script_path}"
        content = script_path.read_text()

        for match in pin_assignment_pattern.finditer(content):
            pin_name = match.group(1)
            pin_value = int(match.group(2))
            if pin_value > 27:
                violations.append(f"  - {script_path.name}: {pin_name} = {pin_value}")

    assert (
        not violations
    ), "BCM-mode scripts contain BOARD-mode pin numbers (> 27):\n" + "\n".join(
        violations
    )
