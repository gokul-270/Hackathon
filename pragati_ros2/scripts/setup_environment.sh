#!/bin/bash
#
# Pragati ROS2 Environment Setup Script
# =====================================
#
# This script sets up the complete environment for the Pragati ROS2 project
# including proper log management, ROS2 configuration, and workspace setup.
#
# Features:
# - Sets up ROS2 log directory within project
# - Configures log management and cleanup
# - Ensures all logging stays within project folders
# - Sets up aliases and convenience functions
#
# Author: Generated for Pragati ROS2 Project
# Date: 2025-09-18
#

set -e

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

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

print_info "Setting up Pragati ROS2 environment..."
print_info "Project root: $PROJECT_ROOT"

# Function to add line to bashrc if not already present
add_to_bashrc() {
    local line="$1"
    local bashrc="$HOME/.bashrc"
    
    if ! grep -q "$line" "$bashrc" 2>/dev/null; then
        echo "$line" >> "$bashrc"
        print_info "Added to ~/.bashrc: $line"
    else
        print_info "Already in ~/.bashrc: $line"
    fi
}

# Create log directories
setup_log_directories() {
    print_info "Creating log directories..."
    
    local log_dirs=(
        "logs"
        "logs/runtime"
        "logs/tests"
        "logs/validation" 
        "logs/archived"
        "logs/ros2"
        "logs/cleanup_reports"
        "logs/build"
        "logs/install"
    )
    
    for dir in "${log_dirs[@]}"; do
        mkdir -p "${PROJECT_ROOT}/${dir}"
        print_info "Created: ${PROJECT_ROOT}/${dir}"
    done
}

# Setup ROS2 environment
setup_ros2_environment() {
    print_info "Configuring ROS2 environment..."
    
    # Set ROS_LOG_DIR to project directory
    local ros_log_dir="${PROJECT_ROOT}/logs/ros2"
    export ROS_LOG_DIR="$ros_log_dir"
    
    # Add to bashrc
    add_to_bashrc "# Pragati ROS2 Project Environment"
    add_to_bashrc "export ROS_LOG_DIR=\"$ros_log_dir\""
    add_to_bashrc "export PRAGATI_PROJECT_ROOT=\"$PROJECT_ROOT\""
    
    # Source ROS2 setup if available
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        add_to_bashrc "source /opt/ros/jazzy/setup.bash"
        print_info "Added ROS2 Jazzy setup to bashrc"
    elif [ -f "/opt/ros/humble/setup.bash" ]; then
        add_to_bashrc "source /opt/ros/humble/setup.bash"
        print_info "Added ROS2 Humble setup to bashrc"
    elif [ -f "/opt/ros/galactic/setup.bash" ]; then
        add_to_bashrc "source /opt/ros/galactic/setup.bash"
        print_info "Added ROS2 Galactic setup to bashrc"
    else
        print_warning "No ROS2 installation found in /opt/ros/"
    fi
    
    # Add project workspace setup
    if [ -f "${PROJECT_ROOT}/install/setup.bash" ]; then
        add_to_bashrc "source \"${PROJECT_ROOT}/install/setup.bash\""
        print_info "Added project workspace setup to bashrc"
    fi
    
    print_success "ROS2 environment configured"
    print_info "ROS2 logs will be written to: $ros_log_dir"
}

# Setup convenience aliases and functions
setup_aliases() {
    print_info "Setting up convenience aliases and functions..."
    
    # Add aliases to bashrc
    add_to_bashrc ""
    add_to_bashrc "# Pragati ROS2 Project Aliases"
    add_to_bashrc "alias pragati-cd='cd \"$PROJECT_ROOT\"'"
    add_to_bashrc "alias pragati-build='cd \"$PROJECT_ROOT\" && colcon build'"
    add_to_bashrc "alias pragati-test='cd \"$PROJECT_ROOT\" && colcon test'"
    add_to_bashrc "alias pragati-logs='cd \"$PROJECT_ROOT/logs\"'"
    add_to_bashrc "alias pragati-clean-logs='\"$PROJECT_ROOT/scripts/monitoring/clean_logs.sh\"'"
    add_to_bashrc "alias pragati-log-status='\"$PROJECT_ROOT/scripts/monitoring/clean_logs.sh\" status'"
    
    # Add convenience functions
    cat >> "$HOME/.bashrc" << 'EOF'

# Pragati ROS2 Project Functions
pragati-launch() {
    cd "$PRAGATI_PROJECT_ROOT" && source install/setup.bash && ros2 launch pragati_complete "$@"
}

pragati-run() {
    cd "$PRAGATI_PROJECT_ROOT" && source install/setup.bash && ros2 run "$@"  
}

pragati-setup() {
    cd "$PRAGATI_PROJECT_ROOT" && source install/setup.bash
    echo "Pragati ROS2 environment activated"
}

pragati-clean-build() {
    cd "$PRAGATI_PROJECT_ROOT"
    rm -rf build/ install/ log/
    echo "Build artifacts cleaned"
}

pragati-full-clean() {
    cd "$PRAGATI_PROJECT_ROOT"
    "$PRAGATI_PROJECT_ROOT/scripts/monitoring/clean_logs.sh" clean --force
    rm -rf build/ install/ log/
    echo "Full cleanup completed"
}

EOF
    
    print_success "Aliases and functions added to ~/.bashrc"
}

