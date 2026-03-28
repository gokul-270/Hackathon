#!/bin/bash
################################################################################
# Module 06: Python Dependencies
# Installs Python packages from requirements.txt system-wide
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
source "${SCRIPT_DIR}/../common.sh"

REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

log_step "Installing Python dependencies"

# Check requirements.txt exists
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    log_error "requirements.txt not found at $REQUIREMENTS_FILE"
    exit 1
fi

# Install system-wide (Ubuntu 24.04 uses PEP 668 externally-managed-environment)
log_install "Python dependencies (requirements.txt)" "pip"
pip3 install --upgrade pip --break-system-packages
if pip3 install --break-system-packages -r "$REQUIREMENTS_FILE"; then
    log_success "Python dependencies (requirements.txt)" "installed system-wide"
else
    log_fail "Python dependencies (requirements.txt)" "pip install failed"
    exit 1
fi

# Validate
if [ -f "${PROJECT_ROOT}/scripts/validate_python_deps.sh" ]; then
    log_step "Validating Python dependencies"
    "${PROJECT_ROOT}/scripts/validate_python_deps.sh"
fi
