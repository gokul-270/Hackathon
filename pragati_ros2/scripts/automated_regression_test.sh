#!/bin/bash

################################################################################
# Pragati ROS2 Automated Regression Test Suite
#
# Runs all unit tests systematically with detailed reporting.
# Suitable for CI/CD integration and manual regression testing.
#
# Usage:
#   ./automated_regression_test.sh [OPTIONS]
#
# Options:
#   --packages PKG1,PKG2  Run tests for specific packages only
#   --verbose             Show detailed test output
#   --junit               Generate JUnit XML reports
#   --coverage            Generate coverage reports (requires lcov)
#   --html                Generate HTML test report
#   --ci                  CI mode: fail fast, minimal output
#   --help                Show this help message
#
# Exit Codes:
#   0 - All tests passed
#   1 - One or more tests failed
#   2 - Build failed
#   3 - Invalid arguments
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_DIR="${WORKSPACE_ROOT}/test_output/regression/regression_${TIMESTAMP}"
LOG_FILE="${REPORT_DIR}/regression_test.log"
JSON_REPORT="${REPORT_DIR}/test_results.json"
HTML_REPORT="${REPORT_DIR}/test_report.html"
JUNIT_DIR="${REPORT_DIR}/junit"

# Default options
VERBOSE=0
GENERATE_JUNIT=0
GENERATE_COVERAGE=0
GENERATE_HTML=0
CI_MODE=0
SPECIFIC_PACKAGES=""
FAIL_FAST=0

# Test counters
TOTAL_SUITES=0
PASSED_SUITES=0
FAILED_SUITES=0
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Timing
START_TIME=$(date +%s)

# Print functions
print_status() {
    local color="$1"
    local message="$2"
    if [[ $CI_MODE -eq 0 ]]; then
        echo -e "${color}${message}${NC}"
    else
        echo "$message"
    fi
}

print_header() {
    local message="$1"
    print_status "$BLUE" ""
    print_status "$BLUE" "════════════════════════════════════════════════════════════════"
    print_status "$CYAN" "  $message"
    print_status "$BLUE" "════════════════════════════════════════════════════════════════"
    print_status "$BLUE" ""
}

print_section() {
    local message="$1"
    print_status "$PURPLE" ""
    print_status "$PURPLE" "────────────────────────────────────────────────────────────────"
    print_status "$PURPLE" "  $message"
    print_status "$PURPLE" "────────────────────────────────────────────────────────────────"
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --packages)
                SPECIFIC_PACKAGES="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE=1
                shift
                ;;
            --junit)
                GENERATE_JUNIT=1
                shift
                ;;
            --coverage)
                GENERATE_COVERAGE=1
                shift
                ;;
            --html)
                GENERATE_HTML=1
                shift
                ;;
            --ci)
                CI_MODE=1
                FAIL_FAST=1
                shift
                ;;
            --help)
                grep '^#' "$0" | grep -v '#!/bin/bash' | sed 's/^# \?//'
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use --help for usage information"
                exit 3
                ;;
        esac
    done
}

# Initialize reporting
init_reports() {
    mkdir -p "$REPORT_DIR"
    mkdir -p "$JUNIT_DIR"
    
    # Initialize log
    {
        echo "Pragati ROS2 Automated Regression Test Suite"
        echo "=============================================="
        echo "Date: $(date)"
        echo "Workspace: $WORKSPACE_ROOT"
        echo "Report Dir: $REPORT_DIR"
        echo ""
    } > "$LOG_FILE"
    
    # Initialize JSON report
    {
        echo "{"
        echo "  \"test_run\": {"
        echo "    \"timestamp\": \"$(date -Iseconds)\","
        echo "    \"workspace\": \"$WORKSPACE_ROOT\","
        echo "    \"hostname\": \"$(hostname)\","
        echo "    \"user\": \"$(whoami)\""
        echo "  },"
        echo "  \"test_suites\": ["
    } > "$JSON_REPORT"
}

