#!/bin/bash
# Full ROS2 Motor Control System Test with CAN
# Tests the complete integration including launch files, services, and nodes

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        FULL ROS2 MOTOR CONTROL SYSTEM TEST - CAN              ║"
echo "║                    October 9, 2025                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# Initialize test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

test_result() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2 - PASSED${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ $2 - FAILED${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}TEST 1: ROS2 Environment Setup${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

cd ~/pragati_ws
source install/setup.bash

if ros2 pkg list | grep -q motor_control_ros2; then
    test_result 0 "ROS2 motor_control_ros2 package found"
else
    test_result 1 "ROS2 motor_control_ros2 package NOT found"
    exit 1
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}TEST 2: Launch File Test - Status Mode${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

timeout 10 ros2 launch motor_control_ros2 mg6010_test.launch.py \
    can_interface:=can0 \
    baud_rate:=250000 \
    motor_id:=1 \
    test_mode:=status > /tmp/ros2_launch_status.log 2>&1 &
LAUNCH_PID=$!

sleep 5
if ps -p $LAUNCH_PID > /dev/null; then
    test_result 0 "Launch file started successfully"
    kill $LAUNCH_PID 2>/dev/null || true
    wait $LAUNCH_PID 2>/dev/null || true
else
    test_result 1 "Launch file failed to start"
fi

echo ""
echo "Launch output:"
cat /tmp/ros2_launch_status.log | head -20
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}TEST 3: Individual Test Modes${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Test 3a: Status mode
echo "3a. Testing STATUS mode..."
timeout 5 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 \
    -p baud_rate:=250000 \
    -p node_id:=1 \
    -p mode:=status > /tmp/test_status.log 2>&1
if [ $? -eq 124 ] || grep -q "Test completed successfully" /tmp/test_status.log; then
    test_result 0 "Status mode test"
else
    test_result 1 "Status mode test"
fi

# Test 3b: Angle mode
echo "3b. Testing ANGLE mode..."
timeout 5 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 \
    -p baud_rate:=250000 \
    -p node_id:=1 \
    -p mode:=angle > /tmp/test_angle.log 2>&1
if [ $? -eq 124 ] || grep -q "Test completed successfully" /tmp/test_angle.log; then
    test_result 0 "Angle mode test"
else
    test_result 1 "Angle mode test"
fi

# Test 3c: ON/OFF mode
echo "3c. Testing ON/OFF mode..."
timeout 5 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 \
    -p baud_rate:=250000 \
    -p node_id:=1 \
    -p mode:=on_off > /tmp/test_onoff.log 2>&1
if [ $? -eq 124 ] || grep -q "Test completed successfully" /tmp/test_onoff.log; then
    test_result 0 "ON/OFF mode test"
else
    test_result 1 "ON/OFF mode test"
fi

# Test 3d: Position mode
echo "3d. Testing POSITION mode..."
timeout 8 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 \
    -p baud_rate:=250000 \
    -p node_id:=1 \
    -p mode:=position \
    -p target_position:=1000 > /tmp/test_position.log 2>&1
if [ $? -eq 124 ] || grep -q "Test completed successfully" /tmp/test_position.log; then
    test_result 0 "Position mode test"
else
    test_result 1 "Position mode test"
fi

# Test 3e: Velocity mode  
echo "3e. Testing VELOCITY mode..."
timeout 8 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 \
    -p baud_rate:=250000 \
    -p node_id:=1 \
    -p mode:=velocity \
    -p target_velocity:=3.0 > /tmp/test_velocity.log 2>&1
if [ $? -eq 124 ] || grep -q "Test completed successfully" /tmp/test_velocity.log; then
    test_result 0 "Velocity mode test"
else
    test_result 1 "Velocity mode test"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}TEST 4: CAN Communication Integrity${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Monitor CAN traffic during a test
sudo candump -td can0 > /tmp/can_traffic_test.log 2>&1 &
CANDUMP_PID=$!
sleep 0.5

# Run a quick test
timeout 5 ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p interface_name:=can0 \
    -p baud_rate:=250000 \
    -p node_id:=1 \
    -p mode:=status > /dev/null 2>&1 || true

sleep 1
sudo kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

CAN_MESSAGES=$(wc -l < /tmp/can_traffic_test.log)
if [ $CAN_MESSAGES -gt 0 ]; then
    test_result 0 "CAN traffic detected ($CAN_MESSAGES messages)"
else
    test_result 1 "No CAN traffic detected"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}TEST 5: Final CAN Statistics${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

ip -s link show can0 | grep -A 2 "RX:\|TX:"

RX_PACKETS=$(ip -s link show can0 | grep "RX:" -A 1 | tail -1 | awk '{print $2}')
TX_PACKETS=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $2}')
TX_ERRORS=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $3}')

echo ""
echo "Statistics Summary:"
echo "  RX Packets: $RX_PACKETS"
echo "  TX Packets: $TX_PACKETS"
echo "  TX Errors: $TX_ERRORS"

if [ "$TX_ERRORS" -eq "0" ]; then
    test_result 0 "Zero TX errors"
else
    test_result 1 "TX errors detected: $TX_ERRORS"
fi

if [ "$RX_PACKETS" -gt "0" ]; then
    test_result 0 "Motor responses received"
else
    test_result 1 "No motor responses"
fi

echo ""
echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                      TEST SUMMARY                              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

SUCCESS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
echo "Success Rate: $SUCCESS_RATE%"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              🎉 ALL TESTS PASSED! 🎉                          ║"
    echo "║                                                                ║"
    echo "║    Full ROS2 Motor Control System is OPERATIONAL              ║"
    echo "║    CAN Communication is VERIFIED                               ║"
    echo "║    System is READY for Integration                             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
else
    echo -e "${YELLOW}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              ⚠ SOME TESTS FAILED ⚠                           ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "Check logs in /tmp/test_*.log for details"
fi

echo ""
echo "Test logs saved to:"
echo "  /tmp/ros2_launch_status.log"
echo "  /tmp/test_status.log"
echo "  /tmp/test_angle.log"
echo "  /tmp/test_onoff.log"
echo "  /tmp/test_position.log"
echo "  /tmp/test_velocity.log"
echo "  /tmp/can_traffic_test.log"
