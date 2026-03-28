#!/bin/bash
# Run stress test in background and save results

cd ~/pragati_ros2

# Run stress test in background, save to file
nohup bash full_stress_test.sh > /tmp/stress_test_full_output.txt 2>&1 &
TEST_PID=$!

echo "=========================================="
echo "Stress Test Started in Background"
echo "=========================================="
echo "PID: $TEST_PID"
echo "Output file: /tmp/stress_test_full_output.txt"
echo ""
echo "To monitor progress:"
echo "  tail -f /tmp/stress_test_full_output.txt"
echo ""
echo "To check status:"
echo "  ps aux | grep $TEST_PID"
echo ""
echo "Test will run for approximately 8-10 minutes"
echo "=========================================="
