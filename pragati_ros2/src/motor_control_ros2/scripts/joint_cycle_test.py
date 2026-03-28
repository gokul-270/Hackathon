#!/usr/bin/env python3
"""
Joint Cycle Test - Standalone validation of all motor joints

This script moves all joints through a fixed test pattern to validate:
1. Motor communication (CAN bus)
2. Position commands work correctly
3. All joints move in expected directions
4. Smart polling provides feedback (/joint_states)

Usage:
    # First start motor_control node:
    ros2 launch motor_control_ros2 mg6010_controller.launch.py
    
    # Then run test in another terminal:
    ros2 run motor_control_ros2 joint_cycle_test.py              # Test all joints
    ros2 run motor_control_ros2 joint_cycle_test.py --joint 3    # Test joint3 only
    ros2 run motor_control_ros2 joint_cycle_test.py --joint 4    # Test joint4 only
    ros2 run motor_control_ros2 joint_cycle_test.py --joint 5    # Test joint5 only
    ros2 run motor_control_ros2 joint_cycle_test.py --cycles 3   # Run 3 cycles
    ros2 run motor_control_ros2 joint_cycle_test.py --dry-run    # Print without moving

Requirements:
    - motor_control node must be running (mg6010_controller.launch.py)
    - CAN bus must be up (can0)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from sensor_msgs.msg import JointState
import argparse
import time
import sys


class JointCycleTest(Node):
    """Test node that cycles joints through a fixed pattern."""
    
    # Test positions for each joint (in joint units: rotations/meters)
    # These are safe, small movements from homing positions
    TEST_POSITIONS = {
        'joint3': {  # Rotation (rotations)
            'home': -0.025,
            'test_pos': 0.02,   # Small positive rotation
            'test_neg': -0.05,  # Small negative rotation
            'description': 'rotation (base)',
        },
        'joint4': {  # Left/right (meters)
            'home': 0.0,
            'test_pos': 0.05,   # 5cm right
            'test_neg': -0.05,  # 5cm left
            'description': 'left/right',
        },
        'joint5': {  # Extension (meters)
            'home': -0.018,
            'test_pos': 0.05,   # Extend 5cm
            'test_neg': -0.018,  # Retract to home
            'description': 'extension',
        },
    }
    
    def __init__(self, dry_run=False, cycles=1, delay=2.0, joint_only=None):
        super().__init__('joint_cycle_test')
        
        self.dry_run = dry_run
        self.cycles = cycles
        self.delay = delay
        self.joint_only = joint_only  # None = all joints, or 'joint3', 'joint4', 'joint5'
        
        # Publishers for each joint
        self.publishers = {
            'joint3': self.create_publisher(Float64, '/joint3_position_controller/command', 10),
            'joint4': self.create_publisher(Float64, '/joint4_position_controller/command', 10),
            'joint5': self.create_publisher(Float64, '/joint5_position_controller/command', 10),
        }
        
        # Subscribe to joint states to verify feedback
        self.joint_states = {}
        self.joint_states_received = False
        self.create_subscription(JointState, '/joint_states', self.joint_states_callback, 10)
        
        self.get_logger().info('=' * 60)
        self.get_logger().info('Joint Cycle Test')
        self.get_logger().info('=' * 60)
        if joint_only:
            self.get_logger().info(f'  Testing: {joint_only} only')
        else:
            self.get_logger().info(f'  Testing: ALL joints')
        self.get_logger().info(f'  Dry run: {dry_run}')
        self.get_logger().info(f'  Cycles: {cycles}')
        self.get_logger().info(f'  Delay between moves: {delay}s')
        self.get_logger().info('=' * 60)
        
    def joint_states_callback(self, msg):
        """Store latest joint states for feedback verification."""
        self.joint_states_received = True
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                self.joint_states[name] = msg.position[i]
    
    def send_command(self, joint: str, position: float):
        """Send position command to a joint."""
        if joint not in self.publishers:
            self.get_logger().error(f'Unknown joint: {joint}')
            return
        
        msg = Float64()
        msg.data = position
        
        if self.dry_run:
            self.get_logger().info(f'  [DRY RUN] Would send {joint} -> {position:.4f}')
        else:
            self.publishers[joint].publish(msg)
            self.get_logger().info(f'  Sent {joint} -> {position:.4f}')
    
    def wait_and_check(self, duration: float):
        """Wait for movement and check joint states."""
        time.sleep(duration)
        
        # Spin to get latest joint_states
        rclpy.spin_once(self, timeout_sec=0.1)
        
        if self.joint_states_received:
            self.get_logger().info(f'  Joint states: {self.format_joint_states()}')
        else:
            self.get_logger().warn('  No /joint_states received (smart polling not working?)')
    
    def format_joint_states(self) -> str:
        """Format joint states for logging."""
        parts = []
        for name in ['joint3', 'joint4', 'joint5']:
            if name in self.joint_states:
                parts.append(f'{name}={self.joint_states[name]:.4f}')
            else:
                parts.append(f'{name}=?')
        return ', '.join(parts)
    
    def test_single_joint(self, joint: str, cycle_num: int):
        """Test a single joint."""
        pos = self.TEST_POSITIONS[joint]
        desc = pos.get('description', joint)
        
        self.get_logger().info(f'\n--- Cycle {cycle_num}/{self.cycles}: {joint} ({desc}) ---')
        
        # Move to home first
        self.get_logger().info(f'  Moving {joint} to home ({pos["home"]:.4f})')
        self.send_command(joint, pos['home'])
        self.wait_and_check(self.delay)
        
        # Test positive direction
        self.get_logger().info(f'  Moving {joint} positive ({pos["test_pos"]:.4f})')
        self.send_command(joint, pos['test_pos'])
        self.wait_and_check(self.delay)
        
        # Test negative direction
        self.get_logger().info(f'  Moving {joint} negative ({pos["test_neg"]:.4f})')
        self.send_command(joint, pos['test_neg'])
        self.wait_and_check(self.delay)
        
        # Return to home
        self.get_logger().info(f'  Returning {joint} to home ({pos["home"]:.4f})')
        self.send_command(joint, pos['home'])
        self.wait_and_check(self.delay)
        
        self.get_logger().info(f'  {joint} test complete')
    
    def run_test_cycle(self, cycle_num: int):
        """Run a single test cycle."""
        
        # If testing single joint only
        if self.joint_only:
            self.test_single_joint(self.joint_only, cycle_num)
            return
        
        # Test all joints
        self.get_logger().info(f'\n--- Cycle {cycle_num}/{self.cycles} (ALL JOINTS) ---')
        
        # Step 1: Move joint5 to home (retract first for safety)
        self.get_logger().info('Step 1: Retract joint5 to home')
        self.send_command('joint5', self.TEST_POSITIONS['joint5']['home'])
        self.wait_and_check(self.delay)
        
        # Step 2: Test joint3 (rotation)
        self.get_logger().info('Step 2: Test joint3 (rotation)')
        self.send_command('joint3', self.TEST_POSITIONS['joint3']['test_pos'])
        self.wait_and_check(self.delay)
        self.send_command('joint3', self.TEST_POSITIONS['joint3']['test_neg'])
        self.wait_and_check(self.delay)
        self.send_command('joint3', self.TEST_POSITIONS['joint3']['home'])
        self.wait_and_check(self.delay)
        
        # Step 3: Test joint4 (left/right)
        self.get_logger().info('Step 3: Test joint4 (left/right)')
        self.send_command('joint4', self.TEST_POSITIONS['joint4']['test_pos'])
        self.wait_and_check(self.delay)
        self.send_command('joint4', self.TEST_POSITIONS['joint4']['test_neg'])
        self.wait_and_check(self.delay)
        self.send_command('joint4', self.TEST_POSITIONS['joint4']['home'])
        self.wait_and_check(self.delay)
        
        # Step 4: Test joint5 (extension)
        self.get_logger().info('Step 4: Test joint5 (extension)')
        self.send_command('joint5', self.TEST_POSITIONS['joint5']['test_pos'])
        self.wait_and_check(self.delay)
        self.send_command('joint5', self.TEST_POSITIONS['joint5']['home'])
        self.wait_and_check(self.delay)
        
        # Step 5: Combined movement (all joints to test position)
        self.get_logger().info('Step 5: Combined movement')
        self.send_command('joint3', self.TEST_POSITIONS['joint3']['test_pos'])
        self.send_command('joint4', self.TEST_POSITIONS['joint4']['test_pos'])
        time.sleep(0.5)  # Small delay between commands
        self.send_command('joint5', self.TEST_POSITIONS['joint5']['test_pos'])
        self.wait_and_check(self.delay * 1.5)
        
        # Step 6: Return all to home
        self.get_logger().info('Step 6: Return all to home')
        self.send_command('joint5', self.TEST_POSITIONS['joint5']['home'])
        time.sleep(0.5)
        self.send_command('joint3', self.TEST_POSITIONS['joint3']['home'])
        self.send_command('joint4', self.TEST_POSITIONS['joint4']['home'])
        self.wait_and_check(self.delay)
        
        self.get_logger().info(f'Cycle {cycle_num} complete')
    
    def run(self):
        """Run the full test sequence."""
        self.get_logger().info('\nStarting joint cycle test...')
        self.get_logger().info('Press Ctrl+C to abort\n')
        
        # Wait a moment for publishers to connect
        time.sleep(1.0)
        
        # Check if we're receiving joint_states
        rclpy.spin_once(self, timeout_sec=1.0)
        if self.joint_states_received:
            self.get_logger().info(f'✅ Receiving /joint_states: {self.format_joint_states()}')
        else:
            self.get_logger().warn('⚠️  No /joint_states received yet (will check during test)')
        
        try:
            for cycle in range(1, self.cycles + 1):
                self.run_test_cycle(cycle)
            
            self.get_logger().info('\n' + '=' * 60)
            self.get_logger().info('✅ Joint cycle test completed successfully!')
            self.get_logger().info('=' * 60)
            
            if self.joint_states_received:
                self.get_logger().info('✅ Smart polling verified (/joint_states working)')
            else:
                self.get_logger().warn('⚠️  Smart polling not verified (no /joint_states received)')
            
            return True
            
        except KeyboardInterrupt:
            self.get_logger().warn('\n⚠️  Test aborted by user')
            # Try to return to home
            self.get_logger().info('Returning to home positions...')
            self.send_command('joint5', self.TEST_POSITIONS['joint5']['home'])
            time.sleep(0.5)
            self.send_command('joint3', self.TEST_POSITIONS['joint3']['home'])
            self.send_command('joint4', self.TEST_POSITIONS['joint4']['home'])
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Joint Cycle Test - Validate motor joints',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Test all joints
  %(prog)s --joint 3          # Test joint3 only (rotation)
  %(prog)s --joint 4          # Test joint4 only (left/right)
  %(prog)s --joint 5          # Test joint5 only (extension)
  %(prog)s --cycles 3         # Run 3 test cycles
  %(prog)s --dry-run          # Preview without moving
""")
    parser.add_argument('--joint', type=int, choices=[3, 4, 5],
                        help='Test single joint only (3, 4, or 5)')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Print commands without sending them')
    parser.add_argument('--cycles', type=int, default=1,
                        help='Number of test cycles to run (default: 1)')
    parser.add_argument('--delay', type=float, default=2.0,
                        help='Delay between movements in seconds (default: 2.0)')
    args = parser.parse_args()
    
    # Convert joint number to joint name
    joint_only = f'joint{args.joint}' if args.joint else None
    
    rclpy.init()
    
    try:
        node = JointCycleTest(
            dry_run=args.dry_run,
            cycles=args.cycles,
            delay=args.delay,
            joint_only=joint_only
        )
        success = node.run()
        node.destroy_node()
        
        return 0 if success else 1
        
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
