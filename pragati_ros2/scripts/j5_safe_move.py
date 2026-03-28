#!/usr/bin/env python3
"""
J5 Safe Move — Collision-aware manual J5 command tool.

Applies the same J5 collision avoidance algorithm used by the trajectory planner:
    J5_limit = clearance / cos(J3)

Usage:
    # Move J5 to 0.18m with collision avoidance (default clearance 0.20m from production.yaml):
    python3 scripts/j5_safe_move.py 0.18 -ca

    # Move J5 to 0.18m with custom clearance 0.22m:
    python3 scripts/j5_safe_move.py 0.18 -ca 0.22

    # Move J5 to 0.25m without collision avoidance (raw pass-through):
    python3 scripts/j5_safe_move.py 0.25

    # Dry-run (compute limit but don't publish):
    python3 scripts/j5_safe_move.py 0.25 -ca 0.20 --dry-run
"""

import argparse
import math
import os
import sys
import time

import yaml
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64

COS_FLOOR = 0.1  # prevents division by zero, matches C++ implementation
J5_TOPIC = "/joint5_position_controller/command"
JOINT_STATES_TOPIC = "/joint_states"

# Default clearance from production.yaml
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
PRODUCTION_YAML = os.path.join(
    REPO_ROOT, "src", "yanthra_move", "config", "production.yaml"
)


def load_default_clearance():
    """Read clearance from production.yaml. Falls back to 0.20 if file missing."""
    try:
        with open(PRODUCTION_YAML, "r") as f:
            config = yaml.safe_load(f)
        # Navigate: yanthra_move -> ros__parameters -> j5_collision_avoidance/clearance
        params = config.get("yanthra_move", {}).get("ros__parameters", {})
        return float(params.get("j5_collision_avoidance/clearance", 0.20))
    except Exception:
        return 0.20


DEFAULT_CLEARANCE = load_default_clearance()


class J5SafeMoveNode(Node):
    def __init__(self):
        super().__init__("j5_safe_move")
        self.j3_position = None
        self.j5_position = None
        self.joint_state_received = False

        self.sub = self.create_subscription(
            JointState, JOINT_STATES_TOPIC, self._joint_states_cb, 10
        )
        qos = QoSProfile(depth=10)
        qos.durability = DurabilityPolicy.VOLATILE
        self.pub = self.create_publisher(Float64, J5_TOPIC, qos)

    def _joint_states_cb(self, msg: JointState):
        for i, name in enumerate(msg.name):
            if name == "joint3" and i < len(msg.position):
                self.j3_position = msg.position[i]
            if name == "joint5" and i < len(msg.position):
                self.j5_position = msg.position[i]
        self.joint_state_received = True

    def wait_for_joint_states(self, timeout_sec=5.0):
        """Wait until we receive at least one /joint_states message."""
        start = time.monotonic()
        while not self.joint_state_received:
            rclpy.spin_once(self, timeout_sec=0.1)
            if time.monotonic() - start > timeout_sec:
                return False
        return True

    def compute_collision_limit(self, clearance: float):
        """Compute J5 safe limit from current J3 position.

        J3 position from /joint_states is in RADIANS (motor_control converts
        rotations → radians via × 2π before publishing, for URDF compatibility).
        Returns (j5_limit, j3_rad, j3_deg, cos_j3).
        """
        if self.j3_position is None:
            return None, None, None, None
        j3_rad = self.j3_position  # already radians from /joint_states
        j3_deg = math.degrees(j3_rad)  # radians → degrees
        cos_j3 = max(math.cos(j3_rad), COS_FLOOR)
        j5_limit = clearance / cos_j3
        return j5_limit, j3_rad, j3_deg, cos_j3

    def publish_j5(self, value: float):
        msg = Float64()
        msg.data = value
        self.pub.publish(msg)


