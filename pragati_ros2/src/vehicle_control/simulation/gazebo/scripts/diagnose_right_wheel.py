#!/usr/bin/env python3
"""
Analyze the steering behavior to diagnose right wheel issue.
"""

import numpy as np

print("=" * 70)
print("ANALYZING OBSERVED STEERING BEHAVIOR")
print("=" * 70)

# User's observed output with vx=0.2, omega=-0.2:
print("\nCommand: vx=0.200, omega=-0.200 (forward + turning right)")
print("\nObserved steering:")
print("  Front: -36.78°")
print("  Left:  +21.57°")
print("  Right: +83.20°")

print("\n" + "=" * 70)
print("CURRENT CONFIGURATION")
print("=" * 70)

# Current config:
front_urdf = [1.405, 0.910]
left_urdf = [-0.105, 1.810]
right_urdf = [-0.105, -0.010]
offset = [0.650, 0.900]

front_kin = [front_urdf[0] - offset[0], front_urdf[1] - offset[1]]
left_kin = [left_urdf[0] - offset[0], left_urdf[1] - offset[1]]
right_kin = [right_urdf[0] - offset[0], right_urdf[1] - offset[1]]

print(f"\nKinematic positions:")
print(f"  Front: x={front_kin[0]:+.3f}, y={front_kin[1]:+.3f}")
print(f"  Left:  x={left_kin[0]:+.3f}, y={left_kin[1]:+.3f}")
print(f"  Right: x={right_kin[0]:+.3f}, y={right_kin[1]:+.3f}")

print("\n" + "=" * 70)
print("CALCULATED vs OBSERVED")
print("=" * 70)

vx = 0.2
omega = -0.2

print(f"\n              Calculated   Observed   Match?")
for name, pos in [("Front", front_kin), ("Left", left_kin), ("Right", right_kin)]:
    vix = vx - omega * pos[1]
    viy = omega * pos[0]
    angle_deg = np.degrees(np.arctan2(viy, vix))
    
    obs = {"Front": -36.78, "Left": +21.57, "Right": +83.20}
    match = "✓" if abs(angle_deg - obs[name]) < 1.0 else "✗"
    print(f"  {name:>5}:    {angle_deg:+7.2f}°    {obs[name]:+7.2f}°    {match}")

print("\n" + "=" * 70)
print("PHYSICAL INTERPRETATION")
print("=" * 70)

print("\nWith vx=0.2, omega=-0.2 (forward + turning RIGHT):")
print("  - Robot should arc to the RIGHT")
print("  - RIGHT wheel is on INSIDE of turn → should steer more")
print("  - LEFT wheel is on OUTSIDE of turn → should steer less")
print("")
print("Observed:")
print("  Front: -36.78° (steering left)")
print("  Left:  +21.57° (steering right - outside wheel)")
print("  Right: +83.20° (steering right - inside wheel, near limit!)")

print("\nThis seems CORRECT for the turn direction!")
print("Right wheel steering 83° is expected for tight inside turn.")

print("\n" + "=" * 70)
print("POSSIBLE ISSUES")
print("=" * 70)

print("\n1. RIGHT WHEEL AT STEERING LIMIT")
print("   Current: +83.20°, Limit: ±90°")
print("   Margin: only 6.8° from limit!")
print("   → Wheel might be hitting physical/software limits")

print("\n2. ASYMMETRIC REAR WHEELS")
print(f"   Left Y:  {left_kin[1]:+.3f}")
print(f"   Right Y: {right_kin[1]:+.3f}")
print(f"   Sum:     {left_kin[1] + right_kin[1]:+.3f}")
print("   → NOT perfectly symmetric!")
print(f"   Difference: {abs(abs(left_kin[1]) - abs(right_kin[1])):.3f} m")

print("\n3. POTENTIAL Y-COORDINATE SIGN ERROR")
print("   The URDF has opposite rotations for left/right plates:")
print("   - Right: rpy=(-π/2, 0, 0)")
print("   - Left:  rpy=(+π/2, 0, 0)")
print("   This OPPOSITE rotation might flip the Y-axis!")

print("\n" + "=" * 70)
print("TEST: SWAP LEFT/RIGHT Y-COORDINATES")
print("=" * 70)

# Test with swapped Y:
left_test = [left_kin[0], -left_kin[1]]
right_test = [right_kin[0], -right_kin[1]]

print(f"\nTest positions (Y-swapped):")
print(f"  Front: x={front_kin[0]:+.3f}, y={front_kin[1]:+.3f}")
print(f"  Left:  x={left_test[0]:+.3f}, y={left_test[1]:+.3f}")
print(f"  Right: x={right_test[0]:+.3f}, y={right_test[1]:+.3f}")

print(f"\nSymmetry check:")
print(f"  Left Y:  {left_test[1]:+.3f}")
print(f"  Right Y: {right_test[1]:+.3f}")
print(f"  Sum:     {left_test[1] + right_test[1]:+.3f}  (should be ≈0)")

print("\nCalculated angles with Y-swapped:")
for name, pos in [("Front", front_kin), ("Left", left_test), ("Right", right_test)]:
    vix = vx - omega * pos[1]
    viy = omega * pos[0]
    angle_deg = np.degrees(np.arctan2(viy, vix))
    
    obs = {"Front": -36.78, "Left": +21.57, "Right": +83.20}
    match = "✓" if abs(angle_deg - obs[name]) < 1.0 else "✗"
    print(f"  {name:>5}:    {angle_deg:+7.2f}°    {obs[name]:+7.2f}°    {match}")

print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)
print("\nThe calculations MATCH observations perfectly!")
print("If there's a visual issue in Gazebo, it might be:")
print("  1. Steering limit being hit (83° is close to 90°)")
print("  2. Visual mesh orientation not matching joint orientation")
print("  3. Plugin PID controller oscillating near limits")
print("\nTo diagnose: Try LOWER omega values (e.g., omega=±0.1)")
print("This will keep steering angles further from limits.")
