#!/bin/bash

################################################################################
# Pragati ROS2 Comprehensive Test Suite (MG6010 Edition)
#
# Provides end-to-end validation for the Pragati ROS2 workspace with updated
# MG6010 motor controller checks, ROS2 readiness validation, and rich reports.
################################################################################

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() {
    local color="$1"
    local message="$2"
    echo -e "${color}${message}${NC}"
    echo -e "${message}" >> "$DETAILED_LOG"
}

# Configuration
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

# Ensure workspace root is valid
if [[ ! -d "$WORKSPACE_ROOT" ]]; then
    echo "Workspace root not found"
    exit 1
fi

# In pure simulation runs we expect the MG6010 controller stack to stay offline.
# Override by exporting SIMULATION_EXPECTS_MG6010=1 when hardware is available.
SIMULATION_EXPECTS_MG6010=${SIMULATION_EXPECTS_MG6010:-0}

# Source centralized test output configuration
source "$WORKSPACE_ROOT/scripts/test_output_config.sh"

# Setup test output directory using centralized config
REPORT_DIR=$(setup_test_output "comprehensive_test")
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DETAILED_LOG="$REPORT_DIR/detailed_test_log.txt"
FUNCTIONALITY_LOG="$REPORT_DIR/functionality_tests.txt"
PERFORMANCE_LOG="$REPORT_DIR/performance_metrics.txt"
JSON_REPORT="$REPORT_DIR/test_results.json"
HTML_REPORT="$REPORT_DIR/test_report.html"
RUNTIME_STATE_LOG="$REPORT_DIR/runtime_system_state.txt"
SYSTEM_LAUNCH_LOG="$REPORT_DIR/system_launch.log"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

# Performance tracking
START_TIME=$(date +%s)

# Create report directory
mkdir -p "$REPORT_DIR"

# Initialize log files
echo "Comprehensive Test Results - $TIMESTAMP" > "$FUNCTIONALITY_LOG"
echo "==========================================" >> "$FUNCTIONALITY_LOG"
echo "" >> "$FUNCTIONALITY_LOG"

# Helper to run commands inside ROS2 workspace environment
run_in_ros_env() {
    (cd "$WORKSPACE_ROOT" && source install/setup.bash 2>/dev/null && "$@")
}

# Function to log test results
log_test_result() {
    local test_name="$1"
    local result="$2"
    local details="$3"
    local duration="$4"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    case "$result" in
        "PASS")
            PASSED_TESTS=$((PASSED_TESTS + 1))
            print_status $GREEN "✅ $test_name"
            ;;
        "FAIL")
            FAILED_TESTS=$((FAILED_TESTS + 1))
            print_status $RED "❌ $test_name"
            ;;
        "WARN")
            WARNING_TESTS=$((WARNING_TESTS + 1))
            print_status $YELLOW "⚠️  $test_name"
            ;;
    esac

    echo "[$result] $test_name: $details (Duration: $duration)" >> "$FUNCTIONALITY_LOG"

    {
        echo "    {"
        echo "      \"test_name\": \"$test_name\"," 
        echo "      \"result\": \"$result\"," 
        echo "      \"details\": \"$details\"," 
        echo "      \"duration\": \"$duration\"," 
        echo "      \"timestamp\": \"$(date -Iseconds)\""
        echo "    },"
    } >> "$JSON_REPORT"
}

ensure_workspace_setup() {
    print_status $BLUE "🛠️ WORKSPACE SETUP VALIDATION"
    local test_start=$(date +%s)

    if [[ -f "$WORKSPACE_ROOT/install/setup.bash" ]]; then
        log_test_result "Workspace Build Check" "PASS" "install/setup.bash present" "$(( $(date +%s) - test_start ))s"
    else
        log_test_result "Workspace Build Check" "FAIL" "Run ./build.sh before executing tests" "$(( $(date +%s) - test_start ))s"
    fi

    test_start=$(date +%s)
    if run_in_ros_env ros2 pkg list >/tmp/ros2_pkg_list.log 2>&1; then
        log_test_result "ROS2 CLI Availability" "PASS" "ros2 CLI accessible" "$(( $(date +%s) - test_start ))s"
    else
        log_test_result "ROS2 CLI Availability" "FAIL" "ros2 CLI not accessible" "$(( $(date +%s) - test_start ))s"
    fi
}

