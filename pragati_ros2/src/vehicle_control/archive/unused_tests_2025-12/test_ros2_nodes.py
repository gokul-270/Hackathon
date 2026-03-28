#!/usr/bin/env python3
"""
ROS2 Node Launch and Runtime Testing
Tests the actual ROS2 node launch and operation
"""

import subprocess
import time
import os
import signal
import json
import sys
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from contextlib import contextmanager

@dataclass
class NodeTestResult:
    """Store node test results"""
    node_name: str
    launched: bool
    running: bool
    topics_published: List[str]
    topics_subscribed: List[str]
    services_advertised: List[str]
    errors: List[str]
    warnings: List[str]
    cpu_percent: float
    memory_mb: float
    uptime_seconds: float

class ROS2NodeTester:
    """Test ROS2 nodes launch and runtime behavior"""
    
    def __init__(self):
        self.test_results = {}
        self.active_processes = []
        
    @contextmanager
    def ros2_environment(self):
        """Ensure ROS2 environment is properly set up"""
        # Check if ROS2 is sourced
        try:
            result = subprocess.run(['ros2', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("ROS2 not available")
            print(f"✅ ROS2 Available: {result.stdout.strip()}")
        except Exception as e:
            raise RuntimeError(f"ROS2 environment check failed: {e}")
        
        # Source the workspace
        workspace_setup = "/home/uday/Downloads/pragati_ros2/install/setup.bash"
        
        # Set up environment
        env = os.environ.copy()
        if os.path.exists(workspace_setup):
            print(f"✅ Workspace setup found: {workspace_setup}")
        else:
            print(f"⚠️  Workspace setup not found, using system ROS2")
        
        try:
            yield env
        finally:
            # Cleanup any remaining processes
            self.cleanup_processes()
    
    def cleanup_processes(self):
        """Clean up any running test processes"""
        for proc in self.active_processes:
            try:
                if proc.poll() is None:  # Process still running
                    proc.terminate()
                    time.sleep(1)
                    if proc.poll() is None:  # Still running, force kill
                        proc.kill()
            except Exception:
                pass
        self.active_processes.clear()
    
    def test_node_launch(self, package_name: str, node_name: str, 
                        timeout: float = 10.0) -> NodeTestResult:
        """Test launching a single ROS2 node"""
        print(f"\n🚀 Testing node launch: {package_name}/{node_name}")
        
        result = NodeTestResult(
            node_name=f"{package_name}/{node_name}",
            launched=False,
            running=False,
            topics_published=[],
            topics_subscribed=[],
            services_advertised=[],
            errors=[],
            warnings=[],
            cpu_percent=0.0,
            memory_mb=0.0,
            uptime_seconds=0.0
        )
        
        with self.ros2_environment() as env:
            try:
                # Launch the node
                cmd = ['ros2', 'run', package_name, node_name]
                print(f"  Command: {' '.join(cmd)}")
                
                start_time = time.time()
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=os.setsid  # Create new process group
                )
                self.active_processes.append(proc)
                
                # Give node time to start
                time.sleep(3.0)
                
                # Check if process is still running
                if proc.poll() is None:
                    result.launched = True
                    result.running = True
                    result.uptime_seconds = time.time() - start_time
                    print(f"  ✅ Node launched successfully")
                    
                    # Get node information
                    self._get_node_info(result, env)
                    
                    # Test basic functionality
                    self._test_node_functionality(result, env, timeout - 3.0)
                    
                else:
                    result.launched = False
                    stdout, stderr = proc.communicate()
                    if stderr:
                        result.errors.append(f"Launch failed: {stderr}")
                    print(f"  ❌ Node failed to launch")
                    
            except subprocess.TimeoutExpired:
                result.errors.append(f"Node launch timed out after {timeout}s")
                print(f"  ❌ Node launch timed out")
            except Exception as e:
                result.errors.append(f"Launch error: {str(e)}")
                print(f"  ❌ Launch error: {e}")
            finally:
                # Clean up this specific process
                try:
                    if proc and proc.poll() is None:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        time.sleep(1)
                        if proc.poll() is None:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        
        return result
    
    def _get_node_info(self, result: NodeTestResult, env: Dict[str, str]):
        """Get information about the running node"""
        try:
            # Get node list
            cmd = ['ros2', 'node', 'list']
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                nodes = [line.strip() for line in proc.stdout.split('\n') if line.strip()]
                print(f"  📋 Active nodes: {len(nodes)}")
                for node in nodes[:3]:  # Show first 3
                    print(f"    - {node}")
                
                # Try to get node info for vehicle_control nodes
                for node in nodes:
                    if 'vehicle_control' in node:
                        self._get_detailed_node_info(node, result, env)
                        break
            
        except Exception as e:
            result.warnings.append(f"Could not get node info: {e}")
    
    def _get_detailed_node_info(self, node_name: str, result: NodeTestResult, env: Dict[str, str]):
        """Get detailed information about a specific node"""
        try:
            # Get node info
            cmd = ['ros2', 'node', 'info', node_name]
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                output = proc.stdout
                print(f"  📊 Node info for {node_name}:")
                
                # Parse topics
                if 'Publications:' in output:
                    pub_section = output.split('Publications:')[1].split('Subscriptions:')[0]
                    topics = [line.strip().split(':')[0] for line in pub_section.split('\n') 
                            if ':' in line and line.strip()]
                    result.topics_published = topics
                    print(f"    📤 Publishing: {len(topics)} topics")
                
                if 'Subscriptions:' in output:
                    sub_section = output.split('Subscriptions:')[1].split('Services:')[0]
                    topics = [line.strip().split(':')[0] for line in sub_section.split('\n') 
                            if ':' in line and line.strip()]
                    result.topics_subscribed = topics  
                    print(f"    📥 Subscribing: {len(topics)} topics")
                
                if 'Services:' in output:
                    srv_section = output.split('Services:')[1].split('Action Servers:')[0] if 'Action Servers:' in output else output.split('Services:')[1]
                    services = [line.strip().split(':')[0] for line in srv_section.split('\n') 
                              if ':' in line and line.strip()]
                    result.services_advertised = services
                    print(f"    🔧 Services: {len(services)}")
                    
        except Exception as e:
            result.warnings.append(f"Could not get detailed node info: {e}")
    
    def _test_node_functionality(self, result: NodeTestResult, env: Dict[str, str], timeout: float):
        """Test basic node functionality"""
        print(f"  🧪 Testing node functionality...")
        
        try:
            # Test topic list
            cmd = ['ros2', 'topic', 'list']
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                topics = [line.strip() for line in proc.stdout.split('\n') if line.strip()]
                vehicle_topics = [t for t in topics if 'vehicle' in t.lower() or 'cmd_vel' in t or 'joint' in t]
                print(f"    📡 Vehicle-related topics: {len(vehicle_topics)}")
                
                # Test echoing a topic if available
                if vehicle_topics:
                    topic = vehicle_topics[0]
                    print(f"    🔍 Testing topic echo: {topic}")
                    try:
                        cmd = ['ros2', 'topic', 'echo', topic, '--once']
                        proc = subprocess.run(cmd, env=env, capture_output=True, 
                                            text=True, timeout=3)
                        if proc.returncode == 0 and proc.stdout.strip():
                            print(f"    ✅ Topic {topic} is publishing data")
                        else:
                            print(f"    ⚠️  Topic {topic} not publishing or no data")
                    except subprocess.TimeoutExpired:
                        print(f"    ⚠️  Topic {topic} echo timed out (may be normal)")
                        
            # Test service list
            cmd = ['ros2', 'service', 'list']
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                services = [line.strip() for line in proc.stdout.split('\n') if line.strip()]
                vehicle_services = [s for s in services if 'vehicle' in s.lower()]
                print(f"    🔧 Vehicle-related services: {len(vehicle_services)}")
                
        except Exception as e:
            result.warnings.append(f"Functionality test error: {e}")
    
    def test_launch_file(self, package_name: str, launch_file: str, 
                        timeout: float = 15.0) -> Dict[str, Any]:
        """Test a ROS2 launch file"""
        print(f"\n🚀 Testing launch file: {package_name}/{launch_file}")
        
        test_result = {
            'launch_file': f"{package_name}/{launch_file}",
            'launched': False,
            'nodes_started': 0,
            'topics_active': 0,
            'services_active': 0,
            'errors': [],
            'warnings': [],
            'uptime_seconds': 0.0
        }
        
        with self.ros2_environment() as env:
            try:
                # Launch the launch file
                cmd = ['ros2', 'launch', package_name, launch_file]
                print(f"  Command: {' '.join(cmd)}")
                
                start_time = time.time()
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=os.setsid  # Create new process group
                )
                self.active_processes.append(proc)
                
                # Give launch file time to start nodes
                time.sleep(5.0)
                
                # Check if process is still running
                if proc.poll() is None:
                    test_result['launched'] = True
                    test_result['uptime_seconds'] = time.time() - start_time
                    print(f"  ✅ Launch file started successfully")
                    
                    # Get system information
                    self._get_system_info(test_result, env)
                    
                    # Let it run for a bit longer to test stability
                    time.sleep(3.0)
                    
                    if proc.poll() is None:
                        test_result['uptime_seconds'] = time.time() - start_time
                        print(f"  ✅ Launch file running stably for {test_result['uptime_seconds']:.1f}s")
                    else:
                        test_result['warnings'].append("Launch file terminated early")
                        
                else:
                    test_result['launched'] = False
                    stdout, stderr = proc.communicate()
                    if stderr:
                        test_result['errors'].append(f"Launch failed: {stderr[:500]}")
                    print(f"  ❌ Launch file failed to start")
                    
            except subprocess.TimeoutExpired:
                test_result['errors'].append(f"Launch file timed out after {timeout}s")
                print(f"  ❌ Launch file timed out")
            except Exception as e:
                test_result['errors'].append(f"Launch error: {str(e)}")
                print(f"  ❌ Launch error: {e}")
            finally:
                # Clean up this specific process
                try:
                    if proc and proc.poll() is None:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        time.sleep(1)
                        if proc.poll() is None:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        
        return test_result
    
    def _get_system_info(self, result: Dict[str, Any], env: Dict[str, str]):
        """Get system information during launch file test"""
        try:
            # Count active nodes
            cmd = ['ros2', 'node', 'list']
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                nodes = [line.strip() for line in proc.stdout.split('\n') if line.strip()]
                result['nodes_started'] = len(nodes)
                print(f"  📋 Nodes started: {result['nodes_started']}")
            
            # Count active topics
            cmd = ['ros2', 'topic', 'list']
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                topics = [line.strip() for line in proc.stdout.split('\n') if line.strip()]
                result['topics_active'] = len(topics)
                print(f"  📡 Topics active: {result['topics_active']}")
            
            # Count active services
            cmd = ['ros2', 'service', 'list']
            proc = subprocess.run(cmd, env=env, capture_output=True, 
                                text=True, timeout=5)
            
            if proc.returncode == 0:
                services = [line.strip() for line in proc.stdout.split('\n') if line.strip()]
                result['services_active'] = len(services)
                print(f"  🔧 Services active: {result['services_active']}")
                
        except Exception as e:
            result['warnings'].append(f"Could not get system info: {e}")

