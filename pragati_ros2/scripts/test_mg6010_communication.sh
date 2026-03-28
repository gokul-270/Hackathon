#!/usr/bin/env bash
# MG6010 Motor Communication Test Script
# 
# Tests MG6010 motor communication using the standalone test node
# with candump logging for message verification.
# 
# Usage: ./test_mg6010_communication.sh [interface] [baud_rate] [node_id]
#   interface: CAN interface name (default: can0)
#   baud_rate: CAN baud rate (default: 1000000 for 1Mbps)
#   node_id: Motor node ID 1-32 (default: 1)

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default parameters
INTERFACE="${1:-can0}"
BAUD_RATE="${2:-1000000}"
NODE_ID="${3:-1}"
LOG_DIR="/tmp/mg6010_test_$(date +%Y%m%d_%H%M%S)"
CANDUMP_LOG="${LOG_DIR}/candump.log"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MG6010 Motor Communication Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Interface: ${GREEN}${INTERFACE}${NC}"
echo -e "Baud Rate: ${GREEN}${BAUD_RATE}${NC} bps"
echo -e "Node ID: ${GREEN}${NODE_ID}${NC}"
echo -e "Log Directory: ${GREEN}${LOG_DIR}${NC}"
echo ""

# Create log directory
mkdir -p "${LOG_DIR}"

# Check if can-utils is installed
if ! command -v candump &> /dev/null; then
    echo -e "${YELLOW}Warning: can-utils not found. Installing...${NC}"
    sudo apt-get update && sudo apt-get install -y can-utils
fi

# Configure CAN interface
echo -e "${BLUE}Configuring CAN interface...${NC}"
sudo ip link set ${INTERFACE} down 2>/dev/null || true
sudo ip link set ${INTERFACE} type can bitrate ${BAUD_RATE}
sudo ip link set ${INTERFACE} up

if ! ip link show ${INTERFACE} | grep -q "UP"; then
    echo -e "${RED}Failed to bring up CAN interface${NC}"
    exit 1
fi

echo -e "${GREEN}CAN interface configured successfully${NC}"
echo ""

# Start candump in background
echo -e "${BLUE}Starting CAN message logging...${NC}"
candump ${INTERFACE} -l -L &> "${CANDUMP_LOG}" &
CANDUMP_PID=$!
echo -e "candump PID: ${CANDUMP_PID}"
sleep 1

# Cleanup function
cleanup() {
    echo -e "\n${BLUE}Cleaning up...${NC}"
    if [ ! -z "${CANDUMP_PID}" ]; then
        kill ${CANDUMP_PID} 2>/dev/null || true
        wait ${CANDUMP_PID} 2>/dev/null || true
    fi
    echo -e "${GREEN}Cleanup complete${NC}"
}

trap cleanup EXIT INT TERM

# Test modes to run
TEST_MODES=("status" "angle" "pid" "encoder" "on_off")

echo -e "${BLUE}Running test modes...${NC}"
echo ""

# Run each test mode
for MODE in "${TEST_MODES[@]}"; do
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Test Mode: ${GREEN}${MODE}${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    TEST_LOG="${LOG_DIR}/test_${MODE}.log"
    
    # Run test node
    ros2 run odrive_control_ros2 mg6010_test_node \
        --ros-args \
        -p interface_name:="${INTERFACE}" \
        -p baud_rate:=${BAUD_RATE} \
        -p node_id:=${NODE_ID} \
        -p mode:="${MODE}" \
        -p verbose:=true \
        2>&1 | tee "${TEST_LOG}"
    
    TEST_RESULT=$?
    
    if [ ${TEST_RESULT} -eq 0 ]; then
        echo -e "${GREEN}✓ Test '${MODE}' passed${NC}"
    else
        echo -e "${RED}✗ Test '${MODE}' failed (exit code: ${TEST_RESULT})${NC}"
    fi
    echo ""
    
    # Small delay between tests
    sleep 1
done

# Stop candump
echo -e "${BLUE}Stopping CAN message logging...${NC}"
kill ${CANDUMP_PID} 2>/dev/null || true
wait ${CANDUMP_PID} 2>/dev/null || true
CANDUMP_PID=""

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}========================================${NC}"

# Count messages in candump log
if [ -f "${CANDUMP_LOG}" ]; then
    MSG_COUNT=$(grep -c "can0" "${CANDUMP_LOG}" 2>/dev/null || echo "0")
    echo -e "Total CAN messages logged: ${GREEN}${MSG_COUNT}${NC}"
    
    # Show unique arbitration IDs
    echo -e "\nUnique CAN IDs detected:"
    grep "can0" "${CANDUMP_LOG}" 2>/dev/null | awk '{print $3}' | cut -d'#' -f1 | sort -u | while read ID; do
        COUNT=$(grep -c "${ID}#" "${CANDUMP_LOG}" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}${ID}${NC}: ${COUNT} messages"
    done
fi

echo ""
echo -e "${GREEN}All tests completed!${NC}"
echo -e "Logs saved to: ${GREEN}${LOG_DIR}${NC}"
echo ""
echo -e "To analyze CAN messages:"
echo -e "  cat ${CANDUMP_LOG}"
echo -e "To compare with tested implementation:"
echo -e "  python3 scripts/compare_can_messages.py ${CANDUMP_LOG} /path/to/colleague/candump.log"
echo ""
