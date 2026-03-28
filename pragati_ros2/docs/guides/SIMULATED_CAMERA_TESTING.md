# Simulated Camera Testing Guide

**Purpose:** Test yanthra arm node with simulated cotton detection data (no camera required)  
**Date:** December 10, 2025  
**Status:** Ready for use

---

## Overview

This guide shows you how to trigger simulated cotton detection results to test the yanthra_move arm node without needing actual camera hardware. This is useful for:

- **Development testing** - Validate arm motion logic without camera
- **Integration testing** - Test the detection → motion pipeline
- **Regression testing** - Verify changes don't break the workflow
- **Debugging** - Isolate arm behavior from camera issues

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Camera Detection Flow (Normal Operation)       │
├─────────────────────────────────────────────────┤
│                                                  │
│  OAK-D Camera                                   │
│       │                                          │
│       ▼                                          │
│  cotton_detection_ros2 (C++ Node)              │
│       │                                          │
│       │ publishes                                │
│       ▼                                          │
│  /cotton_detection/results                      │
│       │ (DetectionResult msg)                   │
│       ▼                                          │
│  yanthra_move (subscribes)                      │
│       │                                          │
│       ▼                                          │
│  MotionController → Arm Movement                │
│                                                  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Simulated Testing Flow (This Guide)            │
├─────────────────────────────────────────────────┤
│                                                  │
│  test_cotton_detection_publisher.py             │
│       │ (Python test script)                    │
│       │                                          │
│       │ publishes                                │
│       ▼                                          │
│  /cotton_detection/results                      │
│       │ (DetectionResult msg)                   │
│       ▼                                          │
│  yanthra_move (subscribes)                      │
│       │                                          │
│       ▼                                          │
│  MotionController → Arm Movement                │
│                                                  │
└─────────────────────────────────────────────────┘
```

**Key Point:** The yanthra node subscribes to `/cotton_detection/results` topic. It doesn't care if the data comes from a real camera or a test script - same interface!

---

## Message Format

### DetectionResult Message

```
# File: cotton_detection_ros2/msg/DetectionResult.msg

std_msgs/Header header           # Timestamp and frame_id
CottonPosition[] positions       # Array of detected cotton positions
int32 total_count               # Number of detections
bool detection_successful       # True if detection ran successfully
float32 processing_time_ms      # Processing time (ms)
```

### CottonPosition Message

```
# File: cotton_detection_ros2/msg/CottonPosition.msg

geometry_msgs/Point position    # x, y, z in meters (camera frame)
float32 confidence             # Detection confidence (0.0 to 1.0)
```

---

## Quick Start - Test Publisher

### Method 1: Single Detection (Default)

Publishes 3 test cotton positions once and exits:

```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash

# Publish single detection with 3 cotton positions
python3 scripts/testing/test_cotton_detection_publisher.py --single
```

**Expected Output:**
```
🌱 Cotton Detection Test Publisher initialized
   Publishing to: /cotton_detection/results
🎯 Publishing single detection with 3 positions
📤 Published detection with 3 cotton position(s):
   Cotton[0]: (0.300, 0.100, 0.500)
   Cotton[1]: (0.250, -0.050, 0.450)
   Cotton[2]: (0.350, 0.000, 0.550)
✅ Publisher shutdown complete
```

---

### Method 2: Continuous Publishing

Publishes detections repeatedly at 2 Hz (useful for continuous testing):

```bash
# Publish continuously at 2 Hz
python3 scripts/testing/test_cotton_detection_publisher.py --continuous

# Custom rate (e.g., 5 Hz)
python3 scripts/testing/test_cotton_detection_publisher.py --continuous --rate 5.0

# Stop with Ctrl+C
```

**Expected Output:**
```
🔄 Starting continuous publishing at 2.0 Hz
   Press Ctrl+C to stop
📤 Published detection with 3 cotton position(s):
   Cotton[0]: (0.300, 0.100, 0.500)
   ...
📤 Published detection with 3 cotton position(s):
   ...
```

---

### Method 3: Custom Position

Publish a single custom position for precise testing:

```bash
# Publish custom position: x=0.4m, y=0.15m, z=0.6m
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.4 0.15 0.6
```

---

### Method 4: Variable Cotton Count

Control how many cotton positions to publish:

```bash
# Publish 1 cotton position
python3 scripts/testing/test_cotton_detection_publisher.py --single --count 1

