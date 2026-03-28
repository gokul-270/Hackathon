#!/bin/bash

################################################################################
# Pragati ROS2 Complete System Launch with Web Dashboard
#
# This script properly launches all components with:
# - Web dashboard for monitoring
# - Correct motor_control node references (not odrive)
# - Continuous operation mode for yanthra_move
# - Offline cotton detection support
################################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${CYAN}🚀 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Parse arguments
LAUNCH_DASHBOARD=true
CONTINUOUS_MODE=true
OFFLINE_COTTON=false
WEB_PORT=8090

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-dashboard)
            LAUNCH_DASHBOARD=false
            shift
            ;;
        --single-run)
            CONTINUOUS_MODE=false
            shift
            ;;
        --offline-cotton)
            OFFLINE_COTTON=true
            shift
            ;;
        --port)
            WEB_PORT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-dashboard      Skip launching web dashboard"
            echo "  --single-run        Run yanthra_move in single-cycle mode (default: continuous)"
            echo "  --offline-cotton    Use offline cotton detection (no camera)"
            echo "  --port PORT         Dashboard port (default: 8090)"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Full launch with dashboard"
            echo "  $0 --single-run --offline-cotton      # Single run, test mode"
            echo "  $0 --port 9090                        # Dashboard on port 9090"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

cd "$WORKSPACE_ROOT"

print_header "Pragati ROS2 System Launch"

# Check ROS2 environment
if [ -z "$ROS_DISTRO" ]; then
    print_error "ROS2 environment not sourced!"
    echo "Run: source /opt/ros/jazzy/setup.bash"
    exit 1
fi

print_success "ROS_DISTRO: $ROS_DISTRO"

# Source workspace
if [ ! -f "install/setup.bash" ]; then
    print_error "Workspace not built! Run: ./build.sh"
    exit 1
fi

source install/setup.bash
print_success "Workspace sourced"

# Display configuration
echo ""
print_step "Launch Configuration:"
echo "  Dashboard: $([ "$LAUNCH_DASHBOARD" = true ] && echo "✅ Enabled (port $WEB_PORT)" || echo "❌ Disabled")"
echo "  Yanthra Mode: $([ "$CONTINUOUS_MODE" = true ] && echo "🔄 Continuous Operation" || echo "🔂 Single Run")"
echo "  Cotton Detection: $([ "$OFFLINE_COTTON" = true ] && echo "📁 Offline (test images)" || echo "📷 Live Camera")"
echo ""

# Track PIDs for cleanup
echo "" > /tmp/pragati_system_pids.txt

# Cleanup function
cleanup() {
    echo ""
    print_step "Shutting down system..."

    if [ -f /tmp/pragati_system_pids.txt ]; then
        while read pid; do
            if [ -n "$pid" ] && kill -0 $pid 2>/dev/null; then
                echo "  Stopping PID: $pid"
                kill $pid 2>/dev/null || true
            fi
        done < /tmp/pragati_system_pids.txt
        rm -f /tmp/pragati_system_pids.txt
    fi

    # Kill any remaining processes
    pkill -f "ros2 run" || true
    pkill -f "ros2 launch" || true
    pkill -f "dashboard_server" || true

    print_success "Shutdown complete"
}

trap cleanup EXIT INT TERM

# Function to start a node
start_node() {
    local cmd="$1"
    local name="$2"
    local log_file="$3"

    print_step "Starting $name..."
    eval "$cmd" > "$log_file" 2>&1 &
    local pid=$!
    echo $pid >> /tmp/pragati_system_pids.txt
    echo "  PID: $pid, Log: $log_file"
    sleep 2

    if ! kill -0 $pid 2>/dev/null; then
        print_error "$name failed to start (see $log_file)"
        tail -20 "$log_file"
        return 1
    fi

    print_success "$name running"
    return 0
}

# 1. Start Web Dashboard (if enabled)
if [ "$LAUNCH_DASHBOARD" = true ]; then
    print_header "Step 1: Launching Web Dashboard"

    if [ ! -f "web_dashboard/run_dashboard.py" ]; then
        print_warning "Web dashboard not found, skipping..."
    else
        # Check dependencies
        python3 -c "import fastapi, uvicorn" 2>/dev/null
        if [ $? -eq 0 ]; then
            start_node "python3 web_dashboard/run_dashboard.py --port $WEB_PORT" \
                      "Web Dashboard" \
                      "/tmp/pragati_dashboard.log"

            echo ""
            print_success "🌐 Dashboard available at: http://localhost:$WEB_PORT"
            echo ""
        else
            print_warning "Dashboard dependencies missing. Install with:"
            echo "  pip install fastapi uvicorn websockets psutil"
        fi
    fi
else
    print_step "Skipping dashboard (use default flags to enable)"
fi

# 2. Start Robot State Publisher
print_header "Step 2: Core ROS2 Nodes"

# Load URDF
URDF_FILE="$WORKSPACE_ROOT/install/robo_description/share/robo_description/urdf/URDF"
if [ -f "$URDF_FILE" ]; then
    ROBOT_DESCRIPTION=$(cat "$URDF_FILE")
    start_node "ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:='$ROBOT_DESCRIPTION'" \
              "Robot State Publisher" \
              "/tmp/pragati_robot_state_pub.log"
