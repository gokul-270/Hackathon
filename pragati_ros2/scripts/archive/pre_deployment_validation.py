#!/usr/bin/env python3
"""
Pre-Deployment Validation Script for Pragati Cotton Picker
Tests joint accuracy, drift detection, and system health before field trials

Usage:
    python3 pre_deployment_validation.py [--quick]

Options:
    --quick: Run abbreviated test (20 cycles instead of 100)
"""

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from motor_control_ros2.srv import SetJointPosition, GetJointState
import time
import sys
import math
from collections import defaultdict

class PreDeploymentValidator(Node):
    def __init__(self, quick_mode=False):
        super().__init__('pre_deployment_validator')

        self.quick_mode = quick_mode
        self.test_cycles = 20 if quick_mode else 100

        # Service clients
        self.homing_client = self.create_client(Trigger, '/motor_control/joint_homing')
        self.set_joint_client = self.create_client(SetJointPosition, '/motor_control/set_joint_position')
        self.get_state_client = self.create_client(GetJointState, '/motor_control/get_joint_state')
        self.diagnostics_client = self.create_client(Trigger, '/motor_control/diagnostics')

        # Thresholds
        self.POSITION_TOLERANCE = {
            'joint3': 0.001,  # rad
            'joint4': 0.0001,  # meters (0.1mm)
            'joint5': 0.0001   # meters (0.1mm)
        }

        self.MAX_TEMP = 65.0  # Celsius
        self.MAX_DRIFT = {
            'joint3': 0.002,  # rad cumulative
            'joint4': 0.0002,  # meters cumulative
            'joint5': 0.0002   # meters cumulative
        }

        # Results storage
        self.results = defaultdict(list)
        self.test_passed = True

    def wait_for_services(self):
        """Wait for all required services"""
        services = [
            (self.homing_client, '/motor_control/joint_homing'),
            (self.set_joint_client, '/motor_control/set_joint_position'),
            (self.get_state_client, '/motor_control/get_joint_state'),
            (self.diagnostics_client, '/motor_control/diagnostics')
        ]

        self.get_logger().info("⏳ Waiting for motor control services...")
        for client, name in services:
            if not client.wait_for_service(timeout_sec=10.0):
                self.get_logger().error(f"❌ Service {name} not available")
                return False

        self.get_logger().info("✅ All services available")
        return True

    def get_joint_position(self, joint_name):
        """Get current joint position"""
        request = GetJointState.Request()
        request.joint_name = joint_name

        future = self.get_state_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)

        if future.result():
            return future.result().position
        return None

    def set_joint_position(self, joint_name, position):
        """Move joint to position"""
        request = SetJointPosition.Request()
        request.joint_name = joint_name
        request.position = position

        future = self.set_joint_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        return future.result() and future.result().success

    def home_all_joints(self):
        """Home all joints"""
        self.get_logger().info("🏠 Homing all joints...")

        request = Trigger.Request()
        future = self.homing_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)

        if future.result() and future.result().success:
            self.get_logger().info("✅ Homing complete")
            time.sleep(2.0)  # Settle time
            return True
        else:
            self.get_logger().error("❌ Homing failed")
            return False

    def test_single_joint_accuracy(self, joint_name, test_positions):
        """Test a single joint's position accuracy"""
        self.get_logger().info(f"\n{'='*60}")
        self.get_logger().info(f"Testing {joint_name.upper()} Position Accuracy")
        self.get_logger().info(f"{'='*60}")

        errors = []
        home_errors = []

        for i, target_pos in enumerate(test_positions):
            # Move to target
            self.get_logger().info(f"  [{i+1}/{len(test_positions)}] Moving to {target_pos:.4f}...")

            if not self.set_joint_position(joint_name, target_pos):
                self.get_logger().error(f"    ❌ Failed to command position")
                self.test_passed = False
                continue

            time.sleep(1.5)  # Movement time

            # Read actual position
            actual_pos = self.get_joint_position(joint_name)
            if actual_pos is None:
                self.get_logger().error(f"    ❌ Failed to read position")
                self.test_passed = False
                continue

            error = abs(target_pos - actual_pos)
            errors.append(error)

            if error > self.POSITION_TOLERANCE[joint_name]:
                self.get_logger().warn(f"    ⚠️  Position error: {error:.6f} (target: {target_pos:.4f}, actual: {actual_pos:.4f})")
                self.test_passed = False
            else:
                self.get_logger().info(f"    ✅ Position error: {error:.6f}")

            # Return to home
            time.sleep(0.5)
            if not self.set_joint_position(joint_name, 0.0):
                self.get_logger().error(f"    ❌ Failed to return home")
                self.test_passed = False
                continue

            time.sleep(1.5)

            # Check home position accuracy
            home_pos = self.get_joint_position(joint_name)
            if home_pos is not None:
                home_error = abs(home_pos)
                home_errors.append(home_error)

                if home_error > self.POSITION_TOLERANCE[joint_name]:
                    self.get_logger().warn(f"    ⚠️  Home error: {home_error:.6f}")
                    self.test_passed = False

        # Report statistics
        if errors:
            avg_error = sum(errors) / len(errors)
            max_error = max(errors)
            self.get_logger().info(f"\n  Position Accuracy Summary:")
            self.get_logger().info(f"    Average error: {avg_error:.6f}")
            self.get_logger().info(f"    Maximum error: {max_error:.6f}")
            self.get_logger().info(f"    Tolerance: {self.POSITION_TOLERANCE[joint_name]:.6f}")

            self.results[joint_name].extend(errors)

        if home_errors:
            avg_home_error = sum(home_errors) / len(home_errors)
            max_home_error = max(home_errors)
            self.get_logger().info(f"  Home Return Accuracy:")
            self.get_logger().info(f"    Average error: {avg_home_error:.6f}")
            self.get_logger().info(f"    Maximum error: {max_home_error:.6f}")

    def test_drift_detection(self, joint_name, test_position):
        """Run repeated cycles to detect drift"""
        self.get_logger().info(f"\n{'='*60}")
        self.get_logger().info(f"Testing {joint_name.upper()} Drift Detection ({self.test_cycles} cycles)")
        self.get_logger().info(f"{'='*60}")

        drift_measurements = []

        for cycle in range(self.test_cycles):
            if cycle % 10 == 0:
                self.get_logger().info(f"  Cycle {cycle}/{self.test_cycles}...")

            # Move to test position
            self.set_joint_position(joint_name, test_position)
            time.sleep(1.0)

            # Return to home
            self.set_joint_position(joint_name, 0.0)
            time.sleep(1.0)

            # Measure home position
            home_pos = self.get_joint_position(joint_name)
            if home_pos is not None:
                drift_measurements.append(abs(home_pos))

            # Check for progressive drift
            if len(drift_measurements) >= 10:
                recent_drift = drift_measurements[-10:]
                avg_recent = sum(recent_drift) / len(recent_drift)

                if avg_recent > self.MAX_DRIFT[joint_name]:
                    self.get_logger().error(f"    ❌ DRIFT DETECTED! Average error over last 10 cycles: {avg_recent:.6f}")
                    self.test_passed = False
                    break

        # Final drift report
        if drift_measurements:
            final_drift = drift_measurements[-1]
            max_drift = max(drift_measurements)
            avg_drift = sum(drift_measurements) / len(drift_measurements)

            self.get_logger().info(f"\n  Drift Test Summary:")
            self.get_logger().info(f"    Cycles completed: {len(drift_measurements)}")
            self.get_logger().info(f"    Final home error: {final_drift:.6f}")
            self.get_logger().info(f"    Maximum drift: {max_drift:.6f}")
            self.get_logger().info(f"    Average drift: {avg_drift:.6f}")
            self.get_logger().info(f"    Threshold: {self.MAX_DRIFT[joint_name]:.6f}")

            if max_drift <= self.MAX_DRIFT[joint_name]:
                self.get_logger().info(f"    ✅ No significant drift detected")
            else:
                self.get_logger().error(f"    ❌ Drift exceeds threshold!")
                self.test_passed = False

    def check_system_health(self):
        """Check motor temperatures and CAN health"""
        self.get_logger().info(f"\n{'='*60}")
        self.get_logger().info("System Health Check")
        self.get_logger().info(f"{'='*60}")

        request = Trigger.Request()
        future = self.diagnostics_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if future.result():
            # Parse diagnostics message for temperature info
            msg = future.result().message
            self.get_logger().info(f"  {msg}")

            # Check for temperature warnings in message
            if "CRITICAL" in msg or "WARNING" in msg:
                self.get_logger().warn("  ⚠️  Temperature warnings detected")
        else:
            self.get_logger().warn("  ⚠️  Could not retrieve diagnostics")

    def print_final_report(self):
        """Print comprehensive validation report"""
        self.get_logger().info("\n\n")
        self.get_logger().info("╔" + "="*62 + "╗")
        self.get_logger().info("║" + "   PRE-DEPLOYMENT VALIDATION REPORT".center(62) + "║")
        self.get_logger().info("╚" + "="*62 + "╝")

        # Joint3 results
        if 'joint3' in self.results:
            errors = self.results['joint3']
            self.get_logger().info("\nJoint3 (Rotation):")
            self.get_logger().info(f"  ✅ Position accuracy: ±{max(errors):.6f} rad")
            self.get_logger().info(f"  ✅ Average error: {sum(errors)/len(errors):.6f} rad")
            self.get_logger().info(f"  ✅ Test cycles: {self.test_cycles}")

        # Joint4 results
        if 'joint4' in self.results:
            errors = self.results['joint4']
            self.get_logger().info("\nJoint4 (Left/Right):")
            self.get_logger().info(f"  ✅ Position accuracy: ±{max(errors)*1000:.2f} mm")
            self.get_logger().info(f"  ✅ Average error: {sum(errors)/len(errors)*1000:.2f} mm")
            self.get_logger().info(f"  ✅ Test cycles: {self.test_cycles}")

        # Joint5 results
        if 'joint5' in self.results:
            errors = self.results['joint5']
            self.get_logger().info("\nJoint5 (Extension):")
            self.get_logger().info(f"  ✅ Position accuracy: ±{max(errors)*1000:.2f} mm")
            self.get_logger().info(f"  ✅ Average error: {sum(errors)/len(errors)*1000:.2f} mm")
            self.get_logger().info(f"  ✅ Test cycles: {self.test_cycles}")

        # Overall result
        self.get_logger().info("\n" + "="*62)
        if self.test_passed:
            self.get_logger().info("Overall: ✅ SYSTEM READY FOR DEPLOYMENT")
        else:
            self.get_logger().error("Overall: ❌ SYSTEM VALIDATION FAILED")
            self.get_logger().error("Fix issues before field deployment!")
        self.get_logger().info("="*62 + "\n")

    def run_validation(self):
        """Run complete validation sequence"""
        self.get_logger().info("\n╔" + "="*62 + "╗")
        self.get_logger().info("║" + "   PRE-DEPLOYMENT VALIDATION TEST".center(62) + "║")
        self.get_logger().info("╚" + "="*62 + "╝\n")

        if self.quick_mode:
            self.get_logger().info("⚡ Quick mode: 20 cycles per joint")
        else:
            self.get_logger().info("🔬 Full validation: 100 cycles per joint")

        self.get_logger().info("")

        # Wait for services
        if not self.wait_for_services():
            return False

        # Initial homing
        if not self.home_all_joints():
            return False

        # Test joint3 (rotation)
        joint3_positions = [-0.15, -0.10, -0.05, 0.05, 0.10, 0.15]  # rad
        self.test_single_joint_accuracy('joint3', joint3_positions)
        self.test_drift_detection('joint3', -0.10)

        # Test joint4 (left/right)
        joint4_positions = [-0.10, -0.05, 0.0, 0.05, 0.10, 0.15]  # meters
        self.test_single_joint_accuracy('joint4', joint4_positions)
        self.test_drift_detection('joint4', 0.10)

        # Test joint5 (extension)
        joint5_positions = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]  # meters
        self.test_single_joint_accuracy('joint5', joint5_positions)
        self.test_drift_detection('joint5', 0.20)

        # Final system health check
        self.check_system_health()

        # Print report
        self.print_final_report()

        return self.test_passed


def main():
    rclpy.init()

    quick_mode = '--quick' in sys.argv

    validator = PreDeploymentValidator(quick_mode=quick_mode)

    try:
        success = validator.run_validation()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        validator.get_logger().info("\n⚠️  Validation interrupted by user")
        sys.exit(2)
    finally:
        validator.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
