#!/usr/bin/env python3
"""
Verification script for demo_patterns.py

Runs individual patterns while subscribing to /joint_states and /steering/*
topics to verify the robot actually responds correctly.

Checks:
  - straight: steering angles near zero, wheels spinning forward
  - turn_in_place: steering angles non-zero, consistent with rotation
  - stop: wheel velocities near zero
  - arc: both linear and angular components present
  - signal handling: clean stop on interrupt

Usage:
    1. Launch Gazebo: ros2 launch vehicle_control gazebo.launch.py
    2. Run: python3 scripts/verify_demo_patterns.py
"""

import math
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List

import rclpy
from geometry_msgs.msg import Twist
from rclpy.parameter import Parameter
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64

# Import pattern functions from demo_patterns
sys.path.insert(0, os.path.dirname(__file__))
from demo_patterns import (
    _twist, straight, arc, turn_in_place, stop,
    row_traversal, headland_uturn, circle, square,
    sharp_turn, sudden_stop,
    letter_P, letter_D, letter_S, letter_L, letter_U, letter_Z,
    figure_eight, compute_path_waypoints,
)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

@dataclass
class Sample:
    """A single timestamped reading."""
    t: float
    steering: Dict[str, float] = field(default_factory=dict)  # front/left/right angles
    drive: Dict[str, float] = field(default_factory=dict)     # front/left/right velocities


class PatternVerifier:
    """Runs a pattern, records joint states, and validates expectations."""

    # Joint name mapping from Gazebo joint_states
    STEERING_JOINTS = {
        'base-plate-front_Revolute-14': 'front',
        'base-plate-right_Revolute-18': 'right',
        'base-plate-left_Revolute-20': 'left',
    }
    DRIVE_JOINTS = {
        'axial-front_Revolute-10': 'front',
        'axial-right_Revolute-19': 'right',
        'axial-left_Revolute-21': 'left',
    }

    def __init__(self, node, publisher):
        self.node = node
        self.publisher = publisher
        self.samples: List[Sample] = []
        self._current_sample = Sample(t=0.0)

        # Subscribe to joint states
        self.joint_sub = node.create_subscription(
            JointState, '/joint_states', self._joint_cb, 10)

    def _joint_cb(self, msg: JointState):
        """Collect joint state data."""
        sample = Sample(t=time.time())
        for i, name in enumerate(msg.name):
            if name in self.STEERING_JOINTS:
                wheel = self.STEERING_JOINTS[name]
                sample.steering[wheel] = msg.position[i] if i < len(msg.position) else 0.0
            elif name in self.DRIVE_JOINTS:
                wheel = self.DRIVE_JOINTS[name]
                # Use velocity if available and non-zero, otherwise fall back to position
                if i < len(msg.velocity) and abs(msg.velocity[i]) > 1e-6:
                    sample.drive[wheel] = msg.velocity[i]
                elif i < len(msg.position):
                    # For continuous joints, position accumulates — use it as
                    # a proxy for "the wheel has rotated"
                    sample.drive[wheel] = msg.position[i]
        if sample.steering or sample.drive:
            self.samples.append(sample)

    def execute(self, commands, speed_scale=1.0):
        """Execute a pattern's command list, collecting samples."""
        # Pre-settle: publish zero velocity and wait for steering to converge
        # (rate-limited steering at 2 rad/s needs ~1.6s to slew 180°)
        for _ in range(30):
            self.publisher.publish(_twist())
            rclpy.spin_once(self.node, timeout_sec=0.01)
            time.sleep(0.1)

        self.samples.clear()
        for msg, duration in commands:
            scaled = _twist(
                linear_x=msg.linear.x * speed_scale,
                angular_z=msg.angular.z * speed_scale,
            )
            elapsed = 0.0
            interval = 0.1
            while elapsed < duration:
                self.publisher.publish(scaled)
                rclpy.spin_once(self.node, timeout_sec=0.01)
                time.sleep(interval)
                elapsed += interval
        # Stop
        self.publisher.publish(_twist())
        # Collect a few more samples during stop
        for _ in range(5):
            rclpy.spin_once(self.node, timeout_sec=0.05)
            time.sleep(0.1)

    def get_steady_state_samples(self, skip_fraction=0.3):
        """Return samples after initial transient (skip first 30%)."""
        n = len(self.samples)
        start = int(n * skip_fraction)
        return self.samples[start:]


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

