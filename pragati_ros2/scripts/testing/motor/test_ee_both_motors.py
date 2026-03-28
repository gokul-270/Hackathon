#!/usr/bin/env python3
"""
End Effector Motor Test — Both M1 and M2
=========================================
Tests M1 (picker) and M2 (drop belt) independently using the canonical
BCM pin assignments from gpio_control_functions.hpp.

Pin assignments (BCM numbering):
  M1 Enable    : BCM 21  (END_EFFECTOR_ON_PIN)
  M1 Direction : BCM 13  (END_EFFECTOR_DIRECTION_PIN)  1=CW, 0=CCW
  M2 Enable    : BCM 12  (END_EFFECTOR_DROP_ON)
  M2 Direction : BCM 20  (END_EFFECTOR_DROP_DIRECTION) 1=forward, 0=reverse

Usage:
  python3 test_ee_both_motors.py            # test both M1 and M2
  python3 test_ee_both_motors.py --m1-only  # test M1 (picker) only
  python3 test_ee_both_motors.py --m2-only  # test M2 (drop belt) only

Requirements:
  pigpiod must be running: sudo systemctl start pigpiod
"""

import sys
import time

# ---------------------------------------------------------------------------
# Pin constants — must match gpio_control_functions.hpp
# ---------------------------------------------------------------------------
M1_ENABLE = 21   # END_EFFECTOR_ON_PIN
M1_DIR = 13      # END_EFFECTOR_DIRECTION_PIN  (HIGH=CW, LOW=CCW)
M2_ENABLE = 12   # END_EFFECTOR_DROP_ON
M2_DIR = 20      # END_EFFECTOR_DROP_DIRECTION (HIGH=forward, LOW=reverse)

ALL_PINS = [M1_ENABLE, M1_DIR, M2_ENABLE, M2_DIR]  # M2_DIR now BCM 20

# How long each test step runs (seconds)
RUN_DURATION = 3.0
# Pause between steps with all pins LOW (seconds)
PAUSE_BETWEEN = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def all_off(pi):
    """Drive all EE pins LOW — safe state."""
    for pin in ALL_PINS:
        pi.write(pin, 0)


def set_pin(pi, pin, level):
    """Write a pin and print what is happening."""
    label = {M1_ENABLE: "M1_EN(21)", M1_DIR: "M1_DIR(13)",
             M2_ENABLE: "M2_EN(12)", M2_DIR: "M2_DIR(20)"}[pin]
    print(f"    {label} = {'HIGH' if level else 'LOW '}")
    pi.write(pin, level)


def run_step(pi, title, enable_pin, dir_pin, dir_level, duration):
    """
    Run a single test step:
      1. Set direction pin
      2. Enable motor
      3. Sleep for duration
      4. Stop (all pins LOW)
      5. Pause before next step
    """
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")

    # Set direction first (Cytron best-practice: DIR before EN)
    set_pin(pi, dir_pin, dir_level)
    time.sleep(0.05)  # small settle time
    set_pin(pi, enable_pin, 1)

    print(f"    >>> Running for {duration:.1f}s — observe motor <<<")
    time.sleep(duration)

    # Stop
    set_pin(pi, enable_pin, 0)
    set_pin(pi, dir_pin, 0)
    print(f"    Motor stopped.")
    time.sleep(PAUSE_BETWEEN)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    test_m1 = "--m2-only" not in args
    test_m2 = "--m1-only" not in args

    try:
        import pigpio
    except ImportError:
        print("ERROR: pigpio not installed. Run: pip install pigpio")
        sys.exit(1)

    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: Cannot connect to pigpiod.")
        print("  Start it with: sudo systemctl start pigpiod")
        sys.exit(1)

    print()
    print("=" * 55)
    print("  END EFFECTOR MOTOR TEST")
    print("=" * 55)
    print(f"  M1 (Picker)    — EN=BCM{M1_ENABLE}, DIR=BCM{M1_DIR}")
    print(f"  M2 (Drop Belt) — EN=BCM{M2_ENABLE}, DIR=BCM{M2_DIR}")
    print(f"  Run duration per step: {RUN_DURATION:.1f}s")
    print("=" * 55)

    # Set all pins as outputs and start in safe-off state
    for pin in ALL_PINS:
        pi.set_mode(pin, pigpio.OUTPUT)
    all_off(pi)
    print("\n  All pins initialised LOW (safe state)")
    time.sleep(0.5)

    try:
        # ── M1 tests ────────────────────────────────────────────────────────
        if test_m1:
            print("\n\n>>> M1 — PICKER MOTOR (BCM EN=21, DIR=13) <<<")

            run_step(
                pi,
                title="[1] M1 Clockwise  — DIR=HIGH(13), EN=HIGH(21)",
                enable_pin=M1_ENABLE,
                dir_pin=M1_DIR,
                dir_level=1,
                duration=RUN_DURATION,
            )

            run_step(
                pi,
                title="[2] M1 Counter-CW — DIR=LOW(13),  EN=HIGH(21)",
                enable_pin=M1_ENABLE,
                dir_pin=M1_DIR,
                dir_level=0,
                duration=RUN_DURATION,
            )

        # ── M2 tests ────────────────────────────────────────────────────────
        if test_m2:
            print("\n\n>>> M2 — DROP BELT MOTOR (BCM EN=12, DIR=20) <<<")

            run_step(
                pi,
                title="[3] M2 Forward    — DIR=HIGH(20), EN=HIGH(12)",
                enable_pin=M2_ENABLE,
                dir_pin=M2_DIR,
                dir_level=1,
                duration=RUN_DURATION,
            )

            run_step(
                pi,
                title="[4] M2 Reverse    — DIR=LOW(20),  EN=HIGH(12)",
                enable_pin=M2_ENABLE,
                dir_pin=M2_DIR,
                dir_level=0,
                duration=RUN_DURATION,
            )

        print("\n" + "=" * 55)
        print("  All tests complete.")
        print("  Note which steps showed correct motor behaviour")
        print("  and report back so pin/direction fixes can be made.")
        print("=" * 55)

    except KeyboardInterrupt:
        print("\n\nWARNING: Test interrupted by user (Ctrl+C).")

    except Exception as e:
        print(f"\nERROR during test: {e}")
        sys.exit(1)

    finally:
        # Always drive all pins LOW before releasing pigpio
        all_off(pi)
        pi.stop()
        print("\n  All pins driven LOW — pigpio released.")


if __name__ == "__main__":
    main()