# Build workspace
build_workspace() {
    print_header "Building Workspace"
    
    cd "$WORKSPACE_ROOT"
    
    local build_args="--cmake-args -DBUILD_TESTING=ON"
    if [[ -n "$SPECIFIC_PACKAGES" ]]; then
        build_args="$build_args --packages-select ${SPECIFIC_PACKAGES//,/ }"
    fi
    
    print_status "$CYAN" "Build command: colcon build $build_args"
    
    if [[ $VERBOSE -eq 1 ]]; then
        if colcon build $build_args 2>&1 | tee -a "$LOG_FILE"; then
            print_status "$GREEN" "✅ Build succeeded"
            return 0
        else
            print_status "$RED" "❌ Build failed"
            return 2
        fi
    else
        if colcon build $build_args >> "$LOG_FILE" 2>&1; then
            print_status "$GREEN" "✅ Build succeeded"
            return 0
        else
            print_status "$RED" "❌ Build failed"
            cat "$LOG_FILE"
            return 2
        fi
    fi
}

# Run unit tests
run_unit_tests() {
    print_header "Running Unit Tests"
    
    cd "$WORKSPACE_ROOT"
    source install/setup.bash
    
    # Define test packages
    local test_packages=(
        "motor_control_ros2"
        "cotton_detection_ros2"
        "yanthra_move"
    )
    
    # Filter packages if specified
    if [[ -n "$SPECIFIC_PACKAGES" ]]; then
        IFS=',' read -ra test_packages <<< "$SPECIFIC_PACKAGES"
    fi
    
    local overall_result=0
    
    for package in "${test_packages[@]}"; do
        run_package_tests "$package"
        local result=$?
        if [[ $result -ne 0 ]]; then
            overall_result=1
            if [[ $FAIL_FAST -eq 1 ]]; then
                print_status "$RED" "Fail-fast mode: stopping after first failure"
                break
            fi
        fi
    done
    
    return $overall_result
}

# Run tests for a specific package
run_package_tests() {
    local package="$1"
    print_section "Testing Package: $package"
    
    TOTAL_SUITES=$((TOTAL_SUITES + 1))
    
    local test_start=$(date +%s)
    local test_args="--packages-select $package --event-handlers console_direct+"
    
    if [[ $GENERATE_JUNIT -eq 1 ]]; then
        test_args="$test_args --pytest-with-coverage --pytest-args --junit-xml=$JUNIT_DIR/${package}_junit.xml"
    fi
    
    local test_output="${REPORT_DIR}/${package}_test_output.txt"
    
    if colcon test $test_args > "$test_output" 2>&1; then
        local test_end=$(date +%s)
        local duration=$((test_end - test_start))
        
        # Parse test results
        parse_test_results "$package" "$test_output" "$duration"
        
        print_status "$GREEN" "✅ $package: All tests passed (${duration}s)"
        PASSED_SUITES=$((PASSED_SUITES + 1))
        
        log_suite_result "$package" "PASS" "$duration" "$test_output"
        return 0
    else
        local test_end=$(date +%s)
        local duration=$((test_end - test_start))
        
        print_status "$RED" "❌ $package: Tests failed (${duration}s)"
        FAILED_SUITES=$((FAILED_SUITES + 1))
        
        if [[ $VERBOSE -eq 1 ]]; then
            cat "$test_output"
        else
            print_status "$YELLOW" "See $test_output for details"
        fi
        
        log_suite_result "$package" "FAIL" "$duration" "$test_output"
        return 1
    fi
}