def main():
    parser = argparse.ArgumentParser(
        description="J5 Safe Move — collision-aware manual J5 command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "position",
        type=float,
        help="Desired J5 position in meters (e.g. 0.18)",
    )
    parser.add_argument(
        "-ca",
        "--collision-avoidance",
        nargs="?",
        const=DEFAULT_CLEARANCE,
        type=float,
        default=None,
        metavar="CLEARANCE",
        help=(
            f"Enable collision avoidance. Optionally specify clearance in meters "
            f"(default: {DEFAULT_CLEARANCE} from production.yaml)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Compute and display limit but do NOT publish the command",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds waiting for /joint_states (default: 5.0)",
    )

    args = parser.parse_args()

    # -ca was used: args.collision_avoidance is a float (clearance value)
    # -ca was NOT used: args.collision_avoidance is None
    ca_enabled = args.collision_avoidance is not None
    clearance = args.collision_avoidance  # float or None

    rclpy.init()
    node = J5SafeMoveNode()

    try:
        if not ca_enabled:
            # No collision check — raw publish (same as ros2 topic pub)
            if args.dry_run:
                print(f"[DRY-RUN] Would publish J5={args.position:.4f}m (no collision check)")
            else:
                node.publish_j5(args.position)
                print(f"✅ Published J5={args.position:.4f}m (collision avoidance OFF)")
            return

        # --- Collision avoidance enabled ---
        print(f"🔍 Reading J3 position from {JOINT_STATES_TOPIC}...")
        if not node.wait_for_joint_states(timeout_sec=args.timeout):
            print(
                f"❌ TIMEOUT: No /joint_states received within {args.timeout}s.\n"
                f"   Is the motor_control node running?",
                file=sys.stderr,
            )
            sys.exit(1)

        j5_limit, j3_rad, j3_deg, cos_j3 = node.compute_collision_limit(clearance)

        if j5_limit is None:
            print(
                "❌ ERROR: joint3 position not found in /joint_states.\n"
                "   Available joints may not include 'joint3'.",
                file=sys.stderr,
            )
            sys.exit(1)

        j3_deg_abs = abs(j3_deg)
        j3_rot = j3_rad / (2.0 * math.pi)  # for display (command units)

        # Display full computation — tabular format
        print(f"\n  ╔══════════════════════════════════════════════════════════════╗")
        if args.position <= j5_limit:
            print(f"  ║  ✅ COLLISION AVOIDANCE — J5 OK                             ║")
        else:
            print(f"  ║  ⛔ COLLISION AVOIDANCE — PICK BLOCKED                      ║")
        print(f"  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  Requested J5   : {args.position:.4f}m                                 ║")
        print(f"  ║  Safe J5 limit  : {j5_limit:.4f}m                                 ║")
        if args.position > j5_limit:
            overshoot = args.position - j5_limit
            pct = (overshoot / j5_limit) * 100.0
            print(f"  ║  Overshoot      : {overshoot:.4f}m ({pct:.1f}%)                          ║")
        else:
            headroom = j5_limit - args.position
            print(f"  ║  Headroom       : {headroom:.4f}m                                 ║")
        print(f"  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  J3 angle       : {j3_rot:.4f} rot ({j3_deg:.1f}°)                      ║")
        print(f"  ║  cos(J3)        : {cos_j3:.4f}                                   ║")
        print(f"  ║  Clearance      : {clearance:.4f}m                                 ║")
        if node.j5_position is not None:
            print(f"  ║  Current J5     : {node.j5_position:.4f}m                                 ║")
        print(f"  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  Formula: J5_limit = {clearance:.4f} / {cos_j3:.4f} = {j5_limit:.4f}m             ║")
        if args.position <= j5_limit:
            print(f"  ║  Result : {args.position:.4f}m <= {j5_limit:.4f}m → SAFE                  ║")
        else:
            print(f"  ║  Result : {args.position:.4f}m >  {j5_limit:.4f}m → BLOCKED               ║")
        print(f"  ╚══════════════════════════════════════════════════════════════╝")

        if args.position <= j5_limit:
            # SAFE — within limit
            if args.dry_run:
                print(f"\n  Would publish J5={args.position:.4f}m [DRY-RUN]")
            else:
                node.publish_j5(args.position)
                print(f"\n  Published J5={args.position:.4f}m to {J5_TOPIC}")
        else:
            # BLOCKED — skip entirely
            print(f"\n  J5 command REJECTED — pick skipped to avoid collision.")
            sys.exit(2)

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
