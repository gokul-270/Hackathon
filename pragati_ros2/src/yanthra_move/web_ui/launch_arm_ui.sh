#!/bin/bash
# ============================================
# Pragati Robot — Arm Simulation Web UI Launch
# ============================================
#
# Starts:
#   1. HTTP server (port 8889) for the web UI
#   2. rosbridge_server (port 9090) for ROS2 WebSocket bridge
#   3. arm_sim_bridge.py ROS2 node for TF/Gazebo operations
#
# Usage:
#   ./launch_arm_ui.sh              # Start all three
#   ./launch_arm_ui.sh --no-bridge  # Skip rosbridge (if already running)
#
# Prerequisites:
#   sudo apt install ros-jazzy-rosbridge-suite
#
# Access: http://localhost:8889 (or WSL IP)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTTP_PORT="${HTTP_PORT:-8889}"
ROSBRIDGE_PORT="${ROSBRIDGE_PORT:-9090}"
NO_BRIDGE=false

for arg in "$@"; do
    case "$arg" in
        --no-bridge) NO_BRIDGE=true ;;
    esac
done

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Pragati Robot — Arm Simulation Web UI${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$WSL_IP" ] && WSL_IP="localhost"

PIDS=()
cleanup() {
    echo ""
    echo -e "${CYAN}Shutting down...${NC}"
    for pid in "${PIDS[@]}"; do
        kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null
    done
    echo -e "${GREEN}Done.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ---- Source ROS2 ----
if [ -z "$ROS_DISTRO" ]; then
    if [ -f /opt/ros/jazzy/setup.bash ]; then
        source /opt/ros/jazzy/setup.bash
        echo -e "${GREEN}Sourced ROS2 Jazzy${NC}"
    else
        echo -e "${RED}ERROR: ROS2 not found${NC}"
        exit 1
    fi
fi

# Source workspace
WORKSPACE_SETUP="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")/install/setup.bash"
if [ -f "$WORKSPACE_SETUP" ]; then
    source "$WORKSPACE_SETUP" 2>/dev/null
    echo -e "${GREEN}Sourced workspace: $WORKSPACE_SETUP${NC}"
else
    # Try common location
    if [ -f "$HOME/pragati_ros2/install/setup.bash" ]; then
        source "$HOME/pragati_ros2/install/setup.bash" 2>/dev/null
        echo -e "${GREEN}Sourced workspace: ~/pragati_ros2${NC}"
    fi
fi

# ---- 1. HTTP server ----
echo -e "${CYAN}Starting HTTP server on port ${HTTP_PORT}...${NC}"
python3 -m http.server "$HTTP_PORT" --bind 0.0.0.0 --directory "$SCRIPT_DIR" \
    > /tmp/arm_ui_http.log 2>&1 &
PIDS+=($!)
echo -e "${GREEN}  HTTP PID: ${PIDS[-1]}${NC}"
echo -e "${GREEN}  URL: http://${WSL_IP}:${HTTP_PORT}${NC}"
echo ""

# ---- 2. rosbridge_server ----
if [ "$NO_BRIDGE" = false ]; then
    ROSBRIDGE_LAUNCH="/opt/ros/${ROS_DISTRO}/share/rosbridge_server/launch/rosbridge_websocket_launch.xml"
    if [ -f "$ROSBRIDGE_LAUNCH" ]; then
        echo -e "${CYAN}Starting rosbridge_server on port ${ROSBRIDGE_PORT}...${NC}"
        ros2 launch rosbridge_server rosbridge_websocket_launch.xml \
            port:="${ROSBRIDGE_PORT}" address:="0.0.0.0" \
            > /tmp/arm_ui_rosbridge.log 2>&1 &
        PIDS+=($!)
        echo -e "${GREEN}  Rosbridge PID: ${PIDS[-1]}${NC}"
        echo -e "${GREEN}  WebSocket: ws://${WSL_IP}:${ROSBRIDGE_PORT}${NC}"
    else
        echo -e "${YELLOW}WARNING: rosbridge_server not installed${NC}"
        echo -e "${YELLOW}Install: sudo apt install ros-jazzy-rosbridge-suite${NC}"
    fi
else
    echo -e "${YELLOW}Skipping rosbridge (--no-bridge)${NC}"
fi
echo ""

# ---- 3. TF infrastructure (robot_state_publisher + static TF + joint_state_publisher) ----
# These provide the TF tree so cotton placement works even without Gazebo running.
# If Gazebo IS running, its joint_states override the defaults.
WORKSPACE_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
URDF_FILE=""
# Try installed path first, then source path
for candidate in \
    "$WORKSPACE_ROOT/install/robot_description/share/robot_description/urdf/MG6010_FLU.urdf" \
    "$WORKSPACE_ROOT/src/robot_description/urdf/MG6010_FLU.urdf"; do
    if [ -f "$candidate" ]; then
        URDF_FILE="$candidate"
        break
    fi
done

if [ -n "$URDF_FILE" ]; then
    echo -e "${CYAN}Starting TF infrastructure (robot_state_publisher + static TF)...${NC}"
    echo -e "  URDF: $URDF_FILE"

    # Generate a YAML params file for robot_state_publisher
    # (passing URDF via --ros-args -p breaks due to XML special chars)
    RSP_PARAMS="/tmp/arm_ui_rsp_params.yaml"
    python3 -c "
import yaml, sys
with open('$URDF_FILE') as f:
    urdf = f.read()
params = {'robot_state_publisher': {'ros__parameters': {'robot_description': urdf}}}
with open('$RSP_PARAMS', 'w') as f:
    yaml.dump(params, f, default_flow_style=False)
print('  Params file written: $RSP_PARAMS')
"

    # robot_state_publisher: publishes TF from URDF
    ros2 run robot_state_publisher robot_state_publisher \
        --ros-args --params-file "$RSP_PARAMS" \
        > /tmp/arm_ui_rsp.log 2>&1 &
    PIDS+=($!)
    echo -e "${GREEN}  robot_state_publisher PID: ${PIDS[-1]}${NC}"

    # static TF: world → base_link (matching Gazebo spawn -z 0.1)
    ros2 run tf2_ros static_transform_publisher \
        0 0 0.1 0 0 0 world base_link \
        > /tmp/arm_ui_static_tf.log 2>&1 &
    PIDS+=($!)
    echo -e "${GREEN}  static_tf (world→base_link) PID: ${PIDS[-1]}${NC}"

    # NOTE: joint_state_publisher is NOT needed here.
    # arm_sim_bridge.py publishes /joint_states directly (with correct J4 positions
    # for cotton placement). This avoids conflicts with Gazebo's joint states.
else
    echo -e "${YELLOW}WARNING: URDF not found — TF will only work when simulation is running${NC}"
    echo -e "${YELLOW}  Looked for: MG6010_FLU.urdf in install/ and src/${NC}"
fi
echo ""

# ---- 4. Arm Sim Bridge Node ----
echo -e "${CYAN}Starting arm_sim_bridge node...${NC}"
python3 "$SCRIPT_DIR/arm_sim_bridge.py" > /tmp/arm_ui_bridge.log 2>&1 &
PIDS+=($!)
echo -e "${GREEN}  Bridge PID: ${PIDS[-1]}${NC}"
echo ""

# Wait for startup
sleep 2

echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN} Arm Simulation Web UI ready!${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Open: http://${WSL_IP}:${HTTP_PORT}${NC}"
echo -e "${GREEN}  Bridge: ws://${WSL_IP}:${ROSBRIDGE_PORT}${NC}"
echo ""
echo -e "${YELLOW}Logs:${NC}"
echo -e "  HTTP:      /tmp/arm_ui_http.log"
echo -e "  Rosbridge: /tmp/arm_ui_rosbridge.log"
echo -e "  RSP:       /tmp/arm_ui_rsp.log"
echo -e "  Static TF: /tmp/arm_ui_static_tf.log"
echo -e "  JSP:       /tmp/arm_ui_jsp.log"
echo -e "  Bridge:    /tmp/arm_ui_bridge.log"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all.${NC}"
echo ""

wait
