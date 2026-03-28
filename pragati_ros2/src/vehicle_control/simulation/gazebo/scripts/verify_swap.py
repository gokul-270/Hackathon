#!/usr/bin/env python3
"""Verify the swapped Y-coordinates give correct steering angles."""

import numpy as np

print("=" * 70)
print("VERIFICATION WITH SWAPPED LEFT/RIGHT Y-COORDINATES")
print("=" * 70)

# New configuration:
front_urdf = [1.510, 0.010]
left_urdf = [0.000, -0.910]  # SWAPPED
right_urdf = [0.000, +0.910]  # SWAPPED
offset = [0.755, 0.005]

# Calculate kinematic positions:
front_kin = [front_urdf[0] - offset[0], front_urdf[1] - offset[1]]
left_kin = [left_urdf[0] - offset[0], left_urdf[1] - offset[1]]
right_kin = [right_urdf[0] - offset[0], right_urdf[1] - offset[1]]

print(f"\nKinematic positions (relative to robot center):")
print(f"  Front: x={front_kin[0]:+.3f}, y={front_kin[1]:+.3f}")
print(f"  Left:  x={left_kin[0]:+.3f}, y={left_kin[1]:+.3f}")
print(f"  Right: x={right_kin[0]:+.3f}, y={right_kin[1]:+.3f}")

print(f"\n{'='*70}")
print("TEST: Pure rotation (vx=0, omega=0.2)")
print(f"{'='*70}")

omega = 0.2

print(f"\n              vix      viy    angle")
print(f"              ----     ----   -------")
for name, pos in [("Front", front_kin), ("Left", left_kin), ("Right", right_kin)]:
    vix = -omega * pos[1]
    viy = omega * pos[0]
    angle_rad = np.arctan2(viy, vix)
    angle_deg = np.degrees(angle_rad)
    print(f"  {name:>5}:  {vix:+.4f}  {viy:+.4f}  {angle_deg:+7.2f}°")

print(f"\n{'='*70}")
print("COMPARISON TO OBSERVED")
print(f"{'='*70}")
print(f"\n              Calculated   Observed   Difference")
print(f"              ----------   --------   ----------")

observed = {"Front": 90.0, "Left": -90.0, "Right": -39.53}

for name, pos in [("Front", front_kin), ("Left", left_kin), ("Right", right_kin)]:
    vix = -omega * pos[1]
    viy = omega * pos[0]
    angle_rad = np.arctan2(viy, vix)
    angle_deg = np.degrees(angle_rad)
    diff = abs(angle_deg - observed[name])
    match = "✓" if diff < 1.0 else "✗"
    print(f"  {name:>5}:    {angle_deg:+7.2f}°    {observed[name]:+7.2f}°    {diff:5.2f}°  {match}")

print(f"\n{'='*70}")
print("SYMMETRY CHECK")
print(f"{'='*70}")
print(f"\nLeft and Right should be symmetric about X-axis:")
print(f"  Left Y:  {left_kin[1]:+.3f}")
print(f"  Right Y: {right_kin[1]:+.3f}")
print(f"  Sum:     {left_kin[1] + right_kin[1]:+.3f}  (should be ≈0)")
print(f"  Symmetric: {'✓' if abs(left_kin[1] + right_kin[1]) < 0.01 else '✗'}")
