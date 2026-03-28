#!/bin/bash

################################################################################
# Pragati ROS2 - Simple Launch Script
# 
# This script provides easy launching options for the Pragati robot system.
################################################################################

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

# Check if workspace is built
if [ ! -f "install/setup.bash" ]; then
    print_status $RED "❌ Workspace not built. Run: ./build.sh"
    exit 1
fi

# Source the workspace
source install/setup.bash

print_status $BLUE "🚀 Pragati ROS2 Launch Options"
print_status $BLUE "=============================="
echo ""

# Parse command line arguments
MODE="interactive"
SIMULATION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --sim|--simulation)
            SIMULATION=true
            shift
            ;;
        --complete|--full)
            MODE="complete"
            shift
            ;;
        --minimal|--min)
            MODE="minimal"
            shift
            ;;
        --terminal|--interactive)
            MODE="terminal"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --complete     Launch complete system (default)"
            echo "  --minimal      Launch minimal system"
            echo "  --simulation   Run in simulation mode"
            echo "  --terminal     Launch interactive terminal only"
            echo "  --help         Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                          # Interactive mode"
            echo "  $0 --complete --simulation  # Complete system in simulation"
            echo "  $0 --terminal               # Terminal interface only"
            exit 0
            ;;
        *)
            print_status $RED "❌ Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Interactive mode if no specific mode chosen
if [ "$MODE" == "interactive" ]; then
    print_status $CYAN "🎯 Choose launch mode:"
    echo ""
    echo "1) Complete System (recommended)"
    echo "2) Minimal System" 
    echo "3) Terminal Interface Only"
    echo "4) Simulation Mode"
    echo ""
    read -p "Enter your choice (1-4): " choice
    
    case $choice in
        1) MODE="complete" ;;
        2) MODE="minimal" ;;
        3) MODE="terminal" ;;
        4) MODE="complete"; SIMULATION=true ;;
        *) 
            print_status $RED "❌ Invalid choice. Using complete mode."
            MODE="complete"
            ;;
    esac
fi

# Set simulation parameter
SIM_PARAM=""
if [ "$SIMULATION" = true ]; then
    SIM_PARAM="use_simulation:=true"
    print_status $YELLOW "⚠️  Running in SIMULATION mode"
fi

echo ""

# Launch based on selected mode
case $MODE in
    "complete")
        print_status $GREEN "🚀 Launching Complete Pragati System..."
        if [ "$SIMULATION" = true ]; then
            ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true
        else
            ros2 launch yanthra_move pragati_complete.launch.py
        fi
        ;;
    "minimal")
        print_status $GREEN "🚀 Launching Minimal System..."
        ros2 launch yanthra_move yanthra_move_minimal.launch.py $SIM_PARAM
        ;;
    "terminal")
        print_status $GREEN "🚀 Starting Interactive Terminal..."
        echo ""
        print_status $CYAN "💡 Terminal Commands Available:"
        print_status $YELLOW "   move_joint <joint_id> <position>"
        print_status $YELLOW "   home_joint <joint_id>"
        print_status $YELLOW "   idle_joint <joint_id>"
        print_status $YELLOW "   status"
        print_status $YELLOW "   quit"
        echo ""
        ./scripts/terminal_interface.py
        ;;
    *)
        print_status $RED "❌ Unknown mode: $MODE"
        exit 1
        ;;
esac
