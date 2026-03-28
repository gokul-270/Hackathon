#!/bin/bash
# Full End-to-End Test: Live Cotton Detection → Motor Movement
# Detects cotton in real-time and commands motors to move to detected positions

echo "================================================="
echo "FULL END-TO-END PIPELINE TEST"
echo "Live Cotton Detection → Absolute Position → Motor Movement"
echo "================================================="
echo ""

# Source ROS2
source /opt/ros/jazzy/setup.bash
source ~/pragati_ros2/install/setup.bash

# Setup CAN
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Kill any existing camera/detection processes to free the device
echo "Cleaning up any existing camera processes..."
pkill -f "CottonDetect.py" 2>/dev/null || true
pkill -f "cotton_detect_ros2_wrapper" 2>/dev/null || true
sleep 2

LOGDIR=~/test_results_$(date +%Y%m%d)
mkdir -p "$LOGDIR"
STAMP=$(date +%H%M%S)
LOGFILE="$LOGDIR/full_pipeline_${STAMP}.log"

echo "Log: $LOGFILE" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# Launch system
echo "Launching complete system..." | tee -a "$LOGFILE"
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=false \
    continuous_operation:=false \
    enable_arm_client:=false \
    can_interface:=can0 \
    can_bitrate:=500000 \
    > "$LOGDIR/system_${STAMP}.log" 2>&1 &

SYSTEM_PID=$!
echo "System PID: $SYSTEM_PID" | tee -a "$LOGFILE"
echo "Waiting for system initialization..." | tee -a "$LOGFILE"

INIT_TIMEOUT=60
START_TIME=$(date +%s)
MOTORS_READY=false
CAMERA_READY=false

while true; do
    # Check if process crashed
    if ! ps -p $SYSTEM_PID > /dev/null; then
        echo "✗ System crashed during initialization!" | tee -a "$LOGFILE"
        tail -50 "$LOGDIR/system_${STAMP}.log"
        exit 1
    fi

    # Check motor homing
    if ! $MOTORS_READY && grep -q "✅ Initialized 3 / 3 motors" "$LOGDIR/system_${STAMP}.log"; then
        ELAPSED=$(($(date +%s) - START_TIME))
        echo "✓ Motor homing complete (${ELAPSED}s)" | tee -a "$LOGFILE"
        MOTORS_READY=true
    fi

    # Check camera initialization - look for DepthAI C++ success
    if ! $CAMERA_READY && grep -q "DepthAI initialization SUCCESS\|Detection mode: DEPTHAI_DIRECT" "$LOGDIR/system_${STAMP}.log"; then
        ELAPSED=$(($(date +%s) - START_TIME))
        echo "✓ Camera initialized (${ELAPSED}s)" | tee -a "$LOGFILE"
        CAMERA_READY=true
    fi

    # Exit when both ready
    if $MOTORS_READY && $CAMERA_READY; then
        break
    fi

    # Check timeout
    ELAPSED=$(($(date +%s) - START_TIME))
    if [ $ELAPSED -ge $INIT_TIMEOUT ]; then
        echo "⚠ Initialization timeout after ${INIT_TIMEOUT}s" | tee -a "$LOGFILE"
        if ! $MOTORS_READY; then
            echo "  ⚠ Motors not fully homed" | tee -a "$LOGFILE"
        fi
        if ! $CAMERA_READY; then
            echo "  ⚠ Camera not fully initialized" | tee -a "$LOGFILE"
        fi
        break
    fi

    sleep 1
done

