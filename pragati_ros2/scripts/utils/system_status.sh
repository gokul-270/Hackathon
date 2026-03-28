#!/bin/bash
# Quick System Status Check

echo "════════════════════════════════════════════════════════════════"
echo "🔍 Pragati System Status Check"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check processes
echo "✅ Running Processes:"
ps aux | grep -E "(dashboard|ros2)" | grep -v grep | awk '{print "   " $2, $11, $12, $13, $14}' | head -10
echo ""

# Check ROS2 nodes
echo "✅ ROS2 Nodes:"
source /opt/ros/jazzy/setup.bash 2>/dev/null
ros2 node list 2>/dev/null | while read node; do echo "   - $node"; done
echo ""

# Check dashboard
echo "✅ Dashboard Status:"
if curl -s http://localhost:8090/api/status > /dev/null 2>&1; then
    echo "   🟢 Dashboard is responding at http://localhost:8090"

    # Get node count
    NODE_COUNT=$(curl -s http://localhost:8090/api/nodes | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('data', {}).get('nodes', {})))" 2>/dev/null)
    echo "   📊 Monitoring $NODE_COUNT nodes"

    # Get topic count
    TOPIC_COUNT=$(curl -s http://localhost:8090/api/topics | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('data', {}).get('topics', {})))" 2>/dev/null)
    echo "   📡 Tracking $TOPIC_COUNT topics"
else
    echo "   🔴 Dashboard not responding"
fi
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📊 Quick Stats:"
echo "════════════════════════════════════════════════════════════════"

# System resources
echo "System CPU: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')"
echo "System Memory: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
echo ""

echo "📝 Logs available at:"
echo "   - Dashboard: /tmp/pragati_dashboard.log"
echo "   - Cotton Detection: /tmp/pragati_cotton_detection.log"
echo "   - Yanthra Move: /tmp/pragati_yanthra_move.log"
echo ""

echo "🌐 Dashboard: http://localhost:8090"
echo "════════════════════════════════════════════════════════════════"