else
    print_warning "URDF not found at $URDF_FILE, skipping robot_state_publisher"
fi

# 3. Start Joint State Publisher
start_node "ros2 run joint_state_publisher joint_state_publisher" \
          "Joint State Publisher" \
          "/tmp/pragati_joint_state_pub.log"

# 4. Start Cotton Detection
print_header "Step 3: Cotton Detection"

if [ "$OFFLINE_COTTON" = true ]; then
    print_step "Offline cotton detection mode"
    # Launch without camera, for testing with images
    start_node "ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false" \
              "Cotton Detection (Offline)" \
              "/tmp/pragati_cotton_detection.log"

    echo ""
    print_success "Cotton detection ready for offline testing"
    echo "  Test with: cd src/cotton_detection_ros2/scripts && python3 test_with_images.py --image /path/to/image.jpg --visualize"
else
    # Launch with camera
    start_node "ros2 run cotton_detection_ros2 cotton_detection_node" \
              "Cotton Detection (Live Camera)" \
              "/tmp/pragati_cotton_detection.log"
fi

# 5. Start Yanthra Move (Main Controller)
print_header "Step 4: Yanthra Move Control System"

# Prepare configuration
CONFIG_FILE="$WORKSPACE_ROOT/src/yanthra_move/config/production.yaml"
CONTINUOUS_PARAM="continuous_operation:=$([ "$CONTINUOUS_MODE" = true ] && echo "true" || echo "false")"

if [ -f "$CONFIG_FILE" ]; then
    print_step "Using configuration: $CONFIG_FILE"
    print_step "Mode: $([ "$CONTINUOUS_MODE" = true ] && echo "Continuous Operation" || echo "Single Run")"

    # Note: yanthra_move expects motor_control services, not odrive
    # It will wait for motor_control_ros2 services to become available
    start_node "ros2 run yanthra_move yanthra_move_node --ros-args --params-file $CONFIG_FILE -p $CONTINUOUS_PARAM -p simulation_mode:=true" \
              "Yanthra Move Controller" \
              "/tmp/pragati_yanthra_move.log"

    # Check if it's waiting for services
    sleep 3
    if grep -q "waiting for.*service" /tmp/pragati_yanthra_move.log 2>/dev/null; then
        echo ""
        print_warning "Yanthra Move is waiting for motor controller services"
        print_warning "Note: Motor controller node (mg6010_controller_node) needs to be built"
        print_warning "      Rebuild with: ./build.sh --clean"
        echo ""
        print_step "System will continue in simulation mode..."
    fi
else
    print_warning "Config file not found: $CONFIG_FILE"
    print_step "Starting with default parameters..."
    start_node "ros2 run yanthra_move yanthra_move_node --ros-args -p $CONTINUOUS_PARAM -p simulation_mode:=true" \
              "Yanthra Move Controller" \
              "/tmp/pragati_yanthra_move.log"
fi

# Wait for nodes to initialize
print_header "System Status"
sleep 5

# Show active nodes
echo ""
print_step "Active ROS2 Nodes:"
ros2 node list 2>/dev/null | while read node; do
    echo "  ✅ $node"
done

# Show topics
echo ""
print_step "Key Topics:"
ros2 topic list 2>/dev/null | grep -E "(joint|cotton|camera)" | while read topic; do
    echo "  📡 $topic"
done

# Show services
echo ""
print_step "Available Services:"
ros2 service list 2>/dev/null | grep -E "(joint|motor|cotton)" | head -10 | while read service; do
    echo "  🛠️  $service"
done

# Final instructions
echo ""
print_header "System Ready!"

if [ "$LAUNCH_DASHBOARD" = true ]; then
    echo ""
    echo "🌐 Web Dashboard: http://localhost:$WEB_PORT"
    echo "   - Real-time node monitoring"
    echo "   - Topic visualization"
    echo "   - Service interface"
    echo "   - System health metrics"
fi

echo ""
echo "📋 System Logs:"
echo "   Dashboard:        /tmp/pragati_dashboard.log"
echo "   Cotton Detection: /tmp/pragati_cotton_detection.log"
echo "   Yanthra Move:     /tmp/pragati_yanthra_move.log"

echo ""
echo "🔧 Quick Commands:"
echo "   Check nodes:    ros2 node list"
echo "   Check topics:   ros2 topic list"
echo "   Monitor status: ros2 topic echo /yanthra/status"

if [ "$OFFLINE_COTTON" = true ]; then
    echo ""
    echo "🧪 Offline Cotton Testing:"
    echo "   cd src/cotton_detection_ros2/scripts"
    echo "   python3 test_with_images.py --image /path/to/image.jpg --visualize"
fi

echo ""
echo "Press Ctrl+C to shutdown the system"
echo ""

# Keep running
while true; do
    sleep 10

    # Periodic health check
    if ! pgrep -f "ros2" > /dev/null; then
        print_error "No ROS2 processes running - system may have crashed"
        echo "Check logs above for errors"
        break
    fi
done
