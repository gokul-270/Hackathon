#!/bin/bash
# Quick timing measurement script
# Usage: ./measure_pick_timing.sh

echo "🔍 Measuring cotton picking timing..."
echo "This will analyze recent log files for timing data"
echo ""

# Check if ros2 is running
if ! ros2 topic list &>/dev/null; then
    echo "❌ ROS2 not running. Please start the system first."
    exit 1
fi

# Monitor detection and picking for 30 seconds
echo "📊 Recording 30 seconds of operation..."
timeout 30s ros2 topic echo /cotton_detection/results | grep -E "(stamp|processing_time_ms|total_count)" > /tmp/timing_data.txt

echo ""
echo "✅ Data collected. Analyzing..."
echo ""
echo "=== TIMING ANALYSIS ==="
grep "processing_time_ms" /tmp/timing_data.txt | awk '{sum+=$2; count++} END {print "Average detection time: " sum/count " ms"}'

echo ""
echo "💡 Next: Check yanthra_move logs for approach/grasp timing"
echo "Run: ros2 topic hz /cotton_detection/results"
