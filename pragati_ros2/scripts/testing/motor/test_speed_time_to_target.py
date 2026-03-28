#!/usr/bin/env python3
"""
test_speed_time_to_target.py
-----------------------------
Test MG4010 motor speed and time-to-reach-target using MULTI_LOOP_ANGLE_1
(set_absolute_position — no speed cap, motor runs at its own internal speed).

For each test case the script:
  1. Reads current multi-turn angle (start position).
  2. Sends MULTI_LOOP_ANGLE_1 (set_absolute_position) to the target.
  3. Polls READ_MULTI_TURN_ANGLE and READ_STATUS_2 every 50 ms.
  4. Declares "arrived" when speed stays under 5 dps for 5 consecutive reads.
  5. Records:
       - Start angle (deg)
       - Target angle (deg)
       - Actual final angle (deg)
       - Angular error (deg)
       - Peak speed observed (dps)
       - Time to reach target (s)
  6. Prints a result block to the terminal and appends a row to a CSV file.

Usage
-----
    # Single move: motor 1, go to 90 deg
    python3 test_speed_time_to_target.py --motor 1 --target 90

    # Sweep multiple targets
    python3 test_speed_time_to_target.py --motor 1 --targets 45 90 180 360

    # Return to 0 between each test
    python3 test_speed_time_to_target.py --motor 1 --targets 90 180 --return-to-zero

    # Interactive — type values at runtime
    python3 test_speed_time_to_target.py --interactive

    # Custom CAN channel / CSV path
    python3 test_speed_time_to_target.py --motor 1 --target 90 --channel can1 --csv /tmp/out.csv

Run with --help for all options.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — allow running from any working directory
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from mgcan import MG4010_CAN  # noqa: E402


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------
POLL_INTERVAL_S = 0.05           # seconds between each status poll
SETTLE_SPEED_THRESHOLD_DPS = 5   # dps — motor treated as stopped below this
SETTLE_STABLE_COUNT = 5          # consecutive readings below threshold → arrived
MAX_WAIT_S = 30.0                # hard timeout per move (seconds)

# Gear ratio: motor shaft turns 6× per output shaft turn (1:6 reduction).
# The CAN bus reports speed in dps at the MOTOR shaft.
# Motor shaft RPM  = dps / 6
# Output shaft RPM = dps / (6 * GEAR_RATIO)
GEAR_RATIO = 6
DPS_TO_MOTOR_RPM = 1.0 / 6.0                    # motor shaft RPM  (before gearbox)
DPS_TO_OUTPUT_RPM = 1.0 / (6.0 * GEAR_RATIO)    # output shaft RPM (after 1:6 gearbox)

DEFAULT_CSV = os.path.join(_SCRIPT_DIR, "speed_time_results.csv")

# ---------------------------------------------------------------------------
# Per-motor position limits (degrees)
# Format: motor_id -> (min_deg, max_deg)
# Commands outside this range are dropped before sending to the motor.
# ---------------------------------------------------------------------------
MOTOR_LIMITS = {
    1: (-8000, 0),    # motor 1: min -8000 deg, max 0 deg
    2: (0,    280),   # motor 2: min 0 deg,     max 280 deg
    3: (-2000, 2000), # motor 3: min -2000 deg, max 2000 deg
}

CSV_HEADER = [
    "timestamp",
    "motor_id",
    "target_deg",
    "start_deg",
    "actual_final_deg",
    "angle_error_deg",
    "peak_speed_dps",
    "peak_motor_shaft_rpm",
    "peak_output_shaft_rpm",
    "move_start_time",        # wall-clock time the move command was sent
    "time_to_target_s",       # seconds from move command to motor settled
    "settled",
    "notes",
]

# Poll log — every sample during a move is written here
POLL_LOG_HEADER = [
    "timestamp",       # wall-clock time of this sample
    "motor_id",
    "target_deg",
    "elapsed_s",       # seconds since move command was sent
    "angle_deg",       # current motor angle
    "speed_dps",       # motor shaft speed
    "motor_rpm",       # motor shaft RPM
    "output_rpm",      # output shaft RPM (after 1:6 gearbox)
]
POLL_LOG_CSV = os.path.join(_SCRIPT_DIR, "speed_time_poll_log.csv")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _check_limit(motor_id: int, target_deg: float) -> bool:
    """
    Return True if target_deg is within the allowed range for motor_id.
    If the motor_id has no entry in MOTOR_LIMITS, the move is allowed.
    Prints a clear error message when the limit is exceeded.
    """
    if motor_id not in MOTOR_LIMITS:
        return True  # no limit defined — allow
    min_deg, max_deg = MOTOR_LIMITS[motor_id]
    if min_deg <= target_deg <= max_deg:
        return True
    print(
        f"  [LIMIT EXCEEDED] Motor {motor_id}: target {target_deg} deg is outside "
        f"allowed range [{min_deg}, {max_deg}] deg. Command dropped."
    )
    return False


def _read_angle(motor: MG4010_CAN, motor_id: int) -> Optional[float]:
    """Read multi-turn angle in degrees via READ_MULTI_TURN_ANGLE (0x92)."""
    resp = motor.read_multi_turn_angle(motor_id)
    if resp and "multi_turn_angle" in resp:
        return resp["multi_turn_angle"]
    return None


def _read_speed(motor: MG4010_CAN, motor_id: int) -> Optional[float]:
    """Read speed_dps via READ_STATUS_2 (0x9C)."""
    resp = motor.read_motor_status_2(motor_id)
    if resp and "speed_dps" in resp:
        return resp["speed_dps"]
    return None


def _print_row(label: str, value: str, unit: str = "") -> None:
    print(f"  {label:<35} {value} {unit}".rstrip())


def _print_result_block(r: dict) -> None:
    w = 58
    print("\n" + "=" * w)
    print(f"  Motor {r['motor_id']}  |  Target {r['target_deg']:.2f} deg")
    print("-" * w)
    _print_row("Start angle",         f"{r['start_deg']:.3f}",        "deg")
    _print_row("Target angle",        f"{r['target_deg']:.3f}",       "deg")
    _print_row("Actual final angle",  f"{r['actual_final_deg']:.3f}", "deg")
    _print_row("Angular error",       f"{r['angle_error_deg']:.3f}",  "deg")
    _print_row("Peak speed (motor shaft)",  f"{r['peak_speed_dps']:.1f} dps  /  {r['peak_motor_shaft_rpm']:.2f} RPM")
    _print_row("Peak speed (output shaft)", f"{r['peak_output_shaft_rpm']:.2f} RPM  (after 1:6 gearbox)")
    _print_row("Time to target",      f"{r['time_to_target_s']:.3f}", "s")
    _print_row("Settled",             "YES" if r["settled"] else "NO (timed out)")
    if r.get("notes"):
        _print_row("Notes", r["notes"])
    print("=" * w)


def _append_csv(filepath: str, row: dict) -> None:
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in CSV_HEADER})


def _append_poll_log(filepath: str, row: dict) -> None:
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=POLL_LOG_HEADER)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in POLL_LOG_HEADER})


# ---------------------------------------------------------------------------
# Core test function
# ---------------------------------------------------------------------------

def run_single_test(
    motor: MG4010_CAN,
    motor_id: int,
    target_deg: float,
    csv_path: str,
    poll_log_path: str,
    return_to_zero: bool = False,
) -> dict:
    """
    Move motor_id to target_deg using MULTI_LOOP_ANGLE_1 (no speed cap).
    Polls until settled or timeout. Saves result to CSV and returns result dict.
    Every poll sample is written to poll_log_path.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    notes = ""

    # ---- 1. Read start angle ----
    print(f"\n[Motor {motor_id}] Reading start angle ...")
    start_deg = _read_angle(motor, motor_id)
    if start_deg is None:
        notes = "Could not read start angle"
        print(f"  WARNING: {notes}")
        start_deg = float("nan")
    else:
        print(f"  Start  : {start_deg:.3f} deg")

    print(f"  Target : {target_deg:.3f} deg")

    # ---- 2. Limit check — drop command if out of range ----
    if not _check_limit(motor_id, target_deg):
        notes = f"Limit exceeded: {target_deg} deg outside {MOTOR_LIMITS.get(motor_id, 'N/A')}"
        result = {
            "timestamp": timestamp,
            "motor_id": motor_id,
            "target_deg": target_deg,
            "start_deg": start_deg,
            "actual_final_deg": float("nan"),
            "angle_error_deg": float("nan"),
            "peak_speed_dps": 0.0,
            "peak_motor_shaft_rpm": 0.0,
            "peak_output_shaft_rpm": 0.0,
            "time_to_target_s": float("nan"),
            "settled": False,
            "notes": notes,
        }
        _append_csv(csv_path, result)
        return result

    # ---- 3. Send MULTI_LOOP_ANGLE_1 move command ----
    print(f"[Motor {motor_id}] Sending set_absolute_position ({target_deg} deg) ...")
    move_start_time = datetime.now().isoformat(timespec="milliseconds")
    t_start = time.monotonic()
    resp = motor.set_absolute_position(motor_id, target_deg)

    if resp is None:
        notes = "set_absolute_position command failed — no response"
        print(f"  ERROR: {notes}")
        result = {
            "timestamp": timestamp,
            "motor_id": motor_id,
            "target_deg": target_deg,
            "start_deg": start_deg,
            "actual_final_deg": float("nan"),
            "angle_error_deg": float("nan"),
            "peak_speed_dps": 0.0,
            "peak_motor_shaft_rpm": 0.0,
            "peak_output_shaft_rpm": 0.0,
            "time_to_target_s": float("nan"),
            "settled": False,
            "notes": notes,
        }
        _print_result_block(result)
        _append_csv(csv_path, result)
        return result

    # ---- 3. Poll speed + angle until settled or timeout ----
    print(
        f"[Motor {motor_id}] Polling ... "
        f"(timeout {MAX_WAIT_S:.0f}s, settle threshold {SETTLE_SPEED_THRESHOLD_DPS} dps)"
    )

    peak_speed = 0.0
    stable_count = 0
    settled = False
    t_settle = None

    while True:
        elapsed = time.monotonic() - t_start
        if elapsed >= MAX_WAIT_S:
            print(f"  [t={elapsed:.2f}s] Timeout — motor did not settle.")
            break

        speed = _read_speed(motor, motor_id)
        angle = _read_angle(motor, motor_id)

        if speed is None:
            time.sleep(POLL_INTERVAL_S)
            continue

        abs_speed = abs(speed)
        if abs_speed > peak_speed:
            peak_speed = abs_speed

        motor_rpm = speed * DPS_TO_MOTOR_RPM
        output_rpm = speed * DPS_TO_OUTPUT_RPM

        # Write every sample to the poll log
        _append_poll_log(poll_log_path, {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "motor_id": motor_id,
            "target_deg": target_deg,
            "elapsed_s": round(elapsed, 4),
            "angle_deg": round(angle, 4) if angle is not None else "",
            "speed_dps": round(speed, 2),
            "motor_rpm": round(motor_rpm, 4),
            "output_rpm": round(output_rpm, 4),
        })

        angle_str = f"{angle:.2f} deg" if angle is not None else "N/A"
        print(
            f"  [t={elapsed:.2f}s]  speed={speed:+6.1f} dps"
            f"  motor={motor_rpm:+6.2f} RPM  output={output_rpm:+5.2f} RPM"
            f"  angle={angle_str}",
            end="",
        )

        if abs_speed < SETTLE_SPEED_THRESHOLD_DPS:
            stable_count += 1
            print(f"   (stable {stable_count}/{SETTLE_STABLE_COUNT})")
            if stable_count >= SETTLE_STABLE_COUNT:
                t_settle = elapsed
                settled = True
                break
        else:
            stable_count = 0
            print()

        time.sleep(POLL_INTERVAL_S)

    time_to_target = t_settle if settled else (time.monotonic() - t_start)

    # ---- 4. Read final angle ----
    final_deg = _read_angle(motor, motor_id)
    if final_deg is None:
        notes = (notes + " | Could not read final angle").lstrip(" |")
        final_deg = float("nan")
        angle_error = float("nan")
    else:
        angle_error = final_deg - target_deg

    # ---- 5. Optionally return to zero ----
    if return_to_zero and motor.bus:
        print(f"[Motor {motor_id}] Returning to 0 deg ...")
        if _check_limit(motor_id, 0.0):
            motor.set_absolute_position(motor_id, 0.0)
            time.sleep(1.0)
        else:
            print(f"  [LIMIT EXCEEDED] 0 deg is outside limits for motor {motor_id} — skipping return.")

    # ---- 6. Build result, print and save ----
    result = {
        "timestamp": timestamp,
        "motor_id": motor_id,
        "target_deg": target_deg,
        "start_deg": start_deg,
        "actual_final_deg": final_deg,
        "angle_error_deg": angle_error,
        "peak_speed_dps": peak_speed,
        "peak_motor_shaft_rpm": round(peak_speed * DPS_TO_MOTOR_RPM, 4),
        "peak_output_shaft_rpm": round(peak_speed * DPS_TO_OUTPUT_RPM, 4),
        "move_start_time": move_start_time,
        "time_to_target_s": time_to_target,
        "settled": settled,
        "notes": notes,
    }

    _print_result_block(result)
    _append_csv(csv_path, result)
    print(f"  Results saved to : {csv_path}")
    print(f"  Poll log saved to: {poll_log_path}")
    return result


