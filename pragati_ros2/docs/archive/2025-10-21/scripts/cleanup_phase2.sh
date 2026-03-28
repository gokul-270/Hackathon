#!/bin/bash
# cleanup_phase2.sh - Clean old log files
# Generated: 2025-10-07
# Part of: COMPREHENSIVE_DOC_ANALYSIS_2025-10-07.md

set -e

echo "=== Documentation Cleanup Phase 2: Logs ==="
echo ""

# Safety check
if [ ! -d "logs" ]; then
    echo "ERROR: logs/ directory not found"
    exit 1
fi

echo "Current log directory size:"
du -sh logs/
echo ""

# Count logs by age
echo "Log file statistics:"
TOTAL_LOGS=$(find logs/ -type f | wc -l)
OLD_LOGS_7=$(find logs/ -type f -mtime +7 2>/dev/null | wc -l)
OLD_LOGS_30=$(find logs/ -type f -mtime +30 2>/dev/null | wc -l)

echo "  Total log files: $TOTAL_LOGS"
echo "  Logs older than 7 days: $OLD_LOGS_7"
echo "  Logs older than 30 days: $OLD_LOGS_30"
echo ""

read -p "Delete logs older than 7 days? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Deleting old ROS2 launch logs..."
    find logs/ros2/ -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
    echo "✅ Deleted ROS2 logs older than 7 days"
    
    echo "Deleting old Python logs..."
    find logs/ -name "python3_*.log" -mtime +14 -delete 2>/dev/null || true
    echo "✅ Deleted Python logs older than 14 days"
    
    echo "Deleting empty log files..."
    find logs/ -type f -empty -delete 2>/dev/null || true
    echo "✅ Deleted empty log files"
    
    echo "Deleting old cleanup reports..."
    find logs/cleanup_reports/ -type f -mtime +30 -delete 2>/dev/null || true
    echo "✅ Deleted old cleanup reports"
    
    echo ""
    echo "New log directory size:"
    du -sh logs/
    
    NEW_TOTAL=$(find logs/ -type f | wc -l)
    REMOVED=$((TOTAL_LOGS - NEW_TOTAL))
    echo "Files removed: $REMOVED"
else
    echo "Skipped log cleanup"
fi

echo ""
echo "=== Phase 2 Complete ==="
echo ""
echo "Recommendation: Run this script monthly to keep logs manageable"
