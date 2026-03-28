#!/usr/bin/env python3
"""
Reverse-engineer actual wheel positions from observed steering angles.
"""

import numpy as np

print("=" * 70)
print("REVERSE ENGINEERING FROM OBSERVED BEHAVIOR")
print("=" * 70)

# User observed with vx=0, omega=0.2:
# Front: +90°
# Left: -90°
# Right: -39.53°

omega = 0.2

print(f"\nCommand: vx=0, omega={omega}")
print("\nObserved steering angles:")
print("  Front: +90.00°")
print("  Left:  -90.00°")
print("  Right: -39.53°")

print("\n" + "=" * 70)
print("WHAT POSITIONS WOULD PRODUCE THESE ANGLES?")
print("=" * 70)

# For vx=0, omega=0.2:
# vix = 0 - 0.2 * y = -0.2 * y
# viy = 0.2 * x
# angle = atan2(viy, vix) = atan2(0.2*x, -0.2*y)

print("\nFor angle = +90° (+π/2):")
print("  atan2(viy, vix) = +90° means viy > 0, vix ≈ 0")
print("  viy = 0.2 * x > 0  → x > 0")
print("  vix = -0.2 * y ≈ 0 → y ≈ 0")
print("  → Front wheel: x > 0, y ≈ 0")

print("\nFor angle = -90° (-π/2):")
print("  atan2(viy, vix) = -90° means viy < 0, vix ≈ 0")
print("  viy = 0.2 * x < 0  → x < 0")
print("  vix = -0.2 * y ≈ 0 → y ≈ 0")
print("  → Left wheel: x < 0, y ≈ 0")

print("\nFor angle = -39.53° (-0.690 rad):")
print("  atan2(viy, vix) = -39.53°")
print("  tan(-39.53°) = viy / vix = -0.825")
print("  viy = 0.2 * x")
print("  vix = -0.2 * y")
print("  0.2 * x / (-0.2 * y) = -0.825")
print("  x / (-y) = -0.825")
print("  x = 0.825 * y")
print("  If this is in 4th quadrant (vix > 0, viy < 0):")
print("    vix > 0 → -0.2*y > 0 → y < 0")
print("    viy < 0 → 0.2*x < 0 → x < 0")
print("  → Right wheel: x < 0, y < 0, with |x/y| ≈ 0.825")

print("\n" + "=" * 70)
print("CURRENT KINEMATICS NODE CONFIGURATION")
print("=" * 70)

# From the kinematics node parameters:
front_urdf = [1.510, 0.010]
left_urdf = [0.000, 0.910]
right_urdf = [0.000, -0.910]
offset = [0.755, 0.005]

front_kin = [front_urdf[0] - offset[0], front_urdf[1] - offset[1]]
left_kin = [left_urdf[0] - offset[0], left_urdf[1] - offset[1]]
right_kin = [right_urdf[0] - offset[0], right_urdf[1] - offset[1]]

print(f"Front: x={front_kin[0]:+.3f}, y={front_kin[1]:+.3f}")
print(f"Left:  x={left_kin[0]:+.3f}, y={left_kin[1]:+.3f}")
print(f"Right: x={right_kin[0]:+.3f}, y={right_kin[1]:+.3f}")

print("\nCalculated angles with omega=0.2:")
for name, pos in [("Front", front_kin), ("Left", left_kin), ("Right", right_kin)]:
    vix = -omega * pos[1]
    viy = omega * pos[0]
    angle_rad = np.arctan2(viy, vix)
    angle_deg = np.degrees(angle_rad)
    print(f"  {name:>5}: vix={vix:+.4f}, viy={viy:+.4f} → {angle_deg:+7.2f}°")

print("\n" + "=" * 70)
print("COMPARING TO OBSERVED")
print("=" * 70)
print("                Calculated   Observed   Match?")
print(f"  Front:        {np.degrees(np.arctan2(omega*front_kin[0], -omega*front_kin[1])):+7.2f}°     +90.00°    {'✓' if abs(np.degrees(np.arctan2(omega*front_kin[0], -omega*front_kin[1])) - 90) < 1 else '✗'}")
print(f"  Left:         {np.degrees(np.arctan2(omega*left_kin[0], -omega*left_kin[1])):+7.2f}°     -90.00°    {'✓' if abs(np.degrees(np.arctan2(omega*left_kin[0], -omega*left_kin[1])) + 90) < 1 else '✗'}")
print(f"  Right:        {np.degrees(np.arctan2(omega*right_kin[0], -omega*right_kin[1])):+7.2f}°     -39.53°    {'✓' if abs(np.degrees(np.arctan2(omega*right_kin[0], -omega*right_kin[1])) + 39.53) < 1 else '✗'}")

print("\n" + "=" * 70)
print("DIAGNOSIS")
print("=" * 70)

# The observed -39.53° for right wheel suggests:
# atan2(0.2*x, -0.2*y) = -39.53° = -0.690 rad
# tan(-0.690) = -0.825
# (0.2*x) / (-0.2*y) = -0.825
# x/y = 0.825

# Current right: x=-0.755, y=0.905
print(f"\nCurrent right wheel kinematic position:")
print(f"  x = {right_kin[0]:.3f}")
print(f"  y = {right_kin[1]:.3f}")
print(f"  x/y ratio = {right_kin[0]/right_kin[1]:.3f}")

print(f"\nFor observed -39.53°, need:")
print(f"  tan(-39.53°) = -0.825")
print(f"  viy/vix = -0.825")
print(f"  (0.2*x)/(-0.2*y) = -0.825")
print(f"  x/(-y) = -0.825")

# If y = 0.905 (current):
y_test = right_kin[1]
x_needed = -0.825 * (-y_test)
print(f"\n  If y = {y_test:.3f}, then x should be: {x_needed:.3f}")
print(f"  But current x = {right_kin[0]:.3f}")
print(f"  Difference: {abs(x_needed - right_kin[0]):.3f}")

print("\n" + "=" * 70)
print("POSSIBLE ISSUE: Y-COORDINATES MAY BE SWAPPED")
print("=" * 70)

# Test if left and right y-coords are swapped:
print("\nWhat if we swap left and right Y positions?")
left_test = [left_kin[0], right_kin[1]]  # Use right's y for left
right_test = [right_kin[0], left_kin[1]]  # Use left's y for right

print(f"Front: x={front_kin[0]:+.3f}, y={front_kin[1]:+.3f}")
print(f"Left:  x={left_test[0]:+.3f}, y={left_test[1]:+.3f}  (swapped)")
print(f"Right: x={right_test[0]:+.3f}, y={right_test[1]:+.3f}  (swapped)")

print("\nCalculated angles with swapped Y:")
for name, pos in [("Front", front_kin), ("Left", left_test), ("Right", right_test)]:
    vix = -omega * pos[1]
    viy = omega * pos[0]
    angle_rad = np.arctan2(viy, vix)
    angle_deg = np.degrees(angle_rad)
    match = ""
    if name == "Front" and abs(angle_deg - 90) < 1:
        match = " ✓"
    elif name == "Left" and abs(angle_deg + 90) < 1:
        match = " ✓"
    elif name == "Right" and abs(angle_deg + 39.53) < 1:
        match = " ✓"
    print(f"  {name:>5}: {angle_deg:+7.2f}° {match}")
