#!/bin/bash

################################################################################
# Smart Log Management System  
# 
# Automatically manages logs during testing to prevent accumulation
################################################################################

# Get workspace root
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Function to check if log cleanup is needed
check_log_cleanup_needed() {
    local log_count=$(find "$WORKSPACE_ROOT" -name "*.log" -type f 2>/dev/null | wc -l)
    local validation_dirs=$(find "$WORKSPACE_ROOT" -name "*validation_results*" -type d 2>/dev/null | wc -l)
    
    # Trigger cleanup if:
    # - More than 100 log files exist, OR
    # - More than 10 validation result directories exist
    if [ "$log_count" -gt 100 ] || [ "$validation_dirs" -gt 10 ]; then
        return 0  # Cleanup needed
    else
        return 1  # No cleanup needed
    fi
}

# Function to perform quick log cleanup
quick_log_cleanup() {
    local cleaned=0
    
    # Keep only last 3 validation results of each type
    for result_dir in "$WORKSPACE_ROOT"/*validation_results*; do
        if [ -d "$result_dir" ]; then
            # Count files in directory
            local file_count=$(find "$result_dir" -name "*.log" -type f 2>/dev/null | wc -l)
            if [ "$file_count" -gt 3 ]; then
                # Keep only the 3 most recent logs
                find "$result_dir" -name "*.log" -type f -printf '%T@ %p\n' 2>/dev/null | \
                sort -nr | tail -n +4 | cut -d' ' -f2- | while read old_log; do
                    [ -f "$old_log" ] && rm -f "$old_log" && cleaned=$((cleaned + 1))
                done
            fi
        fi
    done
    
    # Clean old comprehensive test reports (keep only last 3)
    report_dirs=($(find "$WORKSPACE_ROOT" -name "comprehensive_test_reports_*" -type d 2>/dev/null | sort -r))
    if [ ${#report_dirs[@]} -gt 3 ]; then
        for ((i=3; i<${#report_dirs[@]}; i++)); do
            [ -d "${report_dirs[i]}" ] && rm -rf "${report_dirs[i]}" && cleaned=$((cleaned + 1))
        done
    fi
    
    return $cleaned
}

# Function to auto-cleanup before testing
auto_cleanup_before_test() {
    if check_log_cleanup_needed; then
        echo "🧹 Auto-cleanup: Too many logs detected, performing quick cleanup..."
        quick_log_cleanup
        echo "✅ Quick cleanup completed"
    fi
}

# Function to auto-cleanup after testing
auto_cleanup_after_test() {
    # Always clean temp files after testing
    rm -f /tmp/*test*.log /tmp/*validation*.log /tmp/*odrive*.log /tmp/*integration*.log 2>/dev/null
    
    # Clean up any background processes that might still be running
    pkill -f "ros2 launch" 2>/dev/null || true
    pkill -f "odrive_service_node" 2>/dev/null || true
}

# Main execution based on argument
case "${1:-check}" in
    "before")
        auto_cleanup_before_test
        ;;
    "after") 
        auto_cleanup_after_test
        ;;
    "check")
        if check_log_cleanup_needed; then
            echo "🧹 Log cleanup recommended - run: ./scripts/test.sh cleanup"
            exit 1
        else
            echo "✅ Log levels are manageable"
            exit 0
        fi
        ;;
    "quick")
        echo "🧹 Performing quick log cleanup..."
        quick_log_cleanup
        echo "✅ Quick cleanup completed"
        ;;
esac
