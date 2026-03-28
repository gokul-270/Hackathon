#!/bin/bash
# Quick Motor Test - Tests basic motor functionality
# Usage: ./quick_motor_test.sh [motor_id] [can_id]
# Example: ./quick_motor_test.sh 1 141

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${PRAGATI_WORKSPACE:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SETUP_FILE="${WORKSPACE_ROOT}/install/setup.bash"

if [[ ! -f "$SETUP_FILE" ]]; then
    echo "✗ ROS2 workspace not built. Expected setup file at: $SETUP_FILE"
    echo "  Build the workspace (colcon build) or export PRAGATI_WORKSPACE."
    exit 1
fi

source "$SETUP_FILE"

MOTOR_ID=${1:-1}
CAN_ID=${2:-141}

printf "╔═══════════════════════════════════════════════╗\n"
printf "║     QUICK MOTOR TEST - Motor %s (CAN %s)      ║\n" "$MOTOR_ID" "$CAN_ID"
printf "╚═══════════════════════════════════════════════╝\n\n"

PASS=0
FAIL=0

# Test 1: Status
echo "TEST 1: Reading Motor Status..."
OUTPUT=$(timeout 8s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=$MOTOR_ID -p mode:=status 2>&1)

if echo "$OUTPUT" | grep -q "Test completed successfully"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "$OUTPUT" | grep -E "Temperature|Voltage" | head -2
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi
echo ""

# Test 2: Angle
echo "TEST 2: Reading Encoder Angle..."
OUTPUT=$(timeout 8s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=$MOTOR_ID -p mode:=angle 2>&1)

if echo "$OUTPUT" | grep -q "Test completed successfully"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "$OUTPUT" | grep "Multi-turn angle"
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi
echo ""

# Test 3: ON/OFF
echo "TEST 3: Motor ON/OFF Control..."
OUTPUT=$(timeout 8s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=$MOTOR_ID -p mode:=on_off 2>&1)

if echo "$OUTPUT" | grep -q "Test completed successfully"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "$OUTPUT" | grep -E "Motor ON|Motor OFF" | head -2
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi
echo ""

# Test 4: Position +1.0 rad
echo "TEST 4: Position Control (+1.0 rad / 57.3°)..."
OUTPUT=$(timeout 8s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=$MOTOR_ID \
  -p mode:=position -p position_rad:=1.0 2>&1)

if echo "$OUTPUT" | grep -q "Test completed successfully"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "$OUTPUT" | grep "Current angle"
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi
echo ""

# Test 5: Position -0.5 rad
echo "TEST 5: Position Control (-0.5 rad / -28.6°)..."
OUTPUT=$(timeout 8s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=$MOTOR_ID \
  -p mode:=position -p position_rad:=-0.5 2>&1)

if echo "$OUTPUT" | grep -q "Test completed successfully"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "$OUTPUT" | grep "Current angle"
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi
echo ""

# Test 6: Velocity Control
echo "TEST 6: Velocity Control (2.0 rad/s for 3 seconds)..."
OUTPUT=$(timeout 8s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=$MOTOR_ID \
  -p mode:=velocity -p velocity_rad_s:=2.0 2>&1)

if echo "$OUTPUT" | grep -q "Velocity command sent successfully\|Test completed successfully"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "$OUTPUT" | grep "speed=" | head -2
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi
echo ""

# Test 7: Raw CAN Commands
echo "TEST 7: Raw CAN Commands..."
LOG_FILE="/tmp/can_test_${MOTOR_ID}.log"

timeout 2s candump can0 > "$LOG_FILE" 2>&1 &
CANDUMP_PID=$!
sleep 0.5

cansend can0 ${CAN_ID}#9A00000000000000
timeout 1s true >/dev/null 2>&1 || true

kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

if grep -q "${CAN_ID}" "$LOG_FILE"; then
    echo "✓ PASSED"
    PASS=$((PASS+1))
    echo "  CAN traffic detected on ID $CAN_ID"
else
    echo "✗ FAILED"
    FAIL=$((FAIL+1))
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "RESULTS: $PASS Passed, $FAIL Failed"
if [ $FAIL -eq 0 ]; then
    echo "✓ ALL TESTS PASSED - Motor $MOTOR_ID is READY!"
    exit 0
else
    echo "⚠ Some tests failed"
    exit 1
fi
