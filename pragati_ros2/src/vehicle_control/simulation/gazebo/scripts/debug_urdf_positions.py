#!/usr/bin/env python3
"""
Carefully trace URDF joint positions considering rotations.
The base-v1 position needs to be determined correctly.
"""

import numpy as np
from scipy.spatial.transform import Rotation

print("=" * 70)
print("TRACING URDF JOINT CHAIN")
print("=" * 70)

# From URDF joints (considering rotations):
# base-v1 is the root link

# Joint: base-v1 → base-plate-front
# xyz="1.3 0 0.9" rpy="-1.571 0 0" (approx -90° around X)
print("\n1. base-v1 → base-plate-front:")
print("   xyz: (1.3, 0, 0.9)")
print("   rpy: (-π/2, 0, 0) → rotates -90° around X")
print("   After rotation: z becomes -y, y becomes z")
print("   So in XY plane: front plate is at ~(1.3, -0.9) from base-v1")

# Joint: base-v1 → base-plate-right  
# xyz="0 0 0" (approximately)
print("\n2. base-v1 → base-plate-right:")
print("   xyz: (0, 0, 0)")
print("   Right plate is AT base-v1 origin!")

# Joint: base-v1 → base-plate-left
# xyz="0 0 1.8" rpy="π/2 0 0" (approx +90° around X)
print("\n3. base-v1 → base-plate-left:")
print("   xyz: (0, 0, 1.8)")
print("   rpy: (+π/2, 0, 0) → rotates +90° around X")
print("   After rotation: z becomes +y")
print("   So in XY plane: left plate is at ~(0, +1.8) from base-v1")

print("\n" + "=" * 70)
print("CONCLUSION")
print("=" * 70)
print("base-v1 is positioned AT THE RIGHT WHEEL!")
print("\nWheel positions in XY plane (base-v1 as origin):")
print("  Right: (0, 0)      ← base-v1 is HERE")
print("  Left:  (0, +1.8)")
print("  Front: (1.3, -0.9) ← This seems wrong, should be positive Y")

print("\nWAIT - let me reconsider the rotation directions...")
print("\nWith ROS/URDF conventions:")
print("  rpy=(-π/2, 0, 0) rotates -90° around X")
print("  For vector (x, y, z): after -90° X rotation → (x, z, -y)")
print("  So (1.3, 0, 0.9) → (1.3, 0.9, 0) in rotated frame")

print("\nCORRECTED positions:")
print("  Front: ~(1.3, +0.9) from base-v1")
print("  Left:  ~(0, +1.8) from base-v1") 
print("  Right: ~(0, 0) AT base-v1")

print("\n" + "=" * 70)
print("STEERING JOINT OFFSETS (from base-plate to steering)")
print("=" * 70)

# From URDF:
# base-plate-front → axial-front: xyz="0.105 0.01 -0.097"
# base-plate-left → axial-left: xyz="-0.105 0.01 0.097"
# base-plate-right → axial-right: xyz="-0.105 -0.01 -0.097"

print("Front: plate→steering offset in local coords: (0.105, 0.01, -0.097)")
print("Left:  plate→steering offset in local coords: (-0.105, 0.01, 0.097)")
print("Right: plate→steering offset in local coords: (-0.105, -0.01, -0.097)")

print("\nAssuming these are in the rotated local frames...")
print("Need to apply same rotations to get global positions")

print("\n" + "=" * 70)
print("FINAL STEERING JOINT POSITIONS (from base-v1)")
print("=" * 70)

# More careful calculation accounting for all rotations
# The plates have complex rotations that affect the steering joint offsets

# For simplicity, from user's observation:
# base-v1 is at right wheel position (0, 0)
# User sees front at roughly (+1.3, +0.9)
# User sees left at roughly (0, +1.8)

print("\nFrom URDF structure:")
print("  Right steering: (0, 0) - AT BASE-V1")
print("  Left steering:  (0, ~1.8)")
print("  Front steering: (~1.3, ~0.9)")

print("\nRear axle center (midpoint of left & right):")
rear_y = (1.8 + 0) / 2
print(f"  Y-position: (0 + 1.8) / 2 = {rear_y}")
print(f"  Rear axle at: (0, {rear_y})")

print("\n" + "=" * 70)
print("POSITIONS RELATIVE TO REAR AXLE")
print("=" * 70)

front_rel = np.array([1.3, 0.9 - rear_y])
left_rel = np.array([0.0, 1.8 - rear_y])
right_rel = np.array([0.0, 0.0 - rear_y])

print(f"Front: ({front_rel[0]:+.3f}, {front_rel[1]:+.3f})")
print(f"Left:  ({left_rel[0]:+.3f}, {left_rel[1]:+.3f})")
print(f"Right: ({right_rel[0]:+.3f}, {right_rel[1]:+.3f})")

print("\n" + "=" * 70)
print("FOR KINEMATICS NODE (relative to robot center)")
print("=" * 70)

center_offset = np.array([1.3/2, 0.9])
print(f"Robot center offset: ({center_offset[0]:.3f}, {center_offset[1]:.3f})")

front_kin = front_rel - center_offset
left_kin = left_rel - center_offset
right_kin = right_rel - center_offset

print(f"\nFront: ({front_kin[0]:+.3f}, {front_kin[1]:+.3f})")
print(f"Left:  ({left_kin[0]:+.3f}, {left_kin[1]:+.3f})")
print(f"Right: ({right_kin[0]:+.3f}, {right_kin[1]:+.3f})")

print("\n" + "=" * 70)
print("TEST: Pure rotation omega=0.2 rad/s")
print("=" * 70)

omega = 0.2
for name, pos in [("Front", front_kin), ("Left", left_kin), ("Right", right_kin)]:
    vix = 0 - omega * pos[1]
    viy = omega * pos[0]
    angle_rad = np.arctan2(viy, vix)
    angle_deg = np.degrees(angle_rad)
    print(f"{name:>5}: x={pos[0]:+.3f}, y={pos[1]:+.3f} → vix={vix:+.3f}, viy={viy:+.3f} → {angle_deg:+6.1f}°")