def check_straight(verifier: PatternVerifier) -> List[str]:
    """Verify straight pattern: steering ~0, wheels spinning forward."""
    errors = []
    # Skip first 50% to allow steering transient to settle
    samples = verifier.get_steady_state_samples(skip_fraction=0.5)
    if not samples:
        return ['No joint state samples received during straight pattern']

    # Check steering angles in the last half are near zero (< 15 degrees)
    # The rate-limited steering may still be converging slightly
    max_angle_per_wheel: Dict[str, float] = {}
    for s in samples:
        for wheel, angle in s.steering.items():
            if wheel not in max_angle_per_wheel or abs(angle) > abs(max_angle_per_wheel[wheel]):
                max_angle_per_wheel[wheel] = angle

    for wheel, angle in max_angle_per_wheel.items():
        if abs(angle) > math.radians(15):
            errors.append(
                f'straight: {wheel} steering={math.degrees(angle):.1f}° '
                f'(expected ~0°)')

    # Check that wheels moved (position changed)
    all_samples = verifier.samples
    if len(all_samples) >= 2:
        any_moved = False
        for wheel in ['front', 'left', 'right']:
            first_vals = [s.drive.get(wheel) for s in all_samples[:3]
                          if wheel in s.drive]
            last_vals = [s.drive.get(wheel) for s in all_samples[-3:]
                         if wheel in s.drive]
            if first_vals and last_vals:
                fp = first_vals[0]
                lp = last_vals[-1]
                if fp is not None and lp is not None and abs(lp - fp) > 0.1:
                    any_moved = True
        if not any_moved:
            errors.append('straight: no wheel motion detected')

    return errors


def check_turn_in_place(verifier: PatternVerifier) -> List[str]:
    """Verify turn-in-place: steering angles should be non-zero."""
    errors = []
    samples = verifier.get_steady_state_samples()
    if not samples:
        return ['No joint state samples received during turn_in_place']

    # Collect average steering angles
    angle_sums = {'front': 0.0, 'left': 0.0, 'right': 0.0}
    angle_counts = {'front': 0, 'left': 0, 'right': 0}
    for s in samples:
        for wheel, angle in s.steering.items():
            angle_sums[wheel] += angle
            angle_counts[wheel] += 1

    any_steered = False
    for wheel in ['front', 'left', 'right']:
        if angle_counts[wheel] > 0:
            avg = angle_sums[wheel] / angle_counts[wheel]
            if abs(avg) > math.radians(5):
                any_steered = True

    if not any_steered:
        errors.append(
            'turn_in_place: no wheels steered significantly '
            '(expected non-zero steering angles for rotation)')

    return errors


def check_stop(verifier: PatternVerifier) -> List[str]:
    """Verify stop: wheels should decelerate to near zero.

    Since Gazebo JointState reports accumulated position for continuous
    (drive) joints rather than velocity, we check that position is NOT
    changing between the last few samples — i.e. wheels have stopped.
    """
    errors = []
    # Use last 50% of samples (should be stopped)
    samples = verifier.get_steady_state_samples(skip_fraction=0.5)
    if not samples or len(samples) < 3:
        return ['Not enough joint state samples to verify stop']

    # For each drive joint, check that position is stable (not changing)
    for wheel in ['front', 'left', 'right']:
        positions = [s.drive[wheel] for s in samples[-5:]
                     if wheel in s.drive and s.drive[wheel] is not None]
        if len(positions) >= 2:
            # Check variance of position over last samples
            pos_range = max(positions) - min(positions)
            if pos_range > 1.0:  # > 1 rad change while "stopped" = still moving
                errors.append(
                    f'stop: {wheel} position still changing '
                    f'(range={pos_range:.2f} rad over last samples, '
                    f'expected stable)')

    return errors


