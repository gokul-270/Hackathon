#!/bin/bash
#
# Pragati ROS2 Log Cleanup Utility Scripts
# ========================================
#
# This script provides convenient command-line utilities for log management
# including quick cleanup, status checking, and maintenance operations.
#
# Author: Generated for Pragati ROS2 Project
# Date: 2025-09-18
#

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_MANAGER="${SCRIPT_DIR}/log_manager.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
show_help() {
    cat << EOF
Pragati ROS2 Log Management Utility

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    clean          Run full log cleanup (default: 7 days, 100MB limit)
    quick-clean    Quick cleanup (3 days, 50MB limit)
    status         Show current log status
    dry-run        Show what would be cleaned without making changes
    compress       Compress old logs without removing them
    emergency      Emergency cleanup (remove all logs older than 1 day)
    ros-clean      Clean only external ROS2 logs in ~/.ros/log/
    setup          Setup log environment and directories
    
Options:
    --days NUM     Maximum age in days (default: 7)
    --size NUM     Maximum size in MB (default: 100)
    --verbose      Enable verbose output
    --no-compress  Don't compress old logs, just remove them
    --force        Don't ask for confirmation

Examples:
    $0 clean                    # Standard cleanup
    $0 quick-clean              # Quick cleanup 
    $0 clean --days 3           # Clean logs older than 3 days
    $0 status                   # Show log directory status
    $0 dry-run --verbose        # Show what would be cleaned
    $0 emergency --force        # Emergency cleanup without confirmation

Log Directories:
    Project Logs: ${PROJECT_ROOT}/logs/
    ROS2 Logs:    \$ROS_LOG_DIR or ~/.ros/log/
    Build Logs:   ${PROJECT_ROOT}/build/log/
    Test Logs:    ${PROJECT_ROOT}/logs/test_suite/

EOF
}

# Setup log environment
setup_log_env() {
    print_info "Setting up log environment..."
    
    # Create log directories
    mkdir -p "${PROJECT_ROOT}/logs/"{runtime,tests,validation,archived,cleanup_reports}
    mkdir -p "${PROJECT_ROOT}/logs/ros2"
    
    # Set ROS_LOG_DIR environment variable
    export ROS_LOG_DIR="${PROJECT_ROOT}/logs/ros2"
    
    # Add to current session
    echo "export ROS_LOG_DIR=${PROJECT_ROOT}/logs/ros2" >> "${HOME}/.bashrc"
    
    print_success "Log environment setup completed"
    print_info "ROS2 logs will now be written to: $ROS_LOG_DIR"
    print_info "Added ROS_LOG_DIR to ~/.bashrc for future sessions"
}

# Show log status
show_log_status() {
    print_info "=== Pragati ROS2 Log Status ==="
    
    echo -e "\n${BLUE}Project Root:${NC} ${PROJECT_ROOT}"
    echo -e "${BLUE}ROS Log Directory:${NC} ${ROS_LOG_DIR:-~/.ros/log/}"
    
    echo -e "\n${BLUE}Log Directory Sizes:${NC}"
    
    # Check project logs
    if [ -d "${PROJECT_ROOT}/logs" ]; then
        size=$(du -sh "${PROJECT_ROOT}/logs" 2>/dev/null | cut -f1)
        files=$(find "${PROJECT_ROOT}/logs" -type f 2>/dev/null | wc -l)
        echo -e "  Project Logs:     ${size} (${files} files)"
    else
        echo -e "  Project Logs:     ${YELLOW}Not found${NC}"
    fi
    
    # Check ROS2 logs
    ros_log_path="${ROS_LOG_DIR:-${HOME}/.ros/log}"
    if [ -d "$ros_log_path" ]; then
        size=$(du -sh "$ros_log_path" 2>/dev/null | cut -f1)
        dirs=$(find "$ros_log_path" -maxdepth 1 -type d 2>/dev/null | wc -l)
        echo -e "  ROS2 Logs:        ${size} (${dirs} directories)"
    else
        echo -e "  ROS2 Logs:        ${YELLOW}Not found${NC}"
    fi
    
    # Check build logs
    if [ -d "${PROJECT_ROOT}/build/log" ]; then
        size=$(du -sh "${PROJECT_ROOT}/build/log" 2>/dev/null | cut -f1)
        files=$(find "${PROJECT_ROOT}/build/log" -type f 2>/dev/null | wc -l)
        echo -e "  Build Logs:       ${size} (${files} files)"
    else
        echo -e "  Build Logs:       ${YELLOW}Not found${NC}"
    fi
    
    # Check install logs
    if [ -d "${PROJECT_ROOT}/install/log" ]; then
        size=$(du -sh "${PROJECT_ROOT}/install/log" 2>/dev/null | cut -f1)
        files=$(find "${PROJECT_ROOT}/install/log" -type f 2>/dev/null | wc -l)
        echo -e "  Install Logs:     ${size} (${files} files)"
    else
        echo -e "  Install Logs:     ${YELLOW}Not found${NC}"
    fi
    
    echo -e "\n${BLUE}Recent Activity:${NC}"
    
    # Show recent log files
    recent_files=$(find "${PROJECT_ROOT}" -name "*.log" -mtime -1 2>/dev/null | head -5)
    if [ -n "$recent_files" ]; then
        echo -e "  Recent log files (last 24h):"
        echo "$recent_files" | while read -r file; do
            if [ -n "$file" ]; then
                size=$(ls -lh "$file" 2>/dev/null | awk '{print $5}')
                echo -e "    $(basename "$file") (${size})"
            fi
        done
    else
        echo -e "  ${YELLOW}No recent log files found${NC}"
    fi
}

