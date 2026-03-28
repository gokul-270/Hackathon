"""
Vehicle Control System - GUI Interface

Provides a comprehensive graphical user interface for vehicle simulation,
control, and monitoring using tkinter and matplotlib.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np
import threading
import time
from typing import Dict, List, Tuple, Optional
import json

# Import with fallback
try:
    from config.constants import MotorIDs, SystemConstants
except ImportError:
    # Create minimal constants for standalone operation
    class MotorIDs:
        STEERING_FRONT = 1
        STEERING_REAR_LEFT = 3
        STEERING_REAR_RIGHT = 5
        DRIVE_FRONT = 0
        DRIVE_REAR_LEFT = 2
        DRIVE_REAR_RIGHT = 4
    
    class SystemConstants:
        MAX_STEERING_ANGLE = 45.0

try:
    from vehicle_simulator import VehicleSimulator
    from physics_engine import VehiclePhysics
except ImportError:
    try:
        from .vehicle_simulator import VehicleSimulator
        from .physics_engine import VehiclePhysics
    except ImportError:
        VehicleSimulator = None
        VehiclePhysics = None


class SimulationGUI:
    """
    Main GUI interface for vehicle control simulation.
    
    Features:
    - Real-time vehicle visualization
    - Motor control panels
    - System status monitoring
    - Configuration management
    - Data logging and playback
    """
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Vehicle Control System Simulator v2.1.0")
        self.root.geometry("1400x900")
        self.root.configure(bg='#2c3e50')
        
        # Initialize simulation components
        self.simulator = VehicleSimulator()
        self.physics = VehiclePhysics()
        
        # Simulation state
        self.is_running = False
        self.simulation_thread = None
        self.update_rate = 50  # Hz
        
        # Data storage for plotting
        self.time_data = []
        self.position_data = {'x': [], 'y': []}
        self.velocity_data = {'linear': [], 'angular': []}
        self.motor_data = {
            'steering_front': [],
            'steering_rear_left': [],
            'steering_rear_right': [],
            'drive_front': [],
            'drive_rear_left': [],
            'drive_rear_right': []
        }
        
        self.setup_ui()
        self.setup_plots()
        
    def setup_ui(self):
        """Setup the main UI components."""
        # Create main frames
        self.create_menu()
        self.create_control_panel()
        self.create_visualization_panel()
        self.create_status_panel()
        
    def create_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Configuration", command=self.save_config)
        file_menu.add_command(label="Load Configuration", command=self.load_config)
        file_menu.add_separator()
        file_menu.add_command(label="Export Data", command=self.export_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Simulation menu
        sim_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Simulation", menu=sim_menu)
        sim_menu.add_command(label="Start", command=self.start_simulation)
        sim_menu.add_command(label="Stop", command=self.stop_simulation)
        sim_menu.add_command(label="Reset", command=self.reset_simulation)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
    def create_control_panel(self):
        """Create vehicle control panel."""
        control_frame = ttk.LabelFrame(self.root, text="Vehicle Control", padding="10")
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Simulation controls
        sim_frame = ttk.LabelFrame(control_frame, text="Simulation", padding="5")
        sim_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.start_btn = ttk.Button(sim_frame, text="Start", command=self.start_simulation)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        
        self.stop_btn = ttk.Button(sim_frame, text="Stop", command=self.stop_simulation, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        
        self.reset_btn = ttk.Button(sim_frame, text="Reset", command=self.reset_simulation)
        self.reset_btn.pack(side=tk.LEFT, padx=2)
        
        # Motor control sections
        self.create_motor_controls(control_frame)
        
        # Vehicle parameters
        self.create_vehicle_params(control_frame)
        
    def create_motor_controls(self, parent):
        """Create motor control interfaces."""
        # Steering motors
        steering_frame = ttk.LabelFrame(parent, text="Steering Motors", padding="5")
        steering_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.steering_controls = {}
        
        # Front steering
        front_frame = ttk.Frame(steering_frame)
        front_frame.pack(fill=tk.X, pady=2)
        ttk.Label(front_frame, text="Front:").pack(side=tk.LEFT)
        self.steering_controls['front'] = tk.Scale(
            front_frame, from_=-45, to=45, orient=tk.HORIZONTAL,
            command=lambda v: self.update_motor_command('steering_front', float(v))
        )
        self.steering_controls['front'].pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # Rear left steering
        rear_left_frame = ttk.Frame(steering_frame)
        rear_left_frame.pack(fill=tk.X, pady=2)
        ttk.Label(rear_left_frame, text="Rear Left:").pack(side=tk.LEFT)
        self.steering_controls['rear_left'] = tk.Scale(
            rear_left_frame, from_=-45, to=45, orient=tk.HORIZONTAL,
            command=lambda v: self.update_motor_command('steering_rear_left', float(v))
        )
        self.steering_controls['rear_left'].pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # Rear right steering
        rear_right_frame = ttk.Frame(steering_frame)
        rear_right_frame.pack(fill=tk.X, pady=2)
        ttk.Label(rear_right_frame, text="Rear Right:").pack(side=tk.LEFT)
        self.steering_controls['rear_right'] = tk.Scale(
            rear_right_frame, from_=-45, to=45, orient=tk.HORIZONTAL,
            command=lambda v: self.update_motor_command('steering_rear_right', float(v))
        )
        self.steering_controls['rear_right'].pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # Drive motors
        drive_frame = ttk.LabelFrame(parent, text="Drive Motors", padding="5")
        drive_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.drive_controls = {}
        
        # Front drive
        front_drive_frame = ttk.Frame(drive_frame)
        front_drive_frame.pack(fill=tk.X, pady=2)
        ttk.Label(front_drive_frame, text="Front:").pack(side=tk.LEFT)
        self.drive_controls['front'] = tk.Scale(
            front_drive_frame, from_=-100, to=100, orient=tk.HORIZONTAL,
            command=lambda v: self.update_motor_command('drive_front', float(v))
        )
        self.drive_controls['front'].pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # Rear left drive
        rear_left_drive_frame = ttk.Frame(drive_frame)
        rear_left_drive_frame.pack(fill=tk.X, pady=2)
        ttk.Label(rear_left_drive_frame, text="Rear Left:").pack(side=tk.LEFT)
        self.drive_controls['rear_left'] = tk.Scale(
            rear_left_drive_frame, from_=-100, to=100, orient=tk.HORIZONTAL,
            command=lambda v: self.update_motor_command('drive_rear_left', float(v))
        )
        self.drive_controls['rear_left'].pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        # Rear right drive
        rear_right_drive_frame = ttk.Frame(drive_frame)
        rear_right_drive_frame.pack(fill=tk.X, pady=2)
        ttk.Label(rear_right_drive_frame, text="Rear Right:").pack(side=tk.LEFT)
        self.drive_controls['rear_right'] = tk.Scale(
            rear_right_drive_frame, from_=-100, to=100, orient=tk.HORIZONTAL,
            command=lambda v: self.update_motor_command('drive_rear_right', float(v))
        )
        self.drive_controls['rear_right'].pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
    def create_vehicle_params(self, parent):
        """Create vehicle parameter controls."""
        params_frame = ttk.LabelFrame(parent, text="Vehicle Parameters", padding="5")
        params_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Mass
        mass_frame = ttk.Frame(params_frame)
        mass_frame.pack(fill=tk.X, pady=2)
        ttk.Label(mass_frame, text="Mass (kg):").pack(side=tk.LEFT)
        self.mass_var = tk.StringVar(value="1000")
        mass_entry = ttk.Entry(mass_frame, textvariable=self.mass_var, width=10)
        mass_entry.pack(side=tk.RIGHT)
        
        # Wheelbase
        wheelbase_frame = ttk.Frame(params_frame)
        wheelbase_frame.pack(fill=tk.X, pady=2)
        ttk.Label(wheelbase_frame, text="Wheelbase (m):").pack(side=tk.LEFT)
        self.wheelbase_var = tk.StringVar(value="2.5")
        wheelbase_entry = ttk.Entry(wheelbase_frame, textvariable=self.wheelbase_var, width=10)
        wheelbase_entry.pack(side=tk.RIGHT)
        
        # Track width
        track_frame = ttk.Frame(params_frame)
        track_frame.pack(fill=tk.X, pady=2)
        ttk.Label(track_frame, text="Track Width (m):").pack(side=tk.LEFT)
        self.track_var = tk.StringVar(value="1.8")
        track_entry = ttk.Entry(track_frame, textvariable=self.track_var, width=10)
        track_entry.pack(side=tk.RIGHT)
        
        # Update button
        ttk.Button(params_frame, text="Update Parameters", 
                  command=self.update_vehicle_params).pack(pady=5)
        
    def create_visualization_panel(self):
        """Create the main visualization panel."""
        viz_frame = ttk.LabelFrame(self.root, text="Vehicle Visualization", padding="5")
        viz_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create notebook for different views
        self.notebook = ttk.Notebook(viz_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Vehicle view tab
        self.vehicle_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.vehicle_frame, text="Vehicle View")
        
        # Data plots tab
        self.plots_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.plots_frame, text="Data Plots")
        
    def setup_plots(self):
        """Setup matplotlib plots."""
        # Vehicle visualization plot
        self.vehicle_fig = Figure(figsize=(8, 6), dpi=100)
        self.vehicle_ax = self.vehicle_fig.add_subplot(111)
        self.vehicle_ax.set_xlim(-10, 10)
        self.vehicle_ax.set_ylim(-10, 10)
        self.vehicle_ax.set_aspect('equal')
        self.vehicle_ax.grid(True)
        self.vehicle_ax.set_title("Vehicle Position and Orientation")
        
        self.vehicle_canvas = FigureCanvasTkAgg(self.vehicle_fig, self.vehicle_frame)
        self.vehicle_canvas.draw()
        self.vehicle_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Data plots
        self.data_fig = Figure(figsize=(8, 6), dpi=100)
        
        # Position plot
        self.pos_ax = self.data_fig.add_subplot(221)
        self.pos_ax.set_title("Position")
        self.pos_ax.set_xlabel("Time (s)")
        self.pos_ax.set_ylabel("Position (m)")
        
        # Velocity plot
        self.vel_ax = self.data_fig.add_subplot(222)
        self.vel_ax.set_title("Velocity")
        self.vel_ax.set_xlabel("Time (s)")
        self.vel_ax.set_ylabel("Velocity (m/s)")
        
        # Motor angles plot
        self.motor_ax = self.data_fig.add_subplot(223)
        self.motor_ax.set_title("Motor Angles")
        self.motor_ax.set_xlabel("Time (s)")
        self.motor_ax.set_ylabel("Angle (degrees)")
        
        # Motor speeds plot
        self.speed_ax = self.data_fig.add_subplot(224)
        self.speed_ax.set_title("Motor Speeds")
        self.speed_ax.set_xlabel("Time (s)")
        self.speed_ax.set_ylabel("Speed (%)")
        
        self.data_fig.tight_layout()
        
        self.data_canvas = FigureCanvasTkAgg(self.data_fig, self.plots_frame)
        self.data_canvas.draw()
        self.data_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
    def create_status_panel(self):
        """Create status and information panel."""
        status_frame = ttk.LabelFrame(self.root, text="System Status", padding="5")
        status_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        
        # Status text
        self.status_text = tk.Text(status_frame, width=30, height=10, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)
        
        # Current values display
        values_frame = ttk.LabelFrame(status_frame, text="Current Values", padding="5")
        values_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_labels = {}
        status_items = [
            ("Position X:", "pos_x"),
            ("Position Y:", "pos_y"),
            ("Heading:", "heading"),
            ("Linear Vel:", "linear_vel"),
            ("Angular Vel:", "angular_vel"),
            ("Simulation Time:", "sim_time"),
        ]
        
        for i, (label, key) in enumerate(status_items):
            frame = ttk.Frame(values_frame)
            frame.pack(fill=tk.X, pady=1)
            ttk.Label(frame, text=label).pack(side=tk.LEFT)
            self.status_labels[key] = ttk.Label(frame, text="0.00")
            self.status_labels[key].pack(side=tk.RIGHT)
        
    def update_motor_command(self, motor_name: str, value: float):
        """Update motor command value."""
        if self.simulator:
            self.simulator.set_motor_command(motor_name, value)
            self.log_status(f"Motor {motor_name}: {value:.2f}")
    
    def update_vehicle_params(self):
        """Update vehicle physics parameters."""
        try:
            mass = float(self.mass_var.get())
            wheelbase = float(self.wheelbase_var.get())
            track_width = float(self.track_var.get())
            
            self.physics.update_parameters(mass=mass, wheelbase=wheelbase, track_width=track_width)
            self.log_status(f"Updated vehicle parameters: Mass={mass}kg, Wheelbase={wheelbase}m, Track={track_width}m")
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid parameter values: {e}")
    
    def start_simulation(self):
        """Start the simulation."""
        if not self.is_running:
            self.is_running = True
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            
            self.simulation_thread = threading.Thread(target=self.simulation_loop, daemon=True)
            self.simulation_thread.start()
            
            self.log_status("Simulation started")
    
    def stop_simulation(self):
        """Stop the simulation."""
        if self.is_running:
            self.is_running = False
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.log_status("Simulation stopped")
    
    def reset_simulation(self):
        """Reset the simulation."""
        was_running = self.is_running
        if was_running:
            self.stop_simulation()
            time.sleep(0.1)  # Wait for simulation thread to stop
        
        # Reset simulator
        self.simulator.reset()
        self.physics.reset()
        
        # Clear data
        self.time_data.clear()
        for key in self.position_data:
            self.position_data[key].clear()
        for key in self.velocity_data:
            self.velocity_data[key].clear()
        for key in self.motor_data:
            self.motor_data[key].clear()
        
        # Reset controls
        for control in self.steering_controls.values():
            control.set(0)
        for control in self.drive_controls.values():
            control.set(0)
        
        # Clear plots
        self.vehicle_ax.clear()
        self.vehicle_ax.set_xlim(-10, 10)
        self.vehicle_ax.set_ylim(-10, 10)
        self.vehicle_ax.set_aspect('equal')
        self.vehicle_ax.grid(True)
        self.vehicle_ax.set_title("Vehicle Position and Orientation")
        self.vehicle_canvas.draw()
        
        self.log_status("Simulation reset")
        
        if was_running:
            self.start_simulation()
    
    def simulation_loop(self):
        """Main simulation loop."""
        dt = 1.0 / self.update_rate
        
        while self.is_running:
            start_time = time.time()
            
            # Update physics
            state = self.simulator.update(dt)
            
            # Collect data
            current_time = len(self.time_data) * dt
            self.time_data.append(current_time)
            self.position_data['x'].append(state['position']['x'])
            self.position_data['y'].append(state['position']['y'])
            self.velocity_data['linear'].append(state['velocity']['linear'])
            self.velocity_data['angular'].append(state['velocity']['angular'])
            
            # Update motor data
            for motor in self.motor_data:
                self.motor_data[motor].append(state['motors'].get(motor, 0))
            
            # Update GUI (thread-safe)
            self.root.after_idle(self.update_gui, state)
            
            # Control loop timing
            elapsed = time.time() - start_time
            sleep_time = max(0, dt - elapsed)
            time.sleep(sleep_time)
    
    def update_gui(self, state: Dict):
        """Update GUI elements with current state."""
        # Update status labels
        self.status_labels['pos_x'].config(text=f"{state['position']['x']:.2f} m")
        self.status_labels['pos_y'].config(text=f"{state['position']['y']:.2f} m")
        self.status_labels['heading'].config(text=f"{np.degrees(state['position']['heading']):.1f}°")
        self.status_labels['linear_vel'].config(text=f"{state['velocity']['linear']:.2f} m/s")
        self.status_labels['angular_vel'].config(text=f"{np.degrees(state['velocity']['angular']):.2f}°/s")
        self.status_labels['sim_time'].config(text=f"{len(self.time_data) / self.update_rate:.2f} s")
        
        # Update vehicle visualization
        self.update_vehicle_plot(state)
        
        # Update data plots (every 10 updates to avoid overload)
        if len(self.time_data) % 10 == 0:
            self.update_data_plots()
    
    def update_vehicle_plot(self, state: Dict):
        """Update the vehicle visualization plot."""
        self.vehicle_ax.clear()
        
        x, y = state['position']['x'], state['position']['y']
        heading = state['position']['heading']
        
        # Draw vehicle body
        length, width = 3.0, 1.8
        corners = np.array([
            [-length/2, -width/2],
            [length/2, -width/2],
            [length/2, width/2],
            [-length/2, width/2],
            [-length/2, -width/2]
        ])
        
        # Rotate and translate
        rotation_matrix = np.array([
            [np.cos(heading), -np.sin(heading)],
            [np.sin(heading), np.cos(heading)]
        ])
        rotated_corners = corners @ rotation_matrix.T
        rotated_corners[:, 0] += x
        rotated_corners[:, 1] += y
        
        self.vehicle_ax.plot(rotated_corners[:, 0], rotated_corners[:, 1], 'b-', linewidth=2)
        
        # Draw direction arrow
        arrow_length = 2.0
        arrow_end_x = x + arrow_length * np.cos(heading)
        arrow_end_y = y + arrow_length * np.sin(heading)
        self.vehicle_ax.arrow(x, y, arrow_end_x - x, arrow_end_y - y,
                            head_width=0.3, head_length=0.3, fc='red', ec='red')
        
        # Draw trajectory
        if len(self.position_data['x']) > 1:
            self.vehicle_ax.plot(self.position_data['x'], self.position_data['y'], 'g--', alpha=0.5)
        
        # Set limits and labels
        self.vehicle_ax.set_xlim(x - 15, x + 15)
        self.vehicle_ax.set_ylim(y - 15, y + 15)
        self.vehicle_ax.set_aspect('equal')
        self.vehicle_ax.grid(True)
        self.vehicle_ax.set_title("Vehicle Position and Orientation")
        self.vehicle_ax.set_xlabel("X Position (m)")
        self.vehicle_ax.set_ylabel("Y Position (m)")
        
        self.vehicle_canvas.draw_idle()
    
    def update_data_plots(self):
        """Update the data plots."""
        if len(self.time_data) < 2:
            return
        
        # Position plot
        self.pos_ax.clear()
        self.pos_ax.plot(self.time_data, self.position_data['x'], label='X')
        self.pos_ax.plot(self.time_data, self.position_data['y'], label='Y')
        self.pos_ax.set_title("Position")
        self.pos_ax.set_xlabel("Time (s)")
        self.pos_ax.set_ylabel("Position (m)")
        self.pos_ax.legend()
        self.pos_ax.grid(True)
        
        # Velocity plot
        self.vel_ax.clear()
        self.vel_ax.plot(self.time_data, self.velocity_data['linear'], label='Linear')
        angular_deg = [np.degrees(v) for v in self.velocity_data['angular']]
        self.vel_ax.plot(self.time_data, angular_deg, label='Angular (°/s)')
        self.vel_ax.set_title("Velocity")
        self.vel_ax.set_xlabel("Time (s)")
        self.vel_ax.set_ylabel("Velocity")
        self.vel_ax.legend()
        self.vel_ax.grid(True)
        
        # Motor angles plot
        self.motor_ax.clear()
        steering_motors = ['steering_front', 'steering_rear_left', 'steering_rear_right']
        for motor in steering_motors:
            if motor in self.motor_data:
                self.motor_ax.plot(self.time_data, self.motor_data[motor], label=motor.replace('_', ' ').title())
        self.motor_ax.set_title("Steering Angles")
        self.motor_ax.set_xlabel("Time (s)")
        self.motor_ax.set_ylabel("Angle (degrees)")
        self.motor_ax.legend()
        self.motor_ax.grid(True)
        
        # Motor speeds plot
        self.speed_ax.clear()
        drive_motors = ['drive_front', 'drive_rear_left', 'drive_rear_right']
        for motor in drive_motors:
            if motor in self.motor_data:
                self.speed_ax.plot(self.time_data, self.motor_data[motor], label=motor.replace('_', ' ').title())
        self.speed_ax.set_title("Drive Speeds")
        self.speed_ax.set_xlabel("Time (s)")
        self.speed_ax.set_ylabel("Speed (%)")
        self.speed_ax.legend()
        self.speed_ax.grid(True)
        
        self.data_fig.tight_layout()
        self.data_canvas.draw_idle()
    
    def log_status(self, message: str):
        """Log a status message."""
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
    
    def save_config(self):
        """Save current configuration."""
        config = {
            'vehicle_params': {
                'mass': self.mass_var.get(),
                'wheelbase': self.wheelbase_var.get(),
                'track_width': self.track_var.get()
            },
            'motor_commands': {
                'steering': {
                    'front': self.steering_controls['front'].get(),
                    'rear_left': self.steering_controls['rear_left'].get(),
                    'rear_right': self.steering_controls['rear_right'].get()
                },
                'drive': {
                    'front': self.drive_controls['front'].get(),
                    'rear_left': self.drive_controls['rear_left'].get(),
                    'rear_right': self.drive_controls['rear_right'].get()
                }
            }
        }
        
        filename = tk.filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        
        if filename:
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
            self.log_status(f"Configuration saved to {filename}")
    
    def load_config(self):
        """Load configuration."""
        filename = tk.filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    config = json.load(f)
                
                # Load vehicle params
                if 'vehicle_params' in config:
                    params = config['vehicle_params']
                    self.mass_var.set(params.get('mass', '1000'))
                    self.wheelbase_var.set(params.get('wheelbase', '2.5'))
                    self.track_var.set(params.get('track_width', '1.8'))
                    self.update_vehicle_params()
                
                # Load motor commands
                if 'motor_commands' in config:
                    commands = config['motor_commands']
                    if 'steering' in commands:
                        steering = commands['steering']
                        self.steering_controls['front'].set(steering.get('front', 0))
                        self.steering_controls['rear_left'].set(steering.get('rear_left', 0))
                        self.steering_controls['rear_right'].set(steering.get('rear_right', 0))
                    
                    if 'drive' in commands:
                        drive = commands['drive']
                        self.drive_controls['front'].set(drive.get('front', 0))
                        self.drive_controls['rear_left'].set(drive.get('rear_left', 0))
                        self.drive_controls['rear_right'].set(drive.get('rear_right', 0))
                
                self.log_status(f"Configuration loaded from {filename}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load configuration: {e}")
    
    def export_data(self):
        """Export simulation data."""
        if not self.time_data:
            messagebox.showwarning("Warning", "No data to export")
            return
        
        filename = tk.filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        
        if filename:
            import csv
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Header
                header = ['Time', 'Pos_X', 'Pos_Y', 'Linear_Vel', 'Angular_Vel']
                header.extend([f'Motor_{name}' for name in self.motor_data.keys()])
                writer.writerow(header)
                
                # Data
                for i in range(len(self.time_data)):
                    row = [
                        self.time_data[i],
                        self.position_data['x'][i],
                        self.position_data['y'][i],
                        self.velocity_data['linear'][i],
                        self.velocity_data['angular'][i]
                    ]
                    for motor_data in self.motor_data.values():
                        row.append(motor_data[i] if i < len(motor_data) else 0)
                    writer.writerow(row)
            
            self.log_status(f"Data exported to {filename}")
    
    def show_about(self):
        """Show about dialog."""
        about_text = """
Vehicle Control System Simulator v2.1.0

A comprehensive simulation environment for testing
and visualizing vehicle control algorithms.

Features:
• Real-time vehicle physics simulation
• Interactive motor control
• Data visualization and logging
• Configuration management

Developed by: Vehicle Control Development Team
        """
        messagebox.showinfo("About", about_text)
    
    def run(self):
        """Start the GUI application."""
        self.log_status("Vehicle Control System Simulator initialized")
        self.log_status("Ready for simulation")
        self.root.mainloop()


if __name__ == "__main__":
    app = SimulationGUI()
    app.run()
