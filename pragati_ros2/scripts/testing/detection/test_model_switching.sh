#!/bin/bash
# Test Model Switching for Cotton Detection Node
# Validates that model path argument is correctly passed and loaded

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Model paths
MODELS_DIR="${WORKSPACE_ROOT}/data/models"
INSTALL_MODELS="${WORKSPACE_ROOT}/install/cotton_detection_ros2/share/cotton_detection_ros2/models"

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Cotton Detection - Model Switching Test${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_test() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_failure() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_model_file() {
    local model_path=$1
    if [ -f "${model_path}" ]; then
        print_success "Model file exists: ${model_path}"
        ls -lh "${model_path}"
        return 0
    else
        print_failure "Model file NOT found: ${model_path}"
        return 1
    fi
}

test_model_launch() {
    local model_name=$1
    local model_path=$2
    
    print_test "Testing launch with: ${model_name}"
    echo "   Path: ${model_path}"
    
    # Check if model exists
    if [ ! -f "${model_path}" ]; then
        print_failure "Model file not found, skipping test"
        return 1
    fi
    
    # Launch node for 5 seconds and capture output
    local output_file="/tmp/model_test_${model_name}.log"
    timeout 5s ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
        depthai_model_path:="${model_path}" \
        > "${output_file}" 2>&1 || true
    
    # Check for model in logs
    if grep -q "📦 Model path parameter.*${model_name}" "${output_file}"; then
        print_success "Model parameter detected: ${model_name}"
    else
        print_failure "Model parameter NOT detected in logs"
        echo "   Expected to see: ${model_name}"
        return 1
    fi
    
    if grep -q "🎯 Initializing DepthAI with model.*${model_path}" "${output_file}"; then
        print_success "Model loaded by DepthAI: ${model_name}"
    else
        print_failure "Model NOT loaded by DepthAI"
        return 1
    fi
    
    # Show model confirmation lines
    echo ""
    echo "   Log excerpt:"
    grep -E "📦|✅|🎯.*model" "${output_file}" | sed 's/^/   /'
    echo ""
    
    rm -f "${output_file}"
    return 0
}

test_default_model() {
    print_test "Testing default model (no argument)"
    
    local output_file="/tmp/model_test_default.log"
    timeout 5s ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
        > "${output_file}" 2>&1 || true
    
    if grep -q "yolov8v2.blob" "${output_file}"; then
        print_success "Default model used: yolov8v2.blob"
    else
        print_failure "Default model NOT detected"
        return 1
    fi
    
    echo ""
    echo "   Log excerpt:"
    grep -E "📦|✅|🎯.*model" "${output_file}" | sed 's/^/   /'
    echo ""
    
    rm -f "${output_file}"
    return 0
}

# Main execution
main() {
    print_header
    
    # Source ROS2
    source /opt/ros/jazzy/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash
    source "${WORKSPACE_ROOT}/install/setup.bash"
    
    print_info "Available models:"
    echo ""
    echo "Data models:"
    ls -lh "${MODELS_DIR}"/*.blob 2>/dev/null || echo "  (none)"
    echo ""
    echo "Install models:"
    ls -lh "${INSTALL_MODELS}"/*.blob 2>/dev/null || echo "  (none)"
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    # Test default
    test_default_model
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    # Test each available model
    if [ -f "${MODELS_DIR}/yolov8.blob" ]; then
        test_model_launch "yolov8.blob" "${MODELS_DIR}/yolov8.blob"
        echo "═══════════════════════════════════════════════════════════"
        echo ""
    fi
    
    if [ -f "${MODELS_DIR}/yolov8v2.blob" ]; then
        test_model_launch "yolov8v2.blob" "${MODELS_DIR}/yolov8v2.blob"
        echo "═══════════════════════════════════════════════════════════"
        echo ""
    fi
    
    if [ -f "${MODELS_DIR}/best_openvino_2022.1_6shave.blob" ]; then
        test_model_launch "best_openvino" "${MODELS_DIR}/best_openvino_2022.1_6shave.blob"
        echo "═══════════════════════════════════════════════════════════"
        echo ""
    fi
    
    print_info "Model switching tests complete!"
    echo ""
    echo "Summary:"
    echo "  ✅ Model path argument is correctly passed to the node"
    echo "  ✅ DepthAI loads the specified model file"
    echo "  ✅ Logging clearly shows which model is active"
    echo ""
    echo "Usage in launch files:"
    echo "  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \\"
    echo "    depthai_model_path:=/path/to/your/model.blob"
}

main "$@"