# Setup automatic log cleanup via cron (optional)
setup_automatic_cleanup() {
    print_info "Setting up automatic log cleanup..."
    
    # Create a simple cron job for daily cleanup
    local cron_script="${PROJECT_ROOT}/scripts/maintenance/daily_cleanup.sh"
    
    cat > "$cron_script" << EOF
#!/bin/bash
# Daily log cleanup for Pragati ROS2 project
# Generated by setup script

cd "${PROJECT_ROOT}"
"${PROJECT_ROOT}/scripts/monitoring/clean_logs.sh" clean --force --days 7 --size 100 >> "${PROJECT_ROOT}/logs/cleanup_reports/daily_cleanup.log" 2>&1
EOF
    
    chmod +x "$cron_script"
    
    print_info "Created daily cleanup script: $cron_script"
    print_info "To enable automatic daily cleanup, run:"
    print_info "  crontab -e"
    print_info "And add the following line:"
    print_info "  0 2 * * * $cron_script"
    print_info "This will run cleanup daily at 2 AM"
}

# Setup log rotation configuration
setup_log_rotation() {
    print_info "Setting up log rotation configuration..."
    
    local logrotate_config="${PROJECT_ROOT}/configs/logrotate.conf"
    mkdir -p "$(dirname "$logrotate_config")"
    
    cat > "$logrotate_config" << EOF
# Logrotate configuration for Pragati ROS2 project
# Usage: logrotate -s ${PROJECT_ROOT}/logs/.logrotate_status ${PROJECT_ROOT}/configs/logrotate.conf

${PROJECT_ROOT}/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    sharedscripts
    postrotate
        echo "Log rotation completed on \$(date)" >> ${PROJECT_ROOT}/logs/logrotate.log
    endscript
}

${PROJECT_ROOT}/logs/*/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    size 10M
}

${PROJECT_ROOT}/logs/ros2/* {
    weekly
    missingok
    rotate 4
    compress
    delaycompress
    notifempty
    size 50M
    sharedscripts
}
EOF
    
    print_info "Created logrotate configuration: $logrotate_config"
    
    # Create a script to run logrotate
    local logrotate_script="${PROJECT_ROOT}/scripts/monitoring/rotate_logs.sh"
    cat > "$logrotate_script" << EOF
#!/bin/bash
# Log rotation script for Pragati ROS2 project

cd "${PROJECT_ROOT}"
logrotate -s "${PROJECT_ROOT}/logs/.logrotate_status" "${PROJECT_ROOT}/configs/logrotate.conf" -v
EOF
    
    chmod +x "$logrotate_script"
    print_info "Created log rotation script: $logrotate_script"
}

# Create a status script
create_status_script() {
    local status_script="${PROJECT_ROOT}/scripts/pragati_status.sh"
    
    cat > "$status_script" << EOF
#!/bin/bash
# Pragati ROS2 Project Status Script

echo "=== Pragati ROS2 Project Status ==="
echo
echo "Project Root: $PROJECT_ROOT"
echo "ROS Log Directory: \$ROS_LOG_DIR"
echo "Current Directory: \$(pwd)"
echo

# Show workspace status
echo "=== Workspace Status ==="
if [ -f "${PROJECT_ROOT}/install/setup.bash" ]; then
    echo "✅ Workspace built (install/setup.bash exists)"
else
    echo "❌ Workspace not built (run: colcon build)"
fi

# Show log status
"${PROJECT_ROOT}/scripts/monitoring/clean_logs.sh" status

# Show running ROS2 processes
echo
echo "=== Active ROS2 Processes ==="
if pgrep -f "ros2" > /dev/null; then
    echo "✅ ROS2 processes running:"
    pgrep -af "ros2" | head -5
else
    echo "❌ No ROS2 processes running"
fi

# Show recent activity
echo
echo "=== Recent Activity ==="
if [ -d "${PROJECT_ROOT}/logs" ]; then
    recent_logs=\$(find "${PROJECT_ROOT}/logs" -name "*.log" -mtime -1 2>/dev/null | wc -l)
    echo "Recent log files (last 24h): \$recent_logs"
else
    echo "No recent activity"
fi
EOF
    
    chmod +x "$status_script"
    add_to_bashrc "alias pragati-status='\"$status_script\"'"
    print_info "Created status script: $status_script"
}

# Main setup execution
main() {
    print_info "Starting Pragati ROS2 environment setup..."
    
    # Setup components
    setup_log_directories
    setup_ros2_environment
    setup_aliases
    setup_automatic_cleanup
    setup_log_rotation
    create_status_script
    
    print_success "Environment setup completed!"
    
    echo
    print_info "=== Next Steps ==="
    print_info "1. Restart your terminal or run: source ~/.bashrc"
    print_info "2. Build the workspace: pragati-build"
    print_info "3. Check status: pragati-status"
    print_info "4. View log status: pragati-log-status"
    print_info "5. Clean logs: pragati-clean-logs"
    
    echo
    print_info "=== Available Commands ==="
    print_info "  pragati-cd           - Go to project root"
    print_info "  pragati-build        - Build the workspace"
    print_info "  pragati-test         - Run tests"
    print_info "  pragati-launch <args> - Launch ROS2 nodes"
    print_info "  pragati-setup        - Source workspace environment"
    print_info "  pragati-status       - Show project status"
    print_info "  pragati-clean-logs   - Clean old log files"
    print_info "  pragati-log-status   - Show log directory status"
    
    echo
    print_warning "Please restart your terminal or run 'source ~/.bashrc' to activate the new environment."
}

# Check if being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
else
    print_info "Script is being sourced - running setup..."
    main "$@"
fi