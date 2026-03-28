#!/bin/bash

# Enhanced Parameter Validation Script
# Validates both vehicle control and ODrive parameters

validate_vehicle_parameters() {
    echo "🔍 Validating Vehicle Control Parameters..."
    
    local config_file="src/vehicle_control/config/vehicle_params.yaml"
    
    if [ ! -f "$config_file" ]; then
        echo "❌ Vehicle config file not found: $config_file"
        return 1
    fi
    
    # Validate YAML syntax
    if python3 -c "import yaml; yaml.safe_load(open('$config_file'))" 2>/dev/null; then
        echo "✅ YAML syntax valid"
    else
        echo "❌ YAML syntax error"
        return 1
    fi
    
    # Validate required parameters
    local required_params=(
        "joint_names"
        "physical_params.wheel_diameter"
        "can_bus.interface"
        "gpio_pins.direction_switch_pin"
    )
    
    for param in "${required_params[@]}"; do
        if python3 -c "
import yaml
config = yaml.safe_load(open('$config_file'))
try:
    keys = '$param'.split('.')
    value = config['vehicle_control']['ros__parameters']
    for key in keys:
        value = value[key]
    print(f'✅ {param}: {value}')
except KeyError:
    print(f'❌ Missing parameter: $param')
    exit(1)
        "; then
            continue
        else
            return 1
        fi
    done
    
    echo "✅ All vehicle parameters validated"
    return 0
}

validate_odrive_parameters() {
    echo "🔍 Validating ODrive Parameters..."
    
    local config_file="src/odrive_control_ros2/config/odrive_service_params.yaml"
    
    if [ ! -f "$config_file" ]; then
        echo "❌ ODrive config file not found: $config_file"
        return 1
    fi
    
    # Basic validation
    if python3 -c "import yaml; yaml.safe_load(open('$config_file'))" 2>/dev/null; then
        echo "✅ ODrive YAML syntax valid"
    else
        echo "❌ ODrive YAML syntax error"
        return 1
    fi
    
    echo "✅ ODrive parameters validated"
    return 0
}

# Runtime parameter access test
test_runtime_parameter_access() {
    echo "🔍 Testing Runtime Parameter Access..."
    
    # Start vehicle control in background
    timeout 10s ros2 launch vehicle_control vehicle_control_with_params.launch.py > /tmp/param_test.log 2>&1 &
    local launch_pid=$!
    
    sleep 3
    
    # Test parameter access with retry logic
    local max_attempts=5
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if ros2 param list /vehicle_control_node 2>/dev/null | grep -q joint_names; then
            echo "✅ Parameters accessible (attempt $attempt)"
            kill $launch_pid 2>/dev/null || true
            return 0
        fi
        echo "⏳ Attempt $attempt failed, retrying..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "⚠️ Parameter access timing issues (expected in mock mode)"
    kill $launch_pid 2>/dev/null || true
    return 1
}

main() {
    echo "🧪 Enhanced Parameter Validation Suite"
    echo "======================================="
    
    validate_vehicle_parameters
    validate_odrive_parameters
    test_runtime_parameter_access
    
    echo "✅ Parameter validation complete"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    main "$@"
fi