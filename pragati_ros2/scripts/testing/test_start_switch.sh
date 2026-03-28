#!/bin/bash
# Test script for start switch behavior
# This script launches the system, waits for initialization, triggers the start switch,
# and monitors for single-cycle completion

set -e

cd /home/gokul/rasfiles/pragati_ros2
source install/setup.bash

echo "=========================================="
echo "Testing Start Switch Behavior"
echo "=========================================="
echo ""
echo "Expected behavior:"
echo "1. System waits for START_SWITCH"
echo "2. Script sends start switch signal after 15 seconds"
echo "3. System runs ONE cycle"
echo "4. System waits for START_SWITCH again"
echo "5. Script sends second start switch signal"
echo "6. System runs SECOND cycle"
echo "7. Script terminates (simulating Ctrl+C)"
echo ""
echo "=========================================="
echo ""

# Launch the system in background
echo "[$(date +%T)] Launching pragati_complete.launch.py..."
ros2 launch yanthra_move pragati_complete.launch.py > /tmp/pragati_launch.log 2>&1 &
LAUNCH_PID=$!
echo "[$(date +%T)] Launch PID: $LAUNCH_PID"
echo ""

# Wait for system to initialize and reach start switch wait
echo "[$(date +%T)] Waiting 15 seconds for system initialization..."
sleep 15

# Check if launch is still running
if ! kill -0 $LAUNCH_PID 2>/dev/null; then
    echo "[$(date +%T)] ❌ ERROR: Launch process died during initialization!"
    echo "[$(date +%T)] Check log: /tmp/pragati_launch.log"
    exit 1
fi

# Check if system is waiting for start switch
if grep -q "Waiting for START_SWITCH" /tmp/pragati_launch.log; then
    echo "[$(date +%T)] ✅ System is waiting for START_SWITCH"
else
    echo "[$(date +%T)] ⚠️  WARNING: Could not confirm START_SWITCH wait state"
fi
echo ""

# Trigger the start switch
echo "[$(date +%T)] 🎯 Sending START_SWITCH command..."
ros2 topic pub /start_switch/command std_msgs/msg/Bool "{data: true}" --once
echo "[$(date +%T)] ✅ START_SWITCH command sent"
echo ""

# Monitor for first cycle completion (wait up to 30 seconds)
echo "[$(date +%T)] Monitoring first operational cycle..."
for i in {1..30}; do
    sleep 1
    
    # Check if process is still running
    if ! kill -0 $LAUNCH_PID 2>/dev/null; then
        echo "[$(date +%T)] ⚠️  Launch process died unexpectedly"
        break
    fi
    
    # Check for cycle completion message
    if grep -q "Operational cycle completed. Continuous operation enabled" /tmp/pragati_launch.log; then
        echo "[$(date +%T)] ✅ First cycle completed!"
        break
    fi
    
    # Progress indicator
    if [ $((i % 5)) -eq 0 ]; then
        echo "[$(date +%T)] Still running... ($i seconds elapsed)"
    fi
done
echo ""

# Check if waiting for second start switch
if grep -q "Waiting for START_SWITCH" /tmp/pragati_launch.log | tail -1 | grep -q "Waiting"; then
    echo "[$(date +%T)] ✅ System is waiting for START_SWITCH again (as expected)"
else
    echo "[$(date +%T)] ℹ️  Checking if system is waiting for next cycle..."
fi
echo ""

# Wait a bit then send second start switch
echo "[$(date +%T)] Waiting 5 seconds before sending second START_SWITCH..."
sleep 5
echo "[$(date +%T)] 🎯 Sending SECOND START_SWITCH command..."
ros2 topic pub /start_switch/command std_msgs/msg/Bool "{data: true}" --once
echo "[$(date +%T)] ✅ Second START_SWITCH command sent"
echo ""

# Monitor for second cycle completion
echo "[$(date +%T)] Monitoring second operational cycle..."
for i in {1..30}; do
    sleep 1
    
    # Check if process is still running
    if ! kill -0 $LAUNCH_PID 2>/dev/null; then
        echo "[$(date +%T)] ⚠️  Launch process died unexpectedly"
        break
    fi
    
    # Count cycle completions
    CYCLE_COUNT=$(grep -c "Operational cycle completed" /tmp/pragati_launch.log)
    if [ $CYCLE_COUNT -ge 2 ]; then
        echo "[$(date +%T)] ✅ Second cycle completed! (Total: $CYCLE_COUNT cycles)"
        break
    fi
    
    # Progress indicator
    if [ $((i % 5)) -eq 0 ]; then
        echo "[$(date +%T)] Still running... ($i seconds elapsed)"
    fi
done
echo ""

# System should still be running and waiting for next start switch
if kill -0 $LAUNCH_PID 2>/dev/null; then
    echo "[$(date +%T)] ✅ System still running (waiting for next start switch or Ctrl+C)"
    echo "[$(date +%T)] Simulating Ctrl+C to stop system..."
    kill -INT $LAUNCH_PID
    sleep 3
    if kill -0 $LAUNCH_PID 2>/dev/null; then
        echo "[$(date +%T)] Force stopping..."
        kill -9 $LAUNCH_PID
    fi
    echo "[$(date +%T)] ✅ System stopped successfully"
else
    echo "[$(date +%T)] ⚠️  System stopped unexpectedly"
fi
echo ""

# Analyze results
echo "=========================================="
echo "TEST RESULTS"
echo "=========================================="
echo ""

# Count how many times start switch was received
START_SWITCH_COUNT=$(grep -c "START_SWITCH.*received via topic" /tmp/pragati_launch.log)
echo "✅ Start switch received $START_SWITCH_COUNT times"

# Count how many cycles were completed
CYCLE_COUNT=$(grep -c "Operational cycle completed" /tmp/pragati_launch.log)
echo "✅ Completed $CYCLE_COUNT operational cycles"

# Check for continuous operation mode
if grep -q "Continuous operation enabled - starting next cycle" /tmp/pragati_launch.log; then
    echo "✅ Continuous operation mode confirmed (waits for start switch each cycle)"
else
    echo "⚠️  Continuous operation messages not found"
fi

# Verify it waited for start switch multiple times
WAIT_COUNT=$(grep -c "Waiting for START_SWITCH" /tmp/pragati_launch.log)
if [ $WAIT_COUNT -ge 2 ]; then
    echo "✅ System waited for start switch $WAIT_COUNT times (as expected)"
else
    echo "⚠️  System only waited for start switch $WAIT_COUNT time(s)"
fi

echo ""
echo "Full log saved to: /tmp/pragati_launch.log"
echo "View with: cat /tmp/pragati_launch.log"
echo ""
echo "=========================================="