# Parse test results from output
parse_test_results() {
    local package="$1"
    local output_file="$2"
    local duration="$3"
    
    # Try to extract test counts from XML if available
    local xml_file="build/$package/test_output/integration/$package/*.xml"
    
    if compgen -G "$xml_file" > /dev/null 2>&1; then
        for xml in $xml_file; do
            if [[ -f "$xml" ]]; then
                local tests=$(grep -oP 'tests="\K[0-9]+' "$xml" 2>/dev/null | head -1)
                local failures=$(grep -oP 'failures="\K[0-9]+' "$xml" 2>/dev/null | head -1)
                
                if [[ -n "$tests" ]]; then
                    TOTAL_TESTS=$((TOTAL_TESTS + tests))
                    FAILED_TESTS=$((FAILED_TESTS + failures))
                    PASSED_TESTS=$((PASSED_TESTS + tests - failures))
                fi
            fi
        done
    fi
}

# Log suite result to JSON
log_suite_result() {
    local package="$1"
    local result="$2"
    local duration="$3"
    local output_file="$4"
    
    {
        echo "    {"
        echo "      \"package\": \"$package\","
        echo "      \"result\": \"$result\","
        echo "      \"duration\": $duration,"
        echo "      \"output_file\": \"$output_file\","
        echo "      \"timestamp\": \"$(date -Iseconds)\""
        echo "    },"
    } >> "$JSON_REPORT"
}

# Generate coverage report
generate_coverage() {
    if [[ $GENERATE_COVERAGE -eq 1 ]]; then
        print_section "Generating Coverage Report"
        
        if command -v lcov &> /dev/null; then
            cd "$WORKSPACE_ROOT"
            lcov --capture --directory build --output-file "$REPORT_DIR/coverage.info" >> "$LOG_FILE" 2>&1
            lcov --remove "$REPORT_DIR/coverage.info" '/usr/*' '*/test/*' --output-file "$REPORT_DIR/coverage_filtered.info" >> "$LOG_FILE" 2>&1
            genhtml "$REPORT_DIR/coverage_filtered.info" --output-directory "$REPORT_DIR/coverage_html" >> "$LOG_FILE" 2>&1
            
            print_status "$GREEN" "✅ Coverage report: $REPORT_DIR/coverage_html/index.html"
        else
            print_status "$YELLOW" "⚠️  lcov not found, skipping coverage report"
        fi
    fi
}