# Ask for confirmation
confirm_action() {
    local message="$1"
    if [ "$FORCE" = true ]; then
        return 0
    fi
    
    echo -e "${YELLOW}${message}${NC}"
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Operation cancelled"
        exit 0
    fi
}

# Run log manager with specified parameters
run_log_manager() {
    local cmd_args=("$@")
    
    if [ "$VERBOSE" = true ]; then
        cmd_args+=("--verbose")
    fi
    
    if [ "$NO_COMPRESS" = true ]; then
        cmd_args+=("--no-compress")
    fi
    
    python3 "$LOG_MANAGER" --project-root "$PROJECT_ROOT" "${cmd_args[@]}"
}

# Parse command line arguments
COMMAND=""
DAYS=7
SIZE=100
VERBOSE=false
NO_COMPRESS=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        clean|quick-clean|status|dry-run|compress|emergency|ros-clean|setup)
            COMMAND="$1"
            ;;
        --days)
            DAYS="$2"
            shift
            ;;
        --size)
            SIZE="$2"
            shift
            ;;
        --verbose)
            VERBOSE=true
            ;;
        --no-compress)
            NO_COMPRESS=true
            ;;
        --force)
            FORCE=true
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

# Default command
if [ -z "$COMMAND" ]; then
    COMMAND="clean"
fi

# Main execution
case $COMMAND in
    setup)
        setup_log_env
        ;;
        
    status)
        show_log_status
        ;;
        
    clean)
        confirm_action "This will clean logs older than $DAYS days and compress old files."
        print_info "Running full log cleanup (max age: ${DAYS} days, max size: ${SIZE} MB)..."
        run_log_manager --max-age-days "$DAYS" --max-size-mb "$SIZE"
        print_success "Log cleanup completed"
        ;;
        
    quick-clean)
        DAYS=3
        SIZE=50
        confirm_action "This will perform a quick cleanup (3 days, 50MB limit)."
        print_info "Running quick log cleanup..."
        run_log_manager --max-age-days "$DAYS" --max-size-mb "$SIZE"
        print_success "Quick cleanup completed"
        ;;
        
    dry-run)
        print_info "Running dry-run to show what would be cleaned..."
        run_log_manager --max-age-days "$DAYS" --max-size-mb "$SIZE" --dry-run
        ;;
        
    emergency)
        DAYS=1
        confirm_action "EMERGENCY CLEANUP: This will remove ALL logs older than 1 day!"
        print_warning "Running emergency cleanup..."
        run_log_manager --max-age-days "$DAYS" --max-size-mb 10
        print_success "Emergency cleanup completed"
        ;;
        
    ros-clean)
        confirm_action "This will clean external ROS2 logs in ~/.ros/log/"
        print_info "Cleaning external ROS2 logs..."
        # Clean external ROS2 logs specifically
        if [ -d "${HOME}/.ros/log" ]; then
            find "${HOME}/.ros/log" -maxdepth 1 -type d -mtime +$DAYS -exec rm -rf {} \; 2>/dev/null || true
            print_success "External ROS2 logs cleaned"
        else
            print_info "No external ROS2 logs found"
        fi
        ;;
        
    *)
        print_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac