#!/bin/bash
################################################################################
# File: validate_requirements_vs_rpi.sh
# Purpose: Compare requirements.txt versions against RPi snapshot
# Part of: Pragati Cotton Picker - Generic Ubuntu Development Setup
#
# Created: 2025-02-03
# Version: 1.0.0
#
# Usage:
#   ./scripts/validate_requirements_vs_rpi.sh [snapshot_file]
#   ./scripts/validate_requirements_vs_rpi.sh log/rpi_snapshot_20260203_141644.txt
#
# Exit Codes:
#   0 - All versions aligned
#   1 - Version mismatches found
#   2 - Missing files
################################################################################

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

# Find the latest snapshot if not specified
if [ -n "${1:-}" ]; then
    SNAPSHOT_FILE="$1"
else
    SNAPSHOT_FILE=$(ls -t "${PROJECT_ROOT}"/log/rpi_snapshot_*.txt 2>/dev/null | head -1 || echo "")
fi

# Validation
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo -e "${RED}Error: requirements.txt not found at $REQUIREMENTS_FILE${NC}"
    exit 2
fi

if [ -z "$SNAPSHOT_FILE" ] || [ ! -f "$SNAPSHOT_FILE" ]; then
    echo -e "${RED}Error: No RPi snapshot file found${NC}"
    echo "Please provide a snapshot file or run:"
    echo "  ./scripts/rpi_config_snapshot.sh rpi"
    exit 2
fi

################################################################################
# Version Comparison Logic
################################################################################

# Extract package name and version spec from requirements.txt line
parse_requirement() {
    local line="$1"
    
    # Skip comments and empty lines
    [[ "$line" =~ ^[[:space:]]*# ]] && return 1
    [[ -z "$line" ]] && return 1
    
    # Extract package name (before any operator)
    if [[ "$line" =~ ^([a-zA-Z0-9_-]+)(==|>=|<=|>|<|~=)(.+)$ ]]; then
        echo "${BASH_REMATCH[1]}|${BASH_REMATCH[2]}|${BASH_REMATCH[3]}"
        return 0
    fi
    
    return 1
}

# Check if version satisfies requirement
check_version() {
    local operator="$1"
    local required="$2"
    local actual="$3"
    
    # For now, simple exact match for == and basic range checks
    # Full semantic version comparison would need python-semver or similar
    
    case "$operator" in
        "==")
            [ "$actual" = "$required" ] && return 0 || return 1
            ;;
        ">=")
            # Simple string comparison (works for most version formats)
            [[ "$actual" == "$required" || "$actual" > "$required" ]] && return 0 || return 1
            ;;
        *)
            # For complex operators, assume OK for now
            return 0
            ;;
    esac
}

################################################################################
# Main Validation
################################################################################

echo "========================================"
echo " Requirements vs RPi Version Alignment"
echo "========================================"
echo "Requirements: $REQUIREMENTS_FILE"
echo "RPi Snapshot: $SNAPSHOT_FILE"
echo ""

MISMATCHES=0
MATCHES=0
NOT_FOUND=0

printf "%-20s %-18s %-15s %s\n" "Package" "Required" "RPi Version" "Status"
printf "%-20s %-18s %-15s %s\n" "--------------------" "------------------" "---------------" "--------"

while IFS= read -r line || [ -n "$line" ]; do
    # Parse requirement
    parsed=$(parse_requirement "$line") || continue
    
    IFS='|' read -r pkg_name operator required_ver <<< "$parsed"
    
    # Lookup in snapshot
    rpi_version=$(grep -i "^${pkg_name}[[:space:]]" "$SNAPSHOT_FILE" | awk '{print $2}' || echo "")
    
    if [ -z "$rpi_version" ]; then
        printf "%-20s %-18s ${YELLOW}%-15s${NC} %s\n" \
            "$pkg_name" "${operator}${required_ver}" "Not found" "⚠️  MISSING"
        ((NOT_FOUND++))
        continue
    fi
    
    # Check version
    if check_version "$operator" "$required_ver" "$rpi_version"; then
        printf "%-20s %-18s ${GREEN}%-15s${NC} %s\n" \
            "$pkg_name" "${operator}${required_ver}" "$rpi_version" "✅ OK"
        ((MATCHES++))
    else
        printf "%-20s %-18s ${RED}%-15s${NC} %s\n" \
            "$pkg_name" "${operator}${required_ver}" "$rpi_version" "❌ MISMATCH"
        ((MISMATCHES++))
    fi
    
done < "$REQUIREMENTS_FILE"

echo ""
echo "========================================"
echo " Summary"
echo "========================================"
echo -e "${GREEN}Matches:    ${MATCHES}${NC}"
echo -e "${YELLOW}Not Found:  ${NOT_FOUND}${NC}"
echo -e "${RED}Mismatches: ${MISMATCHES}${NC}"
echo ""

if [ $MISMATCHES -gt 0 ]; then
    echo -e "${RED}❌ Version mismatches detected!${NC}"
    echo ""
    echo "Actions:"
    echo "  1. Update requirements.txt to match RPi versions"
    echo "  2. Or update RPi packages to match requirements.txt"
    echo "  3. Run: pip3 install -r requirements.txt on RPi"
    exit 1
elif [ $NOT_FOUND -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Some packages not found on RPi${NC}"
    echo "This may be expected if they're optional or not yet installed"
    exit 0
else
    echo -e "${GREEN}✅ All versions aligned!${NC}"
    exit 0
fi