# ---------------------------------------------------------------------------
# Simultaneous multi-motor test
# ---------------------------------------------------------------------------

def run_all_motors_test(
    motor: MG4010_CAN,
    targets: Dict[int, float],
    csv_path: str,
    poll_log_path: str,
) -> List[dict]:
    """
    Move multiple motors simultaneously using MULTI_LOOP_ANGLE_1.

    All move commands are sent back-to-back before the poll loop begins,
    so the motors start as close to simultaneously as CAN bus latency allows.

    Each motor tracks its own peak speed, stable count, and settled state.
    The poll loop runs until ALL motors have settled or the global timeout
    fires.  Results for each motor are saved to the same CSV files used by
    run_single_test() and a combined summary table is printed at the end.

    Args:
        motor:         Initialised MG4010_CAN instance.
        targets:       {motor_id: target_deg} mapping.  Entries whose target
                       violates MOTOR_LIMITS are skipped.
        csv_path:      Summary results CSV path.
        poll_log_path: Per-sample poll log CSV path.

    Returns:
        List of result dicts (one per motor that was actually commanded).
    """
    if not targets:
        print("[all-motors] No targets provided — nothing to do.")
        return []

    timestamp_run = datetime.now().isoformat(timespec="seconds")

    # ---- 1. Limit-check and read start angles ----
    valid: Dict[int, float] = {}  # motor_id -> target_deg (after limit check)
    start_angles: Dict[int, float] = {}

    for mid, tgt in sorted(targets.items()):
        if not _check_limit(mid, tgt):
            continue
        angle = _read_angle(motor, mid)
        if angle is None:
            print(f"  [Motor {mid}] WARNING: Could not read start angle — skipping.")
            continue
        valid[mid] = tgt
        start_angles[mid] = angle
        print(f"[Motor {mid}] Start: {angle:.3f} deg  →  Target: {tgt:.3f} deg")

    if not valid:
        print("[all-motors] No valid motors to move — aborting.")
        return []

    # ---- 2. Send all move commands back-to-back ----
    print(f"\n[all-motors] Sending {len(valid)} move command(s) ...")
    move_start_wall: Dict[int, str] = {}
    t_start = time.monotonic()

    failed_send: List[int] = []
    for mid, tgt in sorted(valid.items()):
        move_start_wall[mid] = datetime.now().isoformat(timespec="milliseconds")
        resp = motor.set_absolute_position(mid, tgt)
        if resp is None:
            print(f"  [Motor {mid}] ERROR: set_absolute_position returned no response.")
            failed_send.append(mid)

    for mid in failed_send:
        del valid[mid]

    if not valid:
        print("[all-motors] All move commands failed — aborting.")
        return []

    # ---- 3. Shared poll loop ----
    print(
        f"[all-motors] Polling {list(sorted(valid.keys()))} ... "
        f"(timeout {MAX_WAIT_S:.0f}s, settle {SETTLE_SPEED_THRESHOLD_DPS} dps)"
    )

    # Per-motor tracking state
    peak_speed:   Dict[int, float] = {mid: 0.0 for mid in valid}
    stable_count: Dict[int, int]   = {mid: 0   for mid in valid}
    settled:      Dict[int, bool]  = {mid: False for mid in valid}
    t_settle:     Dict[int, Optional[float]] = {mid: None for mid in valid}

    timed_out = False

    while True:
        elapsed = time.monotonic() - t_start
        if elapsed >= MAX_WAIT_S:
            print(f"  [t={elapsed:.2f}s] Global timeout — some motors may not have settled.")
            timed_out = True
            break
        if all(settled.values()):
            break

        for mid in sorted(valid.keys()):
            if settled[mid]:
                continue  # already done — skip polling this motor

            speed = _read_speed(motor, mid)
            angle = _read_angle(motor, mid)

            if speed is None:
                continue  # skip this motor this iteration

            abs_speed = abs(speed)
            if abs_speed > peak_speed[mid]:
                peak_speed[mid] = abs_speed

            motor_rpm  = speed * DPS_TO_MOTOR_RPM
            output_rpm = speed * DPS_TO_OUTPUT_RPM

            _append_poll_log(poll_log_path, {
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "motor_id": mid,
                "target_deg": valid[mid],
                "elapsed_s": round(elapsed, 4),
                "angle_deg": round(angle, 4) if angle is not None else "",
                "speed_dps": round(speed, 2),
                "motor_rpm": round(motor_rpm, 4),
                "output_rpm": round(output_rpm, 4),
            })

            angle_str = f"{angle:.2f} deg" if angle is not None else "N/A"
            print(
                f"  [t={elapsed:.2f}s] M{mid}"
                f"  speed={speed:+6.1f} dps"
                f"  motor={motor_rpm:+6.2f} RPM  output={output_rpm:+5.2f} RPM"
                f"  angle={angle_str}",
                end="",
            )

            if abs_speed < SETTLE_SPEED_THRESHOLD_DPS:
                stable_count[mid] += 1
                print(f"   (stable {stable_count[mid]}/{SETTLE_STABLE_COUNT})")
                if stable_count[mid] >= SETTLE_STABLE_COUNT:
                    t_settle[mid] = elapsed
                    settled[mid] = True
            else:
                stable_count[mid] = 0
                print()

        time.sleep(POLL_INTERVAL_S)

    # ---- 4. Read final angles + build results ----
    results: List[dict] = []

    for mid in sorted(valid.keys()):
        tgt = valid[mid]
        final_deg = _read_angle(motor, mid)
        notes = ""

        if final_deg is None:
            notes = "Could not read final angle"
            final_deg_val = float("nan")
            angle_error = float("nan")
        else:
            final_deg_val = final_deg
            angle_error = final_deg - tgt

        if timed_out and not settled[mid]:
            time_to_tgt = time.monotonic() - t_start
        else:
            time_to_tgt = t_settle[mid] if t_settle[mid] is not None else (time.monotonic() - t_start)

        result = {
            "timestamp": timestamp_run,
            "motor_id": mid,
            "target_deg": tgt,
            "start_deg": start_angles.get(mid, float("nan")),
            "actual_final_deg": final_deg_val,
            "angle_error_deg": angle_error,
            "peak_speed_dps": peak_speed[mid],
            "peak_motor_shaft_rpm": round(peak_speed[mid] * DPS_TO_MOTOR_RPM, 4),
            "peak_output_shaft_rpm": round(peak_speed[mid] * DPS_TO_OUTPUT_RPM, 4),
            "move_start_time": move_start_wall.get(mid, ""),
            "time_to_target_s": time_to_tgt,
            "settled": settled[mid],
            "notes": notes,
        }

        _print_result_block(result)
        _append_csv(csv_path, result)
        results.append(result)

    # ---- 5. Combined summary table ----
    col = 13
    hdr = (
        f"{'Motor':>{col}} {'Target':>{col}} {'PeakDPS':>{col}} {'MotorRPM':>{col}} "
        f"{'OutputRPM':>{col}} {'TimeToTgt':>{col}} {'Error':>{col}} {'Settled':>{col}}"
    )
    sep = "-" * len(hdr)
    print(f"\n{'=' * len(hdr)}")
    print("ALL-MOTORS SUMMARY")
    print(sep)
    print(hdr)
    print(sep)
    for r in results:
        print(
            f"{r['motor_id']:>{col}} "
            f"{r['target_deg']:>{col}.2f} "
            f"{r['peak_speed_dps']:>{col}.1f} "
            f"{r['peak_motor_shaft_rpm']:>{col}.2f} "
            f"{r['peak_output_shaft_rpm']:>{col}.2f} "
            f"{r['time_to_target_s']:>{col}.3f} "
            f"{r['angle_error_deg']:>{col}.3f} "
            f"{'YES' if r['settled'] else 'TIMEOUT':>{col}}"
        )
    print(f"{'=' * len(hdr)}\n")
    print(f"  Results saved to : {csv_path}")
    print(f"  Poll log saved to: {poll_log_path}")

    return results


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def interactive_mode(motor: MG4010_CAN, csv_path: str, poll_log_path: str) -> None:
    print("\n--- Interactive Test Mode ---")
    print("Type 'quit' or Ctrl-C to exit.\n")
    while True:
        try:
            raw_id = input("Motor ID (1-32): ").strip()
            if raw_id.lower() in ("quit", "q", "exit"):
                break
            motor_id = int(raw_id)
            if not (1 <= motor_id <= 32):
                print("  Motor ID must be 1-32.")
                continue

            raw_target = input("Target angle (degrees): ").strip()
            if raw_target.lower() in ("quit", "q", "exit"):
                break
            target_deg = float(raw_target)

            raw_ret = input("Return to 0 after test? [y/N]: ").strip().lower()
            return_to_zero = raw_ret in ("y", "yes")

            # Limit check before anything else
            if not _check_limit(motor_id, target_deg):
                continue

            # Pre-move health check
            print(f"\n[Motor {motor_id}] Health check ...")
            health = motor.check_motor_health(motor_id)
            print(f"  Health OK  : {health.get('health_ok')}")
            print(f"  Temperature: {health.get('temperature')} C")
            print(f"  Voltage    : {health.get('voltage')} V")
            print(f"  Errors     : {health.get('errors')}")
            if not health.get("health_ok"):
                proceed = input("  Health check failed. Proceed anyway? [y/N]: ").strip().lower()
                if proceed not in ("y", "yes"):
                    continue

            run_single_test(motor, motor_id, target_deg, csv_path, poll_log_path, return_to_zero)

            another = input("\nRun another test? [Y/n]: ").strip().lower()
            if another in ("n", "no"):
                break

        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        except ValueError as e:
            print(f"  Invalid input: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Test MG4010 motor speed and time-to-target using MULTI_LOOP_ANGLE_1 "
            "(set_absolute_position, no speed cap)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single move
  python3 test_speed_time_to_target.py --motor 1 --target 90

  # Sweep multiple targets
  python3 test_speed_time_to_target.py --motor 1 --targets 45 90 180 360

  # Return to zero between tests
  python3 test_speed_time_to_target.py --motor 1 --targets 90 180 --return-to-zero

  # Move all three motors simultaneously
  python3 test_speed_time_to_target.py --all-motors --target-1 -100 --target-2 200 --target-3 500

  # Interactive session
  python3 test_speed_time_to_target.py --interactive

  # Custom CAN interface and output file
  python3 test_speed_time_to_target.py --motor 1 --target 90 --channel can1 --csv /tmp/out.csv
""",
    )
    p.add_argument("--motor", type=int, default=None,
                   help="Motor ID (1-32). Required unless --interactive is set.")
    p.add_argument("--target", type=float, default=None,
                   help="Single target angle in degrees.")
    p.add_argument("--targets", type=float, nargs="+", default=None,
                   help="Multiple target angles in degrees (run in order).")
    p.add_argument("--return-to-zero", action="store_true",
                   help="Return motor to 0 deg after each test move.")
    p.add_argument("--interactive", action="store_true",
                   help="Enter interactive mode — type motor ID and target at runtime.")
    p.add_argument("--channel", type=str, default="can0",
                   help="CAN interface name (default: can0).")
    p.add_argument("--bitrate", type=int, default=500000,
                   help="CAN bitrate in bps (default: 500000).")
    p.add_argument("--timeout", type=float, default=0.05,
                   help="CAN response timeout in seconds (default: 0.05).")
    p.add_argument("--csv", type=str, default=DEFAULT_CSV,
                   help=f"CSV output path (default: {DEFAULT_CSV}).")
    p.add_argument("--poll-log", type=str, default=POLL_LOG_CSV,
                   help=f"Per-sample poll log CSV path (default: {POLL_LOG_CSV}).")
    p.add_argument("--no-health-check", action="store_true",
                   help="Skip pre-test health check.")
    # ---- all-motors mode ----
    p.add_argument("--all-motors", action="store_true",
                   help="Move all motors simultaneously. Use with --target-1, --target-2, --target-3.")
    p.add_argument("--target-1", type=float, default=None,
                   help="Target angle for motor 1 in --all-motors mode.")
    p.add_argument("--target-2", type=float, default=None,
                   help="Target angle for motor 2 in --all-motors mode.")
    p.add_argument("--target-3", type=float, default=None,
                   help="Target angle for motor 3 in --all-motors mode.")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # ---- Connect ----
    print(f"[init] Connecting to '{args.channel}' @ {args.bitrate} bps ...")
    motor = MG4010_CAN(
        channel=args.channel,
        bitrate=args.bitrate,
        response_timeout=args.timeout,
        retries=1,
    )
    if not motor.bus:
        print("[init] ERROR: CAN bus not initialized. Aborting.")
        return 1

    # ---- Interactive ----
    if args.interactive:
        interactive_mode(motor, args.csv, args.poll_log)
        return 0

    # ---- All-motors simultaneous mode ----
    if args.all_motors:
        target_map: Dict[int, float] = {}
        if args.target_1 is not None:
            target_map[1] = args.target_1
        if args.target_2 is not None:
            target_map[2] = args.target_2
        if args.target_3 is not None:
            target_map[3] = args.target_3

        if not target_map:
            parser.error(
                "--all-motors requires at least one of --target-1, --target-2, --target-3."
            )

        # Health checks for all motors
        if not args.no_health_check:
            for mid in sorted(target_map.keys()):
                print(f"\n[Motor {mid}] Pre-test health check ...")
                health = motor.check_motor_health(mid)
                print(f"  Accessible : {health.get('accessible')}")
                print(f"  Health OK  : {health.get('health_ok')}")
                print(f"  Temperature: {health.get('temperature')} C")
                print(f"  Voltage    : {health.get('voltage')} V")
                print(f"  Errors     : {health.get('errors')}")
                if not health.get("health_ok"):
                    print("  WARNING: Attempting auto-recovery ...")
                    recovery = motor.recover_from_error(mid)
                    if not recovery["success"]:
                        print(f"  ERROR: Recovery failed — {recovery['message']}. Aborting.")
                        return 1
                    print(f"  Recovery OK: {recovery['message']}")

        print(f"\n[all-motors] Moving motors {sorted(target_map.keys())} simultaneously.")
        print(f"  Results CSV : {args.csv}")
        print(f"  Poll log CSV: {args.poll_log}\n")

        run_all_motors_test(motor, target_map, args.csv, args.poll_log)
        return 0

    # ---- Validate single-motor batch args ----
    if args.motor is None:
        parser.error("--motor is required (or use --interactive).")
    if not (1 <= args.motor <= 32):
        parser.error("--motor must be between 1 and 32.")
    if args.target is None and not args.targets:
        parser.error("Specify --target <deg> or --targets <deg> [...] (or use --interactive).")

    targets: List[float] = []
    if args.target is not None:
        targets.append(args.target)
    if args.targets:
        targets.extend(args.targets)

    motor_id = args.motor

    # ---- Pre-test health check ----
    if not args.no_health_check:
        print(f"\n[Motor {motor_id}] Pre-test health check ...")
        health = motor.check_motor_health(motor_id)
        print(f"  Accessible : {health.get('accessible')}")
        print(f"  Health OK  : {health.get('health_ok')}")
        print(f"  Temperature: {health.get('temperature')} C")
        print(f"  Voltage    : {health.get('voltage')} V")
        print(f"  Errors     : {health.get('errors')}")
        if not health.get("health_ok"):
            print("  WARNING: Attempting auto-recovery ...")
            recovery = motor.recover_from_error(motor_id)
            if not recovery["success"]:
                print(f"  ERROR: Recovery failed — {recovery['message']}. Aborting.")
                return 1
            print(f"  Recovery OK: {recovery['message']}")

    # ---- Run tests ----
    print(f"\n[Batch] {len(targets)} test(s) on motor {motor_id}.")
    print(f"  Results CSV : {args.csv}")
    print(f"  Poll log CSV: {args.poll_log}\n")

    all_results = []
    for i, target in enumerate(targets, start=1):
        print(f"\n--- Test {i}/{len(targets)} ---")
        result = run_single_test(
            motor,
            motor_id,
            target,
            args.csv,
            args.poll_log,
            return_to_zero=args.return_to_zero,
        )
        all_results.append(result)
        if i < len(targets):
            time.sleep(0.5)

    # ---- Summary table (batch only) ----
    if len(all_results) > 1:
        col = 13
        hdr = (
            f"{'Target':>{col}} {'PeakDPS':>{col}} {'MotorRPM':>{col}} {'OutputRPM':>{col}} "
            f"{'TimeToTgt':>{col}} {'Error':>{col}} {'Settled':>{col}}"
        )
        sep = "-" * len(hdr)
        print(f"\n{'=' * len(hdr)}")
        print("SUMMARY")
        print(sep)
        print(hdr)
        print(sep)
        for r in all_results:
            print(
                f"{r['target_deg']:>{col}.2f} "
                f"{r['peak_speed_dps']:>{col}.1f} "
                f"{r['peak_motor_shaft_rpm']:>{col}.2f} "
                f"{r['peak_output_shaft_rpm']:>{col}.2f} "
                f"{r['time_to_target_s']:>{col}.3f} "
                f"{r['angle_error_deg']:>{col}.3f} "
                f"{'YES' if r['settled'] else 'TIMEOUT':>{col}}"
            )
        print(f"{'=' * len(hdr)}\n")

    print(f"All results saved to: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
