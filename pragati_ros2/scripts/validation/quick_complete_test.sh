#!/bin/bash

################################################################################
# Quick Complete System Test
# Simple test for pragati_complete.launch.py with start_switch_publisher
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Quick Complete System Test                     ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

REMOTE="ubuntu@192.168.137.253"

# Cleanup
echo -e "${YELLOW}🧹 Cleaning up...${NC}"
ssh $REMOTE 'pkill -9 -f "start_switch_publisher|ros2 launch" 2>/dev/null; exit 0'
sleep 2

# Create remote launch script
echo -e "${CYAN}📝 Creating launch script on Pi...${NC}"
ssh $REMOTE 'cat > /tmp/launch_test.sh << "EOFSCRIPT"
#!/bin/bash
cd ~/pragati_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Start start_switch_publisher
python3 web_dashboard/start_switch_publisher.py > /tmp/start_switch.log 2>&1 &
sleep 2

# Launch complete system
ros2 launch yanthra_move pragati_complete.launch.py enable_arm_client:=false > /tmp/complete_launch.log 2>&1 &
EOFSCRIPT
chmod +x /tmp/launch_test.sh
'

# Launch on Pi
echo -e "${CYAN}🚀 Launching system on Pi...${NC}"
ssh $REMOTE 'bash /tmp/launch_test.sh'

echo -e "${YELLOW}⏳ Waiting 15 seconds...${NC}"
sleep 15

# Check status
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  System Status${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${CYAN}📊 Nodes:${NC}"
ssh $REMOTE 'source /opt/ros/jazzy/setup.bash && ros2 node list 2>/dev/null' | while read node; do
    echo -e "${GREEN}   • $node${NC}"
done

echo ""
echo -e "${CYAN}📡 Topic count:${NC}"
TOPICS=$(ssh $REMOTE 'source /opt/ros/jazzy/setup.bash && ros2 topic list 2>/dev/null | wc -l')
echo -e "${GREEN}   • $TOPICS topics${NC}"

echo ""
echo -e "${CYAN}🔧 Motor services:${NC}"
ssh $REMOTE 'source /opt/ros/jazzy/setup.bash && ros2 service list 2>/dev/null | grep -E "(joint|motor)" | head -5' | while read svc; do
    echo -e "${GREEN}   • $svc${NC}"
done

echo ""
echo -e "${CYAN}🔘 Start switch:${NC}"
START_VAL=$(ssh $REMOTE 'source /opt/ros/jazzy/setup.bash && timeout 2s ros2 topic echo /start_switch/state --once 2>/dev/null | grep "data:" | head -1')
if [ -n "$START_VAL" ]; then
    echo -e "${GREEN}   ✅ $START_VAL${NC}"
else
    echo -e "${YELLOW}   ⚠️  Not detected${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Test complete!${NC}"
echo ""
echo -e "${CYAN}💡 System is running on Pi${NC}"
echo -e "${CYAN}📋 Logs: /tmp/complete_launch.log, /tmp/start_switch.log${NC}"
echo ""
echo -e "${YELLOW}🧹 To cleanup: ssh $REMOTE 'pkill -9 -f \"ros2|python3\"'${NC}"
echo ""
