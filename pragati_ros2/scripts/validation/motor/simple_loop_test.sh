#!/bin/bash
# Simple Loop Test - Runs quick motor test multiple times
# Usage: ./simple_loop_test.sh [motor_id] [can_id] [iterations]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${PRAGATI_WORKSPACE:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SETUP_FILE="${WORKSPACE_ROOT}/install/setup.bash"
QUICK_TEST="$SCRIPT_DIR/quick_motor_test.sh"

if [[ ! -f "$SETUP_FILE" ]]; then
    echo "✗ ROS2 workspace not built. Expected setup file at: $SETUP_FILE"
    exit 1
fi

if [[ ! -x "$QUICK_TEST" ]]; then
    echo "✗ quick_motor_test.sh missing at $QUICK_TEST"
    exit 1
fi

source "$SETUP_FILE"

MOTOR_ID=${1:-1}
CAN_ID=${2:-141}
ITERATIONS=${3:-10}

printf "════════════════════════════════════════════════════════════\n"
printf "  LOOP MOTOR TEST - Motor %s (CAN %s)\n" "$MOTOR_ID" "$CAN_ID"
printf "  Running %s iterations\n" "$ITERATIONS"
printf "════════════════════════════════════════════════════════════\n\n"

PASS_COUNT=0
FAIL_COUNT=0

for i in $(seq 1 "$ITERATIONS"); do
    printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    printf "ITERATION %s of %s\n" "$i" "$ITERATIONS"
    printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    LOG_FILE="/tmp/motor_test_${i}.log"
    if bash "$QUICK_TEST" "$MOTOR_ID" "$CAN_ID" > "$LOG_FILE" 2>&1; then
        echo "✓ PASSED - All 7 tests successful"
        PASS_COUNT=$((PASS_COUNT+1))
        grep "Temperature\|Current angle\|speed=" "$LOG_FILE" | head -3 || true
    else
        echo "✗ FAILED - Some tests failed"
        FAIL_COUNT=$((FAIL_COUNT+1))
        grep "✗ FAILED" "$LOG_FILE" || true
    fi
    echo ""
    sleep 1
done

printf "\n════════════════════════════════════════════════════════════\n"
printf "               FINAL RESULTS\n"
printf "════════════════════════════════════════════════════════════\n"
printf "Total Iterations: %s\n" "$ITERATIONS"
printf "Successful: %s\n" "$PASS_COUNT"
printf "Failed: %s\n" "$FAIL_COUNT"

SUCCESS_RATE=$((PASS_COUNT * 100 / ITERATIONS))
printf "Success Rate: %s%%\n\n" "$SUCCESS_RATE"

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo "✓✓✓ ALL $ITERATIONS ITERATIONS PASSED ✓✓✓"
    echo "Motor $MOTOR_ID is HIGHLY RELIABLE!"
    exit 0
else
    echo "⚠ $FAIL_COUNT iterations had failures"
    echo "Check logs in /tmp/motor_test_*.log for details"
    exit 1
fi
