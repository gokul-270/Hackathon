#!/usr/bin/env python3
"""
PID Tuning Visualizer for MG6010 Motors
========================================

Real-time visualization tool for PID tuning with:
- Step response plots
- Error tracking
- Control output visualization
- Performance metrics (overshoot, settling time, steady-state error)
- Multiple motor support
- Export/save capabilities

Usage:
    python3 pid_tuning_visualizer.py --motor-id 1
    python3 pid_tuning_visualizer.py --motor-id 1 --duration 30
    python3 pid_tuning_visualizer.py --all-motors  # Monitor all motors
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import argparse
import json
from datetime import datetime
import threading


@dataclass
class PerformanceMetrics:
    """Performance metrics for PID tuning evaluation"""
    rise_time: float = 0.0          # Time to reach 90% of setpoint
    settling_time: float = 0.0      # Time to settle within 2% of setpoint
    overshoot_percent: float = 0.0  # Maximum overshoot percentage
    steady_state_error: float = 0.0 # Final steady-state error
    peak_time: float = 0.0          # Time to first peak
    
    # Integral metrics
    iae: float = 0.0  # Integral Absolute Error
    ise: float = 0.0  # Integral Square Error
    itse: float = 0.0 # Integral Time Square Error
    
    # Control effort
    control_effort: float = 0.0     # Total control effort (sum of |u|)
    
    def __str__(self) -> str:
        return (f"Rise Time: {self.rise_time:.3f}s | "
                f"Settling: {self.settling_time:.3f}s | "
                f"Overshoot: {self.overshoot_percent:.1f}% | "
                f"SS Error: {self.steady_state_error:.4f} | "
                f"IAE: {self.iae:.3f}")


@dataclass
class MotorData:
    """Data storage for a single motor"""
    motor_id: int
    
    # Time-series data (circular buffers)
    time: deque = field(default_factory=lambda: deque(maxlen=1000))
    setpoint: deque = field(default_factory=lambda: deque(maxlen=1000))
    position: deque = field(default_factory=lambda: deque(maxlen=1000))
    velocity: deque = field(default_factory=lambda: deque(maxlen=1000))
    error: deque = field(default_factory=lambda: deque(maxlen=1000))
    control_output: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # Metadata
    start_time: Optional[float] = None
    last_setpoint: float = 0.0
    setpoint_changed_time: Optional[float] = None
    
    # Performance metrics
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    
    def add_data(self, time_val: float, sp: float, pos: float, 
                 vel: float, err: float, ctrl: float):
        """Add new data point"""
        if self.start_time is None:
            self.start_time = time_val
        
        # Track setpoint changes for step response
        if abs(sp - self.last_setpoint) > 0.01:
            self.setpoint_changed_time = time_val
            self.last_setpoint = sp
        
        self.time.append(time_val - self.start_time)
        self.setpoint.append(sp)
        self.position.append(pos)
        self.velocity.append(vel)
        self.error.append(err)
        self.control_output.append(ctrl)
    
    def calculate_metrics(self) -> PerformanceMetrics:
        """Calculate performance metrics from collected data"""
        if len(self.time) < 10 or self.setpoint_changed_time is None:
            return self.metrics
        
        # Get data after last setpoint change
        start_idx = 0
        for i, t in enumerate(self.time):
            if self.time[i] >= (self.setpoint_changed_time - self.start_time):
                start_idx = i
                break
        
        if start_idx >= len(self.time) - 5:
            return self.metrics
        
        sp_arr = np.array(list(self.setpoint)[start_idx:])
        pos_arr = np.array(list(self.position)[start_idx:])
        time_arr = np.array(list(self.time)[start_idx:])
        err_arr = np.array(list(self.error)[start_idx:])
        ctrl_arr = np.array(list(self.control_output)[start_idx:])
        
        if len(sp_arr) < 5:
            return self.metrics
        
        # Target setpoint (use last setpoint value)
        target = sp_arr[-1]
        initial = pos_arr[0]
        
        if abs(target - initial) < 0.001:
            return self.metrics
        
        # Rise time (10% to 90%)
        ten_percent = initial + 0.1 * (target - initial)
        ninety_percent = initial + 0.9 * (target - initial)
        
        try:
            idx_10 = np.where(pos_arr >= ten_percent)[0][0]
            idx_90 = np.where(pos_arr >= ninety_percent)[0][0]
            self.metrics.rise_time = time_arr[idx_90] - time_arr[idx_10]
        except (IndexError, ValueError):
            pass
        
        # Overshoot
        peak_val = np.max(pos_arr)
        if peak_val > target:
            self.metrics.overshoot_percent = ((peak_val - target) / abs(target - initial)) * 100
            peak_idx = np.argmax(pos_arr)
            self.metrics.peak_time = time_arr[peak_idx]
        
        # Settling time (2% criterion)
        settling_band = 0.02 * abs(target - initial)
        in_band = np.abs(pos_arr - target) <= settling_band
        
        # Find last time outside band
        for i in range(len(in_band) - 1, -1, -1):
            if not in_band[i]:
                self.metrics.settling_time = time_arr[min(i + 1, len(time_arr) - 1)]
                break
        
        # Steady-state error (average of last 10% of data)
        last_n = max(5, len(pos_arr) // 10)
        self.metrics.steady_state_error = np.mean(np.abs(pos_arr[-last_n:] - target))
        
        # Integral metrics
        dt = np.diff(time_arr)
        if len(dt) > 0:
            self.metrics.iae = np.sum(np.abs(err_arr[:-1]) * dt)
            self.metrics.ise = np.sum((err_arr[:-1] ** 2) * dt)
            self.metrics.itse = np.sum((err_arr[:-1] ** 2) * time_arr[:-1] * dt)
            self.metrics.control_effort = np.sum(np.abs(ctrl_arr[:-1]) * dt)
        
        return self.metrics


class PIDTuningVisualizer(Node):
    """ROS2 node for PID tuning visualization"""
    
    def __init__(self, motor_ids: List[int], duration: float = 60.0):
        super().__init__('pid_tuning_visualizer')
        
        self.motor_ids = motor_ids
        self.duration = duration
        self.motor_data: Dict[int, MotorData] = {
            mid: MotorData(motor_id=mid) for mid in motor_ids
        }
        
        # ROS2 subscribers
        self.joint_state_sub = self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            10
        )
        
        # For control output, we'll estimate from velocity
        # In a real system, subscribe to actual control command topic
        
        # Visualization setup
        self.lock = threading.Lock()
        self.running = True
        
        self.get_logger().info(f'PID Tuning Visualizer started for motors: {motor_ids}')
    
    def joint_state_callback(self, msg: JointState):
        """Callback for joint state updates"""
        current_time = self.get_clock().now().nanoseconds / 1e9
        
        with self.lock:
            for i, name in enumerate(msg.name):
                # Extract motor ID from joint name (e.g., "joint_2" -> motor 2)
                if name.startswith('joint_'):
                    try:
                        motor_id = int(name.split('_')[1])
                        if motor_id not in self.motor_ids:
                            continue
                        
                        position = msg.position[i] if i < len(msg.position) else 0.0
                        velocity = msg.velocity[i] if i < len(msg.velocity) else 0.0
                        effort = msg.effort[i] if i < len(msg.effort) else 0.0
                        
                        # Estimate setpoint (in real system, subscribe to command topic)
                        # For now, assume setpoint is close to current position during steady state
                        motor = self.motor_data[motor_id]
                        if len(motor.position) > 0:
                            setpoint = motor.last_setpoint
                        else:
                            setpoint = position
                        
                        error = setpoint - position
                        control_output = effort  # Use effort as proxy for control output
                        
                        self.motor_data[motor_id].add_data(
                            current_time, setpoint, position, 
                            velocity, error, control_output
                        )
                        
                    except (ValueError, IndexError) as e:
                        self.get_logger().warn(f'Failed to parse joint name: {name}')
    
    def get_plot_data(self, motor_id: int) -> Tuple:
        """Get plot data for a specific motor (thread-safe)"""
        with self.lock:
            motor = self.motor_data[motor_id]
            return (
                list(motor.time),
                list(motor.setpoint),
                list(motor.position),
                list(motor.velocity),
                list(motor.error),
                list(motor.control_output),
                motor.calculate_metrics()
            )
    
    def export_data(self, filename: str):
        """Export collected data to JSON"""
        data = {}
        with self.lock:
            for motor_id, motor in self.motor_data.items():
                data[f'motor_{motor_id}'] = {
                    'time': list(motor.time),
                    'setpoint': list(motor.setpoint),
                    'position': list(motor.position),
                    'velocity': list(motor.velocity),
                    'error': list(motor.error),
                    'control_output': list(motor.control_output),
                    'metrics': {
                        'rise_time': motor.metrics.rise_time,
                        'settling_time': motor.metrics.settling_time,
                        'overshoot_percent': motor.metrics.overshoot_percent,
                        'steady_state_error': motor.metrics.steady_state_error,
                        'iae': motor.metrics.iae,
                        'ise': motor.metrics.ise,
                    }
                }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        self.get_logger().info(f'Data exported to {filename}')


def create_visualization(visualizer: PIDTuningVisualizer, motor_id: int):
    """Create real-time visualization plots for a motor"""
    
    # Setup figure
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(f'PID Tuning Visualization - Motor {motor_id}', fontsize=16, fontweight='bold')
    
    gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.3)
    
    # Create subplots
    ax1 = fig.add_subplot(gs[0, :])  # Step response
    ax2 = fig.add_subplot(gs[1, 0])  # Error
    ax3 = fig.add_subplot(gs[1, 1])  # Velocity
    ax4 = fig.add_subplot(gs[2, 0])  # Control output
    ax5 = fig.add_subplot(gs[2, 1])  # Metrics text
    
    # Initialize empty plots
    line_sp, = ax1.plot([], [], 'r--', label='Setpoint', linewidth=2)
    line_pos, = ax1.plot([], [], 'b-', label='Position', linewidth=2)
    line_err, = ax2.plot([], [], 'orange', linewidth=2)
    line_vel, = ax3.plot([], [], 'green', linewidth=2)
    line_ctrl, = ax4.plot([], [], 'purple', linewidth=2)
    
    # Configure axes
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Position (rad)')
    ax1.set_title('Step Response')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Error (rad)')
    ax2.set_title('Position Error')
    ax2.grid(True, alpha=0.3)
    
    ax3.set_xlabel('Time (s)')
    ax3.set_ylabel('Velocity (rad/s)')
    ax3.set_title('Velocity')
    ax3.grid(True, alpha=0.3)
    
    ax4.set_xlabel('Time (s)')
    ax4.set_ylabel('Control Output')
    ax4.set_title('Control Effort')
    ax4.grid(True, alpha=0.3)
    
    ax5.axis('off')
    metrics_text = ax5.text(0.05, 0.95, '', transform=ax5.transAxes,
                           verticalalignment='top', fontfamily='monospace',
                           fontsize=10)
    
    def update_plot(frame):
        """Update plot with new data"""
        time, setpoint, position, velocity, error, control, metrics = \
            visualizer.get_plot_data(motor_id)
        
        if len(time) < 2:
            return line_sp, line_pos, line_err, line_vel, line_ctrl, metrics_text
        
        # Update data
        line_sp.set_data(time, setpoint)
        line_pos.set_data(time, position)
        line_err.set_data(time, error)
        line_vel.set_data(time, velocity)
        line_ctrl.set_data(time, control)
        
        # Auto-scale axes
        ax1.relim()
        ax1.autoscale_view()
        ax2.relim()
        ax2.autoscale_view()
        ax3.relim()
        ax3.autoscale_view()
        ax4.relim()
        ax4.autoscale_view()
        
        # Update metrics text
        metrics_str = f"""Performance Metrics:
        
