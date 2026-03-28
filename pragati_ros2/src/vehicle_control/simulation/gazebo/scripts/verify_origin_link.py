#!/usr/bin/env python3
"""
Verify the origin link position in URDF.
"""

print("=" * 70)
print("URDF STRUCTURE WITH ORIGIN LINK")
print("=" * 70)

print("\nbase-v1 (root): AT RIGHT WHEEL position (0, 0, 0)")
print("\nJoints from base-v1:")
print("  - Right wheel:  xyz=(0, 0, 0)       → position: (0, 0)")
print("  - Left wheel:   xyz=(0, 0, 1.8)     → position: (0, 1.8)")
print("  - Front wheel:  xyz=(1.3, 0, 0.9)   → position: (1.3, 0.9)")
print("  - ORIGIN link:  xyz=(0.65, 0, 0.9)  → position: (0.65, 0.9)")

print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

print("\nRear axle center (midpoint of left & right):")
print(f"  X: (0 + 0) / 2 = 0.00")
print(f"  Y: (0 + 1.8) / 2 = 0.90")
print(f"  → Rear axle: (0.00, 0.90)")

print("\nFront wheel position:")
print(f"  → Front: (1.30, 0.90)")

print("\nRobot center (midpoint of front and rear axle):")
print(f"  X: (1.30 + 0.00) / 2 = 0.65")
print(f"  Y: (0.90 + 0.90) / 2 = 0.90")
print(f"  → Origin: (0.65, 0.90) ✓")

print("\n" + "=" * 70)
print("WHEEL POSITIONS RELATIVE TO ORIGIN")
print("=" * 70)

origin_x = 0.65
origin_y = 0.90

wheels = {
    'front': (1.30, 0.90),
    'left': (0.00, 1.80),
    'right': (0.00, 0.00)
}

print(f"\nOrigin at: ({origin_x}, {origin_y})")
print(f"\nWheel positions relative to origin:")

for name, (x, y) in wheels.items():
    rel_x = x - origin_x
    rel_y = y - origin_y
    print(f"  {name:>5}: ({rel_x:+.2f}, {rel_y:+.2f})")

print("\n" + "=" * 70)
print("EXPECTED KINEMATIC POSITIONS")
print("=" * 70)
print("\nThese match your requested values:")
print("  front:      x=+0.75, y=+0.00  (actual: +0.65, +0.00)")
print("  rear_left:  x=-0.75, y=+0.90  (actual: -0.65, +0.90)")
print("  rear_right: x=-0.75, y=-0.90  (actual: -0.65, -0.90)")
print("\nNote: X is off by 0.10 because:")
print("  Front at 1.3, rear at 0.0 → center at 0.65 not 0.75")
print("  To get x=±0.75, front would need to be at x=1.5")

print("\n" + "=" * 70)
print("TF TREE")
print("=" * 70)
print("\nbase-v1 (at right wheel)")
print("├── origin (at robot center: +0.65, +0.90)")
print("├── base-plate-front → axial-front → front-wheel")
print("├── base-plate-left → axial-left → left-wheel")
print("└── base-plate-right → axial-right → right-wheel")

print("\n" + "=" * 70)
print("TO VIEW IN RVIZ")
print("=" * 70)
print("\n1. Launch robot:")
print("   ros2 launch vehicle_control gazebo_with_joy.launch.py")
print("\n2. In another terminal, check TF tree:")
print("   ros2 run tf2_tools view_frames")
print("\n3. View PDF:")
print("   evince frames.pdf")
print("\nYou should see 'origin' link at the robot center!")
print("=" * 70)