test_parameter_validation() {
    print_status $BLUE "📁 PARAMETER VALIDATION"
    local test_start=$(date +%s)

    if python3 "$WORKSPACE_ROOT/scripts/validation/comprehensive_parameter_validation.py" >> "$DETAILED_LOG" 2>&1; then
        log_test_result "Comprehensive Parameter Validation" "PASS" "Parameter validation script succeeded" "$(( $(date +%s) - test_start ))s"
    else
        log_test_result "Comprehensive Parameter Validation" "WARN" "Parameter validation reported issues" "$(( $(date +%s) - test_start ))s"
    fi
}

test_ros2_functionality() {
    print_status $BLUE "🚀 ROS2 FUNCTIONALITY TESTS"

    local test_start=$(date +%s)
    if run_in_ros_env timeout 10s python3 - <<'PY'
import rclpy
rclpy.init()
node = rclpy.create_node('comprehensive_test_node')
node.get_logger().info('Node created successfully')
node.destroy_node()
rclpy.shutdown()
print('✅ Node creation succeeded')
PY
    then
        log_test_result "ROS2 Node Creation" "PASS" "Node created and destroyed successfully" "$(( $(date +%s) - test_start ))s"
    else
        log_test_result "ROS2 Node Creation" "FAIL" "Unable to create ROS2 node" "$(( $(date +%s) - test_start ))s"
    fi

    test_start=$(date +%s)
    local packages=("yanthra_move" "motor_control_ros2" "cotton_detection_ros2")
    local missing_packages=()
    local pkg_output
    pkg_output=$(run_in_ros_env ros2 pkg list 2>/dev/null)
    for pkg in "${packages[@]}"; do
        if ! grep -q "${pkg}" <<<"$pkg_output"; then
            missing_packages+=("$pkg")
        fi
    done

    if [[ ${#missing_packages[@]} -eq 0 ]]; then
        log_test_result "Core Package Availability" "PASS" "All critical packages detected" "$(( $(date +%s) - test_start ))s"
    else
        log_test_result "Core Package Availability" "WARN" "Missing packages: ${missing_packages[*]}" "$(( $(date +%s) - test_start ))s"
    fi
}

capture_runtime_system_state() {
    print_status $BLUE "🔍 SYSTEM LAUNCH & STATE CAPTURE"
    local test_start=$(date +%s)

    : > "$RUNTIME_STATE_LOG"

    {
        echo "PRAGATI ROS2 SYSTEM STATE ANALYSIS"
        echo "==================================="
        echo "Timestamp: $(date)"
        echo "Workspace: $WORKSPACE_ROOT"
        echo ""
    } >> "$RUNTIME_STATE_LOG"

    (
        cd "$WORKSPACE_ROOT"
        source install/setup.bash 2>/dev/null
        timeout 45s ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true output_log:=log > "$SYSTEM_LAUNCH_LOG" 2>&1
    ) &
    local launch_pid=$!

    # Allow system to start
    sleep 15

    local nodes topics services
    nodes=$(run_in_ros_env ros2 node list 2>/dev/null | sort)
    topics=$(run_in_ros_env ros2 topic list 2>/dev/null | sort)
    services=$(run_in_ros_env ros2 service list 2>/dev/null | sort)

    {
        echo "🤖 Nodes (${nodes//\n/, })"
        echo "" 
        echo "$nodes"
        echo ""
        echo "📡 Topics"
        echo "" 
        echo "$topics"
        echo ""
        echo "🛠️ Services"
        echo ""
        echo "$services"
        echo ""
    } >> "$RUNTIME_STATE_LOG"

    local expected_nodes=(
        "/robot_state_publisher"
        "/joint_state_publisher"
        "/mg6010_controller"
        "/yanthra_move"
        "/cotton_detection_node"
    )

    local expected_services=(
        "/joint_homing"
        "/joint_idle"
        "/joint_status"
        "/motor_calibration"
        "/joint_configuration"
    )

    local simulation_expected_nodes=(
        "/mg6010_controller"
    )

    local simulation_expected_services=(
        "/joint_homing"
        "/joint_idle"
        "/joint_status"
        "/motor_calibration"
        "/joint_configuration"
    )

    local node_missing_raw=()
    for node in "${expected_nodes[@]}"; do
        if ! grep -qx "$node" <<<"$nodes"; then
            node_missing_raw+=("$node")
        fi
    done

    local service_missing_raw=()
    for svc in "${expected_services[@]}"; do
        if ! grep -qx "$svc" <<<"$services"; then
            service_missing_raw+=("$svc")
        fi
    done

    local node_missing=()
    local node_expected_sim=()
    if [[ ${#node_missing_raw[@]} -gt 0 ]]; then
        for node in "${node_missing_raw[@]}"; do
            if [[ "$SIMULATION_EXPECTS_MG6010" -eq 0 && -n "$node" && " ${simulation_expected_nodes[*]} " == *" $node "* ]]; then
                node_expected_sim+=("$node")
            elif [[ -n "$node" ]]; then
                node_missing+=("$node")
            fi
        done
    fi

    local service_missing=()
    local service_expected_sim=()
    if [[ ${#service_missing_raw[@]} -gt 0 ]]; then
        for svc in "${service_missing_raw[@]}"; do
            if [[ "$SIMULATION_EXPECTS_MG6010" -eq 0 && -n "$svc" && " ${simulation_expected_services[*]} " == *" $svc "* ]]; then
                service_expected_sim+=("$svc")
            elif [[ -n "$svc" ]]; then
                service_missing+=("$svc")
            fi
        done
    fi

    if [[ ${#node_missing[@]} -eq 0 ]]; then
        echo "✅ Required nodes present" >> "$RUNTIME_STATE_LOG"
    else
        echo "⚠️ Missing nodes: ${node_missing[*]}" >> "$RUNTIME_STATE_LOG"
    fi

    if [[ ${#service_missing[@]} -eq 0 ]]; then
        echo "✅ Required services present" >> "$RUNTIME_STATE_LOG"
    else
        echo "⚠️ Missing services: ${service_missing[*]}" >> "$RUNTIME_STATE_LOG"
    fi

    if [[ ${#node_expected_sim[@]} -gt 0 ]]; then
        echo "ℹ️ Simulation-only omissions (nodes): ${node_expected_sim[*]}" >> "$RUNTIME_STATE_LOG"
    fi

    if [[ ${#service_expected_sim[@]} -gt 0 ]]; then
        echo "ℹ️ Simulation-only omissions (services): ${service_expected_sim[*]}" >> "$RUNTIME_STATE_LOG"
    fi

    # Attempt safe service introspection if available
    if run_in_ros_env ros2 service type /joint_status >/tmp/joint_status_type.log 2>&1; then
        echo "ℹ️ /joint_status service type: $(cat /tmp/joint_status_type.log)" >> "$RUNTIME_STATE_LOG"
    fi

    kill "$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true

    local duration="$(( $(date +%s) - test_start ))s"

    if [[ ${#node_missing[@]} -eq 0 && ${#service_missing[@]} -eq 0 ]]; then
        local details="All critical nodes and services detected"
        if [[ ${#node_expected_sim[@]} -gt 0 || ${#service_expected_sim[@]} -gt 0 ]]; then
            details="Simulation mode: MG6010 controller/services intentionally absent"
        fi
        log_test_result "System Launch Verification" "PASS" "$details" "$duration"
    elif [[ ${#node_missing[@]} -le 1 && ${#service_missing[@]} -le 1 ]]; then
        log_test_result "System Launch Verification" "WARN" "Missing: ${node_missing[*]} ${service_missing[*]}" "$duration"
    else
        log_test_result "System Launch Verification" "FAIL" "Significant components missing" "$duration"
    fi
}

test_launch_configurations() {
    print_status $BLUE "🧾 LAUNCH CONFIGURATION CHECKS"
    local test_start=$(date +%s)

    local launch_files=(
        "$WORKSPACE_ROOT/src/yanthra_move/launch/pragati_complete.launch.py"
        "$WORKSPACE_ROOT/src/motor_control_ros2/launch/mg6010_test.launch.py"
        "$WORKSPACE_ROOT/src/robo_description/launch/robot_state_publisher.launch.py"
    )

    local syntax_errors=0
    for launch_file in "${launch_files[@]}"; do
        if [[ -f "$launch_file" ]]; then
            if python3 -m py_compile "$launch_file" 2>>"$DETAILED_LOG"; then
                echo "  ✅ $(basename "$launch_file")" >> "$DETAILED_LOG"
            else
                echo "  ❌ $(basename "$launch_file")" >> "$DETAILED_LOG"
                ((syntax_errors++))
            fi
        else
            echo "  ⚠️ $(basename "$launch_file") not found" >> "$DETAILED_LOG"
            ((syntax_errors++))
        fi
    done

    if [[ $syntax_errors -eq 0 ]]; then
        log_test_result "Launch File Syntax Validation" "PASS" "Launch files compiled successfully" "$(( $(date +%s) - test_start ))s"
    else
        log_test_result "Launch File Syntax Validation" "WARN" "$syntax_errors launch files have issues" "$(( $(date +%s) - test_start ))s"
    fi
}

generate_performance_metrics() {
    print_status $BLUE "📊 PERFORMANCE METRICS"
    local total_duration=$(( $(date +%s) - START_TIME ))

    {
        echo "PERFORMANCE METRICS"
        echo "==================="
        echo "Total Test Duration: ${total_duration}s"
        if [[ $total_duration -gt 0 ]]; then
            echo "Tests per Second: $(echo "scale=2; $TOTAL_TESTS / $total_duration" | bc 2>/dev/null || echo 'N/A')"
        else
            echo "Tests per Second: N/A"
        fi
        echo ""
        echo "SYSTEM RESOURCES:"
        echo "CPU Usage: $(top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1 || echo 'N/A')%"
        echo "Memory Usage: $(free -h | awk '/Mem:/ {print $3 "/" $2}' || echo 'N/A')"
        echo "Disk Usage: $(df -h "$WORKSPACE_ROOT" | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}' || echo 'N/A')"
        echo ""
        echo "WORKSPACE STATISTICS:"
        echo "Source Files: $(find "$WORKSPACE_ROOT/src" -type f -name '*.cpp' -o -name '*.hpp' | wc -l)"
        echo "Launch Files: $(find "$WORKSPACE_ROOT" -type f -name '*.launch.py' | wc -l)"
        echo "Config Files: $(find "$WORKSPACE_ROOT" -type f -name '*.yaml' | wc -l)"
        echo "Validation Scripts: $(find "$WORKSPACE_ROOT/scripts/validation" -type f -name '*.sh' -o -name '*.py' | wc -l)"
    } | tee "$PERFORMANCE_LOG" > /dev/null
}

generate_html_report() {
    print_status $CYAN "📄 Generating HTML report..."

    cat > "$HTML_REPORT" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Pragati ROS2 Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
        .summary { background: #ecf0f1; padding: 15px; margin: 20px 0; border-radius: 5px; }
        .pass { color: #27ae60; }
        .fail { color: #e74c3c; }
        .warn { color: #f39c12; }
        .metric { display: inline-block; margin: 10px; padding: 10px; background: #3498db; color: white; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Pragati ROS2 Comprehensive Test Report</h1>
        <p>Generated: $(date)</p>
        <p>Workspace: $WORKSPACE_ROOT</p>
    </div>

    <div class="summary">
        <h2>📊 Test Summary</h2>
        <div class="metric">Total Tests: $TOTAL_TESTS</div>
        <div class="metric pass">Passed: $PASSED_TESTS</div>
        <div class="metric fail">Failed: $FAILED_TESTS</div>
        <div class="metric warn">Warnings: $WARNING_TESTS</div>
        <div class="metric">Duration: $(( $(date +%s) - START_TIME ))s</div>
    </div>

    <div>
        <h2>🧪 Test Categories</h2>
        <ul>
            <li><strong>Workspace Validation</strong>: Build & ROS2 readiness</li>
            <li><strong>Parameter Validation</strong>: Comprehensive YAML checks</li>
            <li><strong>Runtime Verification</strong>: System launch and MG6010 services</li>
        </ul>
    </div>

    <div>
        <h2>📁 Generated Files</h2>
        <ul>
            <li><a href="./detailed_test_log.txt">Detailed Test Log</a></li>
            <li><a href="./functionality_tests.txt">Functionality Test Results</a></li>
            <li><a href="./performance_metrics.txt">Performance Metrics</a></li>
            <li><a href="./test_results.json">JSON Test Results</a></li>
            <li><a href="./runtime_system_state.txt">Runtime System State</a></li>
            <li><a href="./system_launch.log">Launch Output</a></li>
        </ul>
    </div>
EOF

    if [[ -f "$RUNTIME_STATE_LOG" ]]; then
        echo "    <div>" >> "$HTML_REPORT"
        echo "        <h2>🔍 Runtime Snapshot</h2>" >> "$HTML_REPORT"
        echo "        <pre style=\"background-color: #f5f5f5; padding: 15px; border-radius: 5px; white-space: pre-wrap;\">" >> "$HTML_REPORT"
        sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' "$RUNTIME_STATE_LOG" >> "$HTML_REPORT"
        echo "        </pre>" >> "$HTML_REPORT"
        echo "    </div>" >> "$HTML_REPORT"
    fi

    echo "</body></html>" >> "$HTML_REPORT"
}

# Initialize JSON report
echo "{" > "$JSON_REPORT"
echo "  \"test_session\": {" >> "$JSON_REPORT"
echo "    \"timestamp\": \"$(date -Iseconds)\"," >> "$JSON_REPORT"
echo "    \"workspace\": \"$WORKSPACE_ROOT\"," >> "$JSON_REPORT"
echo "    \"hostname\": \"$(hostname)\"" >> "$JSON_REPORT"
echo "  }," >> "$JSON_REPORT"
echo "  \"tests\": [" >> "$JSON_REPORT"

print_status $PURPLE "🔬 PRAGATI ROS2 COMPREHENSIVE TEST SUITE"
print_status $PURPLE "========================================"

cleanup_old_tests

ensure_workspace_setup
test_parameter_validation
test_ros2_functionality
capture_runtime_system_state
test_launch_configurations

generate_performance_metrics

# Finalize JSON
sed -i '$ s/,$//' "$JSON_REPORT"
echo "  ]," >> "$JSON_REPORT"
echo "  \"summary\": {" >> "$JSON_REPORT"
echo "    \"total_tests\": $TOTAL_TESTS," >> "$JSON_REPORT"
echo "    \"passed\": $PASSED_TESTS," >> "$JSON_REPORT"
echo "    \"failed\": $FAILED_TESTS," >> "$JSON_REPORT"
echo "    \"warnings\": $WARNING_TESTS," >> "$JSON_REPORT"
echo "    \"duration\": \"$(( $(date +%s) - START_TIME ))s\"" >> "$JSON_REPORT"
echo "  }" >> "$JSON_REPORT"
echo "}" >> "$JSON_REPORT"

generate_html_report

print_status $PURPLE "🏁 TEST SUITE COMPLETE"
print_status $PURPLE "======================"

print_status $CYAN "📊 Results:"
print_status $GREEN "✅ Passed: $PASSED_TESTS"
print_status $YELLOW "⚠️  Warnings: $WARNING_TESTS"
print_status $RED "❌ Failed: $FAILED_TESTS"

echo "" >> "$DETAILED_LOG"
echo "Reports saved to: $REPORT_DIR" >> "$DETAILED_LOG"

if [[ $FAILED_TESTS -gt 0 ]]; then
    exit 1
elif [[ $WARNING_TESTS -gt 5 ]]; then
    exit 2
else
    exit 0
fi
en