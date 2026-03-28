#!/usr/bin/env python3
"""
Calculate new robot origin for proper velocity kinematics.
Move origin from rear axle center to geometric center of robot.
"""

import numpy as np

print("=" * 70)
print("CURRENT POSITIONS (origin at rear axle center)")
print("=" * 70)

# Current positions from URDF analysis (relative to base-v1 at rear axle)
front_abs = np.array([1.405, 0.910])
left_abs = np.array([-0.105, 1.810])
right_abs = np.array([-0.105, -0.010])

print(f"Front:  ({front_abs[0]:+.3f}, {front_abs[1]:+.3f})")
print(f"Left:   ({left_abs[0]:+.3f}, {left_abs[1]:+.3f})")
print(f"Right:  ({right_abs[0]:+.3f}, {right_abs[1]:+.3f})")

# Calculate geometric center (centroid of triangle)
centroid = (front_abs + left_abs + right_abs) / 3
print(f"\nGeometric center (centroid): ({centroid[0]:+.3f}, {centroid[1]:+.3f})")

# Alternative: midpoint between front and rear axle
rear_axle_x = (left_abs[0] + right_abs[0]) / 2
front_rear_mid_x = (front_abs[0] + rear_axle_x) / 2
front_rear_mid_y = 0.9  # Keep at rear axle y for simplicity

midpoint = np.array([front_rear_mid_x, front_rear_mid_y])
print(f"Front-Rear midpoint:         ({midpoint[0]:+.3f}, {midpoint[1]:+.3f})")

# Choose midpoint for cleaner numbers
new_origin = midpoint
print(f"\n{'='*70}")
print(f"NEW ORIGIN: ({new_origin[0]:+.3f}, {new_origin[1]:+.3f})")
print(f"{'='*70}")

# Calculate wheel positions relative to new origin
front_new = front_abs - new_origin
left_new = left_abs - new_origin
right_new = right_abs - new_origin

print(f"\nNEW WHEEL POSITIONS (relative to center):")
print(f"Front:  ({front_new[0]:+.3f}, {front_new[1]:+.3f})")
print(f"Left:   ({left_new[0]:+.3f}, {left_new[1]:+.3f})")
print(f"Right:  ({right_new[0]:+.3f}, {right_new[1]:+.3f})")

print(f"\n{'='*70}")
print("VERIFICATION - ALL WHEELS HAVE NON-ZERO X!")
print(f"{'='*70}")
print(f"Front x: {front_new[0]:+.3f} ✓")
print(f"Left x:  {left_new[0]:+.3f} ✓")
print(f"Right x: {right_new[0]:+.3f} ✓")

# Test kinematics with example command
print(f"\n{'='*70}")
print("TEST KINEMATICS: vx=0.4 m/s, omega=0.2 rad/s")
print(f"{'='*70}")

vx = 0.4
omega = 0.2

for name, pos in [("Front", front_new), ("Left", left_new), ("Right", right_new)]:
    vix = vx - omega * pos[1]
    viy = omega * pos[0]
    angle_rad = np.arctan2(viy, vix)
    angle_deg = np.degrees(angle_rad)
    speed = np.sqrt(vix**2 + viy**2)
    
    print(f"{name:>5}: vix={vix:+.3f}, viy={viy:+.3f} → steer={angle_deg:+6.2f}° ({angle_rad:+.3f} rad), speed={speed:.3f} m/s")

print(f"\n{'='*70}")
print("URDF TRANSFORM ADJUSTMENT")
print(f"{'='*70}")
print(f"Current base-v1 is at rear axle: (0, 0)")
print(f"Need to shift all joints by: ({-new_origin[0]:+.3f}, {-new_origin[1]:+.3f})")
print(f"\nIn URDF, add this offset to all base-plate-* joint xyz values")

print(f"\n{'='*70}")
print("KINEMATICS NODE CONFIGURATION")
print(f"{'='*70}")
print(f"self.declare_parameter('front_wheel_position', [{front_new[0]:.3f}, {front_new[1]:.3f}])")
print(f"self.declare_parameter('left_wheel_position', [{left_new[0]:.3f}, {left_new[1]:.3f}])")
print(f"self.declare_parameter('right_wheel_position', [{right_new[0]:.3f}, {right_new[1]:.3f}])")
print(f"{'='*70}")
