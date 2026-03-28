#!/bin/bash

echo "🧪 Manual Logrotate Test"
echo "======================="
echo ""

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

echo "📋 Creating test logs..."
mkdir -p logs/test_logs
echo "Test log content $(date)" > logs/test_logs/test1.log
echo "Another test log $(date)" > logs/test_logs/test2.log
echo "Old test log $(date -d '2 days ago')" > logs/test_logs/old.log

echo "📊 Before logrotate:"
ls -la logs/test_logs/

echo ""
echo "🔄 Running logrotate..."
logrotate -s logs/.logrotate_state/status configs/logrotate.conf -v

echo ""
echo "📊 After logrotate:"
ls -la logs/test_logs/

echo ""
echo "✅ Logrotate test completed"
echo "🗂️  State file location: logs/.logrotate_state/status"
echo "⚙️  Config file: configs/logrotate.conf"