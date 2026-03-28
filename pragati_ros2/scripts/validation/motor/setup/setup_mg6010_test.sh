#!/bin/bash
###############################################################################
# MG6010 Motor Test Setup Script
# Run this on the Raspberry Pi after transferring code
# This script will: configure CAN, build package, prepare for testing
###############################################################################

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MG6010 Motor Test Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running on RPi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${RED}Error: This script should run on Raspberry Pi${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Running on Raspberry Pi${NC}"
echo ""

###############################################################################
# Phase 2.3: Configure CAN at 500 kbps
###############################################################################
echo -e "${BLUE}Phase 2.3: Configuring CAN interface at 500 kbps...${NC}"

# Bring down CAN interface
echo "  Bringing down can0..."
sudo ip link set can0 down 2>/dev/null || true

# Configure for 500 kbps with auto-restart
echo "  Setting bitrate to 500000..."
sudo ip link set can0 type can bitrate 500000 restart-ms 100

# Bring up CAN interface
echo "  Bringing up can0..."
sudo ip link set can0 up

# Verify status
echo -e "\n${YELLOW}CAN Interface Status:${NC}"
ip -details link show can0

# Check if UP
if ip link show can0 | grep -q "state UP"; then
    echo -e "${GREEN}✓ CAN interface is UP at 500 kbps${NC}"
else
    echo -e "${RED}✗ CAN interface failed to come UP${NC}"
    exit 1
fi

echo ""

###############################################################################
# Phase 3: Build motor_control_ros2 with test nodes
###############################################################################
echo -e "${BLUE}Phase 3: Building motor_control_ros2 package...${NC}"

# Source ROS 2
if [ -f /opt/ros/jazzy/setup.bash ]; then
    echo "  Sourcing ROS 2 Jazzy..."
    source /opt/ros/jazzy/setup.bash
else
    echo "  Sourcing ROS 2 Humble (fallback)..."
    source /opt/ros/humble/setup.bash
fi

# Navigate to workspace
cd ~/pragati_ws

# Update rosdep
echo "  Updating rosdep..."
rosdep update 2>&1 | tail -5

# Install dependencies
echo "  Installing dependencies..."
rosdep install --from-paths src --ignore-src -y 2>&1 | grep -E "^(All required|#|ERROR)" || true

# Clean previous builds
echo "  Cleaning previous builds..."
rm -rf build/motor_control_ros2 install/motor_control_ros2 log/motor_control_ros2

# Build with test nodes enabled
echo -e "\n  ${YELLOW}Building motor_control_ros2 (this may take 2-5 minutes)...${NC}"
colcon build --packages-select motor_control_ros2 \
  --cmake-args -DODRIVE_BUILD_TEST_NODES=ON \
              -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  2>&1 | tee /tmp/mg6010_build.log | grep -E "^(Starting|Finished|Summary|---)"

# Check build success
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo -e "${GREEN}✓ Build completed successfully${NC}"
else
    echo -e "${RED}✗ Build failed - check /tmp/mg6010_build.log${NC}"
    exit 1
fi

# Source the workspace
echo "  Sourcing workspace..."
source install/setup.bash

# Make test script executable
chmod +x ~/pragati_ws/scripts/test_mg6010_communication.sh

# Verify test node exists
echo -e "\n  ${YELLOW}Verifying mg6010_test_node...${NC}"
if ros2 run motor_control_ros2 mg6010_test_node --help 2>&1 | head -5; then
    echo -e "${GREEN}✓ Test node is available${NC}"
else
    echo -e "${RED}✗ Test node not found${NC}"
    exit 1
fi

echo ""

###############################################################################
# Phase 4: Prepare for testing (motor remains unpowered)
###############################################################################
echo -e "${BLUE}Phase 4: Preparing for testing (motor UNPOWERED)...${NC}"

# Set test parameters
export CAN_IFACE=can0
export CAN_BITRATE=500000
export MG6010_NODE_ID=1

echo "  Test parameters:"
echo "    CAN Interface: $CAN_IFACE"
echo "    Bitrate: $CAN_BITRATE"
echo "    Motor Node ID: $MG6010_NODE_ID"

# Put CAN in listen-only mode (safe - won't send, only monitor)
echo -e "\n  Setting CAN to listen-only mode (safe monitoring)..."
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only on restart-ms 100
sudo ip link set can0 up

ip -details link show can0 | grep -E "can0|state|bitrate"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "  Installing tmux..."
    sudo apt-get update -qq
    sudo apt-get install -y tmux
fi

# Kill any existing canmon session
tmux kill-session -t canmon 2>/dev/null || true

# Start CAN monitoring in background
echo "  Starting CAN monitor in background (tmux session: canmon)..."
tmux new-session -d -s canmon "candump -L can0"
sleep 1

# Verify no errors
echo -e "\n  ${YELLOW}Checking for CAN errors...${NC}"
dmesg | egrep -i "can0|bus-off|error|mcp251" | tail -10 || echo "  No errors found"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Motor is NOT powered yet${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. Verify all checks passed above"
echo -e "  2. ${RED}Keep motor UNPOWERED for now${NC}"
echo -e "  3. When ready, use the phase5 script to power on and test"
echo ""
echo -e "To proceed with testing:"
echo -e "  ${BLUE}bash scripts/validation/motor/phase5_motor_test.sh${NC}"
echo ""

# Save environment variables to file for phase 5
cat > ~/mg6010_test_env.sh <<'EOF'
#!/bin/bash
export CAN_IFACE=can0
export CAN_BITRATE=500000
export MG6010_NODE_ID=1
source /opt/ros/humble/setup.bash
source ~/pragati_ws/install/setup.bash
EOF

echo -e "${GREEN}Environment saved to ~/mg6010_test_env.sh${NC}"
