#!/usr/bin/env python3
"""
Calculate actual wheel steering joint positions from vehicle_control URDF.
The URDF has complex nested transforms - this script traces them.
"""

import numpy as np
from scipy.spatial.transform import Rotation

# From URDF joints - tracing transform chain from base-v1 to each steering joint

# FRONT WHEEL
# base-v1 -> base-plate-front: xyz="1.3 0 0.9" rpy="..."
front_base_to_plate = np.array([1.3, 0.0, 0.9])
# base-plate-front -> axial-front (steering joint): xyz="0.105 0.01 -0.097"
front_plate_to_axial = np.array([0.105, 0.01, -0.097])

# LEFT WHEEL  
# base-v1 -> base-plate-left: xyz="0 0 1.8" (rotated frame)
left_base_to_plate = np.array([0.0, 0.0, 1.8])
# base-plate-left -> axial-left (steering joint): xyz="-0.105 0.01 0.097"
left_plate_to_axial = np.array([-0.105, 0.01, 0.097])

# RIGHT WHEEL
# base-v1 -> base-plate-right: xyz="0 0 0" (rotated frame)  
right_base_to_plate = np.array([0.0, 0.0, 0.0])
# base-plate-right -> axial-right (steering joint): xyz="-0.105 -0.01 -0.097"
right_plate_to_axial = np.array([-0.105, -0.01, -0.097])

print("=" * 70)
print("ANALYZING vehicle_control URDF STRUCTURE")
print("=" * 70)

print("\nFROM URDF INSPECTION:")
print(f"Front: base-v1 -> plate: {front_base_to_plate}")
print(f"       plate -> steering: {front_plate_to_axial}")
print(f"Left:  base-v1 -> plate: {left_base_to_plate}")
print(f"       plate -> steering: {left_plate_to_axial}")
print(f"Right: base-v1 -> plate: {right_base_to_plate}")
print(f"       plate -> steering: {right_plate_to_axial}")

# The plates are attached with complex rotations
# Let me extract the key pattern from the URDF structure:

print("\n" + "=" * 70)
print("ACTUAL WHEEL STEERING JOINT POSITIONS")
print("=" * 70)

# From the URDF structure, it looks like:
# - Front wheel: moved 1.3m in +X, 0.9m in +Y from base-v1
# - Left wheel: moved 1.8m in one direction (frame rotated 90°)
# - Right wheel: at base-v1 position

# The base-plate joints are FIXED (Rigid), so we need to account for rotation
# Looking at the rpy values and the coordinate frames...

# More careful analysis:
# base-v1 is the root. Let's see what the actual positions are:
# The z-values in transforms become y-values due to -90° rotation

# Front: xyz="1.3 0 0.9" with rpy rotation means steering at ~(1.3, 0.9, 0)
front_steering_pos = np.array([1.3 + 0.105, 0.9 + 0.01, 0.0])

# Left: xyz="0 0 1.8" with 90° rotation means y=1.8 becomes actual position
# The -0.105 in local frame goes to -0.105 in global X
left_steering_pos = np.array([-0.105, 1.8 + 0.01, 0.0])

# Right: xyz="0 0 0" means at origin
right_steering_pos = np.array([-0.105, -0.01, 0.0])

print(f"\nFront steering joint:  ({front_steering_pos[0]:.3f}, {front_steering_pos[1]:.3f}) m")
print(f"Left steering joint:   ({left_steering_pos[0]:.3f}, {left_steering_pos[1]:.3f}) m")
print(f"Right steering joint:  ({right_steering_pos[0]:.3f}, {right_steering_pos[1]:.3f}) m")

# Calculate distances to verify
front_dist = np.linalg.norm(front_steering_pos[:2])
left_dist = np.linalg.norm(left_steering_pos[:2])  
right_dist = np.linalg.norm(right_steering_pos[:2])

print(f"\nDistances from base-v1:")
print(f"  Front: {front_dist:.3f} m")
print(f"  Left:  {left_dist:.3f} m")
print(f"  Right: {right_dist:.3f} m")

# Now let's express relative to rear axle center
# If we assume rear axle is midway between left and right:
rear_axle_y = (left_steering_pos[1] + right_steering_pos[1]) / 2
rear_axle_x = (left_steering_pos[0] + right_steering_pos[0]) / 2

print(f"\nRear axle center: ({rear_axle_x:.3f}, {rear_axle_y:.3f}) m")

print("\n" + "=" * 70)
print("WHEEL POSITIONS RELATIVE TO REAR AXLE CENTER")
print("=" * 70)

front_rel = front_steering_pos[:2] - np.array([rear_axle_x, rear_axle_y])
left_rel = left_steering_pos[:2] - np.array([rear_axle_x, rear_axle_y])
right_rel = right_steering_pos[:2] - np.array([rear_axle_x, rear_axle_y])

print(f"Front: x={front_rel[0]:+.3f}, y={front_rel[1]:+.3f}")
print(f"Left:  x={left_rel[0]:+.3f}, y={left_rel[1]:+.3f}")
print(f"Right: x={right_rel[0]:+.3f}, y={right_rel[1]:+.3f}")

print("\n" + "=" * 70)
print("KINEMATICS NODE CONFIGURATION (copy to kinematics_node.py)")
print("=" * 70)
print(f"self.declare_parameter('front_wheel_position', [{front_rel[0]:.3f}, {front_rel[1]:.3f}])")
print(f"self.declare_parameter('left_wheel_position', [{left_rel[0]:.3f}, {left_rel[1]:.3f}])")
print(f"self.declare_parameter('right_wheel_position', [{right_rel[0]:.3f}, {right_rel[1]:.3f}])")
print("=" * 70)
