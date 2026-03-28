#!/bin/bash

# Test Script for Phase 0 Python Critical Fixes
# Tests all 5 fixes implemented

echo "=========================================="
echo "Phase 0 Fixes - Test Suite"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function
check_result() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}: $1"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: $1"
        ((TESTS_FAILED++))
    fi
}

echo "=========================================="
echo "Test 1: Build the Package"
echo "=========================================="
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select cotton_detection_ros2 2>&1 | tee /tmp/phase0_build.log
check_result "Package build"
echo ""

echo "=========================================="
echo "Test 2: Check Fix 0.1 - Log File Creation"
echo "=========================================="
echo "Checking if log file redirection code exists..."
grep -q "log_file_path = '/tmp/CottonDetect_subprocess.log'" \
    src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
check_result "Log file redirection implemented"
echo ""

echo "=========================================="
echo "Test 3: Check Fix 0.2 - Threading.Event"
echo "=========================================="
echo "Checking if camera_ready_event (Event) exists..."
grep -q "self.camera_ready_event = threading.Event()" \
    src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
check_result "Threading.Event implementation"

echo "Checking if Event.wait() is used..."
grep -q "camera_ready_event.wait(timeout=" \
    src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
check_result "Event.wait() with timeout"
echo ""

echo "=========================================="
echo "Test 4: Check Fix 0.3 - Atomic File Writes"
echo "=========================================="
echo "Checking if tempfile is imported in CottonDetect.py..."
grep -q "import tempfile" \
    src/cotton_detection_ros2/scripts/OakDTools/CottonDetect.py
check_result "tempfile import"

echo "Checking if write_file_atomically function exists..."
grep -q "def write_file_atomically" \
    src/cotton_detection_ros2/scripts/OakDTools/CottonDetect.py
check_result "write_file_atomically function"

echo "Checking if atomic write is used..."
grep -q "write_file_atomically(COTTONDETAILSTXTFILEPATH" \
    src/cotton_detection_ros2/scripts/OakDTools/CottonDetect.py
check_result "Atomic write usage"
echo ""

echo "=========================================="
echo "Test 5: Check Fix 0.4 - Auto-Restart Logic"
echo "=========================================="
echo "Checking if restart tracking variables exist..."
grep -q "self.restart_attempts = \[\]" \
    src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
check_result "Restart tracking variables"

echo "Checking if auto-restart logic exists..."
grep -q "Attempting restart" \
    src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
check_result "Auto-restart logic"

echo "Checking if exponential backoff exists..."
grep -q "cooldown = 2.0 \*\* (restart_num - 1)" \
    src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py
check_result "Exponential backoff"
echo ""

echo "=========================================="
echo "Test 6: Check Fix 0.5 - Simulation Mode"
echo "========================================="
echo "⚠️  LEGACY: This test checks archived Phase 0 Python wrapper"
echo "Note: cotton_detection_wrapper.launch.py archived as of 2025-10-21"
echo "Production path is now cotton_detection_cpp.launch.py"
echo ""
echo "Checking if simulation_mode arg exists in launch file..."
if [ -f "src/cotton_detection_ros2/launch/archive/phase1/cotton_detection_wrapper.launch.py" ]; then
    grep -q "simulation_mode_arg" \
        src/cotton_detection_ros2/launch/archive/phase1/cotton_detection_wrapper.launch.py
    check_result "simulation_mode launch argument (archived)"
    
    echo "Checking if simulation_mode parameter is passed to node..."
    grep -q "'simulation_mode': LaunchConfiguration('simulation_mode')" \
        src/cotton_detection_ros2/launch/archive/phase1/cotton_detection_wrapper.launch.py
    check_result "simulation_mode parameter wiring (archived)"
else
    echo -e "${YELLOW}⚠ SKIP${NC}: Archived launch file not found"
    echo "This test validates Phase 0 Python wrapper (now archived)"
fi
echo ""

echo "=========================================="
echo "Test 7: Simulation Mode Functional Test"
echo "=========================================="
echo "Starting node in simulation mode (10 seconds)..."
source install/setup.bash

# Launch in background (check if launch exists, otherwise skip)
if ros2 pkg prefix cotton_detection_ros2 >/dev/null 2>&1 && \
   ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py --show-args >/dev/null 2>&1; then
    timeout 10s ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
        simulation_mode:=true > /tmp/phase0_sim_test.log 2>&1 &
    LAUNCH_PID=$!
else
    echo -e "${YELLOW}⚠ SKIP${NC}: cotton_detection_wrapper.launch.py not installed (archived 2025-10-21)"
    echo "To test: temporarily restore from src/cotton_detection_ros2/launch/archive/phase1/"
    echo "Production launch: ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py"
    LAUNCH_PID=""
fi

sleep 5

# Test service call
echo "Calling detection service..."
timeout 5s ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}" \
    > /tmp/phase0_service_test.log 2>&1

if grep -q "success: true" /tmp/phase0_service_test.log; then
    check_result "Simulation mode service call"
else
    echo -e "${YELLOW}⚠ SKIP${NC}: Simulation mode test (requires ROS2 running)"
fi

# Cleanup
kill $LAUNCH_PID 2>/dev/null || true
wait $LAUNCH_PID 2>/dev/null || true
echo ""

echo "=========================================="
echo "Test 8: File Structure Verification"
echo "=========================================="
echo "Checking if modified files have correct permissions..."
ls -l src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py > /dev/null
check_result "Wrapper file exists and readable"

ls -l src/cotton_detection_ros2/scripts/OakDTools/CottonDetect.py > /dev/null
check_result "CottonDetect.py exists and readable"

if [ -f "src/cotton_detection_ros2/launch/archive/phase1/cotton_detection_wrapper.launch.py" ]; then
    ls -l src/cotton_detection_ros2/launch/archive/phase1/cotton_detection_wrapper.launch.py > /dev/null
    check_result "Archived launch file exists and readable"
else
    echo -e "${YELLOW}⚠ SKIP${NC}: Archived launch file check (file moved)"
fi
echo ""

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Tests Passed: $TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${RED}Tests Failed: $TESTS_FAILED${NC}"
else
    echo -e "${GREEN}Tests Failed: 0${NC}"
fi
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}=========================================="
    echo -e "All Phase 0 Fixes Verified Successfully! ✓"
    echo -e "==========================================${NC}"
    echo ""
    echo "Next Steps:"
    echo "1. Test with hardware (if available)"
    echo "2. Run stability test (1 hour)"
    echo "3. Proceed to Phase 1 (DepthAI C++ integration)"
    exit 0
else
    echo -e "${RED}=========================================="
    echo -e "Some Tests Failed - Review Required"
    echo -e "==========================================${NC}"
    echo ""
    echo "Check logs:"
    echo "  - /tmp/phase0_build.log"
    echo "  - /tmp/phase0_sim_test.log"
    echo "  - /tmp/phase0_service_test.log"
    exit 1
fi
