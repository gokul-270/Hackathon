#!/bin/bash

# ===============================================================================
# YANTHRA ROBOTIC ARM SYSTEM - TEST SUITE MANAGER
# ===============================================================================
# 
# This script manages and executes the comprehensive test suite for all 
# implemented phases of the Yanthra robotic arm system modernization.
#
# Usage: ./tests/run_tests.sh [phase_number|all|list]
# Examples:
#   ./tests/run_tests.sh 2          # Run Phase 2 tests only
#   ./tests/run_tests.sh all        # Run all available tests
#   ./tests/run_tests.sh list       # List all available tests
#
# ===============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get the absolute path to the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTS_DIR="$PROJECT_ROOT/tests"

# Source ROS2 setup
cd "$PROJECT_ROOT"
source install/setup.bash

echo -e "${BLUE}===============================================================================${NC}"
echo -e "${BLUE}        YANTHRA ROBOTIC ARM SYSTEM - TEST SUITE MANAGER${NC}"
echo -e "${BLUE}===============================================================================${NC}"
echo ""

# Function to display available tests
list_tests() {
    echo -e "${CYAN}📋 AVAILABLE TEST PHASES:${NC}"
    echo ""
    
    echo -e "${GREEN}✅ COMPLETED PHASES:${NC}"
    echo -e "  ${GREEN}Phase 1a${NC}: START_SWITCH timeout and infinite loop fixes"
    echo -e "  ${GREEN}Phase 1b${NC}: START_SWITCH topic implementation"
    if [ -f "$TESTS_DIR/phase1/test_start_switch_topic.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase1/test_start_switch_topic.sh"
    fi
    
    echo -e "  ${GREEN}Phase 2${NC}: Parameter Type Safety & Validation Enhancement"
    if [ -f "$TESTS_DIR/phase2/test_phase2_validation.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase2/test_phase2_validation.sh"
    fi
    
    echo -e "  ${GREEN}Phase 3${NC}: Error Recovery & Resilience Mechanisms"
    if [ -f "$TESTS_DIR/phase3/test_phase3_error_recovery.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase3/test_phase3_error_recovery.sh"
    fi
    if [ -f "$TESTS_DIR/phase3/test_phase3_resilience.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase3/test_phase3_resilience.sh"
    fi
    
    echo -e "  ${GREEN}Phase 4${NC}: Runtime Parameter Updates & Hot Reloading"
    if [ -f "$TESTS_DIR/phase4/test_phase4_hot_reloading.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase4/test_phase4_hot_reloading.sh"
    fi
    
    echo -e "  ${GREEN}Phase 5${NC}: Configuration Consolidation & Validation"
    if [ -f "$TESTS_DIR/phase5/test_phase5_configuration.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase5/test_phase5_configuration.sh"
    fi
    
    echo -e "  ${GREEN}Phase 6${NC}: Service Interface Improvements"
    if [ -f "$TESTS_DIR/phase6/test_phase6_services.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase6/test_phase6_services.sh"
    fi
    
    echo -e "  ${GREEN}Phase 7${NC}: Hardware Interface Modernization"
    if [ -f "$TESTS_DIR/phase7/test_phase7_hardware_interfaces.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase7/test_phase7_hardware_interfaces.sh"
    fi
    
    echo -e "  ${GREEN}Phase 8${NC}: Monitoring & Diagnostics Enhancement"
    if [ -f "$TESTS_DIR/phase8/test_phase8_monitoring.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase8/test_phase8_monitoring.sh"
    fi
    
    echo -e "  ${GREEN}Phase 9${NC}: Testing Framework & Validation Suite"
    if [ -f "$TESTS_DIR/phase9/test_phase9_testing_framework.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase9/test_phase9_testing_framework.sh"
    fi
    
    echo -e "  ${GREEN}Phase 10${NC}: Documentation & Developer Experience"
    if [ -f "$TESTS_DIR/phase10/test_phase10_documentation.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase10/test_phase10_documentation.sh"
    fi
    
    echo -e "  ${GREEN}Phase 11${NC}: Performance Optimization & Resource Management"
    if [ -f "$TESTS_DIR/phase11/test_phase11_performance.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase11/test_phase11_performance.sh"
    fi
    
    echo -e "  ${GREEN}Phase 12${NC}: Security & Access Control"
    if [ -f "$TESTS_DIR/phase12/test_phase12_security.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase12/test_phase12_security.sh"
    fi
    
    echo -e "  ${GREEN}Phase 13${NC}: System Integration & Final Validation"
    if [ -f "$TESTS_DIR/phase13/test_phase13_final_integration.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/phase13/test_phase13_final_integration.sh"
    fi
    
    echo ""
    echo -e "${YELLOW}🔄 IN DEVELOPMENT:${NC}"
    echo -e "  ${CYAN}All phases completed! System ready for production.${NC}"
    echo -e "  ${YELLOW}Phase 11${NC}: Performance Optimization & Resource Management"
    echo -e "  ${YELLOW}Phase 12${NC}: Security & Access Control"
    echo -e "  ${YELLOW}Phase 13${NC}: System Integration & Final Validation"
    
    echo ""
    echo -e "${PURPLE}🔧 UTILITY TESTS:${NC}"
    if [ -f "$TESTS_DIR/utils/test_comprehensive_validation.sh" ]; then
        echo -e "    📁 ${TESTS_DIR}/utils/test_comprehensive_validation.sh (Multi-phase validation)"
    fi
    
    echo ""
    echo -e "${CYAN}📦 ARCHIVED TESTS:${NC}"
    for archived_test in "$TESTS_DIR/archive"/*.sh; do
        if [ -f "$archived_test" ]; then
            echo -e "    📁 ${archived_test}"
        fi
    done
}

# Function to run a specific phase test
run_phase_test() {
    local phase=$1
    local test_file=""
    local phase_name=""
    
    case $phase in
        1)
            test_file="$TESTS_DIR/phase1/test_start_switch_topic.sh"
            phase_name="Phase 1: START_SWITCH Implementation"
            ;;
        2)
            test_file="$TESTS_DIR/phase2/test_phase2_validation.sh"
            phase_name="Phase 2: Parameter Type Safety & Validation"
            ;;
        3)
            test_file="$TESTS_DIR/phase3/test_phase3_error_recovery.sh"
            phase_name="Phase 3: Error Recovery & Resilience"
            ;;
        4)
            test_file="$TESTS_DIR/phase4/test_phase4_hot_reloading.sh"
            phase_name="Phase 4: Runtime Parameter Updates & Hot Reloading"
            ;;
        5)
            test_file="$TESTS_DIR/phase5/test_phase5_configuration.sh"
            phase_name="Phase 5: Configuration Consolidation & Validation"
            ;;
        6)
            test_file="$TESTS_DIR/phase6/test_phase6_services.sh"
            phase_name="Phase 6: Service Interface Improvements"
            ;;
        7)
            test_file="$TESTS_DIR/phase7/test_phase7_hardware_interfaces.sh"
            phase_name="Phase 7: Hardware Interface Modernization"
            ;;
        8)
            test_file="$TESTS_DIR/phase8/test_phase8_monitoring.sh"
            phase_name="Phase 8: Monitoring & Diagnostics Enhancement"
            ;;
        9)
            test_file="$TESTS_DIR/phase9/test_phase9_testing_framework.sh"
            phase_name="Phase 9: Testing Framework & Validation Suite"
            ;;
        10)
            test_file="$TESTS_DIR/phase10/test_phase10_documentation.sh"
            phase_name="Phase 10: Documentation & Developer Experience"
            ;;
        11)
            test_file="$TESTS_DIR/phase11/test_phase11_performance.sh"
            phase_name="Phase 11: Performance Optimization & Resource Management"
            ;;
        12)
            test_file="$TESTS_DIR/phase12/test_phase12_security.sh"
            phase_name="Phase 12: Security & Access Control"
            ;;
        13)
            test_file="$TESTS_DIR/phase13/test_phase13_final_integration.sh"
            phase_name="Phase 13: System Integration & Final Validation"
            ;;
        comprehensive|utils)
            test_file="$TESTS_DIR/utils/test_comprehensive_validation.sh"
            phase_name="Comprehensive Multi-Phase Validation"
            ;;
        *)
            echo -e "${RED}❌ Error: Unknown phase '$phase'${NC}"
            echo -e "${YELLOW}💡 Use './tests/run_tests.sh list' to see available phases${NC}"
            exit 1
            ;;
    esac
    
    if [ ! -f "$test_file" ]; then
        echo -e "${RED}❌ Error: Test file not found: $test_file${NC}"
        if [ "$phase" -ge 5 ]; then
            echo -e "${YELLOW}💡 Phase $phase is still in development${NC}"
        fi
        exit 1
    fi
    
    echo -e "${GREEN}🧪 Running $phase_name${NC}"
    echo -e "${CYAN}📁 Test file: $test_file${NC}"
    echo ""
    
    # Make sure the test script is executable
    chmod +x "$test_file"
    
    # Run the test with timeout
    if timeout 120s "$test_file"; then
        echo ""
        echo -e "${GREEN}✅ $phase_name completed successfully${NC}"
        return 0
    else
        echo ""
        echo -e "${RED}❌ $phase_name failed or timed out${NC}"
        return 1
    fi
}

# Function to run all available tests
run_all_tests() {
    local failed_tests=()
    local total_tests=0
    local passed_tests=0
    
    echo -e "${CYAN}🚀 Running all available tests...${NC}"
    echo ""
    
    # Test phases 1-13 (all implemented)
    for phase in 1 2 3 4 5 6 7 8 9 10 11 12 13; do
        total_tests=$((total_tests + 1))
        echo -e "${BLUE}==================== Testing Phase $phase ====================${NC}"
        if run_phase_test $phase; then
            passed_tests=$((passed_tests + 1))
        else
            failed_tests+=("Phase $phase")
        fi
        echo ""
        sleep 2  # Brief pause between tests
    done
    
    # Run comprehensive validation
    total_tests=$((total_tests + 1))
    echo -e "${BLUE}==================== Comprehensive Validation ====================${NC}"
    if run_phase_test comprehensive; then
        passed_tests=$((passed_tests + 1))
    else
        failed_tests+=("Comprehensive validation")
    fi
    
    # Summary
    echo ""
    echo -e "${BLUE}===============================================================================${NC}"
    echo -e "${CYAN}📊 TEST SUITE SUMMARY:${NC}"
    echo -e "${GREEN}✅ Passed: $passed_tests/$total_tests tests${NC}"
    
    if [ ${#failed_tests[@]} -gt 0 ]; then
        echo -e "${RED}❌ Failed: ${#failed_tests[@]}/$total_tests tests${NC}"
        echo -e "${RED}Failed tests:${NC}"
        for failed_test in "${failed_tests[@]}"; do
            echo -e "  ${RED}- $failed_test${NC}"
        done
        return 1
    else
        echo -e "${GREEN}🎉 All tests passed!${NC}"
        return 0
    fi
}

# Main script logic
case "${1:-help}" in
    list|ls|-l|--list)
        list_tests
        ;;
    all|-a|--all)
        run_all_tests
        ;;
    [1-9]|[1-9][0-9])
        run_phase_test "$1"
        ;;
    comprehensive|utils)
        run_phase_test comprehensive
        ;;
    help|-h|--help|"")
        echo -e "${CYAN}Usage: $0 [phase_number|all|list]${NC}"
        echo ""
        echo -e "${CYAN}Examples:${NC}"
        echo -e "  $0 2              ${YELLOW}# Run Phase 2 tests only${NC}"
        echo -e "  $0 all            ${YELLOW}# Run all available tests${NC}"
        echo -e "  $0 list           ${YELLOW}# List all available tests${NC}"
        echo -e "  $0 comprehensive  ${YELLOW}# Run multi-phase validation${NC}"
        echo ""
        echo -e "${CYAN}Available commands:${NC}"
        echo -e "  ${GREEN}list${NC}          List all available test phases and scripts"
        echo -e "  ${GREEN}all${NC}           Run all implemented phase tests"
        echo -e "  ${GREEN}1-13${NC}          Run specific phase test"
        echo -e "  ${GREEN}comprehensive${NC} Run comprehensive multi-phase validation"
        echo -e "  ${GREEN}help${NC}          Show this help message"
        ;;
    *)
        echo -e "${RED}❌ Error: Unknown command '$1'${NC}"
        echo -e "${YELLOW}💡 Use '$0 help' for usage information${NC}"
        exit 1
        ;;
esac