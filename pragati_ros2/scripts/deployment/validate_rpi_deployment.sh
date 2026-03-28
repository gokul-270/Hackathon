#!/bin/bash

################################################################################
# Pragati ROS2 - Raspberry Pi Deployment Validation Script
# 
# This script validates that the Raspberry Pi is properly configured for
# deploying the Pragati cotton picking robot system.
################################################################################

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

print_header() {
    echo ""
    print_status $BLUE "=========================================="
    print_status $BLUE "$1"
    print_status $BLUE "=========================================="
}

check_pass() {
    print_status $GREEN "✅ $1"
}

check_fail() {
    print_status $RED "❌ $1"
}

check_warn() {
    print_status $YELLOW "⚠️  $1"
}

# Initialize counters
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

print_header "Pragati ROS2 - Raspberry Pi Deployment Validation"
echo ""

# Phase 1: System Requirements
print_header "Phase 1: System Requirements"

# Check Raspberry Pi
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null || grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
    check_pass "Running on Raspberry Pi"
    ((PASS_COUNT++))
else
    check_warn "Not running on Raspberry Pi (may be OK for testing)"
    ((WARN_COUNT++))
fi

# Check RAM
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_RAM" -ge 3800 ]; then
    check_pass "Sufficient RAM: ${TOTAL_RAM}MB (>=4GB)"
    ((PASS_COUNT++))
else
    check_warn "Low RAM: ${TOTAL_RAM}MB (4GB+ recommended)"
    ((WARN_COUNT++))
fi

