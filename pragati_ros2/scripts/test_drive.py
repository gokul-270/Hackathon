#!/usr/bin/env python3
"""Quick test script to drive the robot with guaranteed stop."""
import rclpy
from rclpy.parameter import Parameter
from geometry_msgs.msg import Twist
import time, os, sys, signal

def main():
    # Parse args: linear_x, angular_z, duration
    vx = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    wz = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    rclpy.init()
    node = rclpy.create_node('test_drive', parameter_overrides=[
        Parameter('use_sim_time', Parameter.Type.BOOL, False)
    ])
    pub = node.create_publisher(Twist, '/cmd_vel', 10)

    # Ensure we always stop on exit
    def stop_and_exit(signum=None, frame=None):
        msg = Twist()
        for _ in range(20):
            pub.publish(msg)
            time.sleep(0.05)
        print('STOPPED')
        os._exit(0)

    signal.signal(signal.SIGTERM, stop_and_exit)
    signal.signal(signal.SIGINT, stop_and_exit)

    # Wait for publisher discovery
    time.sleep(1)

    msg = Twist()
    msg.linear.x = vx
    msg.angular.z = wz

    print(f'Driving: vx={vx}, wz={wz} for {duration}s')
    start = time.time()
    while time.time() - start < duration:
        pub.publish(msg)
        rclpy.spin_once(node, timeout_sec=0.02)
        time.sleep(0.08)

    # Guaranteed stop
    stop_and_exit()

if __name__ == '__main__':
    main()
