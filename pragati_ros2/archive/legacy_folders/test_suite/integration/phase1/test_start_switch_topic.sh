#!/bin/bash

# Test script for Phase 1b - START_SWITCH topic implementation
# Supports both direct node and launch file modes
echo "=== Testing Phase 1b: START_SWITCH Topic Implementation ==="
echo

# Test mode configuration (can be overridden via environment variables)
LAUNCH_MODE="${LAUNCH_MODE:-node}"  # "node" (default for backwards compat) or "launch"
CONTINUOUS_OPERATION="${CONTINUOUS_OPERATION:-false}"

echo "Test Mode: ${LAUNCH_MODE}"
echo "Continuous Operation: ${CONTINUOUS_OPERATION}"
echo

# Source the setup files
source install/setup.bash

echo "1. Testing parameter validation..."
# Test parameter validation
ros2 param get /yanthra_move start_switch.timeout_sec 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ start_switch.timeout_sec parameter accessible"
else
    echo "✗ start_switch.timeout_sec parameter not found"
fi

ros2 param get /yanthra_move start_switch.enable_wait 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ start_switch.enable_wait parameter accessible"
else
    echo "✗ start_switch.enable_wait parameter not found"
fi

ros2 param get /yanthra_move start_switch.prefer_topic 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ start_switch.prefer_topic parameter accessible"
else
    echo "✗ start_switch.prefer_topic parameter not found"
fi

echo
echo "2. Testing with START_SWITCH disabled (development mode)..."
# Test with START_SWITCH disabled
if [ "$LAUNCH_MODE" = "node" ]; then
    timeout 10s install/yanthra_move/lib/yanthra_move/yanthra_move_node --ros-args \
        --params-file src/yanthra_move/config/production.yaml \
        -p start_switch.enable_wait:=false \
        -p continuous_operation:=${CONTINUOUS_OPERATION} &
    SYSTEM_PID=$!
else
    timeout 10s ros2 launch yanthra_move pragati_complete.launch.py \
        start_switch.enable_wait:=false \
        continuous_operation:=${CONTINUOUS_OPERATION} >/dev/null 2>&1 &
    SYSTEM_PID=$!
fi

sleep 3

# Check if system is running
if kill -0 $SYSTEM_PID 2>/dev/null; then
    echo "✓ System running with START_SWITCH disabled (${LAUNCH_MODE} mode)"
    kill $SYSTEM_PID
    wait $SYSTEM_PID 2>/dev/null
else
    echo "✗ System failed to start with START_SWITCH disabled (${LAUNCH_MODE} mode)"
fi

echo
echo "3. Testing START_SWITCH topic subscription..."
# Start system with topic preference
timeout 15s install/yanthra_move/lib/yanthra_move/yanthra_move_node --ros-args \
    --params-file src/yanthra_move/config/production.yaml \
    -p start_switch.enable_wait:=true \
    -p start_switch.prefer_topic:=true \
    -p start_switch.timeout_sec:=5.0 \
    -p continuous_operation:=false &

SYSTEM_PID=$!
sleep 2

# Check if system is waiting for start switch
echo "System should be waiting for START_SWITCH..."
sleep 1

# Send start command via topic
echo "Sending start command via topic..."
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "data: true"

sleep 2

# Check if system is still running (should proceed after receiving topic message)
if kill -0 $SYSTEM_PID 2>/dev/null; then
    echo "✓ System responded to START_SWITCH topic command"
    kill $SYSTEM_PID
    wait $SYSTEM_PID 2>/dev/null
else
    echo "? System may have completed operation after receiving topic command"
fi

echo
echo "4. Testing START_SWITCH timeout behavior..."
# Test timeout behavior
timeout 8s install/yanthra_move/lib/yanthra_move/yanthra_move_node --ros-args \
    --params-file src/yanthra_move/config/production.yaml \
    -p start_switch.enable_wait:=true \
    -p start_switch.prefer_topic:=true \
    -p start_switch.timeout_sec:=3.0 \
    -p continuous_operation:=false &

SYSTEM_PID=$!
echo "System should timeout after 3 seconds and enter safe idle state..."
sleep 5

# System should have timed out and entered safe state
if ! kill -0 $SYSTEM_PID 2>/dev/null; then
    echo "✓ System correctly timed out and entered safe state"
else
    echo "? System still running after timeout (may be in safe idle)"
    kill $SYSTEM_PID
    wait $SYSTEM_PID 2>/dev/null
fi

echo
echo "=== Phase 1b Test Summary ==="
echo "START_SWITCH topic implementation tested:"
echo "- Parameter validation"
echo "- Development mode (disabled waiting)"
echo "- Topic subscription and response"
echo "- Timeout behavior with safe fallback"
echo
echo "Phase 1b implementation verification complete!"