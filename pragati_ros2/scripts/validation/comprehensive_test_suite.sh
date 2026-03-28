#!/bin/bash
# Wrapper to maintain backwards compatibility for the comprehensive test suite
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/system/comprehensive_test_suite.sh" "$@"