# Check disk space
DISK_AVAIL=$(df -BG / | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$DISK_AVAIL" -ge 10 ]; then
    check_pass "Sufficient disk space: ${DISK_AVAIL}GB available"
    ((PASS_COUNT++))
else
    check_fail "Insufficient disk space: ${DISK_AVAIL}GB (10GB+ required)"
    ((FAIL_COUNT++))
fi

# Check Ubuntu version
if command -v lsb_release &> /dev/null; then
    UBUNTU_VERSION=$(lsb_release -rs 2>/dev/null)
    if [[ "$UBUNTU_VERSION" == "24.04" ]]; then
        check_pass "Ubuntu 24.04 detected"
        ((PASS_COUNT++))
    else
        check_warn "Ubuntu $UBUNTU_VERSION (24.04 recommended)"
        ((WARN_COUNT++))
    fi
fi

# Phase 2: ROS2 Installation
print_header "Phase 2: ROS2 Installation"

# Check ROS2
if command -v ros2 &> /dev/null; then
    check_pass "ROS2 installed"
    ((PASS_COUNT++))
    
    # Check ROS2 version
    if [ -d "/opt/ros/jazzy" ]; then
        check_pass "ROS2 Jazzy detected"
        ((PASS_COUNT++))
    else
        check_warn "ROS2 Jazzy not found (other distro may work)"
        ((WARN_COUNT++))
    fi
else
    check_fail "ROS2 not installed"
    ((FAIL_COUNT++))
fi

# Check colcon
if command -v colcon &> /dev/null; then
    check_pass "colcon build tool installed"
    ((PASS_COUNT++))
else
    check_fail "colcon not installed"
    ((FAIL_COUNT++))
fi

# Check rosdep
if command -v rosdep &> /dev/null; then
    check_pass "rosdep installed"
    ((PASS_COUNT++))
else
    check_fail "rosdep not installed"
    ((FAIL_COUNT++))
fi

# Phase 3: Hardware Interfaces
print_header "Phase 3: Hardware Interfaces"

# Check CAN interface
if ip link show can0 &> /dev/null; then
    CAN_STATE=$(ip link show can0 | grep -o "state [A-Z]*" | awk '{print $2}')
    if [ "$CAN_STATE" == "UP" ]; then
        check_pass "CAN interface can0 is UP"
        ((PASS_COUNT++))
    else
        check_warn "CAN interface can0 exists but is $CAN_STATE"
        ((WARN_COUNT++))
    fi
else
    check_warn "CAN interface can0 not found (needs configuration)"
    ((WARN_COUNT++))
fi

# Check CAN utils
if command -v candump &> /dev/null; then
    check_pass "can-utils installed"
    ((PASS_COUNT++))
else
    check_fail "can-utils not installed"
    ((FAIL_COUNT++))
fi

# Check GPIO
if command -v gpiodetect &> /dev/null; then
    if gpiodetect | grep -q "gpiochip"; then
        check_pass "GPIO interface available"
        ((PASS_COUNT++))
    else
        check_warn "GPIO detected but no chips found"
        ((WARN_COUNT++))
    fi
else
    check_warn "GPIO tools (libgpiod) not installed"
    ((WARN_COUNT++))
fi

# Check SPI (for PiCAN)
if ls /dev/spi* &> /dev/null; then
    check_pass "SPI interface available"
    ((PASS_COUNT++))
else
    check_warn "SPI interface not found (needed for PiCAN hat)"
    ((WARN_COUNT++))
fi

# Phase 4: Python Dependencies
print_header "Phase 4: Python Dependencies"

# Check Python packages
PYTHON_PACKAGES=("opencv" "numpy" "can" "spidev" "pigpio")
for pkg in "${PYTHON_PACKAGES[@]}"; do
    if python3 -c "import ${pkg/opencv/cv2}" &> /dev/null; then
        check_pass "Python package: $pkg"
        ((PASS_COUNT++))
    else
        check_warn "Python package missing: $pkg"
        ((WARN_COUNT++))
    fi
done

# Phase 5: Workspace Status
print_header "Phase 5: Workspace Status"

# Check if in workspace
if [ -f "install/setup.bash" ]; then
    check_pass "Workspace built (install/setup.bash exists)"
    ((PASS_COUNT++))
    
    # Count packages
    PKG_COUNT=$(find install -name "package.xml" 2>/dev/null | wc -l)
    if [ "$PKG_COUNT" -ge 7 ]; then
        check_pass "All packages installed: $PKG_COUNT packages"
        ((PASS_COUNT++))
    else
        check_warn "Only $PKG_COUNT packages found (expected 7)"
        ((WARN_COUNT++))
    fi
else
    check_fail "Workspace not built (run: colcon build)"
    ((FAIL_COUNT++))
fi

# Check key executables (source workspace first)
if [ -f "install/setup.bash" ]; then
    source install/setup.bash 2>/dev/null
fi

# Check executables using ros2 pkg executables
if command -v ros2 &> /dev/null && [ -f "install/setup.bash" ]; then
    # Check yanthra_move_node
    if ros2 pkg executables yanthra_move 2>/dev/null | grep -q "yanthra_move_node"; then
        check_pass "Executable: yanthra_move_node"
        ((PASS_COUNT++))
    else
        check_fail "Executable missing: yanthra_move_node"
        ((FAIL_COUNT++))
    fi
    
    # Check cotton_detection_node
    if ros2 pkg executables cotton_detection_ros2 2>/dev/null | grep -q "cotton_detection_node"; then
        check_pass "Executable: cotton_detection_node"
        ((PASS_COUNT++))
    else
        check_fail "Executable missing: cotton_detection_node"
        ((FAIL_COUNT++))
    fi
    
    # Check odrive_service_node (might be in motor_control or separate package)
    if ros2 pkg executables motor_control_ros2 2>/dev/null | grep -q "odrive" || \
       find install -name "*odrive*" -type f 2>/dev/null | grep -q "odrive"; then
        check_pass "Executable: odrive_service_node"
        ((PASS_COUNT++))
    else
        check_warn "Executable not found: odrive_service_node (may not be needed)"
        ((WARN_COUNT++))
    fi
else
    check_fail "Cannot check executables (ROS2 or workspace not available)"
    ((FAIL_COUNT++))
    ((FAIL_COUNT++))
    ((FAIL_COUNT++))
fi

# Phase 6: Network Configuration
print_header "Phase 6: Network Configuration"

# Check network connectivity
if ping -c 1 8.8.8.8 &> /dev/null; then
    check_pass "Internet connectivity"
    ((PASS_COUNT++))
else
    check_warn "No internet connectivity (may be OK for operation)"
    ((WARN_COUNT++))
fi

# Check SSH
if systemctl is-active --quiet ssh; then
    check_pass "SSH service running"
    ((PASS_COUNT++))
else
    check_warn "SSH service not running"
    ((WARN_COUNT++))
fi

# Phase 7: Performance Check
print_header "Phase 7: Performance Check"

# Check CPU temperature
if command -v vcgencmd &> /dev/null; then
    TEMP=$(vcgencmd measure_temp | grep -o "[0-9]*\.[0-9]*")
    if (( $(echo "$TEMP < 70.0" | bc -l) )); then
        check_pass "CPU temperature: ${TEMP}°C (normal)"
        ((PASS_COUNT++))
    else
        check_warn "CPU temperature: ${TEMP}°C (warm)"
        ((WARN_COUNT++))
    fi
fi

# Check CPU throttling
if command -v vcgencmd &> /dev/null; then
    THROTTLED=$(vcgencmd get_throttled | cut -d= -f2)
    if [ "$THROTTLED" == "0x0" ]; then
        check_pass "No CPU throttling detected"
        ((PASS_COUNT++))
    else
        check_warn "CPU throttling detected: $THROTTLED"
        ((WARN_COUNT++))
    fi
fi

# Summary
print_header "Validation Summary"
echo ""
print_status $GREEN "✅ Passed:  $PASS_COUNT checks"
print_status $YELLOW "⚠️  Warnings: $WARN_COUNT checks"
print_status $RED "❌ Failed:  $FAIL_COUNT checks"
echo ""

# Final verdict
if [ "$FAIL_COUNT" -eq 0 ]; then
    if [ "$WARN_COUNT" -eq 0 ]; then
        print_status $GREEN "🎉 PERFECT! System is fully ready for deployment!"
        exit 0
    else
        print_status $YELLOW "✅ System is ready for deployment (some warnings)"
        print_status $YELLOW "   Review warnings above and fix if needed"
        exit 0
    fi
else
    print_status $RED "❌ System is NOT ready for deployment"
    print_status $RED "   Fix failed checks before proceeding"
    echo ""
    print_status $BLUE "📖 See: RASPBERRY_PI_DEPLOYMENT_GUIDE.md"
    exit 1
fi
