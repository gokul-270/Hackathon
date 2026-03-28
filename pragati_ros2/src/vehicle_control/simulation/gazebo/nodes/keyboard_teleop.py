#!/usr/bin/env python3
"""
Keyboard Teleoperation Node for vehicle_control Robot

Control the robot using arrow keys and other keyboard commands.

Controls:
  Arrow Up/Down    : Forward/Backward
  Arrow Left/Right : Rotate Left/Right
  W/S              : Increase/Decrease linear speed
  A/D              : Increase/Decrease angular speed
  SPACE            : Stop (emergency brake)
  T                : Toggle turbo mode
  Q/ESC            : Quit

Author: vehicle_control Package
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import sys
import termios
import tty
import select


class KeyboardTeleop(Node):
    """Keyboard teleoperation for vehicle_control robot."""

    def __init__(self):
        super().__init__('keyboard_teleop')

        # Create publisher
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # Direct control settings - hold key to move
        self.base_linear_speed = 0.2  # m/s when W/S held (gentle)
        self.base_angular_speed = 0.15  # rad/s when A/D held (gentle steering)

        # Speed adjustment increments
        self.linear_increment = 0.1  # E/C keys adjust by 0.1 m/s
        self.angular_increment = 0.05  # R/F keys adjust by 0.05 rad/s
        self.max_linear_speed = 1.0
        self.max_angular_speed = 0.8

        # Current velocities (updated by key presses)
        self.target_linear = 0.0
        self.target_angular = 0.0

        # Key states - track which keys are currently pressed
        self.keys_pressed = set()

        # Timer to publish commands
        self.timer = self.create_timer(0.05, self.publish_cmd_vel)  # 20Hz for responsive control

        # Terminal settings for raw key input
        self.settings = termios.tcgetattr(sys.stdin)

        self.print_usage()

    def print_usage(self):
        """Print control instructions."""
        print("\n" + "="*60)
        print("🎮 DIRECT CONTROL - vehicle_control Robot")
        print("="*60)
        print("\n🚗 WSAD Movement (Hold to Move):")
        print(f"  W : Move Forward ({self.base_linear_speed:.2f} m/s while held)")
        print(f"  S : Move Backward ({self.base_linear_speed:.2f} m/s while held)")
        print(f"  A : Turn Left + Drive ({self.base_angular_speed:.2f} rad/s arc)")
        print(f"  D : Turn Right + Drive ({self.base_angular_speed:.2f} rad/s arc)")
        print("\n⚡ Speed Adjustment:")
        print(f"  E : Increase Linear Speed (+{self.linear_increment} m/s)")
        print(f"  C : Decrease Linear Speed (-{self.linear_increment} m/s)")
        print(f"  R : Increase Angular Speed (+{self.angular_increment} rad/s)")
        print(f"  F : Decrease Angular Speed (-{self.angular_increment} rad/s)")
        print("\n🎯 Special Commands:")
        print("  SPACE : Emergency Stop")
        print("  Q/ESC : Quit")
        print("\n💡 TIPS:")
        print("  • Hold W to move forward - release to stop")
        print("  • Hold A/D to drive in gentle arcs")
        print("  • Use E/C to adjust forward speed, R/F for turning speed")
        print("  • Vehicle uses kinematics_node for accurate control!")
        print("="*60)
        print(f"\n✅ Ready! Linear: {self.base_linear_speed:.2f} m/s, Angular: {self.base_angular_speed:.2f} rad/s\n")

    def get_key(self):
        """Get a single key press from stdin."""
        tty.setraw(sys.stdin.fileno())
        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
        if rlist:
            key = sys.stdin.read(1)
            # Check for arrow keys (escape sequences)
            if key == '\x1b':  # ESC sequence
                key += sys.stdin.read(2)
            return key
        return ''

    def reset_terminal(self):
        """Reset terminal to normal mode."""
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)

    def process_key(self, key):
        """Process keyboard input - direct control (hold to move)."""
        if key.lower() == 'w':
            self.keys_pressed.add('w')

        elif key.lower() == 's':
            self.keys_pressed.add('s')

        elif key.lower() == 'a':
            self.keys_pressed.add('a')

        elif key.lower() == 'd':
            self.keys_pressed.add('d')

        elif key.lower() == 'e':
            # Increase linear speed
            self.base_linear_speed = min(self.max_linear_speed,
                                        self.base_linear_speed + self.linear_increment)
            self.get_logger().info(
                f"Linear Speed increased: {self.base_linear_speed:.2f} m/s"
            )

        elif key.lower() == 'c':
            # Decrease linear speed
            self.base_linear_speed = max(0.05,
                                        self.base_linear_speed - self.linear_increment)
            self.get_logger().info(
                f"Linear Speed decreased: {self.base_linear_speed:.2f} m/s"
            )

        elif key.lower() == 'r':
            # Increase angular speed
            self.base_angular_speed = min(self.max_angular_speed,
                                         self.base_angular_speed + self.angular_increment)
            self.get_logger().info(
                f"Angular Speed increased: {self.base_angular_speed:.2f} rad/s"
            )

        elif key.lower() == 'f':
            # Decrease angular speed
            self.base_angular_speed = max(0.05,
                                         self.base_angular_speed - self.angular_increment)
            self.get_logger().info(
                f"Angular Speed decreased: {self.base_angular_speed:.2f} rad/s"
            )

        elif key == ' ':  # Space - emergency stop
            self.keys_pressed.clear()
            self.target_linear = 0.0
            self.target_angular = 0.0
            self.get_logger().warn("EMERGENCY STOP!")

        elif key.lower() == 'q' or key == '\x1b':  # Quit
            self.get_logger().info("Shutting down...")
            self.keys_pressed.clear()
            self.target_linear = 0.0
            self.target_angular = 0.0
            self.publish_cmd_vel()
            self.reset_terminal()
            rclpy.shutdown()
            sys.exit(0)

    def update_velocities(self):
        """Update target velocities based on currently pressed keys."""
        prev_linear = self.target_linear
        prev_angular = self.target_angular

        # Reset velocities
        self.target_linear = 0.0
        self.target_angular = 0.0

        # Apply movement based on pressed keys (can combine!)
        if 'w' in self.keys_pressed:
            self.target_linear = self.base_linear_speed
        elif 's' in self.keys_pressed:
            self.target_linear = -self.base_linear_speed

        # Steering with A/D - works with forward or backward movement
        if 'a' in self.keys_pressed:
            self.target_angular = self.base_angular_speed
            # Add forward movement if W/S not pressed (gentle arc)
            if 'w' not in self.keys_pressed and 's' not in self.keys_pressed:
                self.target_linear = self.base_linear_speed
        elif 'd' in self.keys_pressed:
            self.target_angular = -self.base_angular_speed
            # Add forward movement if W/S not pressed (gentle arc)
            if 'w' not in self.keys_pressed and 's' not in self.keys_pressed:
                self.target_linear = self.base_linear_speed

        # Print status when velocities change
        if (abs(self.target_linear - prev_linear) > 0.01 or
            abs(self.target_angular - prev_angular) > 0.01):
            if self.target_linear != 0.0 and self.target_angular != 0.0:
                direction = "LEFT" if self.target_angular > 0 else "RIGHT"
                movement = "FORWARD" if self.target_linear > 0 else "BACKWARD"
                self.get_logger().debug(
                    f"{movement} + {direction}: v={self.target_linear:.2f} m/s, "
                    f"omega={self.target_angular:.2f} rad/s"
                )
            elif self.target_linear != 0.0:
                direction = "FORWARD" if self.target_linear > 0 else "BACKWARD"
                self.get_logger().debug(
                    f"{direction}: v={self.target_linear:.2f} m/s"
                )
            elif self.target_angular != 0.0:
                direction = "LEFT" if self.target_angular > 0 else "RIGHT"
                self.get_logger().debug(
                    f"TURN {direction}: omega={self.target_angular:.2f} rad/s"
                )
            else:
                self.get_logger().debug("STOPPED")

    def publish_cmd_vel(self):
        """Publish current velocity command based on pressed keys."""
        # Update velocities based on currently pressed keys
        self.update_velocities()

        twist = Twist()
        twist.linear.x = self.target_linear
        twist.angular.z = self.target_angular

        self.cmd_vel_pub.publish(twist)

    def run(self):
        """Main loop to read keyboard and control robot."""
        try:
            import time
            last_key_time = {}
            key_timeout = 0.2  # Keys expire after 200ms if not re-pressed

            while rclpy.ok():
                key = self.get_key()
                current_time = time.time()

                if key:
                    self.process_key(key)
                    # Mark this key as recently pressed
                    if key.lower() in ['w', 's', 'a', 'd']:
                        last_key_time[key.lower()] = current_time

                # Remove keys that haven't been pressed recently (released)
                expired_keys = []
                for k, t in last_key_time.items():
                    if current_time - t > key_timeout:
                        expired_keys.append(k)
                        if k in self.keys_pressed:
                            self.keys_pressed.remove(k)

                for k in expired_keys:
                    del last_key_time[k]

                # Spin once to process callbacks
                rclpy.spin_once(self, timeout_sec=0)

        except Exception as e:
            self.get_logger().error(f"Error in teleop loop: {e}")
        finally:
            self.reset_terminal()


def main(args=None):
    rclpy.init(args=args)
    node = KeyboardTeleop()

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
    finally:
        # Send stop command
        twist = Twist()
        node.cmd_vel_pub.publish(twist)
        node.reset_terminal()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