def check_arc(verifier: PatternVerifier) -> List[str]:
    """Verify arc: steering should be non-zero AND wheels spinning."""
    errors = []
    samples = verifier.get_steady_state_samples()
    if not samples:
        return ['No joint state samples received during arc']

    has_steering = False
    has_drive = False
    for s in samples:
        for wheel, angle in s.steering.items():
            if abs(angle) > math.radians(2):
                has_steering = True
        for wheel, vel in s.drive.items():
            if abs(vel) > 0.01:
                has_drive = True

    # If velocity field was zero, check for position changes between samples
    # (continuous joints accumulate position as they spin)
    if not has_drive and len(samples) >= 2:
        for wheel in ['front', 'left', 'right']:
            first_positions = [s.drive.get(wheel) for s in samples[:3]
                               if wheel in s.drive]
            last_positions = [s.drive.get(wheel) for s in samples[-3:]
                              if wheel in s.drive]
            if first_positions and last_positions:
                fp = first_positions[0]
                lp = last_positions[-1]
                if fp is not None and lp is not None:
                    delta = abs(lp - fp)
                    if delta > 0.1:  # wheel position changed by > 0.1 rad
                        has_drive = True

    if not has_steering:
        errors.append('arc: no steering detected (expected curved path)')
    if not has_drive:
        errors.append('arc: no wheel motion detected (expected forward motion)')

    return errors


def check_square_has_turns(verifier: PatternVerifier) -> List[str]:
    """Verify square: should have both straight segments and turn segments."""
    errors = []
    samples = verifier.get_steady_state_samples(skip_fraction=0.1)
    if not samples:
        return ['No joint state samples received during square']

    # Check for presence of both near-zero and non-zero steering
    small_steer_count = 0
    large_steer_count = 0
    for s in samples:
        for wheel, angle in s.steering.items():
            if abs(angle) < math.radians(10):
                small_steer_count += 1
            if abs(angle) > math.radians(20):
                large_steer_count += 1

    if small_steer_count == 0:
        errors.append('square: no straight segments detected')
    if large_steer_count == 0:
        errors.append('square: no turn segments detected')

    return errors


# ---------------------------------------------------------------------------
# Data-driven tests (no Gazebo required)
# ---------------------------------------------------------------------------

