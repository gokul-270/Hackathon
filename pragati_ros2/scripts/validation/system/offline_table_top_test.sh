#!/usr/bin/env bash
# Offline Table Top Test - Cotton Detection + Motor Movement

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${PRAGATI_WORKSPACE:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SETUP_FILE="$WORK_DIR/install/setup.bash"

printf "╔════════════════════════════════════════════════════════════════╗\n"
printf "║   OFFLINE TABLE TOP TEST - Cotton Detection + Motors          ║\n"
printf "╚════════════════════════════════════════════════════════════════╝\n\n"

if [[ ! -f "$SETUP_FILE" ]]; then
    echo "✗ ROS2 workspace not built. Expected: $SETUP_FILE"
    exit 1
fi

cd "$WORK_DIR"
source "$SETUP_FILE"

IMAGE_PATH="$WORK_DIR/inputs/cotton_test.jpg"
if [[ ! -f "$IMAGE_PATH" ]]; then
    echo "✗ Test image not found: $IMAGE_PATH"
    exit 1
fi

echo "✓ Test image found: $IMAGE_PATH"
echo ""

echo "Starting cotton detection in simulation mode..."
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true use_depthai:=false &
DETECTION_PID=$!
echo "Detection PID: $DETECTION_PID"
sleep 10

echo ""
echo "Checking if detection node is running..."
if ros2 node list | grep -q cotton_detection; then
    echo "✓ Cotton detection node is running"
else
    echo "✗ Cotton detection node not found"
    kill $DETECTION_PID 2>/dev/null
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 1: Cotton Detection (Simulation Mode)"
echo "═══════════════════════════════════════════════════════════════"

echo "Triggering cotton detection..."
OUTPUT=$(timeout 10s python3 "$WORK_DIR/src/cotton_detection_ros2/test/test_cotton_detection.py" --command 1 2>&1 || echo "Detection completed")
echo "$OUTPUT"

if echo "$OUTPUT" | grep -q "Success\|detections"; then
    echo "✓ Cotton detection returned results"
    DETECTION_PASS=1
else
    echo "✗ Cotton detection failed"
    DETECTION_PASS=0
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 2: Motor Movement Based on Detection"
echo "═══════════════════════════════════════════════════════════════"

MOTOR_PASS=0

run_motor_test() {
    local node_id="$1"
    local target="$2"
    echo "Moving Motor $node_id to position $target rad..."
    OUTPUT=$(timeout 10s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
        -p interface_name:=can0 -p baud_rate:=500000 -p node_id:="$node_id" \
        -p mode:=position -p position_rad:="$target" 2>&1)
    echo "$OUTPUT"
    if echo "$OUTPUT" | grep -q "Test completed successfully"; then
        ANGLE=$(echo "$OUTPUT" | grep "Current angle:" | awk '{print $4, $5, $6}')
        echo "✓ Motor $node_id reached target: $ANGLE"
        MOTOR_PASS=$((MOTOR_PASS+1))
    else
        echo "✗ Motor $node_id failed"
    fi
    echo ""
}

run_motor_test 1 1.0
run_motor_test 2 0.5
run_motor_test 3 -0.5

echo "Stopping detection node..."
kill $DETECTION_PID 2>/dev/null
wait $DETECTION_PID 2>/dev/null || true
sleep 2

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              OFFLINE TABLE TOP TEST SUMMARY                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "TEST RESULTS:"
echo "─────────────────────────────────────────────────────────────────"

if [[ $DETECTION_PASS -eq 1 ]]; then
    echo " 1. Cotton Detection (Simulation):    ✓ PASS"
else
    echo " 1. Cotton Detection (Simulation):    ✗ FAIL"
fi

if [[ $MOTOR_PASS -eq 3 ]]; then
    echo " 2. Motor Movement to Positions:       ✓ PASS (3/3 motors)"
elif [[ $MOTOR_PASS -gt 0 ]]; then
    echo " 2. Motor Movement to Positions:       ~ PARTIAL ($MOTOR_PASS/3 motors)"
else
    echo " 2. Motor Movement to Positions:       ✗ FAIL (0/3 motors)"
fi

echo "─────────────────────────────────────────────────────────────────"
echo ""

TOTAL_PASS=$((DETECTION_PASS + (MOTOR_PASS >= 3 ? 1 : 0)))

if [[ $TOTAL_PASS -eq 2 ]]; then
    echo "✓✓✓ OFFLINE TABLE TOP TEST PASSED ✓✓✓"
    echo ""
    echo "System validated:"
    echo "  - Cotton detection working (simulation mode)"
    echo "  - All motors moving to target positions"
    echo "  - Ready for real camera integration"
    exit 0
else
    echo "⚠ Some tests failed (Passed: $TOTAL_PASS/2)"
    exit 1
fi
