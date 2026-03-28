#!/bin/bash
##############################################################################
# Gazebo Simulation Test Script
# Tests the Gazebo simulation setup for robot_description package
##############################################################################

set -e

echo "========================================="
echo "Robot Description Gazebo Setup Test"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to print test result
test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}: $2"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: $2"
        ((TESTS_FAILED++))
    fi
}

echo "1. Checking ROS2 Environment..."
if [ -z "$ROS_DISTRO" ]; then
    echo -e "${YELLOW}⚠ ROS2 not sourced. Sourcing setup.bash...${NC}"
    source /home/vasanthakumar/pragati_ros2/install/setup.bash
fi
test_result $? "ROS2 environment"
echo "   ROS_DISTRO: $ROS_DISTRO"
echo ""

echo "2. Checking Gazebo Installation..."
if command -v gz &> /dev/null; then
    GZ_VERSION=$(gz sim --versions 2>&1 | head -1)
    test_result 0 "Gazebo installed"
    echo "   Version: $GZ_VERSION"
else
    test_result 1 "Gazebo installation"
fi
echo ""

echo "3. Checking Required ROS2 Packages..."
REQUIRED_PKGS=("ros_gz_sim" "ros_gz_bridge" "gz_ros2_control" "robot_description")
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ros2 pkg list | grep -q "^${pkg}$"; then
        test_result 0 "Package: $pkg"
    else
        test_result 1 "Package: $pkg"
    fi
done
echo ""

echo "4. Checking URDF Files..."
URDF_DIR="/home/vasanthakumar/pragati_ros2/src/robot_description/urdf"
REQUIRED_URDF_FILES=("MG6010_gazebo.xacro" "materials.xacro" "gazebo_plugins.xacro" "ros2_control.xacro")
for file in "${REQUIRED_URDF_FILES[@]}"; do
    if [ -f "$URDF_DIR/$file" ]; then
        test_result 0 "URDF file: $file"
    else
        test_result 1 "URDF file: $file"
    fi
done
echo ""

echo "5. Checking Configuration Files..."
CONFIG_DIR="/home/vasanthakumar/pragati_ros2/src/robot_description/config"
if [ -f "$CONFIG_DIR/controllers.yaml" ]; then
    test_result 0 "controllers.yaml exists"
else
    test_result 1 "controllers.yaml exists"
fi
echo ""

echo "6. Checking Launch Files..."
LAUNCH_DIR="/home/vasanthakumar/pragati_ros2/src/robot_description/launch"
REQUIRED_LAUNCH_FILES=("gazebo_sim.launch.py" "display_gazebo.launch.py")
for file in "${REQUIRED_LAUNCH_FILES[@]}"; do
    if [ -f "$LAUNCH_DIR/$file" ]; then
        test_result 0 "Launch file: $file"
    else
        test_result 1 "Launch file: $file"
    fi
done
echo ""

echo "7. Checking World Files..."
WORLD_DIR="/home/vasanthakumar/pragati_ros2/src/robot_description/worlds"
if [ -f "$WORLD_DIR/default.sdf" ]; then
    test_result 0 "default.sdf exists"
else
    test_result 1 "default.sdf exists"
fi
echo ""

echo "8. Validating URDF Xacro..."
XACRO_FILE="$URDF_DIR/MG6010_gazebo.xacro"
if command -v xacro &> /dev/null; then
    if xacro "$XACRO_FILE" > /dev/null 2>&1; then
        test_result 0 "URDF Xacro validation"
    else
        test_result 1 "URDF Xacro validation (syntax error)"
    fi
else
    echo -e "${YELLOW}⚠ xacro not found, skipping validation${NC}"
fi
echo ""

echo "9. Checking ros2_control Configuration..."
if grep -q "joint_state_broadcaster" "$CONFIG_DIR/controllers.yaml" 2>/dev/null; then
    test_result 0 "joint_state_broadcaster config"
else
    test_result 1 "joint_state_broadcaster config"
fi

if grep -q "joint_trajectory_controller" "$CONFIG_DIR/controllers.yaml" 2>/dev/null; then
    test_result 0 "joint_trajectory_controller config"
else
    test_result 1 "joint_trajectory_controller config"
fi
echo ""

echo "10. Checking Package Build..."
INSTALL_DIR="/home/vasanthakumar/pragati_ros2/install/robot_description"
if [ -d "$INSTALL_DIR" ]; then
    test_result 0 "Package is built and installed"
else
    test_result 1 "Package build (run 'colcon build --packages-select robot_description')"
fi
echo ""

echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    echo ""
    echo "Your Gazebo simulation setup is ready!"
    echo ""
    echo "To launch the simulation, run:"
    echo "  ros2 launch robot_description gazebo_sim.launch.py"
    echo ""
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please fix the failing tests before running the simulation."
    echo ""
    exit 1
fi
