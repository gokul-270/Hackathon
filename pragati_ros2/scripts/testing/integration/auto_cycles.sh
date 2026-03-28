#!/bin/bash
# Automated Continuous Test - Runs N detection+movement cycles automatically
#
# Usage: ./auto_test_cycles.sh [NUM_CYCLES]
# Example: ./auto_test_cycles.sh 10    # Run 10 cycles

set -e

NUM_CYCLES=${1:-5}  # Default to 5 cycles if not specified

echo "=========================================="
echo "  Automated Continuous Test"
echo "  Running $NUM_CYCLES cycles"
echo "=========================================="
echo ""

source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "📊 Test Configuration:"
echo "   - Cycles: $NUM_CYCLES"
echo "   - Cotton Detection: Automatic (before each cycle)"
echo "   - START Switch: Automatic (after each detection)"
echo ""

# Function to trigger cotton detection
trigger_detection() {
    local cycle=$1
    echo ""
    echo "[$cycle/$NUM_CYCLES] 📷 Triggering cotton detection..."

    # Call detection service and capture result
    RESULT=$(timeout 15 ros2 service call /cotton_detection/detect \
        cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}" \
        2>&1 || echo "TIMEOUT")

    # Extract detection count from result
    if echo "$RESULT" | grep -q "success.*True"; then
        DETECTION_COUNT=$(echo "$RESULT" | grep -oP 'data=\[\K[^\]]*' | tr ',' '\n' | wc -l)
        DETECTION_COUNT=$((DETECTION_COUNT / 3))  # Divide by 3 (x,y,z triplets)
        echo "   ✅ Detection complete: $DETECTION_COUNT cotton(s) found"
        return 0
    else
        echo "   ⚠️  Detection failed or timeout"
        return 1
    fi
}

# Function to send START signal
send_start_signal() {
    local cycle=$1
    echo "[$cycle/$NUM_CYCLES] 🚀 Sending START signal..."
    ros2 topic pub --once /start_switch/command std_msgs/Bool "{data: true}" >/dev/null 2>&1
    echo "   ✅ START signal sent"
}

# Function to wait for cycle completion
wait_for_cycle() {
    local cycle=$1
    local timeout=$2
    echo "[$cycle/$NUM_CYCLES] ⏳ Waiting for cycle completion (max ${timeout}s)..."

    # Monitor yanthra_move for "Waiting for START_SWITCH" message
    local start_time=$(date +%s)
    local found=false

    while [ $(($(date +%s) - start_time)) -lt $timeout ]; do
        # Check if yanthra_move is back to waiting
        if ros2 topic echo /start_switch/command --once --timeout 0.1 >/dev/null 2>&1; then
            # Just a delay to ensure cycle completes
            sleep 1.5
            found=true
            break
        fi
        sleep 0.2
    done

    if [ "$found" = true ]; then
        echo "   ✅ Cycle completed"
        return 0
    else
        echo "   ⚠️  Cycle timeout"
        return 1
    fi
}

echo "🚀 Starting automated test sequence..."
echo ""
sleep 2

SUCCESSFUL_CYCLES=0
FAILED_CYCLES=0
START_TIME=$(date +%s)

for ((i=1; i<=NUM_CYCLES; i++)); do
    echo "=========================================="
    echo "  CYCLE $i / $NUM_CYCLES"
    echo "=========================================="

    # Step 1: Trigger detection
    if trigger_detection $i; then
        # Step 2: Send START signal
        send_start_signal $i

        # Step 3: Wait for cycle to complete
        if wait_for_cycle $i 10; then
            ((SUCCESSFUL_CYCLES++))
        else
            ((FAILED_CYCLES++))
        fi
    else
        ((FAILED_CYCLES++))
    fi

    # Inter-cycle delay
    if [ $i -lt $NUM_CYCLES ]; then
        echo ""
        echo "[$i/$NUM_CYCLES] 💤 Inter-cycle delay (5s) - allowing motors to settle..."
        sleep 5
    fi
    echo ""
done

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

echo "=========================================="
echo "  TEST COMPLETE"
echo "=========================================="
echo ""
echo "📊 Results Summary:"
echo "   - Total Cycles: $NUM_CYCLES"
echo "   - Successful: $SUCCESSFUL_CYCLES"
echo "   - Failed: $FAILED_CYCLES"
echo "   - Total Time: ${TOTAL_TIME}s"
echo "   - Avg Time/Cycle: $((TOTAL_TIME / NUM_CYCLES))s"
echo ""

if [ $FAILED_CYCLES -eq 0 ]; then
    echo "✅ All cycles completed successfully!"
    exit 0
else
    echo "⚠️  Some cycles failed. Check logs for details."
    exit 1
fi
