#!/bin/bash
# Cotton Detection Continuous Loop Test
# Runs detection for fixed number of cycles with detailed terminal output
#
# Usage: ./loop_test.sh [NUM_CYCLES]
# Example: ./loop_test.sh 10

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Cotton Detection Continuous Loop Test${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo ""

# Get workspace root directory (3 levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Source ROS2
source /opt/ros/jazzy/setup.bash

if [ -f "$WORKSPACE_ROOT/install/setup.bash" ]; then
    source "$WORKSPACE_ROOT/install/setup.bash"
    echo -e "${GREEN}✓ Workspace: $WORKSPACE_ROOT${NC}"
else
    echo -e "${RED}Error: Cannot find $WORKSPACE_ROOT/install/setup.bash${NC}"
    echo "Please build the workspace first: colcon build"
    exit 1
fi

# Number of detection cycles
NUM_CYCLES=${1:-10}
echo -e "${BLUE}Configuration:${NC}"
echo "  • Cycles: $NUM_CYCLES"
echo "  • Delay between cycles: 1s"
echo "  • Real-time terminal output: Yes"
echo ""

# Start cotton detection node in background
echo -e "${YELLOW}Starting cotton detection node...${NC}"
pkill -9 -f cotton_detection_node >/dev/null 2>&1 || true
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py > /tmp/cotton_detect_node.log 2>&1 &
NODE_PID=$!
echo -e "${GREEN}✓ Node started (PID: $NODE_PID)${NC}"

# Wait for service to be available
echo -e "${YELLOW}Waiting for detection service...${NC}"
for i in {1..30}; do
    if ros2 service list 2>/dev/null | grep -q '/cotton_detection/detect'; then
        echo -e "${GREEN}✓ Service ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Service timeout${NC}"
        kill $NODE_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done
echo ""

# Statistics tracking
TOTAL_DETECTIONS=0
SUCCESSFUL_CYCLES=0
FAILED_CYCLES=0
TOTAL_TIME=0
MAX_TIME=0
MIN_TIME=999999

echo -e "${CYAN}Starting detection cycles...${NC}"
echo ""

# Run detection cycles
for cycle in $(seq 1 $NUM_CYCLES); do
    echo -e "${CYAN}═════════════════════════════════════════${NC}"
    echo -e "${CYAN}  CYCLE $cycle/$NUM_CYCLES${NC}"
    echo -e "${CYAN}═════════════════════════════════════════${NC}"

    # Trigger detection
    CYCLE_START=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}⏱  Started: ${CYCLE_START}${NC}"

    DETECT_START=$(date +%s.%N)
    OUTPUT=$(timeout 15 ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}" 2>&1 || echo "TIMEOUT")
    DETECT_END=$(date +%s.%N)
    DETECT_TIME=$(awk "BEGIN {printf \"%.3f\", $DETECT_END - $DETECT_START}")

    # Update time statistics
    TOTAL_TIME=$(awk "BEGIN {printf \"%.3f\", $TOTAL_TIME + $DETECT_TIME}")
    if awk "BEGIN {exit !($DETECT_TIME > $MAX_TIME)}"; then
        MAX_TIME=$DETECT_TIME
    fi
    if awk "BEGIN {exit !($DETECT_TIME < $MIN_TIME)}"; then
        MIN_TIME=$DETECT_TIME
    fi

    echo -e "${BLUE}⏱  Detection time: ${DETECT_TIME}s${NC}"
    echo ""

    # Parse and display results
    if echo "$OUTPUT" | grep -q "success.*True"; then
        SUCCESSFUL_CYCLES=$((SUCCESSFUL_CYCLES + 1))

        DATA=$(echo "$OUTPUT" | grep -o "data=\[.*\]" | sed 's/data=\[//;s/\]//' || echo "")

        if [ -n "$DATA" ] && [ "$DATA" != "" ]; then
            IFS=', ' read -ra POSITIONS <<< "$DATA"
            COUNT=$((${#POSITIONS[@]} / 3))
            TOTAL_DETECTIONS=$((TOTAL_DETECTIONS + COUNT))

            echo -e "${GREEN}✓ SUCCESS: Detected $COUNT cotton boll(s)${NC}"
            echo ""

            # Display each detection with color coding
            for ((i=0; i<$COUNT; i++)); do
                idx=$((i * 3))
                X_MM=${POSITIONS[$idx]}
                Y_MM=${POSITIONS[$((idx + 1))]}
                Z_MM=${POSITIONS[$((idx + 2))]}

                # Convert to meters
                X_M=$(awk "BEGIN {printf \"%.3f\", $X_MM / 1000.0}")
                Y_M=$(awk "BEGIN {printf \"%.3f\", $Y_MM / 1000.0}")
                Z_M=$(awk "BEGIN {printf \"%.3f\", $Z_MM / 1000.0}")

                echo -e "  ${YELLOW}Cotton #$((i+1)):${NC}"
                echo -e "    ${CYAN}X:${NC} ${X_MM} mm (${X_M} m)"
                echo -e "    ${CYAN}Y:${NC} ${Y_MM} mm (${Y_M} m)"
                echo -e "    ${CYAN}Z:${NC} ${Z_MM} mm (${Z_M} m)"
            done
        else
            echo -e "${YELLOW}⚠  No cotton detected (empty data)${NC}"
        fi
    else
        FAILED_CYCLES=$((FAILED_CYCLES + 1))
        echo -e "${RED}✗ FAILED: Detection service call failed${NC}"
        if echo "$OUTPUT" | grep -q "TIMEOUT"; then
            echo -e "${RED}  Reason: Service timeout (>15s)${NC}"
        else
            echo "  Output: $(echo "$OUTPUT" | head -2)"
        fi
    fi

    echo ""

    # Progress indicator
    PROGRESS=$((cycle * 100 / NUM_CYCLES))
    echo -e "${BLUE}Progress: ${PROGRESS}% (${cycle}/${NUM_CYCLES} cycles)${NC}"
    echo ""

    # Wait between cycles
    if [ $cycle -lt $NUM_CYCLES ]; then
        echo -e "${CYAN}⏸  Waiting 1s before next cycle...${NC}"
        echo ""
        sleep 1
    fi
done

# Calculate statistics
AVG_TIME=$(awk "BEGIN {printf \"%.3f\", $TOTAL_TIME / $NUM_CYCLES}")
SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", ($SUCCESSFUL_CYCLES * 100.0) / $NUM_CYCLES}")

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${CYAN}  TEST COMPLETE${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📊 Statistics:${NC}"
echo -e "${CYAN}─────────────────────────────────────────────${NC}"
echo -e "  Total Cycles:        ${YELLOW}${NUM_CYCLES}${NC}"
echo -e "  Successful:          ${GREEN}${SUCCESSFUL_CYCLES}${NC}"
echo -e "  Failed:              ${RED}${FAILED_CYCLES}${NC}"
echo -e "  Success Rate:        ${GREEN}${SUCCESS_RATE}%${NC}"
echo ""
echo -e "${BLUE}🎯 Detection Results:${NC}"
echo -e "${CYAN}─────────────────────────────────────────────${NC}"
echo -e "  Total Cotton Bolls:  ${GREEN}${TOTAL_DETECTIONS}${NC}"
echo -e "  Avg per Cycle:       ${YELLOW}$(awk "BEGIN {printf \"%.1f\", $TOTAL_DETECTIONS / $NUM_CYCLES}")${NC}"
echo ""
echo -e "${BLUE}⏱  Timing:${NC}"
echo -e "${CYAN}─────────────────────────────────────────────${NC}"
echo -e "  Total Time:          ${YELLOW}${TOTAL_TIME}s${NC}"
echo -e "  Average Time:        ${YELLOW}${AVG_TIME}s${NC}"
echo -e "  Min Time:            ${GREEN}${MIN_TIME}s${NC}"
echo -e "  Max Time:            ${RED}${MAX_TIME}s${NC}"
echo ""

if [ $FAILED_CYCLES -eq 0 ]; then
    echo -e "${GREEN}✅ All cycles completed successfully!${NC}"
else
    echo -e "${YELLOW}⚠️  $FAILED_CYCLES cycle(s) failed - check logs${NC}"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"

# Cleanup
echo ""
echo -e "${YELLOW}Cleaning up...${NC}"
kill $NODE_PID 2>/dev/null || true
sleep 1
pkill -9 -f cotton_detection_node >/dev/null 2>&1 || true
echo -e "${GREEN}✓ Cleanup complete${NC}"

echo ""
echo -e "${BLUE}📄 Node log: /tmp/cotton_detect_node.log${NC}"
echo ""
