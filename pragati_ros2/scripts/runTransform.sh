#!/bin/bash
# runTrans.sh - Transform a world point through TF chains and verify consistency
# Usage: ./runTrans.sh [x] [y] [z]
# Default point: (0.100, 0.100, 0.100)

set -e

# World point coordinates (can be overridden via arguments)
PX=${1:-0.100}
PY=${2:-0.100}
PZ=${3:-0.100}

echo "================================================"
echo "TF Point Transformation Verification"
echo "================================================"
echo "World Point: ($PX, $PY, $PZ)"
echo ""

# Check if required frames exist (with retry)
echo "Checking TF frames..."
MAX_RETRIES=10
RETRY_DELAY=1

for pair in "world camera_link" "camera_link yanthra_link" "world yanthra_link"; do
    read parent child <<< "$pair"
    success=false
    for ((i=1; i<=MAX_RETRIES; i++)); do
        # tf2_echo outputs transform info on success; check for "Translation" in output
        output=$(timeout 3s ros2 run tf2_ros tf2_echo "$parent" "$child" 2>&1 | head -10)
        if echo "$output" | grep -q "Translation"; then
            success=true
            break
        fi
        echo "  Waiting for $parent → $child... (attempt $i/$MAX_RETRIES)"
        sleep $RETRY_DELAY
    done
    if [ "$success" = false ]; then
        echo "ERROR: Transform $parent → $child not available after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "  ✓ $parent → $child exists"
done
echo ""

# Extract transforms with robust parsing
extract_translation() {
    # Extract numbers from "- Translation: [x, y, z]"
    echo "$1" | grep "Translation" | grep -oP '\[.*?\]' | tr -d '[]' | tr ',' '\n' | tr -d ' ' | head -3 | tr '\n' ',' | sed 's/,$//'
}
extract_quaternion() {
    # Extract numbers from "- Rotation: in Quaternion [x, y, z, w]"
    echo "$1" | grep "Quaternion" | grep -oP '\[.*?\]' | tr -d '[]' | tr ',' '\n' | tr -d ' ' | head -4 | tr '\n' ',' | sed 's/,$//'
}

# Get all transforms
echo "Fetching TF transforms..."
WORLD_TO_CAMERA=$(timeout 5s ros2 run tf2_ros tf2_echo world camera_link 2>&1 | head -20)
CAMERA_TO_YANTHRA=$(timeout 5s ros2 run tf2_ros tf2_echo camera_link yanthra_link 2>&1 | head -20)
WORLD_TO_YANTHRA=$(timeout 5s ros2 run tf2_ros tf2_echo world yanthra_link 2>&1 | head -20)

# Get values
T_WC=$(extract_translation "$WORLD_TO_CAMERA")
Q_WC=$(extract_quaternion "$WORLD_TO_CAMERA")
T_CY=$(extract_translation "$CAMERA_TO_YANTHRA")
Q_CY=$(extract_quaternion "$CAMERA_TO_YANTHRA")
T_WY=$(extract_translation "$WORLD_TO_YANTHRA")
Q_WY=$(extract_quaternion "$WORLD_TO_YANTHRA")

# Validate inputs before Python
for var in T_WC Q_WC T_WY Q_WY T_CY Q_CY; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Failed to extract $var"
        exit 1
    fi
done

echo ""
echo "================================================"
echo "POINT TRANSFORMATION RESULTS"
echo "================================================"

# Python script to transform point through both chains
python3 << EOF
import numpy as np
from scipy.spatial.transform import Rotation as R

def parse_vec(s):
    if not s:
        print("ERROR: Empty input vector")
        exit(1)
    try:
        return np.array([float(x.strip()) for x in s.split(',')])
    except Exception as e:
        print(f"ERROR: Failed to parse vector: {s} - {e}")
        exit(1)

def transform_point(point, translation, quaternion):
    """Transform a point using translation and rotation (quaternion)"""
    rot = R.from_quat(quaternion)  # scipy uses [x,y,z,w]
    # To transform point FROM parent TO child frame:
    # p_child = R_inv * (p_parent - t)
    return rot.inv().apply(point - translation)

def inverse_transform_point(point, translation, quaternion):
    """Inverse transform: from child frame back to parent frame"""
    rot = R.from_quat(quaternion)
    return rot.apply(point) + translation

# World point
world_point = np.array([$PX, $PY, $PZ])

# Parse transforms (these are parent->child transforms from tf2_echo)
# tf2_echo A B gives: translation and rotation of B's origin in A's frame
t_wc = parse_vec("$T_WC")  # world -> camera_link
q_wc = parse_vec("$Q_WC")
t_cy = parse_vec("$T_CY")  # camera_link -> yanthra_link
q_cy = parse_vec("$Q_CY")
t_wy = parse_vec("$T_WY")  # world -> yanthra_link (direct)
q_wy = parse_vec("$Q_WY")

print(f"Input Point in WORLD frame: [{world_point[0]:.4f}, {world_point[1]:.4f}, {world_point[2]:.4f}]")
print()

# Chain 1: world -> camera_link -> yanthra_link
# Step 1: Transform point from world to camera_link frame
point_in_camera = transform_point(world_point, t_wc, q_wc)
print(f"Point in CAMERA_LINK frame: [{point_in_camera[0]:.4f}, {point_in_camera[1]:.4f}, {point_in_camera[2]:.4f}]")

# Step 2: Transform point from camera_link to yanthra_link frame
point_in_yanthra_via_camera = transform_point(point_in_camera, t_cy, q_cy)
print(f"Point in YANTHRA_LINK (via camera): [{point_in_yanthra_via_camera[0]:.4f}, {point_in_yanthra_via_camera[1]:.4f}, {point_in_yanthra_via_camera[2]:.4f}]")
print()

# Chain 2: world -> yanthra_link (direct)
point_in_yanthra_direct = transform_point(world_point, t_wy, q_wy)
print(f"Point in YANTHRA_LINK (direct): [{point_in_yanthra_direct[0]:.4f}, {point_in_yanthra_direct[1]:.4f}, {point_in_yanthra_direct[2]:.4f}]")
print()

# Compare results
print("================================================")
print("COMPARISON")
print("================================================")
diff = point_in_yanthra_via_camera - point_in_yanthra_direct
dist = np.linalg.norm(diff)

print(f"Difference (via_camera - direct):")
print(f"  Δx: {diff[0]:.6f} m")
print(f"  Δy: {diff[1]:.6f} m")
print(f"  Δz: {diff[2]:.6f} m")
print(f"  Total distance: {dist:.6f} m")
print()

TOLERANCE = 0.001  # 1mm tolerance
if dist < TOLERANCE:
    print(f"✓ TRANSFORMS ARE CONSISTENT (error < {TOLERANCE}m)")
else:
    print(f"✗ TRANSFORMS ARE INCONSISTENT (error >= {TOLERANCE}m)")
EOF

echo "================================================"