# Publish 5 cotton positions (repeats predefined positions)
python3 scripts/testing/test_cotton_detection_publisher.py --single --count 5
```

---

## Complete Testing Workflow

### Test 1: Basic Integration Test

Verify yanthra_move receives and processes simulated detections:

```bash
# Terminal 1: Launch yanthra_move in simulation mode
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true

# Terminal 2: Monitor yanthra_move logs
ros2 topic echo /yanthra_move/status

# Terminal 3: Publish test detection
python3 scripts/testing/test_cotton_detection_publisher.py --single
```

**What to Check:**
- ✅ yanthra_move logs: "🌱 Received cotton detection: 3 positions"
- ✅ yanthra_move processes positions in MotionController
- ✅ Arm attempts to move to positions (or logs if motors unavailable)

---

### Test 2: Continuous Operation Test

Simulate continuous cotton detection (like field operation):

```bash
# Terminal 1: Launch yanthra_move
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true

# Terminal 2: Monitor detection reception rate
ros2 topic hz /cotton_detection/results
ros2 topic echo /cotton_detection/results --field total_count

# Terminal 3: Start continuous publisher
python3 scripts/testing/test_cotton_detection_publisher.py --continuous --rate 1.0
```

**What to Check:**
- ✅ Detection rate: ~1 Hz as specified
- ✅ yanthra_move buffers positions correctly
- ✅ No memory leaks or performance degradation over time

---

### Test 3: Edge Cases Testing

Test system behavior with unusual inputs:

```bash
# Test: Zero detections (empty array)
python3 -c "
import rclpy
from rclpy.node import Node
from cotton_detection_ros2.msg import DetectionResult
from std_msgs.msg import Header

rclpy.init()
node = Node('test')
pub = node.create_publisher(DetectionResult, '/cotton_detection/results', 10)

msg = DetectionResult()
msg.header = Header()
msg.header.stamp = node.get_clock().now().to_msg()
msg.header.frame_id = 'camera_link'
msg.positions = []
msg.total_count = 0
msg.detection_successful = True
msg.processing_time_ms = 1.0

pub.publish(msg)
print('Published: 0 detections')
"

# Test: Single cotton very close
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.15 0.0 0.3

# Test: Single cotton far away
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.6 0.0 0.7

# Test: Cotton at extreme angles
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.3 0.3 0.5  # Far right
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.3 -0.3 0.5  # Far left
```

**What to Check:**
- ✅ System handles zero detections gracefully (no crash)
- ✅ Out-of-reach positions logged and skipped
- ✅ Inverse kinematics validates positions before motion

---

### Test 4: Latency and Timing Test

Measure time from detection publication to arm response:

```bash
# Terminal 1: Launch yanthra with debug logging
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true \
  --log-level yanthra_move_system:=debug

# Terminal 2: Publish and timestamp
python3 -c "
import time
import rclpy
from rclpy.node import Node
from cotton_detection_ros2.msg import DetectionResult, CottonPosition
from geometry_msgs.msg import Point
from std_msgs.msg import Header

rclpy.init()
node = Node('latency_test')
pub = node.create_publisher(DetectionResult, '/cotton_detection/results', 10)
time.sleep(1)

msg = DetectionResult()
msg.header = Header()
msg.header.stamp = node.get_clock().now().to_msg()
msg.header.frame_id = 'camera_link'

pos = CottonPosition()
pos.position = Point(x=0.3, y=0.0, z=0.5)
pos.confidence = 0.95
msg.positions.append(pos)

msg.total_count = 1
msg.detection_successful = True
msg.processing_time_ms = 2.0

start = time.time()
pub.publish(msg)
print(f'Published at: {start:.6f}')
print('Check yanthra logs for reception timestamp')
"
```

**What to Check:**
- ✅ Latency < 100ms from publish to yanthra reception
- ✅ Debug logs show timestamps for profiling

---

## Advanced Testing

### Custom Python Script Template

Create your own test patterns:

```python
#!/usr/bin/env python3
"""Custom cotton detection test pattern"""

