#!/bin/bash
################################################################################
# File: rpi_config_snapshot.sh
# Purpose: Capture comprehensive RPi configuration snapshot
# Part of: Pragati Cotton Picker - Generic Ubuntu Development Setup
#
# Created: 2025-02-03
# Version: 1.0.0
#
# Usage:
#   ./scripts/rpi_config_snapshot.sh [hostname_or_ip]
#   ./scripts/rpi_config_snapshot.sh rpi
#   ./scripts/rpi_config_snapshot.sh 192.168.137.238
#   ./scripts/rpi_config_snapshot.sh  # Run locally on RPi
#
# Exit Codes:
#   0 - Success
#   1 - Error
################################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="${PROJECT_ROOT}/log"

# Parse target (local or remote)
TARGET="${1:-local}"

################################################################################
# Snapshot Collection Function
################################################################################

collect_snapshot() {
    local output_file="$1"
    
    {
        echo "========================================"
        echo " Pragati Cotton Picker - RPi Configuration Snapshot"
        echo "========================================"
        echo "Generated: $(date)"
        echo "Hostname: $(hostname)"
        echo "IP: $(hostname -I | awk '{print $1}')"
        echo ""
        
        echo "========================================"
        echo " System Information"
        echo "========================================"
        echo "--- OS Release ---"
        cat /etc/os-release
        echo ""
        echo "--- Kernel ---"
        uname -a
        echo ""
        echo "--- Architecture ---"
        uname -m
        echo ""
        echo "--- CPU Info ---"
        lscpu | grep -E "Architecture|CPU\(s\)|Model name|Thread" || cat /proc/cpuinfo | grep -E "processor|model name|Hardware|Revision" | head -10
        echo ""
        echo "--- Memory ---"
        free -h
        echo ""
        echo "--- Disk Usage ---"
        df -h /
        echo ""
        
        echo "========================================"
        echo " Python Environment"
        echo "========================================"
        echo "--- Python Version ---"
        python3 --version
        echo ""
        echo "--- Python Packages (pip3 list) ---"
        pip3 list 2>/dev/null || echo "pip3 not available"
        echo ""
        
        echo "========================================"
        echo " ROS2 Environment"
        echo "========================================"
        echo "--- ROS2 Version ---"
        if command -v ros2 &> /dev/null; then
            ros2 --version
            echo ""
            echo "--- ROS2 Packages ---"
            ros2 pkg list 2>/dev/null | head -50
            echo "... (truncated, see full list with 'ros2 pkg list')"
        else
            echo "ROS2 not installed"
        fi
        echo ""
        
        echo "========================================"
        echo " Network Configuration"
        echo "========================================"
        echo "--- Network Interfaces ---"
        ip addr show
        echo ""
        echo "--- Routing Table ---"
        ip route show
        echo ""
        
        echo "========================================"
        echo " System Services"
        echo "========================================"
        echo "--- Critical Services Status ---"
        for service in pigpiod ssh systemd-networkd; do
            if systemctl list-unit-files | grep -q "^${service}"; then
                echo "- $service: $(systemctl is-active $service 2>/dev/null || echo 'not found')"
            fi
        done
        echo ""
        
        echo "========================================"
        echo " Hardware Information"
        echo "========================================"
        echo "--- USB Devices ---"
        lsusb 2>/dev/null || echo "lsusb not available"
        echo ""
        echo "--- I2C Devices ---"
        i2cdetect -y 1 2>/dev/null || echo "i2cdetect not available or no I2C devices"
        echo ""
        
        echo "========================================"
        echo " Pragati Project Status"
        echo "========================================"
        if [ -d "$HOME/pragati_ros2" ]; then
            echo "--- Project Directory ---"
            ls -lh "$HOME/pragati_ros2/" 2>/dev/null | head -20
            echo ""
            
            echo "--- Git Status ---"
            cd "$HOME/pragati_ros2" 2>/dev/null && {
                echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
                echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
                echo "Status: $(git status --short | wc -l) modified files"
            }
        else
            echo "Project directory not found at ~/pragati_ros2"
        fi
        echo ""
        
        echo "========================================"
        echo " End of Snapshot"
        echo "========================================"
        
    } > "$output_file"
    
    echo "Snapshot saved to: $output_file"
    ls -lh "$output_file"
}

################################################################################
# Main Execution
################################################################################

if [ "$TARGET" = "local" ]; then
    # Running locally on RPi
    echo "Collecting snapshot on local system..."
    mkdir -p "$OUTPUT_DIR"
    OUTPUT_FILE="${OUTPUT_DIR}/rpi_snapshot_${TIMESTAMP}.txt"
    collect_snapshot "$OUTPUT_FILE"
    
else
    # Running remotely via SSH
    echo "Collecting snapshot from remote system: $TARGET"
    
    # Create log directory
    mkdir -p "$OUTPUT_DIR"
    OUTPUT_FILE="${OUTPUT_DIR}/rpi_snapshot_${TARGET}_${TIMESTAMP}.txt"
    
    # SSH into target and run snapshot collection
    # Note: Uses the RPi bridge if in WSL
    if [ -f "${SCRIPT_DIR}/rpi-wsl-bridge.sh" ]; then
        source "${SCRIPT_DIR}/rpi-wsl-bridge.sh" 2>/dev/null || true
        create_rpi_ssh_wrappers 2>/dev/null || true
    fi
    
    ssh "$TARGET" 'bash -s' << 'REMOTE_SCRIPT' > "$OUTPUT_FILE"
#!/bin/bash
set -euo pipefail

echo "========================================"
echo " Pragati Cotton Picker - RPi Configuration Snapshot"
echo "========================================"
echo "Generated: $(date)"
echo "Hostname: $(hostname)"
echo "IP: $(hostname -I | awk '{print $1}')"
echo ""

echo "========================================"
echo " System Information"
echo "========================================"
echo "--- OS Release ---"
cat /etc/os-release
echo ""
echo "--- Kernel ---"
uname -a
echo ""
echo "--- Architecture ---"
uname -m
echo ""
echo "--- Memory ---"
free -h
echo ""
echo "--- Disk Usage ---"
df -h /
echo ""

echo "========================================"
echo " Python Environment"
echo "========================================"
echo "--- Python Version ---"
python3 --version
echo ""
echo "--- Python Packages (pip3 list) ---"
pip3 list 2>/dev/null || echo "pip3 not available"
echo ""

echo "========================================"
echo " ROS2 Environment"
echo "========================================"
echo "--- ROS2 Version ---"
if command -v ros2 &> /dev/null; then
    ros2 --version
    echo ""
    echo "--- ROS2 Packages (first 50) ---"
    ros2 pkg list 2>/dev/null | head -50
else
    echo "ROS2 not installed"
fi
echo ""

echo "========================================"
echo " Network Configuration"
echo "========================================"
ip addr show
echo ""
ip route show
echo ""

echo "========================================"
echo " End of Snapshot"
echo "========================================"
REMOTE_SCRIPT
    
    echo "Snapshot saved to: $OUTPUT_FILE"
    ls -lh "$OUTPUT_FILE"
fi

echo ""
echo "To extract specific package versions:"
echo "  ./scripts/extract_rpi_versions.sh $OUTPUT_FILE"
echo ""
echo "To compare with requirements.txt:"
echo "  ./scripts/validate_requirements_vs_rpi.sh $OUTPUT_FILE"
