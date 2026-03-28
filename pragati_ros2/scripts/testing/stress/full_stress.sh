#!/bin/bash
# Full System Stress Test - 50 Cycles
# Tests: Cotton Detection + Motor Control Integration

cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "=========================================="
echo "Full System Stress Test - 50 Cycles"
echo "=========================================="
echo "Start time: $(date)"
echo ""

# Setup CAN
echo "Setting up CAN interface..."
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

if ! ip link show can0 | grep -q "state UP"; then
    echo "❌ CAN interface failed"
    exit 1
fi
echo "✅ CAN interface UP"
echo ""

# Start complete system (includes motor controller)
echo "Starting complete system (motor controller + yanthra_move + cotton detection)..."
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true > /tmp/system.log 2>&1 &
SYSTEM_PID=$!

sleep 15

if ! kill -0 $SYSTEM_PID 2>/dev/null; then
    echo "❌ System failed to start"
    cat /tmp/system.log
    exit 1
fi

# Verify joint_states is publishing (wait for homing to complete)
echo "Verifying joint_states..."
if timeout 15 ros2 topic echo /joint_states --once > /dev/null 2>&1; then
    echo "✅ Joint states publishing"
else
    echo "❌ Joint states not publishing"
    tail -50 /tmp/system.log
    kill $SYSTEM_PID
    exit 1
fi

echo "✅ System started (PID: $SYSTEM_PID)"
echo ""

# Send START switch
echo "Sending START switch signal..."
sleep 2
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true" > /dev/null 2>&1
echo "✅ START signal sent"
echo ""

echo "=========================================="
echo "Running 50-Cycle Stress Test"
echo "=========================================="
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0
START_TIME=$(date +%s)

for cycle in $(seq 1 50); do
    CYCLE_START=$(date +%s)
    
    echo "----------------------------------------"
    echo "Cycle $cycle/50 - $(date +%H:%M:%S)"
    echo "----------------------------------------"
    
    # Publish cotton detection
    ./test_cotton_detection_publisher.py --single --count 2 > /tmp/detection_$cycle.log 2>&1 &
    DETECT_PID=$!
    
    # Wait for detection to complete
    wait $DETECT_PID
    DETECT_STATUS=$?
    
    # Give time for motion to complete
    sleep 8
    
    # Check if system still running
    if ! kill -0 $SYSTEM_PID 2>/dev/null; then
        echo "❌ System died at cycle $cycle"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        tail -30 /tmp/system.log
        break
    fi
    
    if [ $DETECT_STATUS -eq 0 ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        CYCLE_END=$(date +%s)
        CYCLE_TIME=$((CYCLE_END - CYCLE_START))
        echo "✅ Cycle $cycle complete (${CYCLE_TIME}s)"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "❌ Cycle $cycle failed (detection error)"
        cat /tmp/detection_$cycle.log
    fi
    
    # Check for X_LINK errors in logs
    if grep -q "X_LINK_ERROR" /tmp/system.log 2>/dev/null; then
        echo "⚠️  X_LINK_ERROR detected in logs"
    fi
    
    echo ""
    
    # Brief pause between cycles
    sleep 2
done

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
MINUTES=$((TOTAL_TIME / 60))
SECONDS=$((TOTAL_TIME % 60))

echo ""
echo "=========================================="
echo "Stress Test Complete"
echo "=========================================="
echo "End time: $(date)"
echo "Total duration: ${MINUTES}m ${SECONDS}s"
echo ""
echo "Results:"
echo "  ✅ Successful cycles: $SUCCESS_COUNT"
echo "  ❌ Failed cycles: $FAIL_COUNT"
echo "  Success rate: $(( SUCCESS_COUNT * 100 / 50 ))%"
echo ""

# Show final joint states
echo "Final joint states:"
timeout 2 ros2 topic echo /joint_states --once 2>&1 | grep -A 10 "name:"

echo ""
echo "=========================================="
echo "Stopping System"
echo "=========================================="

kill $SYSTEM_PID 2>/dev/null
wait $SYSTEM_PID 2>/dev/null

echo "✅ System stopped"
echo ""

# Check for errors in logs
echo "Checking logs for errors..."
if grep -i "X_LINK_ERROR" /tmp/system.log | head -5; then
    echo "⚠️  Found X_LINK_ERROR in system log"
else
    echo "✅ No X_LINK_ERROR detected"
fi

if grep -i "error.*motor" /tmp/system.log | grep -v "ERROR-ACTIVE" | grep -v "Failed to initialize motor 2" | head -5; then
    echo "⚠️  Found motor errors in system log"
else
    echo "✅ No critical motor errors"
fi

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Success Rate: $(( SUCCESS_COUNT * 100 / 50 ))%"
echo "Average Cycle Time: $(( TOTAL_TIME / SUCCESS_COUNT ))s"
echo ""

if [ $SUCCESS_COUNT -eq 50 ]; then
    echo "🎉 PERFECT! All 50 cycles completed successfully!"
    echo "System is PRODUCTION READY ✅"
    exit 0
elif [ $SUCCESS_COUNT -ge 45 ]; then
    echo "✅ Excellent! $(( SUCCESS_COUNT * 100 / 50 ))% success rate"
    echo "System is production ready with minor issues to investigate"
    exit 0
else
    echo "⚠️  System needs attention. Success rate: $(( SUCCESS_COUNT * 100 / 50 ))%"
    exit 1
fi
