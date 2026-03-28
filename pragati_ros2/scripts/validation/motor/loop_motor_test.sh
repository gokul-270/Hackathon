#!/bin/bash
# Loop Motor Test - Runs motor tests multiple times
# Usage: ./loop_motor_test.sh [motor_id] [can_id] [iterations]

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

printf "═══════════════════════════════════════════════════════════\n"
printf "  LOOP MOTOR TEST - Motor %s (CAN %s)\n" "$MOTOR_ID" "$CAN_ID"
printf "  Running %s iterations\n" "$ITERATIONS"
printf "═══════════════════════════════════════════════════════════\n\n"

TOTAL_PASS=0
TOTAL_FAIL=0

for i in $(seq 1 "$ITERATIONS"); do
    printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    printf "ITERATION %s of %s\n" "$i" "$ITERATIONS"
    printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    OUTPUT=$(bash "$QUICK_TEST" "$MOTOR_ID" "$CAN_ID" 2>&1)

    if echo "$OUTPUT" | grep -q "ALL TESTS PASSED"; then
        TOTAL_PASS=$((TOTAL_PASS+1))
        echo "✓ All 7 tests PASSED"
    else
        TOTAL_FAIL=$((TOTAL_FAIL+1))
        echo "✗ Some tests FAILED"
        echo "$OUTPUT" | grep "FAILED" || true
    fi

    echo ""
    sleep 1
done

printf "\n═══════════════════════════════════════════════════════════\n"
printf "               FINAL RESULTS\n"
printf "═══════════════════════════════════════════════════════════\n"
printf "Total Iterations: %s\n" "$ITERATIONS"
printf "Successful: %s\n" "$TOTAL_PASS"
printf "Failed: %s\n" "$TOTAL_FAIL"
printf "\n"

SUCCESS_RATE=$((TOTAL_PASS * 100 / ITERATIONS))
printf "Success Rate: %s%%\n\n" "$SUCCESS_RATE"

if [ $TOTAL_FAIL -eq 0 ]; then
    echo "✓✓✓ ALL ITERATIONS PASSED ✓✓✓"
    exit 0
else
    echo "⚠ Some iterations had failures"
    exit 1
fi
