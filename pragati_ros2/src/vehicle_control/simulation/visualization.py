"""
Vehicle Control System - Visualization Module

Provides advanced visualization capabilities for vehicle simulation including:
- 3D vehicle representation
- Real-time data plotting
- Performance analytics
- Custom chart types
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
from matplotlib.animation import FuncAnimation
import matplotlib.patches as patches
from typing import Dict, List, Tuple, Optional
import matplotlib.gridspec as gridspec


class VehicleVisualizer:
    """
    Advanced vehicle visualization system.
    
    Provides multiple visualization modes:
    - Top-down vehicle view with motor positions
    - Real-time data plots
    - Performance metrics
    - Trajectory visualization
    """
    
    def __init__(self, figsize: Tuple[int, int] = (15, 10)):
        self.figsize = figsize
        self.fig = None
        self.axes = {}
        
        # Vehicle parameters for visualization
        self.vehicle_length = 3.0  # meters
        self.vehicle_width = 1.8   # meters
        self.wheelbase = 2.5       # meters
        self.track_width = 1.8     # meters
        
        # Color scheme
        self.colors = {
            'vehicle_body': '#3498db',
            'motor_steering': '#e74c3c',
            'motor_drive': '#2ecc71',
            'trajectory': '#f39c12',
            'grid': '#bdc3c7',
            'text': '#2c3e50'
        }
        
        # Data storage for plots
        self.max_data_points = 1000
        self.time_data = []
        self.trajectory_data = {'x': [], 'y': []}
        self.performance_data = {
            'velocity': [],
            'acceleration': [],
            'motor_angles': {'front': [], 'rear_left': [], 'rear_right': []},
            'motor_speeds': {'front': [], 'rear_left': [], 'rear_right': []}
        }
        
    def create_dashboard(self) -> plt.Figure:
        """
        Create a comprehensive dashboard with multiple views.
        
        Returns:
            Matplotlib figure with dashboard layout
        """
        self.fig = plt.figure(figsize=self.figsize)
        self.fig.suptitle('Vehicle Control System - Live Dashboard', fontsize=16, fontweight='bold')
        
        # Create grid layout
        gs = gridspec.GridSpec(3, 4, figure=self.fig, hspace=0.3, wspace=0.3)
        
        # Vehicle view (large, top-left)
        self.axes['vehicle'] = self.fig.add_subplot(gs[0:2, 0:2])
        self.axes['vehicle'].set_title('Vehicle Position & Orientation')
        self.axes['vehicle'].set_xlabel('X Position (m)')
        self.axes['vehicle'].set_ylabel('Y Position (m)')
        self.axes['vehicle'].set_aspect('equal')
        self.axes['vehicle'].grid(True, color=self.colors['grid'], alpha=0.3)
        
        # Trajectory view (top-right)
        self.axes['trajectory'] = self.fig.add_subplot(gs[0, 2:4])
        self.axes['trajectory'].set_title('Vehicle Trajectory')
        self.axes['trajectory'].set_xlabel('X (m)')
        self.axes['trajectory'].set_ylabel('Y (m)')
        self.axes['trajectory'].grid(True, color=self.colors['grid'], alpha=0.3)
        
        # Velocity plot (middle-right)
        self.axes['velocity'] = self.fig.add_subplot(gs[1, 2:4])
        self.axes['velocity'].set_title('Velocity Profile')
        self.axes['velocity'].set_xlabel('Time (s)')
        self.axes['velocity'].set_ylabel('Velocity (m/s)')
        self.axes['velocity'].grid(True, color=self.colors['grid'], alpha=0.3)
        
        # Motor angles (bottom-left)
        self.axes['motor_angles'] = self.fig.add_subplot(gs[2, 0:2])
        self.axes['motor_angles'].set_title('Steering Angles')
        self.axes['motor_angles'].set_xlabel('Time (s)')
        self.axes['motor_angles'].set_ylabel('Angle (degrees)')
        self.axes['motor_angles'].grid(True, color=self.colors['grid'], alpha=0.3)
        
        # Motor speeds (bottom-right)
        self.axes['motor_speeds'] = self.fig.add_subplot(gs[2, 2:4])
        self.axes['motor_speeds'].set_title('Drive Speeds')
        self.axes['motor_speeds'].set_xlabel('Time (s)')
        self.axes['motor_speeds'].set_ylabel('Speed (%)')
        self.axes['motor_speeds'].grid(True, color=self.colors['grid'], alpha=0.3)
        
        return self.fig
    
    def update_vehicle_view(self, state: Dict):
        """
        Update the vehicle visualization with current state.
        
        Args:
            state: Vehicle state dictionary
        """
        ax = self.axes['vehicle']
        ax.clear()
        
        # Get vehicle position and orientation
        x = state['position']['x']
        y = state['position']['y']
        heading = state['position']['heading']
        
        # Draw vehicle body
        self._draw_vehicle_body(ax, x, y, heading)
        
        # Draw motors with current angles
        motor_states = state['motors']
        self._draw_motors(ax, x, y, heading, motor_states)
        
        # Draw velocity vector
        velocity = state['velocity']
        self._draw_velocity_vector(ax, x, y, velocity)
        
        # Set view limits centered on vehicle
        margin = 10.0
        ax.set_xlim(x - margin, x + margin)
        ax.set_ylim(y - margin, y + margin)
        ax.set_aspect('equal')
        ax.grid(True, color=self.colors['grid'], alpha=0.3)
        ax.set_title('Vehicle Position & Orientation')
        ax.set_xlabel('X Position (m)')
        ax.set_ylabel('Y Position (m)')
        
        # Add state information as text
        info_text = f"Pos: ({x:.2f}, {y:.2f})\nHeading: {np.degrees(heading):.1f}°\n"
        info_text += f"Speed: {velocity['linear']:.2f} m/s\nAngular: {np.degrees(velocity['angular']):.1f}°/s"
        ax.text(0.02, 0.98, info_text, transform=ax.transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    def _draw_vehicle_body(self, ax, x: float, y: float, heading: float):
        """Draw the vehicle body."""
        # Vehicle corners in local frame
        corners = np.array([
            [-self.vehicle_length/2, -self.vehicle_width/2],
            [self.vehicle_length/2, -self.vehicle_width/2],
            [self.vehicle_length/2, self.vehicle_width/2],
            [-self.vehicle_length/2, self.vehicle_width/2]
        ])
        
        # Rotate and translate
        rotation_matrix = np.array([
            [np.cos(heading), -np.sin(heading)],
            [np.sin(heading), np.cos(heading)]
        ])
        
        rotated_corners = corners @ rotation_matrix.T
        rotated_corners[:, 0] += x
        rotated_corners[:, 1] += y
        
        # Draw vehicle body
        vehicle_patch = patches.Polygon(rotated_corners, closed=True, 
                                      facecolor=self.colors['vehicle_body'], 
                                      edgecolor='black', linewidth=2, alpha=0.7)
        ax.add_patch(vehicle_patch)
        
        # Draw front indicator (arrow)
        front_x = x + (self.vehicle_length/2 - 0.3) * np.cos(heading)
        front_y = y + (self.vehicle_length/2 - 0.3) * np.sin(heading)
        arrow_dx = 0.5 * np.cos(heading)
        arrow_dy = 0.5 * np.sin(heading)
        
        ax.arrow(front_x, front_y, arrow_dx, arrow_dy, 
                head_width=0.3, head_length=0.2, fc='red', ec='red')
    
    def _draw_motors(self, ax, x: float, y: float, heading: float, motor_states: Dict):
        """Draw motors with their current positions and angles."""
        # Motor positions in local frame
        front_pos = np.array([self.wheelbase/2, 0])
        rear_left_pos = np.array([-self.wheelbase/2, -self.track_width/2])
        rear_right_pos = np.array([-self.wheelbase/2, self.track_width/2])
        
        positions = {
            'front': front_pos,
            'rear_left': rear_left_pos,
            'rear_right': rear_right_pos
        }
        
        # Rotation matrix for vehicle orientation
        rotation_matrix = np.array([
            [np.cos(heading), -np.sin(heading)],
            [np.sin(heading), np.cos(heading)]
        ])
        
        for motor_name, local_pos in positions.items():
            # Transform to world coordinates
            world_pos = local_pos @ rotation_matrix.T
            motor_x = x + world_pos[0]
            motor_y = y + world_pos[1]
            
            # Get motor angles
            steering_angle = np.radians(motor_states.get(f'steering_{motor_name}', 0))
            drive_speed = motor_states.get(f'drive_{motor_name}', 0)
            
            # Draw motor base
            motor_circle = Circle((motor_x, motor_y), 0.2, 
                                facecolor=self.colors['motor_steering'], 
                                edgecolor='black', linewidth=1)
            ax.add_patch(motor_circle)
            
            # Draw steering direction
            total_angle = heading + steering_angle
            steer_dx = 0.4 * np.cos(total_angle)
            steer_dy = 0.4 * np.sin(total_angle)
            
            ax.arrow(motor_x, motor_y, steer_dx, steer_dy,
                    head_width=0.1, head_length=0.1, 
                    fc=self.colors['motor_drive'], ec=self.colors['motor_drive'],
                    linewidth=2)
            
            # Add motor labels
            label = f"{motor_name.replace('_', ' ').title()}\nS:{steering_angle*180/np.pi:.0f}° D:{drive_speed:.0f}%"
            ax.text(motor_x, motor_y - 0.5, label, ha='center', va='top', fontsize=8,
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))
    
    def _draw_velocity_vector(self, ax, x: float, y: float, velocity: Dict):
        """Draw velocity vector."""
        vx, vy = velocity['x'], velocity['y']
        magnitude = velocity['linear']
        
        if magnitude > 0.1:  # Only draw if moving
            # Scale vector for visibility
            scale = 2.0
            ax.arrow(x, y, vx * scale, vy * scale,
                    head_width=0.3, head_length=0.3, 
                    fc=self.colors['trajectory'], ec=self.colors['trajectory'],
                    linewidth=3, alpha=0.8)
            
            # Add velocity magnitude label
            ax.text(x + vx * scale + 0.5, y + vy * scale + 0.5, 
                   f"V: {magnitude:.1f} m/s", fontsize=10,
                   bbox=dict(boxstyle='round', facecolor=self.colors['trajectory'], alpha=0.8))
    
    def update_trajectory(self, state: Dict):
        """Update trajectory plot."""
        ax = self.axes['trajectory']
        
        # Add current position to trajectory
        self.trajectory_data['x'].append(state['position']['x'])
        self.trajectory_data['y'].append(state['position']['y'])
        
        # Limit data points
        if len(self.trajectory_data['x']) > self.max_data_points:
            self.trajectory_data['x'].pop(0)
            self.trajectory_data['y'].pop(0)
        
        # Clear and redraw
        ax.clear()
        if len(self.trajectory_data['x']) > 1:
            ax.plot(self.trajectory_data['x'], self.trajectory_data['y'], 
                   color=self.colors['trajectory'], linewidth=2, alpha=0.8)
            
            # Mark current position
            ax.plot(self.trajectory_data['x'][-1], self.trajectory_data['y'][-1], 
                   'ro', markersize=8, label='Current Position')
            
            # Mark start position
            ax.plot(self.trajectory_data['x'][0], self.trajectory_data['y'][0], 
                   'go', markersize=8, label='Start Position')
        
        ax.set_title('Vehicle Trajectory')
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.grid(True, color=self.colors['grid'], alpha=0.3)
        ax.legend()
        ax.set_aspect('equal')
    
    def update_performance_plots(self, state: Dict, current_time: float):
        """Update performance data plots."""
        # Add time point
        self.time_data.append(current_time)
        
        # Add velocity data
        self.performance_data['velocity'].append(state['velocity']['linear'])
        self.performance_data['acceleration'].append(state.get('acceleration', {}).get('linear', 0))
        
        # Add motor data
        motors = state['motors']
        self.performance_data['motor_angles']['front'].append(motors.get('steering_front', 0))
        self.performance_data['motor_angles']['rear_left'].append(motors.get('steering_rear_left', 0))
        self.performance_data['motor_angles']['rear_right'].append(motors.get('steering_rear_right', 0))
        
        self.performance_data['motor_speeds']['front'].append(motors.get('drive_front', 0))
        self.performance_data['motor_speeds']['rear_left'].append(motors.get('drive_rear_left', 0))
        self.performance_data['motor_speeds']['rear_right'].append(motors.get('drive_rear_right', 0))
        
        # Limit data points
        if len(self.time_data) > self.max_data_points:
            self.time_data.pop(0)
            self.performance_data['velocity'].pop(0)
            self.performance_data['acceleration'].pop(0)
            for motor in self.performance_data['motor_angles']:
                self.performance_data['motor_angles'][motor].pop(0)
            for motor in self.performance_data['motor_speeds']:
                self.performance_data['motor_speeds'][motor].pop(0)
        
        # Update velocity plot
        self._update_velocity_plot()
        
        # Update motor plots
        self._update_motor_plots()
    
    def _update_velocity_plot(self):
        """Update velocity plot."""
        ax = self.axes['velocity']
        ax.clear()
        
        if len(self.time_data) > 1:
            ax.plot(self.time_data, self.performance_data['velocity'], 
                   label='Linear Velocity', color='blue', linewidth=2)
            
            # Add acceleration on secondary axis
            ax2 = ax.twinx()
            ax2.plot(self.time_data, self.performance_data['acceleration'], 
                    label='Acceleration', color='red', linewidth=1, alpha=0.7)
            ax2.set_ylabel('Acceleration (m/s²)', color='red')
            ax2.tick_params(axis='y', labelcolor='red')
        
        ax.set_title('Velocity Profile')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Velocity (m/s)', color='blue')
        ax.grid(True, color=self.colors['grid'], alpha=0.3)
        ax.legend(loc='upper left')
    
    def _update_motor_plots(self):
        """Update motor angle and speed plots."""
        # Motor angles
        ax_angles = self.axes['motor_angles']
        ax_angles.clear()
        
        if len(self.time_data) > 1:
            ax_angles.plot(self.time_data, self.performance_data['motor_angles']['front'], 
                          label='Front', linewidth=2)
            ax_angles.plot(self.time_data, self.performance_data['motor_angles']['rear_left'], 
                          label='Rear Left', linewidth=2)
            ax_angles.plot(self.time_data, self.performance_data['motor_angles']['rear_right'], 
                          label='Rear Right', linewidth=2)
        
        ax_angles.set_title('Steering Angles')
        ax_angles.set_xlabel('Time (s)')
        ax_angles.set_ylabel('Angle (degrees)')
        ax_angles.grid(True, color=self.colors['grid'], alpha=0.3)
        ax_angles.legend()
        
        # Motor speeds
        ax_speeds = self.axes['motor_speeds']
        ax_speeds.clear()
        
        if len(self.time_data) > 1:
            ax_speeds.plot(self.time_data, self.performance_data['motor_speeds']['front'], 
                          label='Front', linewidth=2)
            ax_speeds.plot(self.time_data, self.performance_data['motor_speeds']['rear_left'], 
                          label='Rear Left', linewidth=2)
            ax_speeds.plot(self.time_data, self.performance_data['motor_speeds']['rear_right'], 
                          label='Rear Right', linewidth=2)
        
        ax_speeds.set_title('Drive Speeds')
        ax_speeds.set_xlabel('Time (s)')
        ax_speeds.set_ylabel('Speed (%)')
        ax_speeds.grid(True, color=self.colors['grid'], alpha=0.3)
        ax_speeds.legend()
    
    def clear_data(self):
        """Clear all stored visualization data."""
        self.time_data.clear()
        self.trajectory_data['x'].clear()
        self.trajectory_data['y'].clear()
        
        for key in self.performance_data:
            if isinstance(self.performance_data[key], list):
                self.performance_data[key].clear()
            elif isinstance(self.performance_data[key], dict):
                for subkey in self.performance_data[key]:
                    self.performance_data[key][subkey].clear()
    
    def save_plot(self, filename: str):
        """Save current plot to file."""
        if self.fig:
            self.fig.savefig(filename, dpi=300, bbox_inches='tight')
    
    def create_performance_report(self, filename: str):
        """Create a comprehensive performance report."""
        if not self.time_data:
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Vehicle Performance Report', fontsize=16, fontweight='bold')
        
        # Trajectory plot
        ax = axes[0, 0]
        ax.plot(self.trajectory_data['x'], self.trajectory_data['y'], 
               color=self.colors['trajectory'], linewidth=2)
        ax.set_title('Complete Trajectory')
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.grid(True)
        ax.set_aspect('equal')
        
        # Velocity analysis
        ax = axes[0, 1]
        velocities = self.performance_data['velocity']
        ax.plot(self.time_data, velocities, linewidth=2)
        ax.set_title(f'Velocity (Max: {max(velocities):.2f} m/s)')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Velocity (m/s)')
        ax.grid(True)
        
        # Motor usage
        ax = axes[1, 0]
        for motor in ['front', 'rear_left', 'rear_right']:
            angles = self.performance_data['motor_angles'][motor]
            ax.plot(self.time_data, angles, label=motor.replace('_', ' ').title(), linewidth=2)
        ax.set_title('Steering Angle Usage')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Angle (degrees)')
        ax.legend()
        ax.grid(True)
        
        # Speed distribution
        ax = axes[1, 1]
        ax.hist(velocities, bins=20, alpha=0.7, edgecolor='black')
        ax.set_title('Speed Distribution')
        ax.set_xlabel('Velocity (m/s)')
        ax.set_ylabel('Frequency')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close(fig)