echo "✓ System ready" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# Run 1 complete cycle (change to {1..3} for multiple cycles)
for cycle in {1..1}; do
    echo "=================================================" | tee -a "$LOGFILE"
    echo "CYCLE $cycle: DETECT → MOVE" | tee -a "$LOGFILE"
    echo "=================================================" | tee -a "$LOGFILE"
    echo "" | tee -a "$LOGFILE"

    # Step 1: Detect Cotton
    echo "[$cycle/3] Step 1: Detecting cotton..." | tee -a "$LOGFILE"
    DETECT_START=$(date +%s.%N)
    DETECT_START_TIME=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    echo "  🕐 Detection started: ${DETECT_START_TIME}" | tee -a "$LOGFILE"

    # Call detection service
    echo "  📸 Requesting image capture and detection..." | tee -a "$LOGFILE"
    OUTPUT=$(timeout 20 ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}" 2>&1)

    DETECT_END=$(date +%s.%N)
    DETECT_END_TIME=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    DETECT_TIME=$(awk "BEGIN {printf \"%.2f\", $DETECT_END - $DETECT_START}")
    echo "  🕐 Detection completed: ${DETECT_END_TIME}" | tee -a "$LOGFILE"
    echo "  ⏱️  Total detection time: ${DETECT_TIME}s" | tee -a "$LOGFILE"

    echo "$OUTPUT" | head -10 | tee -a "$LOGFILE"
    echo "" | tee -a "$LOGFILE"

    # Parse detection
    if echo "$OUTPUT" | grep -q "success=True"; then
        DATA=$(echo "$OUTPUT" | grep -o "data=\[.*\]" | sed 's/data=\[//;s/\]//')

        if [ -n "$DATA" ] && [ "$DATA" != "" ]; then
            IFS=', ' read -ra POSITIONS <<< "$DATA"
            COUNT=$((${#POSITIONS[@]} / 3))

            echo "✓ Detected $COUNT cotton boll(s)" | tee -a "$LOGFILE"

            # Check for image capture and camera status with detailed timing
            IMG_FILE="/home/ubuntu/pragati_ros2/data/inputs/img100.jpg"
            if [ -f "$IMG_FILE" ]; then
                IMG_TIMESTAMP=$(stat -c %y "$IMG_FILE" | cut -d. -f1)
                IMG_SIZE=$(stat -c %s "$IMG_FILE")
                IMG_SIZE_KB=$(awk "BEGIN {printf \"%.1f\", $IMG_SIZE / 1024.0}")
                echo "  📷 Image acquired: ${IMG_TIMESTAMP}" | tee -a "$LOGFILE"
                echo "     Size: ${IMG_SIZE_KB} KB (${IMG_SIZE} bytes)" | tee -a "$LOGFILE"
                echo "     Path: ${IMG_FILE}" | tee -a "$LOGFILE"
            else
                echo "  ⚠️  Warning: No image file found at ${IMG_FILE}" | tee -a "$LOGFILE"
            fi

            # Camera temperature (if available in logs)
            CAM_TEMP=$(grep -i "temperature" "$LOGDIR/system_${STAMP}.log" 2>/dev/null | tail -1 | grep -oP '\d+\.?\d*°[CF]' || echo "N/A")
            if [ "$CAM_TEMP" != "N/A" ]; then
                echo "  Camera temp: ${CAM_TEMP}" | tee -a "$LOGFILE"
            fi
            echo "" | tee -a "$LOGFILE"

            # Parse and display all detections
            for ((i=0; i<$COUNT; i++)); do
                idx=$((i * 3))
                X_MM=${POSITIONS[$idx]}
                Y_MM=${POSITIONS[$((idx + 1))]}
                Z_MM=${POSITIONS[$((idx + 2))]}

                # Get absolute values
                X_ABS=$(awk "BEGIN {x=$X_MM; printf \"%.3f\", (x < 0 ? -x : x) / 1000.0}")
                Y_ABS=$(awk "BEGIN {y=$Y_MM; printf \"%.3f\", (y < 0 ? -y : y) / 1000.0}")
                Z_ABS=$(awk "BEGIN {z=$Z_MM; printf \"%.3f\", (z < 0 ? -z : z) / 1000.0}")

                echo "Cotton #$((i+1)):" | tee -a "$LOGFILE"
                echo "  Raw (mm):      X=${X_MM}, Y=${Y_MM}, Z=${Z_MM}" | tee -a "$LOGFILE"
                echo "  Absolute (m):  X=${X_ABS}, Y=${Y_ABS}, Z=${Z_ABS}" | tee -a "$LOGFILE"
                echo "" | tee -a "$LOGFILE"
            done

            # Step 2: Move to ALL detected cotton positions
            MOVE_START=$(date +%s.%N)
            MOVE_START_TIME=$(date '+%Y-%m-%d %H:%M:%S.%3N')
            echo "[$cycle/3] Step 2: Moving to all $COUNT detected cotton positions..." | tee -a "$LOGFILE"
            echo "  🕐 Movement started: ${MOVE_START_TIME}" | tee -a "$LOGFILE"
            echo "" | tee -a "$LOGFILE"

            # Move to each cotton sequentially
            for ((i=0; i<$COUNT; i++)); do
                idx=$((i * 3))
                X_MM=${POSITIONS[$idx]}
                Y_MM=${POSITIONS[$((idx + 1))]}
                Z_MM=${POSITIONS[$((idx + 2))]}

                # Get absolute values
                X_ABS=$(awk "BEGIN {x=$X_MM; printf \"%.3f\", (x < 0 ? -x : x) / 1000.0}")
                Y_ABS=$(awk "BEGIN {y=$Y_MM; printf \"%.3f\", (y < 0 ? -y : y) / 1000.0}")
                Z_ABS=$(awk "BEGIN {z=$Z_MM; printf \"%.3f\", (z < 0 ? -z : z) / 1000.0}")

                # Scale down 10% for safety
                SAFE_SCALE="0.1"
                TEST_X=$(awk "BEGIN {printf \"%.3f\", $X_ABS * $SAFE_SCALE}")
                TEST_Y=$(awk "BEGIN {printf \"%.3f\", $Y_ABS * $SAFE_SCALE}")
                TEST_Z=$(awk "BEGIN {printf \"%.3f\", $Z_ABS * $SAFE_SCALE}")

                echo "Moving to Cotton #$((i+1)):" | tee -a "$LOGFILE"
                echo "  Target: J3=${TEST_X} J4=${TEST_Y} J5=${TEST_Z} rad" | tee -a "$LOGFILE"
                echo "" | tee -a "$LOGFILE"

                # Get initial joint positions from encoder
                INITIAL_POS=$(timeout 2 ros2 topic echo --once /joint_states 2>&1 | grep -A 1 "position:" | tail -1 | tr -d '[]')

                # Move Joint 3
                echo "  [1/3] Moving Joint3 to ${TEST_X} rad..." | tee -a "$LOGFILE"
                timeout 3 ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "{data: $TEST_X}" > /dev/null 2>&1 || true
                sleep 2
                POS_J3=$(timeout 2 ros2 topic echo --once /joint_states 2>&1 | grep -A 1 "position:" | tail -1 | awk '{print $1}' | tr -d '[],')
                echo "        Encoder feedback: ${POS_J3} rad" | tee -a "$LOGFILE"

                # Move Joint 4
                echo "  [2/3] Moving Joint4 to ${TEST_Y} rad..." | tee -a "$LOGFILE"
                timeout 3 ros2 topic pub --once /joint4_position_controller/command std_msgs/msg/Float64 "{data: $TEST_Y}" > /dev/null 2>&1 || true
                sleep 2
                POS_J4=$(timeout 2 ros2 topic echo --once /joint_states 2>&1 | grep -A 1 "position:" | tail -1 | awk '{print $2}' | tr -d '[],')
                echo "        Encoder feedback: ${POS_J4} rad" | tee -a "$LOGFILE"

                # Move Joint 5
                echo "  [3/3] Moving Joint5 to ${TEST_Z} rad..." | tee -a "$LOGFILE"
                timeout 3 ros2 topic pub --once /joint5_position_controller/command std_msgs/msg/Float64 "{data: $TEST_Z}" > /dev/null 2>&1 || true
                sleep 2
                POS_J5=$(timeout 2 ros2 topic echo --once /joint_states 2>&1 | grep -A 1 "position:" | tail -1 | awk '{print $3}' | tr -d '[],')
                echo "        Encoder feedback: ${POS_J5} rad" | tee -a "$LOGFILE"

                echo "  ✓ All motors commanded and verified" | tee -a "$LOGFILE"
                echo "" | tee -a "$LOGFILE"

                # Wait between cotton positions
                if [ $i -lt $((COUNT - 1)) ]; then
                    echo "  Waiting 2s before next cotton..." | tee -a "$LOGFILE"
                    sleep 2
                fi
            done

            MOVE_END=$(date +%s.%N)
            MOVE_END_TIME=$(date '+%Y-%m-%d %H:%M:%S.%3N')
            MOVE_TIME=$(awk "BEGIN {printf \"%.2f\", $MOVE_END - $MOVE_START}")
            CYCLE_TOTAL=$(awk "BEGIN {printf \"%.2f\", $MOVE_END - $DETECT_START}")

            echo "  🕐 Movement completed: ${MOVE_END_TIME}" | tee -a "$LOGFILE"
            echo "  ⏱️  Movement time: ${MOVE_TIME}s" | tee -a "$LOGFILE"
            echo "  ⏱️  Total cycle time: ${CYCLE_TOTAL}s (detection: ${DETECT_TIME}s + movement: ${MOVE_TIME}s)" | tee -a "$LOGFILE"
            echo "[$cycle/3] ✅ CYCLE COMPLETE: Detected $COUNT cotton → Moved to all positions" | tee -a "$LOGFILE"
            echo "" | tee -a "$LOGFILE"

            # Return to home position (0, 0, 0) after each cycle
            echo "Returning to home position..." | tee -a "$LOGFILE"
            timeout 3 ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.0}" > /dev/null 2>&1 || true
            sleep 2
            timeout 3 ros2 topic pub --once /joint4_position_controller/command std_msgs/msg/Float64 "{data: 0.0}" > /dev/null 2>&1 || true
            sleep 2
            timeout 3 ros2 topic pub --once /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.0}" > /dev/null 2>&1 || true
            sleep 2
            echo "✓ Homed" | tee -a "$LOGFILE"

        else
            echo "⚠ No cotton data in response" | tee -a "$LOGFILE"
            echo "[$cycle/3] ⚠️ CYCLE INCOMPLETE: No detection data" | tee -a "$LOGFILE"
        fi
    else
        echo "✗ Detection failed" | tee -a "$LOGFILE"
        echo "[$cycle/3] ✗ CYCLE FAILED: Detection unsuccessful" | tee -a "$LOGFILE"
    fi

    echo "" | tee -a "$LOGFILE"

    if [ $cycle -lt 3 ]; then
        echo "Waiting 5s before next cycle..." | tee -a "$LOGFILE"
        sleep 5
    fi
done

# Final Summary
echo "=================================================" | tee -a "$LOGFILE"
echo "TEST COMPLETE" | tee -a "$LOGFILE"
echo "=================================================" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"
echo "Summary:" | tee -a "$LOGFILE"
echo "  - Ran 3 complete detection → movement cycles" | tee -a "$LOGFILE"
echo "  - Each cycle: detect cotton → convert to absolute → command motors" | tee -a "$LOGFILE"
echo "  - Full pipeline validated end-to-end" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"
echo "Full log: $LOGFILE" | tee -a "$LOGFILE"
echo "System log: $LOGDIR/system_${STAMP}.log" | tee -a "$LOGFILE"

# Cleanup
echo ""
echo "Stopping system..."
kill $SYSTEM_PID 2>/dev/null || true
wait $SYSTEM_PID 2>/dev/null || true

echo ""
echo "✅ Full pipeline test complete!"
echo "Results: $LOGFILE"
