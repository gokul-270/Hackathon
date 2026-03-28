#!/usr/bin/env python3
"""Calculate correct offset with swapped Y coordinates."""

import numpy as np

print("=" * 70)
print("RECALCULATING WITH Y-SWAPPED")
print("=" * 70)

# Swapped Y-coordinates:
front_urdf = [1.405, 0.910]
left_urdf = [-0.105, -1.810]  # Swapped
right_urdf = [-0.105, +0.010]  # Swapped

print("\nURDF positions (Y-swapped):")
print(f"  Front: ({front_urdf[0]:+.3f}, {front_urdf[1]:+.3f})")
print(f"  Left:  ({left_urdf[0]:+.3f}, {left_urdf[1]:+.3f})")
print(f"  Right: ({right_urdf[0]:+.3f}, {right_urdf[1]:+.3f})")

# Calculate rear axle center (midpoint of left and right):
rear_axle_y = (left_urdf[1] + right_urdf[1]) / 2
rear_axle_x = (left_urdf[0] + right_urdf[0]) / 2
print(f"\nRear axle center: ({rear_axle_x:+.3f}, {rear_axle_y:+.3f})")

# Robot center (midpoint between front and rear axle):
center_x = (front_urdf[0] + rear_axle_x) / 2
center_y = (front_urdf[1] + rear_axle_y) / 2
print(f"Robot center: ({center_x:+.3f}, {center_y:+.3f})")

offset = [center_x, center_y]

# Calculate kinematic positions:
front_kin = [front_urdf[0] - offset[0], front_urdf[1] - offset[1]]
left_kin = [left_urdf[0] - offset[0], left_urdf[1] - offset[1]]
right_kin = [right_urdf[0] - offset[0], right_urdf[1] - offset[1]]

print(f"\nKinematic positions (relative to center):")
print(f"  Front: ({front_kin[0]:+.3f}, {front_kin[1]:+.3f})")
print(f"  Left:  ({left_kin[0]:+.3f}, {left_kin[1]:+.3f})")
print(f"  Right: ({right_kin[0]:+.3f}, {right_kin[1]:+.3f})")

print(f"\nSymmetry check:")
print(f"  Left Y + Right Y = {left_kin[1]:+.3f} + {right_kin[1]:+.3f} = {left_kin[1]+right_kin[1]:+.3f}")

print("\n" + "=" * 70)
print("TEST with vx=0.2, omega=-0.2")
print("=" * 70)

vx = 0.2
omega = -0.2

print(f"\n              vix      viy    angle")
for name, pos in [("Front", front_kin), ("Left", left_kin), ("Right", right_kin)]:
    vix = vx - omega * pos[1]
    viy = omega * pos[0]
    angle_deg = np.degrees(np.arctan2(viy, vix))
    print(f"  {name:>5}:  {vix:+.4f}  {viy:+.4f}  {angle_deg:+7.2f}°")

print(f"\nExpected (observed):")
print(f"  Front: -36.78°")
print(f"  Left:  +21.57°")
print(f"  Right: +83.20°")

print(f"\n{'='*70}")
print(f"PARAMETERS TO USE")
print(f"{'='*70}")
print(f"self.declare_parameter('front_wheel_urdf', [{front_urdf[0]:.3f}, {front_urdf[1]:.3f}])")
print(f"self.declare_parameter('left_wheel_urdf', [{left_urdf[0]:.3f}, {left_urdf[1]:.3f}])")
print(f"self.declare_parameter('right_wheel_urdf', [{right_urdf[0]:.3f}, {right_urdf[1]:.3f}])")
print(f"self.declare_parameter('kinematic_center_offset', [{offset[0]:.3f}, {offset[1]:.3f}])")
