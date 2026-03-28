#!/usr/bin/env python3
"""
Performance and Memory Profiling for Vehicle Control System
Tests memory usage, CPU utilization, and performance characteristics
"""

import sys
import os
import time
import psutil
import tracemalloc
import threading
import gc
import traceback
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import json

# Add the src directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import all our components
try:
    from utils.circuit_breaker import CircuitBreaker
    from hardware.enhanced_motor_interface import EnhancedMockMotorInterface
    from utils.configuration_manager import ConfigurationManager
    from hardware.robust_motor_controller import RobustMotorController
    from config.constants import *
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

@dataclass
class PerformanceMetrics:
    """Store performance metrics"""
    memory_peak_mb: float
    memory_current_mb: float
    cpu_percent: float
    execution_time_ms: float
    operations_per_second: float
    memory_growth_mb: float

class PerformanceProfiler:
    """Profile memory usage and performance"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.baseline_memory = 0
        
    def start_profiling(self):
        """Start memory and performance tracking"""
        tracemalloc.start()
        gc.collect()  # Clean up before starting
        self.baseline_memory = self.process.memory_info().rss / 1024 / 1024
        return time.perf_counter()
    
    def stop_profiling(self, start_time: float) -> PerformanceMetrics:
        """Stop profiling and return metrics"""
        end_time = time.perf_counter()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        current_memory = self.process.memory_info().rss / 1024 / 1024
        cpu_percent = self.process.cpu_percent()
        
        execution_time_ms = (end_time - start_time) * 1000
        memory_growth = current_memory - self.baseline_memory
        
        return PerformanceMetrics(
            memory_peak_mb=peak / 1024 / 1024,
            memory_current_mb=current / 1024 / 1024,
            cpu_percent=cpu_percent,
            execution_time_ms=execution_time_ms,
            operations_per_second=1000.0 / execution_time_ms if execution_time_ms > 0 else 0,
            memory_growth_mb=memory_growth
        )

def test_circuit_breaker_performance():
    """Test circuit breaker performance under load"""
    print("\n🔧 Testing Circuit Breaker Performance...")
    profiler = PerformanceProfiler()
    
    start_time = profiler.start_profiling()
    
    # Create circuit breaker
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    
    # Test multiple operations
    operations = 1000
    successful_ops = 0
    failed_ops = 0
    
    def test_operation(should_fail=False):
        if should_fail:
            raise ValueError("Test failure")
        return "success"
    
    # Create a protected version of test_operation
    @cb
    def protected_operation(should_fail=False):
        return test_operation(should_fail)
    
    # Run performance test
    for i in range(operations):
        try:
            # Mix of successful and failing operations
            should_fail = (i % 10 == 0)  # 10% failure rate
            result = protected_operation(should_fail)
            if result == "success":
                successful_ops += 1
        except Exception:
            failed_ops += 1
    
    metrics = profiler.stop_profiling(start_time)
    
    print(f"  Operations: {operations}, Success: {successful_ops}, Failed: {failed_ops}")
    print(f"  Execution time: {metrics.execution_time_ms:.2f} ms")
    print(f"  Operations/sec: {operations / (metrics.execution_time_ms / 1000):.1f}")
    print(f"  Memory peak: {metrics.memory_peak_mb:.2f} MB")
    print(f"  Memory growth: {metrics.memory_growth_mb:.2f} MB")
    
    return metrics

def test_enhanced_motor_performance():
    """Test enhanced motor interface performance"""
    print("\n🔧 Testing Enhanced Motor Interface Performance...")
    profiler = PerformanceProfiler()
    
    start_time = profiler.start_profiling()
    
    # Create motor interface
    motor = EnhancedMockMotorInterface()
    motor.initialize()  # Initialize the mock interface
    
    # Test multiple motor operations
    operations = 500
    
    for i in range(operations):
        # Vary motor commands
        speed = (i % 100) / 100.0  # 0.0 to 0.99
        direction = 1 if (i % 2 == 0) else -1
        
        # Use the correct method names for this interface
        motor.set_velocity(0, speed * direction)  # Use motor_id 0
        motor.get_status(0)  # Get status for motor 0
        
        # Simulate some failures
        if i % 50 == 0:
            try:
                motor.set_velocity(0, 20.0)  # Very high speed
            except Exception:
                pass
    
    metrics = profiler.stop_profiling(start_time)
    
    print(f"  Operations: {operations}")
    print(f"  Execution time: {metrics.execution_time_ms:.2f} ms")
    print(f"  Operations/sec: {operations / (metrics.execution_time_ms / 1000):.1f}")
    print(f"  Memory peak: {metrics.memory_peak_mb:.2f} MB")
    print(f"  Memory growth: {metrics.memory_growth_mb:.2f} MB")
    
    return metrics

def test_config_manager_performance():
    """Test configuration manager performance"""
    print("\n🔧 Testing Configuration Manager Performance...")
    profiler = PerformanceProfiler()
    
    start_time = profiler.start_profiling()
    
    # Create config manager
    config_mgr = ConfigurationManager()
    
    # Test configuration operations
    operations = 100
    
    for i in range(operations):
        # Get default config
        default_config = config_mgr.get_default_configuration()
        
        # Update some values (only update top-level parameters to avoid schema validation issues)
        config_mgr.set_parameter('control_frequency', 50.0 + (i % 10) * 10.0)
        config_mgr.set_parameter('cmd_vel_timeout', 0.5 + (i % 3) * 0.2)
        
        # Validate config
        try:
            config_mgr.validate_configuration(default_config)
        except Exception:
            pass
        
        # Get config values
        config_mgr.get_parameter('control_frequency')
        config_mgr.get_parameter('cmd_vel_timeout')
    
    metrics = profiler.stop_profiling(start_time)
    
    print(f"  Operations: {operations}")
    print(f"  Execution time: {metrics.execution_time_ms:.2f} ms")
    print(f"  Operations/sec: {operations / (metrics.execution_time_ms / 1000):.1f}")
    print(f"  Memory peak: {metrics.memory_peak_mb:.2f} MB")
    print(f"  Memory growth: {metrics.memory_growth_mb:.2f} MB")
    
    return metrics

def test_robust_controller_performance():
    """Test robust motor controller performance"""
    print("\n🔧 Testing Robust Motor Controller Performance...")
    profiler = PerformanceProfiler()
    
    start_time = profiler.start_profiling()
    
    # Create robust controller with motor interface
    motor_interface = EnhancedMockMotorInterface()
    motor_interface.initialize()
    controller = RobustMotorController(motor_interface)
    
    # Test controller operations
    operations = 200
    
    for i in range(operations):
        # Test various motor commands
        speed = (i % 200 - 100) / 100.0  # -1.0 to 0.99
        
        try:
            controller.set_motor_speed(speed)
            controller.get_diagnostics()
            
            # Simulate some edge cases
            if i % 25 == 0:
                controller.emergency_stop()
                time.sleep(0.001)  # Brief pause
                
        except Exception as e:
            # Expected for some edge cases
            pass
    
    metrics = profiler.stop_profiling(start_time)
    
    print(f"  Operations: {operations}")
    print(f"  Execution time: {metrics.execution_time_ms:.2f} ms")
    print(f"  Operations/sec: {operations / (metrics.execution_time_ms / 1000):.1f}")
    print(f"  Memory peak: {metrics.memory_peak_mb:.2f} MB")
    print(f"  Memory growth: {metrics.memory_growth_mb:.2f} MB")
    
    return metrics

def test_memory_leak_detection():
    """Test for memory leaks over extended operation"""
    print("\n🔍 Testing for Memory Leaks...")
    
    initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
    memory_samples = []
    
    # Run extended test cycles
    cycles = 10
    for cycle in range(cycles):
        print(f"  Cycle {cycle + 1}/{cycles}")
        
        # Create and destroy components multiple times
        for _ in range(20):
            # Create components
            cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
            motor = EnhancedMockMotorInterface()
            motor.initialize()  # Initialize the mock interface
            config_mgr = ConfigurationManager()
            controller_motor = EnhancedMockMotorInterface()
            controller_motor.initialize()
            controller = RobustMotorController(controller_motor)
            
            # Use components briefly
            try:
                @cb
                def test_func():
                    return "test"
                test_func()
                motor.set_velocity(0, 0.5)
                config_mgr.get_parameter('control_frequency')
                controller.get_diagnostics()
            except:
                pass
            
            # Delete references
            del cb, motor, config_mgr, controller_motor, controller
        
        # Force garbage collection
        gc.collect()
        
        # Sample memory
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_samples.append(current_memory)
        
        time.sleep(0.1)  # Brief pause between cycles
    
    # Analyze memory growth
    memory_growth = memory_samples[-1] - memory_samples[0]
    max_memory = max(memory_samples)
    avg_memory = sum(memory_samples) / len(memory_samples)
    
    print(f"  Initial memory: {initial_memory:.2f} MB")
    print(f"  Final memory: {memory_samples[-1]:.2f} MB")
    print(f"  Memory growth: {memory_growth:.2f} MB")
    print(f"  Max memory: {max_memory:.2f} MB")
    print(f"  Avg memory: {avg_memory:.2f} MB")
    
    # Check for significant memory leaks
    if memory_growth > 5.0:  # More than 5MB growth
        print(f"  ⚠️  Potential memory leak detected: {memory_growth:.2f} MB growth")
        return False
    else:
        print(f"  ✅ No significant memory leaks detected")
        return True

def run_stress_test():
    """Run stress test with concurrent operations"""
    print("\n💪 Running Concurrent Stress Test...")
    
    profiler = PerformanceProfiler()
    start_time = profiler.start_profiling()
    
    results = []
    errors = []
    
    def worker_thread(thread_id, operations):
        """Worker thread for stress testing"""
        try:
            motor_interface = EnhancedMockMotorInterface()
            motor_interface.initialize()
            controller = RobustMotorController(motor_interface)
            
            for i in range(operations):
                try:
                    speed = ((thread_id * operations + i) % 200 - 100) / 100.0
                    controller.set_motor_speed(speed)
                    
                    if i % 10 == 0:
                        controller.get_diagnostics()
                        
                except Exception as e:
                    errors.append(f"Thread {thread_id}: {str(e)}")
                    
            results.append(f"Thread {thread_id} completed {operations} operations")
            
        except Exception as e:
            errors.append(f"Thread {thread_id} failed: {str(e)}")
    
    # Create multiple worker threads
    threads = []
    num_threads = 4
    operations_per_thread = 50
    
    for i in range(num_threads):
        thread = threading.Thread(target=worker_thread, args=(i, operations_per_thread))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    metrics = profiler.stop_profiling(start_time)
    
    total_operations = num_threads * operations_per_thread
    
    print(f"  Threads: {num_threads}")
    print(f"  Total operations: {total_operations}")
    print(f"  Successful threads: {len(results)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Execution time: {metrics.execution_time_ms:.2f} ms")
    print(f"  Operations/sec: {total_operations / (metrics.execution_time_ms / 1000):.1f}")
    print(f"  Memory peak: {metrics.memory_peak_mb:.2f} MB")
    
    if errors:
        print("  Error samples:")
        for error in errors[:5]:  # Show first 5 errors
            print(f"    - {error}")
    
    return len(errors) == 0

def main():
    """Run all performance tests"""
    print("🚀 Starting Performance and Memory Profiling")
    print("=" * 60)
    
    test_results = {}
    
    try:
        # Individual component performance tests
        test_results['circuit_breaker'] = test_circuit_breaker_performance()
        test_results['enhanced_motor'] = test_enhanced_motor_performance()
        test_results['config_manager'] = test_config_manager_performance()
        test_results['robust_controller'] = test_robust_controller_performance()
        
        # Memory leak detection
        no_leaks = test_memory_leak_detection()
        test_results['memory_leaks'] = no_leaks
        
        # Stress testing
        stress_passed = run_stress_test()
        test_results['stress_test'] = stress_passed
        
        # Summary
        print("\n📊 Performance Summary")
        print("=" * 60)
        
        total_memory_growth = sum(
            result.memory_growth_mb for result in test_results.values() 
            if hasattr(result, 'memory_growth_mb')
        )
        
        avg_ops_per_sec = sum(
            result.operations_per_second for result in test_results.values()
            if hasattr(result, 'operations_per_second')
        ) / 4  # 4 performance tests
        
        print(f"Average operations/sec: {avg_ops_per_sec:.1f}")
        print(f"Total memory growth: {total_memory_growth:.2f} MB")
        print(f"Memory leak test: {'✅ PASSED' if no_leaks else '❌ FAILED'}")
        print(f"Stress test: {'✅ PASSED' if stress_passed else '❌ FAILED'}")
        
        # Performance thresholds
        performance_issues = []
        
        if avg_ops_per_sec < 100:
            performance_issues.append("Low operations per second")
        
        if total_memory_growth > 10:
            performance_issues.append("High memory growth")
        
        if not no_leaks:
            performance_issues.append("Memory leaks detected")
        
        if not stress_passed:
            performance_issues.append("Stress test failures")
        
        if performance_issues:
            print(f"\n⚠️  Performance Issues Detected:")
            for issue in performance_issues:
                print(f"  - {issue}")
        else:
            print(f"\n✅ All Performance Tests PASSED - System Ready for Production")
        
        return len(performance_issues) == 0
        
    except Exception as e:
        print(f"\n❌ Performance testing failed: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)