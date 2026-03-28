#!/usr/bin/env python3
"""
Simulation Arm Trigger & Direct Joint Commander

Provides two modes:
  1. TRIGGER mode: Send start_switch topic to trigger yanthra_move operational cycle
  2. DIRECT mode: Command individual joints directly (like MG6010 gazebo_control.py)

Usage:
  # Trigger one operational cycle:
  python3 scripts/sim_arm_trigger.py trigger

  # Move individual joints:
  python3 scripts/sim_arm_trigger.py move joint2 0.2
  python3 scripts/sim_arm_trigger.py move joint3 -0.5
  python3 scripts/sim_arm_trigger.py move joint4 0.05
  python3 scripts/sim_arm_trigger.py move joint5 0.3

  # Run a picking demo sequence:
  python3 scripts/sim_arm_trigger.py pick

  # Home all joints:
  python3 scripts/sim_arm_trigger.py home

  # Move all 3 joints at once:
  python3 scripts/sim_arm_trigger.py moveall -0.3 0.05 0.2
  # (joint3=phi  joint4=theta  joint5=extension)
"""

import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float64


class SimArmTrigger(Node):
    def __init__(self):
        super().__init__('sim_arm_trigger')

        # Start switch publisher (triggers yanthra_move operational cycle)
        self.start_switch_pub = self.create_publisher(
            Bool, '/start_switch/command', 10
        )

        # Direct joint command publishers (native Gazebo JointPositionController topics)
        self.joint_pubs = {
            'joint2': self.create_publisher(Float64, '/joint2_cmd', 10),
            'joint3': self.create_publisher(Float64, '/joint3_cmd', 10),
            'joint4': self.create_publisher(Float64, '/joint4_cmd', 10),
            'joint5': self.create_publisher(Float64, '/joint5_cmd', 10),
        }

    # ── trigger ──────────────────────────────────────────────
    def send_trigger(self):
        msg = Bool()
        msg.data = True
        # Publish a few times to be safe
        for _ in range(3):
            self.start_switch_pub.publish(msg)
            time.sleep(0.05)
        self.get_logger().info('✅ START_SWITCH trigger sent!')

    # ── single joint ─────────────────────────────────────────
    def move_joint(self, joint_name: str, position: float):
        if joint_name not in self.joint_pubs:
            self.get_logger().error(f'Unknown joint: {joint_name}  (valid: joint2, joint3, joint4, joint5)')
            return
        msg = Float64()
        msg.data = position
        self.joint_pubs[joint_name].publish(msg)
        self.get_logger().info(f'📤 {joint_name} → {position:.4f}')

    # ── all three joints ─────────────────────────────────────
    def move_all(self, j3: float, j4: float, j5: float):
        self.get_logger().info(f'📤 Moving all joints: j3={j3:.4f}  j4={j4:.4f}  j5={j5:.4f}')
        self.move_joint('joint5', j5)
        time.sleep(0.2)
        self.move_joint('joint3', j3)
        time.sleep(0.5)
        self.move_joint('joint4', j4)

    # ── home ─────────────────────────────────────────────────
    def home(self):
        self.get_logger().info('🏠 Moving to home position...')
        self.move_joint('joint5', 0.0)
        time.sleep(0.3)
        self.move_joint('joint3', 0.0)
        time.sleep(0.3)
        self.move_joint('joint4', 0.0)
        self.get_logger().info('✅ Home position')

    # ── demo picking sequence ────────────────────────────────
    def picking_demo(self):
        self.get_logger().info('🌱 Starting picking demo sequence...\n')

        self.get_logger().info('Step 1: Tilt arm down (joint3 = -0.5 rad)')
        self.move_joint('joint3', -0.5)
        time.sleep(2)

        self.get_logger().info('Step 2: Shift left/right (joint4 = -0.05 m)')
        self.move_joint('joint4', -0.05)
        time.sleep(2)

        self.get_logger().info('Step 3: Extend arm (joint5 = 0.3 m)')
        self.move_joint('joint5', 0.3)
        time.sleep(2)

        self.get_logger().info('Step 4: Retract arm (joint5 = 0.1 m)')
        self.move_joint('joint5', 0.1)
        time.sleep(2)

        self.get_logger().info('Step 5: Return home')
        self.home()
        self.get_logger().info('\n✅ Picking demo complete!\n')


def print_usage():
    print("""
╔══════════════════════════════════════════════════════════╗
║         Pragati Arm Simulation Controller                ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  COMMANDS:                                               ║
║    trigger           Send START_SWITCH to yanthra_move   ║
║    move <jN> <val>   Move one joint                      ║
║    moveall <j3> <j4> <j5>  Move all 3 joints             ║
║    pick              Run demo picking sequence            ║
║    home              Home all joints                      ║
║                                                          ║
║  EXAMPLES:                                               ║
║    python3 sim_arm_trigger.py trigger                    ║
║    python3 sim_arm_trigger.py move joint2 0.2            ║
║    python3 sim_arm_trigger.py move joint3 -0.5           ║
║    python3 sim_arm_trigger.py move joint4 0.05           ║
║    python3 sim_arm_trigger.py move joint5 0.3            ║
║    python3 sim_arm_trigger.py moveall -0.3 0.05 0.2      ║
║    python3 sim_arm_trigger.py home                       ║
║                                                          ║
║  JOINT LIMITS:                                           ║
║    joint2 (height): [0.100, 0.320] m                     ║
║    joint3 (phi):    [-1.570, 0.000] rad                  ║
║    joint4 (theta):  [-0.250, 0.350] m                    ║
║    joint5 (r):      [ 0.000, 0.450] m                    ║
╚══════════════════════════════════════════════════════════╝
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    rclpy.init()
    node = SimArmTrigger()

    # Allow publishers to discover subscribers
    time.sleep(0.5)

    cmd = sys.argv[1].lower()

    try:
        if cmd == 'trigger':
            node.send_trigger()

        elif cmd == 'move' and len(sys.argv) == 4:
            node.move_joint(sys.argv[2], float(sys.argv[3]))

        elif cmd == 'moveall' and len(sys.argv) == 5:
            node.move_all(float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]))

        elif cmd == 'pick':
            node.picking_demo()

        elif cmd == 'home':
            node.home()

        else:
            print_usage()
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        time.sleep(0.3)  # Let messages get sent
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
