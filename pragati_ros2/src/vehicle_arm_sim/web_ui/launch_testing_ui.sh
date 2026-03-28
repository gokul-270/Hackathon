#!/usr/bin/env bash
# =============================================================================
# Comprehensive Testing Web UI Launcher for Vehicle + Arm Simulation
# =============================================================================
# Starts the full testing environment:
#   1. Gazebo simulation (via vehicle_arm.launch.py — includes vehicle bridge)
#   2. Arm joint parameter bridge (ros_gz_bridge for arm topics)
#   3. Kinematics node (cmd_vel → steering/wheel conversion)
#   4. Rosbridge server (browser ↔ ROS2 WebSocket)
#   5. FastAPI backend (spawn, E-STOP, status)
#
# Usage:
#   ./launch_testing_ui.sh                  # Full launch
#   ./launch_testing_ui.sh --no-gazebo      # Skip Gazebo (already running)
#   ./launch_testing_ui.sh --headless       # Gazebo server only (no GUI)
#   ./launch_testing_ui.sh --no-spawn       # Skip auto-spawn
#
# Ports:
#   8081 — FastAPI backend (HTTP)
#   9090 — rosbridge WebSocket
#
# Architecture:
#   Browser joystick ──→ rosbridge :9090 ──→ /cmd_vel  ──→ kinematics_node
#       ──→ /steering/* + /wheel/*/velocity ──→ parameter_bridge ──→ Gazebo
#
#   Browser sliders  ──→ rosbridge :9090 ──→ /joint3_cmd ──→ arm bridge ──→ Gazebo
# =============================================================================

set -euo pipefail

# ---- Colours ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---- Paths ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$PKG_DIR/../.." && pwd)"

# ---- Ports ----
HTTP_PORT="${HTTP_PORT:-8081}"
ROSBRIDGE_PORT="${ROSBRIDGE_PORT:-9090}"

# ---- Flags ----
NO_GAZEBO=false
NO_SPAWN=false
HEADLESS=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --no-gazebo)  NO_GAZEBO=true ;;
        --no-spawn)   NO_SPAWN=true ;;
        --headless)   HEADLESS=true ;;
        -h|--help)
            echo "Usage: $0 [--no-gazebo] [--headless] [--no-spawn]"
            exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
    shift
done

# ---- Source ROS2 ----
echo -e "${CYAN}Sourcing ROS2 environment...${NC}"
ROS_SOURCED=false
# Temporarily disable nounset — ROS2 setup scripts reference unbound variables
set +u
if [[ -f /opt/ros/jazzy/setup.bash ]]; then
    # shellcheck disable=SC1091
    source /opt/ros/jazzy/setup.bash
    ROS_SOURCED=true
fi
if [[ -f "$WORKSPACE_ROOT/install/setup.bash" ]]; then
    # shellcheck disable=SC1091
    source "$WORKSPACE_ROOT/install/setup.bash"
