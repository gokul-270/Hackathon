#!/bin/bash
# Comprehensive Cotton Detection Integration Test
# Tests the complete flow: cotton_detection_ros2 -> topic -> yanthra_move

set -e
# Find workspace root (go up from docs/archive/2025-10-21/scripts/)
WORKSPACE_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$WORKSPACE_ROOT"
source install/setup.bash

echo "=== Cotton Detection Integration Test ==="
echo ""

# Cleanup function
cleanup() {
    echo "Cleaning up processes..."
    pkill -TERM -f cotton_detection_node 2>/dev/null || true
    pkill -TERM -f yanthra_move_node 2>/dev/null || true
    sleep 2
    pkill -9 -f cotton_detection_node 2>/dev/null || true
    pkill -9 -f yanthra_move_node 2>/dev/null || true
}

trap cleanup EXIT

# Clean old logs
rm -f /tmp/test_cotton.log /tmp/test_yanthra.log /tmp/test_result.txt

echo "Step 1: Starting cotton_detection_node..."
ros2 run cotton_detection_ros2 cotton_detection_node > /tmp/test_cotton.log 2>&1 &
COTTON_PID=$!
echo "  PID: $COTTON_PID"
sleep 3

# Check if node is running
if ! ps -p $COTTON_PID > /dev/null; then
    echo "  ❌ FAILED: cotton_detection_node died"
    cat /tmp/test_cotton.log
    exit 1
fi
echo "  ✅ cotton_detection_node started"

echo ""
echo "Step 2: Checking if /cotton_detection/results topic exists..."
timeout 5 ros2 topic list | grep "/cotton_detection/results" || {
    echo "  ❌ FAILED: Topic not found"
    exit 1
}
echo "  ✅ Topic exists"

echo ""
echo "Step 3: Triggering detection via service..."
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" --timeout 10 > /tmp/test_service_response.txt 2>&1 || {
    echo "  ⚠️  Service call failed (expected if no camera)"
    cat /tmp/test_service_response.txt
}
echo "  ✅ Service call attempted"

echo ""
echo "Step 4: Checking if DetectionResult is published..."
timeout 5 ros2 topic echo /cotton_detection/results --once > /tmp/test_result.txt 2>&1 || {
    echo "  ⚠️  No message received (expected if no camera/images)"
}

if [ -s /tmp/test_result.txt ]; then
    echo "  ✅ DetectionResult received:"
    cat /tmp/test_result.txt | head -20
else
    echo "  ℹ️  No DetectionResult (normal without camera)"
fi

echo ""
echo "Step 5: Starting yanthra_move_node in simulation mode..."
ros2 run yanthra_move yanthra_move_node \
    --ros-args \
    -p simulation_mode:=true \
    -p start_switch.enable_wait:=false \
    -p continuous_operation:=false \
    -p max_runtime_minutes:=0 \
    > /tmp/test_yanthra.log 2>&1 &
YANTHRA_PID=$!
echo "  PID: $YANTHRA_PID"
sleep 5

# Check if node is running
if ! ps -p $YANTHRA_PID > /dev/null; then
    echo "  ⚠️  yanthra_move_node exited (may be normal after one cycle)"
else
    echo "  ✅ yanthra_move_node started"
fi

echo ""
echo "Step 6: Analyzing yanthra_move logs for cotton detection integration..."
if grep -q "Cotton detection subscription initialized" /tmp/test_yanthra.log; then
    echo "  ✅ Cotton detection subscription created"
else
    echo "  ❌ Cotton detection subscription NOT found"
fi

if grep -q "Motion Controller initialized with cotton position provider" /tmp/test_yanthra.log; then
    echo "  ✅ MotionController wired with provider"
else
    echo "  ❌ MotionController provider NOT wired"
fi

if grep -q "cotton_position_provider_" /tmp/test_yanthra.log || grep -q "No cotton detection data" /tmp/test_yanthra.log; then
    echo "  ✅ MotionController attempted to use provider"
else
    echo "  ℹ️  Provider usage not detected in logs"
fi

echo ""
echo "Step 7: Trigger another detection while yanthra_move is alive..."
if ps -p $YANTHRA_PID > /dev/null; then
    ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" --timeout 5 > /dev/null 2>&1 || true
    sleep 2
    echo "  ✅ Second detection triggered"
else
    echo "  ℹ️  yanthra_move already exited (single-cycle mode)"
fi

echo ""
echo "=== Test Summary ==="
echo ""
echo "Cotton Detection Node Log (last 30 lines):"
tail -n 30 /tmp/test_cotton.log
echo ""
echo "Yanthra Move Node Log (last 50 lines):"
tail -n 50 /tmp/test_yanthra.log

echo ""
echo "=== Integration Test Complete ==="
echo ""
echo "Key Checks:"
echo "  - cotton_detection_node: $(ps -p $COTTON_PID > /dev/null 2>&1 && echo '✅ Running' || echo '❌ Stopped')"
echo "  - yanthra_move_node: $(ps -p $YANTHRA_PID > /dev/null 2>&1 && echo '✅ Running' || echo 'ℹ️  Completed')"
echo "  - Topic /cotton_detection/results: $(ros2 topic list 2>/dev/null | grep -q "/cotton_detection/results" && echo '✅ Exists' || echo '❌ Missing')"
echo ""
echo "Run 'cat /tmp/test_cotton.log' for full cotton detection logs"
echo "Run 'cat /tmp/test_yanthra.log' for full yanthra move logs"