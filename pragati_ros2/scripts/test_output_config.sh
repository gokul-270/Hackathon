#!/bin/bash
################################################################################
# Test Output Configuration Script
# 
# Provides centralized configuration for test output directories and formatting
################################################################################

# Base test output directory
TEST_OUTPUT_BASE="${HOME}/pragati_test_results"

# Function to setup test output directory
setup_test_output() {
    local test_name="$1"
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local output_dir="${TEST_OUTPUT_BASE}/${test_name}_${timestamp}"
    
    # Create directory structure
    mkdir -p "$output_dir"
    
    # Export for use in other scripts
    export TEST_OUTPUT_DIR="$output_dir"
    
    echo "$output_dir"
}

# Function to cleanup old test results (keep last 10)
cleanup_old_tests() {
    if [ -d "$TEST_OUTPUT_BASE" ]; then
        # Keep only the 10 most recent test directories
        find "$TEST_OUTPUT_BASE" -maxdepth 1 -type d -name "*_2*" | sort | head -n -10 | xargs rm -rf 2>/dev/null || true
    fi
}

# Initialize test output base directory
mkdir -p "$TEST_OUTPUT_BASE"