import rclpy
from rclpy.node import Node
from cotton_detection_ros2.msg import DetectionResult, CottonPosition
from geometry_msgs.msg import Point
from std_msgs.msg import Header
import time
import math

class CustomPatternPublisher(Node):
    def __init__(self):
        super().__init__('custom_pattern_publisher')
        self.publisher = self.create_publisher(
            DetectionResult,
            '/cotton_detection/results',
            10
        )
        
    def publish_circular_pattern(self, radius=0.3, count=8, height=0.5):
        """Publish cotton in circular pattern around center"""
        msg = DetectionResult()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_link'
        
        for i in range(count):
            angle = (2 * math.pi * i) / count
            pos = CottonPosition()
            pos.position = Point(
                x=0.3,  # Fixed distance forward
                y=radius * math.cos(angle),
                z=height + radius * math.sin(angle)
            )
            pos.confidence = 0.95
            msg.positions.append(pos)
        
        msg.total_count = len(msg.positions)
        msg.detection_successful = True
        msg.processing_time_ms = 5.0
        
        self.publisher.publish(msg)
        self.get_logger().info(f'Published circular pattern: {count} positions')

def main():
    rclpy.init()
    node = CustomPatternPublisher()
    
    # Publish pattern
    node.publish_circular_pattern(radius=0.2, count=6, height=0.5)
    time.sleep(0.5)
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

**Usage:**
```bash
chmod +x custom_pattern.py
python3 custom_pattern.py
```

---

### ROS2 CLI Direct Publishing

Quick one-off tests without Python:

```bash
# Publish empty detection
ros2 topic pub --once /cotton_detection/results cotton_detection_ros2/msg/DetectionResult \
  "{header: {stamp: {sec: 0, nanosec: 0}, frame_id: 'camera_link'}, 
    positions: [], 
    total_count: 0, 
    detection_successful: true, 
    processing_time_ms: 1.0}"

# Publish single position
ros2 topic pub --once /cotton_detection/results cotton_detection_ros2/msg/DetectionResult \
  "{header: {stamp: {sec: 0, nanosec: 0}, frame_id: 'camera_link'}, 
    positions: [{position: {x: 0.3, y: 0.0, z: 0.5}, confidence: 0.95}], 
    total_count: 1, 
    detection_successful: true, 
    processing_time_ms: 2.0}"
```

---

## Monitoring and Debugging

### Monitor Detection Topic

```bash
# View full messages
ros2 topic echo /cotton_detection/results

# View just position count
ros2 topic echo /cotton_detection/results --field total_count

# View first position only
ros2 topic echo /cotton_detection/results --field 'positions[0].position'

# Check publishing rate
ros2 topic hz /cotton_detection/results

# Check message size
ros2 topic bw /cotton_detection/results
```

### Monitor yanthra_move Reception

```bash
# Check if yanthra is subscribed
ros2 topic info /cotton_detection/results
# Should show: Subscription count: 1

# Monitor yanthra logs (debug level)
ros2 topic echo /rosout | grep "cotton detection"

# Check yanthra status
ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus
```

### Verify Data Flow

```bash
# Terminal 1: Launch yanthra
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true

# Terminal 2: Start publisher
python3 scripts/testing/test_cotton_detection_publisher.py --continuous --rate 1.0

# Terminal 3: Verify both ends
echo "=== Publisher Output ==="
ros2 topic echo /cotton_detection/results --once

echo "=== yanthra Subscription ==="
ros2 topic info /cotton_detection/results

echo "=== End-to-end latency test ==="
ros2 topic echo /cotton_detection/results --field header.stamp & \
sleep 2 && \
python3 scripts/testing/test_cotton_detection_publisher.py --single
```

---

## Comparison with Real Camera

### When to Use Simulated Data

✅ **Good for:**
- Unit testing arm motion logic
- Testing extreme/edge case positions
- Regression testing without hardware
- Development on systems without camera
- Reproducible test scenarios
- Performance testing (no camera overhead)

❌ **Not sufficient for:**
- Camera calibration validation
- Detection algorithm testing
- Lighting/environment testing
- USB bandwidth issues
- Full system integration testing
- Field deployment validation

### When to Use Real Camera

