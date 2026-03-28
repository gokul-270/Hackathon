#!/usr/bin/env python3
"""
DEPRECATED: This script is superseded by scripts/demo_patterns.py which
provides a comprehensive motion pattern library with composable functions.
Use: python3 scripts/demo_patterns.py --stress

Quick direct steering test - bypasses kinematics node.
"""
import rclpy
from rclpy.parameter import Parameter
from std_msgs.msg import Float64
from sensor_msgs.msg import JointState
import time, os, sys, math

joint_data = {}

def js_cb(msg):
    global joint_data
    for i, name in enumerate(msg.name):
        if 'Revolute' in name and i < len(msg.position):
            joint_data[name] = msg.position[i]

def main():
    test = sys.argv[1] if len(sys.argv) > 1 else 'both_same'
    angle = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    
    rclpy.init()
    node = rclpy.create_node('steer_test', parameter_overrides=[
        Parameter('use_sim_time', Parameter.Type.BOOL, False)
    ])
    
    left_pub = node.create_publisher(Float64, '/steering/left', 10)
    right_pub = node.create_publisher(Float64, '/steering/right', 10)
    front_pub = node.create_publisher(Float64, '/steering/front', 10)
    
    # Subscribe to joint states from bridge
    node.create_subscription(JointState, '/joint_states', js_cb, 10)
    
    # Wait for connections
    time.sleep(1.5)
    for _ in range(10):
        rclpy.spin_once(node, timeout_sec=0.1)
    
    print(f'\nTest: {test}, angle={angle:.3f} rad ({math.degrees(angle):.1f}°)')
    
    left_msg = Float64()
    right_msg = Float64()
    front_msg = Float64()
    
    if test == 'both_same':
        left_msg.data = angle
        right_msg.data = angle
        front_msg.data = 0.0
        print(f'Sending LEFT={angle}, RIGHT={angle}')
        print('If joint axes match: wheels turn same physical direction')
        print('If left axis is inverted: wheels turn OPPOSITE directions')
    elif test == 'both_negated':
        left_msg.data = -angle
        right_msg.data = angle
        front_msg.data = 0.0
        print(f'Sending LEFT={-angle}, RIGHT={angle} (kinematics negation)')
        print('If left axis IS inverted: wheels turn SAME physical direction')
    elif test == 'left_only':
        left_msg.data = angle
        right_msg.data = 0.0
        front_msg.data = 0.0
        print(f'Sending LEFT={angle} only')
    elif test == 'right_only':
        left_msg.data = 0.0
        right_msg.data = angle
        front_msg.data = 0.0
        print(f'Sending RIGHT={angle} only')
    elif test == 'zero':
        left_msg.data = 0.0
        right_msg.data = 0.0
        front_msg.data = 0.0
        print('Zeroing all')
    
    # Publish for 5 seconds  
    for i in range(50):
        left_pub.publish(left_msg)
        right_pub.publish(right_msg)
        front_pub.publish(front_msg)
        rclpy.spin_once(node, timeout_sec=0.05)
        time.sleep(0.05)
    
    # Print joint states
    print('\n--- Joint positions ---')
    for name in sorted(joint_data.keys()):
        pos = joint_data[name]
        print(f'  {name}: {pos:.4f} rad ({math.degrees(pos):.1f}°)')
    
    if not joint_data:
        print('  (no joint states received)')
    
    os._exit(0)

if __name__ == '__main__':
    main()
