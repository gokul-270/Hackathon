#!/usr/bin/env python3
"""
DEPRECATED: This script is superseded by scripts/demo_patterns.py which
provides a comprehensive motion pattern library with composable functions.
Use: python3 scripts/demo_patterns.py --stress

Diagnostic script to test individual wheel steering and verify joint axis directions.

Usage:
    python3 scripts/test_steering_diagnostic.py [test_name]

Tests:
    left_only   - Send +0.3 rad to left steering only (observe direction)
    right_only  - Send +0.3 rad to right steering only (compare direction)
    both_same   - Send +0.3 rad to both left and right (should turn same way)
    left_turn   - Send cmd_vel for left turn (vx=0.5, wz=0.3) and print computed angles
    all_zero    - Zero all steering (reset position)

After each test, prints the actual joint states from /world/cotton_field/model/pragati/joint_state
"""
import rclpy
from rclpy.parameter import Parameter
from rclpy.node import Node
from std_msgs.msg import Float64
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
import time, os, sys, signal, math


class SteeringDiagnostic(Node):
    def __init__(self):
        super().__init__('steering_diagnostic', parameter_overrides=[
            Parameter('use_sim_time', Parameter.Type.BOOL, False)
        ])

        # Steering publishers (direct to joint controllers)
        self.left_steer_pub = self.create_publisher(Float64, '/steering/left', 10)
        self.right_steer_pub = self.create_publisher(Float64, '/steering/right', 10)
        self.front_steer_pub = self.create_publisher(Float64, '/steering/front', 10)

        # Drive publishers (zero them)
        self.left_drive_pub = self.create_publisher(Float64, '/wheel/left/velocity', 10)
        self.right_drive_pub = self.create_publisher(Float64, '/wheel/right/velocity', 10)
        self.front_drive_pub = self.create_publisher(Float64, '/wheel/front/velocity', 10)

        # cmd_vel publisher
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # Joint state subscriber
        self.joint_states = {}
        self.joint_state_sub = self.create_subscription(
            JointState,
            '/world/cotton_field/model/pragati/joint_state',
            self.joint_state_callback,
            10
        )

        # Also try the standard topic
        self.joint_state_sub2 = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            10
        )

    def joint_state_callback(self, msg):
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                self.joint_states[name] = {
                    'position': msg.position[i],
                    'velocity': msg.velocity[i] if i < len(msg.velocity) else 0.0
                }

    def stop_all(self):
        """Zero all drive velocities."""
        zero = Float64()
        zero.data = 0.0
        self.left_drive_pub.publish(zero)
        self.right_drive_pub.publish(zero)
        self.front_drive_pub.publish(zero)

    def set_steering(self, left=None, right=None, front=None):
        """Set steering angles. None = don't publish."""
        if left is not None:
            msg = Float64()
            msg.data = left
            self.left_steer_pub.publish(msg)
        if right is not None:
            msg = Float64()
            msg.data = right
            self.right_steer_pub.publish(msg)
        if front is not None:
            msg = Float64()
            msg.data = front
            self.front_steer_pub.publish(msg)

    def print_joint_states(self):
        """Print relevant steering joint states."""
        steering_joints = [
            'base-plate-front_Revolute-14',
            'base-plate-right_Revolute-18',
            'base-plate-left_Revolute-20',
        ]
        print('\n--- Joint States ---')
        if not self.joint_states:
            print('  (no joint states received yet - check topic name)')
            # Print all known joints for debugging
            return

        for name in steering_joints:
            if name in self.joint_states:
                pos = self.joint_states[name]['position']
                print(f'  {name}: {pos:.4f} rad ({math.degrees(pos):.1f}°)')
            else:
                print(f'  {name}: NOT FOUND')

        # Also print any joint with "Revolute" in name
        print('\n  All revolute joints:')
        for name, state in sorted(self.joint_states.items()):
            if 'Revolute' in name or 'revolute' in name.lower():
                print(f'    {name}: pos={state["position"]:.4f} rad ({math.degrees(state["position"]):.1f}°)')

    def wait_and_spin(self, seconds):
        """Spin for given seconds, processing callbacks."""
        start = time.time()
        while time.time() - start < seconds:
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)


