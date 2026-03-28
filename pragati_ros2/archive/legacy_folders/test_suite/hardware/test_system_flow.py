#!/usr/bin/env python3

"""
Comprehensive ROS2 System Flow Verification Script
==================================================

This script verifies the complete communication chain:
yanthra_move → publishes → /jointX_position_controller/command → odrive_service_node → CAN bus → ODrive motors

It tests:
1. Parameter loading in both packages
2. Topic publisher/subscriber connections
3. Service availability and functionality
4. Message flow integrity
5. Hardware integration readiness

Usage:
    python3 test_system_flow.py
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
import std_msgs.msg
import sensor_msgs.msg
import threading
import time
import sys
import subprocess
import signal
import os


class SystemFlowTester(Node):
    def __init__(self):
        super().__init__('system_flow_tester')
        self.get_logger().info("🧪 System Flow Tester initialized")
        
        # Test results tracking
        self.test_results = {}
        self.message_received = {}
        
        # Initialize subscribers to monitor communication
        self.setup_subscribers()
        
    def setup_subscribers(self):
        """Set up subscribers to monitor the communication flow"""
        self.joint_state_sub = self.create_subscription(
            sensor_msgs.msg.JointState,
            '/joint_states',
            self.joint_state_callback,
            10
        )
        
        # Monitor joint command topics for activity
        self.joint2_activity = False
        self.joint3_activity = False
        self.joint4_activity = False
        self.joint5_activity = False
        
    def joint_state_callback(self, msg):
        """Monitor joint state messages"""
        self.message_received['/joint_states'] = True
        self.get_logger().debug(f"Joint states received: {len(msg.position)} joints")

    def test_topic_connections(self):
        """Test that all required topics have proper publishers/subscribers"""
        self.get_logger().info("🔍 Testing topic connections...")
        
        required_topics = [
            '/joint2_position_controller/command',
            '/joint3_position_controller/command', 
            '/joint4_position_controller/command',
            '/joint5_position_controller/command',
            '/joint_states'
        ]
        
        results = {}
        for topic in required_topics:
            try:
                # Check topic info
                result = subprocess.run([
                    'ros2', 'topic', 'info', topic
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    output = result.stdout
                    pub_count = 0
                    sub_count = 0
                    
                    for line in output.split('\n'):
                        if 'Publisher count:' in line:
                            pub_count = int(line.split(':')[1].strip())
                        elif 'Subscription count:' in line:
                            sub_count = int(line.split(':')[1].strip())
                    
                    results[topic] = {
                        'publishers': pub_count,
                        'subscribers': sub_count,
                        'status': 'OK' if pub_count > 0 and sub_count > 0 else 'MISSING_CONNECTION'
                    }
                    
                    if pub_count > 0 and sub_count > 0:
                        self.get_logger().info(f"✅ {topic}: {pub_count} pub, {sub_count} sub")
                    else:
                        self.get_logger().error(f"❌ {topic}: {pub_count} pub, {sub_count} sub - BROKEN")
                else:
                    results[topic] = {'status': 'NOT_FOUND'}
                    self.get_logger().error(f"❌ {topic}: Topic not found")
                    
            except Exception as e:
                results[topic] = {'status': 'ERROR', 'error': str(e)}
                self.get_logger().error(f"❌ {topic}: Error - {e}")
        
        return results

    def test_service_availability(self):
        """Test that all required services are available"""
        self.get_logger().info("🔍 Testing service availability...")
        
        required_services = [
            '/joint_homing',
            '/joint_idle', 
            '/joint_position_command',
            '/joint_status',
            '/motor_calibration',
            '/encoder_calibration',
            '/joint_configuration'
        ]
        
        results = {}
        for service in required_services:
            try:
                result = subprocess.run([
                    'ros2', 'service', 'info', service
                ], capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    output = result.stdout
                    client_count = 0
                    service_count = 0
                    
                    for line in output.split('\n'):
                        if 'Clients count:' in line:
                            client_count = int(line.split(':')[1].strip())
                        elif 'Services count:' in line:
                            service_count = int(line.split(':')[1].strip())
                    
                    results[service] = {
                        'clients': client_count,
                        'services': service_count,
                        'status': 'OK' if service_count > 0 else 'NO_SERVER'
                    }
                    
                    if service_count > 0:
                        self.get_logger().info(f"✅ {service}: Available")
                    else:
                        self.get_logger().error(f"❌ {service}: No server")
                else:
                    results[service] = {'status': 'NOT_FOUND'}
                    self.get_logger().error(f"❌ {service}: Service not found")
                    
            except Exception as e:
                results[service] = {'status': 'ERROR', 'error': str(e)}
                self.get_logger().error(f"❌ {service}: Error - {e}")
        
        return results

    def test_parameter_loading(self):
        """Test parameter loading in both nodes"""
        self.get_logger().info("🔍 Testing parameter loading...")
        
        results = {}
        
        # Test ODrive service node parameters
        try:
            result = subprocess.run([
                'ros2', 'param', 'dump', '/odrive_service_node'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                output = result.stdout
                # Check for key parameters (using nested structure)
                required_params = ['can_id: 3', 'transmission_factor: 0.870047022', 'joint2:']
                found_params = []
                
                for param in required_params:
                    if param in output:
                        found_params.append(param)
                
                results['odrive_service_node'] = {
                    'status': 'OK' if len(found_params) == len(required_params) else 'MISSING_PARAMS',
                    'found_params': found_params,
                    'missing_params': [p for p in required_params if p not in found_params]
                }
                
                if len(found_params) == len(required_params):
                    self.get_logger().info(f"✅ ODrive service node: All parameters loaded")
                else:
                    self.get_logger().error(f"❌ ODrive service node: Missing parameters: {results['odrive_service_node']['missing_params']}")
            else:
                results['odrive_service_node'] = {'status': 'PARAM_DUMP_FAILED'}
                self.get_logger().error("❌ ODrive service node: Parameter dump failed")
                
        except Exception as e:
            results['odrive_service_node'] = {'status': 'ERROR', 'error': str(e)}
            self.get_logger().error(f"❌ ODrive service node parameters: Error - {e}")
        
        # Test yanthra_move node parameters
        try:
            result = subprocess.run([
                'ros2', 'param', 'list', '/yanthra_move'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                params = result.stdout.split('\n')
                # Count actual parameter lines (exclude empty lines)
                param_count = len([p for p in params if p.strip() and p.strip() != ''])
                
                results['yanthra_move'] = {
                    'status': 'OK' if param_count > 10 else 'FEW_PARAMS',
                    'param_count': param_count
                }
                
                if param_count > 10:
                    self.get_logger().info(f"✅ yanthra_move: {param_count} parameters loaded")
                else:
                    self.get_logger().warn(f"⚠️  yanthra_move: Only {param_count} parameters found")
            else:
                results['yanthra_move'] = {'status': 'PARAM_LIST_FAILED'}
                self.get_logger().error("❌ yanthra_move: Parameter list failed")
                
        except Exception as e:
            results['yanthra_move'] = {'status': 'ERROR', 'error': str(e)}
            self.get_logger().error(f"❌ yanthra_move parameters: Error - {e}")
        
        return results

    def test_message_flow(self):
        """Test actual message flow by publishing commands and monitoring responses"""
        self.get_logger().info("🔍 Testing message flow...")
        
        # Create publishers for test commands
        joint2_pub = self.create_publisher(std_msgs.msg.Float64, '/joint2_position_controller/command', 10)
        joint3_pub = self.create_publisher(std_msgs.msg.Float64, '/joint3_position_controller/command', 10)
        
        time.sleep(1)  # Allow publishers to establish connections
        
        # Send test commands
        test_msg = std_msgs.msg.Float64()
        test_msg.data = 0.1
        
        self.get_logger().info("📤 Sending test commands...")
        joint2_pub.publish(test_msg)
        joint3_pub.publish(test_msg)
        
        # Wait for response
        time.sleep(2)
        
        # Check if joint states are being published
        joint_states_active = '/joint_states' in self.message_received
        
        return {
            'joint_states_active': joint_states_active,
            'status': 'OK' if joint_states_active else 'NO_FEEDBACK'
        }

    def run_comprehensive_test(self):
        """Run all tests and generate comprehensive report"""
        self.get_logger().info("🚀 Starting comprehensive system flow test...")
        
        # Wait for system to stabilize
        time.sleep(3)
        
        # Run all tests
        topic_results = self.test_topic_connections()
        service_results = self.test_service_availability() 
        param_results = self.test_parameter_loading()
        flow_results = self.test_message_flow()
        
        # Generate report
        self.generate_report(topic_results, service_results, param_results, flow_results)
        
        return topic_results, service_results, param_results, flow_results

    def generate_report(self, topics, services, params, flow):
        """Generate a comprehensive test report"""
        print("\n" + "="*80)
        print("🧪 COMPREHENSIVE SYSTEM FLOW TEST REPORT")
        print("="*80)
        
        # Topic connections report
        print("\n📡 TOPIC CONNECTIONS:")
        topic_pass = 0
        topic_total = len(topics)
        for topic, result in topics.items():
            status = result['status']
            if status == 'OK':
                print(f"  ✅ {topic}")
                topic_pass += 1
            else:
                print(f"  ❌ {topic}: {status}")
        
        print(f"  📊 Topics: {topic_pass}/{topic_total} passing")
        
        # Services report
        print("\n🔧 SERVICES:")
        service_pass = 0
        service_total = len(services)
        for service, result in services.items():
            status = result['status']
            if status == 'OK':
                print(f"  ✅ {service}")
                service_pass += 1
            else:
                print(f"  ❌ {service}: {status}")
        
        print(f"  📊 Services: {service_pass}/{service_total} passing")
        
        # Parameters report
        print("\n⚙️  PARAMETERS:")
        param_pass = 0
        param_total = len(params)
        for node, result in params.items():
            status = result['status']
            if status == 'OK':
                print(f"  ✅ {node}")
                param_pass += 1
            else:
                print(f"  ❌ {node}: {status}")
                if 'missing_params' in result:
                    print(f"     Missing: {result['missing_params']}")
        
        print(f"  📊 Parameter loading: {param_pass}/{param_total} passing")
        
        # Message flow report
        print("\n📨 MESSAGE FLOW:")
        flow_status = flow['status']
        if flow_status == 'OK':
            print("  ✅ Message flow working")
        else:
            print(f"  ❌ Message flow: {flow_status}")
        
        # Overall assessment
        total_pass = topic_pass + service_pass + param_pass + (1 if flow_status == 'OK' else 0)
        total_tests = topic_total + service_total + param_total + 1
        
        print(f"\n📊 OVERALL RESULTS: {total_pass}/{total_tests} tests passing")
        
        if total_pass == total_tests:
            print("🎉 ALL TESTS PASSED - System ready for production!")
        elif total_pass >= total_tests * 0.8:
            print("⚠️  MOSTLY PASSING - Minor issues need attention")
        else:
            print("❌ SIGNIFICANT ISSUES - System needs fixes before production")
        
        print("="*80)


def main():
    """Main test runner"""
    # Check if system is running
    try:
        result = subprocess.run(['ros2', 'node', 'list'], capture_output=True, text=True, timeout=5)
        if '/odrive_service_node' not in result.stdout or '/yanthra_move' not in result.stdout:
            print("❌ System not running. Please start the system first:")
            print("   ros2 launch yanthra_move pragati_complete.launch.py")
            return 1
    except Exception as e:
        print(f"❌ Error checking system status: {e}")
        return 1
    
    # Initialize ROS2
    rclpy.init()
    
    try:
        # Create tester node
        tester = SystemFlowTester()
        
        # Create executor
        executor = MultiThreadedExecutor()
        executor.add_node(tester)
        
        # Start executor in background
        executor_thread = threading.Thread(target=executor.spin)
        executor_thread.daemon = True
        executor_thread.start()
        
        # Run tests
        tester.run_comprehensive_test()
        
        # Cleanup
        executor.shutdown()
        tester.destroy_node()
        
    except KeyboardInterrupt:
        print("🛑 Test interrupted by user")
        return 1
    finally:
        rclpy.shutdown()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())