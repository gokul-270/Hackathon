#!/bin/bash
################################################################################
# File: extract_rpi_versions.sh
# Purpose: Extract package versions from RPi snapshot files
# Part of: Pragati Cotton Picker - Generic Ubuntu Development Setup
#
# Created: 2025-02-03
# Version: 1.0.0
#
# Usage:
#   ./scripts/extract_rpi_versions.sh <snapshot_file> [package_name]
#   ./scripts/extract_rpi_versions.sh log/rpi_snapshot_20260203_141644.txt
#   ./scripts/extract_rpi_versions.sh log/rpi_snapshot_20260203_141644.txt depthai
#
# Exit Codes:
#   0 - Success
#   1 - Error (file not found, invalid format, etc.)
################################################################################

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SNAPSHOT_FILE="${1:-}"
SPECIFIC_PACKAGE="${2:-}"

if [ -z "$SNAPSHOT_FILE" ]; then
    echo "Usage: $0 <snapshot_file> [package_name]"
    echo ""
    echo "Examples:"
    echo "  $0 log/rpi_snapshot_20260203_141644.txt"
    echo "  $0 log/rpi_snapshot_20260203_141644.txt depthai"
    exit 1
fi

if [ ! -f "$SNAPSHOT_FILE" ]; then
    echo "Error: Snapshot file not found: $SNAPSHOT_FILE"
    exit 1
fi

################################################################################
# Extract specific package or show critical packages
################################################################################

if [ -n "$SPECIFIC_PACKAGE" ]; then
    # Extract specific package
    echo "Searching for package: $SPECIFIC_PACKAGE"
    grep -i "^$SPECIFIC_PACKAGE[[:space:]]" "$SNAPSHOT_FILE" || echo "Package not found: $SPECIFIC_PACKAGE"
else
    # Show critical packages defined in requirements.txt
    echo "========================================"
    echo " Critical Package Versions from RPi"
    echo "========================================"
    echo "Source: $SNAPSHOT_FILE"
    echo ""
    
    CRITICAL_PACKAGES=(
        "depthai"
        "opencv-python"
        "numpy"
        "pillow"
        "scipy"
        "PyYAML"
        "pyserial"
        "python-can"
        "cantools"
        "pigpio"
    )
    
    printf "%-20s %s\n" "Package" "Version"
    printf "%-20s %s\n" "--------------------" "---------------"
    
    for pkg in "${CRITICAL_PACKAGES[@]}"; do
        version=$(grep -i "^$pkg[[:space:]]" "$SNAPSHOT_FILE" | awk '{print $2}' || echo "Not found")
        
        if [ "$version" = "Not found" ]; then
            printf "%-20s ${YELLOW}%s${NC}\n" "$pkg" "$version"
        else
            printf "%-20s ${GREEN}%s${NC}\n" "$pkg" "$version"
        fi
    done
    
    echo ""
    echo "========================================"
    echo " System Information"
    echo "========================================"
    
    # Extract OS version
    os_version=$(grep "PRETTY_NAME" "$SNAPSHOT_FILE" | cut -d'"' -f2 || echo "Unknown")
    kernel=$(grep "^Linux" "$SNAPSHOT_FILE" | awk '{print $3}' || echo "Unknown")
    
    echo "OS: $os_version"
    echo "Kernel: $kernel"
    
    echo ""
    echo "Tip: To see all packages, run:"
    echo "  grep -v '^#' $SNAPSHOT_FILE | grep -v '^$' | head -50"
fi