Rise Time:        {metrics.rise_time:.3f} s
Settling Time:    {metrics.settling_time:.3f} s
Overshoot:        {metrics.overshoot_percent:.1f} %
Peak Time:        {metrics.peak_time:.3f} s
SS Error:         {metrics.steady_state_error:.5f} rad

Integral Metrics:
IAE:              {metrics.iae:.3f}
ISE:              {metrics.ise:.3f}
ITSE:             {metrics.itse:.3f}
Control Effort:   {metrics.control_effort:.3f}

Current Values:
Position:         {position[-1]:.4f} rad
Velocity:         {velocity[-1]:.4f} rad/s
Error:            {error[-1]:.5f} rad
"""
        metrics_text.set_text(metrics_str)
        
        return line_sp, line_pos, line_err, line_vel, line_ctrl, metrics_text
    
    # Create animation
    ani = animation.FuncAnimation(
        fig, update_plot, interval=100, blit=True, cache_frame_data=False
    )
    
    return fig, ani


def main():
    parser = argparse.ArgumentParser(description='PID Tuning Visualizer for MG6010 Motors')
    parser.add_argument('--motor-id', type=int, help='Motor ID to monitor (1-5)')
    parser.add_argument('--all-motors', action='store_true', 
                       help='Monitor all motors (2-5)')
    parser.add_argument('--duration', type=float, default=60.0,
                       help='Monitoring duration in seconds (default: 60)')
    parser.add_argument('--export', type=str, 
                       help='Export data to JSON file')
    
    args = parser.parse_args()
    
    # Determine which motors to monitor
    if args.all_motors:
        motor_ids = [2, 3, 4, 5]
    elif args.motor_id:
        motor_ids = [args.motor_id]
    else:
        print("Error: Must specify --motor-id or --all-motors")
        return
    
    # Initialize ROS2
    rclpy.init()
    
    # Create visualizer node
    visualizer = PIDTuningVisualizer(motor_ids, duration=args.duration)
    
    # Start ROS2 spinning in separate thread
    spin_thread = threading.Thread(target=rclpy.spin, args=(visualizer,), daemon=True)
    spin_thread.start()
    
    print(f"PID Tuning Visualizer")
    print(f"Monitoring motors: {motor_ids}")
    print(f"Duration: {args.duration}s")
    print("\nPress Ctrl+C to stop and export data\n")
    
    # Create visualization for each motor
    figures = []
    animations = []
    
    for motor_id in motor_ids:
        fig, ani = create_visualization(visualizer, motor_id)
        figures.append(fig)
        animations.append(ani)
    
    # Show plots
    try:
        plt.show()
    except KeyboardInterrupt:
        print("\nStopping...")
    
    # Export data if requested
    if args.export:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = args.export if args.export.endswith('.json') else f"{args.export}_{timestamp}.json"
        visualizer.export_data(filename)
    
    # Cleanup
    visualizer.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
