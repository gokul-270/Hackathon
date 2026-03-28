#!/bin/bash

################################################################################
# Pragati ROS2 - Quick Start Script
#
# This script guides new users through the complete setup process.
################################################################################

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

print_header() {
    echo ""
    print_status $PURPLE "=========================================="
    print_status $PURPLE "$1"
    print_status $PURPLE "=========================================="
    echo ""
}

print_header "🤖 PRAGATI COTTON PICKING ROBOT - ROS2"
print_status $CYAN "Welcome to the Pragati ROS2 system setup!"
echo ""
print_status $BLUE "This script will guide you through:"
print_status $YELLOW "  1. 📦 Installing dependencies"
print_status $YELLOW "  2. 🔧 Building the system"
print_status $YELLOW "  3. 🧪 Running tests"
print_status $YELLOW "  4. 🚀 Launching the robot"
echo ""

# Check ROS2 installation
print_status $CYAN "🔍 Checking ROS2 installation..."
if ! command -v ros2 &> /dev/null; then
    print_status $RED "❌ ROS2 not found!"
    echo ""
    print_status $YELLOW "Please install ROS2 Jazzy first:"
    print_status $BLUE "https://docs.ros.org/en/jazzy/Installation.html"
    echo ""
    print_status $YELLOW "After installing ROS2, run this script again."
    exit 1
fi

ROS_DISTRO=$(ros2 doctor --report | grep "distribution name" | awk '{print $3}' 2>/dev/null || echo "unknown")
print_status $GREEN "✅ ROS2 $ROS_DISTRO found"
echo ""

# Interactive setup
print_status $CYAN "🎯 Choose setup level:"
echo ""
echo "1) 🚀 Express Setup (recommended for first-time users)"
echo "2) 📋 Custom Setup (choose each step)"
echo "3) 🔧 Developers Only (skip to build)"
echo ""
read -p "Enter your choice (1-3): " setup_choice

echo ""

case $setup_choice in
    1)
        print_status $GREEN "🚀 Starting Express Setup..."

        # Step 1: Install dependencies
        print_header "STEP 1: Installing Dependencies"
        WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
        if [ -f "$WORKSPACE_ROOT/setup_ubuntu_dev.sh" ]; then
            "$WORKSPACE_ROOT/setup_ubuntu_dev.sh"
            if [ $? -ne 0 ]; then
                print_status $RED "Dependency installation failed"
                exit 1
            fi
        else
            print_status $YELLOW "setup_ubuntu_dev.sh not found, skipping..."
        fi

        # Step 2: Build system
        print_header "🔧 STEP 2: Building System"
        ./build.sh
        if [ $? -ne 0 ]; then
            print_status $RED "❌ Build failed"
            exit 1
        fi

        # Step 3: Quick test
        print_header "🧪 STEP 3: Quick Testing"
        ./test.sh --quick

        # Step 4: Launch options
        print_header "🚀 STEP 4: Launch Options"
        print_status $GREEN "✅ Setup complete! Choose what to do next:"
        echo ""
        echo "1) 🎮 Launch Interactive Terminal"
        echo "2) 🤖 Launch Complete Robot System"
        echo "3) 💻 Launch Simulation Mode"
        echo "4) 📚 Show Documentation"
        echo "5) 🏁 Exit"
        echo ""
        read -p "Enter your choice (1-5): " launch_choice

        case $launch_choice in
            1) ./launch.sh --terminal ;;
            2) ./launch.sh --complete ;;
            3) ./launch.sh --complete --simulation ;;
            4)
                print_status $CYAN "📚 Documentation:"
                print_status $BLUE "  • Complete Guide: README.md"
                print_status $BLUE "  • Version History: CHANGELOG.md"
                print_status $BLUE "  • Raspberry Pi: RASPBERRY_PI_DEPLOYMENT.md"
                ;;
            5) print_status $GREEN "👋 Thanks for using Pragati ROS2!" ;;
            *) print_status $YELLOW "Invalid choice. Exiting..." ;;
        esac
        ;;

    2)
        print_status $GREEN "📋 Starting Custom Setup..."

        # Ask for each step
        echo ""
        read -p "Install dependencies? (y/n): " install_deps_choice
        if [[ $install_deps_choice =~ ^[Yy]$ ]]; then
            print_header "Installing Dependencies"
            WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
            [ -f "$WORKSPACE_ROOT/setup_ubuntu_dev.sh" ] && "$WORKSPACE_ROOT/setup_ubuntu_dev.sh"
        fi

        echo ""
        read -p "Build system? (y/n): " build_system
        if [[ $build_system =~ ^[Yy]$ ]]; then
            print_header "🔧 Building System"
            ./build.sh
        fi

        echo ""
        read -p "Run tests? (y/n): " run_tests
        if [[ $run_tests =~ ^[Yy]$ ]]; then
            print_header "🧪 Running Tests"
            echo ""
            echo "Test options:"
            echo "1) Quick tests"
            echo "2) Complete test suite"
            read -p "Choose (1-2): " test_choice
            case $test_choice in
                1) ./test.sh --quick ;;
                2) ./test.sh --complete ;;
                *) print_status $YELLOW "Invalid choice, skipping tests..." ;;
            esac
        fi

        echo ""
        read -p "Launch system? (y/n): " launch_system
        if [[ $launch_system =~ ^[Yy]$ ]]; then
            ./launch.sh
        fi
        ;;

    3)
        print_status $GREEN "🔧 Developer Mode - Building only..."
        ./build.sh
        if [ $? -eq 0 ]; then
            print_status $GREEN "✅ Build complete!"
            print_status $CYAN "💡 Quick commands:"
            print_status $BLUE "  ./launch.sh              # Launch system"
            print_status $BLUE "  ./test.sh --quick         # Quick tests"
            print_status $BLUE "  ./scripts/terminal_interface.py  # Terminal"
        fi
        ;;

    *)
        print_status $RED "❌ Invalid choice. Exiting..."
        exit 1
        ;;
esac

echo ""
print_header "🎉 SETUP COMPLETE"
print_status $GREEN "Your Pragati ROS2 system is ready!"
echo ""
print_status $CYAN "💡 Quick Reference:"
print_status $BLUE "  ./launch.sh               # Launch system"
print_status $BLUE "  ./test.sh                 # Run tests"
print_status $BLUE "  ./build.sh --clean        # Clean build"
print_status $BLUE "  less README.md            # Read documentation"
echo ""
print_status $YELLOW "🍓 For Raspberry Pi deployment, see RASPBERRY_PI_DEPLOYMENT.md"
print_status $GREEN "🎯 Happy robotics! 🤖"
