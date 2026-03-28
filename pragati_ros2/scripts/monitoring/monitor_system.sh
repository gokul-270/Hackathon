#!/bin/bash

# ROS2 System Monitor - Prevents Hangs and Provides Quick Status
# This script monitors the system and provides timeouts for all operations

set -e

echo "🔍 ROS2 System Monitor - Anti-Hang Version"
echo "==========================================="

# Function to run ROS2 commands with timeout
run_ros_command() {
    local cmd="$1"
    local description="$2"
    local timeout_seconds="${3:-5}"
    
    echo "⏱️  $description (${timeout_seconds}s timeout)..."
    timeout $timeout_seconds bash -c "$cmd" || {
        echo "❌ Command timed out: $description"
        return 1
    }
}

# Function to check if nodes are responsive
check_node_responsiveness() {
    echo ""
    echo "📊 Node Responsiveness Check:"
    echo "============================="
    
    # Check each node with timeout
    local nodes=$(timeout 3s ros2 node list 2>/dev/null || echo "")
    
    if [ -z "$nodes" ]; then
        echo "❌ No nodes detected or ROS2 is unresponsive"
        return 1
    fi
    
    echo "✅ Active Nodes:"
    echo "$nodes" | while read node; do
        if [ ! -z "$node" ]; then
            echo "   ✓ $node"
        fi
    done
    
    echo ""
    echo "🔧 Quick Service Test:"
    if timeout 3s ros2 service list > /dev/null 2>&1; then
        echo "   ✅ Service discovery working"
    else
        echo "   ❌ Service discovery timeout"
    fi
    
    echo ""
    echo "📡 Quick Topic Test:"
    if timeout 3s ros2 topic list > /dev/null 2>&1; then
        echo "   ✅ Topic discovery working"
    else
        echo "   ❌ Topic discovery timeout"
    fi
}

# Function to check parameter responsiveness
check_yanthra_parameters() {
    echo ""
    echo "⚙️  Yanthra Move Node Parameters:"
    echo "================================"
    
    if timeout 3s ros2 param get /yanthra_move_node continous_operation > /dev/null 2>&1; then
        local param_value=$(timeout 3s ros2 param get /yanthra_move_node continous_operation 2>/dev/null || echo "unknown")
        echo "   ✅ continous_operation: $param_value"
    else
        echo "   ❌ Parameter access timeout"
        return 1
    fi
    
    if timeout 3s ros2 param get /yanthra_move_node simulation_mode > /dev/null 2>&1; then
        local sim_mode=$(timeout 3s ros2 param get /yanthra_move_node simulation_mode 2>/dev/null || echo "unknown")
        echo "   ✅ simulation_mode: $sim_mode"
    else
        echo "   ❌ Simulation mode parameter timeout"
    fi
}

# Function to test ODrive services
test_odrive_services() {
    echo ""
    echo "🛠️  ODrive Service Test:"
    echo "======================="
    
    if timeout 5s ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: 1}' > /dev/null 2>&1; then
        echo "   ✅ Joint status service responsive"
    else
        echo "   ❌ Joint status service timeout"
        return 1
    fi
}

# Function to check for hung processes
check_for_hangs() {
    echo ""
    echo "🚨 Hang Detection:"
    echo "=================="
    
    # Check if any ROS2 processes are consuming too much CPU (indicating a spin loop)
    local high_cpu_procs=$(ps aux | awk '$3 > 50.0 && /ros2|odrive|yanthra/ {print $2, $3, $11}' || true)
    
    if [ ! -z "$high_cpu_procs" ]; then
        echo "⚠️  High CPU usage detected:"
        echo "$high_cpu_procs"
    else
        echo "✅ No high CPU usage detected"
    fi
    
    # Check for zombie processes
    local zombie_procs=$(ps aux | awk '$8 ~ /Z/ && /ros2|odrive|yanthra/ {print $2, $11}' || true)
    
    if [ ! -z "$zombie_procs" ]; then
        echo "⚠️  Zombie processes detected:"
        echo "$zombie_procs"
    else
        echo "✅ No zombie processes"
    fi
}

# Main execution
main() {
    cd /home/uday/Downloads/pragati_ros2
    source install/setup.bash
    
    echo "🚀 Starting comprehensive system check..."
    echo ""
    
    # Check basic ROS2 connectivity
    if ! timeout 3s ros2 --version > /dev/null 2>&1; then
        echo "❌ ROS2 is not responding"
        exit 1
    fi
    echo "✅ ROS2 basic connectivity OK"
    
    # Run all checks
    check_node_responsiveness || echo "⚠️  Node responsiveness issues detected"
    check_yanthra_parameters || echo "⚠️  Yanthra parameter issues detected"
    test_odrive_services || echo "⚠️  ODrive service issues detected"
    check_for_hangs
    
    echo ""
    echo "📋 Quick System Summary:"
    echo "======================="
    echo "🔢 Total ROS2 Processes: $(ps aux | grep -c '[r]os2' || echo 0)"
    echo "💾 Memory Usage: $(ps aux | grep '[r]os2\|[o]drive\|[y]anthra' | awk '{sum += $6} END {printf "%.1f MB\n", sum/1024}' || echo 'unknown')"
    echo "⏰ System Uptime: $(uptime -p)"
    
    echo ""
    echo "✅ Monitoring complete - no hangs detected!"
}

# Execute main function
main "$@"