def main():
    test_name = sys.argv[1] if len(sys.argv) > 1 else 'left_turn'
    angle = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3

    rclpy.init()
    node = SteeringDiagnostic()

    def cleanup(signum=None, frame=None):
        node.stop_all()
        node.set_steering(left=0.0, right=0.0, front=0.0)
        time.sleep(0.5)
        print('Cleaned up')
        os._exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Wait for publisher discovery
    print(f'Waiting for connections...')
    node.wait_and_spin(2.0)
    node.stop_all()

    print(f'\n=== Test: {test_name} (angle={angle:.3f} rad = {math.degrees(angle):.1f}°) ===\n')

    if test_name == 'left_only':
        print(f'Sending +{angle} rad to /steering/left ONLY')
        print('Watch: which direction does the LEFT rear wheel turn?')
        for _ in range(100):  # 10 seconds
            node.set_steering(left=angle)
            node.stop_all()
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

    elif test_name == 'right_only':
        print(f'Sending +{angle} rad to /steering/right ONLY')
        print('Watch: which direction does the RIGHT rear wheel turn?')
        for _ in range(100):
            node.set_steering(right=angle)
            node.stop_all()
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

    elif test_name == 'front_only':
        print(f'Sending +{angle} rad to /steering/front ONLY')
        for _ in range(100):
            node.set_steering(front=angle)
            node.stop_all()
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

    elif test_name == 'both_same':
        print(f'Sending +{angle} rad to BOTH /steering/left and /steering/right')
        print('Watch: do both rear wheels turn the SAME direction?')
        print('If left has inverted axis, they will turn OPPOSITE.')
        for _ in range(100):
            node.set_steering(left=angle, right=angle)
            node.stop_all()
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

    elif test_name == 'both_negated':
        print(f'Sending -{angle} rad to /steering/left, +{angle} rad to /steering/right')
        print('This is what the kinematics node does (negate left).')
        print('Watch: both wheels should turn the SAME physical direction.')
        for _ in range(100):
            node.set_steering(left=-angle, right=angle)
            node.stop_all()
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

    elif test_name == 'left_turn':
        # Compute what the kinematics would produce
        vx, wz = 0.5, 0.3
        # Wheel positions relative to center
        wheels = {
            'front': {'x': 0.75, 'y': 0.0},
            'left': {'x': -0.75, 'y': 0.90},
            'right': {'x': -0.75, 'y': -0.90},
        }
        print(f'Simulating left turn: vx={vx}, wz={wz}')
        print(f'Computed kinematic steering angles:')
        for name, pos in wheels.items():
            vix = vx - wz * pos['y']
            viy = wz * pos['x']
            angle_k = math.atan2(viy, vix)
            if abs(angle_k) > math.pi / 2:
                angle_k -= math.copysign(math.pi, angle_k)
            print(f'  {name}: kinematic={math.degrees(angle_k):.1f}°', end='')
            if name == 'left':
                print(f'  → negated to {math.degrees(-angle_k):.1f}° for joint command')
            else:
                print()

        print(f'\nNow sending cmd_vel: vx={vx}, wz={wz} for 5 seconds...')
        print('Watch: ALL three wheels should visibly turn during a left turn.')
        twist = Twist()
        twist.linear.x = vx
        twist.angular.z = wz
        for _ in range(100):
            node.cmd_vel_pub.publish(twist)
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

        # Now stop
        twist.linear.x = 0.0
        twist.angular.z = 0.0
        for _ in range(20):
            node.cmd_vel_pub.publish(twist)
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)

    elif test_name == 'all_zero':
        print('Zeroing all steering...')
        for _ in range(50):
            node.set_steering(left=0.0, right=0.0, front=0.0)
            node.stop_all()
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
        node.print_joint_states()

    else:
        print(f'Unknown test: {test_name}')
        print('Available: left_only, right_only, front_only, both_same, both_negated, left_turn, all_zero')

    print('\nDone. Press Ctrl+C to exit.')
    # Keep spinning to receive joint states
    node.wait_and_spin(3.0)
    node.print_joint_states()
    cleanup()


if __name__ == '__main__':
    main()
