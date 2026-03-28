#!/bin/bash
# Comprehensive MG6010 CAN Motor Test
# Tests all motor functions: status, angles, on/off, position, velocity
# Date: October 13, 2025 (relocated to scripts/validation/motor)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${PRAGATI_WORKSPACE:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SETUP_FILE="${WORKSPACE_ROOT}/install/setup.bash"

if [[ ! -f "$SETUP_FILE" ]]; then
    echo "✗ ROS2 workspace not built. Expected setup file at: $SETUP_FILE"
    exit 1
fi

source "$SETUP_FILE"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

printf "${CYAN}\n"
printf "╔════════════════════════════════════════════════════════════════╗\n"
printf "║     COMPREHENSIVE MG6010 CAN MOTOR TEST - October 2025        ║\n"
printf "╚════════════════════════════════════════════════════════════════╝\n"
printf "${NC}"

PASSED=0
FAILED=0
TOTAL=0
declare -a TEST_RESULTS

log_test() {
    local test_name="$1"
    local result="$2"
    TOTAL=$((TOTAL + 1))

    if [[ "$result" == "PASS" ]]; then
        PASSED=$((PASSED + 1))
        printf "${GREEN}✓ %s - PASSED${NC}\n" "$test_name"
        TEST_RESULTS+=("PASS: $test_name")
    else
        FAILED=$((FAILED + 1))
        printf "${RED}✗ %s - FAILED${NC}\n" "$test_name"
        TEST_RESULTS+=("FAIL: $test_name")
    fi
}

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 1: CAN Interface Status${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

CAN_STATE=$(ip -details link show can0 | grep "can " | grep -oP 'state \K\S+' 2>/dev/null || echo "UNKNOWN")
printf "  CAN State: %s\n" "$CAN_STATE"

if [[ "$CAN_STATE" == "ERROR-ACTIVE" ]]; then
    log_test "CAN Interface State" "PASS"
else
    log_test "CAN Interface State" "FAIL"
    printf "${RED}ERROR: CAN not in ERROR-ACTIVE state. Cannot proceed.${NC}\n"
    exit 1
fi

BITRATE=$(ip -details link show can0 | grep -oP 'bitrate \K\d+')
printf "  Bitrate: %s bps\n" "$BITRATE"

if [[ "$BITRATE" == "500000" ]]; then
    log_test "CAN Bitrate Configuration" "PASS"
else
    log_test "CAN Bitrate Configuration" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 2: Motor Status Reading${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

STATUS_OUTPUT=$(ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=1 -p mode:=status 2>&1)

if echo "$STATUS_OUTPUT" | grep -q "Test completed successfully"; then
    log_test "Motor Status Reading" "PASS"
    echo "$STATUS_OUTPUT" | grep -E "Temperature|Voltage|Error|Speed|torque"
else
    log_test "Motor Status Reading" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 3: Encoder Angle Reading${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

ANGLE_OUTPUT=$(ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=1 -p mode:=angle 2>&1)

if echo "$ANGLE_OUTPUT" | grep -q "Test completed successfully"; then
    log_test "Encoder Angle Reading" "PASS"
    echo "$ANGLE_OUTPUT" | grep -E "Multi-turn|Single-turn"
else
    log_test "Encoder Angle Reading" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 4: Motor ON/OFF Control${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

ONOFF_OUTPUT=$(ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=1 -p mode:=on_off 2>&1)

if echo "$ONOFF_OUTPUT" | grep -q "Test completed successfully"; then
    log_test "Motor ON/OFF Control" "PASS"
    echo "$ONOFF_OUTPUT" | grep -E "Motor ON|Motor OFF"
else
    log_test "Motor ON/OFF Control" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 5: Position Control (Movement Test)${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

printf "Testing position control with actual movement...\n"
printf "Target: +1.0 radians (~57.3 degrees)\n\n"

POSITION_OUTPUT=$(timeout 10s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=1 \
  -p mode:=position -p position_rad:=1.0 2>&1)

if echo "$POSITION_OUTPUT" | grep -q "Test completed successfully"; then
    log_test "Position Control" "PASS"
    echo "$POSITION_OUTPUT" | grep -E "Target position|Position command|Current angle"
else
    log_test "Position Control" "FAIL"
fi

printf "\nMoving to different position...\n"
printf "Target: -0.5 radians (~-28.6 degrees)\n\n"

POSITION_OUTPUT2=$(timeout 10s ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=1 \
  -p mode:=position -p position_rad:=-0.5 2>&1)

if echo "$POSITION_OUTPUT2" | grep -q "Test completed successfully"; then
    log_test "Position Control (Negative)" "PASS"
    echo "$POSITION_OUTPUT2" | grep -E "Target position|Current angle"
else
    log_test "Position Control (Negative)" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 6: Velocity Control (Movement Test)${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

printf "Testing velocity control with actual rotation...\n"
printf "Target: 5.0 rad/s (~286 deg/s) for 5 seconds\n\n"

VELOCITY_OUTPUT=$(timeout 8 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 -p baud_rate:=500000 -p node_id:=1 \
  -p mode:=velocity -p target_velocity:=5.0 2>&1 || echo "Test completed (timed out as expected)")

if echo "$VELOCITY_OUTPUT" | grep -q "Velocity command sent successfully\|Test completed successfully"; then
    log_test "Velocity Control" "PASS"
    echo "$VELOCITY_OUTPUT" | grep -E "speed=|torque="
else
    log_test "Velocity Control" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 7: CAN Communication Statistics${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

printf "Final CAN interface statistics:\n"
ip -s link show can0 | grep -A 2 "RX:\|TX:"

RX_PACKETS=$(ip -s link show can0 | grep "RX:" -A 1 | tail -1 | awk '{print $2}')
TX_PACKETS=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $2}')
TX_ERRORS=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $3}')

printf "\nCommunication Summary:\n"
printf "  RX Packets: %s\n" "$RX_PACKETS"
printf "  TX Packets: %s\n" "$TX_PACKETS"
printf "  TX Errors: %s\n" "$TX_ERRORS"

if [[ "$RX_PACKETS" -gt 0 && "$TX_ERRORS" == "0" ]]; then
    log_test "CAN Communication Health" "PASS"
else
    log_test "CAN Communication Health" "FAIL"
fi

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${CYAN}TEST 8: Raw CAN Traffic Test${NC}\n"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n\n"

printf "Sending raw CAN commands and monitoring traffic...\n"

LOG_FILE="/tmp/comprehensive_can_test.log"

timeout 2s candump can0 > "$LOG_FILE" 2>&1 &
CANDUMP_PID=$!
sleep 0.5

printf "  - Motor OFF\n"
cansend can0 141#8000000000000000
sleep 0.2

printf "  - Motor ON\n"
cansend can0 141#8800000000000000
sleep 0.2

printf "  - Read Status\n"
cansend can0 141#9A00000000000000
sleep 0.2

kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

TRAFFIC_LINES=$(wc -l < "$LOG_FILE")
printf "\nCAN Traffic captured: %s messages\n" "$TRAFFIC_LINES"

if [[ "$TRAFFIC_LINES" -gt 3 ]]; then
    log_test "Raw CAN Communication" "PASS"
    printf "\nTraffic sample:\n"
    head -10 "$LOG_FILE"
else
    log_test "Raw CAN Communication" "FAIL"
fi

printf "\n${CYAN}"
printf "╔════════════════════════════════════════════════════════════════╗\n"
printf "║                      TEST SUMMARY                              ║\n"
printf "╚════════════════════════════════════════════════════════════════╝\n"
printf "${NC}\n"

for result in "${TEST_RESULTS[@]}"; do
    if [[ $result == PASS* ]]; then
        printf "${GREEN}✓ %s${NC}\n" "${result#PASS: }"
    else
        printf "${RED}✗ %s${NC}\n" "${result#FAIL: }"
    fi
done

printf "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
printf "Total Tests: %s\n" "$TOTAL"
printf "${GREEN}Passed: %s${NC}\n" "$PASSED"
printf "${RED}Failed: %s${NC}\n" "$FAILED"
printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"

SUCCESS_RATE=$((PASSED * 100 / TOTAL))
printf "\nSuccess Rate: %s%%\n" "$SUCCESS_RATE"

if [[ "$FAILED" -eq 0 ]]; then
    printf "\n${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}\n"
    printf "${GREEN}║              🎉 ALL TESTS PASSED! 🎉                          ║${NC}\n"
    printf "${GREEN}║    CAN Communication is FULLY OPERATIONAL                      ║${NC}\n"
    printf "${GREEN}║    Motor Control is VERIFIED                                   ║${NC}\n"
    printf "${GREEN}║    System is READY for Production                              ║${NC}\n"
    printf "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}\n"
    exit 0
else
    printf "\n${YELLOW}⚠ Some tests failed. Review the output above for details.${NC}\n"
    exit 1
fi