Use real camera testing when:
- Validating camera parameters
- Testing actual field conditions
- Final system integration tests
- Pre-deployment validation
- Troubleshooting detection issues

---

## Coordinate Systems

### Camera Frame (`camera_link`)

Positions in the simulated data use camera frame coordinates:

```
         Z (up)
         │
         │
         │
         └────────► Y (right)
        ╱
       ╱
      X (forward)
```

**Typical Values:**
- `X`: 0.15 to 0.6 meters (forward from camera)
- `Y`: -0.3 to 0.3 meters (left/right)
- `Z`: 0.3 to 0.8 meters (height)

**Test Positions in Script:**
```python
test_positions = [
    (0.3, 0.1, 0.5),    # 30cm forward, 10cm right, 50cm up
    (0.25, -0.05, 0.45), # 25cm forward, 5cm left, 45cm up
    (0.35, 0.0, 0.55),   # 35cm forward, center, 55cm up
]
```

---

## Troubleshooting

### Issue: yanthra_move doesn't receive detections

**Check subscription:**
```bash
ros2 topic info /cotton_detection/results
# Should show: Subscription count: 1
```

**Check node is running:**
```bash
ros2 node list | grep yanthra
```

**Check QoS compatibility:**
```bash
ros2 topic info /cotton_detection/results --verbose
# Publisher and subscriber QoS must be compatible
```

---

### Issue: Positions are out of reach

**Symptom:** yanthra logs "Position unreachable" or IK fails

**Solution:** Adjust test positions to workspace limits:
```python
# Safe workspace for typical robot
safe_positions = [
    (0.25, 0.0, 0.4),   # Center, reachable
    (0.3, 0.1, 0.45),   # Slight right, reachable
    (0.28, -0.1, 0.42), # Slight left, reachable
]
```

---

### Issue: High latency between publish and motion

**Check system load:**
```bash
top
# CPU usage should be < 80%
```

**Check topic frequency:**
```bash
ros2 topic hz /cotton_detection/results
ros2 topic hz /joint_states
```

**Enable debug logging:**
```bash
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true \
  --log-level yanthra_move_system:=debug \
  --log-level motion_controller:=debug
```

---

## Integration with Phase 0 Testing Matrix

This simulated testing supplements the Phase 0 tests in `JANUARY_FIELD_TRIAL_TESTING_MATRIX.md`:

| Test # | Test | Simulated? | Notes |
|--------|------|-----------|--------|
| 0.12 | Camera launch | ❌ | Needs real hardware |
| 0.13 | Detection service | ❌ | Needs real camera |
| 0.14 | Auto-reconnect | ❌ | Needs USB test |
| 0.15 | No-cotton behavior | ✅ | Can test with `--count 0` |
| 0.19 | Arm launch | ✅ | Works with simulation |
| 0.20 | TF tree | ✅ | Independent of camera |
| 0.21 | Arm status | ✅ | Independent of camera |

**Recommended Workflow:**
1. Run simulated tests first (this guide)
2. Validate arm logic and edge cases
3. Then run full hardware tests with camera

---

## Related Documentation

- **Camera Integration:** `docs/guides/CAMERA_INTEGRATION_GUIDE.md`
- **Testing Matrix:** `docs/project-notes/JANUARY_FIELD_TRIAL_TESTING_MATRIX.md`
- **Cotton Detection Migration:** `docs/archive/2025-10/cotton_detection/MIGRATION_GUIDE.md`
- **ROS2 Interface Spec:** `docs/ROS2_INTERFACE_SPECIFICATION.md`

---

## Summary

**Quick Reference Commands:**

```bash
# Single detection (most common)
python3 scripts/testing/test_cotton_detection_publisher.py --single

# Continuous testing
python3 scripts/testing/test_cotton_detection_publisher.py --continuous --rate 2.0

# Custom position
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.3 0.0 0.5

# Monitor reception
ros2 topic echo /cotton_detection/results

# Check yanthra subscribed
ros2 topic info /cotton_detection/results
```

**Key Points:**
- Publishes to same topic as real camera (`/cotton_detection/results`)
- Uses same message format (`DetectionResult`)
- yanthra_move cannot tell the difference
- Perfect for development and regression testing
- Supplement, not replace, real camera testing
