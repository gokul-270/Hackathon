#!/bin/bash

# Test runner script for error handling framework
# This script builds and runs the error handling tests

set -e  # Exit on error

echo "🧪 Error Handling Framework Test Suite"
echo "======================================="

# Get the current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Working directory: $SCRIPT_DIR"

# Check if we're in the right directory
if [[ ! -f "$SCRIPT_DIR/src/odrive_control_ros2/test/test_error_handling.cpp" ]]; then
    echo "❌ Error: test_error_handling.cpp not found!"
    echo "   Please run this script from the pragati_ros2 root directory"
    exit 1
fi

echo ""
echo "🔨 Building the project..."
echo "=========================="

# Build the project
if colcon build --packages-select odrive_control_ros2 --cmake-args -DCMAKE_BUILD_TYPE=Debug; then
    echo "✅ Build successful!"
else
    echo "❌ Build failed!"
    exit 1
fi

echo ""
echo "📦 Sourcing the workspace..."
echo "============================"

# Source the workspace
if [[ -f "$SCRIPT_DIR/install/setup.bash" ]]; then
    source "$SCRIPT_DIR/install/setup.bash"
    echo "✅ Workspace sourced"
else
    echo "⚠️  Warning: install/setup.bash not found, continuing anyway..."
fi

echo ""
echo "🧪 Running Error Handling Tests..."
echo "=================================="

# Check if the test executable exists
TEST_EXECUTABLE="$SCRIPT_DIR/build/odrive_control_ros2/test_error_handling"
if [[ -f "$TEST_EXECUTABLE" ]]; then
    echo "✅ Test executable found: $TEST_EXECUTABLE"
    echo ""
    echo "🚀 Executing tests..."
    echo "--------------------"
    
    # Run the tests
    if "$TEST_EXECUTABLE"; then
        echo ""
        echo "🎉 All tests passed!"
    else
        echo ""
        echo "❌ Some tests failed!"
        exit 1
    fi
else
    echo "❌ Test executable not found: $TEST_EXECUTABLE"
    echo ""
    echo "🔍 Checking build directory:"
    find "$SCRIPT_DIR/build" -name "*test_error*" -type f 2>/dev/null || echo "   No test executables found"
    echo ""
    echo "💡 Possible solutions:"
    echo "   1. Install GTest: sudo apt-get install libgtest-dev"
    echo "   2. Clean rebuild: rm -rf build install log && colcon build --packages-select odrive_control_ros2"
    echo "   3. Check CMakeLists.txt for test configuration"
    exit 1
fi

echo ""
echo "🎯 Test Summary"
echo "=============="
echo "✅ Error handling framework tests completed successfully"
echo "✅ All components are working correctly"
echo ""
echo "📊 What was tested:"
echo "  - Error category enumeration"
echo "  - Error severity levels"
echo "  - ErrorFactory functionality (12 error types)"
echo "  - DefaultErrorHandler auto-recovery logic"
echo "  - Error recovery suggestions"
echo "  - MotorStatus enhanced structure"
echo "  - Performance testing (1000 errors)"
echo "  - Basic thread safety"
echo ""
echo "🚀 Ready for next enhancement phase!"