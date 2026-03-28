#!/bin/bash
# Comprehensive Offline Cotton Detection Test Script
# Tests cotton detection with saved images instead of live camera

set -e  # Exit on error

WORKSPACE_ROOT="/home/uday/Downloads/pragati_ros2"
TEST_DIR="${WORKSPACE_ROOT}/test_offline_detection"
RESULTS_DIR="${TEST_DIR}/results"
TEST_IMAGES_DIR="${TEST_DIR}/test_images"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Offline Cotton Detection Test Suite  ${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# Function to print section headers
print_section() {
    echo ""
    echo -e "${BLUE}>>> $1${NC}"
    echo "-------------------------------------------"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Create test directory structure
print_section "Setting up test environment"
mkdir -p "${TEST_DIR}"
mkdir -p "${RESULTS_DIR}"
mkdir -p "${TEST_IMAGES_DIR}"
print_success "Test directories created"

# Check if workspace is built
print_section "Checking workspace build status"
if [ ! -d "${WORKSPACE_ROOT}/install" ]; then
    print_error "Workspace not built. Building now..."
    cd "${WORKSPACE_ROOT}"
    colcon build --packages-select cotton_detection_ros2
    if [ $? -ne 0 ]; then
        print_error "Build failed. Please fix build errors first."
        exit 1
    fi
fi
print_success "Workspace is built"

# Source the workspace
print_section "Sourcing workspace"
cd "${WORKSPACE_ROOT}"
source install/setup.bash
print_success "Workspace sourced"

# Generate test images if they don't exist
print_section "Preparing test images"
TEST_IMAGE_COUNT=0

# Look for existing images in data/inputs
if [ -d "${WORKSPACE_ROOT}/data/inputs" ]; then
    EXISTING_IMAGES=$(find "${WORKSPACE_ROOT}/data/inputs" -type f \( -iname "*.jpg" -o -iname "*.png" \) | head -5)
    if [ -n "$EXISTING_IMAGES" ]; then
        echo "$EXISTING_IMAGES" | while read img; do
            cp "$img" "${TEST_IMAGES_DIR}/"
            TEST_IMAGE_COUNT=$((TEST_IMAGE_COUNT + 1))
        done
        print_success "Copied $TEST_IMAGE_COUNT existing images"
    fi
fi

# Generate synthetic test images if no real images found
if [ $TEST_IMAGE_COUNT -eq 0 ]; then
    print_warning "No existing images found, generating synthetic test images..."
    
    python3 << 'EOF'
import cv2
import numpy as np
import os

test_dir = os.environ['TEST_IMAGES_DIR']

# Generate 3 synthetic test images
for i in range(3):
    # Create a 640x480 image with random cotton-like blobs
    img = np.ones((480, 640, 3), dtype=np.uint8) * 50  # Dark background
    
    # Add 3-5 white blobs (cotton bolls)
    num_blobs = np.random.randint(3, 6)
    for j in range(num_blobs):
        x = np.random.randint(100, 540)
        y = np.random.randint(100, 380)
        radius = np.random.randint(20, 40)
        cv2.circle(img, (x, y), radius, (240, 240, 240), -1)
        # Add some noise
        noise = np.random.randint(-20, 20, (radius*2, radius*2, 3))
        y1, y2 = max(0, y-radius), min(480, y+radius)
        x1, x2 = max(0, x-radius), min(640, x+radius)
        img[y1:y2, x1:x2] = np.clip(img[y1:y2, x1:x2] + noise[:y2-y1, :x2-x1], 0, 255)
    
    # Save image
    filename = f'{test_dir}/synthetic_cotton_{i+1}.jpg'
    cv2.imwrite(filename, img)
    print(f'Generated: {filename}')

print(f'Created 3 synthetic test images')
EOF
    
    if [ $? -eq 0 ]; then
        print_success "Generated 3 synthetic test images"
        TEST_IMAGE_COUNT=3
    else
        print_error "Failed to generate test images"
        exit 1
    fi
fi

# Count final test images
FINAL_IMAGE_COUNT=$(find "${TEST_IMAGES_DIR}" -type f \( -iname "*.jpg" -o -iname "*.png" \) | wc -l)
print_success "Test images ready: ${FINAL_IMAGE_COUNT} images"
echo ""
ls -lh "${TEST_IMAGES_DIR}"

# Test 1: Check if test_with_images.py exists
print_section "Test 1: Checking test script availability"
TEST_SCRIPT="${WORKSPACE_ROOT}/src/cotton_detection_ros2/test/test_with_images.py"

if [ ! -f "$TEST_SCRIPT" ]; then
    print_error "Test script not found: $TEST_SCRIPT"
    exit 1
fi
print_success "Test script found: $TEST_SCRIPT"

# Test 2: Start cotton detection node in background
print_section "Test 2: Starting cotton detection node"
print_warning "Starting cotton_detection_node in background..."

# Kill any existing instances
pkill -f cotton_detection_node || true
sleep 1

# Start the node with simulation mode for offline testing
ros2 run cotton_detection_ros2 cotton_detection_node \
    --ros-args \
    -p simulation_mode:=false \
    -p enable_debug_output:=true \
    > "${RESULTS_DIR}/node_output.log" 2>&1 &

NODE_PID=$!
echo "Node PID: $NODE_PID"

# Wait for node to be ready
print_warning "Waiting for node to initialize (10 seconds)..."
sleep 10

# Check if node is still running
if ! kill -0 $NODE_PID 2>/dev/null; then
    print_error "Cotton detection node failed to start"
    cat "${RESULTS_DIR}/node_output.log"
    exit 1
fi
print_success "Cotton detection node is running (PID: $NODE_PID)"

# Test 3: Verify topics
print_section "Test 3: Verifying ROS2 topics"
EXPECTED_TOPICS=(
    "/cotton_detection/results"
    "/camera/image_raw"
)

for topic in "${EXPECTED_TOPICS[@]}"; do
    if ros2 topic list | grep -q "^${topic}$"; then
        print_success "Topic exists: $topic"
    else
        print_warning "Topic not found: $topic (may be created on demand)"
    fi
done

# Test 4: Run offline image test with Python test script
print_section "Test 4: Running offline image test"
print_warning "Publishing test images to detection node..."

# Use the Python test script
cd "${WORKSPACE_ROOT}"
python3 "${TEST_SCRIPT}" \
    --dir "${TEST_IMAGES_DIR}" \
    --output "${RESULTS_DIR}/detection_results.json" \
    --timeout 5.0 \
    --delay 1.0 \
    > "${RESULTS_DIR}/test_output.log" 2>&1

TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
    print_success "Offline test completed successfully"
else
    print_error "Offline test failed with exit code: $TEST_EXIT_CODE"
    echo ""
    echo "Last 20 lines of test output:"
    tail -20 "${RESULTS_DIR}/test_output.log"
fi

# Test 5: Analyze results
print_section "Test 5: Analyzing results"

if [ -f "${RESULTS_DIR}/detection_results.json" ]; then
    print_success "Results file created"
    
    # Parse JSON results
    python3 << EOF
import json
import sys

try:
    with open('${RESULTS_DIR}/detection_results.json', 'r') as f:
        results = json.load(f)
    
    total_images = len(results)
    images_with_detections = sum(1 for r in results.values() if r.get('num_detections', 0) > 0)
    total_detections = sum(r.get('num_detections', 0) for r in results.values())
    
    print(f"\n{'='*50}")
    print("DETECTION RESULTS SUMMARY")
    print(f"{'='*50}")
    print(f"Total images tested:     {total_images}")
    print(f"Images with detections:  {images_with_detections}")
    print(f"Total detections:        {total_detections}")
    if total_images > 0:
        print(f"Detection rate:          {images_with_detections/total_images*100:.1f}%")
        print(f"Avg detections/image:    {total_detections/total_images:.2f}")
    print(f"{'='*50}\n")
    
    # Show first few detections
    print("Sample Detections:")
    count = 0
    for img_name, result in list(results.items())[:3]:
        if result.get('num_detections', 0) > 0:
            print(f"  {img_name}: {result['num_detections']} detection(s)")
            if 'detections' in result and result['detections']:
                det = result['detections'][0]
                if 'bbox' in det:
                    print(f"    - Position: ({det['bbox']['center_x']:.0f}, {det['bbox']['center_y']:.0f})")
                    print(f"    - Confidence: {det['confidence']:.2f}")
            count += 1
    
    sys.exit(0 if total_detections > 0 else 1)

except Exception as e:
    print(f"\nError parsing results: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    
    ANALYSIS_EXIT_CODE=$?
    if [ $ANALYSIS_EXIT_CODE -eq 0 ]; then
        print_success "Results analysis complete - detections found!"
    else
        print_warning "No detections found or analysis failed"
    fi
else
    print_error "Results file not created"
    echo "Test output log:"
    cat "${RESULTS_DIR}/test_output.log"
fi

# Test 6: Check for issues
print_section "Test 6: Checking for common issues"

# Check node logs
if grep -i "error\|failed\|exception" "${RESULTS_DIR}/node_output.log" > /dev/null; then
    print_warning "Found errors/warnings in node logs:"
    grep -i "error\|failed\|exception" "${RESULTS_DIR}/node_output.log" | head -5
else
    print_success "No critical errors in node logs"
fi

# Check test logs
if [ -f "${RESULTS_DIR}/test_output.log" ]; then
    if grep -i "timeout\|error\|failed" "${RESULTS_DIR}/test_output.log" > /dev/null; then
        print_warning "Found issues in test logs:"
        grep -i "timeout\|error\|failed" "${RESULTS_DIR}/test_output.log" | head -5
    else
        print_success "No issues in test logs"
    fi
fi

# Cleanup
print_section "Cleanup"
print_warning "Stopping cotton detection node..."
kill $NODE_PID 2>/dev/null || true
sleep 2
pkill -9 -f cotton_detection_node || true
print_success "Node stopped"

# Final summary
print_section "Test Summary"
echo ""
echo "Test Results Location: ${RESULTS_DIR}"
echo "  - Node output:      ${RESULTS_DIR}/node_output.log"
echo "  - Test output:      ${RESULTS_DIR}/test_output.log"
echo "  - Detection results: ${RESULTS_DIR}/detection_results.json"
echo ""
echo "Test Images Location: ${TEST_IMAGES_DIR}"
echo ""

if [ $TEST_EXIT_CODE -eq 0 ] && [ ${ANALYSIS_EXIT_CODE:-1} -eq 0 ]; then
    print_success "ALL TESTS PASSED ✓"
    echo ""
    exit 0
else
    print_error "SOME TESTS FAILED ✗"
    echo ""
    echo "Troubleshooting tips:"
    echo "  1. Check node logs: cat ${RESULTS_DIR}/node_output.log"
    echo "  2. Check test logs: cat ${RESULTS_DIR}/test_output.log"
    echo "  3. Verify camera topic: ros2 topic echo /camera/image_raw --once"
    echo "  4. Check detection service: ros2 service call /cotton_detection/detect ..."
    echo ""
    exit 1
fi
