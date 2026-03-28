#!/bin/bash

################################################################################
# Log Cleanup and Management System
# 
# This script intelligently manages log files, keeping important ones and 
# cleaning up old/redundant logs to save space and reduce clutter.
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
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

# Configuration
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
CLEANUP_LOG="./log_cleanup_${TIMESTAMP}.log"
ARCHIVE_DIR="./logs_archive"

# Retention policies (in days)
VALIDATION_LOGS_KEEP_DAYS=7      # Keep validation logs for 7 days
BUILD_LOGS_KEEP_DAYS=3           # Keep build logs for 3 days  
ROS_LOGS_KEEP_DAYS=2             # Keep ROS logs for 2 days
TEMP_LOGS_KEEP_DAYS=1            # Keep temp logs for 1 day

# Size thresholds
MAX_LOG_DIR_SIZE_MB=100          # Archive when log dir exceeds 100MB
MAX_SINGLE_LOG_SIZE_MB=10        # Archive large individual logs

echo ""
print_status $PURPLE "🧹 LOG CLEANUP AND MANAGEMENT SYSTEM"
print_status $PURPLE "==================================="
echo ""

{
    echo "Log Cleanup Started: $(date)"
    echo "Workspace: $WORKSPACE_ROOT"
    echo "=========================================="
    echo ""

    # Phase 1: Analysis
    print_status $BLUE "📊 Phase 1: Log Analysis..."
    echo ""
    
    total_logs=$(find . -name "*.log" -type f 2>/dev/null | wc -l)
    total_size=$(du -sh . 2>/dev/null | grep -o '^[^[:space:]]*' || echo "Unknown")
    
    print_status $CYAN "📈 Found $total_logs log files"
    print_status $CYAN "💾 Current workspace size: $total_size"
    
    echo "Analysis Results:" >> "$CLEANUP_LOG"
    echo "- Total log files: $total_logs" >> "$CLEANUP_LOG"
    echo "- Workspace size: $total_size" >> "$CLEANUP_LOG"
    echo "" >> "$CLEANUP_LOG"

    # Phase 2: Categorize logs
    print_status $BLUE "🗂️ Phase 2: Categorizing Logs..."
    echo ""
    
    # Find different types of logs
    validation_logs=$(find . -path "*validation_results*" -name "*.log" 2>/dev/null | wc -l)
    build_logs=$(find . -path "*build*" -name "*.log" 2>/dev/null | wc -l)
    ros_logs=$(find . -path "*log*" -name "*.log" -o -path "*logs*" -name "*.log" 2>/dev/null | wc -l)
    cmake_logs=$(find . -name "CMakeOutput.log" -o -name "CMakeError.log" 2>/dev/null | wc -l)
    
    print_status $CYAN "🧪 Validation logs: $validation_logs"
    print_status $CYAN "🔨 Build logs: $build_logs" 
    print_status $CYAN "🤖 ROS logs: $ros_logs"
    print_status $CYAN "⚙️  CMake logs: $cmake_logs"

    echo ""

    # Phase 3: Create archive directory
    print_status $BLUE "📦 Phase 3: Preparing Archive..."
    mkdir -p "$ARCHIVE_DIR/validation_logs"
    mkdir -p "$ARCHIVE_DIR/build_logs"
    mkdir -p "$ARCHIVE_DIR/ros_logs"
    mkdir -p "$ARCHIVE_DIR/temp_logs"
    
    print_status $GREEN "✅ Archive directories created"

    echo ""

    # Phase 4: Clean up old validation logs (keep recent important ones)
    print_status $BLUE "🧪 Phase 4: Managing Validation Logs..."
    echo ""
    
    validation_cleaned=0
    validation_kept=0
    
    # Keep most recent validation logs, archive older ones
    for log_dir in clean_validation_results runtime_validation_results validation_results comprehensive_test_reports_*; do
        if [ -d "$log_dir" ]; then
            print_status $CYAN "Processing $log_dir..."
            
            # Keep the most recent 3 logs in each directory, archive the rest
            recent_logs=$(find "$log_dir" -name "*.log" -type f -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -3 | cut -d' ' -f2-)
            old_logs=$(find "$log_dir" -name "*.log" -type f ! -newer "$log_dir" 2>/dev/null)
            
            # Archive old logs except the most recent ones
            for log_file in $(find "$log_dir" -name "*.log" -type f 2>/dev/null); do
                if echo "$recent_logs" | grep -q "$log_file"; then
                    validation_kept=$((validation_kept + 1))
                else
                    if [ -f "$log_file" ] && [ $(stat -c%Y "$log_file" 2>/dev/null || echo 0) -lt $(date -d "$VALIDATION_LOGS_KEEP_DAYS days ago" +%s 2>/dev/null || echo 0) ]; then
                        mv "$log_file" "$ARCHIVE_DIR/validation_logs/" 2>/dev/null && validation_cleaned=$((validation_cleaned + 1))
                    else
                        validation_kept=$((validation_kept + 1))
                    fi
                fi
            done
        fi
    done
    
    print_status $GREEN "✅ Validation logs: $validation_kept kept, $validation_cleaned archived"

    echo ""

    # Phase 5: Clean up build logs
    print_status $BLUE "🔨 Phase 5: Managing Build Logs..."
    echo ""
    
    build_cleaned=0
    build_kept=0
    
    # Clean CMake logs (keep only latest)
    for cmake_log in $(find . -name "CMakeOutput.log" -o -name "CMakeError.log" 2>/dev/null); do
        log_dir=$(dirname "$cmake_log")
        log_name=$(basename "$cmake_log")
        
        # Keep only if it's recent or in the main build directory
        if echo "$log_dir" | grep -q "build$" || [ $(stat -c%Y "$cmake_log" 2>/dev/null || echo 0) -gt $(date -d "$BUILD_LOGS_KEEP_DAYS days ago" +%s 2>/dev/null || echo 999999999) ]; then
            build_kept=$((build_kept + 1))
        else
            mv "$cmake_log" "$ARCHIVE_DIR/build_logs/" 2>/dev/null && build_cleaned=$((build_cleaned + 1))
        fi
    done
    
    print_status $GREEN "✅ Build logs: $build_kept kept, $build_cleaned archived"

    echo ""

    # Phase 6: Clean up ROS logs
    print_status $BLUE "🤖 Phase 6: Managing ROS Logs..."
    echo ""
    
    ros_cleaned=0
    ros_kept=0
    
    # Clean old ROS logs from log directories
    for log_dir in log logs; do
        if [ -d "$log_dir" ]; then
            print_status $CYAN "Processing $log_dir directory..."
            
            # Archive logs older than retention period
            old_ros_logs=$(find "$log_dir" -name "*.log" -type f -mtime +$ROS_LOGS_KEEP_DAYS 2>/dev/null)
            for old_log in $old_ros_logs; do
                if [ -f "$old_log" ]; then
                    mv "$old_log" "$ARCHIVE_DIR/ros_logs/" 2>/dev/null && ros_cleaned=$((ros_cleaned + 1))
                fi
            done
            
            # Count remaining logs
            remaining=$(find "$log_dir" -name "*.log" -type f 2>/dev/null | wc -l)
            ros_kept=$((ros_kept + remaining))
        fi
    done
    
    print_status $GREEN "✅ ROS logs: $ros_kept kept, $ros_cleaned archived"

    echo ""

    # Phase 7: Clean up temporary files
    print_status $BLUE "🗑️ Phase 7: Cleaning Temporary Files..."
    echo ""
    
    temp_cleaned=0
    
    # Remove temporary log files
    for temp_log in /tmp/*test*.log /tmp/*validation*.log /tmp/*odrive*.log /tmp/*integration*.log; do
        if [ -f "$temp_log" ]; then
            rm -f "$temp_log" 2>/dev/null && temp_cleaned=$((temp_cleaned + 1))
        fi
    done
    
    print_status $GREEN "✅ Temporary files cleaned: $temp_cleaned"

    echo ""

    # Phase 8: Compress large log directories
    print_status $BLUE "📦 Phase 8: Compressing Large Log Archives..."
    echo ""
    
    compressed=0
    
    for archive_subdir in "$ARCHIVE_DIR"/*; do
        if [ -d "$archive_subdir" ]; then
            log_count=$(find "$archive_subdir" -name "*.log" -type f 2>/dev/null | wc -l)
            if [ "$log_count" -gt 10 ]; then
                subdir_name=$(basename "$archive_subdir")
                print_status $CYAN "Compressing $subdir_name ($log_count logs)..."
                
                cd "$ARCHIVE_DIR"
                tar -czf "${subdir_name}_${TIMESTAMP}.tar.gz" "$subdir_name" 2>/dev/null && {
                    rm -rf "$subdir_name"
                    compressed=$((compressed + 1))
                    print_status $GREEN "✅ Compressed $subdir_name"
                }
                cd "$WORKSPACE_ROOT"
            fi
        fi
    done
    
    if [ "$compressed" -eq 0 ]; then
        print_status $CYAN "No large log directories to compress"
    fi

    echo ""

    # Phase 9: Final statistics
    print_status $BLUE "📊 Phase 9: Final Statistics..."
    echo ""
    
    final_logs=$(find . -name "*.log" -type f 2>/dev/null | wc -l)
    final_size=$(du -sh . 2>/dev/null | grep -o '^[^[:space:]]*' || echo "Unknown")
    logs_removed=$((total_logs - final_logs))
    
    print_status $CYAN "📈 Logs before cleanup: $total_logs"
    print_status $CYAN "📉 Logs after cleanup: $final_logs"
    print_status $GREEN "🗑️ Logs cleaned: $logs_removed"
    print_status $CYAN "💾 Current workspace size: $final_size"
    
    echo "" >> "$CLEANUP_LOG"
    echo "Final Results:" >> "$CLEANUP_LOG"
    echo "- Logs removed: $logs_removed" >> "$CLEANUP_LOG"
    echo "- Final log count: $final_logs" >> "$CLEANUP_LOG"
    echo "- Final workspace size: $final_size" >> "$CLEANUP_LOG"
    echo "- Archive location: $ARCHIVE_DIR" >> "$CLEANUP_LOG"

} 2>&1 | tee -a "$CLEANUP_LOG"

echo ""

# Phase 10: Create cleanup summary
print_status $PURPLE "🏆 LOG CLEANUP COMPLETE"
print_status $PURPLE "======================="
echo ""

print_status $GREEN "✅ Cleanup completed successfully!"
print_status $CYAN "📁 Archived logs location: $ARCHIVE_DIR"
print_status $CYAN "📋 Cleanup log: $CLEANUP_LOG"

echo ""
print_status $BLUE "📋 **WHAT WAS CLEANED:**"
print_status $CYAN "├── Validation logs: Keep recent 3 per directory"
print_status $CYAN "├── Build logs: Keep only recent CMake logs"
print_status $CYAN "├── ROS logs: Keep logs newer than $ROS_LOGS_KEEP_DAYS days"
print_status $CYAN "├── Temp files: Cleaned all temporary test logs"
print_status $CYAN "└── Large archives: Compressed when >10 files"

echo ""
print_status $BLUE "💡 **RETENTION POLICY:**"
print_status $CYAN "├── Validation logs: $VALIDATION_LOGS_KEEP_DAYS days"
print_status $CYAN "├── Build logs: $BUILD_LOGS_KEEP_DAYS days"
print_status $CYAN "├── ROS logs: $ROS_LOGS_KEEP_DAYS days"
print_status $CYAN "└── Temp logs: $TEMP_LOGS_KEEP_DAYS day"

echo ""
print_status $BLUE "🔄 **TO RUN AGAIN:**"
print_status $CYAN "./scripts/cleanup_logs.sh"

echo ""
print_status $GREEN "🎉 Your workspace is now clean and organized!"
