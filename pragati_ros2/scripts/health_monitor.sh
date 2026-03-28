#!/bin/bash

# Real-time System Health Monitor
# Monitors ROS2 nodes, topics, services, and hardware status

monitor_system_health() {
    echo "🏥 System Health Monitor"
    echo "======================="
    
    while true; do
        clear
        echo "🕒 $(date)"
        echo "========================="
        
        # ROS2 System Status
        echo "🤖 ROS2 System Status:"
        local node_count=$(ros2 node list 2>/dev/null | wc -l)
        local topic_count=$(ros2 topic list 2>/dev/null | wc -l)
        local service_count=$(ros2 service list 2>/dev/null | wc -l)
        
        echo "  Nodes: $node_count"
        echo "  Topics: $topic_count" 
        echo "  Services: $service_count"
        
        # Vehicle Control Status
        echo ""
        echo "🚗 Vehicle Control Status:"
        if ros2 node list 2>/dev/null | grep -q vehicle_control_node; then
            echo "  ✅ Vehicle Control Node: RUNNING"
            if ros2 param list /vehicle_control_node 2>/dev/null | grep -q joint_names; then
                echo "  ✅ Parameters: ACCESSIBLE"
            else
                echo "  ⚠️ Parameters: INITIALIZING"
            fi
        else
            echo "  ❌ Vehicle Control Node: NOT RUNNING"
        fi
        
        # Hardware Status
        echo ""
        echo "🔧 Hardware Status:"
        if [ -c "/dev/can0" ]; then
            echo "  ✅ CAN Bus: AVAILABLE"
        else
            echo "  ⚠️ CAN Bus: NOT AVAILABLE (simulation mode)"
        fi
        
        if [ -d "/sys/class/gpio" ]; then
            echo "  ✅ GPIO: AVAILABLE"
        else
            echo "  ⚠️ GPIO: NOT AVAILABLE"
        fi
        
        # System Resources
        echo ""
        echo "📊 System Resources:"
        local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')
        local mem_usage=$(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')
        echo "  CPU: ${cpu_usage}%"
        echo "  Memory: ${mem_usage}"
        
        echo ""
        echo "Press Ctrl+C to exit"
        sleep 5
    done
}

# Quick health check
quick_health_check() {
    echo "🏥 Quick Health Check"
    echo "===================="
    
    # Build status
    if [ -f "install/setup.bash" ]; then
        echo "✅ Build: SUCCESS - Project built and ready"
        # Package discovery with built packages
        source install/setup.bash 2>/dev/null
        local pkg_count=$(ros2 pkg list 2>/dev/null | wc -l)
        echo "✅ Packages: $pkg_count discoverable (including built packages)"
    else
        echo "⚠️  Build: Not built yet (normal for fresh checkout)"
        # Package discovery without built packages
        local pkg_count=$(ros2 pkg list 2>/dev/null | wc -l)
        echo "✅ Base Packages: $pkg_count discoverable (ROS2 system packages)"
        echo "ℹ️  Note: Run './build.sh' to build project packages"
    fi
    
    # Source code availability
    echo ""
    echo "📝 Source Code Status:"
    if [ -d "src/vehicle_control" ]; then
        echo "✅ Vehicle Control: Source code available"
    else
        echo "❌ Vehicle Control: Source code not found"
    fi
    
    if [ -d "src/odrive_control_ros2" ]; then
        echo "✅ ODrive Control: Source code available"
    else
        echo "❌ ODrive Control: Source code not found"
    fi
    
    if [ -d "src/yanthra_move" ]; then
        echo "✅ Yanthra Move: Source code available"
    else
        echo "❌ Yanthra Move: Source code not found"
    fi
    
    # Configuration files
    echo ""
    echo "⚙️  Configuration Status:"
    if [ -f "src/vehicle_control/config/vehicle_params.yaml" ]; then
        echo "✅ Vehicle Config: Found"
    else
        echo "⚠️  Vehicle Config: Not found"
    fi
    
    if [ -f "src/yanthra_move/config/yanthra_move_picking_ros2.yaml" ]; then
        echo "✅ Yanthra Config: Found"
    else
        echo "⚠️  Yanthra Config: Not found"
    fi
}

main() {
    case "${1:-quick}" in
        "monitor"|"live")
            monitor_system_health
            ;;
        "quick"|"check")
            quick_health_check
            ;;
        *)
            echo "Usage: $0 [quick|monitor]"
            echo "  quick   - Quick health check"
            echo "  monitor - Live monitoring dashboard"
            ;;
    esac
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    main "$@"
fi