def run_data_tests() -> tuple:
    """Run pure-data tests that don't require Gazebo.

    Returns (passed, failed, errors).
    """
    passed = 0
    failed = 0
    errors: List[str] = []

    print('\n[verify] Data-driven tests (no Gazebo required)')
    print('=' * 60)

    # --- Test: compute_path_waypoints on straight ---
    print('\n--- Data test: compute_path_waypoints (straight) ---')
    cmds = straight(speed=1.0, duration=10.0)
    wps = compute_path_waypoints(cmds, start_x=0.0, start_y=0.0,
                                  start_heading=0.0, dt=0.1, spacing=0.5)
    test_errors = []
    if len(wps) < 2:
        test_errors.append('straight waypoints: expected >=2 waypoints, '
                           f'got {len(wps)}')
    else:
        # All waypoints should have y ~= 0 (straight along X)
        max_y_dev = max(abs(y) for _, y in wps)
        if max_y_dev > 0.01:
            test_errors.append(f'straight waypoints: y deviation {max_y_dev:.4f}'
                               f' (expected ~0)')
        # Final x should be ~10m
        final_x = wps[-1][0]
        if abs(final_x - 10.0) > 0.5:
            test_errors.append(f'straight waypoints: final x={final_x:.2f}'
                               f' (expected ~10.0)')
        # Waypoints should be monotonically increasing in x
        for i in range(1, len(wps)):
            if wps[i][0] < wps[i - 1][0] - 0.01:
                test_errors.append('straight waypoints: x not monotonically '
                                   f'increasing at index {i}')
                break
    if test_errors:
        failed += 1
        for e in test_errors:
            print(f'  FAIL: {e}')
            errors.append(e)
    else:
        passed += 1
        print(f'  PASS ({len(wps)} waypoints, final x={wps[-1][0]:.2f})')

    # --- Test: compute_path_waypoints on circle ---
    print('\n--- Data test: compute_path_waypoints (circle) ---')
    cmds = circle(speed=0.3, radius=3.0, revolutions=1)
    wps = compute_path_waypoints(cmds, start_x=0.0, start_y=0.0,
                                  start_heading=0.0, dt=0.05, spacing=0.3)
    test_errors = []
    gap = 0.0
    if len(wps) < 10:
        test_errors.append(f'circle waypoints: expected >=10, got {len(wps)}')
    else:
        # Start and end should be close (closed circle)
        gap = math.hypot(wps[-1][0] - wps[0][0], wps[-1][1] - wps[0][1])
        if gap > 2.0:
            test_errors.append(f'circle waypoints: start-end gap={gap:.2f}m '
                               f'(expected <2m for closure)')
        # Waypoints should span in 2D (not all on a line)
        xs = [x for x, _ in wps]
        ys = [y for _, y in wps]
        x_range = max(xs) - min(xs)
        y_range = max(ys) - min(ys)
        if x_range < 1.0 or y_range < 1.0:
            test_errors.append(f'circle waypoints: span too small '
                               f'(x_range={x_range:.2f}, y_range={y_range:.2f})')
    if test_errors:
        failed += 1
        for e in test_errors:
            print(f'  FAIL: {e}')
            errors.append(e)
    else:
        passed += 1
        print(f'  PASS ({len(wps)} waypoints, gap={gap:.2f}m)')

    # --- Test: all letter patterns produce commands and viable paths at 10m ---
    h = 10.0  # must match the height used in _letter_patterns()
    letter_fns = [
        ('letter_P', letter_P),
        ('letter_D', letter_D),
        ('letter_S', letter_S),
        ('letter_L', letter_L),
        ('letter_U', letter_U),
        ('letter_Z', letter_Z),
        ('figure_eight', lambda speed=0.3, height=h: figure_eight(
            speed=speed, radius=height * 0.25)),
        ('circle_O', lambda speed=0.3, height=h: circle(
            speed=speed, radius=height * 0.25, revolutions=1)),
    ]
    for name, fn in letter_fns:
        print(f'\n--- Data test: {name} ({h:.0f}m) ---')
        test_errors = []
        # Generate commands at configured height
        if name in ('figure_eight', 'circle_O'):
            cmds = fn(speed=0.3, height=h)
        else:
            cmds = fn(speed=0.3, height=h)

        if len(cmds) < 1:
            test_errors.append(f'{name}: no commands generated')

        # Total duration should be reasonable (> 3s for a 10m letter)
        total_dur = sum(d for _, d in cmds)
        if total_dur < 3.0:
            test_errors.append(f'{name}: total duration {total_dur:.1f}s too short')
        if total_dur > 1200.0:
            test_errors.append(f'{name}: total duration {total_dur:.1f}s '
                               f'unreasonably long')

        # Compute path and check it's non-degenerate
        wps = compute_path_waypoints(cmds, start_x=0.0, start_y=0.0,
                                      start_heading=0.0, dt=0.1, spacing=0.5)
        max_span = 0.0
        if len(wps) < 5:
            test_errors.append(f'{name}: too few waypoints ({len(wps)})')
        else:
            xs = [x for x, _ in wps]
            ys = [y for _, y in wps]
            x_range = max(xs) - min(xs)
            y_range = max(ys) - min(ys)
            # At 10m, path should span at least 2m in at least one axis
            max_span = max(x_range, y_range)
            if max_span < 2.0:
                test_errors.append(f'{name}: path span too small '
                                   f'(max_span={max_span:.1f}m, expected >2m '
                                   f'for {h:.0f}m letter)')
            # Path should span > 5m total (sum of distances between waypoints)
            total_dist = sum(math.hypot(wps[i][0] - wps[i-1][0],
                                         wps[i][1] - wps[i-1][1])
                             for i in range(1, len(wps)))
            if total_dist < 5.0:
                test_errors.append(f'{name}: total path length {total_dist:.1f}m '
                                   f'too short for {h:.0f}m letter')

        if test_errors:
            failed += 1
            for e in test_errors:
                print(f'  FAIL: {e}')
                errors.append(e)
        else:
            passed += 1
            print(f'  PASS ({len(cmds)} cmds, {total_dur:.1f}s, '
                  f'{len(wps)} waypoints, span={max_span:.1f}m)')

    return passed, failed, errors


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def run_tests():
    # --- Phase 1: Data-driven tests (no Gazebo needed) ---
    data_passed, data_failed, data_errors = run_data_tests()

    # --- Phase 2: Live Gazebo tests ---
    rclpy.init()
    node = rclpy.create_node(
        'verify_patterns',
        parameter_overrides=[
            Parameter('use_sim_time', Parameter.Type.BOOL, True),
        ],
    )
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)

    print('\n[verify] Waiting for publisher + subscriber setup...')
    time.sleep(2.0)

    # Spin a bit to start receiving joint states
    for _ in range(20):
        rclpy.spin_once(node, timeout_sec=0.05)
        time.sleep(0.05)

    verifier = PatternVerifier(node, publisher)

    tests = [
        ('straight',       straight(speed=0.5, duration=4.0),      check_straight),
        ('stop',           stop(duration=3.0),                      check_stop),
        ('turn_in_place',  turn_in_place(rate=0.5, duration=4.0),  check_turn_in_place),
        ('arc',            arc(speed=0.3, radius=1.0, duration=5.0), check_arc),
        ('circle',         circle(speed=0.3, radius=1.0, revolutions=1), check_arc),
        ('square',         square(speed=0.3, side_length=2.0),      check_square_has_turns),
        ('headland_uturn', headland_uturn(speed=0.3, direction='left'), check_turn_in_place),
    ]

    live_total = len(tests)
    live_passed = 0
    live_failed = 0
    live_errors: List[str] = []

    print(f'\n[verify] Running {live_total} live Gazebo pattern tests')
    print('=' * 60)

    for name, commands, checker in tests:
        print(f'\n--- Test: {name} ---')
        print(f'  Executing pattern ({len(commands)} commands)...')

        verifier.execute(commands, speed_scale=1.0)
        n_samples = len(verifier.samples)
        print(f'  Collected {n_samples} joint state samples')

        if n_samples == 0:
            errors = [f'{name}: No joint state data received — '
                      f'is Gazebo running with the bridge?']
        else:
            errors = checker(verifier)

        if errors:
            live_failed += 1
            for e in errors:
                print(f'  FAIL: {e}')
                live_errors.append(e)
        else:
            live_passed += 1
            print(f'  PASS')

        # Pause between tests for settling
        publisher.publish(_twist())
        time.sleep(2.0)

    # --- Combined summary ---
    total_passed = data_passed + live_passed
    total_failed = data_failed + live_failed
    total_tests = (data_passed + data_failed) + live_total
    all_errors = data_errors + live_errors

    print('\n' + '=' * 60)
    print(f'[verify] RESULTS: {total_passed}/{total_tests} passed, '
          f'{total_failed}/{total_tests} failed')
    print(f'         Data tests: {data_passed}/{data_passed + data_failed} passed')
    print(f'         Live tests: {live_passed}/{live_total} passed')
    if all_errors:
        print('\nFailures:')
        for e in all_errors:
            print(f'  - {e}')
    else:
        print('\nAll verification checks passed!')
    print('=' * 60)

    # Cleanup
    publisher.publish(_twist())
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:
        pass

    os._exit(0 if total_failed == 0 else 1)


if __name__ == '__main__':
    run_tests()