fi
if [[ -f "$WORKSPACE_ROOT/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$WORKSPACE_ROOT/venv/bin/activate"
fi
set -u

# ---- Cleanup existing processes ----
echo -e "${CYAN}Cleaning up existing processes...${NC}"
KILLED_ANY=false
pkill -9 -f "testing_backend" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed testing_backend${NC}" || true
pkill -9 -f "uvicorn.*testing" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed uvicorn${NC}" || true
if [[ "$NO_GAZEBO" = false ]]; then
    pkill -9 -f "ros2 launch" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed ros2 launch${NC}" || true
    pkill -9 -f "gz sim" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed Gazebo${NC}" || true
    pkill -9 -f "parameter_bridge" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed parameter_bridge${NC}" || true
    pkill -9 -f "rosbridge" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed rosbridge${NC}" || true
    pkill -9 -f "kinematics_node" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed kinematics_node${NC}" || true
    pkill -9 -f "robot_state_publisher" 2>/dev/null && KILLED_ANY=true && echo -e "${GREEN}  Killed robot_state_publisher${NC}" || true
fi
[[ "$KILLED_ANY" = true ]] && sleep 2
echo ""

# ---- Detect WSL IP ----
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

# ---- Detect URDF file ----
URDF_FILE=""
SESSION_FILE="$HOME/.vehicle_arm_sim/latest_editor.urdf"
SAVED_DIR="$PKG_DIR/urdf/saved"

if [[ -f "$SESSION_FILE" ]]; then
    URDF_FILE="$SESSION_FILE"
    echo -e "${GREEN}Using session URDF: $(basename "$URDF_FILE")${NC}"
elif [[ -d "$SAVED_DIR" ]]; then
    URDF_FILE=$(ls -t "$SAVED_DIR"/*.urdf 2>/dev/null | head -1)
    if [[ -n "$URDF_FILE" ]]; then
        echo -e "${GREEN}Using saved URDF: $(basename "$URDF_FILE")${NC}"
    fi
fi

if [[ -z "$URDF_FILE" ]]; then
    echo -e "${RED}ERROR: No URDF file found!${NC}"
    echo -e "${YELLOW}  Looked in: $SESSION_FILE${NC}"
    echo -e "${YELLOW}  Looked in: $SAVED_DIR/*.urdf${NC}"
    exit 1
fi
export VEHICLE_ARM_URDF_FILE="$URDF_FILE"

# ---- Track PIDs ----
PIDS=()

cleanup() {
    echo -e "\n${YELLOW}Shutting down testing environment...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    pkill -f "testing_backend" 2>/dev/null || true
    pkill -f "uvicorn.*testing" 2>/dev/null || true
    if [[ "$NO_GAZEBO" = false ]]; then
        pkill -f "gz sim" 2>/dev/null || true
        pkill -f "parameter_bridge" 2>/dev/null || true
        pkill -f "rosbridge_websocket" 2>/dev/null || true
        pkill -f "kinematics_node" 2>/dev/null || true
        pkill -f "robot_state_publisher" 2>/dev/null || true
    fi
    wait 2>/dev/null || true
    echo -e "${GREEN}All processes stopped.${NC}"
}
trap cleanup EXIT INT TERM

# =============================================================================
# 1. LAUNCH GAZEBO
# =============================================================================
# vehicle_arm.launch.py starts: Gazebo server + GUI + robot_state_publisher +
# model spawn + parameter_bridge (vehicle steering/wheel/odom/sensors).
if [[ "$NO_GAZEBO" = true ]]; then
    echo -e "${YELLOW}1/5  Skipping Gazebo (--no-gazebo)${NC}"
    echo -e "${YELLOW}     Ensure Gazebo + vehicle_arm.launch.py is already running${NC}"
    echo ""
else
    echo -e "${CYAN}1/5  Launching Gazebo simulation...${NC}"
    HEADLESS_ARG="false"
    [[ "$HEADLESS" = true ]] && HEADLESS_ARG="true"

    ros2 launch vehicle_arm_sim vehicle_arm.launch.py \
        headless:="$HEADLESS_ARG" \
        > /tmp/testing_gazebo.log 2>&1 &
    GAZEBO_LAUNCH_PID=$!
    PIDS+=($GAZEBO_LAUNCH_PID)
    echo -e "${GREEN}     Launch PID: $GAZEBO_LAUNCH_PID${NC}"

    # Wait for Gazebo
    GAZEBO_TIMEOUT=45
    GAZEBO_READY=false
    echo -ne "${CYAN}     Waiting for Gazebo "
    for ((i=1; i<=GAZEBO_TIMEOUT; i++)); do
        if ! kill -0 "$GAZEBO_LAUNCH_PID" 2>/dev/null; then
            echo -e "${NC}"
            echo -e "${RED}     Gazebo process exited! Check /tmp/testing_gazebo.log${NC}"
            break
        fi
        if pgrep -f "gz sim" >/dev/null 2>&1; then
            GAZEBO_READY=true
            echo -e "${NC}"
            echo -e "${GREEN}     Gazebo ready (took ${i}s)${NC}"
            sleep 3
            break
        fi
        echo -n "."
        sleep 1
    done
    if [[ "$GAZEBO_READY" = false ]] && kill -0 "$GAZEBO_LAUNCH_PID" 2>/dev/null; then
        echo -e "${NC}"
        echo -e "${YELLOW}     WARNING: Gazebo not ready within ${GAZEBO_TIMEOUT}s — continuing${NC}"
    fi
    echo ""
fi

# =============================================================================
# 2. ARM JOINT PARAMETER BRIDGE
# =============================================================================
# vehicle_arm.launch.py bridges vehicle topics but NOT arm joints.
# We start a second bridge for arm topics (ROS2 → Gazebo direction).
echo -e "${CYAN}2/5  Starting arm joint parameter bridge...${NC}"
ros2 run ros_gz_bridge parameter_bridge \
    /joint3_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /joint4_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /joint5_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /joint3_copy_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /joint4_copy_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /joint5_copy_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /arm_joint3_copy1_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /arm_joint4_copy1_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    /arm_joint5_copy1_cmd@std_msgs/msg/Float64]gz.msgs.Double \
    > /tmp/testing_arm_bridge.log 2>&1 &
ARM_BRIDGE_PID=$!
PIDS+=($ARM_BRIDGE_PID)
echo -e "${GREEN}     PID: $ARM_BRIDGE_PID${NC}"
echo ""

# =============================================================================
# 3. KINEMATICS NODE
# =============================================================================
# Subscribes /cmd_vel → publishes /steering/* + /wheel/*/velocity.
KINEMATICS_NODE="$WORKSPACE_ROOT/src/vehicle_control/simulation/gazebo/nodes/kinematics_node.py"

if [[ ! -f "$KINEMATICS_NODE" ]]; then
    echo -e "${RED}3/5  ERROR: kinematics_node.py not found at:${NC}"
    echo -e "${RED}     $KINEMATICS_NODE${NC}"
    exit 1
fi

if pgrep -f "kinematics_node" >/dev/null 2>&1; then
    echo -e "${YELLOW}3/5  kinematics_node already running — skipping${NC}"
else
    echo -e "${CYAN}3/5  Starting kinematics node...${NC}"
    python3 "$KINEMATICS_NODE" > /tmp/testing_kinematics.log 2>&1 &
    KINEMATICS_PID=$!
    PIDS+=($KINEMATICS_PID)
    echo -e "${GREEN}     PID: $KINEMATICS_PID${NC}"
fi
echo ""

# =============================================================================
# 4. ROSBRIDGE SERVER
# =============================================================================
ROSBRIDGE_LAUNCH="/opt/ros/jazzy/share/rosbridge_server/launch/rosbridge_websocket_launch.xml"

if pgrep -f "rosbridge" >/dev/null 2>&1; then
    echo -e "${YELLOW}4/5  rosbridge already running — skipping${NC}"
elif [[ "$ROS_SOURCED" = false ]]; then
    echo -e "${RED}4/5  ROS2 not available — cannot start rosbridge${NC}"
    echo -e "${RED}     Install: sudo apt install ros-jazzy-rosbridge-suite${NC}"
    exit 1
elif [[ -f "$ROSBRIDGE_LAUNCH" ]]; then
    echo -e "${CYAN}4/5  Starting rosbridge on port ${ROSBRIDGE_PORT}...${NC}"
    ros2 launch rosbridge_server rosbridge_websocket_launch.xml \
        port:="${ROSBRIDGE_PORT}" \
        address:="0.0.0.0" \
        > /tmp/testing_rosbridge.log 2>&1 &
    ROSBRIDGE_PID=$!
    PIDS+=($ROSBRIDGE_PID)
    echo -e "${GREEN}     PID: $ROSBRIDGE_PID (ws://${WSL_IP}:${ROSBRIDGE_PORT})${NC}"
else
    echo -e "${RED}4/5  rosbridge_server not installed!${NC}"
    echo -e "${RED}     sudo apt install ros-jazzy-rosbridge-suite${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 5. FASTAPI BACKEND
# =============================================================================
echo -e "${CYAN}5/5  Starting testing backend on port ${HTTP_PORT}...${NC}"
python3 "$SCRIPT_DIR/testing_backend.py" --port "$HTTP_PORT" \
    > /tmp/testing_backend.log 2>&1 &
BACKEND_PID=$!
PIDS+=($BACKEND_PID)
echo -e "${GREEN}     PID: $BACKEND_PID${NC}"
echo ""

# =============================================================================
# SUMMARY
# =============================================================================
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Testing Environment Ready                   ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Web UI:     http://${WSL_IP}:${HTTP_PORT}${NC}"
echo -e "${GREEN}║  Rosbridge:  ws://${WSL_IP}:${ROSBRIDGE_PORT}${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Logs:                                              ║${NC}"
echo -e "${GREEN}║    /tmp/testing_gazebo.log                          ║${NC}"
echo -e "${GREEN}║    /tmp/testing_arm_bridge.log                      ║${NC}"
echo -e "${GREEN}║    /tmp/testing_kinematics.log                      ║${NC}"
echo -e "${GREEN}║    /tmp/testing_rosbridge.log                       ║${NC}"
echo -e "${GREEN}║    /tmp/testing_backend.log                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Press Ctrl+C to stop all processes${NC}"
echo ""

wait
