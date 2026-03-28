#!/bin/bash

# Pragati ROS2 Quick Commands
# Provides ROS1-style terminal commands for easy migration
# Date: September 10, 2025

echo "🎛️  Pragati ROS2 Quick Commands"
echo "================================"

# Function to move joint (like ROS1 rostopic pub)
move_joint() {
    if [ $# -ne 2 ]; then
        echo "Usage: move_joint <joint_id> <position>"
        echo "Example: move_joint 2 0.5"
        return 1
    fi
    
    joint_id=$1
    position=$2
    
    echo "📤 Moving Joint$joint_id to $position radians..."
    ros2 topic pub --once /joint${joint_id}_position_controller/command std_msgs/msg/Float64 "data: $position"
    
    # Show feedback
    sleep 0.5
    echo "📍 Current joint positions:"
    ros2 topic echo --once /joint_states | grep -A 20 "position:" | head -10
}

# Function to home joint (like ROS1 rosservice call)
home_joint() {
    if [ $# -ne 1 ]; then
        echo "Usage: home_joint <joint_id>"
        echo "Example: home_joint 2"
        return 1
    fi
    
    joint_id=$1
    
    echo "🏠 Homing Joint$joint_id..."
    ros2 service call /joint_homing odrive_control_ros2/srv/JointHoming "{homing_required: true, joint_id: $joint_id}"
}

# Function to set joint idle
idle_joint() {
    if [ $# -ne 1 ]; then
        echo "Usage: idle_joint <joint_id>"
        echo "Example: idle_joint 2"
        return 1
    fi
    
    joint_id=$1
    
    echo "😴 Setting Joint$joint_id to idle..."
    ros2 service call /joint_idle odrive_control_ros2/srv/JointHoming "{homing_required: false, joint_id: $joint_id}"
}

# Function to show current positions
show_positions() {
    echo "📊 Current joint positions:"
    ros2 topic echo --once /joint_states
}

# Function to monitor joint states in real-time
monitor_joints() {
    echo "📈 Monitoring joint states (Ctrl+C to stop):"
    ros2 topic echo /joint_states
}

# Function to show available topics
show_topics() {
    echo "📋 Available ROS2 topics:"
    ros2 topic list
}

# Function to show available services
show_services() {
    echo "🛠️  Available ROS2 services:"
    ros2 service list
}

# Quick command examples
quick_demo() {
    echo "🎮 Quick Demo Commands:"
    echo ""
    echo "# Initialize all joints (like ROS1 InitialiseJoints.sh)"
    echo "home_joint 2"
    echo "home_joint 3" 
    echo "home_joint 4"
    echo "home_joint 5"
    echo ""
    echo "# Move joints to specific positions"
    echo "move_joint 2 0.5    # Move joint2 to 0.5 radians"
    echo "move_joint 3 -1.2   # Move joint3 to -1.2 radians"
    echo "move_joint 4 1.57   # Move joint4 to 90 degrees"
    echo "move_joint 5 0.0    # Move joint5 to home position"
    echo ""
    echo "# Monitor system"
    echo "show_positions      # Show current positions"
    echo "monitor_joints      # Real-time monitoring"
    echo ""
}

# Help function
show_help() {
    echo ""
    echo "🎛️  PRAGATI ROS2 TERMINAL COMMANDS"
    echo "=================================="
    echo ""
    echo "JOINT MOVEMENT (like ROS1 rostopic pub):"
    echo "  move_joint <joint_id> <position>  - Move joint to position"
    echo ""
    echo "JOINT CONTROL (like ROS1 rosservice call):"
    echo "  home_joint <joint_id>              - Home joint to limit switch"
    echo "  idle_joint <joint_id>              - Set joint to idle"
    echo ""
    echo "MONITORING:"
    echo "  show_positions                     - Show current positions"
    echo "  monitor_joints                     - Real-time joint monitoring"
    echo "  show_topics                        - List available topics"
    echo "  show_services                      - List available services"
    echo ""
    echo "EXAMPLES:"
    echo "  move_joint 2 0.5                   # Move joint2 to 0.5 rad"
    echo "  home_joint 3                       # Home joint3"
    echo "  quick_demo                         # Show demo commands"
    echo ""
    echo "ROS1 → ROS2 EQUIVALENT:"
    echo "  ROS1: rostopic pub /joint2_position_controller/command std_msgs/Float64 'data: 0.5'"
    echo "  ROS2: move_joint 2 0.5"
    echo ""
    echo "  ROS1: rosservice call /odrive_control/joint_init_to_home 2"
    echo "  ROS2: home_joint 2"
    echo ""
}

# Check if function name is provided
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Execute the requested function
case "$1" in
    "move_joint")
        shift
        move_joint "$@"
        ;;
    "home_joint")
        shift
        home_joint "$@"
        ;;
    "idle_joint")
        shift
        idle_joint "$@"
        ;;
    "show_positions")
        show_positions
        ;;
    "monitor_joints")
        monitor_joints
        ;;
    "show_topics")
        show_topics
        ;;
    "show_services")
        show_services
        ;;
    "quick_demo")
        quick_demo
        ;;
    "help"|"-h"|"--help")
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "   Use 'help' to see available commands"
        exit 1
        ;;
esac
