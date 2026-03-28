# Examples - Pragati ROS2

Code examples demonstrating usage of Pragati ROS2 packages.

## Overview

| Example | Purpose | Prerequisites |
|---------|---------|---------------|
| [motor_control_example.py](#motor-control) | Basic motor operations | motor_control_ros2 running |
| [cotton_detection_example.py](#cotton-detection) | Detection workflow | cotton_detection_ros2 running |
| [integrated_picking_example.py](#integrated-picking) | End-to-end picking | All nodes running |

---

## Motor Control

**File:** `motor_control_example.py`

Demonstrates:
- Publishing joint commands
- Reading joint states
- Waiting for position targets
- Monitoring diagnostics
- Smooth trajectory generation

**Run:**
```bash
# Terminal 1: Start motor control
ros2 launch motor_control_ros2 mg6010_test_node.launch.py

# Terminal 2: Run example
python3 examples/motor_control_example.py
```

**Features:**
- Example 1: Single position command
- Example 2: Movement sequence (waypoints)
- Example 3: Smooth sinusoidal motion

---

## Cotton Detection

**File:** `cotton_detection_example.py`

Demonstrates:
- Starting/stopping detection
- Subscribing to detection results
- Sequential cotton processing
- Service-based workflow

**Run:**
```bash
# Terminal 1: Start detection (offline mode)
ros2 launch cotton_detection_ros2 offline_detection.launch.py

# Terminal 2: Run example
python3 examples/cotton_detection_example.py
```

**Features:**
- Example 1: Start detection and get first target
- Example 2: Sequential picking workflow
- Example 3: Continuous monitoring

---

## Integrated Picking

**File:** `integrated_picking_example.py`

Demonstrates:
- Complete cotton picking workflow
- Detection → IK → Movement → Pick
- Multi-cotton sequential processing
- Statistics tracking

**Run:**
```bash
# Terminal 1: Start all nodes
ros2 launch [your_main_launch_file].launch.py

# Terminal 2: Run example
python3 examples/integrated_picking_example.py
```

**Features:**
- Full pick-place cycle
- Simplified inverse kinematics
- Vacuum control integration
- Success rate tracking

---

## Installation

No additional installation needed if ROS2 workspace is sourced.

```bash
# Source workspace
source install/setup.bash

# Make examples executable
chmod +x examples/*.py
```

---

## Customization

### Adjust Joint Count

Examples assume 3-joint arms. Modify for your configuration:

```python
# Example: 4-joint arm
target = [0.0, 0.5, -0.5, 0.2]
```

### Change Topic Names

Update topic names to match your setup:

```python
# In motor_control_example.py
self.cmd_pub = self.create_publisher(
    Float64MultiArray,
    '/your_custom_topic',  # Change this
    10
)
```

### Tune Parameters

Adjust tolerances and timeouts:

```python
# Position tolerance
tolerance = 0.05  # radians (default)
tolerance = 0.01  # tighter tolerance

# Timeout duration
timeout = 10.0  # seconds (default)
timeout = 5.0   # shorter timeout
```

---

## Troubleshooting

### "Service not available"

**Issue:** Service clients timeout

**Solution:**
```bash
# Check services are advertised
ros2 service list

# Verify node is running
ros2 node list
```

---

### "Topic not updating"

**Issue:** No messages received on subscribed topic

**Solution:**
```bash
# Check topic exists and publishes
ros2 topic list
ros2 topic hz /joint_states

# Check topic type matches
ros2 topic info /joint_states
```

---

### "Module not found"

**Issue:** Python import errors

**Solution:**
```bash
# Ensure ROS2 workspace sourced
source install/setup.bash

# Install Python dependencies
pip3 install rclpy
```

---

## Related Documentation

- **Motor Control:** [src/motor_control_ros2/README.md](../src/motor_control_ros2/README.md)
- **Cotton Detection:** [src/cotton_detection_ros2/README.md](../src/cotton_detection_ros2/README.md)
- **Yanthra Move:** [src/yanthra_move/README.md](../src/yanthra_move/README.md)
- **Troubleshooting:** [docs/guides/TROUBLESHOOTING.md](../docs/guides/TROUBLESHOOTING.md)
- **Motor Tuning:** [docs/guides/MOTOR_TUNING_GUIDE.md](../docs/guides/MOTOR_TUNING_GUIDE.md)

---

## Contributing

To add new examples:

1. Follow existing naming pattern: `<package>_example.py`
2. Include comprehensive docstring
3. Add error handling
4. Update this README
5. Test in simulation first

---

**Last Updated:** 2025-10-15  
**Status:** Active - Simulation Validated