# Generate HTML report
generate_html_report() {
    if [[ $GENERATE_HTML -eq 1 ]]; then
        print_section "Generating HTML Report"
        
        cat > "$HTML_REPORT" <<EOF
<!DOCTYPE html>
<html>
<head>
    <title>Pragati ROS2 Regression Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        h1 { color: #333; }
        .summary { background-color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .metric { display: inline-block; margin-right: 30px; }
        .suite { background-color: white; padding: 15px; margin-bottom: 10px; border-radius: 5px; }
        .suite-pass { border-left: 5px solid green; }
        .suite-fail { border-left: 5px solid red; }
        pre { background-color: #f0f0f0; padding: 10px; overflow-x: auto; }
    </style>
</head>
<body>
    <h1>Pragati ROS2 Regression Test Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <div class="metric">Date: $(date)</div>
        <div class="metric">Duration: $(($(date +%s) - START_TIME))s</div>
        <br><br>
        <div class="metric">Total Suites: $TOTAL_SUITES</div>
        <div class="metric pass">Passed: $PASSED_SUITES</div>
        <div class="metric fail">Failed: $FAILED_SUITES</div>
        <br><br>
        <div class="metric">Total Tests: $TOTAL_TESTS</div>
        <div class="metric pass">Passed: $PASSED_TESTS</div>
        <div class="metric fail">Failed: $FAILED_TESTS</div>
    </div>
    <h2>Test Suites</h2>
EOF
        
        # Add suite details
        for package in motor_control_ros2 cotton_detection_ros2 yanthra_move; do
            local result_file="${REPORT_DIR}/${package}_test_output.txt"
            if [[ -f "$result_file" ]]; then
                local suite_class="suite-pass"
                if grep -q "failed" "$result_file"; then
                    suite_class="suite-fail"
                fi
                
                cat >> "$HTML_REPORT" <<EOF
    <div class="suite $suite_class">
        <h3>$package</h3>
        <pre>$(cat "$result_file" | head -50)</pre>
    </div>
EOF
            fi
        done
        
        cat >> "$HTML_REPORT" <<EOF
</body>
</html>
EOF
        
        print_status "$GREEN" "✅ HTML report: $HTML_REPORT"
    fi
}

# Generate final summary
generate_summary() {
    print_header "Test Summary"
    
    local end_time=$(date +%s)
    local total_duration=$((end_time - START_TIME))
    
    print_status "$CYAN" "Total Duration: ${total_duration}s"
    print_status "$CYAN" "Test Suites: $TOTAL_SUITES"
    print_status "$GREEN" "  Passed: $PASSED_SUITES"
    if [[ $FAILED_SUITES -gt 0 ]]; then
        print_status "$RED" "  Failed: $FAILED_SUITES"
    fi
    
    if [[ $TOTAL_TESTS -gt 0 ]]; then
        print_status "$CYAN" "Total Tests: $TOTAL_TESTS"
        print_status "$GREEN" "  Passed: $PASSED_TESTS"
        if [[ $FAILED_TESTS -gt 0 ]]; then
            print_status "$RED" "  Failed: $FAILED_TESTS"
        fi
    fi
    
    print_status "$CYAN" ""
    print_status "$CYAN" "Reports saved to: $REPORT_DIR"
    
    # Finalize JSON report
    {
        echo "  ],"
        echo "  \"summary\": {"
        echo "    \"total_suites\": $TOTAL_SUITES,"
        echo "    \"passed_suites\": $PASSED_SUITES,"
        echo "    \"failed_suites\": $FAILED_SUITES,"
        echo "    \"total_tests\": $TOTAL_TESTS,"
        echo "    \"passed_tests\": $PASSED_TESTS,"
        echo "    \"failed_tests\": $FAILED_TESTS,"
        echo "    \"duration\": $total_duration"
        echo "  }"
        echo "}"
    } >> "$JSON_REPORT"
    
    # Print final result
    print_status "$BLUE" ""
    if [[ $FAILED_SUITES -eq 0 ]] && [[ $FAILED_TESTS -eq 0 ]]; then
        print_status "$GREEN" "╔════════════════════════════════════════════════════════════════╗"
        print_status "$GREEN" "║                   ALL TESTS PASSED ✅                          ║"
        print_status "$GREEN" "╚════════════════════════════════════════════════════════════════╝"
        return 0
    else
        print_status "$RED" "╔════════════════════════════════════════════════════════════════╗"
        print_status "$RED" "║                   TESTS FAILED ❌                              ║"
        print_status "$RED" "╚════════════════════════════════════════════════════════════════╝"
        return 1
    fi
}

# CI integration markers
ci_markers() {
    if [[ $CI_MODE -eq 1 ]]; then
        if [[ $FAILED_SUITES -eq 0 ]] && [[ $FAILED_TESTS -eq 0 ]]; then
            echo "::set-output name=result::success"
            echo "::set-output name=passed_tests::$PASSED_TESTS"
        else
            echo "::set-output name=result::failure"
            echo "::set-output name=failed_tests::$FAILED_TESTS"
        fi
    fi
}

# Main execution
main() {
    parse_args "$@"
    
    print_header "Pragati ROS2 Automated Regression Test Suite"
    
    init_reports
    
    # Build
    if ! build_workspace; then
        print_status "$RED" "Build failed, cannot run tests"
        exit 2
    fi
    
    # Run tests
    local test_result=0
    run_unit_tests || test_result=$?
    
    # Generate reports
    generate_coverage
    generate_html_report
    
    # Summary
    generate_summary || test_result=$?
    
    # CI markers
    ci_markers
    
    exit $test_result
}

# Execute main
main "$@"
