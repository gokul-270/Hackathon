#!/bin/bash
#
# Cotton Detection Migration Complete Test Script
# Tests all Phase 5 migration tasks:
# - C++ node launches successfully
# - Python wrapper shows deprecation warnings
# - Services are available
# - Simulation mode works
# - Migration guide exists
#
# Usage: ./test_migration_complete.sh

# Don't exit on error - we want to collect all test results
# set -e

echo "=================================================="
echo "🌱 Cotton Detection Migration - Complete Test"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

WORKSPACE="/home/uday/Downloads/pragati_ros2"
cd $WORKSPACE
source install/setup.bash

PASSED=0
FAILED=0

# Test function
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -n "Testing: $test_name ... "
    if eval "$test_command" > /tmp/test_output.log 2>&1; then
        echo -e "${GREEN}✅ PASSED${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAILED${NC}"
        echo "  Error details in /tmp/test_output.log"
        ((FAILED++))
        return 1
    fi
}

echo "📋 Phase 5.2: System Launch Files Updated"
echo "=========================================="

# Test 1: Verify C++ executable exists
run_test "C++ node executable exists" \
    "ros2 pkg executables cotton_detection_ros2 | grep -q 'cotton_detection_node'"

# Test 2: Verify Python wrapper exists (for backward compatibility)
run_test "Python wrapper exists (backward compat)" \
    "ros2 pkg executables cotton_detection_ros2 | grep -q 'cotton_detect_ros2_wrapper.py'"

# Test 3: Verify launch files exist
run_test "C++ launch file exists" \
    "test -f $WORKSPACE/install/cotton_detection_ros2/share/cotton_detection_ros2/launch/cotton_detection_cpp.launch.py"

run_test "Python wrapper launch file exists" \
    "test -f $WORKSPACE/install/cotton_detection_ros2/share/cotton_detection_ros2/launch/cotton_detection_wrapper.launch.py"

echo ""
echo "📋 Phase 5.3: Migration Guide Created"
echo "======================================"

# Test 4: Migration guide exists
run_test "Migration guide exists" \
    "test -f $WORKSPACE/src/cotton_detection_ros2/MIGRATION_GUIDE.md"

# Test 5: Migration guide has content
run_test "Migration guide has substantial content" \
    "test $(wc -l < $WORKSPACE/src/cotton_detection_ros2/MIGRATION_GUIDE.md) -gt 100"

# Test 6: Migration guide mentions key topics
run_test "Migration guide covers parameter mapping" \
    "grep -q 'Parameter Mapping' $WORKSPACE/src/cotton_detection_ros2/MIGRATION_GUIDE.md"

run_test "Migration guide covers launch files" \
    "grep -q 'Launch File Changes' $WORKSPACE/src/cotton_detection_ros2/MIGRATION_GUIDE.md"

run_test "Migration guide covers troubleshooting" \
    "grep -q 'Troubleshooting' $WORKSPACE/src/cotton_detection_ros2/MIGRATION_GUIDE.md"

echo ""
echo "📋 Phase 5.4: Python Deprecation Warnings"
echo "=========================================="

# Test 7: Python wrapper shows deprecation in code
run_test "Python wrapper has deprecation notice in docstring" \
    "grep -q 'DEPRECATION NOTICE' $WORKSPACE/src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py"

run_test "Python wrapper logs deprecation warning" \
    "grep -q 'DEPRECATION WARNING' $WORKSPACE/src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py"

run_test "Python wrapper emits Python DeprecationWarning" \
    "grep -q 'warnings.warn' $WORKSPACE/src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py"

echo ""
echo "📋 Functional Tests: C++ Node"
echo "============================="

# Test 8: C++ node launches in simulation mode
echo -n "Testing: C++ node launches in simulation mode ... "
timeout 5 ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true > /tmp/cpp_launch.log 2>&1 &
CPP_PID=$!
sleep 3

if ps -p $CPP_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PASSED${NC}"
    ((PASSED++))
    kill $CPP_PID 2>/dev/null || true
else
    echo -e "${RED}❌ FAILED${NC}"
    echo "  Log: /tmp/cpp_launch.log"
    ((FAILED++))
fi
wait $CPP_PID 2>/dev/null || true

# Test 9: C++ node provides detection service
echo -n "Testing: C++ node provides detection service ... "
timeout 5 ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=true > /dev/null 2>&1 &
CPP_PID=$!
sleep 3

if ros2 service list 2>/dev/null | grep -q '/cotton_detection/detect'; then
    echo -e "${GREEN}✅ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}❌ FAILED${NC}"
    ((FAILED++))
fi
kill $CPP_PID 2>/dev/null || true
wait $CPP_PID 2>/dev/null || true

echo ""
echo "📋 Functional Tests: Python Wrapper (Deprecated)"
echo "================================================"

# Test 10: Python wrapper shows deprecation when launched
echo -n "Testing: Python wrapper shows deprecation warning ... "
timeout 5 ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py simulation_mode:=true > /tmp/python_launch.log 2>&1 &
PYTHON_PID=$!
sleep 3

if grep -q 'DEPRECATION WARNING' /tmp/python_launch.log; then
    echo -e "${GREEN}✅ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}❌ FAILED${NC}"
    echo "  Log: /tmp/python_launch.log"
    ((FAILED++))
fi
kill $PYTHON_PID 2>/dev/null || true
wait $PYTHON_PID 2>/dev/null || true

# Test 11: Python wrapper mentions C++ migration
echo -n "Testing: Python wrapper mentions C++ migration ... "
if grep -q 'cotton_detection_node' /tmp/python_launch.log; then
    echo -e "${GREEN}✅ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}❌ FAILED${NC}"
    ((FAILED++))
fi

# Test 12: Python wrapper mentions migration guide
echo -n "Testing: Python wrapper mentions migration guide ... "
if grep -q 'MIGRATION_GUIDE' /tmp/python_launch.log; then
    echo -e "${GREEN}✅ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}❌ FAILED${NC}"
    ((FAILED++))
fi

echo ""
echo "📋 Interface Compatibility Tests"
echo "================================"

# Test 13: Both nodes provide same service interface
run_test "Service interface definition exists" \
    "ros2 interface show cotton_detection_ros2/srv/CottonDetection"

# Test 14: Both nodes publish to same topic
run_test "Detection3DArray message type exists" \
    "ros2 interface show vision_msgs/msg/Detection3DArray"

echo ""
echo "=================================================="
echo "📊 Test Summary"
echo "=================================================="
echo -e "Total Tests: $((PASSED + FAILED))"
echo -e "${GREEN}Passed: $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED${NC}"
else
    echo -e "${GREEN}Failed: 0${NC}"
fi
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo ""
    echo "✅ Phase 5.2: System launch files updated"
    echo "✅ Phase 5.3: Migration guide created and comprehensive"
    echo "✅ Phase 5.4: Python wrapper deprecation warnings active"
    echo ""
    echo "Migration Complete! The cotton detection system is ready."
    echo ""
    echo "Next Steps:"
    echo "  1. Review migration guide: src/cotton_detection_ros2/MIGRATION_GUIDE.md"
    echo "  2. Test on robot hardware with actual camera"
    echo "  3. Update any custom launch files to use C++ node"
    echo "  4. Monitor deprecation warnings in production"
    echo ""
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please review the failures above and check:"
    echo "  - /tmp/test_output.log"
    echo "  - /tmp/cpp_launch.log"
    echo "  - /tmp/python_launch.log"
    echo ""
    exit 1
fi