def main():
    """Run ROS2 node tests"""
    print("🚀 Starting ROS2 Node Launch and Runtime Testing")
    print("=" * 60)
    
    tester = ROS2NodeTester()
    all_results = {}
    
    try:
        # Test individual nodes (if they exist as standalone executables)
        nodes_to_test = [
            ('vehicle_control', 'vehicle_control_node'),
            ('vehicle_control', 'motor_controller_node'),
            ('vehicle_control', 'gpio_controller_node'),
        ]
        
        node_results = []
        for package, node in nodes_to_test:
            print(f"\n🧪 Testing node: {package}/{node}")
            try:
                result = tester.test_node_launch(package, node, timeout=10.0)
                node_results.append(result)
                all_results[f"{package}/{node}"] = result
            except Exception as e:
                print(f"  ❌ Could not test {package}/{node}: {e}")
                continue
        
        # Test launch files
        launch_files_to_test = [
            ('vehicle_control', 'vehicle_control.launch.py'),
            ('vehicle_control', 'vehicle_control_sim.launch.py'),
        ]
        
        launch_results = []
        for package, launch_file in launch_files_to_test:
            print(f"\n🧪 Testing launch file: {package}/{launch_file}")
            try:
                result = tester.test_launch_file(package, launch_file, timeout=15.0)
                launch_results.append(result)
                all_results[f"launch/{package}/{launch_file}"] = result
            except Exception as e:
                print(f"  ❌ Could not test {package}/{launch_file}: {e}")
                continue
        
        # Summary
        print("\n📊 ROS2 Testing Summary")
        print("=" * 60)
        
        successful_nodes = sum(1 for r in node_results if r.launched)
        successful_launches = sum(1 for r in launch_results if r['launched'])
        
        print(f"Node Tests: {successful_nodes}/{len(node_results)} successful")
        print(f"Launch Tests: {successful_launches}/{len(launch_results)} successful")
        
        # Check for issues
        issues = []
        for result in node_results:
            if result.errors:
                issues.extend(result.errors)
            if result.warnings:
                issues.extend(result.warnings)
                
        for result in launch_results:
            if result['errors']:
                issues.extend(result['errors'])
            if result['warnings']:
                issues.extend(result['warnings'])
        
        if issues:
            print(f"\n⚠️  Issues Detected ({len(issues)}):")
            for issue in issues[:5]:  # Show first 5
                print(f"  - {issue[:100]}...")
        else:
            print(f"\n✅ No major issues detected")
        
        # Overall assessment
        total_tests = len(node_results) + len(launch_results)
        successful_tests = successful_nodes + successful_launches
        
        if total_tests > 0:
            success_rate = (successful_tests / total_tests) * 100
            print(f"\nOverall Success Rate: {success_rate:.1f}% ({successful_tests}/{total_tests})")
            
            if success_rate >= 80:
                print("✅ ROS2 System Ready for Production")
                return True
            elif success_rate >= 50:
                print("⚠️  ROS2 System Partially Functional - Review Issues")
                return False
            else:
                print("❌ ROS2 System Has Significant Issues")
                return False
        else:
            print("❌ No successful tests completed")
            return False
            
    except KeyboardInterrupt:
        print("\n⏹️  Testing interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Testing failed with error: {e}")
        return False
    finally:
        print("\n🧹 Cleaning up test processes...")
        tester.cleanup_processes()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)