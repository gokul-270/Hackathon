#!/usr/bin/env python3
"""
Wheel Controller for vehicle_control robot
Control wheels and steering using keyboard or ROS 2 commands
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
import sys
import termios
import tty
import threading


class WheelController(Node):
    def __init__(self):
        super().__init__('wheel_controller')
        
        # Wheel velocity publishers (Gazebo topics)
        self.pub_front_wheel = self.create_publisher(Float64, '/wheel/front/velocity', 10)
        self.pub_right_wheel = self.create_publisher(Float64, '/wheel/right/velocity', 10)
        self.pub_left_wheel = self.create_publisher(Float64, '/wheel/left/velocity', 10)
        
        # Steering position publishers (Gazebo topics)
        self.pub_front_steer = self.create_publisher(Float64, '/steering/front', 10)
        self.pub_right_steer = self.create_publisher(Float64, '/steering/right', 10)
        self.pub_left_steer = self.create_publisher(Float64, '/steering/left', 10)
        
        # Current values
        self.wheel_velocity = 0.0
        self.steering_angle = 0.0
        self.velocity_step = 1.0
        self.steering_step = 0.1
        self.max_velocity = 10.0
        self.max_steering = 1.0
        
        # Print instructions
        self.print_instructions()
        
        # Start keyboard listener
        self.running = True
        self.keyboard_thread = threading.Thread(target=self.keyboard_listener)
        self.keyboard_thread.daemon = True
        self.keyboard_thread.start()
        
        # Timer for continuous publishing
        self.timer = self.create_timer(0.1, self.publish_commands)

    def print_instructions(self):
        self.get_logger().info('=' * 60)
        self.get_logger().info('VEH1 Wheel Controller Ready!')
        self.get_logger().info('=' * 60)
        self.get_logger().info('')
        self.get_logger().info('KEYBOARD CONTROLS:')
        self.get_logger().info('  W / w  - Increase wheel velocity (forward)')
        self.get_logger().info('  S / s  - Decrease wheel velocity (backward)')
        self.get_logger().info('  A / a  - Steer left')
        self.get_logger().info('  D / d  - Steer right')
        self.get_logger().info('  SPACE  - Stop wheels')
        self.get_logger().info('  R / r  - Reset steering to center')
        self.get_logger().info('  Q / q  - Quit')
        self.get_logger().info('')
        self.get_logger().info('TERMINAL COMMANDS (in another terminal):')
        self.get_logger().info('  # Move all wheels forward:')
        self.get_logger().info('  ros2 topic pub /wheel/front/velocity std_msgs/msg/Float64 "{data: 5.0}"')
        self.get_logger().info('  ros2 topic pub /wheel/left/velocity std_msgs/msg/Float64 "{data: 5.0}"')
        self.get_logger().info('  ros2 topic pub /wheel/right/velocity std_msgs/msg/Float64 "{data: 5.0}"')
        self.get_logger().info('')
        self.get_logger().info('  # Steer front wheel:')
        self.get_logger().info('  ros2 topic pub /steering/front std_msgs/msg/Float64 "{data: 0.5}"')
        self.get_logger().info('=' * 60)

    def publish_commands(self):
        """Publish current velocity and steering commands"""
        vel_msg = Float64()
        steer_msg = Float64()
        
        # Publish wheel velocities
        vel_msg.data = self.wheel_velocity
        self.pub_front_wheel.publish(vel_msg)
        self.pub_right_wheel.publish(vel_msg)
        self.pub_left_wheel.publish(vel_msg)
        
        # Publish steering angles
        steer_msg.data = self.steering_angle
        self.pub_front_steer.publish(steer_msg)

    def keyboard_listener(self):
        """Listen for keyboard input"""
        try:
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            
            while self.running:
                try:
                    char = sys.stdin.read(1)
                    
                    if char.lower() == 'q':
                        self.get_logger().info('Quitting...')
                        self.running = False
                        rclpy.shutdown()
                        break
                    elif char.lower() == 'w':
                        self.wheel_velocity = min(self.wheel_velocity + self.velocity_step, self.max_velocity)
                        self.get_logger().info(f'Velocity: {self.wheel_velocity:.1f} rad/s')
                    elif char.lower() == 's':
                        self.wheel_velocity = max(self.wheel_velocity - self.velocity_step, -self.max_velocity)
                        self.get_logger().info(f'Velocity: {self.wheel_velocity:.1f} rad/s')
                    elif char.lower() == 'a':
                        self.steering_angle = min(self.steering_angle + self.steering_step, self.max_steering)
                        self.get_logger().info(f'Steering: {self.steering_angle:.2f} rad')
                    elif char.lower() == 'd':
                        self.steering_angle = max(self.steering_angle - self.steering_step, -self.max_steering)
                        self.get_logger().info(f'Steering: {self.steering_angle:.2f} rad')
                    elif char == ' ':
                        self.wheel_velocity = 0.0
                        self.get_logger().info('STOPPED - Velocity: 0.0 rad/s')
                    elif char.lower() == 'r':
                        self.steering_angle = 0.0
                        self.get_logger().info('Steering RESET - Angle: 0.0 rad')
                        
                except Exception:
                    pass
        except Exception as e:
            self.get_logger().warn(f'Keyboard input not available: {e}')
        finally:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            except Exception:
                pass


def main(args=None):
    rclpy.init(args=args)
    node = WheelController()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
