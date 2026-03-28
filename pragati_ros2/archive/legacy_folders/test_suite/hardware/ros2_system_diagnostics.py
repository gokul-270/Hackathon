#!/usr/bin/env python3

"""
ROS2 System Diagnostics Tool
=============================

This script provides comprehensive diagnostics for ROS2 systems, specifically
designed to debug issues like:
- Missing joint state publishers (/jointN/state topics)
- Hanging nodes during startup
- Orphaned topic/service detection
- Node liveness verification

Usage:
    python3 ros2_system_diagnostics.py
"""

import subprocess
import time
import json
import re
import signal
import sys
from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class NodeInfo:
    name: str
    alive: bool = False
    topics_published: List[str] = None
    topics_subscribed: List[str] = None
    services_provided: List[str] = None
    
    def __post_init__(self):
        if self.topics_published is None:
            self.topics_published = []
        if self.topics_subscribed is None:
            self.topics_subscribed = []
        if self.services_provided is None:
            self.services_provided = []

class ROS2Diagnostics:
    def __init__(self):
        self.nodes: Dict[str, NodeInfo] = {}
        self.topics: Set[str] = set()
        self.services: Set[str] = set()
        self.expected_joint_topics = [f"/joint{i}/state" for i in range(2, 6)]  # joint2 through joint5
        
    def run_ros2_command(self, args: List[str], timeout: int = 10) -> Optional[List[str]]:
        """Run a ros2 command and return output lines."""
        try:
            result = subprocess.run(
                ["ros2"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"⚠️  Command 'ros2 {' '.join(args)}' failed: {e}")
            return None

    def check_ros2_environment(self) -> bool:
        """Verify ROS2 environment is properly set up."""
        print("🔍 Checking ROS2 Environment...")
        
        # Check ROS_DISTRO
        distro = subprocess.run(["printenv", "ROS_DISTRO"], capture_output=True, text=True)
        if distro.returncode != 0 or not distro.stdout.strip():
            print("❌ ROS_DISTRO not set. Please source ROS2 setup.bash")
            return False
        
        print(f"✅ ROS_DISTRO: {distro.stdout.strip()}")
        
        # Test basic ros2 command
        if self.run_ros2_command(["--help"]) is None:
            print("❌ ros2 command not available")
            return False
            
        print("✅ ros2 command available")
        return True

    def discover_system_state(self):
        """Discover current ROS2 system state."""
        print("\n🔍 Discovering ROS2 System State...")
        
        # Get all nodes
        node_lines = self.run_ros2_command(["node", "list"])
        if node_lines:
            for node_name in node_lines:
                self.nodes[node_name] = NodeInfo(name=node_name, alive=True)
            print(f"📊 Found {len(self.nodes)} active nodes")
        
        # Get all topics
        topic_lines = self.run_ros2_command(["topic", "list"])
        if topic_lines:
            self.topics = set(topic_lines)
            print(f"📊 Found {len(self.topics)} active topics")
        
        # Get all services
        service_lines = self.run_ros2_command(["service", "list"])
        if service_lines:
            self.services = set(service_lines)
            print(f"📊 Found {len(self.services)} active services")

    def analyze_node_details(self):
        """Get detailed information about each node."""
        print("\n🔍 Analyzing Node Details...")
        
        for node_name in self.nodes.keys():
            print(f"  📋 Analyzing {node_name}...")
            
            # Get node info
            info_output = self.run_ros2_command(["node", "info", node_name])
            if info_output:
                current_section = None
                for line in info_output:
                    if "Publications:" in line:
                        current_section = "publications"
                    elif "Subscriptions:" in line:
                        current_section = "subscriptions"
                    elif "Services:" in line:
                        current_section = "services"
                    elif line.startswith("  ") and current_section:
                        topic_or_service = line.strip().split(":")[0].strip()
                        if current_section == "publications":
                            self.nodes[node_name].topics_published.append(topic_or_service)
                        elif current_section == "subscriptions":
                            self.nodes[node_name].topics_subscribed.append(topic_or_service)
                        elif current_section == "services":
                            self.nodes[node_name].services_provided.append(topic_or_service)

    def check_joint_state_publishers(self):
        """Check for missing individual joint state publishers."""
        print("\n🔍 Checking Individual Joint State Publishers...")
        
        missing_topics = []
        for expected_topic in self.expected_joint_topics:
            if expected_topic not in self.topics:
                missing_topics.append(expected_topic)
        
        if missing_topics:
            print(f"❌ Missing joint state topics: {missing_topics}")
            print("💡 This suggests joint_state_publishers_[i] are not initialized in hardware interface")
            self.suggest_joint_publisher_fix()
        else:
            print("✅ All expected joint state topics are present")

    def suggest_joint_publisher_fix(self):
        """Suggest fixes for missing joint state publishers."""
        print("\n🔧 Suggested Fix for Missing Joint State Publishers:")
        print("="*60)
        print("The individual joint state publishers are likely not initialized.")
        print("Add this code to your hardware interface constructor or init method:")
        print()
        print("```cpp")
        print("// Initialize individual joint state publishers")
        print("joint_state_publishers_.resize(num_joints_);")
        print("for (size_t i = 0; i < num_joints_; ++i) {")
        print("    std::string topic_name = \"/joint\" + std::to_string(i + 2) + \"/state\";")
        print("    joint_state_publishers_[i] = node_->create_publisher<std_msgs::msg::Float64>(topic_name, 10);")
        print("}")
        print("```")
        print()

    def check_for_hanging_nodes(self):
        """Check for nodes that might be hanging during startup."""
        print("\n🔍 Checking for Hanging Nodes...")
        
        # Check if expected nodes are running
        expected_nodes = ["/odrive_service_node", "/odrive_hardware_interface"]
        
        missing_nodes = []
        for expected_node in expected_nodes:
            if expected_node not in self.nodes:
                missing_nodes.append(expected_node)
        
        if missing_nodes:
            print(f"⚠️  Expected nodes not running: {missing_nodes}")
            print("💡 These nodes might be hanging during startup")
            self.suggest_hanging_node_debug()
        else:
            print("✅ All expected nodes are running")

    def suggest_hanging_node_debug(self):
        """Suggest debugging steps for hanging nodes."""
        print("\n🔧 Debugging Hanging Nodes:")
        print("="*40)
        print("1. Check CAN hardware initialization - this often causes hangs")
        print("2. Add timeout checks to hardware setup")
        print("3. Use LazyROS to monitor node startup in real-time")
        print("4. Check for blocking I/O operations in constructors")
        print("5. Add detailed logging to identify where the hang occurs")

    def generate_report(self):
        """Generate a comprehensive diagnostic report."""
        print("\n" + "="*60)
        print("🔍 ROS2 SYSTEM DIAGNOSTIC REPORT")
        print("="*60)
        print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 Total Nodes: {len(self.nodes)}")
        print(f"📊 Total Topics: {len(self.topics)}")
        print(f"📊 Total Services: {len(self.services)}")
        
        print("\n📋 ACTIVE NODES:")
        for node_name, node_info in self.nodes.items():
            print(f"  ✅ {node_name}")
            if node_info.topics_published:
                print(f"    📤 Publishes: {node_info.topics_published[:3]}{'...' if len(node_info.topics_published) > 3 else ''}")
            if node_info.topics_subscribed:
                print(f"    📥 Subscribes: {node_info.topics_subscribed[:3]}{'...' if len(node_info.topics_subscribed) > 3 else ''}")
        
        print("\n📋 TOPIC ANALYSIS:")
        joint_topics = [t for t in self.topics if '/joint' in t and '/state' in t]
        if joint_topics:
            print(f"  ✅ Joint state topics found: {joint_topics}")
        else:
            print("  ❌ No individual joint state topics found")
        
        print("\n💡 RECOMMENDATIONS:")
        missing_joint_topics = [t for t in self.expected_joint_topics if t not in self.topics]
        if missing_joint_topics:
            print(f"  🔧 Initialize publishers for: {missing_joint_topics}")
        
        expected_nodes = ["/odrive_service_node", "/odrive_hardware_interface"]
        missing_nodes = [n for n in expected_nodes if n not in self.nodes]
        if missing_nodes:
            print(f"  🔧 Debug startup hangs for: {missing_nodes}")
        
        if not missing_joint_topics and not missing_nodes:
            print("  ✅ System appears to be functioning correctly!")

def signal_handler(signum, frame):
    print("\n\n👋 Diagnostic interrupted by user")
    sys.exit(0)

def main():
    """Main diagnostic routine."""
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 ROS2 System Diagnostics")
    print("=" * 30)
    
    diagnostics = ROS2Diagnostics()
    
    # Check ROS2 environment
    if not diagnostics.check_ros2_environment():
        return 1
    
    # Discover system state
    diagnostics.discover_system_state()
    
    # Analyze node details
    diagnostics.analyze_node_details()
    
    # Run specific checks
    diagnostics.check_joint_state_publishers()
    diagnostics.check_for_hanging_nodes()
    
    # Generate final report
    diagnostics.generate_report()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())